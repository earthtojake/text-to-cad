import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { scenePartCount, viewFeaturesForKind } from "@text-to-cad/core/common/viewSettings.js";
import { useExportView } from "../../export/context.js";
import { useViewerHost } from "../../host/context.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { useMotionExclusion } from "../kit/tools/model-effects/motionExclusion.js";
import { useSceneToolState, useSceneTools } from "../kit/tools/sceneTools.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { useSceneReferences } from "../kit/tools/select/sceneReferences.jsx";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { useI18n } from "@text-to-cad/ui/i18n";

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const NO_REFERENCES = Object.freeze([]);
const EXPLODE_OFF = Object.freeze({ exploded: { enabled: false, amount: 0 } });
const CLIP_OFF = Object.freeze({ clip: { enabled: false, axis: "x", invert: false } });

/**
 * Whether a loaded scene carries an FEA result: a mesh `cadgen fea solve` wrote. Its generator alone says so; what
 * else the result holds is `feaResult.js`'s to read, and one that does not read is the load's alert, never a plain GLB.
 */
function carriesFeaResult(root) {
  let found = false;
  root?.traverse?.((object) => {
    if (!found && object?.isMesh && object.geometry && object.userData?.generator === "cadgen fea") found = true;
  });
  return found;
}

// The FEA result viewer (`feaView.jsx`), once a result has loaded it, for every result after it.
let feaView = null;
/** Loads the FEA result viewer: its own chunk, which a plain GLB never fetches. */
export const loadFeaView = () => import("./feaView.jsx").then((module) => { feaView = module; return module; });

/**
 * The FEA result viewer for a scene that carries a result, loaded the first time one does; `pending` while it
 * loads. A plain GLB's is null. Should the chunk fail to load, `error` says so, and the result is not drawn as
 * the plain GLB it is not.
 */
function useFeaView(root) {
  const wanted = useMemo(() => carriesFeaResult(root), [root]);
  const [kit, setKit] = useState(feaView);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!wanted || kit || error) return undefined;
    let live = true;
    loadFeaView().then((module) => { if (live) setKit(module); }, (failure) => { if (live) setError(failure); });
    return () => { live = false; };
  }, [wanted, kit, error]);
  return { kit: wanted && kit ? kit : null, pending: wanted && !kit && !error, error: wanted ? error : null };
}

/**
 * A GLB file: its scene, loaded once, drawn by the FEA result viewer when it carries a result (`FeaSurface.jsx`,
 * its own surface over the same shell) and by the GLB surface below otherwise. A result waits for its viewer as
 * the file loading, so it is framed once, as that viewer draws it.
 */
function GlbFile({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useGlbScene({ entry: document.entry, resources: document.client.resources });
  const { kit: fv, pending, error } = useFeaView(loaded.scene?.document?.scene);
  if (fv) return <fv.FeaSurface view={view} document={document} loaded={loaded} fv={fv} />;
  return <GlbSurface view={view} document={document} loaded={loaded} pending={pending} feaError={error} />;
}

function GlbSurface({ view, document, loaded, pending, feaError }) {
  const { t } = useI18n();
  const scene = pending || feaError ? null : loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error || feaError, modelKey: document.modelKey, hasScene: Boolean(scene), t
  }), [document.catalogError, loaded.error, feaError, document.modelKey, scene, t]);

  const shellRef = useRef(null);
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  // A routine let go puts its nodes back at rest, under Explode's: Explode puts them back out.
  const animation = useGlbAnimation(scene?.document || null, () => { sceneRef.current?.syncExplode?.(); shellRef.current?.requestRender(); });
  const preview = usePreviewState();
  const previewing = preview.previewing;
  // A routine takes the nodes where they were authored: Explode lets go of them before it plays,
  // so the routine starts from (and goes back to) rest, never from where Explode put them.
  const explodeAppliedRef = useRef(false);
  const routine = useMemo(() => {
    if (!animation) return null;
    const settle = run => (...args) => {
      if (explodeAppliedRef.current) {
        sceneRef.current?.setExplode?.(0);
        shellRef.current?.viewSettings.store.patch(EXPLODE_OFF);
      }
      return run(...args);
    };
    return { ...animation, onPlayToggle: settle(animation.onPlayToggle), onScrub: settle(animation.onScrub),
      onClipSelect: settle(animation.onClipSelect), onRestart: settle(animation.onRestart) };
  }, [animation]);

  // ---- tools: Select (its nodes), Annotate, Measure, Explode, Clip --------------------------
  const tools = useSceneToolState({ toolModes: GLB_TOOL_MODES, previewing, fileKey: document.modelKey, revision: loaded.revision,
    measurable: true, resource: document.resource });
  const { measure } = tools;
  const requestHighlightFrame = useCallback(() => shellRef.current?.requestFrame?.(), []);
  const selection = useSceneSelection({ scene, requestRender: requestHighlightFrame });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  // Parts where the file has several meshes to colour, Explode where it has several rigid nodes that draw (`glbScene.js`).
  const features = useMemo(() => viewFeaturesForKind("glb", { parts: scenePartCount(scene), explodeParts: scene?.explodeParts || 0 }), [scene]);
  const live = useMemo(() => ({
    declined: GLB_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => selectionRef.current.clear() },
    state: () => ({ selectedNodes: [...selectionRef.current.selected] })
  }), []);
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const escape = useMemo(() => ({
    active: selection.active || measure.drafting || measure.selected.length > 0,
    // Escape cancels a measurement in progress, then lets go of what is picked.
    handle: () => {
      const now = measureRef.current;
      if (now.drafting) { now.cancelDraft(); return true; }
      if (now.selected.length) { now.select([]); return true; }
      if (selectionRef.current.active) { selectionRef.current.clear(); return true; }
      return false;
    }
  }), [selection.active, measure.drafting, measure.selected.length]);

  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features, toolModes: GLB_TOOL_MODES, tool: tools.tool, previewable: true, preview, scene, sceneEffects: true,
    load: { busy: (loaded.busy || pending) && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation: routine, live, escape, deleteSelection: measure.removeSelected
  });
  shellRef.current = shell;
  useDeclinedSelectReference(document);

  // ---- one motion at a time: Explode, the routine and Clip --------------------------------
  const { view: viewSettings, store } = shell.viewSettings;
  const explodeApplied = Boolean(viewSettings.exploded?.enabled && viewSettings.exploded.amount > 0);
  const clipApplied = Boolean(viewSettings.clip?.enabled);
  explodeAppliedRef.current = explodeApplied;
  useMotionExclusion(document.modelKey, {
    explode: { applied: explodeApplied, reset: () => store.patch(EXPLODE_OFF) },
    clip: { applied: clipApplied, reset: () => store.patch(CLIP_OFF) },
    animation: { applied: Boolean(animation?.enabled), reset: () => animation?.onRelease() }
  });

  // ---- Preview: its own scene, the editor's sibling over its geometry, and its own routine ---
  const previewScene = usePreviewScene(scene, previewing);
  const previewAnimation = useGlbAnimation(previewScene?.document || null, () => shell.frame.previewViewRef.current?.requestRender?.());
  const previewView = useMemo(() => ({ scene: previewScene, animation: previewAnimation }), [previewScene, previewAnimation]);

  // Export converts the file shown to the other two mesh kinds: its path names it and the bytes on
  // screen (their catalog hash) are its revision; the server refuses a file that has changed since.
  const host = useViewerHost();
  const exportView = useMemo(() => scene && loaded.revision && document.modelKey && !host.environment.compact ? {
    doc: document.modelKey, revision: loaded.revision, file: view.file.path, name: view.file.name
  } : null, [scene, loaded.revision, document.modelKey, host.environment.compact, view.file.path, view.file.name]);
  useExportView(exportView);
  const sceneTools = useSceneTools({ shell, scene, features, state: tools, measurable: true, clearParts: selection.clear });
  const selectActive = !previewing && Boolean(scene) && shell.toolMode === GLB_TOOL.SELECT;
  const strip = [shell.tools.own({ id: GLB_TOOL.SELECT, label: t("tool.select"), shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON }), ...sceneTools.tools];
  const { references, chips } = useSceneReferences({ scene, selection, resource: shell.frame.resource });
  const resourcePath = shell.frame.resource?.path;
  const nameNode = useCallback(reference => {
    const id = reference?.resource?.path === resourcePath && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const part = id ? sceneRef.current?.describePart?.(id) : null;
    return part ? { name: part.name, kind: "solid" } : "";
  }, [resourcePath]);
  const handlePick = useCallback((hit, modifiers) => {
    selection.pick(hit, modifiers);
    if (hit && !modifiers?.multiSelect) measureRef.current.select([]);
  }, [selection.pick]);

  return <RendererShell shell={shell} tools={strip} subToolbar={sceneTools.subToolbar} previewView={previewView}
    references={previewing ? NO_REFERENCES : references} referenceChips={previewing ? NO_REFERENCES : chips} nameReference={nameNode}
    onClearReferences={() => { selection.clear(); measure.select([]); }}
    onSelectPress={sceneTools.onSelectPress} onSelectHover={sceneTools.onSelectHover}
    viewportOverlay={viewport => <>
      {sceneTools.overlay(viewport)}
      <PointerPick viewport={viewport} scene={scene} enabled={selectActive} onPick={handlePick} onHover={selection.hoverHit} />
    </>} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbFile key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

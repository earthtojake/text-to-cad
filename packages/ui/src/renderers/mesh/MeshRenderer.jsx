import { useCallback, useEffect, useMemo, useRef } from "react";
import { MousePointer2 } from "lucide-react";
import { scenePartCount, viewFeaturesForKind } from "@cad/core/common/viewSettings.js";
import { useExportView } from "../../export/context.js";
import { useViewerHost } from "../../host/context.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { noGeometryAlert } from "../kit/status/loadAlerts.js";
import { useSceneToolState, useSceneTools } from "../kit/tools/sceneTools.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { sceneCopyText, useSceneDescribe, useSceneInspect, useSceneReferences } from "../kit/tools/select/sceneReferences.jsx";
import { sceneMenuEntries } from "../kit/tools/select/sceneMenu.js";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import SceneTreeSection from "../kit/inspector/SceneTreeSection.jsx";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { MESH_DECLINED_LIVE_COMMANDS, MESH_TOOL, STL_TOOL_MODES, THREE_MF_TOOL_MODES } from "./tools.js";
import { useMeshScene } from "./useMeshScene.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { useI18n } from "@cad/ui/i18n";

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const NO_REFERENCES = Object.freeze([]);

/** A slicer's print file (a 3MF of G-code, `useMeshScene`'s `sliced`): no model to draw, and nothing broken to retry or report. */
function slicedFileAlert(fileRef, t) {
  return { severity: "warning", reportable: false, summary: t("alert.sliced.summary"), title: t("alert.sliced.title"),
    message: t("alert.sliced.message", { file: fileRef }), recovery: t("alert.sliced.recovery") };
}

function MeshSurface({ view, data }) {
  const { t } = useI18n();
  const document = useWorkspaceDocument({ view, data });
  const loaded = useMeshScene({ entry: document.entry, resources: document.client.resources, name: view.file.name });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene), t
  }) || (loaded.sliced ? slicedFileAlert(document.modelKey, t) : loaded.empty ? noGeometryAlert(document.modelKey, t) : null),
  [document.catalogError, loaded.error, loaded.empty, loaded.sliced, document.modelKey, scene, t]);
  // A 3MF has objects and a unit; an STL has bodies (`stlBodies.js`) and no unit, so nothing to measure in.
  const threeMf = /\.3mf$/i.test(view.file.path);
  const toolModes = threeMf ? THREE_MF_TOOL_MODES : STL_TOOL_MODES;
  // Parts where the file has several objects or bodies to colour.
  const features = useMemo(() => viewFeaturesForKind(threeMf ? "3mf" : "stl", { parts: scenePartCount(scene) }), [threeMf, scene]);

  const shellRef = useRef(null);
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const preview = usePreviewState();
  const previewing = preview.previewing;
  const tools = useSceneToolState({ toolModes, previewing, fileKey: document.modelKey, revision: loaded.revision,
    measurable: threeMf, resource: document.resource });
  const { measure } = tools;
  const requestHighlightFrame = useCallback(() => shellRef.current?.requestFrame?.(), []);
  const selection = useSceneSelection({ scene, requestRender: requestHighlightFrame });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  // An STL's bodies arrive after its first scene (one body, the whole file): what was picked in it goes, since its
  // `b1` now names the largest body.
  useEffect(() => { if (loaded.split) selectionRef.current.clear(); }, [loaded.split]);
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const live = useMemo(() => ({
    declined: MESH_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => selectionRef.current.clear() },
    state: () => ({ selectedObjects: [...selectionRef.current.selected] })
  }), []);
  const escape = useMemo(() => ({
    active: selection.active || measure.drafting || measure.selected.length > 0,
    handle: ({ toolInHand = false } = {}) => {
      const now = measureRef.current;
      if (now.drafting) { now.cancelDraft(); return true; }
      // The tool in hand goes down first (the shell's), keeping what is picked, as a STEP's Escape does.
      if (toolInHand) return false;
      if (now.selected.length) { now.select([]); return true; }
      if (selectionRef.current.active) { selectionRef.current.clear(); return true; }
      return false;
    }
  }), [selection.active, measure.drafting, measure.selected.length]);

  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features, toolModes, tool: tools.tool, previewable: true, preview, scene, sceneEffects: true,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live, escape, deleteSelection: measure.removeSelected,
    // A prompt's annotation is in the scene's coordinates: the file's own unit.
    annotationUnits: scene?.units?.unit || ""
  });
  shellRef.current = shell;
  useDeclinedSelectReference(document);
  // Preview's own scene: the editor's sibling, over its geometry.
  const previewScene = usePreviewScene(scene, previewing);
  const previewView = useMemo(() => ({ scene: previewScene }), [previewScene]);

  // Export converts the file shown to the other two mesh kinds: its path names it and the bytes on
  // screen (their catalog hash) are its revision; the server refuses a file that has changed since.
  const host = useViewerHost();
  const exportView = useMemo(() => scene && loaded.revision && document.modelKey && !host.environment.compact ? {
    doc: document.modelKey, revision: loaded.revision, file: view.file.path, name: view.file.name
  } : null, [scene, loaded.revision, document.modelKey, host.environment.compact, view.file.path, view.file.name]);
  useExportView(exportView);
  const sceneTools = useSceneTools({ shell, scene, features, state: tools, measurable: threeMf, clearParts: selection.clear });
  const selectActive = !previewing && Boolean(scene) && shell.toolMode === MESH_TOOL.SELECT;
  // Select picks a 3MF's objects and an STL's bodies.
  const strip = [shell.tools.own({ id: MESH_TOOL.SELECT, label: t("tool.select"), shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON }), ...sceneTools.tools];
  // The picked objects or bodies, as references (`model.3mf#o2.1`, `model.stl#b2`).
  const { references, chips } = useSceneReferences({ scene, selection, resource: shell.frame.resource });
  const resourcePath = shell.frame.resource?.path;
  const nameObject = useCallback(reference => {
    const id = reference?.resource?.path === resourcePath && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const part = id ? sceneRef.current?.describePart?.(id) : null;
    return part ? { name: part.name, kind: "solid" } : "";
  }, [resourcePath]);
  const handlePick = useCallback((hit, modifiers) => {
    selection.pick(hit, modifiers);
    if (hit && !modifiers?.multiSelect) measureRef.current.select([]);
  }, [selection.pick]);

  // The view's menu, under Select (`kit/tools/select/sceneMenu.js`): the reference, Select, the framing.
  const viewportRef = useRef(null);
  const contextMenuItems = scene && !previewing && shell.toolMode === MESH_TOOL.SELECT ? press => sceneMenuEntries({
    press, viewport: viewportRef.current, scene, selected: selectionRef.current.selected, t,
    copyText: hit => sceneCopyText(shell.frame.resource, [...new Set([...selectionRef.current.selected, hit.id])]),
    onCopy: text => { void Promise.resolve(host.clipboard.writeText(text)).catch(() => {}); },
    onSelect: (hit, selected) => selection.select(hit.id, { multiSelect: selected }),
    viewer: () => shellRef.current?.frame.viewerRef.current || null
  }) : null;

  const zoomToSelection = {
    available: selection.selected.length > 0 && Boolean(scene?.selectionBounds),
    run: () => { const box = scene?.selectionBounds?.(selectionRef.current.selected); if (box) shellRef.current?.frame.viewerRef.current?.zoomToBounds?.(box); }
  };

  // What is picked, as the frame reads it: the hover tip, and the chips' cards' rows.
  const described = useSceneDescribe(scene);
  const inspect = useSceneInspect({ scene: previewing ? null : scene, selection, describe: described });

  // The view's panel, from the first frame: its Model tab the file's objects or bodies (`SceneTreeSection.jsx`), as a
  // GLB's nodes are, a row each — a 3MF of one object, or an STL of one body, its one row — empty while the file loads.
  const sidebar = <SceneTreeSection tree={scene ? scene.nodeTree : null} selection={selection} active={!previewing}
    onPick={() => { if (shellRef.current?.toolMode !== MESH_TOOL.SELECT) shellRef.current?.selectTool(MESH_TOOL.SELECT); }} />;
  return <RendererShell shell={shell} tools={strip} contextMenuItems={contextMenuItems} zoomToSelection={zoomToSelection} subToolbar={sceneTools.subToolbar} previewView={previewView}
    inspect={inspect} sidebar={sidebar}
    references={previewing ? NO_REFERENCES : references} referenceChips={previewing ? NO_REFERENCES : chips} nameReference={nameObject}
    onClearReferences={() => { selection.clear(); measure.select([]); }}
    onSelectPress={sceneTools.onSelectPress} onSelectHover={sceneTools.onSelectHover}
    viewportOverlay={viewport => { viewportRef.current = viewport; return <>
      {sceneTools.overlay(viewport)}
      <PointerPick viewport={viewport} scene={scene} enabled={selectActive} onPick={handlePick} onHover={selection.hoverHit} takesAway={selection.takesAway} touchAdds />
    </>; }} />;
}

export default function MeshRenderer(props) {
  const { data, ...view } = props;
  return <MeshSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

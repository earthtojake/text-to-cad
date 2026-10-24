import { useCallback, useMemo, useRef } from "react";
import { MousePointer2 } from "lucide-react";
import { scenePartCount, viewFeaturesForKind } from "@text-to-cad/core/common/viewSettings.js";
import { useExportView } from "../../export/context.js";
import { useViewerHost } from "../../host/context.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { noGeometryAlert } from "../kit/status/loadAlerts.js";
import { useSceneToolState, useSceneTools } from "../kit/tools/sceneTools.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { useSceneReferences } from "../kit/tools/select/sceneReferences.jsx";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { MESH_DECLINED_LIVE_COMMANDS, MESH_TOOL, STL_TOOL_MODES, THREE_MF_TOOL_MODES } from "./tools.js";
import { useMeshScene } from "./useMeshScene.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const NO_REFERENCES = Object.freeze([]);

function MeshSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useMeshScene({ entry: document.entry, resources: document.client.resources });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }) || (loaded.empty ? noGeometryAlert(document.modelKey) : null),
  [document.catalogError, loaded.error, loaded.empty, document.modelKey, scene]);
  // A 3MF has objects and a unit; an STL is one mesh in none.
  const parted = /\.3mf$/i.test(view.file.path);
  const toolModes = parted ? THREE_MF_TOOL_MODES : STL_TOOL_MODES;
  // Parts where a 3MF has several objects to colour; an STL is one mesh.
  const features = useMemo(() => viewFeaturesForKind(parted ? "3mf" : "stl", { parts: scenePartCount(scene) }), [parted, scene]);

  const shellRef = useRef(null);
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const preview = usePreviewState();
  const previewing = preview.previewing;
  const tools = useSceneToolState({ toolModes, previewing, fileKey: document.modelKey, revision: loaded.revision,
    measurable: parted, resource: document.resource });
  const { measure } = tools;
  const requestHighlightFrame = useCallback(() => shellRef.current?.requestFrame?.(), []);
  const selection = useSceneSelection({ scene: parted ? scene : null, requestRender: requestHighlightFrame });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const live = useMemo(() => ({
    declined: MESH_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => selectionRef.current.clear() },
    state: () => ({ selectedObjects: [...selectionRef.current.selected] })
  }), []);
  const escape = useMemo(() => ({
    active: selection.active || measure.drafting || measure.selected.length > 0,
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
    doc: document.modelKey, revision: loaded.revision, file: view.file.path, name: view.file.name, preview: previewing
  } : null, [scene, loaded.revision, document.modelKey, host.environment.compact, view.file.path, view.file.name, previewing]);
  useExportView(exportView);
  const sceneTools = useSceneTools({ shell, scene, features, state: tools, measurable: parted, clearParts: selection.clear });
  const selectActive = parted && !previewing && Boolean(scene) && shell.toolMode === MESH_TOOL.SELECT;
  // Select on every mesh file: an STL's picks nothing, the view's plain navigation.
  const strip = [shell.tools.own({ id: MESH_TOOL.SELECT, label: "Select", shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON }), ...sceneTools.tools];
  // A 3MF's picked objects; an STL's Quick Edit carries the whole file and nothing picked in it.
  const { references, chips } = useSceneReferences({ scene: parted ? scene : null, selection, resource: shell.frame.resource });
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

  return <RendererShell shell={shell} tools={strip} subToolbar={sceneTools.subToolbar} previewView={previewView}
    references={previewing ? NO_REFERENCES : references} referenceChips={previewing ? NO_REFERENCES : chips} nameReference={nameObject}
    onClearReferences={() => { selection.clear(); measure.select([]); }}
    onSelectPress={sceneTools.onSelectPress} onSelectHover={sceneTools.onSelectHover}
    viewportOverlay={viewport => <>
      {sceneTools.overlay(viewport)}
      {parted ? <PointerPick viewport={viewport} scene={scene} enabled={selectActive} onPick={handlePick} onHover={selection.hoverHit} /> : null}
    </>} />;
}

export default function MeshRenderer(props) {
  const { data, ...view } = props;
  return <MeshSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

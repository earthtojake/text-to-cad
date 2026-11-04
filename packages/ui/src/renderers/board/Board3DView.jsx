import { useI18n } from "@cad/ui/i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { MousePointer2 } from "lucide-react";
import { buildBoardRefToken, parseBoardRefSelector, splitBoardRefSelectors } from "@cad/core/lib/boardRefs.js";
import { scenePartCount, viewFeaturesForKind } from "@cad/core/common/viewSettings.js";
import { isAbortError, loadRenderGlbDocument } from "@cad/core/lib/renderAssetClient.js";
import { disposeGlbDocument } from "@cad/core/lib/render/glbMeshData.js";
import { createGlbScene } from "@cad/core/lib/render/glbScene.js";
import { DRAWING_TOOLS } from "../../annotation/toolbar.jsx";
import { useViewerHost } from "../../host/context.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { VIEWPORT_INSET_PX } from "../kit/shell/viewportLayout.js";
import { failureAlert } from "../kit/status/loadAlerts.js";
import ViewerAlertCard from "../kit/status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../kit/status/ViewerLoadingOverlay.js";
import FloatingToolBar, { StripTouchProvider } from "../kit/tools/FloatingToolBar.js";
import { createToolModes } from "../kit/tools/toolModes.js";
import { useSceneToolState, useSceneTools } from "../kit/tools/sceneTools.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { BoardViewItems, boardViewOnlyControls } from "./BoardDisplay.jsx";
import BoardSection from "./BoardSection.jsx";

/**
 * A KiCad board in 3D: KiCad's own 3D model of it (`kicad-cli pcb export glb`: its body, copper, silkscreen,
 * solder mask and parts' models), made by the server in the background and kept by the board's bytes
 * (`client.boardModel`, `GET /api/v1/documents/kicad_pcb/<id>/glb`), shown on the stage every 3D file is shown
 * on (`kit/shell/RendererShell.jsx`, the GLB renderer's scene, `glbScene.js`): orbit, the view cube, the
 * theme, Projection, Display's modes and Grid, Measure, Explode, Clip and Preview. Display leads with the
 * board's View (2D or 3D, `BoardDisplay.jsx`'s `BoardViewItems`), the way back to the 2D picture.
 *
 * It is the board's other half (`BoardRenderer.jsx`'s `BoardFile`): the Circuit, the selection, what is
 * isolated, the chips and Quick Edit are the board's, one with its 2D view's. KiCad names each part's node
 * in its GLB by its reference (`U3`): a press on a part picks it as a press on it in 2D does (the Circuit
 * reveals it, a chip names it, Quick Edit carries `#U3`), and what is selected in the Circuit or in 2D is lit
 * here (a pad, its part); a part isolated shows alone. Its copper, mask and body are one mesh each: a press
 * there picks nothing. A part KiCad found no model file for is drawn as KiCad draws it: not at all.
 *
 * Quick Edit carries what is selected, never a view of this one: a board's snapshot replays its 2D picture.
 * So there is no Pencil or Shapes here. Until the model is first made, the shared loading screen says
 * where KiCad is, the View tile above it (2D is one choice away); a model KiCad could not make is the
 * alert card's, with the same tile.
 */

export const BOARD3D_TOOL = Object.freeze({ SELECT: "select", MEASURE: "measure" });
export const BOARD3D_TOOL_MODES = createToolModes({
  defaultMode: BOARD3D_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(BOARD3D_TOOL).map(mode => [mode, {}]))
});
const DRAWING = new Set(DRAWING_TOOLS.map(tool => tool.id));
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
// Nothing declined: the camera and the 3D Display are the stage's, a selection the board's (`live`).
const BOARD3D_DECLINED = Object.freeze({});
const INSET = `${VIEWPORT_INSET_PX}px`;
// The board's model being made, in the engine's words for it (`progress.board-model.<stage>`), then read.
const progressOf = frame => Object.freeze({ phase: "read", label: `progress.${frame.kind}.${frame.stage}`, done: 0, total: 0, determinate: false });
const WAITING = progressOf({ kind: "board-model", stage: "queued" });
const LOADING = Object.freeze({ phase: "geometry", label: "Loading geometry", done: 0, total: 1, determinate: true });

/**
 * The board's 3D model on screen: asked for and waited on (each stage heard), read, and made a scene. A new
 * revision of the board is made behind the model on screen, which stays until the new one is read.
 *
 * @returns {{ scene: object | null, key: string, modelled: string[], missing: string[], busy: boolean, progress: object | null, error: unknown }}
 */
export function useBoardModel({ client, file, revision }) {
  const [state, setState] = useState({ scene: null, key: "", modelled: [], missing: [], busy: true, progress: WAITING, error: null });
  const sceneRef = useRef(null);
  const adopt = scene => {
    const previous = sceneRef.current;
    sceneRef.current = scene;
    previous?.dispose();
  };
  useEffect(() => () => adopt(null), []);
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    setState(current => ({ ...current, busy: true, error: null, progress: current.scene ? current.progress : WAITING }));
    (async () => {
      const made = await client.boardModel(file, { signal, onProgress: frame => setState(current => ({ ...current, progress: progressOf(frame) })) });
      if (signal.aborted) return;
      setState(current => ({ ...current, progress: current.scene ? current.progress : LOADING }));
      const document = await loadRenderGlbDocument(made.url, { resources: client.resources, signal });
      if (signal.aborted) { disposeGlbDocument(document); return; }
      const scene = createGlbScene(THREE, document);
      adopt(scene);
      setState({ scene, key: made.key, modelled: made.modelled, missing: made.missing, busy: false, progress: null, error: null });
    })().catch(error => {
      if (signal.aborted || isAbortError(error)) return;
      setState(current => ({ ...current, busy: false, progress: null, error }));
    });
    return () => controller.abort();
  }, [client, file, revision]);
  return state;
}

/**
 * A KiCad GLB's parts, by reference: each part's node (named for it, `U3`) and the nodes under it that draw
 * (`n12`, the scene's picks), where the board's index has that part.
 */
export function boardPartNodes(scene, index) {
  const nodes = new Map(), refOf = new Map();
  scene?.document?.scene?.traverse?.(object => {
    const name = String(object.userData?.name || object.name || "");
    if (!name || nodes.has(name) || !index?.resolve(`#${name}`) || index.resolve(`#${name}`).kind !== "part") return;
    const drawn = [];
    object.traverse(child => { const id = child.isMesh ? child.userData?.partId : null; if (id && !drawn.includes(id)) drawn.push(id); });
    if (!drawn.length) return;
    nodes.set(name, { ids: drawn, object });
    for (const id of drawn) refOf.set(id, name);
  });
  return { nodes, refOf };
}

/** The part a board selector names (a part's, or a pad's part's), or "". */
function partOf(index, selector) {
  const found = index?.resolve(selector);
  return found?.kind === "part" ? found.part.ref : found?.kind === "pad" ? found.pad.ref : "";
}

function Board3DWaiting({ view, workspace, model, viewChoice: boardView }) {
  const { t } = useI18n();
  const mobile = useViewerMobile();
  const file = workspace.modelKey || view.file.path;
  const alert = model.error ? { ...failureAlert(file, model.error?.message || model.error, model.error?.failure, false, t),
    title: t("board.text.couldn_t_draw_the_board_in_3d") } : null;
  return <div className="@container/cad-viewport relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
    data-slot="cad-file-view" data-board-model="waiting" aria-busy={alert ? "false" : "true"}>
    <ViewerLoadingOverlay loading={alert ? null : { opening: true, progress: model.progress }} operationKey={file} />
    {/* View over the loading screen: 2D is one choice away while KiCad works, or once it could not. */}
    {view.appearance?.compact ? null : <div className="pointer-events-none absolute z-30 flex flex-col items-center" style={{ top: INSET, left: INSET, right: INSET }}
      data-cad-tool-groups=""><StripTouchProvider value={mobile}>
        <FloatingToolBar tools={[]} views={boardViewOnlyControls({ boardView, t })} touch={mobile} />
      </StripTouchProvider></div>}
    {alert ? <ViewerAlertCard alert={alert} hasContent={false} dismissed={false} onDismiss={() => {}} onReload={view.reload} file={file} /> : null}
  </div>;
}

function Board3DStage({ view, workspace, document, files, display, isolation, scene: boardScene, selection, references, chips, nameReference, sink,
  viewChoice: boardView, model }) {
  const { t } = useI18n();
  const host = useViewerHost();
  const scene = model.scene;
  const { index } = document;
  // The 3D view's own record (its camera, its Display), kept inside the board's.
  const { write } = files;
  const shellView = useMemo(() => ({ ...view, state: files.record.current.scene3d, onStateChange: record => write({ scene3d: record }) }),
    [view, files, write]);
  const preview = usePreviewState();
  const tools = useSceneToolState({ toolModes: BOARD3D_TOOL_MODES, previewing: preview.previewing, fileKey: workspace.modelKey, revision: model.key,
    measurable: true, resource: workspace.resource });
  const { measure } = tools;
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const indexRef = useRef(index);
  indexRef.current = index;
  const displayRef = useRef(display);
  displayRef.current = display;
  const features = useMemo(() => viewFeaturesForKind("glb", { parts: scenePartCount(scene), explodeParts: scene?.explodeParts || 0 }), [scene]);
  const live = useMemo(() => ({
    declined: BOARD3D_DECLINED,
    commands: {
      select(request) {
        const raw = Array.isArray(request) ? request : Array.isArray(request?.selectors) ? request.selectors : [request?.selector ?? request];
        const list = raw.flatMap(selector => splitBoardRefSelectors(selector));
        const board = indexRef.current;
        const unknown = list.filter(selector => !parseBoardRefSelector(selector) || !board?.resolve(selector));
        if (!board || unknown.length) throw new Error(`Not on this board: ${unknown.join(", ") || list.join(", ")}. Select board references such as #U3, #U3.9, #net:VIN.`);
        selectionRef.current.clear();
        for (const selector of list) selectionRef.current.select(parseBoardRefSelector(selector).canonical, { multiSelect: true });
      },
      clearSelection: () => selectionRef.current.clear()
    },
    state: () => ({ boardView: "3d", boardDisplay: { ...displayRef.current } })
  }), []);
  const measureRef = useRef(measure);
  measureRef.current = measure;
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
  const updateAlert = model.error && scene ? { severity: "error", kind: "status", blocking: false, title: t("board.text.couldn_t_draw_the_board_in_3d"),
    message: String(model.error?.message || model.error) } : null;
  const shell = useRendererShell({
    view: shellView, services: workspace.services, resource: workspace.resource, modelKey: workspace.modelKey, revisionKey: model.key,
    features, toolModes: BOARD3D_TOOL_MODES, tool: tools.tool, previewable: true, preview, scene, sceneEffects: true,
    load: { busy: false, updating: model.busy, progress: model.progress, alert: updateAlert, replayUnavailable: t("board.text.not_replayed_in_3d") },
    live, escape, deleteSelection: measure.removeSelected
  });
  const shellRef = useRef(shell);
  shellRef.current = shell;

  // ---- the board's selection, lit on its parts' nodes; what is isolated shown alone -------------
  const parts = useMemo(() => boardPartNodes(scene, index), [scene, index]);
  useEffect(() => {
    const own = sink.current;
    const nodesOf = selectors => selectors.flatMap(selector => parts.nodes.get(partOf(index, selector))?.ids || []);
    own.highlight = (_ink, named) => scene?.setHighlight({ hovered: nodesOf(named.hovered), selected: nodesOf(named.selected) });
    own.paint = () => shellRef.current?.requestFrame?.();
    own.highlight(own.ink, own.named);
    own.paint();
    return () => { own.highlight = null; own.paint = null; };
  }, [scene, parts, index, sink]);
  useEffect(() => {
    const alone = new Set(isolation.isolated.map(selector => partOf(index, selector)).filter(Boolean));
    for (const [ref, { object }] of parts.nodes) {
      const shown = !alone.size || alone.has(ref);
      object.traverse(child => { if (child.isMesh) child.visible = shown; });
    }
    shellRef.current?.requestRender?.();
  }, [parts, isolation.isolated, index]);
  const pickScene = useMemo(() => ({
    pick(ray) {
      const hit = scene?.pick(ray);
      const ref = hit ? parts.refOf.get(hit.id) : "";
      const selector = ref ? index?.resolve(`#${ref}`)?.selector : "";
      return selector ? { id: selector, point: hit.point } : null;
    }
  }), [scene, parts, index]);

  // ---- tools: Select (the board's parts), Measure, Explode, Clip; Preview ---------------------
  const previewScene = usePreviewScene(scene, shell.previewing);
  const previewView = useMemo(() => ({ scene: previewScene, animation: null }), [previewScene]);
  const sceneTools = useSceneTools({ shell, scene, features, state: tools, measurable: true, clearParts: selection.clear });
  const selectActive = !shell.previewing && Boolean(scene) && shell.toolMode === BOARD3D_TOOL.SELECT;
  const strip = [shell.tools.own({ id: BOARD3D_TOOL.SELECT, label: t("tool.select"), shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON }),
    ...sceneTools.tools.filter(tool => !DRAWING.has(tool.id))];
  const handlePick = useCallback((hit, modifiers) => {
    selectionRef.current.pick(hit, modifiers);
    if (hit && !modifiers?.multiSelect) measureRef.current.select([]);
  }, []);
  const path = workspace.resource?.kind === "workspace-file" ? workspace.resource.path : "";
  const copySelection = selection.selected.length && path ? () => {
    void Promise.resolve(host.clipboard.writeText(buildBoardRefToken({ path, selectors: selectionRef.current.selected }))).catch(() => {});
    return true;
  } : null;
  const sidebar = index ? <BoardSection index={index} selection={selection} isolated={isolation.isolated} onIsolate={isolation.toggle}
    onSelect={() => shell.selectTool(BOARD3D_TOOL.SELECT)} /> : null;

  return <RendererShell shell={shell} tools={strip} subToolbar={sceneTools.subToolbar} previewView={previewView} sidebar={sidebar}
    references={shell.previewing ? [] : references} referenceChips={shell.previewing ? [] : chips} nameReference={nameReference}
    onClearReferences={() => { selection.clear(); measure.select([]); }} copySelection={copySelection} selectsAnnotations={false}
    onSelectPress={sceneTools.onSelectPress} onSelectHover={sceneTools.onSelectHover}
    displayLead={boardView ? <BoardViewItems boardView={boardView} /> : null}
    viewportOverlay={viewport => <>
      {sceneTools.overlay(viewport)}
      <PointerPick viewport={viewport} scene={pickScene} enabled={selectActive} onPick={handlePick} onHover={hit => selectionRef.current.hover(hit?.id || "")} />
    </>} />;
}

/** The board's 3D half (the module): the loading screen until its model is first read, then the stage. */
export default function Board3DSurface(props) {
  const { workspace, document } = props;
  const model = useBoardModel({ client: workspace.client, file: document.file, revision: String(workspace.resource?.revision || "") });
  // A host asked for the view at once: the Display's View is on screen either way.
  useEffect(() => { props.view.onReady?.(true); }, [props.view.onReady]);
  if (!model.scene || !document.index) return <Board3DWaiting {...props} model={model.scene ? { ...model, progress: model.progress || LOADING } : model} />;
  return <Board3DStage {...props} model={model} />;
}

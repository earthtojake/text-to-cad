import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { viewFeaturesForKind } from "@text-to-cad/core/common/viewSettings.js";
import { sceneFramingBounds } from "@text-to-cad/core/lib/viewer/sceneContract.js";
import { boundsInUnits } from "@text-to-cad/core/lib/viewer/sceneUnits.js";
import { fetchXbfPartGroups } from "@text-to-cad/core/lib/xbf/xbfDocument.js";
import { parseXbfElementId } from "@text-to-cad/core/lib/xbf/xbfScene.js";
import { useExportView } from "../../export/context.js";
import { useViewerHost } from "../../host/context.js";
import { readFileView } from "../kit/shell/fileView.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { useViewportLoadStatus } from "../kit/shell/useViewportLoadStatus.js";
import { buildFailedAlert, noGeometryAlert, staleBuildAlert } from "../kit/status/loadAlerts.js";
import { useI18n } from "@text-to-cad/ui/i18n";
import { useModelTools } from "../kit/tools/model-effects/ModelTools.jsx";
import { useMotionExclusion } from "../kit/tools/model-effects/motionExclusion.js";
import { useMeasureSession } from "../kit/tools/measure/useMeasureSession.js";
import { MeasurementsBar } from "../kit/tools/measure/measurementChips.jsx";
import { measureSelectHandlers } from "../kit/tools/measure/measureSelection.js";
import MeasureFilterMenu, { MEASURE_MODES } from "../kit/tools/measure/MeasureFilterMenu.jsx";
import { MEASURE_FILTER_DEFAULT } from "../kit/tools/measure/measureFilter.js";
import JointHandleOverlay from "../kit/tools/pose/JointHandleOverlay.jsx";
import { pickModeOf, selects } from "../kit/tools/select/selectFilter.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { usePointerPick } from "../kit/tools/select/usePointerPick.js";
import { prefersCoarsePointer } from "../kit/viewport/dom.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { createClickActivation } from "./clickActivation.js";
import XbfMeasureOverlay from "./XbfMeasure.jsx";
import XbfModelTree from "./XbfModelTree.jsx";
import XbfPositionSection, { useXbfPose, writeXbfPosition, xbfPoseGiven, xbfPositionRows } from "./XbfPositionSection.jsx";
import { MeasureIcon, SelectIcon, SelectModeMenu, XBF_SELECT_DEFAULT, xbfSelectModes } from "./XbfSelectionModes.jsx";
import { useXbfElementFacts, useXbfSelectionChips, xbfCopyText, xbfNodeRefs } from "./xbfChips.jsx";
import { xbfJointHandles } from "./xbfJointHandles.js";
import { viewportMenuEntries } from "./xbfMenuItems.js";
import { xbfModelMenu, xbfPartMenu, xbfTopologyMenu } from "./xbfMenus.js";
import { NO_CONNECTED_SELECTION, nextSelectionIds, selectGeometryMode, treeShape } from "./xbfSelectionFilter.js";
import { isXbfAssemblyId, presentXbfTree, xbfAssemblyIds, xbfCoveringIds, xbfPickFrontier } from "./xbfTree.js";
import { XBF_DECLINED_LIVE_COMMANDS, XBF_TOOL, XBF_TOOL_MODES } from "./tools.js";
import { xbfLookSubject } from "./xbfLookAt.js";
import { readXbfView, xbfViewSignatures, xbfViewSlices } from "./xbfViewSlices.js";
import { useXbfScene } from "./useXbfScene.js";
import { useXbfMotion } from "./useXbfMotion.js";

// An engine document in the viewer, exactly as a STEP is: the same tools in the same order
// (Select with its filter, Pencil, Shapes, Measure, Explode, Clip), the same selection (Parts, Faces and
// Edges as the filter ticks them, a collapsed assembly picked as a unit, a part's faces and edges
// once it is open, Group faces and Group edges), the same file sidebar (Model tree, Position), the
// same menus, the same Quick Edit chips; and, for a document with motions, the file sidebar's
// Motion section, the shell's routine transport playing them (`useXbfMotion.js`). What differs is
// underneath: the document is read from the engine that serves it, and every face and edge is to
// hand from the start, so nothing waits on topology.

const NO_REFERENCES = Object.freeze([]);
const EMPTY = Object.freeze([]);
const NO_HOVER = Object.freeze({ parts: EMPTY, element: null });
const EXPLODE_OFF = Object.freeze({ exploded: { enabled: false, amount: 0 } });
const isElementId = id => String(id).includes("/");

/** The selection after a pick of a part or subassembly, as a STEP's: a plain pick drops the faces and edges. */
function pickNode(current, id, multiSelect) {
  const nodes = current.filter(item => !isElementId(item)), elements = current.filter(isElementId);
  if (!multiSelect && elements.length) return [id];
  const next = nextSelectionIds(nodes, [id], multiSelect);
  return multiSelect ? [...next, ...elements] : next;
}

/** The selection after a pick of faces or edges (one, or a grown group): a plain pick drops the parts. */
function pickElements(current, ids, multiSelect) {
  const nodes = current.filter(item => !isElementId(item)), elements = current.filter(isElementId);
  if (!multiSelect && nodes.length) return [...ids];
  const next = nextSelectionIds(elements, ids, multiSelect);
  return multiSelect ? [...nodes, ...next] : next;
}

/** Every selection id at and under `ids` in the tree: what an isolation keeps in reach. */
function subtreeIds(tree, ids) {
  const found = new Set();
  const visit = node => { if (node.selectionId) found.add(node.selectionId); (node.children || EMPTY).forEach(visit); };
  for (const id of ids) { const node = tree.nodes.get(id); if (node) visit(node); }
  return found;
}

function XbfSurface({ view, data }) {
  const host = useViewerHost();
  const document = useWorkspaceDocument({ view, data });
  const loaded = useXbfScene({ client: document.client, file: view.file.path });
  const scene = loaded.scene;
  const source = loaded.document?.source?.url || "";
  // What every later read of the document's engine is made with: the fetch it was read with.
  const engineFetch = loaded.document?.fetch;
  const { t } = useI18n();
  // A failed build of the file is said over the version on screen, the last that built; the view
  // updates by itself when one succeeds. A model shown from its last build though its code changed
  // since (the engine's `stale`) says so, with the command that builds it again.
  const stale = loaded.document?.structure?.stale || null;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }) || (loaded.failed ? buildFailedAlert(document.modelKey, loaded.failed, Boolean(scene)) : null)
    || (stale && scene ? staleBuildAlert(stale, t) : null)
    || (loaded.empty ? noGeometryAlert(document.modelKey) : null),
  [document.catalogError, loaded.error, loaded.failed, loaded.empty, document.modelKey, scene, stale, t]);
  const tree = useMemo(() => presentXbfTree(scene?.structure || null), [scene?.structure]);
  // The model's two readiness moments, as a STEP's are published (`window.__cadViewerLoad`): its
  // first scene, and the whole of it -- one moment here, every part is in the first scene.
  useViewportLoadStatus({ modelKey: `${document.modelKey}:${loaded.revision}`, hasGeometry: Boolean(scene),
    modelComplete: Boolean(scene) && !loaded.busy });
  // An assembly's view is a STEP assembly's: the Model tree, Parts in the filter, Explode.
  const assembly = (scene?.partCount || 0) > 1;
  const features = useMemo(() => viewFeaturesForKind("xbf", { parts: scene?.partCount || 0 }), [scene]);

  const shellRef = useRef(null);
  const preview = usePreviewState();
  const previewing = preview.previewing;
  const [toolMode, setToolMode] = useState(XBF_TOOL_MODES.defaultMode);
  const tool = useMemo(() => ({ mode: toolMode, set: setToolMode }), [toolMode]);
  const measuring = !previewing && toolMode === XBF_TOOL.MEASURE;
  const measure = useMeasureSession({ fileKey: document.modelKey, revision: loaded.revision, picking: measuring });
  const requestFrame = useCallback(() => shellRef.current?.requestFrame?.(), []);
  const requestRender = useCallback(() => shellRef.current?.requestRender?.(), []);

  // ---- Select's menu: All as the file opens, or one kind alone ---------------------------------
  const [selectFilter, setSelectFilter] = useState(XBF_SELECT_DEFAULT);
  // Measure's menu, a STEP's (`kit/tools/measure/measureFilter.js`): All as the file opens, or
  // Vertices, Edges or Faces alone: what a press takes whole (`XbfMeasure.jsx`).
  const [measureFilter, setMeasureFilter] = useState(MEASURE_FILTER_DEFAULT);
  const [connected, setConnected] = useState(NO_CONNECTED_SELECTION);
  const geometryFilter = useMemo(() => (assembly ? selectFilter : selectFilter.filter(id => id !== "parts")), [assembly, selectFilter]);
  const mode = selectGeometryMode(geometryFilter);
  const shape = treeShape(mode);

  // ---- the model tree's state, the host's: what is open, hidden, isolated, selected ------------
  const [expandedIds, setExpandedIds] = useState(EMPTY);
  const [hiddenIds, setHiddenIds] = useState(EMPTY);
  const [isolatedIds, setIsolatedIds] = useState(EMPTY);
  const [chosen, setChosen] = useState(EMPTY);
  const [hover, setHover] = useState(NO_HOVER);
  const selected = useMemo(() => (scene ? chosen.filter(id => (isElementId(id) ? scene.describeElement(id) : tree.nodes.has(id))) : EMPTY),
    [scene, tree, chosen]);
  const selectedNodeIds = useMemo(() => selected.filter(id => !isElementId(id)), [selected]);
  const selectedElementIds = useMemo(() => selected.filter(isElementId), [selected]);
  const leavesOf = useCallback(ids => [...new Set(ids.flatMap(id => tree.nodes.get(id)?.leafPartIds || []))], [tree]);
  // What is open: the person's own under "all"; every assembly under the filter's other shapes, and
  // under Faces and Edges every part's faces and edges with them.
  const assemblyIds = useMemo(() => xbfAssemblyIds(tree), [tree]);
  const openIds = useMemo(() => {
    if (shape === "all") return new Set(expandedIds);
    const open = new Set(assemblyIds);
    if (shape !== "parts") for (const id of tree.nodes.keys()) if (!isXbfAssemblyId(id)) open.add(id);
    return open;
  }, [shape, expandedIds, assemblyIds, tree]);
  const selectableIds = useMemo(() => (isolatedIds.length ? subtreeIds(tree, isolatedIds) : null), [tree, isolatedIds]);

  // The scene follows: hidden parts, the isolation, what is lit.
  useEffect(() => { scene?.setHiddenParts(hiddenIds); requestRender(); }, [scene, hiddenIds, requestRender]);
  useEffect(() => { scene?.setFocusedParts(leavesOf(isolatedIds)); requestRender(); }, [scene, isolatedIds, leavesOf, requestRender]);
  useEffect(() => {
    if (!scene) return;
    scene.setHighlight({ hovered: hover.parts, selected: leavesOf(selectedNodeIds) });
    scene.setElementHighlight({ hovered: hover.element, selected: selectedElementIds });
    requestFrame();
  }, [scene, hover, selectedNodeIds, selectedElementIds, leavesOf, requestFrame]);

  // ---- Position: the mechanism's pose ---------------------------------------------------------
  const kinematics = scene?.kinematics || null;
  const positionRows = useMemo(() => (kinematics ? xbfPositionRows(kinematics) : EMPTY), [kinematics]);
  const posable = positionRows.length > 0;
  const pose = useXbfPose(kinematics);
  const { values: poseValues, applied: poseApplied, preset: posePreset, couplings: poseCouplings,
    setValues: setPoseValues, choosePreset, reset: resetPose } = pose;
  // ---- Motion: the document's motions played (`useXbfMotion.js`) ------------------------------
  // While a motion owns the pose (playing, or paused off its start, until Reset lets go of it) its
  // frames pose the scene and Position shows them, read-only. It is a motion as Explode and the
  // pose are (below): playing it puts both at rest, and Explode used puts it at rest.
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const positionRef = useRef(null);
  positionRef.current = { values: poseValues, applied: poseApplied };
  const poseFrame = useCallback((values) => {
    const now = sceneRef.current;
    if (!now) return;
    const position = positionRef.current;
    now.setPose(values || (position.applied ? position.values : null));
    if (!values) shellRef.current?.syncSceneBounds?.();
    shellRef.current?.requestRender?.();
  }, []);
  const motion = useXbfMotion(kinematics, poseFrame);
  const motionOwns = Boolean(motion?.enabled);
  const motionRef = useRef(motion);
  motionRef.current = motion;
  useEffect(() => {
    if (!scene || !poseValues || motionRef.current?.enabled) return;
    scene.setPose(poseApplied ? poseValues : null);
    shellRef.current?.syncSceneBounds?.();
    requestRender();
  }, [scene, poseValues, poseApplied, requestRender]);
  // A prompt's view, as a STEP's carried its pose and what it hid: the pose Position holds off as
  // built, as `cadgen snapshot --pose` takes it (`jointValues`), and the parts hidden and isolated as
  // its `--display` takes them (`hidden`, `isolated`), each node as Copy Prompt copies it and the
  // hidden parts by the fewest nodes that name them -- so the view ink was drawn in is drawn as it was.
  // While a motion owns the pose, the pose on screen is its frame.
  const positionGiven = useMemo(() => (poseApplied && kinematics && poseValues ? xbfPoseGiven(kinematics, poseValues, poseCouplings) : null),
    [poseApplied, kinematics, poseValues, poseCouplings]);
  const motionGiven = useCallback((at) => {
    const values = motionRef.current?.valuesAt(at);
    return values && kinematics ? xbfPoseGiven(kinematics, values) : null;
  }, [kinematics]);
  const poseGiven = useMemo(() => (motionOwns ? motionGiven(motion.elapsedSec) : positionGiven),
    [motionOwns, motion?.elapsedSec, motion?.activeClipId, motionGiven, positionGiven]);
  const viewState = useCallback(() => {
    const refs = ids => xbfNodeRefs({ scene, tree, resource: shellRef.current?.frame.resource, ids });
    const playing = motionRef.current?.enabled && motionRef.current.playing;
    return { jointValues: playing ? motionGiven(motionRef.current.clock.getAnimationClock()) : poseGiven,
      hidden: refs(xbfCoveringIds(tree, hiddenIds)), isolated: refs(isolatedIds) };
  }, [poseGiven, motionGiven, scene, tree, hiddenIds, isolatedIds]);

  // ---- this document's own slices of the file's view: the tree and the pose --------------------
  // As a STEP's were (`xbfViewSlices.js`): what is open, hidden and isolated in the Model tree, and
  // Position's pose, come back when the file is opened again (a reload, the tab reopened), each only
  // while the document is the one it was written against. Read once, as the first scene arrives (an
  // engine document's slices are signed by its structure, which only the scene knows), and written
  // soon after any of them changes. Until then the shell keeps what was stored as it is.
  const [stored] = useState(() => view.state);
  const viewSignatures = useMemo(() => xbfViewSignatures(scene?.structure || null, kinematics), [scene?.structure, kinematics]);
  const [viewRestored, setViewRestored] = useState(false);
  const restorePose = pose.restore;
  useLayoutEffect(() => {
    if (viewRestored || !viewSignatures) return;
    const kept = readXbfView(readFileView(stored, viewSignatures).renderer);
    if (kept.tree.expanded.length) setExpandedIds(kept.tree.expanded);
    if (kept.tree.hidden.length) setHiddenIds(kept.tree.hidden);
    if (kept.tree.isolated.length) setIsolatedIds(kept.tree.isolated);
    if (kept.pose && kinematics) restorePose(kept.pose);
    setViewRestored(true);
  }, [viewRestored, viewSignatures, stored, kinematics, restorePose]);
  const viewInputs = useRef(null);
  viewInputs.current = { tree: { expanded: expandedIds, hidden: hiddenIds, isolated: isolatedIds }, pose: kinematics ? pose.saved : null };
  const rendererState = useMemo(() => (viewRestored && viewSignatures
    ? { signatures: viewSignatures, read: () => xbfViewSlices(viewInputs.current) } : null), [viewRestored, viewSignatures]);
  useEffect(() => { if (viewRestored) shellRef.current?.scheduleStateSave(); },
    [viewRestored, viewSignatures, expandedIds, hiddenIds, isolatedIds, pose.saved]);

  // ---- the shell ------------------------------------------------------------------------------
  const clearSelection = useCallback(() => setChosen(now => (now.length ? EMPTY : now)), []);
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const live = useMemo(() => ({
    declined: XBF_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => setChosen(EMPTY) },
    state: () => ({ selected: [...selectedRef.current] })
  }), []);
  // The selection in the prompt grammar, as Quick Edit's chips reference it (set below, once they
  // are made): what a capture sent to the chat names, and what `cad_view` says is selected.
  const promptReferencesRef = useRef(NO_REFERENCES);
  const promptReferences = useCallback(() => promptReferencesRef.current, []);
  // Escape, as a STEP's: a measurement in progress, then the tool in hand (Select taken up), then
  // the measurements picked, then the parts, faces and edges, then the isolation -- one layer a press.
  const escapeRef = useRef(() => false);
  const escape = useMemo(() => ({
    active: selected.length > 0 || isolatedIds.length > 0 || toolMode !== XBF_TOOL.SELECT || measure.selected.length > 0,
    handle: () => escapeRef.current()
  }), [selected.length, isolatedIds.length, toolMode, measure.selected.length]);
  // An xbf's CAD edges are hairlines (`xbfScene.js`): while the view draws them the viewport keeps
  // its pixel ratio through a camera gesture, as a STEP's does for its edges, so a press or a
  // drag never softens and shifts the model (the edges the view draws are only known after the
  // shell resolves them; until then a view draws them, as every display mode but Shaded does).
  const [edgesDrawn, setEdgesDrawn] = useState(true);
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features, toolModes: XBF_TOOL_MODES, tool, previewable: true, preview, scene, sceneEffects: true, animation: motion,
    // A build writing the file is the model on screen updating, its stage the progress
    // (`progress.py`'s frame), until it lands or fails.
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), editPending: Boolean(loaded.building),
      progress: loaded.progress || loaded.building, alert: loadAlert },
    live, promptReferences, escape, deleteSelection: measure.removeSelected, preserveInteractionPixelRatio: edgesDrawn, viewState, rendererState,
    // A prompt's annotation is in the scene's coordinates: the document's millimetres.
    annotationUnits: scene?.units?.unit || "mm"
  });
  // Export writes the document as its code built it: the displayed document and revision alone,
  // never the selection or the pose (`docs/viewer-host.md`, Export destinations and jobs).
  const exportView = useMemo(() => loaded.document && !host.environment.compact ? {
    doc: loaded.document.source.doc, revision: loaded.revision, file: view.file.path, name: view.file.name,
    preview: shell.previewing
  } : null, [loaded.document, loaded.revision, host.environment.compact, view.file.path, view.file.name, shell.previewing]);
  useExportView(exportView);
  // A measurement taken, deleted or cleared is a step of the view's one history, with the ink's.
  measure.history.current = shell.frame.history;
  shellRef.current = shell;
  // Ink drawn over the version before does not describe this one: a new version of the file takes
  // it, and its history with it, so Undo cannot put it back over the new model, as a STEP's did.
  // Annotate stays the tool in hand.
  const inkVersion = useRef({ file: document.modelKey, revision: loaded.revision });
  useEffect(() => {
    const before = inkVersion.current;
    inkVersion.current = { file: document.modelKey, revision: loaded.revision };
    if (before.file === document.modelKey && before.revision && loaded.revision && before.revision !== loaded.revision) {
      shellRef.current?.frame.annotation.discard();
    }
  }, [document.modelKey, loaded.revision]);
  useDeclinedSelectReference(document);
  const ensureSelect = useCallback(() => { if (shellRef.current?.toolMode !== XBF_TOOL.SELECT) shellRef.current?.selectTool(XBF_TOOL.SELECT); }, []);

  // ---- one motion at a time: Explode, the pose and a motion, nothing set aside -----------------
  const { view: viewSettings, store } = shell.viewSettings;
  const explodeApplied = Boolean(viewSettings.exploded?.enabled && viewSettings.exploded.amount > 0);
  useMotionExclusion(document.modelKey, {
    explode: { applied: explodeApplied, reset: () => store.patch(EXPLODE_OFF) },
    position: { applied: poseApplied, reset: resetPose },
    motion: { applied: motionOwns, reset: () => motionRef.current?.onRelease() }
  });

  // The edges the display mode draws, as the view resolved them; Preview's scene draws none.
  const edges = shell.frame.resolvedScene?.view?.edges || null;
  const edgesKey = JSON.stringify(edges);
  useEffect(() => {
    if (!edges) return;
    setEdgesDrawn(edges.enabled !== false);
    if (!scene) return;
    scene.setEdgeLook(edges);
    shell.requestRender();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, edgesKey]);
  // The scene's screen-space lines (its highlights) are registered with the viewport showing it,
  // as a STEP's are: the viewport keeps their resolution at its drawing buffer's and counts them.
  // The viewport's runtime is made after the first render and again after a lost context, so
  // every render hands the scene the one there is (the scene ignores the same one twice).
  useEffect(() => { scene?.setLineRegistry(viewportRef.current?.runtimeRef.current || null); });
  const previewScene = usePreviewScene(scene, previewing);
  useEffect(() => { previewScene?.setEdgeLook({ enabled: false }); }, [previewScene]);
  // Preview's own motion, on its own scene: at rest as Preview opens, let go as it closes.
  const previewSceneRef = useRef(previewScene);
  previewSceneRef.current = previewScene;
  const previewFrame = useCallback((values) => {
    previewSceneRef.current?.setPose(values);
    shellRef.current?.frame.previewViewRef.current?.requestRender?.();
  }, []);
  const previewMotion = useXbfMotion(previewScene?.kinematics || null, previewFrame);
  const previewView = useMemo(() => ({ scene: previewScene, animation: previewMotion }), [previewScene, previewMotion]);

  // ---- the tree's actions --------------------------------------------------------------------
  const toggleExpanded = useCallback(id => setExpandedIds(now => (now.includes(id) ? now.filter(item => item !== id) : [...now, id])), []);
  const collapseSubtree = useCallback(id => {
    const under = subtreeIds(tree, [id]);
    setExpandedIds(now => (now.some(item => under.has(item)) ? now.filter(item => !under.has(item)) : now));
  }, [tree]);
  const selectTreeNode = useCallback((id, { multiSelect = false } = {}) => {
    ensureSelect();
    setChosen(now => pickNode(now, id, multiSelect));
  }, [ensureSelect]);
  // Isolate: what it names alone in reach, everything else dimmed; its parts shown, opened.
  const isolate = useCallback((ids) => {
    if (!assembly) return;
    const targets = [ids].flat().filter(id => tree.nodes.has(id));
    if (!targets.length) { setIsolatedIds(EMPTY); return; }
    const leaves = new Set(leavesOf(targets));
    setChosen(EMPTY);
    setIsolatedIds(targets);
    setExpandedIds(now => [...new Set([...now, ...targets])]);
    setHiddenIds(now => (now.some(id => leaves.has(id)) ? now.filter(id => !leaves.has(id)) : now));
  }, [assembly, tree, leavesOf]);
  const exitIsolate = useCallback(() => {
    for (const id of isolatedIds) collapseSubtree(id);
    setIsolatedIds(EMPTY);
  }, [isolatedIds, collapseSubtree]);
  escapeRef.current = () => {
    const now = measureRef.current;
    if (!previewing && toolMode === XBF_TOOL.MEASURE && now.drafting) { now.cancelDraft(); return true; }
    if (!previewing && toolMode !== XBF_TOOL.SELECT) { shellRef.current?.selectTool(XBF_TOOL.SELECT); return true; }
    if (now.selected.length) { now.select([]); return true; }
    if (selectedRef.current.length) { setChosen(EMPTY); return true; }
    if (isolatedIds.length) { exitIsolate(); return true; }
    return false;
  };
  const exitSingleIsolate = useCallback((id) => {
    collapseSubtree(id);
    setIsolatedIds(now => now.filter(item => item !== id));
  }, [collapseSubtree]);
  const hideNodes = useCallback((ids) => {
    const leaves = new Set(leavesOf(ids));
    for (const id of ids) collapseSubtree(id);
    // What is hidden is let go of: a face or edge of a hidden part, a node all of whose parts are.
    const gone = item => (isElementId(item) ? leaves.has(item.split("/")[0])
      : (tree.nodes.get(item)?.leafPartIds || EMPTY).every(leaf => leaves.has(leaf)));
    setChosen(now => now.filter(item => !gone(item)));
    setIsolatedIds(now => now.filter(item => !ids.some(id => subtreeIds(tree, [id]).has(item))));
    setHiddenIds(now => [...new Set([...now, ...leaves])]);
  }, [leavesOf, collapseSubtree, tree]);
  const revealNodes = useCallback((ids) => {
    const leaves = new Set(leavesOf(ids));
    setHiddenIds(now => now.filter(id => !leaves.has(id)));
  }, [leavesOf]);
  const toggleVisibility = useCallback((id) => {
    const leaves = tree.nodes.get(id)?.leafPartIds || EMPTY;
    if (leaves.length && leaves.every(leaf => hiddenIds.includes(leaf))) revealNodes([id]); else hideNodes([id]);
  }, [tree, hiddenIds, hideNodes, revealNodes]);
  const showAll = useCallback(() => setHiddenIds(EMPTY), []);
  const hideOthers = useCallback((ids) => {
    const keep = new Set(leavesOf(ids));
    setIsolatedIds(EMPTY);
    setHiddenIds([...tree.nodes.values()].filter(node => node.kind === "part" && !isXbfAssemblyId(node.selectionId))
      .map(node => node.selectionId).filter(id => !keep.has(id)));
    setChosen(now => now.filter(item => (isElementId(item) ? keep.has(item.split("/")[0])
      : (tree.nodes.get(item)?.leafPartIds || EMPTY).some(leaf => keep.has(leaf)))));
  }, [leavesOf, tree]);

  // ---- picking --------------------------------------------------------------------------------
  // The instances whose faces and edges a press can take under "all": each part the host has open
  // whose owners are open too (a press elsewhere takes the part, or the collapsed assembly it is in).
  const frontier = useCallback(id => xbfPickFrontier(tree, id, openIds), [tree, openIds]);
  const openElements = useMemo(() => {
    if (shape !== "all") return null;
    const open = new Set();
    // The instances the person opened; an assembly, and a folded group's row (which the tree keeps
    // open by its own id), are none.
    for (const id of openIds) {
      const element = parseXbfElementId(id);
      if (element && frontier(id) === id) open.add(element.instance);
    }
    return open;
  }, [shape, openIds, frontier]);
  const pickOptions = useMemo(() => ({
    faces: geometryFilter.includes("faces"), edges: geometryFilter.includes("edges"),
    parts: assembly && geometryFilter.includes("parts"), elements: openElements
  }), [geometryFilter, assembly, openElements]);
  const viewportRef = useRef(null);
  // What the last press was made with (`XbfPick`): a finger's press reaches an edge from further off, as a STEP's.
  const pointerTypeRef = useRef("");
  // A press's pick and a resting pointer's (an edge is taken from further away on a press), as one hit.
  const picker = useMemo(() => (scene ? {
    pick(ray) {
      const camera = viewportRef.current?.runtimeRef.current?.camera;
      const rect = viewportRef.current?.hostRef.current?.getBoundingClientRect?.();
      if (!camera || !rect?.width || mode === "none") return null;
      const view = { camera, width: rect.width, height: rect.height };
      const press = scene.pickElement(ray, view, { ...pickOptions, touch: pointerTypeRef.current === "touch" });
      const rest = scene.pickElement(ray, view, { ...pickOptions, hover: true });
      return press || rest ? { id: rest?.id || "", press, rest } : null;
    }
  } : null), [scene, pickOptions, mode]);
  const pickAtClient = useCallback((clientX, clientY) => {
    const viewport = viewportRef.current;
    const runtime = viewport?.runtimeRef.current;
    const rect = viewport?.hostRef.current?.getBoundingClientRect?.();
    if (!runtime?.camera || !rect?.width || !picker) return null;
    const raycaster = new runtime.THREE.Raycaster();
    raycaster.setFromCamera(new runtime.THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, 1 - ((clientY - rect.top) / rect.height) * 2), runtime.camera);
    return picker.pick(raycaster.ray)?.press || null;
  }, [picker]);
  // What a hit reaches: a face or an edge, or the node a press on its part takes.
  const nodeOf = useCallback(hit => (hit && !hit.kind ? frontier(hit.id) : ""), [frontier]);
  // What Annotate's ink touches at a point of the view, as a STEP's said it (`RendererShell`'s
  // `inkTouches`): the part under it, with the face or the edge there as its reference, as copying
  // that face or edge writes it -- whatever Select's filter picks, and whichever parts are open.
  const inkTouches = useCallback((clientX, clientY) => {
    const viewport = viewportRef.current;
    const runtime = viewport?.runtimeRef.current;
    const rect = viewport?.hostRef.current?.getBoundingClientRect?.();
    if (!scene || !runtime?.camera || !rect?.width) return [];
    const raycaster = new runtime.THREE.Raycaster();
    raycaster.setFromCamera(new runtime.THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, 1 - ((clientY - rect.top) / rect.height) * 2), runtime.camera);
    const hit = scene.pickElement(raycaster.ray, { camera: runtime.camera, width: rect.width, height: rect.height },
      { faces: true, edges: true, parts: true, elements: null });
    const instance = parseXbfElementId(hit?.id)?.instance;
    if (instance == null) return [];
    const part = `i${instance}`;
    const ref = hit.kind ? xbfCopyText({ scene, tree, resource: shellRef.current?.frame.resource, ids: [hit.id] }).split("\n")[0] : "";
    return [ref ? { part, ref } : { part }];
  }, [scene, tree]);

  // Group faces and Group edges: the engine's groups of a part, asked for once per part.
  const groupsRef = useRef(new Map());
  const groupsOf = useCallback((key) => {
    if (!source) return Promise.resolve(null);
    const known = groupsRef.current.get(key);
    if (known) return known;
    const asked = fetchXbfPartGroups(source, key, { fetch: engineFetch }).catch(() => null);
    groupsRef.current.set(key, asked);
    return asked;
  }, [source, engineFetch]);
  const grownIds = useCallback(async (hit) => {
    const option = hit.kind === "face" ? "tangentFaces" : "edgeChain";
    if (!connected[option]) return [hit.id];
    const groups = await groupsOf(hit.key);
    const table = groups?.[hit.kind === "face" ? "faces" : "edges"];
    const group = table?.[String(hit.ordinal)];
    if (group == null) return [hit.id];
    return Object.entries(table).filter(([, value]) => value === group).map(([ordinal]) => `i${hit.instance}/${hit.kind}/${ordinal}`);
  }, [connected, groupsOf]);

  // The selection as the last activation found it: what a double-click whose first click picked puts back.
  const lastPick = useRef(null);
  const handlePick = useCallback(async (found, modifiers) => {
    const hit = found?.press || null;
    const multiSelect = Boolean(modifiers?.multiSelect);
    lastPick.current = { before: selectedRef.current };
    if (shellRef.current?.toolMode !== XBF_TOOL.SELECT) ensureSelect();
    if (!hit) { if (!multiSelect) { setChosen(EMPTY); measureRef.current.select([]); } return; }
    if (!multiSelect) measureRef.current.select([]);
    if (hit.kind) {
      const ids = await grownIds(hit);
      setChosen(now => pickElements(now, ids, multiSelect));
      return;
    }
    const node = nodeOf(hit);
    if (node && (!selectableIds || selectableIds.has(node))) setChosen(now => pickNode(now, node, multiSelect));
  }, [ensureSelect, grownIds, nodeOf, selectableIds]);
  const handleHover = useCallback((found) => {
    const hit = found?.rest || null;
    if (!hit) { setHover(now => (now === NO_HOVER ? now : NO_HOVER)); return; }
    if (hit.kind) { setHover({ parts: EMPTY, element: hit.id }); return; }
    const node = nodeOf(hit);
    setHover({ parts: node ? tree.nodes.get(node)?.leafPartIds || EMPTY : EMPTY, element: null });
  }, [nodeOf, tree]);
  const selectActive = !previewing && Boolean(scene) && toolMode === XBF_TOOL.SELECT;
  // A pick under Explode or Clip takes Select up, as a STEP's does.
  const picking = !previewing && Boolean(scene) && [XBF_TOOL.SELECT, XBF_TOOL.EXPLODE, XBF_TOOL.CLIP].includes(toolMode);
  useEffect(() => { if (!picking) setHover(NO_HOVER); }, [picking]);

  // ---- references and copies -------------------------------------------------------------------
  const facts = useXbfElementFacts({ source, fetch: engineFetch, version: loaded.revision, scene, elementIds: selectedElementIds });
  const removeFromSelection = useCallback(ids => setChosen(now => now.filter(id => !ids.includes(id))), []);
  const hoverChip = useCallback(ids => {
    if (!ids) { setHover(NO_HOVER); return; }
    const elements = ids.filter(isElementId);
    setHover(elements.length ? { parts: EMPTY, element: elements[0] } : { parts: ids, element: null });
  }, []);
  const resource = shell.frame.resource;
  const { references, chips } = useXbfSelectionChips({ scene, tree, resource, selectedIds: selected, facts,
    onRemove: removeFromSelection, onHover: hoverChip });
  promptReferencesRef.current = previewing ? NO_REFERENCES : references;
  // What a node or an element copies: its reference, the file's path with it.
  const singleChip = useCallback(ids => xbfCopyText({ scene, tree, resource, ids }), [scene, tree, resource]);
  const copy = useCallback(text => { if (text) void host.clipboard.writeText(text).catch(() => {}); }, [host.clipboard]);
  const copySelection = selected.length && !previewing ? () => copy(chips.map(chip => chip.copy).filter(Boolean).join("\n")) : null;
  const nameReference = useCallback((reference) => {
    const selector = reference?.target?.kind === "cad-selector" ? reference.target.selectors?.[0] : "";
    const chip = selector ? chips.find(item => item.selectors?.includes(selector)) : null;
    if (!chip) return "";
    return chip.compact || { name: chip.label, kind: chip.glyph };
  }, [chips]);

  // ---- double-click: a face or edge looked at, a part isolated, empty space leaves isolation ----
  // A face or an edge: the view turns square to it (CAD's Normal To, `kit/camera/lookAt.js`) and
  // nothing is picked; navigation only.
  const lookAt = useCallback((id) => {
    const subject = xbfLookSubject(scene, id);
    if (subject) shellRef.current?.frame.viewerRef.current?.lookAt?.(subject);
  }, [scene]);
  // `activated`: the gesture's first click picked (`clickActivation.js`), so the selection it found
  // comes back first, through the one setter every pick goes through; then the double-click acts
  // as if that click had never happened. Under Select, Explode or Clip alike: under the two a pick
  // would leave, the click waited, so the tool is still the one in hand.
  const handleDoublePick = useCallback((clientX, clientY, { activated = false } = {}) => {
    if (activated && lastPick.current) setChosen(lastPick.current.before);
    lastPick.current = null;
    const hit = pickAtClient(clientX, clientY);
    if (!hit) { exitIsolate(); return; }
    if (hit.kind) { lookAt(hit.id); return; }
    const node = nodeOf(hit);
    if (node && assembly) isolate([node]);
  }, [pickAtClient, exitIsolate, lookAt, nodeOf, assembly, isolate]);
  // Under Measure, as a STEP's: the face or edge Measure takes there is looked at, empty space
  // leaves isolation (the presses of the gesture were Measure's own).
  const handleMeasureDoublePick = useCallback((id) => { if (id) lookAt(id); else exitIsolate(); }, [lookAt, exitIsolate]);
  // A pick under Explode or Clip takes Select up: it waits the double-click window first.
  const deferPickRef = useRef(false);
  deferPickRef.current = toolMode !== XBF_TOOL.SELECT;
  // What Measure lights under the resting pointer: the face or edge it would take.
  const hoverElement = useCallback(id => setHover(now => (id
    ? (now.element === id && !now.parts.length ? now : { parts: EMPTY, element: id })
    : (now === NO_HOVER ? now : NO_HOVER))), []);

  // ---- the menus --------------------------------------------------------------------------------
  const zoomSelectionAvailable = selected.length > 0;
  const zoomToSelection = useCallback(() => {
    const ids = [...leavesOf(selectedRef.current.filter(id => !isElementId(id))), ...selectedRef.current.filter(isElementId)];
    const bounds = scene?.selectionBounds(ids);
    if (bounds) shellRef.current?.frame.viewerRef.current?.zoomToBounds?.(bounds);
  }, [scene, leavesOf]);
  const menuForNode = useCallback(id => xbfPartMenu({ tree, nodeId: id, assembly, hiddenIds, isolatedIds,
    selectedNodeIds, expandedIds, copyText: singleChip([...new Set([...selectedNodeIds, id])]), zoomSelectionAvailable, shape }),
  [tree, assembly, hiddenIds, isolatedIds, selectedNodeIds, expandedIds, singleChip, zoomSelectionAvailable, shape]);
  const partMenuActions = useMemo(() => Object.fromEntries(Object.entries({
    onCopyReference: menu => copy(menu.copyText),
    onSelect: (menu) => {
      if (menu.referenceId) {
        if (menu.selected && menu.referenceIds.length > 1) { setChosen(now => now.filter(id => !isElementId(id))); return; }
        setChosen(now => pickElements(now, [menu.referenceId], false));
        return;
      }
      if (menu.selected) {
        if (menu.actionNodeIds.length > 1) setChosen(EMPTY); else setChosen(now => now.filter(id => id !== menu.nodeId));
        return;
      }
      setChosen(now => pickNode(now, menu.nodeId, false));
    },
    onIsolate: menu => (menu.focused ? exitSingleIsolate(menu.nodeId) : isolate(menu.actionNodeIds)),
    onExitAllIsolate: exitIsolate,
    onHideOther: menu => hideOthers(menu.actionNodeIds),
    onHideAll: () => showAll(),
    onHide: menu => hideNodes(menu.selected && menu.actionNodeIds.length > 1 ? selectedNodeIds : menu.actionNodeIds),
    onReveal: menu => revealNodes(menu.actionNodeIds),
    onExpandSelected: menu => menu.collapsedActionNodeIds.forEach(toggleExpanded),
    onCollapseSelected: menu => menu.expandedActionNodeIds.forEach(toggleExpanded),
    onExpandAll: menu => setExpandedIds(now => [...new Set([...now, ...menu.collapsedExpandableTreeNodeIds])]),
    onCollapseAll: menu => setExpandedIds(now => now.filter(id => !menu.expandedExpandableTreeNodeIds.includes(id))),
    onZoomFit: () => shellRef.current?.frame.viewerRef.current?.resetZoom?.(),
    onZoomSelection: zoomToSelection
  }).map(([name, action]) => [name, (menu) => { ensureSelect(); return action(menu); }])),
  [copy, exitSingleIsolate, isolate, exitIsolate, hideOthers, showAll, hideNodes, selectedNodeIds, revealNodes, toggleExpanded,
    zoomToSelection, ensureSelect]);
  const contextMenuItems = selectActive ? (press) => {
    const hit = pickAtClient(press.clientX, press.clientY);
    let menu = null;
    if (hit?.kind) {
      menu = xbfTopologyMenu({ elementId: hit.id, label: hit.name || hit.id, selectedElementIds,
        copyText: singleChip([...new Set([...selectedElementIds, hit.id])]), zoomSelectionAvailable });
    } else if (hit && assembly) {
      menu = menuForNode(nodeOf(hit));
    }
    menu ||= xbfModelMenu({ tree, assembly, expandedIds, hiddenCount: hiddenIds.length, zoomSelectionAvailable, shape,
      copyText: assembly ? "" : singleChip([tree.roots[0]?.selectionId].filter(Boolean)) });
    return viewportMenuEntries(menu, { actions: partMenuActions });
  } : null;

  // ---- the strip --------------------------------------------------------------------------------
  const bounds = scene ? boundsInUnits(sceneFramingBounds(scene), scene.units) : null;
  const effects = useModelTools({ view: viewSettings, features, store, mesh: bounds ? { bounds } : null,
    disabled: shell.idle, selectedTool: shell.toolMode, onSelect: shell.selectTool });
  const selectModeMenu = useMemo(() => <SelectModeMenu value={selectFilter} assembly={assembly} posable={posable} disabled={shell.idle}
    onChange={value => { setSelectFilter(value); shellRef.current?.selectTool(XBF_TOOL.SELECT); }}
    connected={connected} onConnectedChange={(id, checked) => setConnected(now => ({ ...now, [id]: checked }))} />,
  [selectFilter, assembly, posable, shell.idle, connected]);
  // Measure's chevron, a STEP's: a choice takes Measure up, as Select's takes Select up.
  const measureFilterMenu = useMemo(() => <MeasureFilterMenu value={measureFilter} disabled={shell.idle}
    onChange={value => { setMeasureFilter(value); shellRef.current?.selectTool(XBF_TOOL.MEASURE); }} />,
  [measureFilter, shell.idle]);
  const strip = [
    // Each button badged with what its tool picks alone (its chevron's menu), none for All.
    shell.tools.own({ id: XBF_TOOL.SELECT, label: "Select", shortcut: TOOL_SHORTCUTS.select, menu: selectModeMenu,
      icon: <SelectIcon mode={pickModeOf(selectFilter, xbfSelectModes({ assembly, posable })).id} className="size-3.5" aria-hidden="true" /> }),
    ...shell.tools.drawing.map(tool => ({ ...tool, disabled: shell.idle })),
    shell.tools.own({ id: XBF_TOOL.MEASURE, label: "Measure", shortcut: TOOL_SHORTCUTS.measure, menu: measureFilterMenu,
      icon: <MeasureIcon mode={pickModeOf(measureFilter, MEASURE_MODES).id} className="size-3.5" aria-hidden="true" />,
      onSelect: () => { if (shell.toolMode !== XBF_TOOL.MEASURE) shell.selectTool(XBF_TOOL.MEASURE); } }),
    ...effects.tools
  ];
  // Under Select a press on a measurement picks it before any part under it, while Select picks measurements.
  const runtimeOf = () => viewportRef.current?.runtimeRef.current;
  const measureSelect = measureSelectHandlers(measure, runtimeOf, clearSelection, { picks: selects(selectFilter, "measurement") });

  // Position's knobs: Select's, while its filter ticks Position, with nothing exploded and no motion owning the pose.
  const knobsShown = selectActive && posable && selects(selectFilter, "position") && !explodeApplied && !motionOwns;
  const handles = useMemo(() => (knobsShown && poseValues ? xbfJointHandles({ kinematics, rows: positionRows, values: poseValues, scene,
    onChange: (row, value) => { const written = writeXbfPosition(poseValues, row, value); if (written) setPoseValues(written); } }) : null),
  [knobsShown, kinematics, positionRows, poseValues, scene, setPoseValues]);
  const handleLayoutRef = useRef(null);

  // ---- the file sidebar: the Model tree (an assembly's), then Position --------------------------
  const partControls = useMemo(() => ({
    isAssemblyView: assembly, hiddenPartIds: hiddenIds, focusedNodeIds: isolatedIds, selectableNodeIds: selectableIds ? [...selectableIds] : null,
    expandedTreeNodeIds: expandedIds, onToggleTreeNode: toggleExpanded, onSelectTreeNode: selectTreeNode,
    onFocusTreeNode: ids => { ensureSelect(); isolate(ids); }, onUnfocusTreeNode: exitSingleIsolate, onExitAllIsolate: exitIsolate,
    onTogglePartVisibility: toggleVisibility, showAllHiddenParts: showAll,
    onHoverTreeNode: id => setHover(id ? { parts: tree.nodes.get(id)?.leafPartIds || EMPTY, element: null } : NO_HOVER),
    menuForNode, partMenuActions
  }), [assembly, hiddenIds, isolatedIds, selectableIds, expandedIds, toggleExpanded, selectTreeNode, ensureSelect, isolate, exitSingleIsolate,
    exitIsolate, toggleVisibility, showAll, tree, menuForNode, partMenuActions]);
  const sidebar = scene && (assembly || kinematics) ? <>
    {assembly ? <XbfModelTree key={document.modelKey} tree={tree} active={!previewing} disabled={shell.idle} mode={shape}
      selectedIds={selected} onClearSelection={clearSelection} partControls={partControls} /> : null}
    {kinematics ? <XbfPositionSection kinematics={kinematics} motion={motionOwns ? motion : null} values={poseValues || {}} couplings={poseCouplings} preset={posePreset}
      changed={poseApplied} onValues={setPoseValues} onPreset={choosePreset} onReset={resetPose} /> : null}
  </> : null;

  return <RendererShell shell={shell} tools={strip} subToolbar={measuring ? <MeasurementsBar measure={measure} /> : effects.subToolbar} sidebar={sidebar} previewView={previewView}
    references={previewing ? NO_REFERENCES : references} referenceChips={previewing ? NO_REFERENCES : chips} nameReference={nameReference}
    onClearReferences={() => { setChosen(EMPTY); measure.select([]); }} copySelection={copySelection}
    onSelectPress={measureSelect.press} onSelectHover={measureSelect.hover} selectsAnnotations={selects(selectFilter, "annotation")}
    inkTouches={inkTouches} contextMenuItems={contextMenuItems}
    viewportOverlay={viewport => {
      viewportRef.current = viewport;
      return <>
        <XbfMeasureOverlay viewport={viewport} scene={scene} measure={measure} picking={measuring} preview={shell.previewing}
          filter={measureFilter} source={source} fetch={engineFetch} onHoverElement={hoverElement} onDoublePick={handleMeasureDoublePick} />
        {handles ? <JointHandleOverlay handles={handles} layoutSeamRef={handleLayoutRef} {...viewport} /> : null}
        <XbfPick viewport={viewport} scene={picker} enabled={picking} onPick={handlePick} onHover={handleHover} onDoublePick={handleDoublePick}
          deferRef={deferPickRef} pointerTypeRef={pointerTypeRef} />
      </>;
    }} />;
}

// A press that moves further than this, in CSS pixels, is a drag of the camera, not a click (`usePointerPick`'s).
const FINE_TAP_SLOP_PX = 4;
const COARSE_TAP_SLOP_PX = 12;

/**
 * Select's pointer: taps and the resting pointer through the picker (`usePointerPick`), and what
 * each press is made with (`pointerTypeRef`), heard before the pick's own listener hears it. A tap
 * activates as a STEP's did (`clickActivation.js`): at once, but for the second click of a
 * double-click, which the `dblclick` owns (`onDoublePick`, told whether the first click picked),
 * and a tap under a tool a pick would leave (`deferRef`: Explode, Clip), which waits the
 * double-click window. A coarse pointer has no double-click: every tap picks at once.
 */
function XbfPick({ viewport, scene, enabled, onPick, onHover, onDoublePick, deferRef, pointerTypeRef }) {
  const { hostRef, runtimeRef, viewerReadyTick } = viewport;
  const callbacks = useRef(null);
  callbacks.current = { onPick, onDoublePick };
  // The browser's count of the press just released in its click sequence (`detail`: 2 for a double-click's second).
  const countRef = useRef(0);
  const doubleClick = useMemo(() => !prefersCoarsePointer(), []);
  const activation = useMemo(() => createClickActivation({ commit: (found, options) => callbacks.current.onPick(found, options), doubleClick }),
    [doubleClick]);
  useEffect(() => {
    const host = hostRef.current;
    if (!enabled || !host) return undefined;
    const coarseDefault = prefersCoarsePointer();
    const slop = pointerType => (pointerType === "touch" || pointerType === "pen" || coarseDefault ? COARSE_TAP_SLOP_PX : FINE_TAP_SLOP_PX);
    const onCanvas = event => event.target === runtimeRef.current?.renderer?.domElement;
    const touches = new Set();
    let press = null;
    // Heard before the pick's own listeners: the press's count is known when it is taken.
    const down = (event) => {
      pointerTypeRef.current = event.pointerType || "";
      if (event.pointerType === "touch") {
        touches.add(event.pointerId);
        // A second finger is a camera gesture: no click waits through it.
        if (touches.size > 1) { press = null; activation.cancel(); return; }
      }
      // A right press is the viewport's menu: no click waits through it either.
      if (event.button !== 0) { if (event.button === 2) activation.cancel(); return; }
      press = onCanvas(event) ? { x: event.clientX, y: event.clientY, pointerId: event.pointerId, pointerType: event.pointerType || "",
        count: Number(event.detail) || 0, moved: false } : null;
    };
    // The mouse event behind the press carries the browser's count.
    const mouseDown = (event) => { if (press && event.button === 0) press.count = Math.max(press.count, Number(event.detail) || 0); };
    const move = (event) => {
      if (press?.pointerId === event.pointerId && Math.hypot(event.clientX - press.x, event.clientY - press.y) > slop(press.pointerType)) press.moved = true;
    };
    const up = (event) => {
      touches.delete(event.pointerId);
      const started = press;
      press = null;
      if (!started || event.button !== 0 || event.pointerId !== started.pointerId) return;
      countRef.current = started.count;
      // A press that was no tap (a drag of the camera): a fresh gesture's forgets an earlier click.
      if (started.moved || Math.hypot(event.clientX - started.x, event.clientY - started.y) > slop(started.pointerType)) activation.miss(started.count);
    };
    const cancel = (event) => {
      touches.delete(event.pointerId);
      if (press?.pointerId === event.pointerId) activation.miss(press.count);
      press = null;
    };
    const dblclick = (event) => {
      if (!onCanvas(event)) return;
      // Whether the first click of this gesture picked: what the double-click puts back first.
      const activated = activation.double();
      callbacks.current.onDoublePick?.(event.clientX, event.clientY, { activated });
    };
    host.addEventListener("pointerdown", down, true);
    host.addEventListener("mousedown", mouseDown, true);
    host.addEventListener("pointermove", move, true);
    host.addEventListener("pointerup", up, true);
    host.addEventListener("pointercancel", cancel, true);
    if (doubleClick) host.addEventListener("dblclick", dblclick);
    return () => {
      host.removeEventListener("pointerdown", down, true);
      host.removeEventListener("mousedown", mouseDown, true);
      host.removeEventListener("pointermove", move, true);
      host.removeEventListener("pointerup", up, true);
      host.removeEventListener("pointercancel", cancel, true);
      host.removeEventListener("dblclick", dblclick);
      // A click still waiting belongs to the tool it was made under.
      activation.cancel();
    };
  }, [enabled, hostRef, runtimeRef, viewerReadyTick, pointerTypeRef, activation, doubleClick]);
  usePointerPick({
    viewport, scene, enabled, onHover,
    onPick: (found, modifiers) => activation.tap(countRef.current, found, modifiers, { wait: Boolean(deferRef.current) }),
    sameHit: (left, right) => (left?.rest?.id || "") === (right?.rest?.id || "")
  });
  return null;
}

export default function XbfRenderer(props) {
  const { data, ...view } = props;
  return <XbfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

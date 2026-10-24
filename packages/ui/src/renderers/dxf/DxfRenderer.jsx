import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";
import { entityAt, drawEntityHighlights, snapAt } from "@text-to-cad/core/lib/drawing2d/entities.js";
import { drawAnnotationMarks } from "@text-to-cad/core/lib/drawing2d/marks.js";
import { planCamera, planProjection } from "@text-to-cad/core/lib/drawing2d/planView.js";
import { screenToModel } from "@text-to-cad/core/lib/drawing2d/index.js";
import { usePromptDestination, useViewerHost, ViewerElementContext } from "../../host/context.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import { hasOpenPopup } from "../../lib/popups.js";
import { useAnnotationSession } from "../../annotation/session.js";
import { annotationAt, withGroups } from "../../annotation/geometry.js";
import { AnnotationToolbar, DRAWING_TOOLS, annotationToolIcon, drawingToolVariant } from "../../annotation/toolbar.jsx";
import { promptView, promptViews } from "../../annotation/views.js";
import ViewerAlertCard, { useAlertDismissal } from "../kit/status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../kit/status/ViewerLoadingOverlay.js";
import { ViewUpdateStatus } from "../kit/status/ViewUpdateStatus.jsx";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "../kit/shell/viewportLayout.js";
import { ViewportTopRight } from "../kit/shell/ViewportTopRight.jsx";
import { attachLiveBinding } from "../kit/shell/liveBinding.js";
import { useWhenSettled } from "../kit/shell/useWhenSettled.js";
import { useViewerHistory } from "../kit/shell/useViewerHistory.js";
import { useViewerShortcuts } from "../kit/shell/useViewerShortcuts.js";
import { createViewPromptContext, promptDeliveryError } from "../kit/shell/promptContext.js";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import FloatingToolBar, { StripTouchProvider } from "../kit/tools/FloatingToolBar.js";
import FileSidebar from "../kit/tools/FileSidebar.jsx";
import PreviewChrome from "../kit/tools/PreviewChrome.jsx";
import { normalizeToolStack } from "../kit/tools/toolStackLayout.js";
import AnnotationOverlay, { CAD_ANNOTATION_DEFAULTS } from "../kit/tools/annotate/AnnotationOverlay.jsx";
import { MeasureIcon } from "../kit/tools/measure/SceneMeasure.jsx";
import { measureSelectHandlers } from "../kit/tools/measure/measureSelection.js";
import { useMeasureOverlay } from "../kit/tools/measure/useMeasureOverlay.js";
import { useMeasureSession } from "../kit/tools/measure/useMeasureSession.js";
import { MeasurementsBar } from "../kit/tools/measure/measurementChips.jsx";
import QuickEdit from "../kit/tools/quick-edit/QuickEdit.jsx";
import { useSceneReferences } from "../kit/tools/select/sceneReferences.jsx";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { TOUCH_HIT_PX } from "../kit/viewport/dom.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { drawingLoadAlert, useDrawingPayload } from "./useDrawingPayload.js";
import { useDrawingView } from "./useDrawingView.js";
import { drawingTransformCamera, readDrawingTransform } from "./drawingTransform.js";
import { createDrawingScene, drawingHandleOf, drawingReferenceId, drawingUnits, layersSectionShown } from "./drawingReferences.js";
import { drawingAnnotationDocument, drawingAnnotationSurface } from "./drawingAnnotation.js";
import LayersSection from "./LayersSection.jsx";
import { DXF_DECLINED_LIVE_COMMANDS, DXF_NO_CAMERA, DXF_NO_DISPLAY, DXF_TOOL, DXF_TOOL_MODES } from "./tools.js";
import { DRAWING_SHORTCUTS, TOOL_SHORTCUTS, pressToolKey } from "../kit/tools/toolShortcuts.js";

/**
 * A `.dxf` is drawn as a drawing: on a canvas, head on, in the pens it declares. No 3D, no fold
 * preview, no thickness or material, no Display settings and no Preview — a DXF is a finished 2D
 * document, and the questions those answered were about a sheet-metal part the viewer would be
 * inventing from it.
 *
 * What it has is what a person needs to talk about a drawing (`tools.js`): Select, which picks its
 * entities (by handle: `drawingReferences.js`) and is the view's hand — a drag pans, the wheel or a
 * pinch zooms, a double-click fits; Annotate, which draws on the sheet; and Measure, between points
 * snapped to its ends, centres and lines, in the unit the drawing declares (bare drawing units when
 * it declares none). What is picked and drawn is Quick Edit's (what is measured, Measure's row's), whose views are the window
 * on screen as a plan-view camera, which `cadgen snapshot --annotation PACKET --camera authored` draws again. A drawing with
 * layers and blocks to read has a Layers section in the file sidebar (`layersSectionShown`). The
 * chrome is every view's — the strip at the top centre, the tool's row under it, the sidebar at the
 * top-left, Quick Edit at the top-right — drawn from the kit's parts around the 2D canvas.
 *
 * The picture comes from the BACKEND (`GET /__cad/drawing`), which runs ezdxf over the file and
 * returns flat primitives, each naming its entity. This renderer never parses DXF.
 */

const SAVE_DELAY_MS = 180;
const DRAWING_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating drawing…" });
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const MEASURE_ICON = <MeasureIcon className="size-3.5" aria-hidden="true" />;
const NO_LAYERS = Object.freeze(new Set());
// How near a pick must be, in CSS pixels: a cursor's, or a fingertip's (`TOUCH_HIT_PX`).
const PICK_PX = 6;
const pickPx = pointerType => (pointerType === "touch" ? TOUCH_HIT_PX : PICK_PX);
const INSET = `${VIEWPORT_INSET_PX}px`;
// The strip and what hangs under it: one column at the top centre, as every view's (`RendererShell.jsx`).
const TOOLBAR_POSITION = Object.freeze({ top: INSET, left: INSET, right: INSET, bottom: INSET });
// On a phone with a sidebar, its one tile stands at the left of the strip's line.
const TOOLBAR_POSITION_PHONE_SIDEBAR = Object.freeze({ ...TOOLBAR_POSITION, left: `${VIEWPORT_INSET_PX + 46 + 8}px` });
const SIDEBAR_POSITION = Object.freeze({ top: INSET, left: INSET, bottom: INSET });
const SIDEBAR_POSITION_PHONE = Object.freeze({ top: INSET, left: INSET, bottom: `calc(var(--cad-quick-edit-peek, 0px) + ${INSET})` });

function DxfSurface({ view, data }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const mobile = useViewerMobile();
  const viewerElement = useContext(ViewerElementContext);
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = useDrawingPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const drawing = payload.drawing;
  const units = useMemo(() => drawingUnits(drawing?.units), [drawing]);
  const [actionError, setActionError] = useState(null);
  const { onReady, onStateChange } = view;
  const colorScheme = view.appearance?.colorScheme === "dark" ? "dark" : "light";

  // ---- the view this file was left at ---------------------------------------
  // The file's view (`kit/shell/fileView.js`) with the drawing's transform as its camera and
  // nothing else: a drawing has no Display settings and no slices of its own.
  const [restored] = useState(() => readDrawingTransform(readFileView(view.state).camera));
  const storedRef = useRef(JSON.stringify(writeFileView({ camera: drawingTransformCamera(restored, Boolean(restored)) })));
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(onStateChange);
  stateChangeRef.current = onStateChange;
  // A view that is still the fit stores nothing — `null` is "fit me", and it is
  // what a drawing dropped back to the fit must write, not a stale transform.
  const rememberView = useCallback((transform) => {
    const record = writeFileView({ camera: drawingTransformCamera(transform, Boolean(transform)) });
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  // ---- tools ----------------------------------------------------------------
  // The tool in hand is never saved: a drawing opens in Select.
  const [toolMode, setToolMode] = useState(DXF_TOOL_MODES.defaultMode);
  const selectTool = useCallback(mode => setToolMode(current => DXF_TOOL_MODES.next(current, mode)), []);
  const drawingFamily = toolMode === DXF_TOOL.PENCIL || toolMode === DXF_TOOL.SHAPES ? toolMode : null;
  const annotating = drawingFamily !== null;
  const measuring = toolMode === DXF_TOOL.MEASURE;
  const selecting = toolMode === DXF_TOOL.SELECT;
  const history = useViewerHistory();
  const annotation = useAnnotationSession(drawingFamily, CAD_ANNOTATION_DEFAULTS, history);
  const measure = useMeasureSession({ fileKey: file, revision: workspace.resource.revision, picking: measuring && Boolean(drawing) });
  // A measurement taken, deleted or cleared is a step of the drawing's one history, with the ink's.
  measure.history.current = history;
  const [hiddenLayers, setHiddenLayers] = useState(NO_LAYERS);
  const toggleLayer = useCallback(name => setHiddenLayers(current => {
    const next = new Set(current);
    if (!next.delete(name)) next.add(name);
    return next;
  }), []);

  // The live values the pointer's handlers read: they are bound once, to the canvas.
  const drawingRef = useRef(drawing);
  drawingRef.current = drawing;
  const hiddenRef = useRef(hiddenLayers);
  hiddenRef.current = hiddenLayers;
  const annotationRef = useRef(annotation);
  annotationRef.current = annotation;
  const toolRef = useRef(toolMode);
  toolRef.current = toolMode;
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const unitsRef = useRef(units);
  unitsRef.current = units;
  const viewRef = useRef(null);

  // What is lit (handles) and the ink under the pointer: painted over the drawing, never React state.
  const highlightRef = useRef({ hovered: [], selected: [] });
  const hoveredInkRef = useRef([]);
  const paintRef = useRef(() => {});
  const requestPaint = useCallback(() => paintRef.current(), []);
  const scene = useMemo(() => (drawing ? createDrawingScene(drawing, {
    onHighlight: ink => { highlightRef.current = ink; }, unit: units.declared ? units.unit : ""
  }) : null), [drawing, units]);
  const selection = useSceneSelection({ scene, requestRender: requestPaint });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const { references, chips } = useSceneReferences({ scene, selection, resource: workspace.resource });
  const overlay = useCallback((ctx, { transform, pixelRatio }) => {
    const drawable = drawingRef.current;
    if (!drawable) return;
    drawEntityHighlights(ctx, drawable, { transform, pixelRatio, ...highlightRef.current, hiddenLayers: hiddenRef.current });
    const session = annotationRef.current;
    drawAnnotationMarks(ctx, session.items, { transform, pixelRatio, selected: session.selected, hovered: hoveredInkRef.current });
  }, []);

  // Annotate's layer: ink on the sheet, under the view as it stands.
  const annotationSurface = useMemo(() => drawingAnnotationSurface({
    transform: () => viewRef.current?.transformRef.current || null,
    canvas: () => viewRef.current?.canvasRef.current || null
  }), []);
  // The view as Measure's and Select's kit code reads a scene's: its camera (the plan view as
  // matrices) and the element its pointer events arrive on.
  const measureRuntimeRef = useRef(null);
  if (!measureRuntimeRef.current) {
    measureRuntimeRef.current = {
      get camera() {
        const current = viewRef.current, size = current?.sizeRef.current;
        return current && size ? planProjection(current.transformRef.current, size.width, size.height) : null;
      },
      renderer: { get domElement() { return viewRef.current?.canvasRef.current || null; } }
    };
  }

  // ---- pointer: what a tap and a resting pointer do under each tool -----------
  const [pointing, setPointing] = useState(false);
  const measureHoverRef = useRef(null);
  const measureAnchorRef = useRef(null);
  useEffect(() => { if (!measuring) { measureHoverRef.current = null; measureAnchorRef.current = null; } }, [measuring]);
  useEffect(() => { if (!measure.state?.draft?.anchor) measureAnchorRef.current = null; }, [measure.state]);
  const handlers = useMemo(() => {
    // The drawing point under a pane point, and how far a pick there reaches, in drawing units.
    const atPoint = (point, pointerType) => {
      const transform = viewRef.current?.transformRef.current;
      return transform ? { model: screenToModel(transform, point.x, point.y), reach: pickPx(pointerType) / transform.scale } : null;
    };
    const snapPick = (point, pointerType) => {
      const at = atPoint(point, pointerType), drawable = drawingRef.current;
      if (!at || !drawable) return null;
      const snap = snapAt(drawable, at.model, at.reach, { hiddenLayers: hiddenRef.current });
      return { point: [snap.point[0], snap.point[1], 0], snapKind: snap.kind, units: { unit: unitsRef.current.unit, perWorld: 1 } };
    };
    const inkUnder = (point, pointerType) => (annotationRef.current.items.length
      ? annotationAt(point, annotationSurface.onScreen(annotationRef.current.items), pickPx(pointerType))[0]?.id || null : null);
    const measured = clear => measureSelectHandlers(measureRef.current, () => measureRuntimeRef.current, clear);
    const pointer = event => ({ clientX: event.clientX, clientY: event.clientY, pointerType: event.pointerType, shiftKey: event.shiftKey });
    const tap = (point, event) => {
      if (!drawingRef.current) return;
      const tool = toolRef.current;
      if (tool === DXF_TOOL.MEASURE) {
        const pick = snapPick(point, event.pointerType);
        if (!pick) return;
        // A second tap on the end already taken (a double-click, to fit) measures nothing.
        const anchor = measureAnchorRef.current;
        if (anchor && anchor.point[0] === pick.point[0] && anchor.point[1] === pick.point[1]) return;
        if (!anchor) { measureAnchorRef.current = pick; measureHoverRef.current = pick; } else measureAnchorRef.current = null;
        measureRef.current.onPick(pick);
        return;
      }
      if (tool !== DXF_TOOL.SELECT) return;
      const shift = event.shiftKey;
      const session = annotationRef.current;
      // Front to back, as every view picks: a measurement, then the ink, then the drawing's entities.
      if (measured(() => selectionRef.current.clear()).press(pointer(event))) {
        if (!shift && session.selected.length) session.select([]);
        return;
      }
      const ink = inkUnder(point, event.pointerType);
      if (ink) {
        const picked = shift ? (session.selected.includes(ink) ? session.selected.filter(id => id !== ink) : [...session.selected, ink]) : [ink];
        if (!shift) selectionRef.current.clear();
        session.select(withGroups(picked, session.items));
        return;
      }
      if (!shift && session.selected.length) session.select([]);
      const at = atPoint(point, event.pointerType);
      const handle = at ? entityAt(drawingRef.current, at.model, at.reach, { hiddenLayers: hiddenRef.current }) : "";
      selectionRef.current.pick(handle ? { id: drawingReferenceId(handle) } : null, { multiSelect: shift });
      if (handle && !shift) measureRef.current.select([]);
    };
    const hover = (point, event) => {
      const tool = toolRef.current;
      if (tool === DXF_TOOL.MEASURE) {
        const pick = point && drawingRef.current ? snapPick(point, event?.pointerType) : null;
        measureHoverRef.current = pick || measureAnchorRef.current;
        measureRef.current.onHoverPoint(pick);
        return;
      }
      let over = false, inkIds = [], handle = "";
      if (tool === DXF_TOOL.SELECT && point && drawingRef.current) {
        const onMeasurement = measured(() => {}).hover(pointer(event));
        const ink = onMeasurement ? null : inkUnder(point, event.pointerType);
        inkIds = ink ? withGroups([ink], annotationRef.current.items) : [];
        const at = onMeasurement || ink ? null : atPoint(point, event.pointerType);
        handle = at ? entityAt(drawingRef.current, at.model, at.reach, { hiddenLayers: hiddenRef.current }) : "";
        over = onMeasurement || Boolean(ink) || Boolean(handle);
      } else if (measureRef.current.hovered) measureRef.current.hover("");
      if (inkIds.join() !== hoveredInkRef.current.join()) { hoveredInkRef.current = inkIds; requestPaint(); }
      selectionRef.current.hover(handle ? drawingReferenceId(handle) : "");
      setPointing(current => (current === over ? current : over));
    };
    return { tap, hover };
  }, [annotationSurface, requestPaint]);

  const drawingView = useDrawingView({
    drawing, restored, colorScheme, onViewMoved: rememberView, hiddenLayers, overlay, onTap: handlers.tap, onHover: handlers.hover
  });
  viewRef.current = drawingView;
  paintRef.current = drawingView.requestPaint;
  const { canvasRef, capture, containerRef, dragging, fit, thumbnail } = drawingView;
  // Ink put down, picked or let go: the same view, painted again.
  useEffect(() => { requestPaint(); }, [annotation.items, annotation.selected, requestPaint]);
  // A tool put down lets go of what it lit under the pointer.
  useEffect(() => { handlers.hover(null, null); }, [toolMode, handlers]);

  // The view on screen as a prompt carries it: the plan view's camera, the pane's shape.
  const currentView = useCallback(() => {
    const current = viewRef.current, size = current?.sizeRef.current;
    const camera = current && size ? planCamera(current.transformRef.current, size.width, size.height) : null;
    return camera ? promptView({ camera, width: size.width, height: size.height }) : null;
  }, []);

  // Measure's layer: the measurements, the one being drawn, and the snap under the pointer.
  const measureCanvasRef = useRef(null);
  useMeasureOverlay({
    measureCanvasRef, measureState: measure.state, activeMeasurementId: measure.activeId,
    selectedMeasurementIds: measure.selected, hoveredMeasurementId: measure.hovered, measureHoverRef,
    measureModeActive: measuring, runtimeRef: measureRuntimeRef, mountRef: containerRef, preview: false, viewerReadyTick: 0
  });

  // ---- host chrome -----------------------------------------------------------
  useEffect(() => { onReady?.(true); }, [onReady]);

  // With a drawing on screen, a failure to read the file again leaves that drawing to use.
  const shown = Boolean(drawing);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: "Couldn’t open the drawing",
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = drawingLoadAlert(workspace.modelKey || file, payload.error);
    return failed && shown ? { ...failed, blocking: false, message: `${failed.message} The existing drawing remains visible.` } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown]);
  const empty = shown && !drawing.bounds;
  // Settled is this revision's drawing painted: a capture waits out an update.
  const ready = shown && !payload.loading && !payload.updating && !alert;

  // ---- snapshot to the prompt ------------------------------------------------
  const resourceRef = useRef(workspace.resource);
  resourceRef.current = workspace.resource;
  const promptAvailable = destination.available;
  const snapshot = useCallback(() => {
    setActionError(null);
    // The host binds its destination during the gesture, BEFORE the PNG exists.
    const pixels = capture();
    void pixels.catch(() => {});
    let pending;
    try { pending = host.promptContext.deliver(createViewPromptContext({ resource: resourceRef.current, capture: pixels })); }
    catch (error) { pending = Promise.reject(error); }
    Promise.resolve(pending)
      .catch((error) => ({ status: "failed", message: error instanceof Error ? error.message : String(error) }))
      .then((result) => setActionError(promptDeliveryError(result)));
  }, [capture, host.promptContext]);

  // A host's own capture request is the same act, acknowledged.
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;
  const captureKey = workspace.commands.captureRequest?.key ?? null;
  const appliedCapture = useRef(null);
  useEffect(() => {
    if (captureKey === null || appliedCapture.current === captureKey || !ready || !promptAvailable) return;
    appliedCapture.current = captureKey;
    workspace.acknowledgeCommand?.("captureRequest", captureKey);
    snapshotRef.current();
  }, [captureKey, ready, promptAvailable, workspace.acknowledgeCommand]);

  // A host asking to select a reference is answered rather than dropped: a person picks.
  const selectKey = workspace.commands.selectReference?.key ?? null;
  const declinedSelect = useRef(null);
  useEffect(() => {
    if (selectKey === null || declinedSelect.current === selectKey) return;
    declinedSelect.current = selectKey;
    workspace.acknowledgeCommand?.("selectReference", selectKey);
  }, [selectKey, workspace.acknowledgeCommand]);

  // ---- Quick Edit ------------------------------------------------------------
  // A note carries the views with annotation ink as JSON files — a plan-view job
  // `cadgen snapshot --annotation PACKET --camera authored` draws, the annotation on the sheet.
  const promptFile = useCallback(() => (resourceRef.current?.kind === "workspace-file" ? resourceRef.current.path : null), []);
  const annotationNow = useCallback(() => drawingAnnotationDocument(annotationRef.current.items, unitsRef.current.unit), []);
  const quickEditPrompt = useMemo(() => ({
    views: () => (host.promptFiles && promptFile() ? promptViews(currentView(), annotationRef.current.views, annotationRef.current.items) : []),
    files: views => {
      const input = promptFile();
      if (!host.promptFiles || !input || !views.length) return null;
      return host.promptFiles.create({ name: input.split("/").pop(), input, views, annotation: annotationNow() });
    },
    read: path => host.promptFiles.read(path),
  }), [host.promptFiles, promptFile, currentView, annotationNow]);
  const resourcePath = workspace.resource?.path;
  const nameReference = useCallback(reference => {
    const id = reference?.resource?.path === resourcePath && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const part = id ? scene?.describePart(id) : null;
    return part ? { name: part.name, kind: "solid" } : "";
  }, [resourcePath, scene]);
  const forgetAnnotation = annotation.forget;
  const quickEditAnnotation = useMemo(() => (annotating || annotation.hasAnnotation
    ? { present: annotation.hasAnnotation, clear: forgetAnnotation } : null), [annotating, annotation.hasAnnotation, forgetAnnotation]);
  const clearQuickEdit = () => { selection.clear(); measure.select([]); if (annotation.hasAnnotation) annotation.forget(); };
  // Annotate's copy: the drawing with its ink, to the clipboard.
  const copyAction = () => {
    if (!annotating || !shown) return false;
    void host.clipboard.writeImage(capture()).catch(error => setActionError(error instanceof Error ? error.message : String(error)));
    return true;
  };

  // ---- keys: Escape lets go, Delete deletes what Select picked, ⌘Z walks the history ----
  const letGo = () => {
    const session = annotationRef.current, now = measureRef.current;
    if (session.selected.length) { session.select([]); return true; }
    if (now.drafting) { now.cancelDraft(); return true; }
    if (now.selected.length) { now.select([]); return true; }
    if (selectionRef.current.active) { selectionRef.current.clear(); return true; }
    return false;
  };
  // The strip's tools as last drawn: what a tool's letter takes up.
  const toolKeysRef = useRef([]);
  useViewerShortcuts({
    viewerElement,
    onCopy: () => copyAction(),
    onDelete: () => {
      if (annotating) return false;
      const session = annotationRef.current;
      const ink = session.selected.length > 0;
      if (ink) session.remove(session.selected);
      return Boolean(measureRef.current.removeSelected()) || ink;
    },
    onUndo: () => history.undo(),
    onRedo: () => history.redo(),
    // A tool's letter takes it up, F fits the drawing (`toolShortcuts.js`), over the strip as drawn.
    onKey: event => shown && pressToolKey(event, { tools: toolKeysRef.current,
      selectDrawing: tool => annotationRef.current.selectTool(tool), fit }),
    escapeActive: Boolean(selection.active || measure.drafting || measure.selected.length || annotation.selected.length || !selecting),
    onEscape(event) {
      if (hasOpenPopup(viewerElement?.current)) return;
      // Annotate's layer spends its own Escape (its editor, the stroke in hand).
      if (annotating && event.target instanceof Element && event.target.closest("[data-cad-annotation-overlay]")) return;
      if (letGo()) return;
      // Nothing to let go of: the tool in hand goes down, back to Select.
      if (!selecting) selectTool(DXF_TOOL.SELECT);
    }
  });

  // ---- the live command surface ----------------------------------------------
  const referencesRef = useRef(references);
  referencesRef.current = references;
  const runtimeRef = useRef(null);
  runtimeRef.current = {
    readState: () => ({
      resource: { ...workspace.resource }, revision: String(workspace.resource.revision || ""),
      loading: payload.loading || payload.updating, selection: referencesRef.current, camera: null, display: {},
      selectedEntities: selectionRef.current.selected.map(drawingHandleOf)
    }),
    setCamera() { throw new Error(DXF_NO_CAMERA); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(DXF_NO_DISPLAY); },
    clearSelection() { selectionRef.current.clear(); },
    capture,
    thumbnail
  };
  // A drawing has settled once it is read and painted: a library card's picture waits for that.
  const whenSettled = useWhenSettled(() => ready);
  // The card the viewport shows, and its dismissal: put away, its icon in the navbar brings it back.
  const cardAlert = alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: "Couldn’t capture the drawing", message: actionError } : null);
  const alertDismissal = useAlertDismissal(cardAlert, { hasContent: shown, scope: file, onNavigationActionsChange: view.onNavigationActionsChange });
  const binding = data.services.live;
  useEffect(() => {
    if (!binding) return undefined;
    return attachLiveBinding(binding, () => runtimeRef.current, { commands: ["clearSelection"], declined: DXF_DECLINED_LIVE_COMMANDS, ready: whenSettled });
  }, [binding, whenSettled]);

  // ---- the frame ---------------------------------------------------------------
  // While the drawing loads, or once it has failed to, none of the viewer's own chrome: the load
  // itself, or the card saying why. A compact host gets the drawing alone.
  const failed = Boolean(alert) && !shown;
  const compact = Boolean(view.appearance?.compact);
  const chromeHidden = payload.loading || failed;
  const toolsHidden = chromeHidden || compact;
  const layered = layersSectionShown(drawing);
  const besideSidebarTile = mobile && layered;
  const toolStack = useMemo(() => normalizeToolStack(workspace.services.preferences?.toolStack), [workspace.services.preferences?.toolStack]);
  const toolStackRef = useRef(toolStack);
  toolStackRef.current = toolStack;
  const onPreferenceChange = workspace.services.onPreferenceChange;
  const changeToolStack = useCallback(patch => {
    const next = normalizeToolStack({ ...toolStackRef.current, ...(typeof patch === "function" ? patch(toolStackRef.current) : patch) });
    toolStackRef.current = next;
    onPreferenceChange?.({ toolStack: next });
  }, [onPreferenceChange]);
  const stripTool = (id, label, icon, extra = {}) => ({ id, label, icon, active: toolMode === id, disabled: !shown, onSelect: () => selectTool(id), ...extra });
  const tools = [
    stripTool(DXF_TOOL.SELECT, "Select", SELECT_ICON, { shortcut: TOOL_SHORTCUTS.select }),
    // Pencil and Shapes: plain buttons, each the tool last chosen in it, its tooltip that tool and its key; the tools are the row's.
    ...DRAWING_TOOLS.map(({ id, label, entries }) => {
      const variant = drawingToolVariant(id, annotation);
      const Icon = annotationToolIcon(variant);
      return stripTool(id, label, <Icon className="size-3" strokeWidth={2} aria-hidden="true" />,
        { tooltip: entries.find(entry => entry.id === variant)?.label ?? label, shortcut: DRAWING_SHORTCUTS[variant] });
    }),
    stripTool(DXF_TOOL.MEASURE, "Measure", MEASURE_ICON, { shortcut: TOOL_SHORTCUTS.measure })
  ];
  toolKeysRef.current = tools;
  // The drawing tools' row under the strip, and Measure's (its measurements, while there are any); Select has none.
  const toolRow = annotating
    ? <AnnotationToolbar annotation={annotation} colorScheme={colorScheme} placements={false} />
    : measuring ? <MeasurementsBar measure={measure} /> : null;
  const updateStatus = payload.updating && !alert ? <div className="pointer-events-none flex max-w-full items-center" data-viewport-status="">
    <ViewUpdateStatus status={DRAWING_UPDATE_STATUS} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
  </div> : null;

  // The strip's column is measured into the view's variables, as every view's is: the sidebar's
  // panel stops short of its left side, and the top-right corner (Quick Edit) starts past its right.
  const frameRef = useRef(null);
  const topControls = useRef(null);
  useLayoutEffect(() => {
    const controls = topControls.current, viewport = frameRef.current;
    if (!controls || !viewport) return undefined;
    const measureColumn = () => {
      const rows = [...controls.children].map(row => row.getBoundingClientRect()).filter(box => box.height > 0);
      const top = controls.getBoundingClientRect().top;
      viewport.style.setProperty("--cad-tools-bottom", `${Math.round(VIEWPORT_INSET_PX * 2 + Math.max(top, ...rows.map(box => box.bottom)) - top)}px`);
      if (mobile || !rows.length) {
        viewport.style.removeProperty("--cad-file-sidebar-max-width");
        viewport.style.removeProperty("--cad-top-right-left");
        return;
      }
      const box = viewport.getBoundingClientRect();
      const left = Math.min(...rows.map(row => row.left)) - box.left, right = Math.max(...rows.map(row => row.right)) - box.left;
      viewport.style.setProperty("--cad-file-sidebar-max-width", `${Math.max(0, Math.round(left - 2 * VIEWPORT_INSET_PX))}px`);
      viewport.style.setProperty("--cad-top-right-left", `${Math.round(right + VIEWPORT_INSET_PX)}px`);
    };
    measureColumn();
    if (typeof ResizeObserver === "undefined") return undefined;
    const resized = new ResizeObserver(measureColumn);
    resized.observe(controls);
    resized.observe(viewport);
    return () => {
      resized.disconnect();
      for (const name of ["--cad-tools-bottom", "--cad-file-sidebar-max-width", "--cad-top-right-left"]) viewport.style.removeProperty(name);
    };
  }, [toolsHidden, mobile, layered]);

  // The 3D views' cursors under Select: the arrow, pressed or dragging too, and the pointing hand
  // over what a press would pick. Measure keeps its crosshair (Annotate's layer has its own).
  const cursor = measuring ? "cursor-crosshair" : pointing && !dragging ? "cursor-pointer" : "cursor-default";

  return (
    <div ref={frameRef} className="@container/cad-viewport relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" data-drawing-surface data-cad-scene-backdrop="" tabIndex={-1}
      onPointerDownCapture={event => { if (event.target instanceof Element && event.target.closest("canvas")) event.currentTarget.focus({ preventScroll: true }); }}>
      <div ref={containerRef} className="relative min-h-0 flex-1" aria-busy={payload.loading || payload.updating ? "true" : "false"}>
        <canvas ref={canvasRef} aria-label={`Drawing: ${view.file.name}`} role="img" data-drawing-tool={toolMode}
          className={cn("absolute inset-0 block touch-none select-none", cursor)} />
        {/* Measure's layer, over the drawing and under the tools: the pointer stays the drawing's. */}
        <canvas ref={measureCanvasRef} className="pointer-events-none absolute inset-0 z-[1] h-full w-full" aria-hidden="true" data-scene-measure="" />
        {annotating && shown ? <AnnotationOverlay annotation={annotation} surface={annotationSurface} viewOf={currentView} /> : null}
        {empty ? (
          <p className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground"
            data-drawing-empty>
            This drawing has no geometry in its modelspace, so there is nothing to show.
          </p>
        ) : null}
      </div>
      <PreviewChrome active={false}>
        {toolsHidden ? null : <div className={cn("pointer-events-none absolute z-20 flex flex-col gap-2", besideSidebarTile ? "items-start" : "items-center")}
          style={besideSidebarTile ? TOOLBAR_POSITION_PHONE_SIDEBAR : TOOLBAR_POSITION} data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
          <StripTouchProvider value={mobile}>
            <div ref={topControls} className={cn("flex max-w-full shrink-0 flex-col gap-2", besideSidebarTile ? "items-start" : "items-center")} data-cad-top-controls="">
              <FloatingToolBar tools={tools} touch={mobile} />
              {toolRow}
              {updateStatus}
            </div>
          </StripTouchProvider>
        </div>}
        {/* The top-right: the host's notice once the drawing is on screen, and Quick Edit under it —
            hidden, not unmounted, while the drawing loads: a note being written outlives a reload. */}
        <ViewportTopRight notice={chromeHidden ? null : view.notice}>
          {compact ? null : <QuickEdit key={file} className="self-stretch" hidden={chromeHidden} docked={mobile}
            resource={workspace.resource} references={references} chips={chips} nameReference={nameReference} annotation={quickEditAnnotation}
            prompt={quickEditPrompt} onCopy={copyAction} onEscape={letGo} onClear={clearQuickEdit} disabled={!shown} />}
        </ViewportTopRight>
      </PreviewChrome>
      {toolsHidden || !layered ? null : <FileSidebar style={mobile ? SIDEBAR_POSITION_PHONE : SIDEBAR_POSITION} phone={mobile}
        layout={toolStack} onLayoutChange={changeToolStack}>
        <LayersSection drawing={drawing} hiddenLayers={hiddenLayers} onToggleLayer={toggleLayer} selection={selection} />
      </FileSidebar>}
      {/* Where there is no strip (a compact host), the drawing catching up says so at the top centre. */}
      {toolsHidden && payload.updating && !alert ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
        style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
        <ViewUpdateStatus status={DRAWING_UPDATE_STATUS} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
      </div> : null}
      <ViewerLoadingOverlay loading={{ opening: payload.loading && !alert, progress: { label: "Reading drawing" } }}
        operationKey={file} />
      <ViewerAlertCard alert={cardAlert} hasContent={shown} dismissed={alertDismissal.dismissed} onDismiss={alertDismissal.dismiss} onReload={view.reload} file={file} />
    </div>
  );
}

export default function DxfRenderer(props) {
  const { data, ...view } = props;
  return <DxfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

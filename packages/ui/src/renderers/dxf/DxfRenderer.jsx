import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box } from "lucide-react";
import { cn } from "@cad/ui/utils";
import { entityAt, drawEntityHighlights, snapAt } from "@cad/core/lib/drawing2d/entities.js";
import { drawAnnotationMarks } from "@cad/core/lib/drawing2d/marks.js";
import { planCamera, planProjection } from "@cad/core/lib/drawing2d/planView.js";
import { screenToModel } from "@cad/core/lib/drawing2d/index.js";
import { useViewerHost } from "../../host/context.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import { annotationAt, withGroups } from "../../annotation/geometry.js";
import { promptView } from "../../annotation/views.js";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import FlatViewFrame, { flatViewTools } from "../kit/shell/FlatViewFrame.jsx";
import { useFlatHandover, useFlatTools } from "../kit/shell/useFlatView.js";
import AnnotationOverlay from "../kit/tools/annotate/AnnotationOverlay.jsx";
import { measureSelectHandlers } from "../kit/tools/measure/measureSelection.js";
import { useMeasureOverlay } from "../kit/tools/measure/useMeasureOverlay.js";
import { sceneCopyText, useSceneInspect, useSceneReferences } from "../kit/tools/select/sceneReferences.jsx";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { TOUCH_HIT_PX } from "../kit/viewport/dom.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { drawingLoadAlert, useDrawingPayload } from "./useDrawingPayload.js";
import { useDrawingView } from "./useDrawingView.js";
import { menuEntry, menuGroups, pickGroup, referenceGroup, zoomGroup } from "../kit/shell/viewMenu.js";
import { drawingTransformCamera, readDrawingTransform } from "./drawingTransform.js";
import { createDrawingScene, describeDrawingPick, drawingPickTip, drawingHandleOf, drawingReferenceId, drawingUnits, layersSectionShown } from "./drawingReferences.js";
import { drawingAnnotationDocument, drawingAnnotationSurface } from "./drawingAnnotation.js";
import LayersSection from "./LayersSection.jsx";
import { DXF_DECLINED_LIVE_COMMANDS, DXF_NO_CAMERA, DXF_NO_DISPLAY, DXF_TOOL, DXF_TOOL_MODES } from "./tools.js";
import { useI18n } from "@cad/ui/i18n";

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
 * on screen as a plan-view camera, which `cad <type> snapshot --annotation PACKET --camera authored` draws again. A drawing with
 * layers and blocks to read has the view's panel docked at the left (`kit/shell/FlatPanel.jsx`, a
 * board's and a 3D view's): its search, then its Layers tab (`layersSectionShown`), kept open or
 * collapsed as the other views' panel is, ⌘\ to show or hide it and / to search it. The chrome and
 * the hands are every flat view's, a board's and a schematic's (`kit/shell/FlatViewFrame.jsx`,
 * `kit/shell/useFlatView.js`): this renderer brings its canvas, its picks and its Layers.
 *
 * The picture comes from the BACKEND (`GET /api/v1/documents/dxf/<id>/drawing`), which runs ezdxf over the file and
 * returns flat primitives, each naming its entity. This renderer never parses DXF.
 */

const SAVE_DELAY_MS = 180;
const NO_LAYERS = Object.freeze(new Set());
// The frame's own data attribute, which says what is drawn.
const DRAWING_SURFACE = Object.freeze({ "data-drawing-surface": "" });
// What a host may ask of a drawing, and the words for what it cannot (`tools.js`).
const DXF_LIVE = Object.freeze({ commands: ["clearSelection"], declined: DXF_DECLINED_LIVE_COMMANDS });
// How near a pick must be, in CSS pixels: a cursor's, or a fingertip's (`TOUCH_HIT_PX`).
const PICK_PX = 6;
const pickPx = pointerType => (pointerType === "touch" ? TOUCH_HIT_PX : PICK_PX);
// A block reference's glyph in the Selected pane and its chip's card, the Layers' own for it.
const DRAWING_GLYPHS = Object.freeze({ block: Box });

function DxfSurface({ view, data }) {
  const { t } = useI18n();
  const host = useViewerHost();
  const mobile = useViewerMobile();
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = useDrawingPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const drawing = payload.drawing;
  const units = useMemo(() => drawingUnits(drawing?.units), [drawing]);
  const { onStateChange } = view;
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

  // ---- tools: every flat view's (`kit/shell/useFlatView.js`); a drawing opens in Select ----
  const tools = useFlatTools({ toolModes: DXF_TOOL_MODES, file, revision: workspace.resource.revision, ready: Boolean(drawing) });
  const { toolMode, annotating, measuring, annotation, measure } = tools;
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
    onHighlight: ink => { highlightRef.current = ink; }, unit: units.unit, t
  }) : null), [drawing, units, t]);
  const selection = useSceneSelection({ scene, requestRender: requestPaint });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  // What a pick is, as the Selected pane, its chip's card and the hover tip read it (`describeDrawingPick`).
  const describe = useCallback(id => (drawing ? describeDrawingPick(drawing, id, units.unit, t) : null), [drawing, units, t]);
  const { references, chips } = useSceneReferences({ scene, selection, resource: workspace.resource, describe });
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
      selectionRef.current.hoverHit(handle ? { id: drawingReferenceId(handle) } : null);
      setPointing(current => (current === over ? current : over));
    };
    // The entity under a pane point, as Select would take it ("" for none).
    const entityUnder = (point, pointerType) => {
      const at = atPoint(point, pointerType);
      return at && drawingRef.current ? entityAt(drawingRef.current, at.model, at.reach, { hiddenLayers: hiddenRef.current }) : "";
    };
    return { tap, hover, entityUnder };
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

  // With a drawing on screen, a failure to read the file again leaves that drawing to use.
  const shown = Boolean(drawing);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: t("alert.openDrawingFailed"),
        message: t("alert.catalogFailed"),
        recovery: t("alert.catalogRecovery"),
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = drawingLoadAlert(workspace.modelKey || file, payload.error, t);
    return failed && shown ? { ...failed, blocking: false, message: t("alert.drawingStillShown", { message: failed.message }) } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown, t]);
  const empty = shown && !drawing.bounds;
  // Settled is this revision's drawing painted: a capture waits out an update.
  const ready = shown && !payload.loading && !payload.updating && !alert;

  // A host asking to select a reference is answered rather than dropped: a person picks.
  const selectKey = workspace.commands.selectReference?.key ?? null;
  const declinedSelect = useRef(null);
  useEffect(() => {
    if (selectKey === null || declinedSelect.current === selectKey) return;
    declinedSelect.current = selectKey;
    workspace.acknowledgeCommand?.("selectReference", selectKey);
  }, [selectKey, workspace.acknowledgeCommand]);

  const resourcePath = workspace.resource?.path;
  const nameReference = useCallback(reference => {
    const id = reference?.resource?.path === resourcePath && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const part = id ? scene?.describePart(id) : null;
    return part ? { name: part.name, kind: "solid" } : "";
  }, [resourcePath, scene]);
  // ---- Quick Edit, the keys and the live command surface: every flat view's (`useFlatHandover`) ----
  const referencesRef = useRef(references);
  referencesRef.current = references;
  const runtime = {
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
  const annotationDocument = useCallback(items => drawingAnnotationDocument(items, unitsRef.current.unit), []);
  const handover = useFlatHandover({
    view, data, workspace, file, shown, ready, alert, tools, selection, references, chips, nameReference,
    capture, currentView, annotationDocument, runtime, live: DXF_LIVE, fit, captureFailed: t("alert.captureDrawingFailed")
  });

  // ---- the menu: a secondary tap on the drawing, under Select (`kit/shell/viewMenu.js`'s groups) ----
  // Over an entity: its reference (with what is picked already), Select or Deselect, Hide its layer,
  // then the framing. Over bare paper: Show all layers while any is hidden, and the framing.
  const frameEntities = useCallback(ids => {
    const drawable = drawingRef.current;
    const boxes = ids.map(id => drawable?.entities?.get(drawingHandleOf(id))?.box).filter(Boolean);
    if (!boxes.length) return;
    drawingView.frame([Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])), Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3]))]);
  }, [drawingView]);
  const contextMenuItems = shown && toolMode === DXF_TOOL.SELECT ? press => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const handle = handlers.entityUnder({ x: press.clientX - rect.left, y: press.clientY - rect.top }, "mouse");
    const now = selectionRef.current;
    const zoom = zoomGroup({ t, onZoomFit: fit, onZoomSelection: () => frameEntities(selectionRef.current.selected), selectionAvailable: now.selected.length > 0 });
    if (!handle) {
      return menuGroups(hiddenLayers.size ? [menuEntry("show-all-layers", t("menu.showAllLayers"), { onSelect: () => setHiddenLayers(NO_LAYERS) })] : [], zoom);
    }
    const id = drawingReferenceId(handle), selected = now.selected.includes(id);
    const layer = drawingRef.current?.entities?.get(handle)?.layer || "0";
    const copyText = sceneCopyText(workspace.resource, [...new Set([...now.selected, id])]);
    return menuGroups(
      referenceGroup({ copyText, onCopy: () => { void Promise.resolve(host.clipboard.writeText(copyText)).catch(() => {}); }, t }),
      pickGroup({ selected, onSelect: () => now.select(id, { multiSelect: selected }), t }),
      [menuEntry("hide-layer", t("layers.hideNamed", { name: layer }), { onSelect: () => toggleLayer(layer) })],
      zoom);
  } : null;

  // What is picked, as the frame reads it: the Selected pane under the Layers, the hover tip, the cards' rows.
  const resource = workspace.resource;
  const copyText = useCallback(ids => sceneCopyText(resource, ids), [resource]);
  const tip = useCallback(id => (drawing ? drawingPickTip(drawing, id, units.unit, t) : ""), [drawing, units, t]);
  const inspect = useSceneInspect({ scene, selection, describe, tip, frame: frameEntities, copyText, glyphs: DRAWING_GLYPHS, data: "drawing" });

  // ---- the frame: every flat view's (`kit/shell/FlatViewFrame.jsx`) around the drawing's canvas ----
  // While the drawing loads, or once it has failed to, none of the viewer's own chrome. A compact host
  // gets the drawing alone.
  const failed = Boolean(alert) && !shown;
  const compact = Boolean(view.appearance?.compact);
  const chromeHidden = payload.loading || failed;
  const { strip, row } = flatViewTools(tools, { colorScheme, shown, t });
  // The strip's zoom, and the zoom's keys (`useFlatHandover`'s `zoomKeys`).
  const zoom = { ...drawingView.zoom, zoomToSelection: () => frameEntities(selectionRef.current.selected), selectionAvailable: selection.selected.length > 0 };
  handover.zoomKeys.current = zoom;
  // The panel: the drawing's Layers, where it has layers and blocks to read (`layersSectionShown`).
  const panel = layersSectionShown(drawing) ? { kind: "drawing", label: t("drawing.panel"), searchLabel: t("drawing.search"), tabs: [{
    id: "layers", label: t("layers.title"),
    content: <LayersSection drawing={drawing} hiddenLayers={hiddenLayers} onToggleLayer={toggleLayer} selection={selection} />
  }] } : null;

  // The 3D views' cursors under Select: the arrow, pressed or dragging too, and the pointing hand
  // over what a press would pick. Measure keeps its crosshair (Annotate's layer has its own).
  const cursor = measuring ? "cursor-crosshair" : pointing && !dragging ? "cursor-pointer" : "cursor-default";

  return (
    <FlatViewFrame surface={DRAWING_SURFACE} containerRef={containerRef} busy={payload.loading || payload.updating}
      file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} loading={payload.loading} loadingLabel={t("drawing.reading")}
      updating={payload.updating} updateStatus={{ pending: true, label: t("drawing.updating") }} tools={strip} toolRow={row} views={[]}
      panel={panel} panelControl={handover.panelControl} toolStack={handover.toolStack} onToolStackChange={handover.changeToolStack} notice={view.notice}
      quickEdit={handover.quickEdit} alert={alert} cardAlert={handover.cardAlert} alertDismissal={handover.alertDismissal}
      shown={shown} onReload={view.reload} canvasRef={canvasRef} contextMenuItems={contextMenuItems} zoom={zoom} inspect={inspect}>
      <canvas ref={canvasRef} aria-label={t("drawing.canvas", { name: view.file.name })} role="img" data-drawing-tool={toolMode}
        className={cn("absolute inset-0 block touch-none select-none", cursor)} />
      {/* Measure's layer, over the drawing and under the tools: the pointer stays the drawing's. */}
      <canvas ref={measureCanvasRef} className="pointer-events-none absolute inset-0 z-[1] h-full w-full" aria-hidden="true" data-scene-measure="" />
      {annotating && shown ? <AnnotationOverlay annotation={annotation} surface={annotationSurface} viewOf={currentView} /> : null}
      {empty ? (
        <p className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground"
          data-drawing-empty>
          {t("drawing.empty")}
        </p>
      ) : null}
    </FlatViewFrame>
  );
}

export default function DxfRenderer(props) {
  const { data, ...view } = props;
  return <DxfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

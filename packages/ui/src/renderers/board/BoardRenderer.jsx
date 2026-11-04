import { useI18n } from "@cad/ui/i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@cad/ui/utils";
import { boardOverlayColors, drawBoardOverlay } from "@cad/core/lib/board2d/boardOverlay.js";
import { buildBoardRefToken, parseBoardRefSelector, splitBoardRefSelectors } from "@cad/core/lib/boardRefs.js";
import { drawAnnotationMarks } from "@cad/core/lib/drawing2d/marks.js";
import { planCamera } from "@cad/core/lib/drawing2d/planView.js";
import { screenToModel } from "@cad/core/lib/drawing2d/index.js";
import {
  boardDisplayAirwires, boardDrawView, boardMirrorX, boardPlanProjection, marksInPlan, nextBoardOthers, planToSheet
} from "@cad/core/lib/plot2d/index.js";
import { useViewerHost } from "../../host/context.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import { annotationAt, withGroups } from "../../annotation/geometry.js";
import { promptView } from "../../annotation/views.js";
import FlatViewFrame, { flatViewTools } from "../kit/shell/FlatViewFrame.jsx";
import { useFlatHandover, useFlatTools } from "../kit/shell/useFlatView.js";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import AnnotationOverlay from "../kit/tools/annotate/AnnotationOverlay.jsx";
import { measureSelectHandlers } from "../kit/tools/measure/measureSelection.js";
import { useMeasureOverlay } from "../kit/tools/measure/useMeasureOverlay.js";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { TOUCH_HIT_PX } from "../kit/viewport/dom.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { plotAnnotationDocument, plotAnnotationSurface } from "../kit/tools/annotate/plotAnnotation.js";
import { useBoardReferences } from "./boardReferences.jsx";
import { createBoardScene } from "./boardScene.js";
import { readBoardDisplay } from "./BoardDisplay.jsx";
import BoardSection from "./BoardSection.jsx";
import BoardSelectFilter from "./BoardSelectFilter.jsx";
import LayersSection from "./LayersSection.jsx";
import {
  BOARD_DEFAULT_FILTER, BOARD_NO_CAMERA, BOARD_NO_DISPLAY, BOARD_TOOL, BOARD_TOOL_MODES, boardPickKinds, boardWorkingLayer, readBoardFilter
} from "./tools.js";
import { useBoardDocument } from "./useBoardDocument.js";
import { readIsolation, useIsolation } from "../kit/tools/select/useIsolation.js";
import { useBoardView } from "./useBoardView.js";

/**
 * A KiCad board as the picture drawn from its file, on a canvas, head on, as a drawing is: in
 * KiCad's colours, layer by layer, on the app's canvas, in the view's theme — KiCad's own on the
 * dark canvas, the same hues darkened to read on the light one (`plot2d/theme.js`), the overlay's
 * highlight and dim too (`board2d/boardOverlay.js`); a switch of theme draws it again here, from
 * the payload it holds (the payload comes from the BACKEND, `GET /api/v1/documents/kicad_pcb/<id>/plot`,
 * geometry alone; nothing here parses KiCad's files).
 *
 * It is a flat view, composed exactly as a drawing's (`../dxf/DxfRenderer.jsx`), from the same
 * kit (`kit/shell/FlatViewFrame.jsx`, `useFlatView.js`): Select, as KiCad's — a click picks the most
 * specific thing under the pointer that its filter (KiCad's Selection Filter, `BoardSelectFilter.jsx`)
 * ticks, on a layer the Display draws (a pad, a via, a track, a text, a dimension, a graphic, a pour
 * or a rule area by its outline, then a part), Shift adds, and a click on nothing clears; a drag
 * draws a box and names the area, on the view's working layer (`tools.js`); the rest are the 3D
 * views' drags (a right or middle drag, or a drag with Ctrl, Cmd or Shift, pans; the wheel, a
 * trackpad's two-finger scroll or a pinch zooms), a double-click fits — Annotate, which
 * draws on the board, and Measure, between points snapped to pad, via and hole centres, track ends
 * and outline corners, in millimetres. What is picked, drawn and measured is Quick Edit's, in board
 * references (`#R1`, `#R1.2`, `#net:VBUS`, `#track:<uuid>`, `#F.Cu@x10y5..x20y15`), whose views are the window on screen as a plan-view camera with the
 * board's Display, which `cad <type> snapshot --job` draws again, the references lit. Its panel
 * (`kit/shell/FlatPanel.jsx`) is a search over two tabs, the Circuit (its parts in their schematic
 * blocks, and its nets) and the Layers (the board's view settings — preset, side, the other layers,
 * the pours and the zones' and tracks' opacities, `BoardDisplay.jsx` — and each layer's eye, a row's
 * press for the active layer): one contract with `cad <type> snapshot --display`. The strip has no view controls. A payload without its
 * index (an older server's) is the picture alone: no tools, no Circuit, no Quick Edit.
 */

const SAVE_DELAY_MS = 180;
// What the frame says it draws: a board, on its theme's canvas.
const BOARD_SURFACE = Object.freeze({ "data-board-surface": "" });
// The file's slices: the board's Display and what is isolated, kept across rebuilds.
const SLICES = Object.freeze({ board: "1", isolated: "1" });

const BOARD_LIVE = Object.freeze({ commands: Object.freeze(["select", "clearSelection"]), declined: Object.freeze({}) });
const NO_SELECTION = Object.freeze({ hovered: [], selected: [] });
// How near a pick must be, in CSS pixels: a cursor's, or a fingertip's (`TOUCH_HIT_PX`).
const PICK_PX = 6;
const pickPx = pointerType => (pointerType === "touch" ? TOUCH_HIT_PX : PICK_PX);
const finite = value => typeof value === "number" && Number.isFinite(value);
/** The stored view, or null for the fit: nothing but the transform's three numbers. */
function readTransform(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const { scale, offsetX, offsetY } = raw;
  return finite(scale) && scale > 0 && finite(offsetX) && finite(offsetY) ? { scale, offsetX, offsetY } : null;
}
/** What a board's snapshot packet carries of its prompt's references: their selectors into the board, once each, as the box orders them. */
const boardPacketReferences = (references, file) => [...new Set(references
  .filter(reference => reference?.resource?.path === file && reference.target?.kind === "cad-selector")
  .flatMap(reference => reference.target.selectors))];
/** The board's Display as a view carries it, and a snapshot job reads it. */
const viewDisplay = display => ({ mode: display.mode, side: display.side, poured: display.poured, ...(display.layers ? { layers: [...display.layers] } : {}),
  ...(display.active ? { active: display.active } : {}), others: display.others, zones: display.zones, tracks: display.tracks });

function BoardSurface({ view, data }) {
  const { t } = useI18n();
  const host = useViewerHost();
  const mobile = useViewerMobile();
  const workspace = useWorkspaceDocument({ view, data });
  const document = useBoardDocument({ workspace, path: view.file.path });
  const { file, plot, index, sheet, layered, shown, alert } = document;
  const colorScheme = view.appearance?.colorScheme === "dark" ? "dark" : "light";

  // ---- the file's view: the transform, the board's Display, what is isolated ----
  const [stored] = useState(() => readFileView(view.state, SLICES));
  const [restored] = useState(() => readTransform(stored.camera));
  const [display, setDisplay] = useState(() => readBoardDisplay(stored.renderer.board));
  const canonicalPick = useCallback(id => index?.resolve(id)?.selector, [index]);
  const [restoredIsolation] = useState(() => readIsolation(stored.renderer.isolated?.selectors));
  const isolation = useIsolation({ index, restored: restoredIsolation, canonical: canonicalPick });
  const saved = useRef({ camera: restored, display, isolated: restoredIsolation });
  const storedRef = useRef("");
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(view.onStateChange);
  stateChangeRef.current = view.onStateChange;
  const save = useCallback(change => {
    saved.current = { ...saved.current, ...change };
    const { camera, display: board, isolated } = saved.current;
    const record = writeFileView({ camera, renderer: { board, isolated: { selectors: [...isolated] } }, signatures: SLICES });
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  // A view that is still the fit stores no camera: `null` is "fit me".
  const rememberView = useCallback(transform => save({ camera: transform ? { ...transform } : null }), [save]);
  useEffect(() => { storedRef.current = JSON.stringify(writeFileView({ camera: restored, renderer: { board: display, isolated: { selectors: [...restoredIsolation] } }, signatures: SLICES })); }, []);
  useEffect(() => { save({ display, isolated: isolation.isolated }); }, [display, isolation.isolated, save]);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  // ---- tools ----------------------------------------------------------------
  const tools = useFlatTools({ toolModes: BOARD_TOOL_MODES, file, revision: workspace.resource.revision, ready: Boolean(index) });
  const { toolMode, selectTool, annotating, measuring, annotation, measure } = tools;
  // Select's filter: every kind ticked and no locked items as a board opens (KiCad's), and held while it
  // is open, across its rebuilds; a filter of another shape (the earlier Nets or Point or area) drops what it named.
  const [filter, setFilter] = useState(BOARD_DEFAULT_FILTER);
  const changeFilter = useCallback(next => { setFilter(readBoardFilter(next)); selectTool(BOARD_TOOL.SELECT); }, [selectTool]);
  const drawView = useMemo(() => (sheet ? boardDrawView(display, sheet) : null), [display, sheet]);
  const mirrorX = boardMirrorX(sheet, display.side);

  // The live values the pointer's handlers read: they are bound once, to the canvas.
  const indexRef = useRef(index);
  indexRef.current = index;
  const mirrorRef = useRef(mirrorX);
  mirrorRef.current = mirrorX;
  const filterRef = useRef(filter);
  filterRef.current = filter;
  const sideRef = useRef(display.side);
  sideRef.current = display.side;
  // What a press may take is on a layer the Display draws; a dragged area is on its working layer.
  const drawnLayers = useMemo(() => new Set(drawView?.layers || []), [drawView]);
  const drawnRef = useRef(drawnLayers);
  drawnRef.current = drawnLayers;
  const workingRef = useRef(null);
  workingRef.current = drawView ? boardWorkingLayer(sheet, drawView.layers, display.side) : null;
  // The box an area is being dragged over (page millimetres), painted over the board: never React state.
  const draftRef = useRef(null);
  const placementRef = useRef(false);
  placementRef.current = boardDisplayAirwires(display);
  const isolationRef = useRef(isolation);
  isolationRef.current = isolation;
  const annotationRef = useRef(annotation);
  annotationRef.current = annotation;
  const toolRef = useRef(toolMode);
  toolRef.current = toolMode;
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const viewRef = useRef(null);

  // What is lit (resolved references) and the ink under the pointer: painted over the board, never React state.
  const highlightRef = useRef(NO_SELECTION);
  const hoveredInkRef = useRef([]);
  const paintRef = useRef(() => {});
  const requestPaint = useCallback(() => paintRef.current(), []);
  const scene = useMemo(() => (index ? createBoardScene(index, { t, onHighlight: ink => { highlightRef.current = ink; } }) : null), [index, t]);
  const selection = useSceneSelection({ scene, requestRender: requestPaint });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const { references, chips } = useBoardReferences({ scene, selection, resource: workspace.resource });
  // The overlay's colours are the theme's (`board2d/boardOverlay.js`): a highlight that reads on the canvas under it.
  const schemeRef = useRef(colorScheme);
  schemeRef.current = colorScheme;
  const overlay = useCallback((ctx, { transform, pixelRatio, width, height }) => {
    const board = indexRef.current;
    if (!board) return;
    const colors = boardOverlayColors(schemeRef.current);
    const base = { transform, pixelRatio, width, height, mirrorX: mirrorRef.current, colors };
    const isolated = isolationRef.current.resolved;
    // What is isolated first, everything else stepped back; then the hover and the selection (a net
    // in focus steps the rest back).
    if (isolated.length) {
      drawBoardOverlay(ctx, board, { ...base, dim: true, selection: isolated, colors: { ...colors, selection: colors.hover } });
    }
    const { hovered, selected } = highlightRef.current;
    const net = selected.some(item => item.kind === "net");
    drawBoardOverlay(ctx, board, { ...base, hover: hovered[0] || null, selection: selected, dim: net && !isolated.length, placement: placementRef.current,
      draft: draftRef.current });
    const session = annotationRef.current;
    drawAnnotationMarks(ctx, marksInPlan(session.items, mirrorRef.current), { transform, pixelRatio, selected: session.selected, hovered: hoveredInkRef.current });
  }, []);

  // Annotate's layer: ink on the board, under the view (and its side) as it stands.
  const annotationSurface = useMemo(() => plotAnnotationSurface({
    transform: () => viewRef.current?.transformRef.current || null,
    mirrorX: () => mirrorRef.current,
    canvas: () => viewRef.current?.canvasRef.current || null
  }), []);
  // The view as Measure's and Select's kit code reads a scene's: its camera (the sheet to the screen
  // as matrices, through the mirror from below) and the element its pointer events arrive on.
  const measureRuntimeRef = useRef(null);
  if (!measureRuntimeRef.current) {
    measureRuntimeRef.current = {
      get camera() {
        const current = viewRef.current, size = current?.sizeRef.current;
        return current && size ? boardPlanProjection(current.transformRef.current, size.width, size.height, mirrorRef.current) : null;
      },
      renderer: { get domElement() { return viewRef.current?.canvasRef.current || null; } }
    };
  }

  // ---- pointer: what a tap and a resting pointer do under each tool -----------
  const [overPick, setOverPick] = useState(false);
  const measureHoverRef = useRef(null);
  const measureAnchorRef = useRef(null);
  useEffect(() => { if (!measuring) { measureHoverRef.current = null; measureAnchorRef.current = null; } }, [measuring]);
  useEffect(() => { if (!measure.state?.draft?.anchor) measureAnchorRef.current = null; }, [measure.state]);
  const handlers = useMemo(() => {
    // The sheet point under a pane point, and how far a pick there reaches, in millimetres.
    const atPoint = (point, pointerType) => {
      const transform = viewRef.current?.transformRef.current;
      return transform ? { page: planToSheet(screenToModel(transform, point.x, point.y), mirrorRef.current), reach: pickPx(pointerType) / transform.scale } : null;
    };
    // Measure's end: a pad, via or hole centre, a track end or an outline corner near the pointer, else the point itself.
    const snapPick = (point, pointerType) => {
      const at = atPoint(point, pointerType), board = indexRef.current;
      if (!at || !board) return null;
      const snap = board.snap(at.page, { tolerance: at.reach });
      const [x, y] = snap ? snap.point : at.page;
      return { point: [x, y, 0], snapKind: snap ? snap.kind : "free", units: { unit: "mm", perWorld: 1 } };
    };
    const pickAt = (point, pointerType) => {
      const at = atPoint(point, pointerType), board = indexRef.current, kinds = boardPickKinds(filterRef.current);
      return at && board && kinds ? board.pick(at.page, { kinds, view: sideRef.current, tolerance: at.reach, layers: drawnRef.current }) : null;
    };
    const inkUnder = (point, pointerType) => (annotationRef.current.items.length
      ? annotationAt(point, annotationSurface.onScreen(annotationRef.current.items), pickPx(pointerType))[0]?.id || null : null);
    const measured = clear => measureSelectHandlers(measureRef.current, () => measureRuntimeRef.current, clear);
    const pointer = event => ({ clientX: event.clientX, clientY: event.clientY, pointerType: event.pointerType, shiftKey: event.shiftKey });
    const tap = (point, event) => {
      if (!indexRef.current) return;
      const tool = toolRef.current;
      if (tool === BOARD_TOOL.MEASURE) {
        const pick = snapPick(point, event.pointerType);
        if (!pick) return;
        // A second tap on the end already taken (a double-click, to fit) measures nothing.
        const anchor = measureAnchorRef.current;
        if (anchor && anchor.point[0] === pick.point[0] && anchor.point[1] === pick.point[1]) return;
        if (!anchor) { measureAnchorRef.current = pick; measureHoverRef.current = pick; } else measureAnchorRef.current = null;
        measureRef.current.onPick(pick);
        return;
      }
      if (tool !== BOARD_TOOL.SELECT) return;
      const shift = event.shiftKey;
      const session = annotationRef.current;
      // Front to back, as every view picks: a measurement, then the ink, then the board's own.
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
      const hit = pickAt(point, event.pointerType);
      selectionRef.current.pick(hit ? { id: hit.selector } : null, { multiSelect: shift });
      if (hit && !shift) measureRef.current.select([]);
    };
    const hover = (point, event) => {
      const tool = toolRef.current;
      if (tool === BOARD_TOOL.MEASURE) {
        const pick = point && indexRef.current ? snapPick(point, event?.pointerType) : null;
        measureHoverRef.current = pick || measureAnchorRef.current;
        measureRef.current.onHoverPoint(pick);
        return;
      }
      let over = false, inkIds = [], hit = null;
      if (tool === BOARD_TOOL.SELECT && point && indexRef.current) {
        const onMeasurement = measured(() => {}).hover(pointer(event));
        const ink = onMeasurement ? null : inkUnder(point, event.pointerType);
        inkIds = ink ? withGroups([ink], annotationRef.current.items) : [];
        hit = onMeasurement || ink ? null : pickAt(point, event.pointerType);
        over = onMeasurement || Boolean(ink) || Boolean(hit);
      } else if (measureRef.current.hovered) measureRef.current.hover("");
      if (inkIds.join() !== hoveredInkRef.current.join()) { hoveredInkRef.current = inkIds; requestPaint(); }
      selectionRef.current.hover(hit ? hit.selector : "");
      setOverPick(current => (current === over ? current : over));
    };
    // Select's drag is the box between its ends, KiCad's window selection: drawn as it goes, an area
    // on the working layer once it lets go (Shift adds it); a drag cancelled (a second finger) is nothing.
    const drag = (phase, { start, point, event }) => {
      const board = indexRef.current;
      if (toolRef.current !== BOARD_TOOL.SELECT || !board) return false;
      const from = atPoint(start, "mouse")?.page, to = atPoint(point, "mouse")?.page;
      if (!from || !to) return false;
      draftRef.current = phase === "start" || phase === "move"
        ? [Math.min(from[0], to[0]), Math.min(from[1], to[1]), Math.max(from[0], to[0]), Math.max(from[1], to[1])] : null;
      requestPaint();
      if (phase === "end") selectionRef.current.pick({ id: board.areaSelector(from, to, workingRef.current) }, { multiSelect: Boolean(event?.shiftKey) });
      return true;
    };
    return { tap, hover, drag };
  }, [annotationSurface, requestPaint]);

  const boardView = useBoardView({
    plot, restored, colorScheme, onViewMoved: rememberView, drawView, overlay, onTap: handlers.tap, onHover: handlers.hover, onDrag: handlers.drag
  });
  viewRef.current = boardView;
  paintRef.current = boardView.requestPaint;
  const { canvasRef, capture, containerRef, dragging, fit, thumbnail } = boardView;
  // A row of the Circuit pressed: what it picked, framed, from the side looked at (a page box to the plan's model space).
  const frameSelectors = useCallback(selectors => {
    const board = indexRef.current;
    if (!board) return;
    const boxes = selectors.map(id => board.extent(board.resolve(id))).filter(Boolean);
    if (!boxes.length) return;
    let [x0, y0, x1, y1] = [Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])), Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3]))];
    const mirror = mirrorRef.current;
    if (mirror != null) [x0, x1] = [2 * mirror - x1, 2 * mirror - x0];
    viewRef.current?.frame([x0, -y1, x1, -y0]);
  }, []);
  // Ink put down, picked or let go, a side or an isolation changed: the same view, painted again.
  useEffect(() => { requestPaint(); }, [annotation.items, annotation.selected, display, isolation.resolved, requestPaint]);
  // A tool put down lets go of what it lit under the pointer.
  useEffect(() => { handlers.hover(null, null); }, [toolMode, handlers]);

  // The view on screen as a prompt carries it: the plan view's camera, the pane's shape, and the
  // board's Display, so a snapshot draws the layers, the pours and the side the person saw.
  const displayRef = useRef(display);
  displayRef.current = display;
  const currentView = useCallback(() => {
    const current = viewRef.current, size = current?.sizeRef.current;
    const camera = current && size ? planCamera(current.transformRef.current, size.width, size.height) : null;
    const seen = camera ? promptView({ camera, width: size.width, height: size.height }) : null;
    // The view as it was seen: its Display and the theme it was drawn in (a snapshot's `appearance`).
    return seen ? { ...seen, display: { ...viewDisplay(displayRef.current), appearance: schemeRef.current } } : null;
  }, []);

  // Measure's layer: the measurements, the one being drawn, and the snap under the pointer.
  const measureCanvasRef = useRef(null);
  useMeasureOverlay({
    measureCanvasRef, measureState: measure.state, activeMeasurementId: measure.activeId,
    selectedMeasurementIds: measure.selected, hoveredMeasurementId: measure.hovered, measureHoverRef,
    measureModeActive: measuring, runtimeRef: measureRuntimeRef, mountRef: containerRef, preview: false, viewerReadyTick: 0
  });

  // Settled is this revision's board painted: a capture waits out an update.
  const ready = shown && !document.loading && !document.updating && !alert;

  // A host asking to select a reference selects it, once the board's index is in.
  const selectRequest = workspace.commands.selectReference ?? null;
  const selectKey = selectRequest?.key ?? null;
  const handledSelect = useRef(null);
  const { acknowledgeCommand } = workspace;
  useEffect(() => {
    if (selectKey === null || handledSelect.current === selectKey) return;
    const named = splitBoardRefSelectors(selectRequest?.selector).map(selector => parseBoardRefSelector(selector)?.canonical).filter(Boolean);
    if (index && named.length) {
      selectionRef.current.clear();
      for (const selector of named) if (index.resolve(selector)) selectionRef.current.select(selector, { multiSelect: true });
    } else if (document.loading) return;
    handledSelect.current = selectKey;
    acknowledgeCommand?.("selectReference", selectKey);
  }, [selectKey, selectRequest, index, document.loading, acknowledgeCommand]);

  // ---- Quick Edit, the keys and the live command surface ------------------------
  const nameReference = useCallback(reference => {
    const id = reference?.resource?.path === workspace.resource?.path && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const described = id ? scene?.describePart(id) : null;
    return described ? { name: described.name, kind: described.glyph } : "";
  }, [workspace.resource?.path, scene]);
  // The copy key, while Annotate is not up: the selection's references, comma-joined after the file.
  const path = workspace.resource?.kind === "workspace-file" ? workspace.resource.path : "";
  const copySelection = () => {
    const selected = selectionRef.current.selected;
    if (!selected.length || !path) return false;
    void Promise.resolve(host.clipboard.writeText(buildBoardRefToken({ path, selectors: selected })))
      .catch(error => handover.reportActionError(error instanceof Error ? error.message : String(error)));
    return true;
  };
  const selectList = request => {
    const raw = Array.isArray(request) ? request : Array.isArray(request?.selectors) ? request.selectors : [request?.selector ?? request];
    const list = raw.flatMap(selector => splitBoardRefSelectors(selector));
    const unknown = list.filter(selector => !parseBoardRefSelector(selector) || !index?.resolve(selector));
    if (!index || unknown.length) {
      throw new Error(`Not on this board: ${unknown.join(", ") || list.join(", ")}. Select board references such as #U3, #U3.9, #net:VIN, `
        + "#track:<uuid> (#via:, #zone:, #text:, #dimension:, #shape:), #F.Cu@x10y5 or #F.Cu@x10y5..x20y15.");
    }
    selectionRef.current.clear();
    for (const selector of list) selectionRef.current.select(parseBoardRefSelector(selector).canonical, { multiSelect: true });
  };
  const runtime = {
    readState: () => ({
      resource: { ...workspace.resource }, revision: String(workspace.resource.revision || ""),
      loading: document.loading || document.updating, selection: references, camera: null, display: {},
      boardDisplay: viewDisplay(displayRef.current)
    }),
    setCamera() { throw new Error(BOARD_NO_CAMERA); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(BOARD_NO_DISPLAY); },
    select: selectList,
    clearSelection() { selectionRef.current.clear(); },
    capture,
    thumbnail
  };
  // Ctrl+H (⌘H), as KiCad's: the other layers shown, dimmed, hidden, and round again.
  const cycleOthers = useCallback(event => {
    if (event.key.toLowerCase() !== "h" || event.shiftKey || !layered) return false;
    setDisplay(current => ({ ...current, others: nextBoardOthers(current.others) }));
    return true;
  }, [layered, setDisplay]);
  const handover = useFlatHandover({
    view, data, workspace, file, shown, ready, alert, tools, selection, references, chips, nameReference,
    capture, currentView, annotationDocument: plotAnnotationDocument, runtime, live: BOARD_LIVE, onChord: cycleOthers,
    copySelection: index ? copySelection : null, fit, captureFailed: t("alert.captureDrawingFailed"), packetReferences: boardPacketReferences
  });

  // ---- the frame ---------------------------------------------------------------
  // While the board loads, or once it has failed to, none of the viewer's own chrome. A compact host
  // gets the board alone; a payload without its index, the picture and its Display alone.
  const failed = Boolean(alert) && !shown;
  const compact = Boolean(view.appearance?.compact);
  const chromeHidden = document.loading || failed;
  const selectMenu = <BoardSelectFilter value={filter} onChange={changeFilter} disabled={!shown} />;
  const { strip, row } = flatViewTools(tools, { colorScheme, shown, selectMenu, t });
  // The panel (`kit/shell/FlatPanel.jsx`): the Circuit, then the Layers with the board's view settings.
  const panelTabs = [
    ...(index ? [{ id: "circuit", label: t("board.text.circuit"), searchLast: true, content: <BoardSection index={index} selection={selection} isolated={isolation.isolated}
      onIsolate={isolation.toggle} onFrame={frameSelectors} onSelect={() => selectTool(BOARD_TOOL.SELECT)} /> }] : []),
    ...(layered ? [{ id: "layers", label: t("layers.title"), content: <LayersSection sheet={sheet} display={display} onDisplayChange={setDisplay} colorScheme={colorScheme} /> }] : [])
  ];
  const panel = panelTabs.length ? { kind: "board", label: t("board.text.board_panel"), searchLabel: t("board.text.search_board"),
    searchPlaceholder: t("board.text.search_board_placeholder"), tabs: panelTabs } : null;

  // The 3D views' cursors under Select: the arrow, pressed or dragging too, and the pointing hand
  // over what a press would pick. Measure keeps a crosshair (Annotate's layer has its own).
  const cursor = measuring ? "cursor-crosshair"
    : overPick && !dragging ? "cursor-pointer" : "cursor-default";

  return (
    <FlatViewFrame surface={BOARD_SURFACE} containerRef={containerRef} busy={document.loading || document.updating}
      file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} loading={document.loading} loadingLabel={t("board.text.reading_board")}
      updating={document.updating} updateStatus={{ pending: true, label: t("board.text.updating_board") }} tools={index ? strip : []} toolRow={index ? row : null} views={[]}
      panel={panel} panelControl={handover.panelControl} toolStack={handover.toolStack} onToolStackChange={handover.changeToolStack} notice={view.notice}
      quickEdit={index ? handover.quickEdit : null} alert={alert} cardAlert={handover.cardAlert} alertDismissal={handover.alertDismissal}
      shown={shown} onReload={view.reload}>
      <canvas ref={canvasRef} aria-label={t("board.text.board_file", { file: view.file.name })} role="img" data-board-tool={toolMode}
        className={cn("absolute inset-0 block touch-none select-none", cursor)} />
      {/* Measure's layer, over the board and under the tools: the pointer stays the board's. */}
      <canvas ref={measureCanvasRef} className="pointer-events-none absolute inset-0 z-[1] h-full w-full" aria-hidden="true" data-scene-measure="" />
      {annotating && shown && index ? <AnnotationOverlay annotation={annotation} surface={annotationSurface} viewOf={currentView} /> : null}
    </FlatViewFrame>
  );
}

export default function BoardRenderer(props) {
  const { data, ...view } = props;
  return <BoardSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

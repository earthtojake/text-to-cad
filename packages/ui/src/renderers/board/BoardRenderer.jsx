import { useI18n } from "@text-to-cad/ui/i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { BOARD_OVERLAY_COLORS, drawBoardOverlay } from "@text-to-cad/core/lib/board2d/boardOverlay.js";
import { buildBoardRefToken, parseBoardRefSelector, splitBoardRefSelectors } from "@text-to-cad/core/lib/boardRefs.js";
import { drawAnnotationMarks } from "@text-to-cad/core/lib/drawing2d/marks.js";
import { planCamera } from "@text-to-cad/core/lib/drawing2d/planView.js";
import { screenToModel } from "@text-to-cad/core/lib/drawing2d/index.js";
import {
  boardDisplayAirwires, boardDrawView, boardMirrorX, boardPlanProjection, marksInPlan, planToSheet
} from "@text-to-cad/core/lib/plot2d/index.js";
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
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { modeGlyphIcon } from "../kit/tools/select/modeGlyphs.jsx";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { TOUCH_HIT_PX } from "../kit/viewport/dom.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { boardAnnotationDocument, boardAnnotationSurface } from "./boardAnnotation.js";
import { NetKindIcon, PadKindIcon, PartKindIcon } from "./boardIcons.jsx";
import { useBoardReferences } from "./boardReferences.jsx";
import { createBoardScene } from "./boardScene.js";
import { boardDisplayControl, readBoardDisplay } from "./BoardDisplay.jsx";
import BoardSection from "./BoardSection.jsx";
import LayersSection from "./LayersSection.jsx";
import { BOARD_NO_CAMERA, BOARD_NO_DISPLAY, BOARD_SELECT_KINDS, BOARD_TOOL, BOARD_TOOL_MODES, boardPickKinds } from "./tools.js";
import { useBoardDocument } from "./useBoardDocument.js";
import { readBoardIsolation, useBoardIsolation } from "./useBoardIsolation.js";
import { useBoardView } from "./useBoardView.js";

/**
 * A KiCad board as the picture drawn from its file, on a canvas, head on, as a drawing is: in
 * KiCad's own colours, on its board background, layer by layer (the payload comes from the
 * BACKEND, `GET /__cad/plot`; nothing here parses KiCad's files).
 *
 * It is a flat view, composed exactly as a drawing's (`../dxf/DxfRenderer.jsx`), from the same
 * kit (`kit/shell/FlatViewFrame.jsx`, `useFlatView.js`): Select — the board's hand, a drag pans,
 * the wheel or a pinch zooms, a double-click fits, a tap picks the most specific thing its filter
 * ticks under the pointer (a pad, then copper, then a part), Shift adds — Annotate, which draws on
 * the board, and Measure, between points snapped to pad, via and hole centres, track ends and
 * outline corners, in millimetres. What is picked, drawn and measured is Quick Edit's, in board
 * references (`#R1`, `#R1.2`, `#net:VBUS`), whose views are the window on screen as a plan-view
 * camera with the board's Display, which `cadgen pcb snapshot --job` draws again. Its sidebar is the
 * Board (parts and nets) and its Layers; its one view control is its Display (the modes, the pours,
 * the side), the contract `cadgen pcb snapshot --display` shares. A payload without its index
 * (an older cadgen's) is the picture alone: no tools, no Board, no Quick Edit.
 */

const SAVE_DELAY_MS = 180;
// What the frame says it draws: a board, a picture dark whatever the theme (the floating surfaces' cue).
const BOARD_SURFACE = Object.freeze({ "data-board-surface": "", "data-cad-dark-picture": "" });
// The file's slices: the board's Display and what is isolated, kept across rebuilds.
const SLICES = Object.freeze({ board: "1", isolated: "1" });

const BOARD_LIVE = Object.freeze({ commands: Object.freeze(["select", "clearSelection"]), declined: Object.freeze({}) });
const KIND_ICONS = Object.freeze({ parts: PartKindIcon, pads: PadKindIcon, nets: NetKindIcon });
const KIND_LABELS = Object.freeze({ parts: "board.text.parts", pads: "board.text.pads", nets: "board.text.nets" });
// Select's menu, one choice (`kit/tools/select/SelectFilterMenu.jsx`): All, then each kind alone.
const SELECT_MODES = [
  { id: "all", labelKey: "pick.all", kinds: BOARD_SELECT_KINDS, icon: modeGlyphIcon("all") },
  ...BOARD_SELECT_KINDS.map(id => {
    const Icon = KIND_ICONS[id];
    return { id, labelKey: KIND_LABELS[id], kinds: [id], icon: <Icon className="size-3.5" /> };
  })
];
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
/** The board's Display as a view carries it, and a snapshot job reads it. */
const viewDisplay = display => ({ mode: display.mode, side: display.side, poured: display.poured, ...(display.layers ? { layers: [...display.layers] } : {}) });

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
  const [restoredIsolation] = useState(() => readBoardIsolation(stored.renderer.isolated));
  const isolation = useBoardIsolation({ index, restored: restoredIsolation });
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
  // Select's filter: every kind ticked as a board opens, and held while it is open, across its rebuilds.
  const [filter, setFilter] = useState(BOARD_SELECT_KINDS);
  const changeFilter = useCallback(next => { setFilter(next); selectTool(BOARD_TOOL.SELECT); }, [selectTool]);
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
  const overlay = useCallback((ctx, { transform, pixelRatio, width, height }) => {
    const board = indexRef.current;
    if (!board) return;
    const base = { transform, pixelRatio, width, height, mirrorX: mirrorRef.current };
    const isolated = isolationRef.current.resolved;
    // What is isolated first, everything else stepped back; then the hover and the selection (a net
    // in focus steps the rest back).
    if (isolated.length) {
      drawBoardOverlay(ctx, board, { ...base, dim: true, selection: isolated, colors: { ...BOARD_OVERLAY_COLORS, selection: BOARD_OVERLAY_COLORS.hover } });
    }
    const { hovered, selected } = highlightRef.current;
    const net = selected.some(item => item.kind === "net");
    drawBoardOverlay(ctx, board, { ...base, hover: hovered[0] || null, selection: selected, dim: net && !isolated.length, placement: placementRef.current });
    const session = annotationRef.current;
    drawAnnotationMarks(ctx, marksInPlan(session.items, mirrorRef.current), { transform, pixelRatio, selected: session.selected, hovered: hoveredInkRef.current });
  }, []);

  // Annotate's layer: ink on the board, under the view (and its side) as it stands.
  const annotationSurface = useMemo(() => boardAnnotationSurface({
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
  const [pointing, setPointing] = useState(false);
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
      return at && board && kinds ? board.pick(at.page, { kinds, view: sideRef.current, tolerance: at.reach }) : null;
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
      setPointing(current => (current === over ? current : over));
    };
    return { tap, hover };
  }, [annotationSurface, requestPaint]);

  const boardView = useBoardView({
    plot, restored, colorScheme, onViewMoved: rememberView, drawView, overlay, onTap: handlers.tap, onHover: handlers.hover
  });
  viewRef.current = boardView;
  paintRef.current = boardView.requestPaint;
  const { canvasRef, capture, containerRef, dragging, fit, thumbnail } = boardView;
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
    return seen ? { ...seen, display: viewDisplay(displayRef.current) } : null;
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
      throw new Error(`Not on this board: ${unknown.join(", ") || list.join(", ")}. Select board references such as #U3, #U3.9, #net:VIN or #@x10y5.`);
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
  const handover = useFlatHandover({
    view, data, workspace, file, shown, ready, alert, tools, selection, references, chips, nameReference,
    capture, currentView, annotationDocument: boardAnnotationDocument, runtime, live: BOARD_LIVE,
    copySelection: index ? copySelection : null, fit, captureFailed: t("alert.captureDrawingFailed")
  });

  // ---- the frame ---------------------------------------------------------------
  // While the board loads, or once it has failed to, none of the viewer's own chrome. A compact host
  // gets the board alone; a payload without its index, the picture and its Display alone.
  const failed = Boolean(alert) && !shown;
  const compact = Boolean(view.appearance?.compact);
  const chromeHidden = document.loading || failed;
  const selectMenu = <SelectFilterMenu value={filter} onChange={changeFilter} modes={SELECT_MODES.map(mode => ({ ...mode, label: t(mode.labelKey) }))} disabled={!shown} />;
  const { strip, row } = flatViewTools(tools, { colorScheme, shown, selectMenu, t });
  const views = layered ? [boardDisplayControl({ t, display, sheet, onChange: setDisplay, disabled: !shown })] : [];
  const sidebar = layered || index ? <>
    {index ? <BoardSection index={index} selection={selection} isolated={isolation.isolated} onIsolate={isolation.toggle}
      onSelect={() => selectTool(BOARD_TOOL.SELECT)} /> : null}
    {layered ? <LayersSection sheet={sheet} display={display} onDisplayChange={setDisplay} /> : null}
  </> : null;

  // The 3D views' cursors under Select: the arrow, pressed or dragging too, and the pointing hand
  // over what a press would pick. Measure keeps its crosshair (Annotate's layer has its own).
  const cursor = measuring ? "cursor-crosshair" : pointing && !dragging ? "cursor-pointer" : "cursor-default";

  return (
    <FlatViewFrame surface={BOARD_SURFACE} containerRef={containerRef} busy={document.loading || document.updating}
      file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} loading={document.loading} loadingLabel={t("board.text.reading_board")}
      updating={document.updating} updateStatus={{ pending: true, label: t("board.text.updating_board") }} tools={index ? strip : []} toolRow={index ? row : null} views={views}
      sidebar={sidebar} toolStack={handover.toolStack} onToolStackChange={handover.changeToolStack} notice={view.notice}
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

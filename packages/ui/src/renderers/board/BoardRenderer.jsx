import { useI18n } from "@cad/ui/i18n";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BOARD_THICKNESS_MM, headOnCamera, leavingView, sideSeenAlong } from "@cad/core/lib/board3d/boardFrame.js";
import { cn } from "@cad/ui/utils";
import { boardOverlayColors, drawBoardOverlay } from "@cad/core/lib/board2d/boardOverlay.js";
import { buildBoardRefToken, formatBoardRefSelector, parseBoardRefSelector, splitBoardRefSelectors } from "@cad/core/lib/boardRefs.js";
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
import { exitIsolateEntry, menuEntry, menuGroups, pickGroup, referenceGroup, zoomGroup } from "../kit/shell/viewMenu.js";
import AnnotationOverlay from "../kit/tools/annotate/AnnotationOverlay.jsx";
import { measureSelectHandlers } from "../kit/tools/measure/measureSelection.js";
import { useMeasureOverlay } from "../kit/tools/measure/useMeasureOverlay.js";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import { groupChips } from "../kit/tools/select/groupChips.js";
import { TOUCH_HIT_PX } from "../kit/viewport/dom.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { plotAnnotationDocument, plotAnnotationSurface } from "../kit/tools/annotate/plotAnnotation.js";
import { useBoardDescribe, useBoardInspect, useBoardReferences, useBoardTip } from "./boardReferences.jsx";
import { createBoardScene } from "./boardScene.js";
import { BOARD_DIMENSION_SHORTCUT, BOARD_FLIP_SHORTCUT, boardViewControls, readBoardDisplay } from "./BoardDisplay.jsx";
import { shortcutOfEvent } from "../kit/tools/toolShortcuts.js";
import BoardSection, { useBoardTrees } from "./BoardSection.jsx";
import BoardSelectFilter from "./BoardSelectFilter.jsx";
import LayersSection from "./LayersSection.jsx";
import {
  BOARD_DEFAULT_FILTER, BOARD_NO_CAMERA, BOARD_NO_DISPLAY, BOARD_TOOL, BOARD_TOOL_MODES, boardPickKinds, boardWorkingLayer, readBoardFilter
} from "./tools.js";
import { useBoardDocument } from "./useBoardDocument.js";
import { readIsolation, useIsolation } from "../kit/tools/select/useIsolation.js";
import { viewportZoom } from "../kit/shell/ZoomControl.jsx";
import { useBoardView } from "./useBoardView.js";
import { board3dAnnotationSurface } from "./board3dAnnotation.js";
import { useBoardModels } from "./useBoardModels.js";

// The board in 3D, its own chunk: a board shown in 2D loads no three.js.
const Board3dView = lazy(() => import("./Board3dView.jsx"));

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
 * views' drags (a right or middle drag, or a drag with Ctrl, Cmd or Shift, pans, as a trackpad's
 * two-finger scroll does; a mouse's wheel or a pinch zooms), a double-click fits, a right-click opens
 * the view's menu (every view's, `kit/shell/viewMenu.js`: the reference, Select, Isolate and the
 * copper's net, and the framing) — Annotate, which
 * draws on the board, and Measure, between points snapped to pad, via and hole centres, track ends
 * and outline corners, in millimetres. What is picked, drawn and measured is Quick Edit's, in board
 * references (`#R1`, `#R1.2`, `#net:VBUS`, `#track:<uuid>`, `#F.Cu@x10y5..x20y15`), whose views are the window on screen as a plan-view camera with the
 * board's Display, which `cad <type> snapshot --job` draws again, the references lit. Its panel
 * (`kit/shell/FlatPanel.jsx`) is a search over three tabs, the Parts (in their schematic blocks), the
 * Nets and the Layers (each layer's eye, a row's press for the active layer), and under them the
 * picked part's or net's pads (`BoardSection.jsx`'s detail); its view
 * controls are the view's corner's (`kit/shell/ViewCorner.jsx`), in its column over the zoom pill
 * (`BoardDisplay.jsx`): Display (the preset), 2D/3D and Flip (the side, top or bottom; ⇧F), each of the
 * two a button whose icon is the state on screen; the Layers tab has the
 * layers, the other layers, the pours and the opacities: one contract with `cad <type> snapshot --display`. A payload without its
 * index (an older server's) is the picture alone: no tools, no Parts or Nets, no Quick Edit.
 *
 * The same view, drawn in 3D (2D/3D, or the key 3): the board as a slab with its two faces, each the
 * 2D drawer's picture of that side (`Board3dView.jsx`, a lazy chunk, over `@cad/core/lib/board3d/`). It
 * is the view's other canvas, in the same frame: the strip, the panel, the selection, the ink, the
 * measurements, Quick Edit and the corner are the same mounted components either way. The corner's
 * pill zooms the 3D camera (the 3D views' zoom, `viewportZoom`), and Display's menu ends with the
 * camera's projection; there is no cube and no Home button (Zoom to fit frames the board). A press
 * picks what the 2D view picks where the pointer's ray meets the face it enters; a drag turns the view
 * (naming an area by a drag is the 2D view's); Flip turns the camera over, and its icon follows the camera to
 * whichever side of the board it is on, turned by hand too.
 * Entering 3D opens head on, on the window the 2D view shows (the flat canvas on screen until the board in
 * 3D has drawn that same picture), and eases, on the side the 2D view showed, to the 3D views' Home tilt,
 * the board framed whole (from the bottom, Home turned over as Flip turns it), or to the camera this file
 * was left at in 3D, turned over to that side if it looks at the other: the ease never crosses the board's
 * plane, so Flip's icon stays the side it was. Leaving it with the camera where that
 * left it gives the 2D view back as it was; once the camera has been moved (a Flip moves it), or when the 3D
 * view opened on the camera a file was left at in 3D (a reload in 3D, with no 2D picture under it), leaving
 * frames the 2D view on what the camera was centred on, at its scale, from its side, the side Flip's icon
 * showed (the board in 3D up until the flat canvas has painted it). Which of the two is up, and the 3D camera
 * and projection, are the file's view (`board3d`).
 */

const SAVE_DELAY_MS = 180;
// What the frame says it draws: a board, on its theme's canvas.
const BOARD_SURFACE = Object.freeze({ "data-board-surface": "" });
// The file's slices: the board's Display, what is isolated, and the board in 3D (which is up, its camera, its projection), kept across rebuilds.
const SLICES = Object.freeze({ board: "1", isolated: "1", board3d: "1" });
/** The board in 3D as the file's view keeps it: 2D or 3D, the 3D camera (null: Home), the projection, whether its parts' 3D models show. */
function readBoard3d(raw) {
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  return { mode: value.mode === "3d" ? "3d" : "2d", camera: value.camera && typeof value.camera === "object" ? value.camera : null,
    projection: value.projection === "perspective" ? "perspective" : "orthographic", models: value.models !== false };
}
const point3 = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
/** The side of the board a stored 3D camera sees (`boardFrame.js`'s `sideSeenAlong`), or null for none. */
const cameraSide = camera => (point3(camera?.position) && point3(camera?.target)
  ? sideSeenAlong(camera.target.map((value, axis) => value - camera.position[axis])) : null);

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
  // How thick the board is (its file's stack-up; KiCad's default where it names none), and its parts' 3D models table.
  const thickness = plot?.board?.thickness > 0 ? plot.board.thickness : BOARD_THICKNESS_MM;
  const thicknessRef = useRef(thickness);
  thicknessRef.current = thickness;
  const models = useBoardModels({ client: workspace.client, file, revision: workspace.resource.revision, enabled: Boolean(index) });

  // ---- the file's view: the transform, the board's Display, what is isolated ----
  const [stored] = useState(() => readFileView(view.state, SLICES));
  const [restored] = useState(() => readTransform(stored.camera));
  // 2D or 3D, the 3D camera and its projection: the file's, as it was left.
  const [restored3d] = useState(() => readBoard3d(stored.renderer.board3d));
  // In 3D the side shown is the side the camera is on (Flip's icon follows it): a file left in 3D opens on its
  // camera, so on that camera's side, whatever its Display last said.
  const [display, setDisplay] = useState(() => {
    const board = readBoardDisplay(stored.renderer.board);
    const side = restored3d.mode === "3d" ? cameraSide(restored3d.camera) : null;
    return side && side !== board.side ? { ...board, side } : board;
  });
  const canonicalPick = useCallback(id => index?.resolve(id)?.selector, [index]);
  const [restoredIsolation] = useState(() => readIsolation(stored.renderer.isolated?.selectors));
  const isolation = useIsolation({ index, restored: restoredIsolation, canonical: canonicalPick });
  const [dimension, setDimension] = useState(restored3d.mode);
  const [projection, setProjection] = useState(restored3d.projection);
  const [showModels, setShowModels] = useState(restored3d.models);
  const saved = useRef({ camera: restored, display, isolated: restoredIsolation, board3d: restored3d });
  const storedRef = useRef("");
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(view.onStateChange);
  stateChangeRef.current = view.onStateChange;
  const recordOf = ({ camera, display: board, isolated, board3d }) => writeFileView({ camera,
    renderer: { board, isolated: { selectors: [...isolated] }, board3d }, signatures: SLICES });
  const save = useCallback(change => {
    saved.current = { ...saved.current, ...change };
    const record = recordOf(saved.current);
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  // A view that is still the fit stores no camera: `null` is "fit me".
  const rememberView = useCallback(transform => save({ camera: transform ? { ...transform } : null }), [save]);
  const remember3d = useCallback(change => save({ board3d: { ...saved.current.board3d, ...change } }), [save]);
  useEffect(() => { storedRef.current = JSON.stringify(recordOf({ camera: restored, display, isolated: restoredIsolation, board3d: restored3d })); }, []);
  useEffect(() => { save({ display, isolated: isolation.isolated }); }, [display, isolation.isolated, save]);
  useEffect(() => { remember3d({ mode: dimension, projection, models: showModels }); }, [dimension, projection, showModels, remember3d]);
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
  // The board in 3D, while it is up: its handle (`Board3dView.jsx`) and its viewport's (`ShellViewport.jsx`).
  const view3dRef = useRef(null);
  const viewer3dRef = useRef(null);
  const dimensionRef = useRef(dimension);
  dimensionRef.current = dimension;
  const in3d = () => (dimensionRef.current === "3d" ? view3dRef.current : null);
  // In 3D a press may take what a layer drawn on the face it meets holds: that side's layers.
  const sideLayers = useMemo(() => (sheet ? { top: new Set(boardDrawView({ ...display, side: "top" }, sheet).layers),
    bottom: new Set(boardDrawView({ ...display, side: "bottom" }, sheet).layers) } : null), [display, sheet]);
  const sideLayersRef = useRef(sideLayers);
  sideLayersRef.current = sideLayers;

  // What is lit (resolved references) and the ink under the pointer: painted over the board, never React state.
  const highlightRef = useRef(NO_SELECTION);
  const hoveredInkRef = useRef([]);
  const paintRef = useRef(() => {});
  const requestPaint = useCallback(() => paintRef.current(), []);
  const scene = useMemo(() => (index ? createBoardScene(index, { t, onHighlight: ink => { highlightRef.current = ink; } }) : null), [index, t]);
  const selection = useSceneSelection({ scene, requestRender: requestPaint });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const describe = useBoardDescribe(index, models);
  const { references, chips: pickChips } = useBoardReferences({ scene, selection, resource: workspace.resource, describe });
  // A block picked whole (its row menu's Select all parts) is one chip, not a chip a part.
  const trees = useBoardTrees(index, models);
  const chips = useMemo(() => groupChips({ selected: selection.selected, chips: pickChips, resource: workspace.resource, select: selection.select,
    groups: [...(trees?.parts.nodesById.values() || [])].filter(node => node.picks?.length > 1).sort((a, b) => b.picks.length - a.picks.length)
      .map(node => ({ id: node.id, label: node.label, picks: node.picks })),
    label: group => t("chip.blockParts", { name: group.label, count: group.picks.length }) }), [selection.selected, selection.select, pickChips, workspace.resource, trees, t]);
  // The overlay's colours are the theme's (`board2d/boardOverlay.js`): a highlight that reads on the canvas under it.
  const schemeRef = useRef(colorScheme);
  schemeRef.current = colorScheme;
  // The same overlay on a face of the board in 3D (`Board3dView.jsx`): `frame.mirrorX` is that face's, and
  // what it answers says whether there was anything to draw (nothing: the face's overlay is put away).
  const overlay = useCallback((ctx, { transform, pixelRatio, width, height, ...frame }) => {
    const board = indexRef.current;
    const session = annotationRef.current;
    const isolated = isolationRef.current.resolved;
    const { hovered, selected } = highlightRef.current;
    if (!board) return false;
    const face = "mirrorX" in frame;
    if (face && !isolated.length && !hovered.length && !selected.length && !placementRef.current && !session.items.length) return false;
    const mirrorX = face ? frame.mirrorX : mirrorRef.current;
    const colors = boardOverlayColors(schemeRef.current);
    const base = { transform, pixelRatio, width, height, mirrorX, colors };
    // What is isolated first, everything else stepped back; then the hover and the selection (a net
    // in focus steps the rest back).
    if (isolated.length) {
      drawBoardOverlay(ctx, board, { ...base, dim: true, selection: isolated, colors: { ...colors, selection: colors.hover } });
    }
    const net = selected.some(item => item.kind === "net");
    drawBoardOverlay(ctx, board, { ...base, hover: hovered[0] || null, selection: selected, dim: net && !isolated.length, placement: placementRef.current,
      draft: face ? null : draftRef.current });
    // The ink over the board, in 2D and on a face in 3D alike: edged, so red ink reads on red copper.
    drawAnnotationMarks(ctx, marksInPlan(session.items, mirrorX), { transform, pixelRatio, selected: session.selected, hovered: hoveredInkRef.current,
      keyline: colors.inkKeyline });
    return true;
  }, []);

  // The parts' bodies in 3D, lit and faded as the faces' overlay lights the copper: the parts hovered and
  // selected, and while something is isolated, the parts that stay bright (an isolated part, a pad's
  // part, a part with a pad on an isolated net).
  const bodyInk = useCallback(() => {
    const { hovered, selected } = highlightRef.current;
    const refs = list => list.filter(item => item?.kind === "part").map(item => item.part.ref);
    const isolated = isolationRef.current.resolved;
    if (!isolated.length) return { hovered: refs(hovered), selected: refs(selected), bright: null };
    const bright = new Set();
    for (const item of isolated) {
      if (item?.kind === "part") bright.add(item.part.ref);
      else if (item?.kind === "pad") bright.add(item.pad.ref);
      for (const pad of item?.net?.pads || []) bright.add(pad.ref);
    }
    return { hovered: refs(hovered), selected: refs(selected), bright: [...bright] };
  }, []);

  // Annotate's layer: ink on the board, under the view (and its side) as it stands; in 3D, on the face
  // the camera sees (`board3dAnnotation.js`). The marks are sheet millimetres either way.
  const flatSurface = useMemo(() => plotAnnotationSurface({
    transform: () => viewRef.current?.transformRef.current || null,
    mirrorX: () => mirrorRef.current,
    canvas: () => viewRef.current?.canvasRef.current || null
  }), []);
  const surface3d = useMemo(() => board3dAnnotationSurface({
    ray: point => view3dRef.current?.ray(point) || null,
    project: world => view3dRef.current?.project(world) || null,
    side: () => view3dRef.current?.side() || "top",
    thickness: () => view3dRef.current?.thickness() ?? thicknessRef.current,
    canvas: () => view3dRef.current?.canvas() || null
  }), []);
  const annotationSurface = dimension === "3d" ? surface3d : flatSurface;
  const annotationSurfaceRef = useRef(annotationSurface);
  annotationSurfaceRef.current = annotationSurface;
  // The view as Measure's and Select's kit code reads a scene's: its camera (the sheet to the screen
  // as matrices, through the mirror from below; in 3D through the camera, onto the face it sees) and
  // the element its pointer events arrive on.
  const measureRuntimeRef = useRef(null);
  if (!measureRuntimeRef.current) {
    measureRuntimeRef.current = {
      get camera() {
        const solid = in3d();
        if (solid) return solid.measureCamera();
        const current = viewRef.current, size = current?.sizeRef.current;
        return current && size ? boardPlanProjection(current.transformRef.current, size.width, size.height, mirrorRef.current) : null;
      },
      renderer: { get domElement() { return in3d()?.canvas() || viewRef.current?.canvasRef.current || null; } }
    };
  }
  // The canvas the view's menu opens over: the one on screen.
  const activeCanvasRef = useMemo(() => ({ get current() { return in3d()?.canvas() || viewRef.current?.canvasRef.current || null; } }), []);

  // What a press under Select would pick, which the frame names in its hover tip (`describeBoardPick`'s
  // name, and a pad's net or a part's value).
  const [hovered, setHovered] = useState("");
  // ---- pointer: what a tap and a resting pointer do under each tool -----------
  const [overPick, setOverPick] = useState(false);
  const measureHoverRef = useRef(null);
  const measureAnchorRef = useRef(null);
  useEffect(() => { if (!measuring) { measureHoverRef.current = null; measureAnchorRef.current = null; } }, [measuring]);
  useEffect(() => { if (!measure.state?.draft?.anchor) measureAnchorRef.current = null; }, [measure.state]);
  const handlers = useMemo(() => {
    // The sheet point under a pane point, and how far a pick there reaches, in millimetres; in 3D, where
    // its ray meets the face it enters, and that face's side and layers.
    const atPoint = (point, pointerType) => {
      const solid = in3d();
      if (dimensionRef.current === "3d") {
        const at = solid?.atPoint(point, pickPx(pointerType));
        return at ? { ...at, layers: sideLayersRef.current?.[at.side] || drawnRef.current } : null;
      }
      const transform = viewRef.current?.transformRef.current;
      return transform ? { page: planToSheet(screenToModel(transform, point.x, point.y), mirrorRef.current), reach: pickPx(pointerType) / transform.scale,
        side: sideRef.current, layers: drawnRef.current } : null;
    };
    // Measure's end: a pad, via or hole centre, a track end or an outline corner near the pointer, else the point itself.
    const snapPick = (point, pointerType) => {
      const at = atPoint(point, pointerType), board = indexRef.current;
      if (!at || !board) return null;
      const snap = board.snap(at.page, { tolerance: at.reach });
      const [x, y] = snap ? snap.point : at.page;
      return { point: [x, y, 0], snapKind: snap ? snap.kind : "free", units: { unit: "mm", perWorld: 1 } };
    };
    // A part, picked by its body in 3D, as the filter takes it: with Footprints ticked, a locked one with Locked items.
    const pickPart = ref => {
      const board = indexRef.current, kinds = boardPickKinds(filterRef.current), part = board?.parts.get(ref);
      return part && kinds?.parts && (!part.locked || kinds.locked) ? { kind: "part", part, selector: formatBoardRefSelector({ kind: "part", ref }) } : null;
    };
    const pickAt = (point, pointerType) => {
      // In 3D a part's body in front of the face is what a press there takes, front to back.
      const body = dimensionRef.current === "3d" ? in3d()?.bodyAt(point) : null;
      const part = body ? pickPart(body.ref) : null;
      if (part) return part;
      const at = atPoint(point, pointerType), board = indexRef.current, kinds = boardPickKinds(filterRef.current);
      return at && board && kinds ? board.pick(at.page, { kinds, view: at.side, tolerance: at.reach, layers: at.layers }) : null;
    };
    const inkUnder = (point, pointerType) => (annotationRef.current.items.length
      ? annotationAt(point, annotationSurfaceRef.current.onScreen(annotationRef.current.items), pickPx(pointerType))[0]?.id || null : null);
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
      setHovered(hit && point ? hit.selector : "");
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
    // What the board in 3D picks where a ray meets it (`boardStage.js`'s `pick`: a double-click's, the kit's tap-or-drag's).
    const pickLocated = located => {
      const board = indexRef.current, kinds = boardPickKinds(filterRef.current);
      return board && kinds ? board.pick(located.page, { kinds, view: located.side, tolerance: 0.1, layers: sideLayersRef.current?.[located.side] }) : null;
    };
    return { tap, hover, drag, pickAt, pickLocated, pickPart };
  }, [requestPaint]);

  // The flat canvas lets go of its rasters while the board is up in 3D (it is covered); it keeps its view.
  // `shown3d`: the board in 3D is on screen in its place; `closing3d`: leaving 3D, the board in 3D stays
  // over the flat canvas until the flat canvas has painted the window it hands over.
  const [shown3d, setShown3d] = useState(false);
  const [closing3d, setClosing3d] = useState(false);
  const boardView = useBoardView({
    plot, restored, colorScheme, onViewMoved: rememberView, drawView, overlay, onTap: handlers.tap, onHover: handlers.hover, onDrag: handlers.drag,
    paused: dimension === "3d" && shown3d
  });
  viewRef.current = boardView;
  paintRef.current = dimension === "3d" ? () => view3dRef.current?.requestPaint() : boardView.requestPaint;
  const { canvasRef, containerRef, dragging, thumbnail } = boardView;
  // The view on screen fits, frames and captures: the flat canvas, or the board in 3D.
  const fit = useCallback(() => (dimensionRef.current === "3d" ? view3dRef.current?.fit() : viewRef.current?.fit()), []);
  const capture = useCallback(() => (dimensionRef.current === "3d" && view3dRef.current ? view3dRef.current.capture() : viewRef.current.capture()), []);
  // A row of the Parts, the Nets or the detail double-clicked: what it picked, framed, from the side looked at (a page box to the
  // plan's model space; in 3D, the camera's direction kept).
  const frameSelectors = useCallback(selectors => {
    const board = indexRef.current;
    if (!board) return;
    const boxes = selectors.map(id => board.extent(board.resolve(id))).filter(Boolean);
    if (!boxes.length) return;
    let [x0, y0, x1, y1] = [Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])), Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3]))];
    if (dimensionRef.current === "3d") { view3dRef.current?.frameSheet([x0, y0, x1, y1]); return; }
    const mirror = mirrorRef.current;
    if (mirror != null) [x0, x1] = [2 * mirror - x1, 2 * mirror - x0];
    viewRef.current?.frame([x0, -y1, x1, -y0]);
  }, []);

  // ---- 2D/3D: one view, its other canvas -------------------------------------------------
  // Entering 3D opens head on, on the window the 2D view shows, from its side, then eases to the camera
  // this file was left at in 3D, or to Home's tilt, on that same side (a camera on the other side turned
  // over to it); a file left in 3D opens on its camera. The flat canvas stays on screen until the board in
  // 3D has drawn that same picture (`Board3dView.jsx`'s `onShown`).
  const mirrorFor = useCallback(side => boardMirrorX(sheetRef.current, side), []);
  const sheetRef = useRef(sheet);
  sheetRef.current = sheet;
  // `flat`: it opens on the flat canvas's own picture, which stays on screen until the board in 3D has drawn it;
  // `side`: the side the 2D view showed, which the opening's ease ends on.
  const [opening, setOpening] = useState(() => ({ camera: restored3d.camera, then: null, home: false, side: display.side, flat: false }));
  const openingRef = useRef(opening);
  openingRef.current = opening;
  // The side the 2D view showed as 3D was entered, and the window leaving 3D hands the 2D view (none: its own).
  const enteredRef = useRef(null);
  const leavingRef = useRef(null);
  const switchDimension = useCallback(next => {
    if (next === dimensionRef.current) return;
    if (next === "3d") {
      const flat = viewRef.current, size = flat?.sizeRef.current, board = sheetRef.current, side = displayRef.current.side;
      const span = board ? Math.max(board.width, board.height) : 100;
      const headOn = size ? headOnCamera({ transform: flat.transformRef.current, width: size.width, height: size.height, side,
        mirrorX: mirrorFor(side), thickness: thicknessRef.current, distance: 2 * span }) : null;
      const left = saved.current.board3d.camera;
      enteredRef.current = { side };
      setOpening({ camera: headOn, then: left, home: !left, side, flat: Boolean(headOn) });
      setClosing3d(false);
    } else {
      // Leaving a 3D view that opened on the 2D picture, its camera moved by nobody since (the opening's ease is
      // not a move), gives the 2D view back as it was, from the side it showed; else the 2D view is framed on
      // what the camera centres, at its scale, from its side: a camera moved, or the one a file left in 3D
      // reopened on, which no 2D picture was under (`boardFrame.js`'s `leavingView`).
      const solid3d = view3dRef.current;
      const leaving = leavingView({ flat: Boolean(openingRef.current.flat), moved: Boolean(solid3d?.moved()), side: enteredRef.current?.side ?? null,
        plan: () => solid3d?.plan(mirrorFor) ?? null });
      leavingRef.current = leaving.transform;
      if (leaving.side && leaving.side !== displayRef.current.side) setDisplay(current => ({ ...current, side: leaving.side }));
      setClosing3d(true);
    }
    dimensionRef.current = next;
    setDimension(next);
  }, [mirrorFor]);
  // Left: the flat canvas painted at the window it is handed, under the board in 3D, which then goes.
  useEffect(() => {
    if (dimension !== "2d" || !closing3d) return;
    if (leavingRef.current) viewRef.current?.setView(leavingRef.current);
    leavingRef.current = null;
    viewRef.current?.settle();
    setShown3d(false);
    setClosing3d(false);
  }, [dimension, closing3d]);
  // Flip: the Display's side in 2D; in 3D the camera turns over to it, and the side follows the camera.
  const chooseSide = useCallback(side => (dimensionRef.current === "3d" && view3dRef.current ? view3dRef.current.turnTo(side)
    : setDisplay(current => ({ ...current, side }))), []);
  // The 3D camera, kept with the file's view; the side it sees is the Display's side (Flip's icon follows it).
  // Only while 3D is the view: leaving, the board in 3D is still up for a frame, and what its camera does then
  // (an ease cut short, its viewport taken down) is nobody's.
  const onCamera3d = useCallback((camera, side) => {
    if (dimensionRef.current !== "3d") return;
    remember3d({ camera });
    if (side !== displayRef.current.side) setDisplay(current => ({ ...current, side }));
  }, [remember3d]);
  // Ink put down, picked or let go, a side or an isolation changed: the same view, painted again.
  useEffect(() => { requestPaint(); }, [annotation.items, annotation.selected, display, isolation.resolved, requestPaint]);
  // A tool put down lets go of what it lit under the pointer.
  useEffect(() => { handlers.hover(null, null); }, [toolMode, handlers]);

  // The view on screen as a prompt carries it: the plan view's camera, the pane's shape, and the
  // board's Display, so a snapshot draws the layers, the pours and the side the person saw.
  const displayRef = useRef(display);
  displayRef.current = display;
  // In 3D, the window on the board the camera shows, as a plan-view camera from the side it sees.
  const currentView = useCallback(() => {
    const current = viewRef.current, size = current?.sizeRef.current;
    const plan = dimensionRef.current === "3d" ? view3dRef.current?.plan(mirrorFor) || null : null;
    const transform = plan ? plan.transform : current?.transformRef.current;
    const camera = transform && size ? planCamera(transform, size.width, size.height) : null;
    const seen = camera ? promptView({ camera, width: size.width, height: size.height }) : null;
    // The view as it was seen: its Display and the theme it was drawn in (a snapshot's `appearance`).
    const shownDisplay = plan ? { ...displayRef.current, side: plan.side } : displayRef.current;
    return seen ? { ...seen, display: { ...viewDisplay(shownDisplay), appearance: schemeRef.current } } : null;
  }, [mirrorFor]);

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
      loading: document.loading || document.updating, selection: references, camera: in3d()?.camera() ?? null, display: {},
      boardDisplay: viewDisplay(displayRef.current)
    }),
    // A camera to pose is the board's in 3D, as every 3D view's; drawn flat, it has none.
    setCamera(camera) {
      const solid = in3d();
      if (!solid) throw new Error(BOARD_NO_CAMERA);
      solid.setCamera(camera);
    },
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
    copySelection: index ? copySelection : null, fit, captureFailed: t("alert.captureDrawingFailed"), packetReferences: boardPacketReferences,
    // 3, as KiCad's Alt+3 opens its 3D viewer: the board in 3D, and back. ⇧F, Flip's: the board seen from
    // its other side (in 3D the camera turned over), as the corner's button does.
    onViewKey: event => {
      if (!layered) return false;
      if (event.key === BOARD_DIMENSION_SHORTCUT && !event.shiftKey) {
        switchDimension(dimensionRef.current === "3d" ? "2d" : "3d");
        return true;
      }
      if (shortcutOfEvent(event) !== BOARD_FLIP_SHORTCUT) return false;
      chooseSide(displayRef.current.side === "bottom" ? "top" : "bottom");
      return true;
    }
  });

  // ---- the menu: a secondary tap on the board, under Select (`kit/shell/viewMenu.js`'s groups) ----
  // Over something Select would pick: its reference (with what is picked already), Select or
  // Deselect, Isolate for a part or a net and its net for copper, then the framing. Over bare board:
  // Exit isolate and the framing (the side is Display's View from).
  const contextMenuItems = index && toolMode === BOARD_TOOL.SELECT ? press => {
    const canvas = activeCanvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const hit = handlers.pickAt({ x: press.clientX - rect.left, y: press.clientY - rect.top }, "mouse");
    const now = selectionRef.current, isolated = isolation.isolated;
    const zoom = zoomGroup({ t, onZoomFit: fit, onZoomSelection: () => frameSelectors(selectionRef.current.selected), selectionAvailable: now.selected.length > 0 });
    if (!hit) {
      return menuGroups([exitIsolateEntry({ isolatedCount: isolated.length, onExitIsolates: isolation.clear, t })], zoom);
    }
    const id = hit.selector, selected = now.selected.includes(id);
    const copyText = path ? buildBoardRefToken({ path, selectors: [...new Set([...now.selected, id])] }) : "";
    const ownNet = hit.kind === "net" ? "" : String(hit.pad?.net || hit.item?.net || hit.net?.name || "");
    const netId = ownNet ? formatBoardRefSelector({ kind: "net", net: ownNet }) : "";
    const isolatable = hit.kind === "part" || hit.kind === "net";
    return menuGroups(
      referenceGroup({ copyText, onCopy: () => { void Promise.resolve(host.clipboard.writeText(copyText)).catch(() => {}); }, t }),
      pickGroup({ selected, onSelect: () => now.select(id, { multiSelect: selected }), t,
        isolated: isolatable ? isolated.includes(id) : null, onIsolate: () => isolation.toggle(id), isolatedCount: isolated.length, onExitIsolates: isolation.clear }),
      netId ? [menuEntry("isolate-net", isolated.includes(netId) ? t("tree.exitIsolateNamed", { name: ownNet }) : t("tree.isolateNamed", { name: ownNet }),
        { onSelect: () => isolation.toggle(netId) })] : [],
      zoom);
  } : null;

  // ---- the frame ---------------------------------------------------------------
  // While the board loads, or once it has failed to, none of the viewer's own chrome. A compact host
  // gets the board alone; a payload without its index, the picture and its Display alone.
  const failed = Boolean(alert) && !shown;
  const compact = Boolean(view.appearance?.compact);
  const chromeHidden = document.loading || failed;
  const selectMenu = <BoardSelectFilter value={filter} onChange={changeFilter} disabled={!shown} />;
  const { strip, row } = flatViewTools(tools, { colorScheme, shown, selectMenu, t });
  // The panel (`kit/shell/FlatPanel.jsx`): the Parts, the Nets, then the Layers with the board's view
  // settings; under them, what is picked in detail.
  // A list row's Copy Reference: what it names, with what is selected, as one reference into the file.
  const copyReferences = ids => { void Promise.resolve(host.clipboard.writeText(buildBoardRefToken({ path, selectors: ids }))).catch(() => {}); };
  const takeSelect = useCallback(() => selectTool(BOARD_TOOL.SELECT), [selectTool]);
  const list = id => <BoardSection index={index} trees={trees} list={id} selection={selection} isolated={isolation.isolated}
    onIsolate={isolation.toggle} onCopyReference={path ? copyReferences : null} onFrame={frameSelectors} onSelect={takeSelect} />;
  const copySelectors = useCallback(ids => (path ? buildBoardRefToken({ path, selectors: ids }) : ""), [path]);
  const tip = useBoardTip(index);
  // How many parts the 3D view stands a model on (the Layers tab's 3D models row's count): every part with one shown, found.
  const modelCount = useMemo(() => (index && models ? [...index.parts.values()].filter(part => part.models.some(model => !model.hidden && models[model.name]?.document)).length : 0),
    [index, models]);
  const inspect = useBoardInspect({ index, describe, tip, selection, hovered, onSelect: takeSelect, frame: frameSelectors, copyText: copySelectors });
  const panelTabs = [
    ...(index ? [{ id: "parts", label: t("board.text.parts"), searchLast: true, content: list("parts") },
      { id: "nets", label: t("board.text.nets"), searchLast: true, content: list("nets") }] : []),
    ...(layered ? [{ id: "layers", label: t("layers.title"), content: <LayersSection sheet={sheet} display={display} onDisplayChange={setDisplay} colorScheme={colorScheme}
      models={index ? { shown: showModels, onChange: setShowModels, count: modelCount } : null} /> }] : [])
  ];
  const panel = panelTabs.length ? { kind: "board", label: t("board.text.board_panel"), searchLabel: t("board.text.search_board"),
    tabs: panelTabs } : null;

  // The 3D views' cursors under Select: the arrow, pressed or dragging too, and the pointing hand
  // over what a press would pick. Measure keeps a crosshair (Annotate's layer has its own).
  const cursor = measuring ? "cursor-crosshair"
    : overPick && !dragging ? "cursor-pointer" : "cursor-default";

  // The corner's pill, and the zoom's keys (`useFlatHandover`'s `zoomKeys`): the flat canvas's, or in 3D the
  // 3D views' own, made again once the 3D view is up, so the pill hears its camera from then on.
  const zoom3d = useMemo(() => viewportZoom(viewer3dRef), [shown3d]);
  const zoom = { ...(dimension === "3d" ? zoom3d : boardView.zoom), zoomToSelection: () => frameSelectors(selectionRef.current.selected),
    selectionAvailable: selection.selected.length > 0 };
  handover.zoomKeys.current = zoom;
  const solid = dimension === "3d" && layered && plot;
  // The board in 3D is mounted while it is the view, and while it leaves (`closing3d`).
  const mounted3d = (dimension === "3d" || closing3d) && layered && plot;
  // In 3D, Display's menu ends with the camera's projection, a setting changed seldom (`settings-ui.md`).
  const views = layered ? boardViewControls({ t, display, sheet, onChange: setDisplay, disabled: !shown, dimension, onDimensionChange: switchDimension,
    onSide: chooseSide, projection: solid ? { value: projection, onChange: setProjection } : null }) : [];
  // The parts the 3D view stands models on: the index's (page millimetres, as the stage's outline is), each with its models.
  const boardParts = useMemo(() => (index ? [...index.parts.values()] : null), [index]);
  return (
    <FlatViewFrame surface={BOARD_SURFACE} containerRef={containerRef} busy={document.loading || document.updating}
      file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} loading={document.loading} loadingLabel={t("board.text.reading_board")}
      updating={document.updating} updateStatus={{ pending: true, label: t("board.text.updating_board") }} tools={index ? strip : []} toolRow={index ? row : null} views={views}
      panel={panel} panelControl={handover.panelControl} toolStack={handover.toolStack} onToolStackChange={handover.changeToolStack} notice={view.notice}
      quickEdit={index ? handover.quickEdit : null} alert={alert} cardAlert={handover.cardAlert} alertDismissal={handover.alertDismissal}
      shown={shown} onReload={view.reload} canvasRef={activeCanvasRef} contextMenuItems={contextMenuItems}
      zoom={zoom} inspect={inspect}>
      {/* In 3D the flat canvas takes no pointer: until the board in 3D is up it shows the picture that opens it. */}
      <canvas ref={canvasRef} aria-label={t("board.text.board_file", { file: view.file.name })} role="img" data-board-tool={toolMode}
        className={cn("absolute inset-0 block touch-none select-none", cursor, solid && "pointer-events-none", solid && shown3d && "invisible")} />
      {/* The board in 3D, unseen over the flat canvas until it has drawn the same picture, which then lets its rasters
          go; leaving, over it until it has painted the window it is handed. */}
      {mounted3d ? <Suspense fallback={null}>
        <Board3dView handle={view3dRef} viewerRef={viewer3dRef} modelKey={`${file}#3d`} layout={plot.layout} outline={plot.board?.outline ?? null}
          thickness={thickness} parts={boardParts} models={models} client={workspace.client} showModels={showModels} bodyInk={bodyInk} pickPart={handlers.pickPart}
          display={display} colorScheme={colorScheme} opening={opening} projection={projection} pickAt={handlers.pickLocated}
          onTap={handlers.tap} onHover={handlers.hover} picking={Boolean(index) && !annotating} shown={shown3d || !opening.flat}
          overlay={overlay} onCamera={onCamera3d} onShown={() => { if (dimensionRef.current === "3d") setShown3d(true); }} />
      </Suspense> : null}
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

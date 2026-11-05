import { useI18n } from "@cad/ui/i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@cad/ui/utils";
import { drawAnnotationMarks } from "@cad/core/lib/drawing2d/marks.js";
import { planCamera } from "@cad/core/lib/drawing2d/planView.js";
import { screenToModel } from "@cad/core/lib/drawing2d/index.js";
import { boardPlanProjection, planToSheet } from "@cad/core/lib/plot2d/index.js";
import { drawSchematicOverlay } from "@cad/core/lib/schematic2d/schematicOverlay.js";
import { buildSchematicRefToken, canonicalSheetPath, parseSchematicRefSelector, splitSchematicRefSelectors } from "@cad/core/lib/schematicRefs.js";
import { useViewerHost } from "../../host/context.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import { annotationAt, withGroups } from "../../annotation/geometry.js";
import { promptView } from "../../annotation/views.js";
import FlatViewFrame, { flatViewTools } from "../kit/shell/FlatViewFrame.jsx";
import { useFlatHandover, useFlatTools } from "../kit/shell/useFlatView.js";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import { exitIsolateEntry, menuEntry, menuGroups, pickGroup, referenceGroup, zoomGroup } from "../kit/shell/viewMenu.js";
import AnnotationOverlay from "../kit/tools/annotate/AnnotationOverlay.jsx";
import { plotAnnotationDocument, plotAnnotationSurface } from "../kit/tools/annotate/plotAnnotation.js";
import { measureSelectHandlers } from "../kit/tools/measure/measureSelection.js";
import { useMeasureOverlay } from "../kit/tools/measure/useMeasureOverlay.js";
import { readIsolation, useIsolation } from "../kit/tools/select/useIsolation.js";
import { useSceneSelection } from "../kit/tools/select/useSceneSelection.js";
import HoverTip from "../kit/shell/HoverTip.jsx";
import { groupChips } from "../kit/tools/select/groupChips.js";
import { TOUCH_HIT_PX } from "../kit/viewport/dom.js";
import { usePlotView } from "../kit/viewport/usePlotView.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import SchematicSection, { useSchematicDetail, useSchematicTrees } from "./SchematicSection.jsx";
import SchematicSelectFilter from "./SchematicSelectFilter.jsx";
import SheetsSection from "./SheetsSection.jsx";
import { useSchematicReferences } from "./schematicReferences.jsx";
import { createSchematicScene } from "./schematicScene.js";
import { SCHEMATIC_NO_CAMERA, SCHEMATIC_NO_DISPLAY, SCHEMATIC_SELECT_KINDS, SCHEMATIC_TOOL, SCHEMATIC_TOOL_MODES, readSchematicFilter } from "./tools.js";
import { useSchematicDocument } from "./useSchematicDocument.js";

/**
 * A KiCad schematic, a sheet at a time, as the picture drawn from its files, on a canvas, head on, as a
 * board is: the board's flat view (`kit/viewport/usePlotView.js`, `kit/shell/FlatViewFrame.jsx`), its
 * pan, zoom and fit, Select (a click the most specific thing under the pointer its filter ticks —
 * `SchematicSelectFilter.jsx` — a pin, a junction or a no-connect, a label, a wire, a symbol or a sheet
 * symbol; Shift adds; a drag the box between its ends, everything inside it), Annotate and Measure (to
 * pins' and wires' ends, junctions and labels, in millimetres), Quick Edit's references (`#R1`, `#R1.2`,
 * `#net:/MID`, `#wire:<uuid>`, `#sheet:/Load/`) and its Export (KiCad's PDF, SVGs, netlist and BOM). The
 * payload comes from the BACKEND, a sheet at a time (`useSchematicDocument.js`); nothing here parses
 * KiCad's files.
 *
 * It follows the viewer's theme, live: KiCad's light paper and dark ink in light, a dark sheet and light
 * ink of the same hues in dark (`plot2d/theme.js`'s `schematicColors`: a switch redraws, it reads nothing
 * again), on the app's neutral grey round the sheet. No drawing sheet (KiCad's frame and title block) is
 * drawn, as a board draws none. Its panel (`kit/shell/FlatPanel.jsx`) is the Parts and the Nets
 * (`SchematicSection.jsx`, a board's list rules, the picked part's or net's pins under them) and, for a
 * schematic of more than one sheet, the Hierarchy (`SheetsSection.jsx`, KiCad's Hierarchy
 * Navigator: a press shows that sheet, the way back up from one entered); a double-click on a sheet
 * symbol enters its sheet, and a right-click opens the view's menu (every view's, `kit/shell/viewMenu.js`:
 * the reference, Select, Isolate and a pin's net, Show sheet on a sheet symbol, Up one sheet over bare
 * paper, and the framing). Each sheet keeps its view with the file: going back to one, or reopening the file, finds it where it was left.
 * Ink and measurements are the sheet's they were made on: showing another sheet lets them go. A schematic has no view controls: it has no layers, and its colours are the theme's.
 * A selected net is lit across the sheet shown, the rest stepped back, as KiCad's net highlight.
 */

const SAVE_DELAY_MS = 180;
const SCHEMATIC_SURFACE = Object.freeze({ "data-schematic-surface": "" });
// The file's slices: the sheet shown and what is isolated, kept across rebuilds.
const SLICES = Object.freeze({ schematic: "1", isolated: "1" });
const SCHEMATIC_LIVE = Object.freeze({ commands: Object.freeze(["select", "clearSelection"]), declined: Object.freeze({}) });
const NO_SELECTION = Object.freeze({ hovered: [], selected: [] });
// The app's neutral grey round the sheet: a shade off the light theme's paper, the dark theme's own background.
const SURROUND = Object.freeze({ light: "#E5E5E5", dark: "#292929" });
const surroundOf = scheme => SURROUND[scheme === "dark" ? "dark" : "light"];
const PICK_PX = 6;
const pickPx = pointerType => (pointerType === "touch" ? TOUCH_HIT_PX : PICK_PX);
const finite = value => typeof value === "number" && Number.isFinite(value);
function readTransform(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const { scale, offsetX, offsetY } = raw;
  return finite(scale) && scale > 0 && finite(offsetX) && finite(offsetY) ? { scale, offsetX, offsetY } : null;
}
/** Each sheet's view as the file kept it: a sheet's path to its transform; a sheet at the fit is not kept. */
function readSheetViews(raw) {
  const views = raw?.views;
  if (!views || typeof views !== "object" || Array.isArray(views)) return [];
  return Object.entries(views).map(([path, transform]) => [canonicalSheetPath(path), readTransform(transform)]).filter(([, transform]) => transform);
}
const sheetViewsRecord = views => Object.fromEntries([...views].filter(([, transform]) => transform).map(([path, transform]) => [path, { ...transform }]));
const readSheet = raw => (typeof raw?.sheet === "string" && raw.sheet ? canonicalSheetPath(raw.sheet) : "/");
const schematicPacketReferences = (references, file) => [...new Set(references
  .filter(reference => reference?.resource?.path === file && reference.target?.kind === "cad-selector")
  .flatMap(reference => reference.target.selectors))];

function SchematicSurface({ view, data }) {
  const { t } = useI18n();
  const host = useViewerHost();
  const mobile = useViewerMobile();
  const workspace = useWorkspaceDocument({ view, data });
  const colorScheme = view.appearance?.colorScheme === "dark" ? "dark" : "light";

  // ---- the file's view: the sheet shown, its transform, what is isolated ----
  const [stored] = useState(() => readFileView(view.state, SLICES));
  const [restored] = useState(() => readTransform(stored.camera));
  const [sheet, setSheet] = useState(() => readSheet(stored.renderer.schematic));
  const document = useSchematicDocument({ workspace, path: view.file.path, sheet });
  const { file, plot, index, page, shown, alert } = document;
  const shownSheet = document.sheet;
  const canonicalPick = useCallback(id => index?.resolve(id)?.selector, [index]);
  const [restoredIsolation] = useState(() => readIsolation(stored.renderer.isolated?.selectors));
  const isolation = useIsolation({ index, restored: restoredIsolation, canonical: canonicalPick });
  const saved = useRef({ camera: restored, sheet, isolated: restoredIsolation });
  // Each sheet's view, kept with the file: going back to a sheet, or reopening the file, finds it
  // where it was left (null: the fit). The file's camera is the one on screen, on the sheet it reopens on.
  const sheetViews = useRef(null);
  if (!sheetViews.current) sheetViews.current = new Map([...readSheetViews(stored.renderer.schematic), [sheet, restored]]);
  const storedRef = useRef("");
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(view.onStateChange);
  stateChangeRef.current = view.onStateChange;
  const save = useCallback(change => {
    saved.current = { ...saved.current, ...change };
    const { camera, sheet: path, isolated } = saved.current;
    const record = writeFileView({ camera, renderer: { schematic: { sheet: path, views: sheetViewsRecord(sheetViews.current) }, isolated: { selectors: [...isolated] } }, signatures: SLICES });
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  const lastSheet = useRef(null);
  const rememberView = useCallback(transform => {
    const camera = transform ? { ...transform } : null;
    sheetViews.current.set(lastSheet.current ?? sheet, camera);
    save({ camera });
  }, [save, sheet]);
  useEffect(() => { storedRef.current = JSON.stringify(writeFileView({ camera: restored, renderer: { schematic: { sheet, views: sheetViewsRecord(sheetViews.current) }, isolated: { selectors: [...restoredIsolation] } }, signatures: SLICES })); }, []);
  useEffect(() => { if (shownSheet) save({ sheet: shownSheet }); }, [shownSheet, save]);
  useEffect(() => { save({ isolated: isolation.isolated }); }, [isolation.isolated, save]);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  // ---- tools: measurements are the sheet's (`file` keys Measure's session) ----
  const tools = useFlatTools({ toolModes: SCHEMATIC_TOOL_MODES, file: `${file}#sheet:${shownSheet || ""}`, revision: workspace.resource.revision, ready: Boolean(page) });
  const { toolMode, selectTool, annotating, measuring, annotation, measure } = tools;
  const [filter, setFilter] = useState(SCHEMATIC_SELECT_KINDS);
  const changeFilter = useCallback(next => { setFilter(readSchematicFilter(next)); selectTool(SCHEMATIC_TOOL.SELECT); }, [selectTool]);
  // The sheet as KiCad draws it: no page edge, in the theme (`usePlotView`'s `colorScheme`).
  const drawView = null;

  const indexRef = useRef(index);
  indexRef.current = index;
  const pageRef = useRef(page);
  pageRef.current = page;
  const sheetRef = useRef(null);
  sheetRef.current = plot?.layout.sheets[0] ?? null;
  const filterRef = useRef(filter);
  filterRef.current = filter;
  const schemeRef = useRef(colorScheme);
  schemeRef.current = colorScheme;
  const draftRef = useRef(null);
  const isolationRef = useRef(isolation);
  isolationRef.current = isolation;
  const annotationRef = useRef(annotation);
  annotationRef.current = annotation;
  const toolRef = useRef(toolMode);
  toolRef.current = toolMode;
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const viewRef = useRef(null);

  const highlightRef = useRef(NO_SELECTION);
  const hoveredInkRef = useRef([]);
  const paintRef = useRef(() => {});
  const requestPaint = useCallback(() => paintRef.current(), []);
  const scene = useMemo(() => (index ? createSchematicScene(index, { t, onHighlight: ink => { highlightRef.current = ink; } }) : null), [index, t]);
  const selection = useSceneSelection({ scene, requestRender: requestPaint });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const { references, chips: pickChips } = useSchematicReferences({ scene, selection, resource: workspace.resource });
  // A block picked whole (its row menu's Select all parts) is one chip, not a chip a part.
  const trees = useSchematicTrees(index);
  const chips = useMemo(() => groupChips({ selected: selection.selected, chips: pickChips, resource: workspace.resource, select: selection.select,
    groups: [...(trees?.parts.nodesById.values() || [])].filter(node => node.picks?.length > 1).sort((a, b) => b.picks.length - a.picks.length)
      .map(node => ({ id: node.id, label: node.label, picks: node.picks })),
    label: group => t("chip.blockParts", { name: group.label, count: group.picks.length }) }), [selection.selected, selection.select, pickChips, workspace.resource, trees, t]);
  const overlay = useCallback((ctx, { transform, pixelRatio, width, height }) => {
    const drawn = pageRef.current, sheetLayout = sheetRef.current;
    if (!drawn || !sheetLayout) return;
    const entries = list => list.flatMap(resolved => drawn.itemsOf(resolved));
    const { hovered, selected } = highlightRef.current;
    // A net in focus, or what is isolated, steps the rest of the sheet back.
    drawSchematicOverlay(ctx, sheetLayout, { transform, pixelRatio, width, height, appearance: schemeRef.current,
      isolated: entries(isolationRef.current.resolved), hovered: entries(hovered.slice(0, 1)), selected: entries(selected),
      dim: selected.some(item => item.kind === "net"), draft: draftRef.current });
    const session = annotationRef.current;
    drawAnnotationMarks(ctx, session.items, { transform, pixelRatio, selected: session.selected, hovered: hoveredInkRef.current });
  }, []);

  const annotationSurface = useMemo(() => plotAnnotationSurface({
    transform: () => viewRef.current?.transformRef.current || null,
    mirrorX: () => null,
    canvas: () => viewRef.current?.canvasRef.current || null
  }), []);
  const measureRuntimeRef = useRef(null);
  if (!measureRuntimeRef.current) {
    measureRuntimeRef.current = {
      get camera() {
        const current = viewRef.current, size = current?.sizeRef.current;
        return current && size ? boardPlanProjection(current.transformRef.current, size.width, size.height, null) : null;
      },
      renderer: { get domElement() { return viewRef.current?.canvasRef.current || null; } }
    };
  }

  // ---- showing a sheet: from the Hierarchy, a double-click, a pick on another sheet ----
  // What a press asked to see on a sheet not yet shown: framed once that sheet is drawn.
  const pendingFrame = useRef(null);
  const showSheet = useCallback((path, frameSelectors = null) => {
    pendingFrame.current = frameSelectors;
    setSheet(canonicalSheetPath(path));
  }, []);
  useEffect(() => {
    if (!shownSheet || !page) return;
    const previous = lastSheet.current;
    lastSheet.current = shownSheet;
    if (previous === null) return;
    if (previous !== shownSheet) {
      // Ink is the sheet's it was drawn on.
      if (annotationRef.current.hasAnnotation) annotationRef.current.forget();
      selectionRef.current.hover("");
    }
    const wanted = pendingFrame.current;
    pendingFrame.current = null;
    if (wanted && frameOnPage(wanted)) return;
    if (previous === shownSheet) return;
    const left = sheetViews.current.get(shownSheet);
    if (left) viewRef.current?.setView(left);
    else viewRef.current?.fit();
  }, [shownSheet, page]);
  /** Frame what `selectors` name on the sheet shown; false when none of it is drawn here. */
  function frameOnPage(selectors) {
    const drawn = pageRef.current, schematic = indexRef.current;
    if (!drawn || !schematic) return false;
    const boxes = selectors.map(id => drawn.extent(schematic.resolve(id))).filter(Boolean);
    if (!boxes.length) return false;
    const [x0, y0, x1, y1] = [Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])), Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3]))];
    viewRef.current?.frame([x0, -y1, x1, -y0]);
    return true;
  }
  /** What a press in a list picked, shown: the sheet shown if it is there, else the first sheet it is on, at that sheet's view. */
  const showSelectors = useCallback(selectors => {
    const drawn = pageRef.current, schematic = indexRef.current;
    if (!schematic) return;
    if (drawn && selectors.some(id => drawn.extent(schematic.resolve(id)))) return;
    const onSheet = selectors.map(id => schematic.resolve(id)?.sheets?.[0]).find(Boolean);
    if (onSheet && onSheet !== drawn?.path) showSheet(onSheet);
  }, [showSheet]);
  /** What a double-click in a list picked, framed: here, or on the first sheet it is on. */
  const frameSelectors = useCallback(selectors => {
    if (frameOnPage(selectors)) return;
    const schematic = indexRef.current;
    const onSheet = selectors.map(id => schematic?.resolve(id)?.sheets?.[0]).find(Boolean);
    if (onSheet && onSheet !== pageRef.current?.path) showSheet(onSheet, selectors);
  }, [showSheet]);

  // The name of what the pointer rests on, under Select (`kit/shell/HoverTip.jsx`): its name, and a pad's or
  // pin's net, a part's value.
  const [hoverTip, setHoverTip] = useState(null);
  const tipOfRef = useRef(null);
  tipOfRef.current = selector => {
    const resolved = indexRef.current?.resolve(selector), name = scene?.describePart(selector)?.name;
    return name ? [name, resolved?.kind === "pin" ? resolved.net : resolved?.kind === "part" ? resolved.part.value : ""].filter(Boolean).join(" · ") : "";
  };
  // ---- pointer -------------------------------------------------------------
  const [overPick, setOverPick] = useState(false);
  const measureHoverRef = useRef(null);
  const measureAnchorRef = useRef(null);
  useEffect(() => { if (!measuring) { measureHoverRef.current = null; measureAnchorRef.current = null; } }, [measuring]);
  useEffect(() => { if (!measure.state?.draft?.anchor) measureAnchorRef.current = null; }, [measure.state]);
  const handlers = useMemo(() => {
    const atPoint = (point, pointerType) => {
      const transform = viewRef.current?.transformRef.current;
      return transform ? { page: planToSheet(screenToModel(transform, point.x, point.y), null), reach: pickPx(pointerType) / transform.scale } : null;
    };
    const snapPick = (point, pointerType) => {
      const at = atPoint(point, pointerType), drawn = pageRef.current;
      if (!at || !drawn) return null;
      const snap = drawn.snap(at.page, { tolerance: at.reach });
      const [x, y] = snap ? snap.point : at.page;
      return { point: [x, y, 0], snapKind: snap ? snap.kind : "free", units: { unit: "mm", perWorld: 1 } };
    };
    const pickAt = (point, pointerType) => {
      const at = atPoint(point, pointerType), drawn = pageRef.current, kinds = filterRef.current;
      return at && drawn && kinds.length ? drawn.pick(at.page, { kinds, tolerance: at.reach }) : null;
    };
    const inkUnder = (point, pointerType) => (annotationRef.current.items.length
      ? annotationAt(point, annotationSurface.onScreen(annotationRef.current.items), pickPx(pointerType))[0]?.id || null : null);
    const measured = clear => measureSelectHandlers(measureRef.current, () => measureRuntimeRef.current, clear);
    const pointer = event => ({ clientX: event.clientX, clientY: event.clientY, pointerType: event.pointerType, shiftKey: event.shiftKey });
    const tap = (point, event) => {
      if (!pageRef.current) return;
      const tool = toolRef.current;
      if (tool === SCHEMATIC_TOOL.MEASURE) {
        const pick = snapPick(point, event.pointerType);
        if (!pick) return;
        const anchor = measureAnchorRef.current;
        if (anchor && anchor.point[0] === pick.point[0] && anchor.point[1] === pick.point[1]) return;
        if (!anchor) { measureAnchorRef.current = pick; measureHoverRef.current = pick; } else measureAnchorRef.current = null;
        measureRef.current.onPick(pick);
        return;
      }
      if (tool !== SCHEMATIC_TOOL.SELECT) return;
      const shift = event.shiftKey;
      const session = annotationRef.current;
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
    // A double-click on a sheet symbol, under Select, enters its sheet; anywhere else it fits.
    const doubleTap = (point, event) => {
      if (toolRef.current !== SCHEMATIC_TOOL.SELECT) return false;
      const at = atPoint(point, event?.pointerType), child = at ? pageRef.current?.sheetAt(at.page, at.reach) : null;
      if (!child) return false;
      selectionRef.current.clear();
      showSheet(child);
      return true;
    };
    const hover = (point, event) => {
      const tool = toolRef.current;
      if (tool === SCHEMATIC_TOOL.MEASURE) {
        const pick = point && pageRef.current ? snapPick(point, event?.pointerType) : null;
        measureHoverRef.current = pick || measureAnchorRef.current;
        measureRef.current.onHoverPoint(pick);
        return;
      }
      let over = false, inkIds = [], hit = null;
      if (tool === SCHEMATIC_TOOL.SELECT && point && pageRef.current) {
        const onMeasurement = measured(() => {}).hover(pointer(event));
        const ink = onMeasurement ? null : inkUnder(point, event.pointerType);
        inkIds = ink ? withGroups([ink], annotationRef.current.items) : [];
        hit = onMeasurement || ink ? null : pickAt(point, event.pointerType);
        over = onMeasurement || Boolean(ink) || Boolean(hit);
      } else if (measureRef.current.hovered) measureRef.current.hover("");
      if (inkIds.join() !== hoveredInkRef.current.join()) { hoveredInkRef.current = inkIds; requestPaint(); }
      selectionRef.current.hover(hit ? hit.selector : "");
      const tipKey = hit && point ? hit.selector : "";
      setHoverTip(now => ((now?.key || "") === tipKey ? now : tipKey ? { key: tipKey, text: tipOfRef.current(tipKey), x: point.x, y: point.y } : null));
      setOverPick(current => (current === over ? current : over));
    };
    // Select's drag is KiCad's window selection: drawn as it goes, everything wholly inside it once it lets go (Shift adds).
    const drag = (phase, { start, point, event }) => {
      const drawn = pageRef.current;
      if (toolRef.current !== SCHEMATIC_TOOL.SELECT || !drawn) return false;
      const from = atPoint(start, "mouse")?.page, to = atPoint(point, "mouse")?.page;
      if (!from || !to) return false;
      const box = [Math.min(from[0], to[0]), Math.min(from[1], to[1]), Math.max(from[0], to[0]), Math.max(from[1], to[1])];
      draftRef.current = phase === "start" || phase === "move" ? box : null;
      requestPaint();
      if (phase === "end") {
        const inside = drawn.within(box, { kinds: filterRef.current });
        if (!event?.shiftKey) selectionRef.current.clear();
        const kept = new Set(event?.shiftKey ? selectionRef.current.selected : []);
        for (const selector of inside) if (!kept.has(selector)) selectionRef.current.select(selector, { multiSelect: true });
      }
      return true;
    };
    // The sheet symbol under a pane point, for the menu's Show sheet.
    const sheetUnder = (point, pointerType) => {
      const at = atPoint(point, pointerType);
      return at ? pageRef.current?.sheetAt(at.page, at.reach) || null : null;
    };
    return { tap, hover, drag, doubleTap, pickAt, sheetUnder };
  }, [annotationSurface, requestPaint, showSheet]);

  const plotView = usePlotView({
    plot, restored, colorScheme, surround: surroundOf, noun: "schematic", onViewMoved: rememberView, drawView, overlay,
    onTap: handlers.tap, onHover: handlers.hover, onDrag: handlers.drag, onDoubleTap: handlers.doubleTap
  });
  viewRef.current = plotView;
  paintRef.current = plotView.requestPaint;
  const { canvasRef, capture, containerRef, dragging, fit, thumbnail } = plotView;
  useEffect(() => { requestPaint(); }, [annotation.items, annotation.selected, isolation.resolved, colorScheme, page, requestPaint]);
  useEffect(() => { handlers.hover(null, null); }, [toolMode, handlers]);

  // The view on screen as a prompt carries it: the plan view's camera, the pane's shape, and the sheet in
  // the appearance shown, which `cad kicad_sch snapshot --display` draws again.
  const currentView = useCallback(() => {
    const current = viewRef.current, size = current?.sizeRef.current;
    const camera = current && size ? planCamera(current.transformRef.current, size.width, size.height) : null;
    const seen = camera ? promptView({ camera, width: size.width, height: size.height }) : null;
    return seen ? { ...seen, display: { sheet: pageRef.current?.path || "/", border: false, appearance: schemeRef.current } } : null;
  }, []);

  const measureCanvasRef = useRef(null);
  useMeasureOverlay({
    measureCanvasRef, measureState: measure.state, activeMeasurementId: measure.activeId,
    selectedMeasurementIds: measure.selected, hoveredMeasurementId: measure.hovered, measureHoverRef,
    measureModeActive: measuring, runtimeRef: measureRuntimeRef, mountRef: containerRef, preview: false, viewerReadyTick: 0
  });

  const ready = shown && !document.loading && !document.updating && !alert;

  // A selection that names something on another sheet shows the first sheet it is on.
  const showSelected = useCallback(named => {
    const schematic = indexRef.current;
    const first = named.map(selector => schematic?.resolve(selector)).find(Boolean);
    if (!first || first.sheets.includes(pageRef.current?.path)) { frameOnPage(named); return; }
    if (first.sheets[0]) showSheet(first.sheets[0], named);
  }, [showSheet]);

  const selectRequest = workspace.commands.selectReference ?? null;
  const selectKey = selectRequest?.key ?? null;
  const handledSelect = useRef(null);
  const { acknowledgeCommand } = workspace;
  useEffect(() => {
    if (selectKey === null || handledSelect.current === selectKey) return;
    const named = splitSchematicRefSelectors(selectRequest?.selector).map(selector => parseSchematicRefSelector(selector)?.canonical).filter(Boolean);
    if (index && named.length) {
      selectionRef.current.clear();
      const found = named.filter(selector => index.resolve(selector));
      for (const selector of found) selectionRef.current.select(selector, { multiSelect: true });
      if (found.length) showSelected(found);
    } else if (document.loading) return;
    handledSelect.current = selectKey;
    acknowledgeCommand?.("selectReference", selectKey);
  }, [selectKey, selectRequest, index, document.loading, acknowledgeCommand, showSelected]);

  // ---- Quick Edit, the keys and the live command surface ------------------------
  const nameReference = useCallback(reference => {
    const id = reference?.resource?.path === workspace.resource?.path && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const described = id ? scene?.describePart(id) : null;
    return described ? { name: described.name, kind: described.glyph } : "";
  }, [workspace.resource?.path, scene]);
  const path = workspace.resource?.kind === "workspace-file" ? workspace.resource.path : "";
  const copySelection = () => {
    const selected = selectionRef.current.selected;
    if (!selected.length || !path) return false;
    void Promise.resolve(host.clipboard.writeText(buildSchematicRefToken({ path, selectors: selected })))
      .catch(error => handover.reportActionError(error instanceof Error ? error.message : String(error)));
    return true;
  };
  const selectList = request => {
    const raw = Array.isArray(request) ? request : Array.isArray(request?.selectors) ? request.selectors : [request?.selector ?? request];
    const list = raw.flatMap(selector => splitSchematicRefSelectors(selector));
    const unknown = list.filter(selector => !parseSchematicRefSelector(selector) || !index?.resolve(selector));
    if (!index || unknown.length) {
      throw new Error(`Not in this schematic: ${unknown.join(", ") || list.join(", ")}. Select schematic references such as #U3, #U3.7, #net:VBUS, `
        + "#sheet:/Power/ or #wire:<uuid> (#bus:, #label:, #junction:, #no_connect:, #bus_entry:, #symbol:).");
    }
    selectionRef.current.clear();
    const canonical = list.map(selector => parseSchematicRefSelector(selector).canonical);
    for (const selector of canonical) selectionRef.current.select(selector, { multiSelect: true });
    showSelected(canonical);
  };
  const runtime = {
    readState: () => ({
      resource: { ...workspace.resource }, revision: String(workspace.resource.revision || ""),
      loading: document.loading || document.updating, selection: references, camera: null, display: {},
      schematicDisplay: { sheet: pageRef.current?.path || "/", border: false, appearance: schemeRef.current }
    }),
    setCamera() { throw new Error(SCHEMATIC_NO_CAMERA); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(SCHEMATIC_NO_DISPLAY); },
    select: selectList,
    clearSelection() { selectionRef.current.clear(); },
    capture,
    thumbnail
  };
  const handover = useFlatHandover({
    view, data, workspace, file, shown, ready, alert, tools, selection, references, chips, nameReference,
    capture, currentView, annotationDocument: plotAnnotationDocument, runtime, live: SCHEMATIC_LIVE,
    copySelection: index ? copySelection : null, fit, captureFailed: t("alert.captureDrawingFailed"), packetReferences: schematicPacketReferences
  });

  // What the view's menu's Show in list asked the panel's lists to bring into view (`CircuitTree.jsx`).
  const [reveal, setReveal] = useState(null);
  // ---- the menu: a secondary tap on the sheet, under Select (`kit/shell/viewMenu.js`'s groups) ----
  // Over something Select would pick: its reference (with what is picked already), Select or
  // Deselect, Isolate for a part or a net and its net for a pin or a wire, Show sheet on a sheet
  // symbol, then the framing. Over bare paper: Exit isolate, Up one sheet in a sheet entered, the framing.
  const contextMenuItems = index && toolMode === SCHEMATIC_TOOL.SELECT ? press => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const point = { x: press.clientX - rect.left, y: press.clientY - rect.top };
    const hit = handlers.pickAt(point, "mouse"), child = handlers.sheetUnder(point, "mouse");
    const now = selectionRef.current, isolated = isolation.isolated;
    const zoom = zoomGroup({ t, onZoomFit: fit, onZoomSelection: () => frameSelectors(selectionRef.current.selected), selectionAvailable: now.selected.length > 0 });
    const enter = child ? [menuEntry("show-sheet", t("schematic.text.show_sheet", { name: index.sheetName(child) }),
      { onSelect: () => { selectionRef.current.clear(); showSheet(child); } })] : [];
    if (!hit) {
      const parts = String(shownSheet || "/").split("/").filter(Boolean);
      const parent = parts.length ? canonicalSheetPath(parts.slice(0, -1).join("/")) : "";
      return menuGroups([exitIsolateEntry({ isolatedCount: isolated.length, onExitIsolates: isolation.clear, t })], enter,
        parent ? [menuEntry("parent-sheet", t("menu.parentSheet"), { onSelect: () => showSheet(parent) })] : [], zoom);
    }
    const id = hit.selector, selected = now.selected.includes(id), resolved = index.resolve(id);
    const copyText = path ? buildSchematicRefToken({ path, selectors: [...new Set([...now.selected, id])] }) : "";
    const ownNet = resolved && resolved.kind !== "net" ? String(resolved.net || "") : "";
    const netId = ownNet ? index.resolve(`#net:${ownNet}`)?.selector || "" : "";
    const isolatable = resolved?.kind === "part" || resolved?.kind === "net";
    // Show in list: the Parts' row of a part or a pin's part, the Nets' row of a net or of what is on one.
    const listed = resolved?.kind === "part" || resolved?.kind === "pin" ? ["parts", id] : resolved?.kind === "net" ? ["nets", id] : netId ? ["nets", netId] : null;
    const showInList = listed ? [menuEntry("show-in-list", t("menu.showInList"), { onSelect: () => {
      handover.panelControl.current?.show?.(listed[0]);
      setReveal({ id: listed[1], key: Date.now() });
    } })] : [];
    return menuGroups(
      referenceGroup({ copyText, onCopy: () => { void Promise.resolve(host.clipboard.writeText(copyText)).catch(() => {}); }, t }),
      pickGroup({ selected, onSelect: () => now.select(id, { multiSelect: selected }), t,
        isolated: isolatable ? isolated.includes(id) : null, onIsolate: () => isolation.toggle(id), isolatedCount: isolated.length, onExitIsolates: isolation.clear }),
      [...(netId ? [menuEntry("isolate-net", isolated.includes(netId) ? t("tree.exitIsolateNamed", { name: ownNet }) : t("tree.isolateNamed", { name: ownNet }),
        { onSelect: () => isolation.toggle(netId) })] : []), ...enter, ...showInList],
      zoom);
  } : null;

  // ---- the frame ---------------------------------------------------------------
  const failed = Boolean(alert) && !shown;
  const compact = Boolean(view.appearance?.compact);
  const chromeHidden = document.loading || failed;
  const selectMenu = <SchematicSelectFilter value={filter} onChange={changeFilter} disabled={!shown} />;
  const { strip, row } = flatViewTools(tools, { colorScheme, shown, selectMenu, t });
  const toolRow = row;
  // The panel (`kit/shell/FlatPanel.jsx`): the Parts, the Nets, then, for more than one sheet, the
  // Hierarchy; under them, what is picked in detail.
  // A list row's Copy Reference: what it names, with what is selected, as one reference into the file.
  const copyReferences = ids => { void Promise.resolve(host.clipboard.writeText(buildSchematicRefToken({ path, selectors: ids }))).catch(() => {}); };
  const takeSelect = () => selectTool(SCHEMATIC_TOOL.SELECT);
  const list = id => <SchematicSection index={index} trees={trees} list={id} selection={selection} isolated={isolation.isolated} revealRequest={reveal}
    onIsolate={isolation.toggle} onCopyReference={path ? copyReferences : null} onShow={showSelectors} onFrame={frameSelectors} onSelect={takeSelect} />;
  const detail = useSchematicDetail(index, selection, { onSelect: takeSelect, onShow: showSelectors, onFrame: frameSelectors });
  const panel = index ? { kind: "schematic", label: t("schematic.text.schematic_panel"), searchLabel: t("schematic.text.search_schematic"),
    searchPlaceholder: t("schematic.text.search_schematic_placeholder"), detail, tabs: [
      { id: "parts", label: t("board.text.parts"), searchLast: true, content: list("parts") },
      { id: "nets", label: t("board.text.nets"), searchLast: true, content: list("nets") },
      ...(index.order.length > 1 ? [{ id: "hierarchy", label: t("schematic.text.hierarchy"), content: <SheetsSection index={index} shown={shownSheet}
        onShow={showSheet} onHover={selector => selection.hover(selector)} /> }] : [])
    ] } : null;
  const cursor = measuring ? "cursor-crosshair" : overPick && !dragging ? "cursor-pointer" : "cursor-default";

  // The strip's zoom, and the zoom's keys (`useFlatHandover`'s `zoomKeys`).
  const zoom = { ...plotView.zoom, zoomToSelection: () => frameSelectors(selectionRef.current.selected), selectionAvailable: selection.selected.length > 0 };
  handover.zoomKeys.current = zoom;
  return (
    <FlatViewFrame surface={SCHEMATIC_SURFACE} containerRef={containerRef} busy={document.loading || document.updating}
      file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} loading={document.loading} loadingLabel={t("schematic.text.reading_schematic")}
      updating={document.updating} updateStatus={{ pending: true, label: t("schematic.text.updating_schematic") }} tools={index ? strip : []}
      toolRow={index ? toolRow : null} views={[]} panel={panel} panelControl={handover.panelControl} toolStack={handover.toolStack} onToolStackChange={handover.changeToolStack} notice={view.notice}
      quickEdit={index ? handover.quickEdit : null} alert={alert} cardAlert={handover.cardAlert} alertDismissal={handover.alertDismissal}
      shown={shown} onReload={view.reload} canvasRef={canvasRef} contextMenuItems={contextMenuItems}
      zoom={zoom}>
      <canvas ref={canvasRef} aria-label={t("schematic.text.schematic_file", { file: view.file.name, sheet: shownSheet && index ? index.sheetName(shownSheet) : "" })}
        role="img" data-schematic-tool={toolMode} data-schematic-sheet={shownSheet || ""}
        className={cn("absolute inset-0 block touch-none select-none", cursor)} />
      <canvas ref={measureCanvasRef} className="pointer-events-none absolute inset-0 z-[1] h-full w-full" aria-hidden="true" data-scene-measure="" />
      {annotating && shown && index ? <AnnotationOverlay annotation={annotation} surface={annotationSurface} viewOf={currentView} /> : null}
      {dragging ? null : <HoverTip tip={hoverTip} />}
    </FlatViewFrame>
  );
}

export default function SchematicRenderer(props) {
  const { data, ...view } = props;
  return <SchematicSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}


import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { parseBoardRefSelector, splitBoardRefSelectors } from "@text-to-cad/core/lib/boardRefs.js";
import { usePromptDestination, useViewerHost } from "../../host/context.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import ToolColumn from "../kit/shell/ToolColumn.jsx";
import { useViewerShortcuts } from "../kit/shell/useViewerShortcuts.js";
import QuickEdit from "../kit/tools/quick-edit/QuickEdit.jsx";
import { normalizeToolStack } from "../kit/tools/toolStackLayout.js";
import { findingCopyText } from "./board/boardFacts.js";
import { BOARD_TOOL, useBoardInspector } from "./board/useBoardInspector.js";
import { useBoardDrawing } from "./board/useBoardDrawing.js";
import { useCrossProbe } from "./board/useCrossProbe.js";
import { Pencil } from "lucide-react";
import DrawingOverlay from "../kit/tools/draw/DrawingOverlay.jsx";
import ToolPanel, { ToolPanelFooterButton } from "../kit/tools/ToolPanel.jsx";
import { DRAWING_TOOLBAR_TOOLS, DrawingToolbar } from "../../drawing/toolbar.jsx";
import { BoardMeasurePanel, BoardReferencePanel, BoardTreePanel } from "./board/BoardPanels.jsx";
import { BoardMeasureIcon, BoardSelectIcon } from "./board/boardModes.jsx";
import { BoardDisplaySection, boardDisplayAirwires, boardDrawView, readBoardDisplay } from "./board/BoardDisplay.jsx";
import DisplayPopover from "../kit/shell/DisplayPopover.jsx";
import ViewerAlertCard, { useAlertDismissal } from "../kit/status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../kit/status/ViewerLoadingOverlay.js";
import { ViewUpdateStatus } from "../kit/status/ViewUpdateStatus.jsx";
import { VIEWPORT_ACTION_HEIGHT_PX, VIEWPORT_CUBE_BOTTOM_PX, VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "../kit/shell/viewportLayout.js";
import { ViewportTopRight } from "../kit/shell/ViewportTopRight.jsx";
import { attachLiveBinding } from "../kit/shell/liveBinding.js";
import { useWhenSettled } from "../kit/shell/useWhenSettled.js";
import { createViewPromptContext, promptDeliveryError } from "../kit/shell/promptContext.js";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import { planeTransformCamera, readPlaneTransform } from "../kit/plane/planeTransform.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { plotLoadAlert, usePlotPayload } from "./usePlotPayload.js";
import { usePlotView } from "./usePlotView.js";
import { plotKindForPath, plotWords } from "./plotWords.js";

/**
 * A KiCad board or schematic, or a wiring harness, as the picture its own tool draws of it, on a
 * canvas: a board with all its layers stacked back to front on KiCad's board background, its
 * unrouted connections as a ratsnest; a schematic's sheets one under another, root first.
 *
 * The picture comes from the BACKEND (`GET /__cad/plot`), which runs `kicad-cli` over the file
 * and returns its SVG plot. This renderer never parses KiCad's files. A board's payload also
 * carries its index (`board`: parts, pads, nets, tracks, checks, in the sheet's millimetres), and
 * with it the board has the tools a person points with: Select (with its tree and Reference),
 * Draw, Measure, Quick Edit and the copy key, all speaking board references (`#U3`, `#U3.9`,
 * `#net:VIN`) that the agent resolves with `cadgen.pcb.read_board`. A schematic's payload carries
 * its own (`schematic`: symbols, pins, wires, labels, nets), and with it Select, Quick Edit and the
 * copy key, in the same references (`cadgen.pcb.read_schematic`); a distance or a sketch on a
 * schematic's layout means nothing to the design, so it has no Measure and no Draw. Nothing here
 * edits a design: the agent does, in its script. No 3D: a board model exports its STEP and GLB as
 * files of their own.
 */

const SAVE_DELAY_MS = 180;
// A plot keeps its tool's colours whatever the theme: where its paper is the other way round from the
// theme (a schematic's light sheet in the dark, a board's dark one in the light), the tool panels
// over it stand nearly opaque (`lib/floatingSurface.js`).
const CONTRASTING_CHROME_ALPHA = "90%";
// A board's Display button: in the bottom-left corner, under the tool column, which stops short of it.
const DISPLAY_POSITION = Object.freeze({ bottom: VIEWPORT_CUBE_BOTTOM_PX, left: VIEWPORT_INSET_PX, height: VIEWPORT_ACTION_HEIGHT_PX });
const lightColour = (hex) => {
  const match = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || ""));
  if (!match) return null;
  const [r, g, b] = match.slice(1).map((part) => parseInt(part, 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5;
};
// A board's Display, as a slice of its file's view; a new shape gets a new signature.
const BOARD_SLICE = Object.freeze({ board: "1" });

function PlotSurface({ view, data }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = usePlotPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const words = plotWords(payload.plot?.layout.kind || plotKindForPath(view.file.path));
  // A failed action's card: its title says which action failed (a copy, a capture), its message why.
  const [actionError, setActionError] = useState(null);
  const [displayOpen, setDisplayOpen] = useState(false);
  const { onReady, onStateChange } = view;

  // ---- the view this file was left at ---------------------------------------
  // The file's view (`kit/shell/fileView.js`): the plot's transform as its camera, and a board's
  // Display (mode, side, pours) as its one slice.
  const isBoardFile = plotKindForPath(view.file.path) === "board";
  const [stored] = useState(() => readFileView(view.state, BOARD_SLICE));
  const [restored] = useState(() => readPlaneTransform(stored.camera));
  const [boardDisplay, setBoardDisplay] = useState(() => readBoardDisplay(stored.renderer.board));
  const cameraRef = useRef(planeTransformCamera(restored, Boolean(restored)));
  const displayRef = useRef(boardDisplay);
  const recordView = () => writeFileView({ camera: cameraRef.current, ...(isBoardFile ? { renderer: { board: displayRef.current }, signatures: BOARD_SLICE } : {}) });
  const storedRef = useRef(null);
  if (storedRef.current === null) storedRef.current = JSON.stringify(recordView());
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(onStateChange);
  stateChangeRef.current = onStateChange;
  const recordViewRef = useRef(recordView);
  recordViewRef.current = recordView;
  const saveView = useCallback(() => {
    const record = recordViewRef.current();
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  // A view that is still the fit stores nothing — `null` is "fit me", and it is what a plot
  // dropped back to the fit must write, not a stale transform.
  const rememberView = useCallback((transform) => {
    cameraRef.current = planeTransformCamera(transform, Boolean(transform));
    saveView();
  }, [saveView]);
  const changeBoardDisplay = useCallback((next) => {
    displayRef.current = next;
    setBoardDisplay(next);
    saveView();
  }, [saveView]);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  // ---- a board's and a schematic's tools ------------------------------------------
  // The inspector reads the view through refs, so it is made before the view and handed its parts.
  const viewParts = useRef({ transformRef: { current: null }, requestPaint: null, canvasRef: { current: null } });
  // A board drawn layer by layer can be seen from either side, with any of its layers.
  const boardSheet = payload.plot?.layout.sheets?.[0] ?? null;
  const layered = isBoardFile && Array.isArray(boardSheet?.layers) && boardSheet.layers.length > 0;
  const shownDisplay = layered ? boardDisplay : null;
  const inspector = useBoardInspector({
    plot: payload.plot, transformRef: { get current() { return viewParts.current.transformRef.current; } },
    requestPaint: useCallback(() => viewParts.current.requestPaint?.(), []),
    canvasRef: { get current() { return viewParts.current.canvasRef.current; } }, side: shownDisplay?.side || "top",
    placement: boardDisplayAirwires(shownDisplay)
  });
  const drawView = useMemo(() => (shownDisplay ? boardDrawView(shownDisplay, boardSheet) : null), [shownDisplay, boardSheet]);
  const plotView = usePlotView({
    plot: payload.plot, restored, colorScheme: view.appearance?.colorScheme === "dark" ? "dark" : "light",
    onViewMoved: rememberView, noun: words.noun, drawView,
    overlay: inspector.available ? inspector.paintOverlay : null, picking: inspector.available ? inspector.picking : null
  });
  const { canvasRef, containerRef, dragging, fit, thumbnail } = plotView;
  // A capture is the view as it stands, without the hover under a pointer that has moved on to ask for it.
  const { dropHover } = inspector;
  const { capture: captureView } = plotView;
  const capture = useCallback(() => { dropHover(); return captureView(); }, [dropHover, captureView]);
  viewParts.current = { transformRef: plotView.transformRef, requestPaint: plotView.requestPaint, canvasRef };
  // A board and its schematic open in two views select together, through the host (selection only).
  useCrossProbe({ port: host.crossProbe, path: view.file.path, inspector, view: plotView, canvasRef,
    layout: payload.plot?.layout ?? null, mirrored: shownDisplay?.side === "bottom" });
  const drawing = inspector.available && inspector.tool === BOARD_TOOL.DRAW;
  const boardDrawing = useBoardDrawing({ active: drawing, transformRef: plotView.transformRef, setView: plotView.setView, paintNow: plotView.paintNow,
    settle: plotView.settle, canvasRef });

  // ---- host chrome -----------------------------------------------------------
  useEffect(() => { onReady?.(true); }, [onReady]);

  // With a plot on screen, a failure to read the file again leaves that plot to use.
  const shown = Boolean(payload.plot);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: words.openFailed,
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = plotLoadAlert(workspace.modelKey || file, payload.error);
    return failed && shown ? { ...failed, blocking: false, message: `${failed.message} ${words.remains}` } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown, words]);
  // Settled is this revision's plot read and decoded: a capture waits out an update.
  const ready = shown && !payload.loading && !payload.updating && !alert;

  // ---- what a board hands over ---------------------------------------------------
  const mobile = useViewerMobile();
  // The name copied references give this file, as a STEP's do: its absolute path, so they still say
  // which file they belong to when pasted into a prompt spanning several.
  const referencePath = view.file.path;
  const copySelection = useCallback(async (selectors = inspector.selection) => {
    const token = inspector.copyText(referencePath, selectors);
    // A chosen check copies with its sentence, so a paste says what is wrong as well as where.
    const text = selectors === inspector.selection ? findingCopyText(inspector.finding, token) : token;
    if (!text) return false;
    try {
      await host.clipboard.writeText(text);
      setActionError((current) => (current?.title === words.copyFailed ? null : current));
      return true;
    } catch (error) {
      setActionError({ title: words.copyFailed, message: error instanceof Error ? error.message : String(error) });
      return false;
    }
  }, [inspector, referencePath, host.clipboard, words]);
  inspector.copyRef.current = copySelection;
  // What is selected, in the prompt grammar: the references a Quick Edit attaches.
  const references = useMemo(() => (inspector.selection.length
    ? [{ resource: workspace.resource, target: { kind: "cad-selector", selectors: [...inspector.selection] },
        ...(inspector.finding?.summary ? { summary: inspector.finding.summary } : {}) }] : []),
  [inspector.selection, inspector.finding, workspace.resource]);
  const rootRef = useRef(null);
  // The pane, once mounted: Display's dropdown keeps inside it, as a 3D view's keeps inside its viewer.
  const [rootElement, setRootElement] = useState(null);
  useEffect(() => { setRootElement(rootRef.current); }, []);
  // Draw's copy: the view with its ink, to the clipboard.
  const copyDrawing = useCallback(async () => {
    if (!boardDrawing.drawing.hasContent) return false;
    try {
      await host.clipboard.writeImage(boardDrawing.capture());
      setActionError((current) => (current?.title === words.copyFailed ? null : current));
      return true;
    } catch (error) {
      setActionError({ title: words.copyFailed, message: error instanceof Error ? error.message : String(error) });
      return false;
    }
  }, [boardDrawing, host.clipboard, words]);
  const copyAction = () => {
    if (drawing && boardDrawing.drawing.hasContent) { void copyDrawing(); return true; }
    if (inspector.selection.length) { void copySelection(); return true; }
    return false;
  };
  useViewerShortcuts({
    viewerElement: rootRef,
    escapeActive: inspector.available && Boolean(inspector.selection.length || inspector.measureStart || inspector.finding || inspector.tool === BOARD_TOOL.MEASURE),
    onEscape: () => { inspector.escape(); }, onCopy: inspector.available ? copyAction : undefined
  });
  const toolStack = useMemo(() => normalizeToolStack(workspace.services.preferences?.toolStack), [workspace.services.preferences?.toolStack]);
  const toolStackRef = useRef(toolStack);
  toolStackRef.current = toolStack;
  const changeToolStack = useCallback((patch) => {
    const next = normalizeToolStack({ ...toolStackRef.current, ...(typeof patch === "function" ? patch(toolStackRef.current) : patch) });
    toolStackRef.current = next;
    workspace.services.onPreferenceChange({ toolStack: next });
  }, [workspace.services]);
  const DrawIcon = DRAWING_TOOLBAR_TOOLS.find((item) => item.id === boardDrawing.drawing.tool)?.Icon || Pencil;
  const onBoard = inspector.document === "board";
  const tools = useMemo(() => (inspector.available ? [
    { id: BOARD_TOOL.SELECT, label: "Select", icon: <BoardSelectIcon mode={inspector.selectMode} document={inspector.document} className="size-3.5" aria-hidden="true" />,
      active: inspector.tool === BOARD_TOOL.SELECT, onSelect: () => inspector.chooseTool(BOARD_TOOL.SELECT),
      panel: { id: "tree", label: onBoard ? "Board" : "Schematic" } },
    // The button shows the drawing tool in hand, as on a STEP.
    ...(onBoard ? [
      { id: BOARD_TOOL.DRAW, label: "Draw", icon: <DrawIcon data-drawing-tool={boardDrawing.drawing.tool} className="size-3" strokeWidth={2} aria-hidden="true" />,
        active: inspector.tool === BOARD_TOOL.DRAW, onSelect: () => inspector.chooseTool(BOARD_TOOL.DRAW) },
      { id: BOARD_TOOL.MEASURE, label: "Measure", icon: <BoardMeasureIcon mode={inspector.measureMode} className="size-3.5" aria-hidden="true" />,
        active: inspector.tool === BOARD_TOOL.MEASURE, onSelect: () => inspector.chooseTool(BOARD_TOOL.MEASURE) },
    ] : []),
  ] : []), [inspector, onBoard, DrawIcon, boardDrawing.drawing.tool]);

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
      .then((result) => {
        const message = promptDeliveryError(result);
        setActionError(message ? { title: words.captureFailed, message } : null);
      });
  }, [capture, host.promptContext, words]);

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

  // A host asking to select a reference: a board selects it once its index is in; anything else
  // answers rather than dropping it.
  const selectRequest = workspace.commands.selectReference ?? null;
  const selectKey = selectRequest?.key ?? null;
  const handledSelect = useRef(null);
  useEffect(() => {
    if (selectKey === null || handledSelect.current === selectKey) return;
    const selectors = splitBoardRefSelectors(selectRequest?.selector);
    if (inspector.available && selectors.length && selectors.every((selector) => parseBoardRefSelector(selector))) {
      inspector.select(selectors);
    } else if (!ready && payload.loading) return;
    handledSelect.current = selectKey;
    workspace.acknowledgeCommand?.("selectReference", selectKey);
  }, [selectKey, selectRequest, inspector, ready, payload.loading, workspace.acknowledgeCommand]);

  // ---- the live command surface ----------------------------------------------
  // A KiCad document answers select and clearSelection from the start: while it loads, the binding
  // says to wait; once on screen, by its index — or, read without one, in words.
  const kicad = isBoardFile || plotKindForPath(view.file.path) === "schematic";
  const runtimeRef = useRef(null);
  runtimeRef.current = {
    readState: () => ({
      resource: { ...workspace.resource }, revision: String(workspace.resource.revision || ""),
      loading: payload.loading || payload.updating, selection: references.map((reference) => ({ ...reference, resource: { ...reference.resource } })),
      camera: null, display: {}, renderMode: "inspect"
    }),
    // A board or a schematic selects by board references (`#U3`, `#U3.9`, `#net:VIN`): an agent
    // pointing at what it changed.
    ...(kicad ? {
      select(request) {
        if (!inspector.available) throw new Error(words.declined.select);
        const raw = Array.isArray(request) ? request : Array.isArray(request?.selectors) ? request.selectors : [request?.selector ?? request];
        const list = raw.flatMap((selector) => splitBoardRefSelectors(selector));
        const unknown = list.filter((selector) => !parseBoardRefSelector(selector) || !inspector.index.resolve(selector));
        if (unknown.length) {
          throw new Error(onBoard
            ? `Not on this board: ${unknown.join(", ")}. Select board references such as #U3, #U3.9, #net:VIN or #@x10y5.`
            : `Not on this schematic: ${unknown.join(", ")}. Select references such as #U3, #U3.9 or #net:VIN (points are a board's).`);
        }
        inspector.select(list);
      },
      clearSelection() {
        if (!inspector.available) throw new Error(words.declined.clearSelection);
        inspector.clear();
      },
    } : {}),
    setCamera() { throw new Error(words.noCamera); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(layered ? words.displayInView : words.noDisplay); },
    setRenderMode() { throw new Error(words.noDisplay); },
    capture,
    thumbnail
  };
  // A plot has settled once it is read and decoded: a library card's picture waits for that.
  const whenSettled = useWhenSettled(() => ready);
  // The card the viewport shows, and its dismissal: put away, its icon in the navbar brings it back.
  const cardAlert = alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: actionError.title, message: actionError.message } : null);
  const alertDismissal = useAlertDismissal(cardAlert, { hasContent: shown, scope: file, onNavigationActionsChange: view.onNavigationActionsChange });
  const binding = data.services.live;
  // A board or a schematic answers select and clearSelection itself; a harness declines them.
  const declined = useMemo(() => {
    if (!kicad) return words.declined;
    const { select: _select, clearSelection: _clear, ...rest } = words.declined;
    return rest;
  }, [kicad, words.declined]);
  const liveCommands = useMemo(() => (kicad ? ["select", "clearSelection"] : []), [kicad]);
  useEffect(() => {
    if (!binding) return undefined;
    return attachLiveBinding(binding, () => runtimeRef.current, { declined, ready: whenSettled, commands: liveCommands });
  }, [binding, whenSettled, declined, liveCommands]);

  // While the plot loads, or once it has failed to, there is no chrome: no tools, no Quick Edit.
  const chromeHidden = !shown || payload.loading || Boolean(alert && !shown);
  const compact = Boolean(view.appearance?.compact);
  const boardChrome = inspector.available && !chromeHidden && !compact;
  const copyShortcut = host.environment?.platform === "darwin" ? "⌘C" : "Ctrl+C";
  const darkTheme = view.appearance?.colorScheme === "dark";
  const paperAgainstTheme = (payload.plot?.layout.sheets || []).some((sheet) => {
    const light = lightColour(sheet.background);
    return light !== null && light === darkTheme;
  });
  // Quick Edit's sketch: while Draw is up, the view with its ink once there is some.
  const sketch = useMemo(() => (drawing ? { ink: boardDrawing.drawing.hasContent, capture: boardDrawing.capture } : null),
    [drawing, boardDrawing.drawing.hasContent, boardDrawing.capture]);
  return (
    <div ref={rootRef} className="relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" data-plot-surface tabIndex={-1}>
      <div ref={containerRef} className="@container/cad-viewport relative min-h-0 flex-1" aria-busy={payload.loading || payload.updating ? "true" : "false"} data-cad-scene-backdrop=""
        style={paperAgainstTheme ? { "--cad-chrome-alpha": CONTRASTING_CHROME_ALPHA } : undefined}>
        <canvas ref={canvasRef} aria-label={`${words.label}: ${view.file.name}`} role="img"
          className={cn("absolute inset-0 block touch-none select-none", dragging ? "cursor-grabbing" : inspector.available ? "cursor-default" : "cursor-grab")} />
        {boardChrome && drawing ? <DrawingOverlay {...boardDrawing.overlay} /> : null}
        {/* The board's Display settings in the bottom-left corner, where a 3D file's sit on its cube. */}
        {boardChrome && layered ? <div className="pointer-events-auto absolute z-20 flex items-center" style={DISPLAY_POSITION} data-viewport-actions="">
          <DisplayPopover open={displayOpen} onOpenChange={setDisplayOpen} boundary={rootElement}>
            <BoardDisplaySection display={boardDisplay} onChange={changeBoardDisplay} />
          </DisplayPopover>
        </div> : null}
        {boardChrome ? <ToolColumn tools={tools} layout={toolStack} onLayoutChange={changeToolStack} mobile={mobile}>
          {/* Draw's controls lead the stack while it is up, and once there is ink, Copy Drawing at their foot. */}
          {drawing ? <ToolPanel id="drawing" label="Drawing controls" collapsible={false}
            footer={boardDrawing.drawing.hasContent ? <ToolPanelFooterButton label="Copy Drawing" shortcut={mobile ? "" : copyShortcut} onClick={copyDrawing} /> : null}>
            <DrawingToolbar drawing={boardDrawing.drawing} layout="panel" className="p-1" />
          </ToolPanel> : null}
          <BoardTreePanel index={inspector.index} documentKind={inspector.document} selection={inspector.selection} focusedFinding={inspector.focusedFinding}
            selectMode={inspector.selectMode} onSelectMode={inspector.setSelectMode} select={inspector.select} clear={inspector.clear}
            active={inspector.tool === BOARD_TOOL.SELECT} />
          <BoardReferencePanel inspector={inspector} active={inspector.tool === BOARD_TOOL.SELECT} onCopy={() => copySelection()} copyShortcut={mobile ? "" : copyShortcut} />
          <BoardMeasurePanel inspector={inspector} shown={inspector.tool === BOARD_TOOL.MEASURE || inspector.measurements.length > 0}
            onClose={() => { inspector.clearMeasure(); if (inspector.tool === BOARD_TOOL.MEASURE) inspector.chooseTool(BOARD_TOOL.SELECT); }} />
        </ToolColumn> : null}
        {payload.updating && !alert ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
          <ViewUpdateStatus status={words.updateStatus} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
        </div> : null}
        {/* The host's notice, top-right, once the plot is on screen: a rebuild, or a failed update the
            plot survives, keeps it there, as the 3D views do. */}
        <ViewportTopRight notice={shown && !payload.loading ? view.notice : null} belowStrip={boardChrome}>
          {inspector.available && !compact ? <QuickEdit key={file} className="self-stretch" hidden={chromeHidden}
            resource={workspace.resource} references={references} sketch={sketch}
            onCopy={copyAction} onEscape={() => inspector.escape()}
            onClear={() => { inspector.clear(); if (boardDrawing.drawing.hasContent) boardDrawing.drawing.clear(); }} disabled={!ready} /> : null}
        </ViewportTopRight>
        <ViewerLoadingOverlay loading={{ opening: payload.loading && !alert, progress: { label: words.reading } }}
          operationKey={file} />
        <ViewerAlertCard alert={cardAlert} hasContent={shown} dismissed={alertDismissal.dismissed} onDismiss={alertDismissal.dismiss} onReload={view.reload} file={file} />
      </div>
    </div>
  );
}

export default function PlotRenderer(props) {
  const { data, ...view } = props;
  return <PlotSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

import { useCallback, useMemo, useState } from "react";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import { useViewerHost } from "../../host/context.js";
import PlaneShell from "../kit/shell/PlaneShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { usePlaneFileView, usePlaneShell } from "../kit/shell/usePlaneShell.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { BoardDisplaySection, boardDisplayAirwires, boardDrawView, readBoardDisplay } from "./board/BoardDisplay.jsx";
import { BoardMeasurePanel, BoardReferencePanel, BoardTreePanel } from "./board/BoardPanels.jsx";
import FindingsList, { ChecksPanel, findingsAlert, splitFindings } from "./board/FindingsList.jsx";
import { BoardMeasureIcon, BoardSelectIcon } from "./board/boardModes.jsx";
import { useBoardHandover } from "./board/useBoardHandover.js";
import { readBoardIsolation, useBoardIsolation } from "./board/useBoardIsolation.js";
import { useBoardMeasure } from "./board/useBoardMeasure.js";
import { useBoardPicking } from "./board/useBoardPicking.js";
import { useBoardSelection } from "./board/useBoardSelection.js";
import { useCrossProbe } from "./board/useCrossProbe.js";
import { chromeStyle } from "./paperContrast.js";
import { PLOT_TOOL, PLOT_TOOL_MODES, escapePlot } from "./tools.js";
import { usePlotDocument } from "./usePlotDocument.js";
import { usePlotView } from "./usePlotView.js";

/**
 * A KiCad board or schematic, or a wiring harness, as the picture its own tool draws of it, on a
 * canvas (the payload comes from the BACKEND, `GET /__cad/plot`; nothing here parses KiCad's files).
 * Its frame is the flat views' shell (`kit/shell/usePlaneShell.js`). A board or a schematic whose
 * payload carries its index has the tools a person points with, speaking board references (`#U3`,
 * `#U3.9`, `#net:VIN`): Select (its tree and Reference), Quick Edit and the copy key, and on a board
 * Draw and Measure too, and its Display. A harness is the picture alone. Nothing here edits a design.
 */

// The file's slices: a board's Display and what is isolated, kept across rebuilds (a new shape gets a new signature).
const SLICES = Object.freeze({ board: "1", isolated: "1" });
const SELECT_PANEL = Object.freeze({ board: { id: "tree", label: "Board" }, schematic: { id: "tree", label: "Schematic" } });

function PlotSurface({ view, data }) {
  const host = useViewerHost();
  const mobile = useViewerMobile();
  const workspace = useWorkspaceDocument({ view, data });
  const document = usePlotDocument({ workspace, path: view.file.path });
  const { kind, index, words, layered } = document;

  // ---- the file's view: the plot's transform, a board's Display, what is isolated ----
  const [stored] = useState(() => readFileView(view.state, SLICES).renderer);
  const [display, setDisplay] = useState(() => readBoardDisplay(stored.board));
  const [restoredIsolation] = useState(() => readBoardIsolation(stored.isolated));
  const isolation = useBoardIsolation({ index, restored: restoredIsolation });
  const rendererState = useMemo(() => (kind === "board" || kind === "schematic" ? {
    signatures: kind === "board" ? SLICES : { isolated: SLICES.isolated },
    read: () => ({ ...(kind === "board" ? { board: display } : {}), isolated: { selectors: isolation.isolated } })
  } : null), [kind, display, isolation.isolated]);
  const fileView = usePlaneFileView({ view, rendererState });
  const shownDisplay = layered ? display : null;
  const drawView = useMemo(() => (shownDisplay ? boardDrawView(shownDisplay, document.sheet) : null), [shownDisplay, document.sheet]);
  const plotView = usePlotView({ plot: document.plot, restored: fileView.restored, colorScheme: view.appearance?.colorScheme === "dark" ? "dark" : "light",
    onViewMoved: fileView.rememberView, noun: words.noun, drawView });

  // ---- what a person points at ------------------------------------------------------
  const [toolMode, setToolMode] = useState(PLOT_TOOL_MODES.defaultMode);
  const selectTool = useCallback((mode) => setToolMode((current) => PLOT_TOOL_MODES.next(current, mode)), []);
  const selection = useBoardSelection({ index, requestPaint: plotView.requestPaint, toolMode, selectTool });
  const measure = useBoardMeasure({ index, toolMode, requestPaint: plotView.requestPaint });
  const handover = useBoardHandover({ workspace, document, selection, path: view.file.path });
  const { dropHover } = selection;
  const { capture: captureView } = plotView;
  // A capture is the view as it stands, without the hover under a pointer that has moved on to ask for it.
  const capture = useCallback(() => { dropHover(); return captureView(); }, [dropHover, captureView]);
  const escape = useMemo(() => ({
    active: Boolean(index && (selection.active || measure.start || toolMode === PLOT_TOOL.MEASURE)),
    handle: () => escapePlot({ toolMode, selectTool, selection, measure })
  }), [index, selection, measure, toolMode, selectTool]);
  // What KiCad and the review found: the errors are the card, as a STEP's alerts are; the rest are Select's Checks.
  const compact = Boolean(view.appearance?.compact);
  const findings = document.shown && !compact ? index?.findings ?? null : null;
  const { errors, suggestions } = useMemo(() => splitFindings(findings), [findings]);
  const reportAlert = useMemo(() => findingsAlert(errors), [errors]);

  const shell = usePlaneShell({
    view, services: workspace.services, resource: workspace.resource, modelKey: document.file, plane: plotView, load: document.load,
    words, toolModes: PLOT_TOOL_MODES, tool: { mode: toolMode, set: setToolMode }, live: handover.live, references: handover.references,
    selectionText: selection.selection.length ? handover.copyText : null, capture, escape, reportAlert, displayInView: layered
  });
  const { copyText } = shell;
  const { copyText: referenceText } = handover;
  const copyReferences = useCallback((selectors) => copyText(referenceText(selectors)), [copyText, referenceText]);
  const picking = useBoardPicking({ view: plotView, index, sheet: document.sheet, toolMode, selection, measure, isolated: isolation.resolved,
    side: shownDisplay?.side, placement: boardDisplayAirwires(shownDisplay), onCopy: copyReferences });
  // A board and its schematic open in two views select together, through the host (selection only).
  useCrossProbe({ port: host.crossProbe, path: view.file.path, index, selection, toolMode, view: plotView,
    layout: document.plot?.layout ?? null, mirrored: picking.mirrored });
  // A finding chosen in the card or in Checks selects what it names, as a tree row would, and puts away the card if one is up.
  const { select } = selection;
  const { dismissAlert } = shell;
  const chooseFinding = useCallback((finding) => {
    select(finding.items.map((item) => item.ref).filter(Boolean), { finding: finding.index });
    dismissAlert();
  }, [select, dismissAlert]);

  // ---- tools and panels: a board's Select, Draw and Measure; a schematic's Select ----
  const onBoard = index?.document === "board";
  const tools = index ? [
    shell.tools.own({ id: PLOT_TOOL.SELECT, label: "Select", panel: SELECT_PANEL[index.document],
      icon: <BoardSelectIcon mode={selection.selectMode} document={index.document} className="size-3.5" aria-hidden="true" /> }),
    ...(onBoard ? [shell.tools.draw, shell.tools.own({ id: PLOT_TOOL.MEASURE, label: "Measure",
      icon: <BoardMeasureIcon mode={measure.mode} className="size-3.5" aria-hidden="true" />,
      // A press while Measure is up clears it as it puts it down.
      onSelect: () => { if (toolMode === PLOT_TOOL.MEASURE) measure.clear(); selectTool(PLOT_TOOL.MEASURE); } })] : []),
  ] : [];
  const selecting = toolMode === PLOT_TOOL.SELECT;
  const copyShortcut = mobile ? "" : shell.frame.copyShortcut;
  const toolPanels = index ? <>
    <BoardTreePanel index={index} selection={selection.selection} isolated={isolation.isolated}
      selectMode={selection.selectMode} onSelectMode={selection.setSelectMode} select={select} hover={selection.hover}
      onIsolate={isolation.toggle} clear={selection.clear} active={selecting} />
    <BoardReferencePanel index={index} resolved={selection.resolved} finding={selection.finding} active={selecting}
      onClear={selection.clear} onSelect={select} onCopy={() => copyReferences(selection.selection)} copyShortcut={copyShortcut} />
    <ChecksPanel suggestions={suggestions} onChoose={chooseFinding} active={selecting} />
    <BoardMeasurePanel measure={measure} shown={toolMode === PLOT_TOOL.MEASURE || measure.measurements.length > 0}
      onClose={() => { measure.clear(); if (toolMode === PLOT_TOOL.MEASURE) selectTool(PLOT_TOOL.SELECT); }} />
  </> : null;

  return <PlaneShell shell={shell} surface="plot-surface" label={`${words.label}: ${view.file.name}`} interactive={Boolean(index)}
    tools={tools} toolPanels={toolPanels} onClearReferences={selection.clear}
    display={layered ? <BoardDisplaySection display={display} onChange={setDisplay} /> : null}
    reportBody={<FindingsList errors={errors} onChoose={chooseFinding} />}
    style={chromeStyle(document.plot?.layout.sheets, view.appearance?.colorScheme === "dark")} />;
}

export default function PlotRenderer(props) {
  const { data, ...view } = props;
  return <PlotSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

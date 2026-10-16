import { useCallback, useMemo, useState } from "react";
import { boardDisplayAirwires, boardDrawView } from "@text-to-cad/core/lib/plot2d/index.js";
import { useViewerMobile } from "../../file-viewer/responsive.js";
import PlaneShell from "../kit/shell/PlaneShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { usePlaneFileView, usePlaneShell } from "../kit/shell/usePlaneShell.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { BoardDisplaySection, readBoardDisplay } from "./board/BoardDisplay.jsx";
import { BoardReferencePanel, BoardTreePanel } from "./board/BoardPanels.jsx";
import { BoardSelectIcon } from "./board/boardModes.jsx";
import { useBoardHandover } from "./board/useBoardHandover.js";
import { readBoardIsolation, useBoardIsolation } from "./board/useBoardIsolation.js";
import { useBoardPicking } from "./board/useBoardPicking.js";
import { useBoardSelection } from "./board/useBoardSelection.js";
import { chromeStyle } from "./paperContrast.js";
import { PLOT_TOOL, PLOT_TOOL_MODES, escapePlot } from "./tools.js";
import { usePlotDocument } from "./usePlotDocument.js";
import { usePlotView } from "./usePlotView.js";

/**
 * A KiCad board as the picture drawn from its file, on a canvas (the payload comes from the BACKEND,
 * `GET /__cad/plot`; nothing here parses KiCad's files). Its frame is the flat views' shell
 * (`kit/shell/usePlaneShell.js`). A board whose payload carries its index has the one tool a person
 * points with, speaking board references (`#U3`, `#U3.9`, `#net:VIN`): Select (its tree and
 * Reference), with Quick Edit and the copy key, and its Display (the mode, the side, the pours and
 * the layers drawn). Neither Draw nor Measure is asked of the shell. A payload without an index is
 * the picture alone. Nothing here edits a design.
 */

// The file's slices: the board's Display and what is isolated, kept across rebuilds (a new shape gets a new signature).
const SLICES = Object.freeze({ board: "1", isolated: "1" });
const SELECT_PANEL = Object.freeze({ id: "tree", label: "Board" });

function PlotSurface({ view, data }) {
  const mobile = useViewerMobile();
  const workspace = useWorkspaceDocument({ view, data });
  const document = usePlotDocument({ workspace, path: view.file.path });
  const { index, words, layered } = document;

  // ---- the file's view: the plot's transform, the board's Display, what is isolated ----
  const [stored] = useState(() => readFileView(view.state, SLICES).renderer);
  const [display, setDisplay] = useState(() => readBoardDisplay(stored.board));
  const [restoredIsolation] = useState(() => readBoardIsolation(stored.isolated));
  const isolation = useBoardIsolation({ index, restored: restoredIsolation });
  const rendererState = useMemo(() => ({
    signatures: SLICES,
    read: () => ({ board: display, isolated: { selectors: isolation.isolated } })
  }), [display, isolation.isolated]);
  const fileView = usePlaneFileView({ view, rendererState });
  const shownDisplay = layered ? display : null;
  const drawView = useMemo(() => (shownDisplay ? boardDrawView(shownDisplay, document.sheet) : null), [shownDisplay, document.sheet]);
  const plotView = usePlotView({ plot: document.plot, restored: fileView.restored, colorScheme: view.appearance?.colorScheme === "dark" ? "dark" : "light",
    onViewMoved: fileView.rememberView, noun: words.noun, drawView });

  // ---- what a person points at ------------------------------------------------------
  // Select is the board's one tool; the shell's machine holds it so the strip reads as every file's.
  const [toolMode, setToolMode] = useState(PLOT_TOOL_MODES.defaultMode);
  const selection = useBoardSelection({ index, requestPaint: plotView.requestPaint });
  const handover = useBoardHandover({ workspace, document, selection, path: view.file.path });
  const { dropHover } = selection;
  const { capture: captureView } = plotView;
  // A capture is the view as it stands, without the hover under a pointer that has moved on to ask for it.
  const capture = useCallback(() => { dropHover(); return captureView(); }, [dropHover, captureView]);
  const escape = useMemo(() => ({
    active: Boolean(index && selection.active),
    handle: () => escapePlot({ selection })
  }), [index, selection]);

  const shell = usePlaneShell({
    view, services: workspace.services, resource: workspace.resource, modelKey: document.file, plane: plotView, load: document.load,
    words, toolModes: PLOT_TOOL_MODES, tool: { mode: toolMode, set: setToolMode }, live: handover.live, references: handover.references,
    selectionText: selection.selection.length ? handover.copyText : null, capture, escape, displayInView: layered
  });
  const { copyText } = shell;
  const { copyText: referenceText } = handover;
  const copyReferences = useCallback((selectors) => copyText(referenceText(selectors)), [copyText, referenceText]);
  useBoardPicking({ view: plotView, index, sheet: document.sheet, selection, isolated: isolation.resolved,
    side: shownDisplay?.side, placement: boardDisplayAirwires(shownDisplay), onCopy: copyReferences });
  const { select } = selection;

  // ---- the tool and its panels: Select, its tree and the Reference ----
  const tools = index ? [
    shell.tools.own({ id: PLOT_TOOL.SELECT, label: "Select", panel: SELECT_PANEL,
      icon: <BoardSelectIcon mode={selection.selectMode} className="size-3.5" aria-hidden="true" /> }),
  ] : [];
  const copyShortcut = mobile ? "" : shell.frame.copyShortcut;
  const toolPanels = index ? <>
    <BoardTreePanel index={index} selection={selection.selection} isolated={isolation.isolated}
      selectMode={selection.selectMode} onSelectMode={selection.setSelectMode} select={select} hover={selection.hover}
      onIsolate={isolation.toggle} clear={selection.clear} active />
    <BoardReferencePanel index={index} resolved={selection.resolved} active
      onClear={selection.clear} onSelect={select} onCopy={() => copyReferences(selection.selection)} copyShortcut={copyShortcut} />
  </> : null;

  return <PlaneShell shell={shell} surface="plot-surface" label={`${words.label}: ${view.file.name}`} interactive={Boolean(index)}
    tools={tools} toolPanels={toolPanels} onClearReferences={selection.clear}
    display={layered ? <BoardDisplaySection display={display} onChange={setDisplay} sheet={document.sheet} /> : null}
    style={chromeStyle(document.plot?.layout.sheets, view.appearance?.colorScheme === "dark")} />;
}

export default function PlotRenderer(props) {
  const { data, ...view } = props;
  return <PlotSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}

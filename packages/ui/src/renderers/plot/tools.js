import { createToolModes } from "../kit/tools/toolModes.js";

/**
 * A board's one tool is Select (`PlotRenderer.jsx`): the tree, the Reference, hover, net highlight,
 * copy reference and Quick Edit. Neither Draw nor Measure is mounted for a board — the shell keeps
 * both for the views that ask for them (`kit/shell/usePlaneShell.js`); the plot renderer asks for
 * neither. A board is read and pointed at here; what is to change, the agent changes in the script.
 */
export const PLOT_TOOL = Object.freeze({ SELECT: "select" });

// A plot opens in Select, and Select cannot be put down: the tool in hand is never saved.
export const PLOT_TOOL_MODES = createToolModes({
  defaultMode: PLOT_TOOL.SELECT,
  modes: { [PLOT_TOOL.SELECT]: {} }
});

/** Escape on a plot: the selection, when there is one. Answers whether it spent the key. */
export function escapePlot({ selection }) {
  if (selection.active) { selection.clear(); return true; }
  return false;
}

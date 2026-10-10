import { SHELL_TOOL, createToolModes } from "../kit/tools/toolModes.js";

/**
 * A board's tools are Select, Draw and Measure; a schematic's, Select alone; a harness has none
 * (`PlotRenderer.jsx`). Draw is the shell's (`kit/shell/usePlaneShell.js`).
 */
export const PLOT_TOOL = Object.freeze({ SELECT: "select", MEASURE: "measure", DRAW: SHELL_TOOL.DRAW });

// A plot opens in Select: the tool in hand is never saved. Measure and Draw toggle: a second press
// puts either down, back to Select (a press on Measure while it is up also clears its results, the
// board's own rule, in `PlotRenderer.jsx`).
export const PLOT_TOOL_MODES = createToolModes({
  defaultMode: PLOT_TOOL.SELECT,
  modes: { [PLOT_TOOL.SELECT]: {}, [PLOT_TOOL.MEASURE]: { toggles: true }, [PLOT_TOOL.DRAW]: { toggles: true } }
});

/**
 * Escape on a plot, innermost first, as on a STEP: an unfinished measurement, then Measure (its
 * results stay), then the selection and the check in focus. Answers whether it spent the key.
 */
export function escapePlot({ toolMode, selectTool, selection, measure }) {
  if (measure.start) { measure.cancel(); return true; }
  if (toolMode === PLOT_TOOL.MEASURE) { selectTool(PLOT_TOOL.SELECT); return true; }
  if (selection.active) { selection.clear(); return true; }
  return false;
}

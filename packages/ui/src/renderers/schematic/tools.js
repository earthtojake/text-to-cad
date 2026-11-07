import { SCHEMATIC_PICK_KINDS } from "@cad/core/lib/schematic2d/schematicIndex.js";
import { FLAT_TOOL } from "../kit/shell/useFlatView.js";
import { createToolModes } from "../kit/tools/toolModes.js";

// A schematic's tools are a board's (`../board/tools.js`): Select picks what is on the sheet, as KiCad's
// Selection Filter ticks it — a click the most specific thing under the pointer (a pin, a junction or a
// no-connect, a label, a wire, a symbol, a sheet symbol), what Quick Edit names (`divider.kicad_sch#R1.2`,
// `#net:/MID`, `#wire:<uuid>`, `#sheet:/Load/`), a click on nothing clearing; a drag the box between its
// ends, everything wholly inside it, as KiCad's window selection; a double-click on a sheet symbol enters
// its sheet. The view moves as every flat view's: a right or middle drag, or a drag with Ctrl, Cmd or
// Shift, or a trackpad's two-finger scroll, pans, a mouse's wheel or a pinch zooms, a double-click elsewhere fits;
// Pencil and Shapes draw on the sheet; Measure takes distances between points snapped to its pins' ends,
// its wires' ends, its junctions and its labels, in millimetres.
export const SCHEMATIC_TOOL = FLAT_TOOL;

export const SCHEMATIC_TOOL_MODES = createToolModes({
  defaultMode: SCHEMATIC_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(SCHEMATIC_TOOL).map(mode => [mode, {}]))
});

/** The kinds Select's filter ticks, KiCad's (`schematicIndex.js`'s `SCHEMATIC_PICK_KINDS`); All items ticks them all. */
export const SCHEMATIC_SELECT_KINDS = SCHEMATIC_PICK_KINDS;
/** The filter's grid, KiCad's two columns row by row: All items, then the kinds. */
export const SCHEMATIC_FILTER_GRID = Object.freeze([
  Object.freeze(["all"]), Object.freeze(["symbols", "pins"]), Object.freeze(["wires", "labels"]), Object.freeze(["sheets", "other"])
]);
/** A filter as Select holds it: the kinds it names, in the grid's order; not a list at all, every kind. */
export function readSchematicFilter(raw) {
  if (!Array.isArray(raw)) return SCHEMATIC_SELECT_KINDS;
  return SCHEMATIC_SELECT_KINDS.filter(id => raw.includes(id));
}

/** What a host command a schematic cannot carry out is told. */
export const SCHEMATIC_NO_CAMERA = "A schematic's sheet is drawn flat and head on: it has no camera to pose. "
  + "Zoom and pan it in the view, or call resetCamera to fit the sheet again.";
export const SCHEMATIC_NO_DISPLAY = "A schematic is drawn as KiCad draws it, in the viewer's light or dark theme: "
  + "it has no surfaces, lighting or render mode. Select a sheet's reference (#sheet:/Power/) to show that sheet.";

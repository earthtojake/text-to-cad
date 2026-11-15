import { FLAT_TOOL } from "../kit/shell/useFlatView.js";
import { createToolModes } from "../kit/tools/toolModes.js";

// A board's tools are a drawing's (`../dxf/tools.js`): Select picks what is on the board, as KiCad's
// Selection Filter ticks it (`boardPick.js`) — a click the most specific thing under the pointer, what
// Quick Edit names (`blinky.kicad_pcb#R1.2`, the pad 2 of R1; a track, a via, a zone, a rule area, a
// text, a dimension or a graphic by the uuid KiCad saved it with), a click on nothing clearing; a
// plain drag the box between its ends (every viewer's), taking what it touches as the filter does -- or,
// taking nothing, naming its area on the view's working layer (`#F.Cu@x10y5..x20y15`), Shift at its
// release adding — and the view moves under it as the 3D views' does: a right or middle
// drag, or a drag with Ctrl, Cmd or Shift, or a trackpad's two-finger scroll, pans, a mouse's wheel or a pinch zooms, a double-click fits;
// Pencil and Shapes draw on the board; Measure takes
// distances between points snapped to its pad, via and hole centres, its track ends and its
// outline's corners, in millimetres (a drag pans under it). Its view settings are its panel's Layers tab.
export const BOARD_TOOL = FLAT_TOOL;

export const BOARD_TOOL_MODES = createToolModes({
  defaultMode: BOARD_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(BOARD_TOOL).map(mode => [mode, {}]))
});

/**
 * What a board's drawing tools open with: the pen and Shapes in the palette's neon green
 * (`annotation/toolbar.jsx`'s `ANNOTATION_COLORS`), where every other view opens them in its neon red
 * (`CAD_ANNOTATION_DEFAULTS`). A board is mostly KiCad's red front copper, often a pour edge to edge: red
 * ink on it read by its keyline alone, a hairline at the fit. Of the palette, green is the one hue far from
 * both outer coppers (red, blue), the courtyards' magenta and the silkscreen's yellow, and it is not the
 * highlight's white or black; its keyline still edges it. The highlighter keeps its yellow, and a colour
 * the person picks is theirs, as in every view.
 */
const BOARD_INK = "#39ff14";
export const BOARD_ANNOTATION_DEFAULTS = Object.freeze({
  styles: Object.freeze({ pen: Object.freeze({ color: BOARD_INK }), shapes: Object.freeze({ color: BOARD_INK }) })
});

export {
  BOARD_DEFAULT_FILTER, BOARD_LOCKED, BOARD_SELECT_KINDS, boardFilterAll, boardPickKinds, boardWorkingLayer, readBoardFilter
} from "./boardPick.js";

/** What a host command a board cannot carry out is told. */
export const BOARD_NO_CAMERA = "This board is drawn flat and head on (2D): it has no camera to pose. "
  + "Zoom and pan it in the view, call resetCamera to fit the whole board again, or switch the view to 3D, whose camera setCamera poses.";
export const BOARD_NO_DISPLAY = "A board's Display (its mode, the side it is seen from, its copper pours and the layers drawn) "
  + "is the person's, set in the Layers tab of the view's panel; it has no surfaces, lighting or render mode.";

import { FLAT_TOOL } from "../kit/shell/useFlatView.js";
import { createToolModes } from "../kit/tools/toolModes.js";

// A board's tools are a drawing's (`../dxf/tools.js`): Select picks its pads, copper and parts, as
// its filter ticks them — what Quick Edit names (`blinky.kicad_pcb#R1.2`, the pad 2 of R1) — and is
// the view's hand: a drag pans, the wheel or a pinch zooms, a double-click fits; Pencil and Shapes
// draw on the board; Measure takes distances between points snapped to its pad, via and hole centres, its
// track ends and its outline's corners, in millimetres. Its one view control is its Display.
export const BOARD_TOOL = FLAT_TOOL;

export const BOARD_TOOL_MODES = createToolModes({
  defaultMode: BOARD_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(BOARD_TOOL).map(mode => [mode, {}]))
});

/** What Select's filter offers on a board, in the order its menu lists them. */
export const BOARD_SELECT_KINDS = Object.freeze(["parts", "pads", "nets"]);

/**
 * What a press may pick under a filter (the board index's `kinds`), or null for nothing. Each kind
 * ticked is one a press can take, the most specific under the pointer first: a pad, then copper
 * (a track or a via: the net's copper where it was pressed), then a part. Nets alone takes whole
 * nets: any copper under the pointer, a pad's or a pour's too, picks its net.
 * @param {readonly string[]} filter
 */
export function boardPickKinds(filter) {
  const parts = filter.includes("parts"), pads = filter.includes("pads"), nets = filter.includes("nets");
  if (!parts && !pads && !nets) return null;
  if (nets && !parts && !pads) return { pads: true, copper: true, parts: false, nets: true };
  return { pads, copper: nets, parts, nets: false };
}

/** What a host command a board cannot carry out is told. */
export const BOARD_NO_CAMERA = "A board is drawn flat and head on: it has no camera to pose. "
  + "Zoom and pan it in the view, or call resetCamera to fit the whole board again.";
export const BOARD_NO_DISPLAY = "A board's Display (its mode, the side it is seen from, its copper pours and the layers drawn) "
  + "is the person's, set in the view's Display menu and its Layers; it has no surfaces, lighting or render mode.";

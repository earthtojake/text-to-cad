/**
 * The canvas a board is painted on: the kit's plot view (`kit/viewport/usePlotView.js`), on KiCad's
 * board canvas.
 *
 * The whole pane is the board's background, the viewer's neutral dark grey (the plot's, the app's
 * dark `--background`), whatever the theme: KiCad draws a board on one dark canvas, which reaches
 * past the board.
 */
import { usePlotView } from "../kit/viewport/usePlotView.js";

/** The canvas around the board: the board's own background, before a board has loaded too. */
const KICAD_CANVAS = "#292929";
const surroundColor = (_scheme, plot) => plot?.layout.sheets[0]?.background || KICAD_CANVAS;

/** @param {Omit<Parameters<typeof usePlotView>[0], "surround" | "noun">} options */
export function useBoardView(options) {
  return usePlotView({ ...options, surround: surroundColor, noun: "board" });
}

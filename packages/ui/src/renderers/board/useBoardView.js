/**
 * The canvas a board is painted on: the kit's plot view (`kit/viewport/usePlotView.js` — the flat
 * view's pan, zoom, fit, tap, drag and hover, its rasters, its capture and its card's picture).
 *
 * The whole pane is the board's canvas in the view's theme (`plot2d/theme.js`'s `boardPalette`: the
 * app's light or dark `--background`), which reaches past the board as KiCad's does, and the board
 * is drawn in that theme's palette. A switch of theme draws the rasters again from the payload
 * already held: nothing is asked of the server.
 */
import { boardPalette } from "@cad/core/lib/plot2d/index.js";
import { usePlotView } from "../kit/viewport/usePlotView.js";

/** The canvas around the board, before a board has loaded too: the theme's (`plot2d/theme.js`). */
const surroundColor = (scheme) => boardPalette(scheme).background;

/** @param {Omit<Parameters<typeof usePlotView>[0], "surround" | "noun">} options */
export function useBoardView(options) {
  return usePlotView({ ...options, surround: surroundColor, noun: "board" });
}

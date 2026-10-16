/**
 * `cadgen pcb snapshot` in the page: a `GET /__cad/plot` payload — a KiCad board drawn from its
 * file, geometry per layer — fitted on a 2D canvas, as a PNG.
 *
 * This is the CLI half of the viewer's plot pane, and shares its whole drawing path
 * (`../lib/plot2d`): the same layout of the sheet, the same fit (drawing2d's), the same frame
 * (`drawPlot`: the sheet on KiCad's board background, the layers the board's Display chooses,
 * back to front, from the side it says), on the same theme surround. The job's `display` is the
 * board's Display contract (`plot2d/boardDisplay.js`: `mode`, `side`, `poured`, `layers`, with
 * the surround's `appearance`), read exactly as the pane reads it, so a snapshot draws what the
 * Display shows — Placement's pads and airwires included (`board2d/boardOverlay.js`). The pane
 * keeps rasters of a view so a pan costs nothing; this draws the geometry itself, once, which is
 * what those rasters are made of. So a CLI render cannot show what the pane cannot.
 *
 * The payload arrives over the snapshot host's loopback asset server rather than inside the
 * job, as a drawing's does: cadgen reads the board, caches the payload in the store and writes
 * the bytes to a file the page fetches. A large board's pours run to megabytes; inlined in the
 * job they would cross the Playwright driver pipe as one escaped protocol message.
 */
import { appThemeColors } from "../lib/appTheme.js";
import { createBoardIndex } from "../lib/board2d/boardIndex.js";
import { drawBoardOverlay } from "../lib/board2d/boardOverlay.js";
import { clearSurface } from "../lib/drawing2d/index.js";
import {
  boardDisplayAirwires, boardDrawView, drawPlot, fitPlotTransform, layoutPlot, readBoardDisplay
} from "../lib/plot2d/index.js";
import { paintOutput, renderOutputs, renderScale } from "./headlessCanvas.js";

/** One output's PNG: the plot fitted to it under the board's Display, on the appearance's background. */
function drawOutput(layout, display, { width, height, scale, background }) {
  const [sheet] = layout.sheets;
  const view = boardDrawView(display, sheet);
  return paintOutput({ width, height, scale }, (context) => {
    clearSurface(context, { width, height, pixelRatio: scale, background });
    const transform = fitPlotTransform(layout, width, height);
    drawPlot(context, layout, { transform, pixelRatio: scale, view });
    // Placement: the pads, their holes and every connection as an airwire, as the pane's overlay draws them.
    if (boardDisplayAirwires(display) && layout.board) {
      const index = createBoardIndex(layout.board, { x: sheet.x, y: sheet.y });
      const mirrorX = view.side === "bottom" ? sheet.x + sheet.width / 2 : null;
      drawBoardOverlay(context, index, { transform, pixelRatio: scale, width, height, placement: true, mirrorX });
    }
  });
}

/**
 * Render one resolved `plot` snapshot job.
 *
 * @param {object} job The resolved render job; `job.resolved.plotUrl` names the payload.
 * @returns {Promise<object>} The host's result shape: `{ ok, mode, outputs, warnings }`.
 */
export async function runHeadlessPlotJob(job) {
  const url = String(job?.resolved?.plotUrl || "");
  if (!url) {
    throw new Error(
      "a plot render job carries no plotUrl: cadgen resolves a board to its plot payload before "
      + "the page is asked to draw it"
    );
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`the plot payload could not be read (HTTP ${response.status} for ${url})`);
  }
  const layout = layoutPlot(await response.json());
  const display = readBoardDisplay(job?.display);
  const warnings = [];
  if (layout.unrouted) {
    // A true answer, and one a thin line in a PNG does not shout — or one the Display leaves out.
    const ratsnest = boardDrawView(display, layout.sheets[0]).layers.includes("ratsnest");
    warnings.push(
      `${layout.unrouted} connection${layout.unrouted === 1 ? " is" : "s are"} still unrouted: `
      + (ratsnest ? "the image draws each as a straight ratsnest line" : "the display leaves the ratsnest out of the image")
    );
  }
  const { background } = appThemeColors(job?.display?.appearance);
  const scale = renderScale(job);
  const transparent = job?.output?.transparent === true;
  const outputs = renderOutputs(job, (width, height) => drawOutput(layout, display, {
    width,
    height,
    scale,
    background: transparent ? null : background
  }));
  return {
    ok: true,
    mode: "view",
    appearance: job?.display?.appearance === "dark" ? "dark" : "light",
    sheetCount: layout.sheets.length,
    outputs,
    warnings
  };
}

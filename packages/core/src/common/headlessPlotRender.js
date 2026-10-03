/**
 * `cadgen pcb snapshot` in the page: a `GET /__cad/plot` payload — the SVG sheets a KiCad
 * board or schematic's own tool plots — fitted on a 2D canvas, as a PNG.
 *
 * This is the CLI half of the viewer's plot pane, and shares its whole drawing path
 * (`../lib/plot2d`): the same layout of the sheets, the same fit (drawing2d's), the same frame
 * (`drawPlot`: each sheet on its own background, its SVG over it), on the same theme surround.
 * The pane keeps rasters of the SVGs so a pan costs nothing; this draws the SVGs themselves,
 * once, which is what those rasters are made of. So a CLI render cannot show what the pane
 * cannot.
 *
 * The payload arrives over the snapshot host's loopback asset server rather than inside the
 * job, as a drawing's does: cadgen plots it with `kicad-cli`, caches it in the store and writes
 * the bytes to a file the page fetches. A board's SVG runs to tens of megabytes; inlined in the
 * job it would cross the Playwright driver pipe as one escaped protocol message.
 */
import { appThemeColors } from "../lib/appTheme.js";
import { clearSurface } from "../lib/drawing2d/index.js";
import { drawPlot, fitPlotTransform, layoutPlot, loadSheetImages, sheetImages } from "../lib/plot2d/index.js";
import { paintOutput, renderOutputs, renderScale } from "./headlessCanvas.js";

/** One output's PNG: the plot fitted to it, on the appearance's background. */
function drawOutput(layout, images, { width, height, scale, background }) {
  return paintOutput({ width, height, scale }, (context) => {
    clearSurface(context, { width, height, pixelRatio: scale, background });
    drawPlot(context, layout, {
      transform: fitPlotTransform(layout, width, height),
      pixelRatio: scale,
      images: sheetImages(layout, images)
    });
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
      "a plot render job carries no plotUrl: cadgen resolves a board or schematic to its plot "
      + "payload before the page is asked to draw it"
    );
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`the plot payload could not be read (HTTP ${response.status} for ${url})`);
  }
  const layout = layoutPlot(await response.json());
  const images = await loadSheetImages(layout);
  const warnings = [];
  if (layout.unrouted) {
    // A true answer, and one a thin grey line in a PNG does not shout.
    warnings.push(
      `${layout.unrouted} connection${layout.unrouted === 1 ? " is" : "s are"} still unrouted: `
      + "the image draws each as a straight ratsnest line"
    );
  }
  const { background } = appThemeColors(job?.display?.appearance);
  const scale = renderScale(job);
  const transparent = job?.output?.transparent === true;
  const outputs = renderOutputs(job, (width, height) => drawOutput(layout, images, {
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

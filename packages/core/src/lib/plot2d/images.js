/**
 * A plot's sheets as images the browser can draw: each SVG, decoded once.
 *
 * The browser is the SVG renderer — the same one in the viewer and in the snapshot bundle —
 * so an SVG becomes an `HTMLImageElement` over a `blob:` URL and is drawn with `drawImage`,
 * which rasterises the vector at whatever scale it lands at. As an image, an SVG runs no
 * script and loads nothing beside itself. The URL is revoked once the image has decoded: a
 * decoded image keeps its picture.
 *
 * The browser globals are injectable (`Image`, `URL`, `Blob`) so this module is exercised in
 * `node --test` with doubles and never drags a DOM into core's unit tests.
 */

function abortError() {
  return new DOMException("The plot's images were no longer wanted.", "AbortError");
}

/**
 * Decode every sheet's SVG, and every layer's of a board sheet: its picture and, where it has
 * one, its picture without pours.
 *
 * Throws — naming the sheet and the layer — on an SVG this browser cannot draw: a picture with
 * a sheet or a layer missing is worse than a picture that refuses to open.
 *
 * @param {import("./plot.js").PlotLayout} layout
 * @param {{ signal?: AbortSignal, Image?: any, URL?: any, Blob?: any }} [options]
 * @returns {Promise<(HTMLImageElement|import("./plot.js").PlotLayerImages[])[]>} One per sheet, in
 *   payload order: a schematic or harness sheet's image, or a board sheet's layers'
 *   `{ id, poured, unpoured }`, back to front.
 */
export async function loadSheetImages(layout, {
  signal,
  Image: ImageCtor = globalThis.Image,
  URL: Urls = globalThis.URL,
  Blob: BlobCtor = globalThis.Blob
} = {}) {
  if (typeof ImageCtor !== "function" || typeof Urls?.createObjectURL !== "function" || typeof BlobCtor !== "function") {
    throw new Error("Drawing a plot needs a browser: this runtime has no Image, Blob or URL.createObjectURL.");
  }
  signal?.throwIfAborted?.();
  const decode = async (svg, sheet, layer) => {
    const url = Urls.createObjectURL(new BlobCtor([svg], { type: "image/svg+xml" }));
    const image = new ImageCtor();
    image.decoding = "async";
    image.src = url;
    try {
      await image.decode();
    } catch (error) {
      if (signal?.aborted) throw abortError();
      const reason = error instanceof Error && error.message ? ` (${error.message})` : "";
      const which = layer ? `Layer ${layer} of sheet` : "Sheet";
      throw new Error(
        `${which} ${sheet.index + 1} of this plot${sheet.name ? `, “${sheet.name}”,` : ""} is not an SVG this `
        + `browser can draw${reason}.`
      );
    } finally {
      Urls.revokeObjectURL(url);
    }
    if (signal?.aborted) throw abortError();
    return image;
  };
  return Promise.all(layout.sheets.map((sheet) => {
    if (!sheet.layers) return decode(sheet.svg, sheet, null);
    return Promise.all(sheet.layers.map(async (layer) => {
      const [poured, unpoured] = await Promise.all([
        decode(layer.svg, sheet, layer.id),
        layer.unpoured ? decode(layer.unpoured, sheet, `${layer.id} (unpoured)`) : null
      ]);
      return { id: layer.id, poured, unpoured };
    }));
  }));
}

// A transmissive look is ONE fade, not two. A look that draws transmission (Render, the regular
// modes' kept finishes) shows the part at the alpha its file writes with the transmission
// (`transmittedOpacity`); a look that draws none (Flat, X-ray, a fill) shows it at the one preview
// alpha build123d's material setter infers (`previewOpacity`), and never both. The engine's are
// `formats/gltf.py`'s `preview_alpha` and `export/glb.py`'s `_alpha`; `previewOpacity.parity.json`
// holds the two languages to the same numbers.

const PREVIEW_FLOOR = 0.15;
const PREVIEW_SLOPE = 0.7;

/**
 * The alpha a transmissive look is drawn at with its transmission: its PBR `opacity` where that fades
 * it below 1 (an author's fade), else 1 -- a GLB's, as the engine writes it. Its colour's alpha says
 * nothing here: build123d's setter infers it from the transmission, and nothing tells that from a
 * colour set by hand.
 */
export function transmittedOpacity(opacity) {
  const value = Number(opacity);
  return opacity !== null && opacity !== undefined && opacity !== "" && Number.isFinite(value) && value < 1
    ? Math.max(value, 0) : 1;
}

/**
 * The alpha `alpha` (a file's, as `transmittedOpacity` gives it) previews at where a look draws no
 * transmission: at alpha 1, `max(0.15, 1 - 0.7 transmission)` to four places, as
 * `threejs_materials.PbrProperties.interpolate_color` infers; an alpha below 1, or a look that does not
 * transmit, is its own.
 */
export function previewOpacity(alpha, transmission) {
  const value = Number(alpha);
  const amount = Number(transmission);
  if (!(amount > 0) || !(value >= 1)) return value;
  return Math.round(Math.max(PREVIEW_FLOOR, 1 - PREVIEW_SLOPE * amount) * 1e4) / 1e4;
}

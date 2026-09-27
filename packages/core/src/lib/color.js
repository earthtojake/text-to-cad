// The sRGB transfer function, in one place, both directions.
//
// The pipeline's colour convention: everything upstream of a hex string is
// LINEAR. build123d `Color` and OCCT `Quantity_Color` are linear, so the
// descriptor's `occurrences[].color`, `components[].color`, a surf's
// `partColor`, and per-face colours are all linear floats. Everything that is
// a `#rrggbb` string is sRGB-ENCODED: that is what a colour picker shows, what
// a model's `baseColor` param holds, what three.js decodes with
// `new THREE.Color(hex)`, and what 3MF's `displaycolor` is specified to be.
//
// Crossing that boundary without applying the transfer function is silently
// wrong in exactly the places nobody tests: 0 and 1 are fixed points of the
// curve, so saturated primaries survive a missing conversion untouched and
// only the midtones drift (linear 0.5 encodes as 0xbc, not 0x80).

/** One sRGB-encoded channel (0..1) to linear. */
export function srgbToLinear(component) {
  return component <= 0.04045
    ? component / 12.92
    : ((component + 0.055) / 1.055) ** 2.4;
}

/** One linear channel (0..1) to sRGB-encoded. Inverse of `srgbToLinear`. */
export function linearToSrgb(component) {
  return component <= 0.0031308
    ? component * 12.92
    : 1.055 * component ** (1 / 2.4) - 0.055;
}

/** One linear channel to the 0..255 byte an sRGB hex string carries. */
export function linearChannelToSrgbByte(channel) {
  const clamped = Math.min(1, Math.max(0, Number(channel) || 0));
  return Math.round(Math.min(1, Math.max(0, linearToSrgb(clamped))) * 255);
}

/**
 * Linear RGB(A) floats to an sRGB `#rrggbb` string; alpha is dropped by design
 * (hex carries none, so opacity has to ride separately). Returns null when the
 * input is not at least a 3-channel array.
 */
export function linearRgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) {
    return null;
  }
  const hex = rgb
    .slice(0, 3)
    .map((channel) => linearChannelToSrgbByte(channel).toString(16).padStart(2, "0"))
    .join("");
  return `#${hex}`;
}

/**
 * The surface a drawing sheet lies on.
 *
 * A model hangs in a void, so the viewport's own backdrop suits it. A page does
 * not: white paper on near-black reads as a lit rectangle floating in space, and
 * a drop shadow on that ground is invisible. A document editor puts the page on a
 * desk a shade off the paper, which is what gives it an edge and a shadow. This
 * derives that desk from whatever the theme's backdrop is, so a themed viewer
 * keeps its character: a dark backdrop lifts toward the light, a light one settles.
 */

function parseHex(color) {
  const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(color || "").trim());
  if (!match) {
    return null;
  }
  const hex = match[1].length === 3 ? match[1].split("").map((c) => c + c).join("") : match[1];
  return [0, 2, 4].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
}

function toHex(rgb) {
  return `#${rgb.map((value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0")).join("")}`;
}

/** Perceived lightness, 0 to 1. */
export function backdropLuminance(color) {
  const rgb = parseHex(color);
  if (!rgb) {
    return 0;
  }
  return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
}

/**
 * @param {string} backdrop the viewport's own backdrop, as hex
 * @returns {string} the desk tone, or the backdrop unchanged when it cannot be read
 */
export function documentDeskColor(backdrop) {
  const rgb = parseHex(backdrop);
  if (!rgb) {
    return backdrop;
  }
  // Toward the light on a dark desk, toward the dark on a light one, and never far
  // enough to flip which side of the fence the theme is on.
  const towards = backdropLuminance(backdrop) < 0.5 ? 255 : 0;
  const amount = towards === 255 ? 0.14 : 0.07;
  return toHex(rgb.map((value) => value + (towards - value) * amount));
}

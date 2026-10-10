/**
 * A plot keeps its tool's colours whatever the theme. Where its paper is the other way round from
 * the theme (a schematic's light sheet in the dark, a board's dark one in the light), the tool panels
 * over it stand nearly opaque (`lib/floatingSurface.js` reads `--cad-chrome-alpha`).
 */

const CONTRASTING_CHROME_ALPHA = "90%";

/** Whether a `#rrggbb` colour is light (its relative luminance past half), or null for anything else. */
export function lightColour(hex) {
  const match = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || ""));
  if (!match) return null;
  const [r, g, b] = match.slice(1).map((part) => parseInt(part, 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5;
}

/**
 * The style the view's chrome takes over these sheets in this theme: the panels' alpha raised where
 * any sheet's paper is the other way round from the theme, nothing otherwise.
 *
 * @param {readonly { background?: string }[]|null|undefined} sheets
 * @param {boolean} dark  The theme is dark.
 */
export function chromeStyle(sheets, dark) {
  const against = (sheets || []).some((sheet) => {
    const light = lightColour(sheet.background);
    return light !== null && light === dark;
  });
  return against ? { "--cad-chrome-alpha": CONTRASTING_CHROME_ALPHA } : undefined;
}

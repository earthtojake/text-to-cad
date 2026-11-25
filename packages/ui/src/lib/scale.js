// THE scale's numbers, for what must count in pixels in script (a virtual list's row height, the phone strip's fit):
// the same values `styles/globals.css` sets as its tokens ("THE scale", and a phone's switch), which stay the one
// source for every drawn size. `scale.test.js` holds the two the same.
//
// Importing this module has no environmental effects.

/** A desktop's tokens (`--cad-*`), in px. */
export const DESKTOP_SCALE = Object.freeze({ control: 28, iconButton: 24, row: 28, rowSm: 24, chip: 20, glyph: 16, glyphSm: 14, pad: 8, step: 4, radiusControl: 4,
  switchH: 14, switchW: 24, thumb: 12, check: 14, text: Object.freeze([11, 12, 13, 15]) });
/** A phone's (the viewer under 600px), in px. */
export const PHONE_SCALE = Object.freeze({ control: 36, iconButton: 36, row: 36, rowSm: 36, chip: 28, glyph: 18, glyphSm: 16, pad: 10, step: 4, radiusControl: 6,
  switchH: 20, switchW: 36, thumb: 20, check: 20, text: Object.freeze([13, 14, 15, 17]) });
/** The scale in force for a view: a phone's or a desktop's. */
export const scaleFor = mobile => (mobile ? PHONE_SCALE : DESKTOP_SCALE);

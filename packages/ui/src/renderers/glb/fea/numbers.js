/**
 * Numbers as an FEA result's words say them, shared by the check kinds, the setup rows and the
 * verdict (`../feaResult.js`). Pure: no three.js, no React.
 */

/** A figure for a sentence: whole numbers from 10 up, two significant figures below. */
export function plainNumber(value) {
  const v = Number(value) || 0;
  return String(Math.abs(v) >= 10 ? Math.round(v) : Number(v.toPrecision(2)));
}

/** Three significant figures: a limit often under a millimetre, and 1.04 is not 1. */
export const threeFigures = (value) => String(Number(Number(value).toPrecision(3)));

/** A factor as the findings say it: floored, one decimal under 10, whole from 10 up. */
export function flooredFactor(value) {
  const v = Number(value) || 0;
  return String(v >= 10 ? Math.floor(v + 1e-9) : (Math.floor(v * 10 + 1e-9) / 10).toFixed(1));
}

/** Each half kept whole, so a narrow panel breaks the line at its comma. */
export const unbrokenHalves = (halves) => halves.map((half) => half.replace(/ /g, " ")).join(", ");

// The number field's arithmetic (`SliderValueField.jsx`): a value's text split into its number and its unit,
// what is typed read in the field's unit (another length or angle converted), and a number written back at
// the precision the field shows. Pure, so it is tested without a page.

const NUMBER = /^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(\s*)(.*?)\s*$/i;

/**
 * A value's text as the field draws it: the number (what is edited), the unit after it (drawn muted, never
 * edited) and the space between them ("7.3 mm": "7.3", " ", "mm"; "45°": "45", "", "°").
 * @param {string} text
 */
export function splitValueText(text) {
  const match = String(text ?? "").match(NUMBER);
  if (!match) return { number: String(text ?? "").trim(), space: "", unit: "" };
  return { number: match[1], space: match[3] ? match[2] || "" : "", unit: match[3] };
}

// How many millimetres, or degrees, one of each unit is. A field's unit and a typed one of the same family
// convert; any other typed unit is unknown.
const FAMILIES = [
  { µm: 0.001, um: 0.001, mm: 1, cm: 10, m: 1000, km: 1e6, in: 25.4, "\"": 25.4, inch: 25.4, inches: 25.4, ft: 304.8, "'": 304.8, feet: 304.8, foot: 304.8 },
  { "°": 1, deg: 1, degree: 1, degrees: 1, rad: 180 / Math.PI, rads: 180 / Math.PI, radian: 180 / Math.PI, radians: 180 / Math.PI },
];
const factorOf = unit => {
  const key = String(unit || "").trim().toLowerCase();
  for (const family of FAMILIES) if (Object.hasOwn(family, key)) return { family, factor: family[key] };
  return null;
};

/** Whether `unit` is a length the field converts other lengths into. */
export const isLengthUnit = unit => factorOf(unit)?.family === FAMILIES[0];

/**
 * What is typed, read in the field's `unit`: `{ kind: "number", value }` (a typed length in another unit
 * converted when the field's is a length, an angle likewise), `{ kind: "unit", unit }` for a unit the
 * field does not take, `{ kind: "invalid" }` for no number at all.
 * @param {string} draft @param {string} unit
 */
export function readTyped(draft, unit = "") {
  const match = String(draft ?? "").match(NUMBER);
  if (!match) return { kind: "invalid" };
  const value = Number(match[1]);
  if (!Number.isFinite(value)) return { kind: "invalid" };
  const typed = match[3].trim();
  const own = String(unit || "").trim();
  if (!typed || typed.toLowerCase() === own.toLowerCase()) return { kind: "number", value };
  const from = factorOf(typed), to = factorOf(own);
  if (from && to && from.family === to.family) return { kind: "number", value: Number(((value * from.factor) / to.factor).toPrecision(12)) };
  return { kind: "unit", unit: typed };
}

/** The decimals a number's text, or a step, is written with ("0.05": 2, "7": 0, "1e-3": 3). */
export function decimalsOf(value) {
  const text = String(value ?? "");
  const exponent = text.match(/e-(\d+)$/i);
  if (exponent) return Number(exponent[1]) + (text.split("e")[0].split(".")[1]?.length || 0);
  return text.split(".")[1]?.length || 0;
}

/** `value` at `decimals`, with nothing after the point that says nothing more ("9.000" at 0 decimals: "9"). */
export function formatNumber(value, decimals) {
  const fixed = Number(value).toFixed(Math.max(0, Math.min(10, decimals)));
  return fixed === "-0" || /^-0\.0*$/.test(fixed) ? fixed.slice(1) : fixed;
}

/** `value` within `[min, max]` (either may be unbounded). */
export const clampNumber = (value, min, max) => Math.min(Math.max(value, Number.isFinite(min) ? min : -Infinity), Number.isFinite(max) ? max : Infinity);

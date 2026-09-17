// The two numeric guards every scene module needs, in one place.
//
// `clamp` and a finite-or-fallback coercion were being re-declared privately
// in module after module; identical four-line copies are how two of them
// quietly stop agreeing about what a non-number is.

/** Constrain a number to [min, max]. NaN in, NaN out — coerce first. */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

/**
 * The value when it is a finite number, otherwise the fallback. Strings and
 * null are rejected rather than coerced: a scene control that accepts "2" has
 * a validation hole upstream, not a conversion need here.
 */
export function finiteOr(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

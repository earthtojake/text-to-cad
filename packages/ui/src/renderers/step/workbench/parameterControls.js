const DEFAULT_NUMBER_CONTROL_STEP = 0.01;
const MIN_NUMBER_CONTROL_STEP = 0.000001;
const TARGET_NUMBER_SLIDER_STEPS = 1000;

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function compactNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? Number(numericValue.toPrecision(12))
    : DEFAULT_NUMBER_CONTROL_STEP;
}

// A slider's step from its range: about a thousand steps across it, never coarser than a
// hundredth, so a control over a few degrees and one over thousands both drag finely.
export function resolveParameterNumberControlStep(control) {
  const min = toFiniteNumber(control?.min, 0);
  const max = toFiniteNumber(control?.max, min);
  const range = Math.abs(max - min);
  const rangeStep = range > 0
    ? Math.max(
        10 ** Math.floor(Math.log10(range / TARGET_NUMBER_SLIDER_STEPS)),
        MIN_NUMBER_CONTROL_STEP
      )
    : DEFAULT_NUMBER_CONTROL_STEP;
  return compactNumber(rangeStep);
}

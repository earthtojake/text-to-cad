// How a generic parameter's number reads and steps, for every panel that shows parameters as rows
// (`parameterRow.jsx`): Position's joints and an FEA result's controls. Pure, so a node test can
// import it with no React.

const DEFAULT_NUMBER_CONTROL_STEP = 0.01;
const MIN_NUMBER_CONTROL_STEP = 0.000001;
const TARGET_NUMBER_SLIDER_STEPS = 1000;

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function positiveNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0;
}

function compactNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? Number(numericValue.toPrecision(12))
    : DEFAULT_NUMBER_CONTROL_STEP;
}

/** A slider's step: about a thousandth of its range, a power of ten, finer than any declared step. */
export function resolveParameterNumberControlStep(parameter) {
  const declaredStep = positiveNumber(parameter?.step);
  const min = toFiniteNumber(parameter?.min, 0);
  const max = toFiniteNumber(parameter?.max, min);
  const range = Math.abs(max - min);
  const rangeStep = range > 0
    ? Math.max(
        10 ** Math.floor(Math.log10(range / TARGET_NUMBER_SLIDER_STEPS)),
        MIN_NUMBER_CONTROL_STEP
      )
    : DEFAULT_NUMBER_CONTROL_STEP;
  return compactNumber(declaredStep > 0 ? Math.min(declaredStep, rangeStep) : rangeStep);
}

/** A number in a compact value field: whole from 100, one decimal from 10, two below. */
export function formatControlNumber(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0";
  }
  if (Math.abs(numericValue) >= 100) {
    return numericValue.toFixed(0);
  }
  if (Math.abs(numericValue) >= 10) {
    return numericValue.toFixed(1);
  }
  return numericValue.toFixed(2);
}

/** A value's unit as its compact field shows it: degrees as the sign ("90.0°"), others after a space. */
export function unitSuffix(unit) {
  const text = String(unit || "").trim();
  return !text ? "" : /^(deg|degrees?|°)$/i.test(text) ? "°" : ` ${text}`;
}

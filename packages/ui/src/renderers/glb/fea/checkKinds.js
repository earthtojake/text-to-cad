/**
 * The check kinds a static result's verdict can judge, in plain words: the peak stress against the
 * yield and the largest displacement against a limit. Each kind says what its headline is when it is
 * the only check (`titles`, by status), the name a check without a label of its own takes
 * (`defaultLabel`), its unit, how a value is written (`figure`) and its row line (`line`: its value
 * against its limit). Both move with the load the viewer's load control sets, k times at k times it.
 *
 * A check here is the verdict's: the file's check (`kind`, `label`, `value`, `limit`, `unit`, `ratio`,
 * `margin`) judged at the load shown, with `shown` its value at that load and `times`, how many times
 * this load it takes to reach its limit. Pure data and functions: no three.js, no React.
 */
import { flooredFactor, plainNumber, threeFigures, unbrokenHalves } from "./numbers.js";

const titles = (fails, close, passes) => Object.freeze({ fails, close, passes });

/** What this many times the load means: "OK up to 1.6× this load", "OK only to 0.4× this load" (floored, so it never overstates). */
export function loadCaption(times) {
  return `OK ${times < 1 ? "only to" : "up to"} ${flooredFactor(times)}× this load`;
}

/**
 * A check's line from its lead word: "Peak 405 MPa, limit 276 MPa". The verdict's row, whose label
 * says what it is, drops it (`bare`: "405 MPa, limit 276 MPa").
 */
const peakLine = (lead, unit, figure = plainNumber) => (check, { bare = false } = {}) => {
  const u = check.unit || unit;
  const value = `${figure(check.shown)} ${u}`;
  return unbrokenHalves([bare ? value : `${lead} ${value}`, `limit ${figure(check.limit)} ${u}`]);
};

export const CHECK_KINDS = Object.freeze({
  // The peak von Mises stress against the yield; how far it is from yield is the safety factor.
  stress: Object.freeze({
    titles: titles("Too weak", "Close to the limit", "Strong enough"), defaultLabel: "Strength", unit: "MPa", figure: plainNumber,
    line: peakLine("Peak", "MPa"),
  }),
  displacement: Object.freeze({
    titles: titles("Moves too much", "Close to the limit", "Stiff enough"), defaultLabel: "Displacement", unit: "mm",
    // A displacement keeps three figures: its limit is often under a millimetre, and 1.04 is not 1.
    figure: threeFigures, line: peakLine("Moves", "mm", threeFigures),
  }),
});

/** Every check kind cadgen judges, and so this viewer: a result with a check of any other kind does not read. */
export const FEA_CHECK_KINDS = Object.freeze(Object.keys(CHECK_KINDS));

/** A check's headline when it is the only one, at its status: "Too weak", "Stiff enough". */
export function checkTitle(check, status) {
  return CHECK_KINDS[check.kind].titles[status];
}

/** A check's name: its own label, else the kind's. */
export function checkLabel(check) {
  return check.label || CHECK_KINDS[check.kind].defaultLabel;
}

/**
 * A check's line, its value against its limit, each half kept whole: "405 MPa, limit 276 MPa" bare
 * (the verdict's row, its label saying what it is), "Peak 405 MPa, limit 276 MPa" in a sentence.
 */
export function checkLine(check, { bare = false } = {}) {
  return CHECK_KINDS[check.kind].line(check, { bare });
}

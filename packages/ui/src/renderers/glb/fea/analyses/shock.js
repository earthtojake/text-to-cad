/**
 * Shock: the peak response of a held part to a shock given as a shock response spectrum (SRS).
 * Each mode's peak comes from the spectrum at its own frequency, and the modes are combined (SRSS,
 * or CQC for modes close together), so its result is two envelopes, no series: the peak von Mises
 * stress and the peak displacement relative to where it is held. Its verdict judges stress
 * (labelled "Shock") and displacement, both k times larger at k times this shock. What you see is
 * the field and the deformation; it plays no routine (a spectrum gives peaks, not a time history).
 * Its setup says where it is held, the shock ("Shocked": the spectrum in a line, "50 g above
 * 100 Hz along Z, 5% damping", how the modes were combined its hint) and what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber, threeFigures } from "../numbers.js";
import { axisWords, heldRows, madeOfRows, wholeRefs } from "../setup.js";

const finite = (value) => typeof value === "number" && Number.isFinite(value);

/** The spectrum's rows, [Hz, g] with both positive and the frequencies rising; [] for anything else. */
function spectrumRows(table) {
  if (!Array.isArray(table)) return [];
  const rows = table.filter((row) => Array.isArray(row) && row.length === 2 && finite(row[0]) && finite(row[1]) && row[0] > 0 && row[1] > 0);
  return rows.length === table.length && rows.every((row, index) => index === 0 || row[0] > rows[index - 1][0]) ? rows : [];
}

/**
 * A spectrum's level in words, by its highest plateau: "50 g above 100 Hz" (flat to its top),
 * "50 g from 10 to 2000 Hz" (flat throughout), "50 g up to 400 Hz", "50 g from 100 to 1000 Hz",
 * "up to 30 g at 400 Hz" (a single peak). "" for no table.
 */
export function spectrumLevel(table) {
  const rows = spectrumRows(table);
  if (!rows.length) return "";
  const peak = Math.max(...rows.map((row) => row[1]));
  const atPeak = rows.map((row) => row[1] >= peak * (1 - 1e-9));
  const first = atPeak.indexOf(true);
  let last = first;
  while (last + 1 < rows.length && atPeak[last + 1]) last += 1;
  const g = `${threeFigures(peak)} g`;
  const [from, to] = [plainNumber(rows[first][0]), plainNumber(rows[last][0])];
  if (first === last) return `up to ${g} at ${from} Hz`;
  if (last === rows.length - 1 && first > 0) return `${g} above ${from} Hz`;
  if (first === 0 && last < rows.length - 1) return `${g} up to ${to} Hz`;
  return `${g} from ${from} to ${to} Hz`;
}

/** The whole spectrum in a line: "50 g above 100 Hz along Z, 5% damping" (the read study's `srs`, or the file's own). "" for no table. */
export function spectrumWords(srs) {
  const level = spectrumLevel(srs?.table);
  if (!level) return "";
  const along = Array.isArray(srs.direction) && srs.direction.length === 3 && srs.direction.every(finite) ? axisWords(srs.direction) : "";
  const ratio = finite(srs.dampingRatio) ? srs.dampingRatio : srs.damping_ratio;
  const damping = finite(ratio) ? `, ${plainNumber(ratio * 100)}% damping` : "";
  return `${level}${along ? ` along ${along}` : ""}${damping}`;
}

/**
 * Study's "Shocked", under a wave: the spectrum in a line, how the modes were combined its hint,
 * chosen with every fixed face (where the shock comes in). [] for a file with no spectrum.
 */
export function shockedRows(result) {
  const study = result.study || {};
  const label = spectrumWords(study.srs);
  if (!label) return [];
  const combination = study.combination === "cqc" ? "CQC" : study.combination === "srss" ? "SRSS" : "";
  const faces = (result.study?.fixtures || []).flatMap((fixture) => fixture.faces);
  const refs = faces.length ? { faces } : wholeRefs(result).length ? { refs: wholeRefs(result) } : null;
  return [{ id: "shocked", label: "Shocked", detail: "", glyph: "wave", children: [{ id: "shocked:0", label, detail: "", wrap: true,
    ...(combination ? { hint: `Modes combined by ${combination}` } : {}),
    ...(refs ? { ...refs, summary: `Shocked where it is held: ${label}` } : {}) }] }];
}

export default Object.freeze({
  name: "shock",
  tier: 1,
  word: "Shock",
  noun: "this shock",
  family: null,
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["stress", "displacement"]),
  checkLabels: Object.freeze({ stress: "Shock" }),
  defaultControls: fieldAndDeformation,
  setupGroups: Object.freeze([heldRows, shockedRows, madeOfRows]),
  routine: () => null,
  markers: Object.freeze(["fixture", "base_excitation"]),
  displayTitle: "Shaker and fixtures",
  limitWord: "",
});

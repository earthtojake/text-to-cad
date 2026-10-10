/**
 * Random vibration: the part's response to a random shake given as a PSD (a transport or MIL-STD
 * profile in g²/Hz), shaken where it is held. Its fields are RMS, one standard deviation (Stress
 * (1σ), Displacement (1σ)); the Sigma control shows them at 1σ or 3σ, opening on the level the
 * study judges at. Its verdict judges stress (labelled "Random vibration") and displacement at that
 * level, both k times larger at k times this shake. Nothing deforms (an RMS has no sign) and it
 * plays no routine. Its setup says where it is held, how hard it is shaken ("6.1 g rms along Z, 20
 * to 2000 Hz") and what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { sigmaControl } from "../series.js";
import { axisWords, heldRows, madeOfRows, wholeRefs } from "../setup.js";

/** The field select over every field (stress first), then the Sigma level; the field alone for a result with no RMS field. */
export function fieldAndSigma(result) {
  const field = fieldAndDeformation(result)[0];
  const sigma = sigmaControl(result);
  return sigma ? [field, sigma] : [field];
}

/** A PSD table's g rms: the area under its straight lines on log-log axes, each segment exactly. */
export function psdGrms(table) {
  let area = 0;
  for (let i = 0; i + 1 < table.length; i += 1) {
    const [f0, p0] = table[i];
    const [f1, p1] = table[i + 1];
    const ratio = Math.log(f1 / f0);
    const exponent = Math.log(p1 / p0) / ratio + 1;
    area += p0 * f0 * (Math.abs(exponent * ratio) < 1e-12 ? ratio : Math.expm1(exponent * ratio) / exponent);
  }
  return Math.sqrt(area);
}

/** The study's PSD as the file echoes it: its rows, its g rms and its direction; null for none. */
export function psdOf(result) {
  const psd = result.mesh?.userData?.study?.psd;
  const table = Array.isArray(psd?.table)
    ? psd.table.filter((row) => Array.isArray(row) && row.length === 2 && row.every((value) => Number.isFinite(value) && value > 0)) : [];
  if (table.length < 2) return null;
  const grms = Number.isFinite(psd.grms) && psd.grms > 0 ? psd.grms : psdGrms(table);
  return { table, grms, direction: result.study?.excitation?.direction || null };
}

/** The PSD in words: "6.1 g rms along Z, 20 to 2000 Hz". "" for none. */
export function psdWords(psd) {
  if (!psd) return "";
  const along = psd.direction ? ` along ${axisWords(psd.direction)}` : "";
  return `${plainNumber(psd.grms)} g rms${along}, ${plainNumber(psd.table[0][0])} to ${plainNumber(psd.table[psd.table.length - 1][0])} Hz`;
}

/** Study's "Shaken", under a wave: the PSD summarised, chosen with every fixed face; the level judged at its hint. */
export function shakenAtRandomRows(result) {
  const psd = psdOf(result);
  if (!psd) return [];
  const label = psdWords(psd);
  const sigma = result.study?.sigma;
  const faces = result.study.fixtures.flatMap((fixture) => fixture.faces);
  const refs = faces.length ? { faces } : wholeRefs(result).length ? { refs: wholeRefs(result) } : null;
  return [{ id: "shaken", label: "Shaken", detail: "", glyph: "wave", children: [{ id: "shaken:0", label, detail: "", wrap: true,
    hint: `At random, a ${psd.table.length}-point PSD${sigma ? `, judged at ${sigma}σ` : ""}`,
    ...(refs ? { ...refs, summary: `Shaken at random where it is held: ${label}` } : {}) }] }];
}

export default Object.freeze({
  name: "random_vibration",
  tier: 1,
  word: "Random vibration",
  noun: "this shake",
  family: null,
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["stress", "displacement"]),
  checkLabels: Object.freeze({ stress: "Random vibration" }),
  defaultControls: fieldAndSigma,
  setupGroups: Object.freeze([heldRows, shakenAtRandomRows, madeOfRows]),
  routine: () => null,
  markers: Object.freeze(["fixture", "base_excitation"]),
  displayTitle: "Shaker and fixtures",
  limitWord: "",
});

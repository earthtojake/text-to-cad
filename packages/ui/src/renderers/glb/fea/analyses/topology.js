/**
 * Lighten it (lite): topology optimisation, where the material should go, Tier 3. Its series is the
 * design over the iterations ("Iteration 12" ... "Final design"), opening on the final design. Its
 * verdict judges the mass saved ("Saves 62 % of the mass, needs 25 %"), and the stress and the
 * displacement of the verified design (the thresholded design solved as a static part); none moves
 * with a load control. Its takeaway leads with "Lite · "; Details lists its limits. What you see
 * opens on the iteration scrubber, the field (Material kept first) and a "Show above" threshold at
 * 0.5 on the material kept, so the material that goes is drawn grey; its routine plays the design
 * forming. Its setup: held at, pushed, then "Lighten" ("Keep 30% of the material", "Kept solid:
 * face 2, face 7") and made of.
 */
import { fieldOptions } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { frameControl } from "../series.js";
import { faceLabel, heldRows, madeOfRows, pushedRows, wholeRefs } from "../setup.js";
import { routineOf } from "./stub.js";

/** The design forming: the iterations one after another, interpolated (GlbRenderer plays a series this way). */
export const FORMING = routineOf("Watch it form", "play");

/** The field a lightened design is shown by: its density, 1 where the material stays. */
export const MATERIAL_KEPT = "_material_kept";

/** "Keep 30% of the material" from a share (0.3); "" for none. */
export function keepWords(fraction) {
  if (!Number.isFinite(fraction) || !(fraction > 0)) return "";
  return `Keep ${plainNumber(fraction * 100)}% of the material`;
}

/** "Kept solid: face 2, face 7" from the faces whose nearby material stays; "" for none. */
export function keptSolidWords(refs) {
  if (!refs?.length) return "";
  return `Kept solid: ${refs.map((ref) => faceLabel(ref).toLowerCase()).join(", ")}`;
}

/** Study's "Lighten": the share of the material to keep, and the faces kept solid (the fixtures, loads and holes among them). */
export function lightenRows(result) {
  const study = result.study || {};
  const rows = [];
  const keep = keepWords(study.volumeFraction);
  const refs = wholeRefs(result);
  if (keep) rows.push({ id: "lighten:keep", label: keep, detail: "", wrap: true, ...(refs.length ? { refs, summary: keep } : {}) });
  const kept = study.keptSolid || [];
  const solid = keptSolidWords(kept);
  if (solid) {
    rows.push({ id: "lighten:solid", label: solid, detail: "", wrap: true, faces: kept, summary: solid,
      hint: "The material near these faces stays: fixtures, loads, bolt holes and the faces the study keeps" });
  }
  return rows.length ? [{ id: "lighten", label: "Lighten", detail: "", glyph: "material", children: rows }] : [];
}

export const TOPOLOGY_SETUP = Object.freeze([heldRows, pushedRows, lightenRows, madeOfRows]);

/**
 * What you see with no view: the iteration scrubber (on the final design), the field (Material kept
 * first, then the verified design's stress and displacement), and "Show above" 0.5 on the material
 * kept, which draws the material that goes grey.
 */
export function topologyControls(result) {
  const every = result.fields.map((entry) => entry.attribute);
  const ordered = [MATERIAL_KEPT, ...every.filter((attribute) => attribute !== MATERIAL_KEPT)];
  const options = fieldOptions(result, ordered);
  const controls = [];
  const frames = frameControl(result, "frame", { label: "Iteration" });
  if (frames) controls.push(frames);
  if (options.length) {
    controls.push({ id: "field", drives: "field", type: "enum", label: "Field", ariaLabel: "Result field", hideLabel: true, options,
      defaultValue: options[0].value });
  }
  if (result.fields.some((entry) => entry.attribute === MATERIAL_KEPT)) {
    controls.push({ id: "threshold", drives: "threshold", type: "number", label: "Show above", min: 0, max: 1, step: 0.05,
      defaultValue: 0.5, unit: "", field: MATERIAL_KEPT });
  }
  return controls;
}

export default Object.freeze({
  name: "topology",
  tier: 3,
  word: "Lighten it",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["mass_saved", "stress", "displacement"]),
  checkLabels: Object.freeze({}),
  defaultControls: topologyControls,
  setupGroups: TOPOLOGY_SETUP,
  routine: (result) => (result?.series ? FORMING : null),
  markers: Object.freeze(["load", "fixture"]),
  displayTitle: "Loads and fixtures",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway.
  limitWord: "Lite",
});

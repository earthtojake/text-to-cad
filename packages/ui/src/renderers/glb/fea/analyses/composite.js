/**
 * Composite (lite): a laminated plate judged ply by ply, Tier 3. Its verdict judges the worst ply
 * against a failure index of 1 (Tsai-Wu or max stress, the larger: "Worst ply 3 (+45°), failure
 * index 0.82") and the displacement; neither follows a load control (a Tsai-Wu index is not
 * proportional to the load). Its takeaway leads with "Lite · "; Details lists its limits. What
 * you see is the field (failure index, the ply envelope's stress, displacement) and the
 * deformation. Its setup: held at, pushed, and the layup ("4 plies, [0/90]s, 2 mm"), the ply
 * materials its hint, read from the study the viewer read (`result.study.layup`).
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { heldRows, pushedRows, wholeRefs } from "../setup.js";

/** A layup's angles in the short form, bottom ply first: "[0/90]s" for a symmetric one, else "[0/45/-45/90]". */
export function layupNotation(plies) {
  const angles = plies.map((ply) => plainNumber(Number(ply.angle_deg) || 0));
  const same = (a, b) => a.material === b.material && a.angle_deg === b.angle_deg && a.thickness_mm === b.thickness_mm;
  const symmetric = plies.length >= 2 && plies.length % 2 === 0 && plies.every((ply, i) => same(ply, plies[plies.length - 1 - i]));
  return symmetric ? `[${angles.slice(0, plies.length / 2).join("/")}]s` : `[${angles.join("/")}]`;
}

/** The layup the result was solved with, from the study the viewer read (`study.layup`): `plies`, `notation`, `thicknessMm`. null for none. */
export function readLayup(result) {
  const layup = result?.study?.layup;
  const plies = layup?.plies || [];
  if (!plies.length) return null;
  const thickness = layup.thicknessMm ?? plies.reduce((sum, ply) => sum + ply.thickness_mm, 0);
  return { plies, notation: layup.notation || layupNotation(plies), thicknessMm: thickness };
}

/** Its words: "4 plies, [0/90]s, 2 mm". */
export function layupWords(layup) {
  const count = layup.plies.length;
  return `${count} ${count === 1 ? "ply" : "plies"}, ${layup.notation}, ${plainNumber(layup.thicknessMm)} mm`;
}

/** Study's "Layup": one row, the plies' count, angles and thickness, the ply materials its hint. */
export function layupRows(result) {
  const layup = readLayup(result);
  if (!layup) return [];
  const label = layupWords(layup);
  const materials = [...new Set(layup.plies.map((ply) => String(ply.material || "")).filter(Boolean))];
  const refs = wholeRefs(result);
  return [{ id: "layup", label: "Layup", detail: "", glyph: "material", children: [{ id: "layup:0", label, detail: "", wrap: true,
    ...(materials.length ? { hint: materials.join(", ") } : {}),
    ...(refs.length ? { refs, summary: `Layup ${label}${materials.length ? ` of ${materials.join(", ")}` : ""}` } : {}) }] }];
}

export const COMPOSITE_SETUP = Object.freeze([heldRows, pushedRows, layupRows]);

export default Object.freeze({
  name: "composite",
  tier: 3,
  word: "Composite",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["ply_failure", "displacement"]),
  checkLabels: Object.freeze({}),
  defaultControls: fieldAndDeformation,
  setupGroups: COMPOSITE_SETUP,
  routine: () => null,
  markers: Object.freeze(["load", "fixture", "body_load"]),
  displayTitle: "Loads and fixtures",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway.
  limitWord: "Lite",
});

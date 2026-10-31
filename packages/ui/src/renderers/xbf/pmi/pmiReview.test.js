// What the PMI section reviews a requirement by (`pmiReview.js`): a dimension's limits from its
// signed deviations, or those it was given, and none without a tolerance; the requirements on a
// face; a frame's datums and a datum's users, each on the annotation's own part.
import assert from "node:assert/strict";
import test from "node:test";
import { datumDependents, datumRelationships, dimensionLimits, featureRequirements } from "./pmiReview.js";

const datum = { id: "A", part: 0, kind: "datum", datum: { letter: "A" }, status: "ok", supported: true,
  featureIds: ["i0/face/1"], refs: [{ ref: "bracket/f:base", status: "ok" }] };
const diameter = { id: "bore", part: 0, kind: "dimension", status: "ok", supported: true,
  dimension: { type: "diameter", nominal: 10, unit: "mm", tolerance: { lower: 0, upper: .05 } },
  featureIds: ["i0/face/2"], refs: [{ ref: "bracket/f:bore", status: "ok" }] };
const position = { id: "position", part: 0, kind: "geometric_tolerance", status: "ok", supported: true,
  tolerance: { characteristic: "position", value: .1, unit: "mm", zone: "diameter", datums: ["A"] },
  featureIds: ["i0/face/2"], refs: [{ ref: "bracket/f:bore", status: "ok" }] };
const entries = [datum, diameter, position];
test("size limits preserve signed deviations and never invent an unspecified tolerance", () => {
  assert.deepEqual(dimensionLimits(diameter), { lower: 10, upper: 10.05, unit: "mm", places: 2 });
  assert.deepEqual(dimensionLimits({ ...diameter, dimension: { ...diameter.dimension, tolerance: { lower: -.2, upper: .1 } } }), { lower: 9.8, upper: 10.1, unit: "mm", places: 1 });
  assert.equal(dimensionLimits({ ...diameter, dimension: { ...diameter.dimension, tolerance: null } }), null);
  // Both limits at the places the nominal is written at: what it needs, where the tolerance needs fewer.
  assert.deepEqual(dimensionLimits({ ...diameter, dimension: { ...diameter.dimension, nominal: 6.35, tolerance: { lower: -0.1, upper: 0.1 } } }),
    { lower: 6.25, upper: 6.45, unit: "mm", places: 2 });
  assert.equal(dimensionLimits({ ...diameter, status: "missing" }), null);
});
test("a dimension given its limits has those for its limits, at their own places, with or without a nominal", () => {
  const thickness = { ...diameter, dimension: { type: "distance", nominal: 10, unit: "mm", tolerance: { type: "limits", lower: 9.8, upper: 10.2 } } };
  assert.deepEqual(dimensionLimits(thickness), { lower: 9.8, upper: 10.2, unit: "mm", places: 1 });
  assert.deepEqual(dimensionLimits({ ...thickness, dimension: { ...thickness.dimension, nominal: null } }), { lower: 9.8, upper: 10.2, unit: "mm", places: 1 });
});
test("a face reveals every attached requirement, and datum links stay on the same part", () => {
  assert.deepEqual(featureRequirements(entries, ["i0/face/2"]).map(e => e.id), ["bore", "position"]);
  assert.deepEqual(featureRequirements(entries, ["i0/face/99"]), []);
  const foreign = { ...datum, id: "other-A", part: 1 };
  assert.deepEqual(datumRelationships(position, [foreign, ...entries]).map(r => [r.role, r.entry?.id]), [["Primary", "A"]]);
});
test("a datum is used by the tolerances of its own part that refer to its letter", () => {
  const foreign = { ...position, id: "other-position", part: 1 };
  assert.deepEqual(datumDependents(datum, [...entries, foreign]).map(e => e.id), ["position"]);
  assert.deepEqual(datumDependents(position, entries), []);
});

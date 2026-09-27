import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { applyStepModuleEffectsToRecords, displayTransformForPart } from "./stepModuleEffects.js";

const TRANSFORM = [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1];

test("composed packages (partTransformsBaked: false) always place parts by transform", () => {
  const meshData = { partTransformsBaked: false };
  const part = { transform: TRANSFORM };
  // Packages render shared component-local geometry, so the occurrence
  // transform must always apply.
  assert.equal(displayTransformForPart(meshData, part), TRANSFORM);
  assert.equal(displayTransformForPart(meshData, {}), null);
});

test("baked meshDatas never re-apply part transforms", () => {
  const part = { transform: TRANSFORM };
  assert.equal(displayTransformForPart({ partTransformsBaked: true }, part), null);
  // World-baked vertices need no per-part transform, flag stated or not.
  assert.equal(displayTransformForPart({}, part), null);
});

test("a pass reports whether anything but a transform changed, so a moving frame can skip the appearance work", () => {
  const records = [{ partId: "a" }, { partId: "b" }];
  const moved = (x) => new Map([["a", { matrix: new THREE.Matrix4().makeTranslation(x, 0, 0) }]]);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, moved(1)).appearanceChanged, false, "a first move changes no appearance");
  assert.equal(records[0].effectMatrix.elements[12], 1);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, moved(2)).appearanceChanged, false);
  assert.equal(records[0].effectMatrix.elements[12], 2);
  assert.equal(records[1].effectMatrix, null);

  const styled = new Map([["a", { matrix: new THREE.Matrix4(), style: { color: "#f00", opacity: 0.5 } }]]);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, styled).appearanceChanged, true);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, new Map(styled)).appearanceChanged, false, "the same style again is no change");
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, new Map([["a", { style: { color: "#f00", opacity: 0.6 } }]])).appearanceChanged, true);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, new Map([["a", { style: { color: "#f00", opacity: 0.6 }, visible: false }]])).appearanceChanged, true);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, new Map([["b", { highlighted: true }]])).appearanceChanged, true, "a hidden part shown again, and a highlight");
  // An effect that ends is a change back to rest, and rest again is none.
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, new Map()).appearanceChanged, true);
  assert.equal(applyStepModuleEffectsToRecords(THREE, records, new Map()).appearanceChanged, false);
  assert.deepEqual(records.map(record => [record.effectStyle, record.effectVisible, record.effectHighlighted]), [[null, null, false], [null, null, false]]);
});

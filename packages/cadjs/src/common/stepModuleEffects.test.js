import assert from "node:assert/strict";
import test from "node:test";

import { displayTransformForPart } from "./stepModuleEffects.js";

const TRANSFORM = [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1];

test("composed packages (partTransformsBaked: false) always place parts by transform", () => {
  const meshData = { partTransformsBaked: false };
  const part = { transform: TRANSFORM };
  // Regression: packages render shared component-local geometry, so the
  // occurrence transform must apply even outside individual-parts mode.
  assert.equal(displayTransformForPart(meshData, part, false), TRANSFORM);
  assert.equal(displayTransformForPart(meshData, part, true), TRANSFORM);
});

test("baked meshDatas never re-apply part transforms", () => {
  const meshData = { partTransformsBaked: true };
  const part = { transform: TRANSFORM };
  assert.equal(displayTransformForPart(meshData, part, true), null);
  assert.equal(displayTransformForPart(meshData, part, false), null);
});

test("legacy meshDatas keep the individual-mode-only behavior", () => {
  const meshData = {};
  const part = { transform: TRANSFORM };
  assert.equal(displayTransformForPart(meshData, part, true), TRANSFORM);
  assert.equal(displayTransformForPart(meshData, part, false), null);
  assert.equal(displayTransformForPart(meshData, {}, true), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import { displayTransformForPart } from "./stepModuleEffects.js";

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

import assert from "node:assert/strict";
import test from "node:test";

import { stageFitCurrent, stageFitInputs } from "./stageFollow.js";

function scene(min = [0, 0, 0], max = [10, 4, 3]) {
  return { bounds: { min, max }, restBounds: { min: [0, 0, 0], max: [10, 4, 3] } };
}

test("a sync that finds the scene where the stage was fitted refits nothing", () => {
  const fit = () => 1;
  const model = scene();
  const fitted = stageFitInputs(fit, model, [0, 0, 0]);
  assert.equal(stageFitCurrent(fitted, stageFitInputs(fit, model, [0, 0, 0])), true, "a hover's pose pass moved nothing");
  // The same values, written again in place by a pass that recomputed them.
  model.bounds.max = [10, 4, 3];
  assert.equal(stageFitCurrent(fitted, stageFitInputs(fit, model, [0, 0, 0])), true);
});

test("a moved scene, a moved model, another scene or a changed setting refits", () => {
  const fit = () => 1;
  const model = scene();
  const fitted = stageFitInputs(fit, model, [0, 0, 0]);
  assert.equal(stageFitCurrent(null, fitted), false, "never fitted");
  model.bounds.max = [10, 4, 3.5];
  assert.equal(stageFitCurrent(fitted, stageFitInputs(fit, model, [0, 0, 0])), false, "a routine's frame that moved a part");
  model.bounds.max = [10, 4, 3];
  model.restBounds.max = [11, 4, 3];
  assert.equal(stageFitCurrent(fitted, stageFitInputs(fit, model, [0, 0, 0])), false, "a rebuilt model at rest");
  model.restBounds.max = [10, 4, 3];
  assert.equal(stageFitCurrent(fitted, stageFitInputs(fit, model, [0, 0, 1])), false, "the model's offset");
  assert.equal(stageFitCurrent(fitted, stageFitInputs(fit, scene(), [0, 0, 0])), false, "another scene");
  assert.equal(stageFitCurrent(fitted, stageFitInputs(() => 1, model, [0, 0, 0])), false, "a fit that reads other settings");
});

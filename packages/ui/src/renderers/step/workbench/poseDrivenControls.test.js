import assert from "node:assert/strict";
import { test } from "node:test";

import {
  poseControlDisplayValue,
  poseControlWrite,
  poseDisplayValues,
  poseDrivenDofs
} from "./poseDrivenControls.js";

// A planetary stage, the shape the routing exists for: one coupling gears the sun, the
// carrier and a planet, so sliding any of them has to turn the train. The articulation is
// cadgen's: each member's handle names the coupling as what a gesture writes, with its ratio.
const control = (id, min, max, unit = "deg") => ({ id, label: id, unit, min, max, default: 0 });
const row = (...terms) => ({ bias: 0, terms });
function stage({ sunRatio = 1, carrierRatio = 0.2857142857142857, planetRatio = -0.9523809523809523 } = {}) {
  return {
    schemaVersion: 1,
    controls: [control("sun", -1260, 1260), control("carrier", -360, 360), control("planet1", -5040, 5040), control("drive", 0, 1260, "")],
    joints: [
      { id: "sun", parent: null, kind: "revolute", origin: [0, 0, 0], axis: [0, 0, 1], turn: row(["sun", 1], ["drive", sunRatio]) },
      { id: "carrier", parent: null, kind: "revolute", origin: [0, 0, 0], axis: [0, 0, 1], turn: row(["carrier", 1], ["drive", carrierRatio]) },
      { id: "planet1", parent: "carrier", kind: "revolute", origin: [0, 0, 0], axis: [0, 0, 1], turn: row(["planet1", 1], ["drive", planetRatio]) },
      { id: "pin1", parent: "carrier", kind: "fixed" }
    ],
    carries: {},
    handles: [
      { id: "sun", joint: "sun", dof: "turn", control: "drive", weight: sunRatio, label: "sun", unit: "deg", min: -1260, max: 1260 },
      { id: "carrier", joint: "carrier", dof: "turn", control: "drive", weight: carrierRatio, label: "carrier", unit: "deg", min: -360, max: 360 },
      { id: "planet1", joint: "planet1", dof: "turn", control: "drive", weight: planetRatio, label: "planet1", unit: "deg", min: -5040, max: 5040 }
    ],
    poses: { quarter: { drive: 315 } },
    opening: { sun: 0, carrier: 0, planet1: 0, drive: 0 }
  };
}

const PLANETARY = stage();
const PLANETARY_DEFINITION = { url: "/planetary.step.json", articulation: PLANETARY };
const controlOf = (id) => PLANETARY.controls.find((entry) => entry.id === id);

test("pose routing marks geared members driven and leaves the coupling independent", () => {
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  assert.deepEqual(Object.keys(driven).sort(), ["carrier", "planet1", "sun"]);
  assert.equal(driven.sun.control, "drive");
  // The coupling itself, and a fastened joint that is no row at all.
  assert.equal(driven.drive, undefined);
  assert.equal(driven.pin1, undefined);
});

test("a definition with no coupling (or none at all) drives nothing", () => {
  const plain = { articulation: { ...PLANETARY, handles: [{ id: "sun", joint: "sun", dof: "turn", control: "sun", weight: 1 }] } };
  assert.deepEqual(poseDrivenDofs(plain), {});
  assert.deepEqual(poseDrivenDofs(null), {});
  assert.deepEqual(poseDisplayValues(null, { swing: 10 }), {});
});

test("driven sliders display the row value, independent ones the stored value", () => {
  const values = { sun: 0, carrier: 0, planet1: 0, drive: 630 };
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  const displayValues = poseDisplayValues(PLANETARY_DEFINITION, values);
  const show = (id) => poseControlDisplayValue({ driven, displayValues, values, parameter: controlOf(id) });
  assert.equal(show("sun"), 630);
  assert.equal(Math.round(show("carrier") * 1e6) / 1e6, 180);
  assert.equal(Math.round(show("planet1") * 1e6) / 1e6, -600);
  // The coupling's own slider is untouched by any of this.
  assert.equal(show("drive"), 630);
});

test("sliding a driven member writes the coupling, not the member", () => {
  const values = { sun: 0, carrier: 0, planet1: 0, drive: 0 };
  const write = poseControlWrite({ definition: PLANETARY_DEFINITION, values, parameterId: "sun", value: 630 });
  assert.deepEqual(write, { id: "drive", value: 630 });
  // A negative ratio back-drives the coupling the other way, and the whole
  // train follows: carrier and sun move too.
  const planetWrite = poseControlWrite({ definition: PLANETARY_DEFINITION, values, parameterId: "planet1", value: -600 });
  assert.equal(planetWrite.id, "drive");
  assert.equal(Math.round(planetWrite.value * 1e6) / 1e6, 630);
  const after = poseDisplayValues(PLANETARY_DEFINITION, { ...values, drive: planetWrite.value });
  assert.equal(Math.round(after.sun * 1e6) / 1e6, 630);
  assert.equal(Math.round(after.carrier * 1e6) / 1e6, 180);
});

test("a member's own term survives back-driving and is compensated for", () => {
  // A preset or --kinematics JSON set sun's OWN value; sliding sun to 700
  // effective must leave that 100 alone and put the rest on the coupling.
  const values = { sun: 100, carrier: 0, planet1: 0, drive: 0 };
  const write = poseControlWrite({ definition: PLANETARY_DEFINITION, values, parameterId: "sun", value: 700 });
  assert.deepEqual(write, { id: "drive", value: 600 });
  const after = poseDisplayValues(PLANETARY_DEFINITION, { ...values, drive: write.value });
  assert.equal(after.sun, 700);
});

test("back-driving clamps to the coupling's limits", () => {
  const values = { sun: 0, carrier: 0, planet1: 0, drive: 0 };
  // drive stops at 1260, so a sun beyond that cannot be reached through it.
  assert.deepEqual(poseControlWrite({ definition: PLANETARY_DEFINITION, values, parameterId: "sun", value: 2000 }), {
    id: "drive",
    value: 1260
  });
  // drive starts at 0, so a positive planet1 (negative ratio) pins there.
  assert.deepEqual(poseControlWrite({ definition: PLANETARY_DEFINITION, values, parameterId: "planet1", value: 500 }), {
    id: "drive",
    value: 0
  });
});

test("an independent control writes straight through", () => {
  assert.deepEqual(poseControlWrite({ definition: PLANETARY_DEFINITION, values: {}, parameterId: "drive", value: 42 }), {
    id: "drive",
    value: 42
  });
  // A member cadgen left to itself (two couplings gear it: the inverse is underdetermined,
  // so its handle names the member) writes itself.
  const contested = { articulation: { ...PLANETARY,
    handles: [{ id: "sun", joint: "sun", dof: "turn", control: "sun", weight: 1, label: "sun", unit: "deg", min: -1260, max: 1260 }] } };
  assert.deepEqual(poseDrivenDofs(contested), {});
  assert.deepEqual(poseControlWrite({ definition: contested, values: {}, parameterId: "sun", value: 30 }), { id: "sun", value: 30 });
});

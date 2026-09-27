import assert from "node:assert/strict";
import { test } from "node:test";

import { stepModuleFromKinematics } from "@hardcore/core/common/kinematicsModule.js";
import { normalizeStepModuleDefinition } from "@hardcore/core/common/stepModule.js";

import {
  poseControlDisplayValue,
  poseControlWrite,
  poseDisplayValues,
  poseDrivenDofs
} from "./poseDrivenControls.js";

// A planetary stage, the shape the routing exists for: one coupling gears the
// sun, the carrier and a planet, so sliding any of them has to turn the train.
function revolute(name, parent, child, limit) {
  return {
    name,
    kind: "revolute",
    parent: `#${parent}`,
    child: `#${child}`,
    axis: { origin: [0, 0, 0], dir: [0, 0, 1] },
    limits: { value: [-limit, limit] }
  };
}

const PLANETARY = {
  mates: [
    revolute("sun", "ring", "sun_gear", 1260),
    revolute("carrier", "ring", "carrier_plate", 360),
    revolute("planet1", "carrier_plate", "planet_gear_1", 5040),
    { name: "pin1", kind: "fastened", parent: "#carrier_plate", child: "#planet_pin_1", limits: {} }
  ],
  couplings: [
    { name: "drive", gears: { sun: 1, carrier: 0.2857142857142857, planet1: -0.9523809523809523 }, limits: [0, 1260] }
  ],
  poses: { quarter: { drive: 315 } }
};

function definitionFor(block) {
  return normalizeStepModuleDefinition(stepModuleFromKinematics(block), { cadPath: "STEP/x.step" });
}

const PLANETARY_DEFINITION = definitionFor(PLANETARY);

test("pose routing marks geared members driven and leaves the coupling independent", () => {
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  assert.deepEqual(Object.keys(driven).sort(), ["carrier", "planet1", "sun"]);
  assert.equal(driven.sun.coupling, "drive");
  // The coupling itself, and a fastened mate that is not a DOF at all.
  assert.equal(driven.drive, undefined);
  assert.equal(driven.pin1, undefined);
});

test("a definition with no kinematics (or none at all) drives nothing", () => {
  const plain = definitionFor({ mates: [revolute("swing", "body", "lever", 90)] });
  assert.deepEqual(poseDrivenDofs(plain), {});
  assert.deepEqual(poseDrivenDofs(null), {});
  assert.deepEqual(poseDisplayValues(null, { swing: 10 }), {});
});

test("driven sliders display the effective value, independent ones the stored value", () => {
  const values = { sun: 0, carrier: 0, planet1: 0, drive: 630 };
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  const displayValues = poseDisplayValues(PLANETARY_DEFINITION, values);
  const show = (id) => poseControlDisplayValue({
    driven,
    displayValues,
    values,
    parameter: PLANETARY_DEFINITION.parameterMap[id]
  });
  assert.equal(show("sun"), 630);
  assert.equal(Math.round(show("carrier") * 1e6) / 1e6, 180);
  assert.equal(Math.round(show("planet1") * 1e6) / 1e6, -600);
  // The coupling's own slider is untouched by any of this.
  assert.equal(show("drive"), 630);
});

test("sliding a driven member writes the coupling, not the member", () => {
  const values = { sun: 0, carrier: 0, planet1: 0, drive: 0 };
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  const write = poseControlWrite({ driven, values, parameterId: "sun", value: 630 });
  assert.deepEqual(write, { id: "drive", value: 630 });
  // A negative ratio back-drives the coupling the other way, and the whole
  // train follows: carrier and sun move too.
  const planetWrite = poseControlWrite({ driven, values, parameterId: "planet1", value: -600 });
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
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  const write = poseControlWrite({ driven, values, parameterId: "sun", value: 700 });
  assert.deepEqual(write, { id: "drive", value: 600 });
  const after = poseDisplayValues(PLANETARY_DEFINITION, { ...values, drive: write.value });
  assert.equal(after.sun, 700);
});

test("back-driving clamps to the coupling's limits", () => {
  const values = { sun: 0, carrier: 0, planet1: 0, drive: 0 };
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  // drive stops at 1260, so a sun beyond that cannot be reached through it.
  assert.deepEqual(poseControlWrite({ driven, values, parameterId: "sun", value: 2000 }), {
    id: "drive",
    value: 1260
  });
  // drive starts at 0, so a positive planet1 (negative ratio) pins there.
  assert.deepEqual(poseControlWrite({ driven, values, parameterId: "planet1", value: 500 }), {
    id: "drive",
    value: 0
  });
});

test("an independent DOF writes straight through, driven or not", () => {
  const driven = poseDrivenDofs(PLANETARY_DEFINITION);
  assert.deepEqual(poseControlWrite({ driven, values: {}, parameterId: "drive", value: 42 }), {
    id: "drive",
    value: 42
  });
  // A member geared by TWO couplings stays independent: the inverse is
  // underdetermined and the routing refuses to guess a split.
  const contested = definitionFor({
    mates: [revolute("elbow", "arm", "forearm", 150)],
    couplings: [
      { name: "curl", gears: { elbow: 90 }, limits: [0, 1] },
      { name: "fold", gears: { elbow: 45 }, limits: [0, 1] }
    ]
  });
  assert.deepEqual(poseDrivenDofs(contested), {});
  assert.deepEqual(poseControlWrite({
    driven: poseDrivenDofs(contested),
    values: {},
    parameterId: "elbow",
    value: 30
  }), { id: "elbow", value: 30 });
});

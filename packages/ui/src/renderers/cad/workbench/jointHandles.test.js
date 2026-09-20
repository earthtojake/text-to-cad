import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { kinematicsDeltas } from "@hardcore/core/common/kinematicsRuntime.js";

import { stepJointHandles, stepPosableDofs } from "./jointHandles.js";

/** Which mate DOFs the Pose tool offers in a STEP, and where their handles are for a posed chain. */

const round = (values) => values.map((value) => Math.round(value * 1e6) / 1e6 || 0);

// ring -(carrier, Z)-> carrier -(planet, Z at x=40)-> planet -(probe, X slider)-> probe; a coupling gears
// carrier and planet; a cylindrical mate contributes a turn and a travel; a fastened mate contributes nothing.
const block = {
  mates: [
    { name: "carrier", kind: "revolute", parent: "#ring", child: "#carrier", axis: { origin: [0, 0, 0], dir: [0, 0, 1] }, limits: { value: [-360, 360] } },
    { name: "planet", kind: "revolute", parent: "#carrier", child: "#planet", axis: { origin: [40, 0, 0], dir: [0, 0, 1] }, limits: { value: [-720, 720] } },
    { name: "probe", kind: "slider", parent: "#planet", child: "#probe", axis: { origin: [40, 0, 5], dir: [1, 0, 0] }, limits: { value: [0, 12] } },
    { name: "crown", kind: "cylindrical", parent: "#ring", child: "#crown", axis: { origin: [0, 60, 0], dir: [0, 1, 0] }, limits: { turn: [0, 90], travel: [0, 2] } },
    { name: "lid", kind: "fastened", parent: "#ring", child: "#lid" }
  ],
  couplings: [{ name: "drive", gears: { carrier: 0.25, planet: -1 }, limits: [0, 1440] }]
};
const parameterIds = ["carrier", "planet", "probe", "crown.turn", "crown.travel", "drive"];
const definition = { manifest: { kinematics: block }, parameterMap: Object.fromEntries(parameterIds.map((id) => [id, { id }])) };
const features = { planet: { center: [40, 10, 0] }, carrier: { center: [0, 0, 0] }, crown: { missing: true, center: [9, 9, 9] } };

test("a STEP's handles are its mate DOFs, the geared ones included; a coupling has no axis to hold", () => {
  assert.deepEqual(stepPosableDofs(definition).map(({ id, kind }) => `${id}:${kind}`),
    ["carrier:revolute", "planet:revolute", "probe:prismatic", "crown.turn:revolute", "crown.travel:prismatic"]);
  assert.deepEqual(stepPosableDofs({ manifest: { kinematics: { mates: [block.mates[4]] } }, parameterMap: {} }), []);
  assert.deepEqual(stepPosableDofs(null), []);
});

test("a STEP handle rides its whole mate chain, exactly as the runtime poses the parts", () => {
  const values = { drive: 120, probe: 7, "crown.turn": 30, "crown.travel": 1.5 };
  const handles = Object.fromEntries(stepJointHandles({ definition, parameterValues: values, features, onParameterChange() {} })
    .map((handle) => [handle.id, handle]));
  const deltas = kinematicsDeltas(THREE, block, values);
  const carried = (ref, point) => round(new THREE.Vector3(...point).applyMatrix4(deltas.get(ref)).toArray());
  // Effective values: what the sliders show for geared members.
  assert.deepEqual([handles.carrier.value, handles.planet.value, handles.probe.value], [30, -120, 7]);
  // Two levels down: the probe's pivot is the rest origin carried by the probe's own accumulated delta.
  assert.deepEqual(round(handles.probe.pivot), carried("#probe", [40, 0, 5]));
  assert.deepEqual(round(handles.probe.axis), round(new THREE.Vector3(1, 0, 0).transformDirection(deltas.get("#probe")).toArray()));
  assert.deepEqual(round(handles.planet.pivot), carried("#planet", [40, 0, 0]));
  // The planet's arm points at the planet's own centre, turned with it.
  assert.deepEqual(round(handles.planet.toward), carried("#planet", [40, 1, 0]));
  assert.deepEqual([handles.planet.min, handles.planet.max], [-720, 720]);
  // A cylindrical mate is one child with two handles on one axis line.
  assert.deepEqual(round(handles["crown.turn"].pivot), carried("#crown", [0, 60, 0]));
  assert.deepEqual(round(handles["crown.travel"].pivot), round(handles["crown.turn"].pivot));
  assert.deepEqual([handles["crown.turn"].unit, handles["crown.travel"].unit], ["deg", "mm"]);
});

test("a geared member writes through its coupling, as its slider does; a free one writes itself", () => {
  const writes = [];
  const handles = stepJointHandles({ definition, parameterValues: { drive: 120 }, features, onParameterChange: (id, value) => writes.push([id, value]) });
  handles.find(({ id }) => id === "carrier").onChange(60);
  handles.find(({ id }) => id === "probe").onChange(99);
  assert.deepEqual(writes, [["drive", 240], ["probe", 99]]);
});

test("concentric members fan their knobs round the shared axis, decided at rest", () => {
  const concentric = {
    mates: ["rotor", "cage", "output"].map((name) => (
      { name, kind: "revolute", parent: "#housing", child: `#${name}`, axis: { origin: [0, 0, 0], dir: [0, 0, 1] } }
    ))
  };
  const handles = stepJointHandles({
    definition: { manifest: { kinematics: concentric }, parameterMap: { rotor: {}, cage: {}, output: {} } },
    parameterValues: { cage: 40 }, features: {}, onParameterChange() {}
  });
  const bearing = ({ toward, pivot }) => (Math.atan2(toward[1] - pivot[1], toward[0] - pivot[0]) * 180) / Math.PI;
  const [rotor, cage, output] = handles.map(bearing);
  const turn = (deg) => Math.round((((deg % 360) + 360) % 360) * 1e6) / 1e6;
  assert.equal(turn(cage - rotor), 160);
  assert.equal(turn(output - rotor), 240);
});

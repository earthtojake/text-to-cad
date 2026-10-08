import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { jointDeltas } from "@text-to-cad/core/common/articulation.js";

import { stepJointHandles, stepPosableHandles } from "./jointHandles.js";

/** Which rows the Position tool offers in a STEP, and where their handles are for a posed chain. */

const round = (values) => values.map((value) => Math.round(value * 1e6) / 1e6 || 0);

// The articulation cadgen writes for: ring -(carrier, Z)-> carrier -(planet, Z at x=40)-> planet
// -(probe, X slider)-> probe; a coupling `drive` gears carrier and planet; a cylindrical mate
// `crown` contributes a turn and a travel; a fastened `lid` contributes nothing to hold.
const control = (id, unit, min, max) => ({ id, label: id, unit, min, max, default: 0 });
const row = (...terms) => ({ bias: 0, terms });
const handle = (id, joint, dof, control, weight, unit, min, max) => ({ id, joint, dof, control, weight, label: id, unit, min, max });
const articulation = {
  schemaVersion: 1,
  controls: [
    control("carrier", "deg", -360, 360), control("planet", "deg", -720, 720), control("probe", "mm", 0, 12),
    control("crown.turn", "deg", 0, 90), control("crown.travel", "mm", 0, 2), control("drive", "", 0, 1440)
  ],
  joints: [
    { id: "carrier", parent: null, kind: "revolute", origin: [0, 0, 0], axis: [0, 0, 1], turn: row(["carrier", 1], ["drive", 0.25]) },
    { id: "planet", parent: "carrier", kind: "revolute", origin: [40, 0, 0], axis: [0, 0, 1], turn: row(["planet", 1], ["drive", -1]) },
    { id: "probe", parent: "planet", kind: "slider", origin: [40, 0, 5], axis: [1, 0, 0], travel: row(["probe", 1]) },
    { id: "crown", parent: null, kind: "cylindrical", origin: [0, 60, 0], axis: [0, 1, 0], turn: row(["crown.turn", 1]), travel: row(["crown.travel", 1]) },
    { id: "lid", parent: null, kind: "fixed" }
  ],
  carries: { carrier: ["carrier"], planet: ["planet"], probe: ["probe"], crown: ["crown"], lid: ["lid"] },
  handles: [
    handle("carrier", "carrier", "turn", "drive", 0.25, "deg", -360, 360),
    handle("planet", "planet", "turn", "drive", -1, "deg", -720, 720),
    handle("probe", "probe", "travel", "probe", 1, "mm", 0, 12),
    handle("crown.turn", "crown", "turn", "crown.turn", 1, "deg", 0, 90),
    handle("crown.travel", "crown", "travel", "crown.travel", 1, "mm", 0, 2)
  ],
  poses: {},
  opening: { carrier: 0, planet: 0, probe: 0, "crown.turn": 0, "crown.travel": 0, drive: 0 }
};
const definition = { url: "/train.step.json", articulation };
// The rest mesh: the parts a joint carries give its arm a direction.
const meshData = { parts: [
  { id: "planet", bounds: { min: [38, 8, -1], max: [42, 12, 1] } },
  { id: "carrier", bounds: { min: [-1, -1, -1], max: [1, 1, 1] } }
] };

test("a STEP's handles are its articulation's, the geared ones included; a coupling has no axis to hold", () => {
  assert.deepEqual(stepPosableHandles(definition).map(({ id, kind }) => `${id}:${kind}`),
    ["carrier:revolute", "planet:revolute", "probe:prismatic", "crown.turn:revolute", "crown.travel:prismatic"]);
  assert.deepEqual(stepPosableHandles({ articulation: { ...articulation, handles: [], joints: [articulation.joints[4]] } }), []);
  assert.deepEqual(stepPosableHandles(null), []);
});

test("a STEP handle rides its whole joint chain, exactly as the player poses the parts", () => {
  const values = { drive: 120, probe: 7, "crown.turn": 30, "crown.travel": 1.5 };
  const handles = Object.fromEntries(stepJointHandles({ definition, parameterValues: values, meshData, onParameterChange() {} })
    .map((handle) => [handle.id, handle]));
  const deltas = jointDeltas(THREE, articulation, values);
  const carried = (joint, point) => round(new THREE.Vector3(...point).applyMatrix4(deltas.get(joint)).toArray());
  // Row values: what the sliders show for geared members.
  assert.deepEqual([handles.carrier.value, handles.planet.value, handles.probe.value], [30, -120, 7]);
  // Two levels down: the probe's pivot is the rest origin carried by the probe's own delta.
  assert.deepEqual(round(handles.probe.pivot), carried("probe", [40, 0, 5]));
  assert.deepEqual(round(handles.probe.axis), round(new THREE.Vector3(1, 0, 0).transformDirection(deltas.get("probe")).toArray()));
  assert.deepEqual(round(handles.planet.pivot), carried("planet", [40, 0, 0]));
  // The planet's arm points at the planet's own centre, turned with it.
  assert.deepEqual(round(handles.planet.toward), carried("planet", [40, 1, 0]));
  assert.deepEqual([handles.planet.min, handles.planet.max], [-720, 720]);
  // A cylindrical joint is one child with two handles on one axis line.
  assert.deepEqual(round(handles["crown.turn"].pivot), carried("crown", [0, 60, 0]));
  assert.deepEqual(round(handles["crown.travel"].pivot), round(handles["crown.turn"].pivot));
  assert.deepEqual([handles["crown.turn"].unit, handles["crown.travel"].unit], ["deg", "mm"]);
});

test("a geared member writes through its coupling, as its slider does; a free one writes itself", () => {
  const writes = [];
  const handles = stepJointHandles({ definition, parameterValues: { drive: 120 }, meshData, onParameterChange: (id, value) => writes.push([id, value]) });
  handles.find(({ id }) => id === "carrier").onChange(60);
  handles.find(({ id }) => id === "probe").onChange(99);
  assert.deepEqual(writes, [["drive", 240], ["probe", 12]], "a write never goes past the control's limits");
});

test("concentric members fan their knobs round the shared axis, decided at rest", () => {
  const concentric = { ...articulation,
    controls: ["rotor", "cage", "output"].map((id) => control(id, "deg", -360, 360)),
    joints: ["rotor", "cage", "output"].map((id) => ({ id, parent: null, kind: "revolute", origin: [0, 0, 0], axis: [0, 0, 1], turn: row([id, 1]) })),
    carries: {},
    handles: ["rotor", "cage", "output"].map((id) => handle(id, id, "turn", id, 1, "deg", -360, 360)),
    opening: { rotor: 0, cage: 0, output: 0 } };
  const handles = stepJointHandles({ definition: { articulation: concentric }, parameterValues: { cage: 40 }, meshData: { parts: [] }, onParameterChange() {} });
  const bearing = ({ toward, pivot }) => (Math.atan2(toward[1] - pivot[1], toward[0] - pivot[0]) * 180) / Math.PI;
  const [rotor, cage, output] = handles.map(bearing);
  const turn = (deg) => Math.round((((deg % 360) + 360) % 360) * 1e6) / 1e6;
  assert.equal(turn(cage - rotor), 160);
  assert.equal(turn(output - rotor), 240);
});

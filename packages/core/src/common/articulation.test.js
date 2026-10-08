import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  applyArticulationToEffects,
  articulationAtRest,
  controlWriteForHandle,
  handleRowValue,
  jointDeltas,
  jointValues,
  normalizeControlValues,
  openingControlValues,
  poseControlValues
} from "./articulation.js";
import { applySceneState } from "./applySceneState.js";
import { normalizeAnimationClips } from "./animationRuntime.js";

// A hand-built articulation, in the shape cadgen writes (`cadgen.articulation`): an elbow
// turning about z at x=10 carrying the forearm, a slider on the forearm carrying the carriage,
// a cylindrical lead screw, a fixed pin riding the elbow, and a coupling `curl` gearing the
// elbow and the slider. The player decides nothing: what it reads here is what it plays.
const ARTICULATION = {
  schemaVersion: 1,
  controls: [
    { id: "elbow", label: "elbow", unit: "deg", min: 0, max: 150, default: 0 },
    { id: "extend", label: "extend", unit: "mm", min: 0, max: 80, default: 0 },
    { id: "lead.turn", label: "lead.turn", unit: "deg", min: 0, max: 3600, default: 0 },
    { id: "lead.travel", label: "lead.travel", unit: "mm", min: 0, max: 40, default: 0 },
    { id: "curl", label: "curl", unit: "", min: 0, max: 1, default: 0 }
  ],
  joints: [
    { id: "elbow", parent: null, kind: "revolute", origin: [10, 0, 0], axis: [0, 0, 1],
      turn: { bias: 0, terms: [["elbow", 1], ["curl", 90]] } },
    { id: "extend", parent: "elbow", kind: "slider", origin: [0, 0, 0], axis: [1, 0, 0],
      travel: { bias: 0, terms: [["extend", 1], ["curl", 10]] } },
    { id: "lead", parent: null, kind: "cylindrical", origin: [0, 0, 0], axis: [0, 0, 1],
      turn: { bias: 0, terms: [["lead.turn", 1]] }, travel: { bias: 0, terms: [["lead.travel", 1]] } },
    { id: "pin", parent: "elbow", kind: "fixed" }
  ],
  carries: { elbow: ["forearm"], extend: ["carriage"], lead: ["screw"], pin: ["pin"] },
  handles: [
    { id: "elbow", joint: "elbow", dof: "turn", control: "curl", weight: 90, label: "elbow", unit: "deg", min: 0, max: 150 },
    { id: "extend", joint: "extend", dof: "travel", control: "curl", weight: 10, label: "extend", unit: "mm", min: 0, max: 80 },
    { id: "lead.turn", joint: "lead", dof: "turn", control: "lead.turn", weight: 1, label: "lead.turn", unit: "deg", min: 0, max: 3600 },
    { id: "lead.travel", joint: "lead", dof: "travel", control: "lead.travel", weight: 1, label: "lead.travel", unit: "mm", min: 0, max: 40 }
  ],
  poses: { open: { elbow: 40 } },
  opening: { elbow: 0, extend: 0, "lead.turn": 0, "lead.travel": 0, curl: 0 }
};

function through(matrix, point) {
  return new THREE.Vector3(...point).applyMatrix4(matrix).toArray().map((v) => Math.round(v * 1e6) / 1e6);
}

test("a configuration is every control: given values clamped to their limits, the rest at their rest value", () => {
  assert.deepEqual(openingControlValues(ARTICULATION), { elbow: 0, extend: 0, "lead.turn": 0, "lead.travel": 0, curl: 0 });
  assert.deepEqual(normalizeControlValues(ARTICULATION, { elbow: 200, extend: "7", stray: 1 }),
    { elbow: 150, extend: 7, "lead.turn": 0, "lead.travel": 0, curl: 0 });
  // A named pose is a full configuration: what it names, and every other control at rest.
  assert.deepEqual(poseControlValues(ARTICULATION, "open"), { elbow: 40, extend: 0, "lead.turn": 0, "lead.travel": 0, curl: 0 });
  assert.deepEqual(poseControlValues(ARTICULATION, "shut"), openingControlValues(ARTICULATION));
});

test("joint values are the rows' dot products: an own term and a coupling's add", () => {
  assert.deepEqual(jointValues(ARTICULATION, { curl: 0.5 }).elbow, { turn: 45, travel: 0 });
  assert.deepEqual(jointValues(ARTICULATION, { curl: 0.5 }).extend, { turn: 0, travel: 5 });
  assert.deepEqual(jointValues(ARTICULATION, { elbow: 10, curl: 0.5 }).elbow, { turn: 55, travel: 0 });
  assert.equal(articulationAtRest(ARTICULATION, {}), true);
  assert.equal(articulationAtRest(ARTICULATION, { curl: 0.001 }), false);
});

test("a revolute delta turns about its own axis, not the world origin", () => {
  const deltas = jointDeltas(THREE, ARTICULATION, { elbow: 90 });
  // The pivot stays; a point one unit +x of it goes to one unit +y of it.
  assert.deepEqual(through(deltas.get("elbow"), [10, 0, 0]), [10, 0, 0]);
  assert.deepEqual(through(deltas.get("elbow"), [11, 0, 0]), [10, 1, 0]);
});

test("a child's delta composes through its parent chain, and a fixed joint rides its parent", () => {
  const deltas = jointDeltas(THREE, ARTICULATION, { elbow: 90, extend: 5 });
  // The slider's +x travel is carried by the elbow's quarter turn: it moves the carriage +y.
  assert.deepEqual(through(deltas.get("extend"), [10, 0, 0]), [10, 5, 0]);
  assert.deepEqual(deltas.get("pin").elements, deltas.get("elbow").elements);
});

test("a cylindrical joint turns and travels about one axis", () => {
  const delta = jointDeltas(THREE, ARTICULATION, { "lead.turn": 90, "lead.travel": 3 }).get("lead");
  assert.deepEqual(through(delta, [1, 0, 0]), [0, 1, 3]);
});

test("the pose lands on the effect records of exactly the occurrences each joint carries", () => {
  const effects = new Map();
  assert.equal(applyArticulationToEffects(THREE, ARTICULATION, { elbow: 90 }, effects), 4);
  assert.deepEqual([...effects.keys()].sort(), ["carriage", "forearm", "pin", "screw"]);
  assert.deepEqual(through(effects.get("forearm").matrix, [11, 0, 0]), [10, 1, 0]);
  assert.deepEqual(through(effects.get("carriage").matrix, [11, 0, 0]), [10, 1, 0], "the slider at rest carries the elbow alone");
  assert.deepEqual(effects.get("screw").matrix.elements, new THREE.Matrix4().elements);
  // At rest nothing is written: the artifact as written is q=0.
  assert.equal(applyArticulationToEffects(THREE, ARTICULATION, {}, new Map()), 0);
});

test("a handle shows its row and back-drives the control it names, clamped to that control's limits", () => {
  const [elbow, extend, leadTurn] = ARTICULATION.handles;
  const values = { elbow: 10, curl: 0.5 };
  assert.equal(handleRowValue(ARTICULATION, elbow, values), 55);
  // The member's own term stays as a preset set it; the coupling makes up the rest.
  assert.deepEqual(controlWriteForHandle(ARTICULATION, elbow, values, 100), { id: "curl", value: 1 });
  assert.deepEqual(controlWriteForHandle(ARTICULATION, extend, { extend: 2 }, 7), { id: "curl", value: 0.5 });
  assert.deepEqual(controlWriteForHandle(ARTICULATION, elbow, {}, 2000), { id: "curl", value: 1 }, "no further than the coupling goes");
  assert.deepEqual(controlWriteForHandle(ARTICULATION, elbow, {}, -5), { id: "curl", value: 0 });
  assert.deepEqual(controlWriteForHandle(ARTICULATION, leadTurn, {}, 30), { id: "lead.turn", value: 30 }, "a free row writes itself");
});

// Left slides +x at 1 mm/s.
const SLIDE = normalizeAnimationClips({ clips: [{
  id: "slide", label: "Slide", duration: 4, loop: true,
  tracks: [{ targets: ["forearm"], times: [0, 4], pivot: [0, 0, 0], transform: [
    [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
    [4, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0]
  ] }]
}] });

test("the scene pass plays the pose, then the clip on top of it, onto the records", () => {
  const runtime = { displayRecords: [{ partId: "forearm" }, { partId: "carriage" }, { partId: "screw" }, { partId: "pin" }] };
  const state = applySceneState(THREE, {
    runtime, meshData: { parts: [] },
    pose: { articulation: ARTICULATION, values: { elbow: 90 } },
    animation: { clip: SLIDE.slide, elapsedSec: 1.5 }
  });
  assert.equal(state.applied, true);
  assert.equal(state.transformDetected, true);
  const forearm = runtime.displayRecords[0].effectMatrix;
  // The elbow's turn first, the clip's +1.5 mm slide in world space on top: never the reverse.
  assert.deepEqual(through(forearm, [11, 0, 0]), [11.5, 1, 0]);
  assert.deepEqual(through(runtime.displayRecords[1].effectMatrix, [11, 0, 0]), [10, 1, 0], "the clip never touched the carriage");
  // Neither half with anything to say: the caller resets to rest.
  assert.equal(applySceneState(THREE, { runtime, meshData: { parts: [] } }).applied, false);
});

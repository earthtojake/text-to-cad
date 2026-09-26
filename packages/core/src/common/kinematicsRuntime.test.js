import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  couplingValueForDrivenDof,
  effectiveDofValues,
  kinematicsAtRest,
  kinematicsDeltas,
  kinematicsDofs,
  kinematicsDrivenDofs
} from "./kinematicsRuntime.js";

const BLOCK = {
  mates: [
    {
      name: "elbow", kind: "revolute", parent: "#upper_arm", child: "#forearm",
      axis: { origin: [10, 0, 0], dir: [0, 0, 1] },
      limits: { value: [0, 150] }
    },
    {
      name: "extend", kind: "slider", parent: "#forearm", child: "#carriage",
      axis: { origin: [0, 0, 0], dir: [1, 0, 0] },
      limits: { value: [0, 80] }
    },
    {
      name: "lead", kind: "cylindrical", parent: "#housing", child: "#screw",
      axis: { origin: [0, 0, 0], dir: [0, 0, 1] },
      limits: { turn: [0, 3600], travel: [0, 40] }
    }
  ],
  couplings: [{ name: "curl", gears: { elbow: 90, extend: 10 }, limits: [0, 1] }],
  poses: { open: { elbow: 40 } }
};

function pointThrough(matrix, point) {
  return new THREE.Vector3(...point).applyMatrix4(matrix).toArray().map((v) => Math.round(v * 1e6) / 1e6);
}

test("kinematics DOFs list mates (cylindrical twice) then couplings, with limits", () => {
  const dofs = kinematicsDofs(BLOCK);
  assert.deepEqual(dofs.map((d) => d.id), ["elbow", "extend", "lead.turn", "lead.travel", "curl"]);
  assert.deepEqual(dofs[0].limits, [0, 150]);
  assert.equal(dofs[4].kind, "coupling");
});

test("effective values start at zero and add coupling gears", () => {
  assert.equal(effectiveDofValues(BLOCK, {}).extend, 0);
  const geared = effectiveDofValues(BLOCK, { curl: 0.5 });
  assert.equal(geared.elbow, 45);
  assert.equal(geared.extend, 5);
  // Direct values and gearing compose additively.
  const both = effectiveDofValues(BLOCK, { elbow: 10, curl: 0.5 });
  assert.equal(both.elbow, 55);
});

test("a mate DOF geared by exactly one coupling is driven by it", () => {
  const driven = kinematicsDrivenDofs(BLOCK);
  assert.deepEqual(Object.keys(driven).sort(), ["elbow", "extend"]);
  assert.deepEqual(driven.elbow, { coupling: "curl", ratio: 90, limits: [0, 1] });
  // A coupling is never itself driven, and neither is an ungeared mate DOF.
  assert.equal(driven.curl, undefined);
  assert.equal(driven["lead.turn"], undefined);
});

test("driven classification refuses zero ratios, unknown gears and multi-coupling members", () => {
  const block = {
    mates: BLOCK.mates,
    couplings: [
      { name: "curl", gears: { elbow: 90, extend: 0, "lead.turn": 5, ghost: 3 }, limits: [0, 1] },
      { name: "fold", gears: { elbow: 45, "lead.travel": 2 }, limits: [0, 2] }
    ]
  };
  const driven = kinematicsDrivenDofs(block);
  // elbow is geared by BOTH couplings: inversion is underdetermined, so it
  // stays independent rather than guessing which one to move.
  assert.equal(driven.elbow, undefined);
  // A zero ratio is not a drive, an unknown gear name is not a DOF.
  assert.equal(driven.extend, undefined);
  assert.equal(driven.ghost, undefined);
  assert.deepEqual(driven["lead.turn"], { coupling: "curl", ratio: 5, limits: [0, 1] });
  assert.deepEqual(driven["lead.travel"], { coupling: "fold", ratio: 2, limits: [0, 2] });
});

test("a block with no couplings drives nothing", () => {
  assert.deepEqual(kinematicsDrivenDofs({ mates: BLOCK.mates }), {});
  assert.deepEqual(kinematicsDrivenDofs(null), {});
});

test("inverting a driven DOF returns the coupling value that lands its effective value", () => {
  const driven = kinematicsDrivenDofs(BLOCK);
  // elbow = 90 * curl, so 45 degrees of elbow is half a turn of curl.
  assert.equal(couplingValueForDrivenDof(driven.elbow, 45), 0.5);
  // The member's own term is kept: the coupling only makes up the difference.
  assert.equal(couplingValueForDrivenDof(driven.elbow, 55, 10), 0.5);
  // Round trip: the inverse fed back through the forward evaluator hits target.
  assert.equal(effectiveDofValues(BLOCK, { elbow: 10, curl: 0.5 }).elbow, 55);
});

test("inverting a negative ratio moves the coupling the other way", () => {
  const block = {
    mates: [{
      name: "planet", kind: "revolute", parent: "#a", child: "#b",
      axis: { origin: [0, 0, 0], dir: [0, 0, 1] }, limits: { value: [-5040, 5040] }
    }],
    couplings: [{ name: "drive", gears: { planet: -0.5 }, limits: [-1000, 1000] }]
  };
  const driver = kinematicsDrivenDofs(block).planet;
  assert.equal(driver.ratio, -0.5);
  assert.equal(couplingValueForDrivenDof(driver, -100), 200);
  assert.equal(effectiveDofValues(block, { drive: 200 }).planet, -100);
});

test("inversion clamps to the coupling's limits, in either limit order", () => {
  const driven = kinematicsDrivenDofs(BLOCK);
  // curl tops out at 1, so an elbow beyond 90 degrees cannot be back-driven.
  assert.equal(couplingValueForDrivenDof(driven.elbow, 180), 1);
  assert.equal(couplingValueForDrivenDof(driven.elbow, -90), 0);
  assert.equal(couplingValueForDrivenDof({ ratio: 2, limits: [4, -4] }, 100), 4);
  // A zero-ratio (or absent) driver has no inverse at all.
  assert.equal(couplingValueForDrivenDof({ ratio: 0, limits: [0, 1] }, 5), null);
  assert.equal(couplingValueForDrivenDof(null, 5), null);
});

test("a revolute delta rotates about its own axis, not the world origin", () => {
  const deltas = kinematicsDeltas(THREE, BLOCK, { elbow: 90 });
  const delta = deltas.get("#forearm");
  // The axis origin is on the rotation axis, so it stays put; a point one unit
  // +X of the axis swings to one unit +Y of it.
  assert.deepEqual(pointThrough(delta, [10, 0, 0]), [10, 0, 0]);
  assert.deepEqual(pointThrough(delta, [11, 0, 0]), [10, 1, 0]);
});

test("a child mate's delta composes through its parent chain", () => {
  const deltas = kinematicsDeltas(THREE, BLOCK, { elbow: 90, extend: 3 });
  // extend slides +X in rest space, but the elbow has already rotated the
  // forearm 90 degrees, so the carriage's slide emerges rotated to +Y.
  const carriage = deltas.get("#carriage");
  assert.deepEqual(pointThrough(carriage, [10, 0, 0]), [10, 3, 0]);
  // With no values at all, every delta is identity: zero is the artifact.
  const atRest = kinematicsDeltas(THREE, BLOCK, {});
  assert.deepEqual(pointThrough(atRest.get("#carriage"), [0, 0, 0]), [0, 0, 0]);
});

test("a cylindrical mate turns and travels about one axis", () => {
  const deltas = kinematicsDeltas(THREE, BLOCK, { "lead.turn": 180, "lead.travel": 7 });
  const screw = deltas.get("#screw");
  assert.deepEqual(pointThrough(screw, [1, 0, 0]), [-1, 0, 7]);
});

test("rest is all zeros", () => {
  assert.equal(kinematicsAtRest(BLOCK, {}), true);
  assert.equal(kinematicsAtRest(BLOCK, { extend: 0 }), true);
  assert.equal(kinematicsAtRest(BLOCK, { elbow: 1 }), false);
  assert.equal(kinematicsAtRest(BLOCK, { curl: 0.1 }), false);
});

test("an unresolved axis ref refuses to evaluate", () => {
  const unresolved = { mates: [{ name: "j", kind: "revolute", parent: "#a", child: "#b", axis: { ref: "#b.f1" } }] };
  assert.throws(() => kinematicsDeltas(THREE, unresolved, { j: 10 }), /not resolved to numbers/);
});

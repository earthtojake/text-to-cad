import assert from "node:assert/strict";
import test from "node:test";

import {
  solveDragWeights,
  applyWeightsToPoint,
  ModalSuperposition,
} from "./modalInteraction.js";

function close(a, b, eps = 1e-6) {
  return Math.abs(a - b) <= eps;
}

test("solveDragWeights hits the target displacement (constraint satisfied)", () => {
  const deltas = [
    [0.1, 0, 0],
    [0, 0, 0.2],
  ];
  const target = [0.05, 0, 0.1];
  const q = solveDragWeights({ deltas, target });
  const reached = applyWeightsToPoint(deltas, q);
  assert.ok(close(reached[0], target[0], 1e-4), `x ${reached[0]}`);
  assert.ok(close(reached[2], target[2], 1e-4), `z ${reached[2]}`);
});

test("energy weighting prefers the lower-frequency (softer) mode", () => {
  // Two modes both displace +x; the stiffer (higher-freq) one should be used less.
  const deltas = [
    [0.1, 0, 0],
    [0.1, 0, 0],
  ];
  const target = [0.1, 0, 0];
  const q = solveDragWeights({ deltas, target, frequencies: [10, 100] });
  // Reconstruction still matches.
  const reached = applyWeightsToPoint(deltas, q);
  assert.ok(close(reached[0], target[0], 1e-4));
  // Softer mode dominates (≈100x by omega^2 weighting).
  assert.ok(q[0] > q[1] * 50, `expected soft mode to dominate, got ${q[0]} vs ${q[1]}`);
});

test("single mode solves to the exact scale factor", () => {
  const q = solveDragWeights({ deltas: [[0.2, 0, 0]], target: [0.1, 0, 0] });
  assert.ok(close(q[0], 0.5, 1e-4), `q0 ${q[0]}`);
});

test("ModalSuperposition rings each mode at its own frequency", () => {
  const sup = new ModalSuperposition({
    frequencies: [10, 20],
    weights: [1, 0.5],
    damping: 0,
    slowdown: 10, // sim time = real/10
  });
  // At t=0, weights = initial.
  let w = sup.weightsAt(0);
  assert.ok(close(w[0], 1, 1e-9) && close(w[1], 0.5, 1e-9));
  // Mode 0 (10 Hz): half period in sim time = 1/(2*10) = 0.05s sim ->
  // real = 0.05*10 = 0.5s. cos(pi) = -1.
  w = sup.weightsAt(0.5);
  assert.ok(close(w[0], -1, 1e-6), `mode0 at half period ${w[0]}`);
  // Mode 1 (20 Hz) completes a full period in the same sim time -> cos(2pi)=1.
  assert.ok(close(w[1], 0.5, 1e-6), `mode1 at full period ${w[1]}`);
});

test("ModalSuperposition decays with damping", () => {
  const sup = new ModalSuperposition({
    frequencies: [10],
    weights: [1],
    damping: 0.1,
    slowdown: 1,
  });
  const early = Math.abs(sup.weightsAt(0.0)[0]);
  const later = Math.abs(sup.weightsAt(1.0)[0]);
  assert.ok(later < early, `expected decay: ${later} < ${early}`);
  assert.ok(sup.energyFraction(1.0) < sup.energyFraction(0.0));
});

test("initial velocity imparts kinetic energy (flick)", () => {
  // q0=0, v0=1, f=10, no damping, slowdown=1. Response = (v0/omega) sin(omega*t).
  const sup = new ModalSuperposition({
    frequencies: [10],
    weights: [0],
    velocities: [1],
    damping: 0,
    slowdown: 1,
  });
  assert.ok(close(sup.weightsAt(0)[0], 0, 1e-9)); // starts at zero displacement
  const omega = 2 * Math.PI * 10;
  // Quarter period: t = (pi/2)/omega -> sin = 1 -> q = 1/omega.
  const tq = Math.PI / 2 / omega;
  assert.ok(close(sup.weightsAt(tq)[0], 1 / omega, 1e-4), `peak ${sup.weightsAt(tq)[0]}`);
  // Moves immediately after release (nonzero velocity).
  assert.ok(sup.weightsAt(1e-4)[0] > 0);
});

test("advance accumulates real time", () => {
  const sup = new ModalSuperposition({ frequencies: [5], weights: [1], damping: 0, slowdown: 1 });
  sup.advance(0.1);
  sup.advance(0.1);
  assert.ok(close(sup.elapsedReal, 0.2, 1e-9));
});

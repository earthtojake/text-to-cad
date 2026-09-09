import assert from "node:assert/strict";
import test from "node:test";

import {
  DXF_FLAT_THICKNESS_SCALE,
  dxfBendGuideSegments,
  dxfFoldIsIdentity,
  foldDxfPoint,
  normalizeDxfFoldOptions,
  transformDxfPreviewPositions,
} from "./foldPreview.js";

// foldDxfPoint takes RESOLVED options (with precomputed pivots); normalize is the API.
const resolve = (bendAxesX, bendAnglesRad, thicknessScale = 1) =>
  normalizeDxfFoldOptions({ bendAxesX, bendAnglesRad, thicknessScale });

const close = (actual, expected, label) => {
  assert.ok(Math.abs(actual - expected) < 1e-6, `${label}: ${actual} should be ~${expected}`);
};

test("a 90-degree fold stands geometry beyond the axis straight up", () => {
  const [x, y, z] = foldDxfPoint(1, 5, 0, resolve([0], [Math.PI / 2]));
  close(x, 0, "x lands on the axis");
  close(y, 5, "y is untouched by a fold about an X axis");
  close(z, 1, "the run beyond the axis becomes rise");
});

test("a vertex clearly before the axis does not move", () => {
  const options = resolve([10], [Math.PI / 2]);
  assert.deepEqual(foldDxfPoint(3, 0, 0, options), [3, 0, 0]);
});

test("two bends accumulate down the chain", () => {
  // Axes at 0 and 1, both 90 degrees: the strip past the SECOND bend has been folded twice,
  // so a point 1 beyond it comes back over the top — x returns toward the first axis.
  const [x, , z] = foldDxfPoint(2, 0, 0, resolve([0, 1], [Math.PI / 2, Math.PI / 2]));
  close(x, -1, "folded twice: up, then back over");
  close(z, 1, "sits at the height of the first fold");
});

test("each bend folds by ITS OWN angle", () => {
  // First bend 90 degrees, second bend 0: the far strip rides the first fold but stays
  // coplanar with the middle strip — straight up.
  const [x, , z] = foldDxfPoint(2, 0, 0, resolve([0, 1], [Math.PI / 2, 0]));
  close(x, 0, "no second rotation");
  close(z, 2, "the whole run past the first bend is vertical");
});

test("direction is the sign of the angle", () => {
  const up = foldDxfPoint(1, 0, 0, resolve([0], [Math.PI / 2]));
  const down = foldDxfPoint(1, 0, 0, resolve([0], [-Math.PI / 2]));
  close(up[2], 1, "up folds +Z");
  close(down[2], -1, "down folds -Z");
});

test("thickness scales Z BEFORE the fold, so folded walls keep their thickness", () => {
  // The bug this module exists to prevent: with thickness applied AFTER the fold as a group
  // scale, a folded-up flange (which now extends in Z) is flattened back into the sheet
  // plane. Applied before, the cap offset rides the fold instead.
  const [x, , z] = foldDxfPoint(1, 0, 0.5, resolve([0], [Math.PI / 2], 4));
  close(x, -2, "the scaled cap offset folds with the strip");
  close(z, 1, "the run still becomes rise");
});

test("a crease vertex takes the miter, keeping the wall constant-thickness", () => {
  // At 90 degrees the two outer cap planes (z = +t/2 incoming, x = axis - t/2 outgoing)
  // intersect at (axis - t/2, +t/2): offset t/2 stretched by 1/cos(45) along the bisector.
  // Leaving the crease vertex in place is what fanned the wall from thin to thick.
  const [x, , z] = foldDxfPoint(0, 0, 0.5, resolve([0], [Math.PI / 2]));
  close(x, -0.5, "outer corner x");
  close(z, 0.5, "outer corner z");
  // The inner corner mirrors it.
  const [ix, , iz] = foldDxfPoint(0, 0, -0.5, resolve([0], [Math.PI / 2]));
  close(ix, 0.5, "inner corner x");
  close(iz, -0.5, "inner corner z");
});

test("a crease vertex at angle 0 sits exactly where the flat sheet has it", () => {
  // Continuity: the miter must degrade to the identity as the angle closes, or the sheet
  // pops at the first slider tick.
  const [x, , z] = foldDxfPoint(0, 0, 0.5, resolve([0], [0], 2));
  close(x, 0, "no bisector offset at 0");
  close(z, 1, "just the thickness scale");
});

test("transformDxfPreviewPositions always folds from the FLAT buffer", () => {
  const flat = Float32Array.from([2, 0, 0]);
  const output = new Float32Array(3);
  const options = { bendAxesX: [0], bendAnglesRad: [Math.PI / 2] };
  transformDxfPreviewPositions(flat, output, options);
  const once = [...output];
  transformDxfPreviewPositions(flat, output, options);
  assert.deepEqual([...output], once, "idempotent over the same flat source");
  assert.deepEqual([...flat], [2, 0, 0], "the flat source is never written");
});

test("identity is only identity", () => {
  assert.ok(dxfFoldIsIdentity({ thicknessScale: 1 }));
  assert.ok(dxfFoldIsIdentity({ bendAxesX: [5], bendAnglesRad: [0], thicknessScale: 1 }));
  assert.ok(!dxfFoldIsIdentity({ thicknessScale: 3 }));
  assert.ok(!dxfFoldIsIdentity({ bendAxesX: [5], bendAnglesRad: [0.1], thicknessScale: 1 }));
  // Zero thickness is a transform (the flat collapse), not identity.
  assert.ok(!dxfFoldIsIdentity({ thicknessScale: 0 }));
});

test("zero thickness collapses to a hair, never to a singular scale", () => {
  const [, , z] = foldDxfPoint(10, 0, 0.5, resolve([], [], 0));
  assert.ok(z > 0 && z <= 0.5 * DXF_FLAT_THICKNESS_SCALE + 1e-12, `hair-thin, got ${z}`);
});

test("axis/angle pairs stay paired through the sort", () => {
  // Axes handed over unsorted: bend at x=10 must keep ITS 90 degrees, not inherit the
  // other bend's 0.
  const sortedPair = resolve([110, 10], [0, Math.PI / 2]);
  const [x, , z] = foldDxfPoint(11, 0, 0, sortedPair);
  close(x, 10, "folded about the x=10 bend");
  close(z, 1, "by its own 90 degrees");
});

test("bend guides ride their creases through earlier folds", () => {
  const flat = Float32Array.from([0, 0, 0.5, 140, 70, -0.5]);
  const segments = dxfBendGuideSegments(flat, {
    bendAxesX: [30, 110],
    bendAnglesRad: [Math.PI / 2, Math.PI / 2],
    thicknessScale: 1,
  });
  assert.equal(segments.length, 12, "two guides, two endpoints each");
  assert.equal(segments[1], 0, "spans from yMin");
  assert.equal(segments[4], 70, "to yMax");
  // Guide 1 rides its own miter: just off its axis, just above the surface.
  assert.ok(Math.abs(segments[0] - 30) < 1.5, `guide 1 near its axis, got ${segments[0]}`);
  // Guide 2 rode the first fold: back beside the first axis, ~80 up.
  assert.ok(Math.abs(segments[6] - 30) < 2.5, `guide 2 folded back near the first axis, got ${segments[6]}`);
  assert.ok(segments[8] > 78 && segments[8] < 82, `guide 2 rises ~80, got ${segments[8]}`);
});

test("no bends means no guides", () => {
  assert.equal(dxfBendGuideSegments(Float32Array.from([0, 0, 0]), { bendAxesX: [] }).length, 0);
});

// --- arbitrary bend-line orientation ---------------------------------------------------

const resolveLines = (bendLines, bendAnglesRad, thicknessScale = 1) =>
  normalizeDxfFoldOptions({ bendLines, bendAnglesRad, thicknessScale });

test("a bend line given as a segment folds identically to its bare axis X", () => {
  const viaAxis = resolve([30], [Math.PI / 3]);
  const viaSegment = resolveLines([{ start: [30, 0], end: [30, 70] }], [Math.PI / 3]);
  for (const [x, y, z] of [[50, 10, 0.5], [10, 60, -0.5], [30, 35, 0.5]]) {
    const a = foldDxfPoint(x, y, z, viaAxis);
    const b = foldDxfPoint(x, y, z, viaSegment);
    close(a[0], b[0], `x at (${x},${y})`);
    close(a[1], b[1], `y at (${x},${y})`);
    close(a[2], b[2], `z at (${x},${y})`);
  }
});

test("a horizontal bend line folds the +Y side up", () => {
  // Line y=10 along X. The moving side is +Y (the oriented-normal convention), and a
  // positive angle lifts it: a point 5 beyond the line rises to z=5 at 90 degrees.
  const options = resolveLines([{ start: [0, 10], end: [100, 10] }], [Math.PI / 2]);
  const [x, y, z] = foldDxfPoint(50, 15, 0, options);
  close(x, 50, "x is untouched by a fold about a Y-axis line");
  close(y, 10, "the run beyond the line lands on it");
  close(z, 5, "and becomes rise");
  const fixed = foldDxfPoint(50, 5, 0, options);
  close(fixed[1], 5, "the -Y side is anchored");
  close(fixed[2], 0, "and stays flat");
});

test("a 45-degree bend line folds about its own direction", () => {
  // Line through the origin along (1,1). A point on the perpendicular at distance d from
  // the line rotates 90 degrees: it lands on the line's vertical plane at height d.
  const options = resolveLines([{ start: [0, 0], end: [10, 10] }], [Math.PI / 2]);
  const d = Math.SQRT2; // (2,0) is sqrt(2) from the line y=x
  const [x, y, z] = foldDxfPoint(2, 0, 0, options);
  close(x, 1, "folds onto the foot of its perpendicular");
  close(y, 1, "which sits on the line");
  close(z, d, "rising by its flat distance");
});

test("the whole fold is invariant under rotating the flat pattern", () => {
  // The strongest check the general math can face: rotate the entire configuration
  // (bend lines AND the query point) by 45 degrees, and the folded result must be the
  // upright chain's result rotated by the same 45 degrees. Uses the two-bend accumulation
  // case whose upright answer is pinned above: axes 0 and 1 at 90/90, point (2,0) -> (-1,0,1).
  const theta = Math.PI / 4;
  const rot = ([x, y]) => [
    x * Math.cos(theta) - y * Math.sin(theta),
    x * Math.sin(theta) + y * Math.cos(theta)
  ];
  const options = resolveLines(
    [
      { start: rot([0, -10]), end: rot([0, 10]) },
      { start: rot([1, -10]), end: rot([1, 10]) }
    ],
    [Math.PI / 2, Math.PI / 2]
  );
  const [qx, qy] = rot([2, 0]);
  const [x, y, z] = foldDxfPoint(qx, qy, 0, options);
  const [ex, ey] = rot([-1, 0]);
  close(x, ex, "x is the upright answer rotated");
  close(y, ey, "y is the upright answer rotated");
  close(z, 1, "height is rotation-invariant");
});

test("guides from segment bends use the segment's own endpoints", () => {
  const flat = Float32Array.from([0, 0, 0.5, 100, 100, -0.5]);
  const segments = dxfBendGuideSegments(flat, {
    bendLines: [{ start: [20, 5], end: [20, 45] }],
    bendAnglesRad: [0],
    thicknessScale: 1
  });
  assert.equal(segments.length, 6);
  close(segments[1], 5, "guide starts at the bend line's own start");
  close(segments[4], 45, "and ends at its end");
});

import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  applyExplodedViewProgress,
  clearExplodedViewRecords,
  computeExplodedViewLayout,
  easeExplodedViewProgress,
  explodedViewBounds
} from "./explodedView.js";

function record(partId, bounds) {
  return {
    partId,
    mesh: new THREE.Object3D(),
    partBounds: bounds
  };
}

function box(center, half) {
  return {
    min: [center[0] - half, center[1] - half, center[2] - half],
    max: [center[0] + half, center[1] + half, center[2] + half]
  };
}

// Resolve a layout into per-record displacement at `progress`, so tests can
// assert on where parts actually end up.
function explode(records, bounds, progress = 1) {
  const layout = computeExplodedViewLayout(records, bounds);
  applyExplodedViewProgress(THREE, layout, progress);
  const offsets = new Map();
  for (const r of records) {
    const m = r.explodedViewMatrix;
    offsets.set(r.partId, m ? [m.elements[12], m.elements[13], m.elements[14]] : [0, 0, 0]);
  }
  return { layout, offsets };
}

function length(vec) {
  return Math.hypot(vec[0], vec[1], vec[2]);
}

test("parts bloom radially away from the assembly center in full 3D", () => {
  // Four parts in a ring around the origin plus one above: each must move
  // outward along its own assembled direction, not onto a shared axis.
  const records = [
    record("o1.1", box([10, 0, 0], 1)),
    record("o1.2", box([-10, 0, 0], 1)),
    record("o1.3", box([0, 10, 0], 1)),
    record("o1.4", box([0, -10, 0], 1)),
    record("o1.5", box([0, 0, 10], 1))
  ];
  const bounds = { min: [-11, -11, -1], max: [11, 11, 11] };
  const { offsets } = explode(records, bounds);

  assert.ok(offsets.get("o1.1")[0] > 1, "right part moves +X");
  assert.ok(offsets.get("o1.2")[0] < -1, "left part moves -X");
  assert.ok(offsets.get("o1.3")[1] > 1, "back part moves +Y");
  assert.ok(offsets.get("o1.4")[1] < -1, "front part moves -Y");
  assert.ok(offsets.get("o1.5")[2] > 1, "top part moves +Z");
  // Radial: every offset is parallel to the part's direction from the center.
  for (const [partId, offset] of offsets) {
    const center = records.find((r) => r.partId === partId).partBounds;
    const dir = [
      (center.min[0] + center.max[0]) / 2,
      (center.min[1] + center.max[1]) / 2,
      (center.min[2] + center.max[2]) / 2 - 4.5 // model center z
    ];
    const cross = Math.hypot(
      dir[1] * offset[2] - dir[2] * offset[1],
      dir[2] * offset[0] - dir[0] * offset[2],
      dir[0] * offset[1] - dir[1] * offset[0]
    );
    assert.ok(cross < length(dir) * length(offset) * 0.35, `${partId} moves roughly radially`);
  }
});

test("a coaxial stack telescopes along its stacking axis", () => {
  // Washers stacked in Z with a common XY center: the only separating
  // direction is Z, and it must fall out of the radial rule automatically.
  const records = [
    record("o1.1", { min: [-5, -5, 0], max: [5, 5, 2] }),
    record("o1.2", { min: [-5, -5, 2], max: [5, 5, 4] }),
    record("o1.3", { min: [-5, -5, 4], max: [5, 5, 6] })
  ];
  const bounds = { min: [-5, -5, 0], max: [5, 5, 6] };
  const { offsets } = explode(records, bounds);

  assert.ok(offsets.get("o1.1")[2] < 0, "bottom washer moves down");
  assert.ok(Math.abs(offsets.get("o1.2")[2]) < 1e-6, "middle washer stays");
  assert.ok(offsets.get("o1.3")[2] > 0, "top washer moves up");
  for (const offset of offsets.values()) {
    assert.ok(Math.abs(offset[0]) < 1e-6 && Math.abs(offset[1]) < 1e-6, "no sideways scatter");
  }
});

test("a concentric core anchors while the ring blooms", () => {
  // A central column with a bolt circle: the column has no radial direction
  // and anchors; the bolts fan outward in the ring plane.
  const records = [
    record("o1.1", { min: [-2, -2, 0], max: [2, 2, 20] }),
    record("o1.2", box([8, 0, 10], 1)),
    record("o1.3", box([-8, 0, 10], 1)),
    record("o1.4", box([0, 8, 10], 1)),
    record("o1.5", box([0, -8, 10], 1))
  ];
  const bounds = { min: [-9, -9, 0], max: [9, 9, 20] };
  const { offsets } = explode(records, bounds);

  assert.ok(length(offsets.get("o1.1")) < 1e-6, "core column stays put");
  assert.ok(offsets.get("o1.2")[0] > 4, "bolt moves outward");
  assert.ok(offsets.get("o1.3")[0] < -4, "opposite bolt moves the other way");
  assert.ok(offsets.get("o1.4")[1] > 4);
  assert.ok(offsets.get("o1.5")[1] < -4);
});

test("fully concentric parts telescope out along their long axis", () => {
  // A shaft inside a housing, both centered at the origin: the housing (larger)
  // anchors and the shaft pulls out along its own long axis.
  const records = [
    record("o1.1", { min: [-10, -10, -10], max: [10, 10, 10] }),
    record("o1.2", { min: [-1, -1, -9], max: [1, 1, 9] })
  ];
  const bounds = { min: [-10, -10, -10], max: [10, 10, 10] };
  const { offsets } = explode(records, bounds);

  assert.ok(length(offsets.get("o1.1")) < 1e-6, "housing anchors");
  const shaft = offsets.get("o1.2");
  assert.ok(Math.abs(shaft[2]) > 10, "shaft telescopes along Z");
  assert.ok(Math.abs(shaft[0]) < 1e-6 && Math.abs(shaft[1]) < 1e-6);
});

test("subassemblies separate first, then bloom internally (cascade)", () => {
  const records = [
    record("o1.1.1", box([-10, -1.5, 0], 1)),
    record("o1.1.2", box([-10, 1.5, 0], 1)),
    record("o1.2.1", box([10, -1.5, 0], 1)),
    record("o1.2.2", box([10, 1.5, 0], 1))
  ];
  const bounds = { min: [-11, -3, -1], max: [11, 3, 1] };
  const { layout } = explode(records, bounds);
  assert.equal(layout.levelCount, 2);

  // Early in the scrub only level 1 has advanced: subassembly moves rigidly.
  const early = explode(records, bounds, 0.3).offsets;
  assert.ok(length(early.get("o1.1.1")) > 0.5, "subassembly is moving");
  const delta = [
    early.get("o1.1.1")[0] - early.get("o1.1.2")[0],
    early.get("o1.1.1")[1] - early.get("o1.1.2")[1],
    early.get("o1.1.1")[2] - early.get("o1.1.2")[2]
  ];
  assert.ok(length(delta) < 0.15, "parts within a subassembly still move together early on");

  // At full explode the internal bloom has separated them too.
  const full = explode(records, bounds, 1).offsets;
  assert.ok(full.get("o1.1.1")[1] < full.get("o1.1.2")[1], "parts bloom apart within the subassembly");
  assert.ok(full.get("o1.1.1")[0] < -1 && full.get("o1.2.1")[0] > 1, "subassemblies separated radially");
});

test("scrub is monotonic: parts only move outward as the slider advances", () => {
  const records = [
    record("o1.1.1", box([-10, -1.5, 0], 1)),
    record("o1.1.2", box([-10, 1.5, 0], 1)),
    record("o1.2", box([10, 0, 0], 2))
  ];
  const bounds = { min: [-11, -3, -2], max: [12, 3, 2] };
  let previous = 0;
  for (const progress of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
    const { offsets } = explode(records, bounds, progress);
    const total = [...offsets.values()].reduce((sum, offset) => sum + length(offset), 0);
    assert.ok(total >= previous - 1e-9, `travel does not regress at ${progress}`);
    previous = total;
  }
  assert.ok(previous > 0, "full explode moves parts");
});

test("siblings never overlap at full explode, even with nearby centers", () => {
  // Large bodies whose centers sit close together: proportional radial moves
  // alone leave them intersecting, so the separation sweep must clear them.
  const records = [
    record("o1.1", { min: [-10, -10, -10], max: [8, 10, 10] }),
    record("o1.2", { min: [-8, -10, -10], max: [10, 10, 10] }),
    record("o1.3", { min: [-9, -8, -10], max: [9, 12, 10] })
  ];
  const bounds = { min: [-10, -10, -10], max: [10, 12, 10] };
  const layout = computeExplodedViewLayout(records, bounds);
  applyExplodedViewProgress(THREE, layout, 1);
  const shifted = records.map((r) => {
    const m = r.explodedViewMatrix;
    const offset = m ? [m.elements[12], m.elements[13], m.elements[14]] : [0, 0, 0];
    return {
      min: r.partBounds.min.map((value, axis) => value + offset[axis]),
      max: r.partBounds.max.map((value, axis) => value + offset[axis])
    };
  });
  for (let i = 0; i < shifted.length; i += 1) {
    for (let j = i + 1; j < shifted.length; j += 1) {
      const disjoint = [0, 1, 2].some((axis) => (
        shifted[i].max[axis] <= shifted[j].min[axis] ||
        shifted[j].max[axis] <= shifted[i].min[axis]
      ));
      assert.ok(disjoint, `parts ${i} and ${j} are separated at full explode`);
    }
  }
});

test("progress 0 clears every record matrix", () => {
  const records = [
    record("o1.1", box([-5, 0, 0], 1)),
    record("o1.2", box([5, 0, 0], 1))
  ];
  const bounds = { min: [-6, -1, -1], max: [6, 1, 1] };
  const layout = computeExplodedViewLayout(records, bounds);
  applyExplodedViewProgress(THREE, layout, 1);
  assert.ok(records.some((r) => r.explodedViewMatrix));
  applyExplodedViewProgress(THREE, layout, 0);
  assert.ok(records.every((r) => r.explodedViewMatrix === null));
});

test("explodedViewBounds expands with the explode", () => {
  const records = [
    record("o1.1", box([-5, 0, 0], 1)),
    record("o1.2", box([5, 0, 0], 1))
  ];
  const bounds = { min: [-6, -1, -1], max: [6, 1, 1] };
  const layout = computeExplodedViewLayout(records, bounds);
  const exploded = explodedViewBounds(layout, bounds, 1);
  assert.ok(exploded.min[0] < bounds.min[0]);
  assert.ok(exploded.max[0] > bounds.max[0]);
  const assembled = explodedViewBounds(layout, bounds, 0);
  assert.deepEqual(assembled.min, [-6, -1, -1]);
  assert.deepEqual(assembled.max, [6, 1, 1]);
});

test("degenerate inputs produce an empty layout", () => {
  assert.equal(computeExplodedViewLayout([], null).entries.length, 0);
  assert.equal(
    computeExplodedViewLayout([record("o1.1", box([0, 0, 0], 1))], null).entries.length,
    0
  );
  const noBounds = [
    { partId: "o1.1", mesh: new THREE.Object3D(), partBounds: null },
    { partId: "o1.2", mesh: new THREE.Object3D(), partBounds: null }
  ];
  assert.equal(computeExplodedViewLayout(noBounds, null).entries.length, 0);
});

test("non-occurrence part ids explode as flat leaves", () => {
  const records = [
    record("part:0", box([-5, 0, 0], 1)),
    record("part:1", box([5, 0, 0], 1))
  ];
  const bounds = { min: [-6, -1, -1], max: [6, 1, 1] };
  const { offsets } = explode(records, bounds);
  assert.ok(offsets.get("part:0")[0] < -1);
  assert.ok(offsets.get("part:1")[0] > 1);
});

test("clearExplodedViewRecords nulls every matrix", () => {
  const records = [
    record("o1.1", box([-5, 0, 0], 1)),
    record("o1.2", box([5, 0, 0], 1))
  ];
  const layout = computeExplodedViewLayout(records, { min: [-6, -1, -1], max: [6, 1, 1] });
  applyExplodedViewProgress(THREE, layout, 1);
  clearExplodedViewRecords(records);
  assert.ok(records.every((r) => r.explodedViewMatrix === null));
});

test("easeExplodedViewProgress clamps and eases out", () => {
  assert.equal(easeExplodedViewProgress(-1), 0);
  assert.equal(easeExplodedViewProgress(2), 1);
  assert.ok(easeExplodedViewProgress(0.5) > 0.5);
});

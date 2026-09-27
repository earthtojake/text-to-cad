import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import {
  adoptEdgePickTable,
  attachEdgePickRaycast,
  edgePickTable,
  EDGE_PICK_LEAF_SEGMENTS,
} from "./edgePickRaycast.js";
import { buildEdgePickLines, syncSelectorPickGroups } from "./selectorPickGroups.js";

// Deterministic PRNG so a failure reproduces.
function rng(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// A synthetic assembly laid out the way the composed proxy is: part by part,
// edge by edge. Each part is a cluster of circles, straight edges and helices
// around its own center; the centers overlap on screen from most directions.
function syntheticEdgeProxy(random, { parts = 40, edgesPerPart = 12, spread = 200 } = {}) {
  const positions = [];
  const indices = [];
  const edgeIds = [];
  let edgeRow = 0;
  for (let part = 0; part < parts; part += 1) {
    const cx = (random() - 0.5) * spread, cy = (random() - 0.5) * spread * 0.3, cz = (random() - 0.5) * spread;
    const size = 5 + random() * 30;
    for (let edge = 0; edge < edgesPerPart; edge += 1) {
      const kind = Math.floor(random() * 3);
      const points = [];
      if (kind === 0) {
        const r = size * (0.2 + random()), n = 8 + Math.floor(random() * 56), axis = Math.floor(random() * 3);
        const ox = cx + (random() - 0.5) * size, oy = cy + (random() - 0.5) * size, oz = cz + (random() - 0.5) * size;
        for (let i = 0; i <= n; i += 1) {
          const a = (i / n) * Math.PI * 2, u = Math.cos(a) * r, v = Math.sin(a) * r;
          points.push(axis === 0 ? [ox, oy + u, oz + v] : axis === 1 ? [ox + u, oy, oz + v] : [ox + u, oy + v, oz]);
        }
      } else if (kind === 1) {
        const a = [cx + (random() - 0.5) * size * 2, cy + (random() - 0.5) * size * 2, cz + (random() - 0.5) * size * 2];
        const b = [cx + (random() - 0.5) * size * 2, cy + (random() - 0.5) * size * 2, cz + (random() - 0.5) * size * 2];
        // Axis-aligned straight edges too, the common CAD case.
        if (random() < 0.5) { b[1] = a[1]; b[2] = a[2]; }
        const n = 1 + Math.floor(random() * 4);
        for (let i = 0; i <= n; i += 1) points.push(a.map((value, k) => value + (b[k] - value) * (i / n)));
      } else {
        const r = size * 0.3, n = 40 + Math.floor(random() * 80), pitch = size * 0.05;
        for (let i = 0; i <= n; i += 1) {
          const a = (i / 12) * Math.PI * 2;
          points.push([cx + Math.cos(a) * r, cy + i * pitch * 0.1, cz + Math.sin(a) * r]);
        }
      }
      const base = positions.length / 3;
      for (const point of points) positions.push(...point);
      for (let i = 0; i + 1 < points.length; i += 1) {
        indices.push(base + i, base + i + 1);
        edgeIds.push(edgeRow);
      }
      edgeRow += 1;
    }
  }
  return {
    edgePositions: new Float32Array(positions),
    edgeIndices: new Uint32Array(indices),
    edgeIds: new Uint32Array(edgeIds),
  };
}

function stockLines(geometry, source) {
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial());
  lines.position.copy(source.position);
  lines.quaternion.copy(source.quaternion);
  lines.scale.copy(source.scale);
  lines.updateMatrixWorld(true);
  return lines;
}

function summarize(intersections) {
  return intersections.map(({ distance, point, index, face, faceIndex, barycoord }) => ({
    distance, point: point.toArray(), index, face, faceIndex, barycoord,
  }));
}

function randomRay(random, center, radius) {
  const target = new THREE.Vector3(
    center.x + (random() - 0.5) * radius * 1.6,
    center.y + (random() - 0.5) * radius * 0.6,
    center.z + (random() - 0.5) * radius * 1.6,
  );
  const style = random();
  let direction;
  if (style < 0.2) {
    // Axis-aligned views: zero direction components.
    const axis = Math.floor(random() * 3);
    direction = new THREE.Vector3(axis === 0 ? 1 : 0, axis === 1 ? 1 : 0, axis === 2 ? 1 : 0)
      .multiplyScalar(random() < 0.5 ? -1 : 1);
  } else {
    direction = new THREE.Vector3(random() - 0.5, random() - 0.5, random() - 0.5).normalize();
  }
  // From far outside down to inside the model.
  const distance = radius * (style < 0.9 ? 0.2 + random() * 6 : random() * 0.2);
  const origin = target.clone().addScaledVector(direction, -distance);
  return new THREE.Ray(origin, direction);
}

function differential({ seed, rays, transform = null, parts = 40 }) {
  const random = rng(seed);
  const proxy = syntheticEdgeProxy(random, { parts });
  const lines = buildEdgePickLines(THREE, { proxy });
  if (transform) transform(lines);
  lines.updateMatrixWorld(true);
  const stock = stockLines(lines.geometry, lines);
  lines.geometry.computeBoundingSphere();
  const sphere = lines.geometry.boundingSphere.clone().applyMatrix4(lines.matrixWorld);
  const raycaster = new THREE.Raycaster();
  const segmentCount = proxy.edgeIndices.length / 2;
  let hitRays = 0, multiHitRays = 0, totalHits = 0;
  for (let i = 0; i < rays; i += 1) {
    const ray = randomRay(random, sphere.center, sphere.radius);
    raycaster.ray.copy(ray);
    // Pick thresholds from sub-pixel to very coarse, relative to the model.
    raycaster.params.Line.threshold = sphere.radius * 10 ** (-4 + random() * 3.5);
    raycaster.near = random() < 0.2 ? random() * sphere.radius : 0;
    raycaster.far = random() < 0.2 ? sphere.radius * (0.5 + random() * 3) : Infinity;
    const expected = summarize(raycaster.intersectObject(stock, false));
    const actual = raycaster.intersectObject(lines, false);
    assert.ok(actual.every((hit) => hit.object === lines));
    assert.deepEqual(summarize(actual), expected, `ray ${i} (seed ${seed})`);
    assert.equal(lines.geometry.drawRange.start, 0);
    assert.equal(lines.geometry.drawRange.count, Infinity);
    if (expected.length) hitRays += 1;
    if (expected.length > 1) multiHitRays += 1;
    totalHits += expected.length;
  }
  return { segmentCount, hitRays, multiHitRays, totalHits };
}

test("culled edge raycast returns exactly the stock LineSegments intersections", () => {
  const result = differential({ seed: 1, rays: 1000, parts: 30 });
  assert.ok(result.segmentCount > 5000, `synthetic proxy has ${result.segmentCount} segments`);
  // The comparison is not vacuous: most rays hit, many hit several segments.
  assert.ok(result.hitRays > 300, `${result.hitRays} rays hit`);
  assert.ok(result.multiHitRays > 150, `${result.multiHitRays} rays hit more than one segment`);
});

test("culled edge raycast matches under a moved, rotated and scaled pick object", () => {
  for (const [seed, transform] of [
    [2, (lines) => lines.position.set(120, -40, 75)],
    [3, (lines) => { lines.rotation.set(0.3, 1.1, -0.4); lines.position.set(-3, 9, 1); }],
    [4, (lines) => lines.scale.set(2.5, 2.5, 2.5)],
    [5, (lines) => { lines.scale.set(0.5, 1.5, 3); lines.rotation.set(0.1, 0.2, 0.3); }],
    [6, (lines) => lines.scale.set(-1, 1, 1)],
  ]) {
    const result = differential({ seed, rays: 300, transform, parts: 16 });
    assert.ok(result.hitRays > 30, `seed ${seed}: ${result.hitRays} rays hit`);
  }
});

test("culled edge raycast matches on the threshold boundary and for near-parallel rays", () => {
  // Where three's rounding decides the hit: rays exactly at the pick distance
  // from a segment, and rays (nearly) along a segment from far away.
  const random = rng(10);
  const proxy = syntheticEdgeProxy(random, { parts: 16 });
  const lines = buildEdgePickLines(THREE, { proxy });
  lines.updateMatrixWorld(true);
  const stock = stockLines(lines.geometry, lines);
  const positions = proxy.edgePositions;
  const indices = proxy.edgeIndices;
  const raycaster = new THREE.Raycaster();
  let hitRays = 0;
  for (let i = 0; i < 600; i += 1) {
    const segment = Math.floor(random() * (indices.length / 2));
    const a = new THREE.Vector3().fromArray(positions, indices[segment * 2] * 3);
    const b = new THREE.Vector3().fromArray(positions, indices[segment * 2 + 1] * 3);
    const along = b.clone().sub(a);
    if (along.lengthSq() === 0) continue;
    along.normalize();
    const threshold = 10 ** (-3 + random() * 3);
    const normal = new THREE.Vector3(random() - 0.5, random() - 0.5, random() - 0.5).cross(along).normalize();
    const mid = a.clone().lerp(b, random());
    let direction;
    let origin;
    if (i % 2) {
      // Perpendicular-ish ray grazing the segment at the threshold (+- ulps).
      direction = normal.clone().cross(along).normalize();
      const offset = normal.clone().multiplyScalar(threshold * (1 + (random() - 0.5) * 1e-6));
      origin = mid.clone().add(offset).addScaledVector(direction, -(50 + random() * 5000));
    } else {
      // Along the segment within 1e-9..1e-3 rad, from far away.
      const tilt = 10 ** (-9 + random() * 6);
      direction = along.clone().addScaledVector(normal, tilt).normalize().multiplyScalar(random() < 0.5 ? 1 : -1);
      origin = mid.clone()
        .addScaledVector(normal, threshold * (random() * 2))
        .addScaledVector(direction, -(50 + random() * 50000));
    }
    raycaster.set(origin, direction);
    raycaster.params.Line.threshold = threshold;
    const expected = summarize(raycaster.intersectObject(stock, false));
    hitRays += expected.length ? 1 : 0;
    assert.deepEqual(summarize(raycaster.intersectObject(lines, false)), expected, `ray ${i}`);
  }
  assert.ok(hitRays > 100, `${hitRays} rays hit`);
});

test("culled edge raycast visits only the segment runs near the ray", () => {
  const random = rng(7);
  const proxy = syntheticEdgeProxy(random, { parts: 60 });
  const lines = buildEdgePickLines(THREE, { proxy });
  lines.updateMatrixWorld(true);
  const raycaster = new THREE.Raycaster(new THREE.Vector3(0, 0, 1000), new THREE.Vector3(0, 0, -1));
  raycaster.params.Line.threshold = 0.5;
  const visited = [];
  const base = THREE.LineSegments.prototype.raycast;
  THREE.LineSegments.prototype.raycast = function spy(...args) {
    visited.push(this.geometry.drawRange.count / 2);
    return base.apply(this, args);
  };
  try {
    raycaster.intersectObject(lines, false);
  } finally {
    THREE.LineSegments.prototype.raycast = base;
  }
  const scanned = visited.reduce((sum, count) => sum + Math.min(count, proxy.edgeIndices.length / 2), 0);
  assert.ok(scanned < proxy.edgeIndices.length / 2 / 4, `scanned ${scanned} of ${proxy.edgeIndices.length / 2}`);
});

test("segments three can only evaluate to NaN are never culled", () => {
  const positions = new Float32Array([
    0, 0, 0, 1, 0, 0,
    NaN, 5, 5, 6, 5, 5,
    100, 100, 100, 101, 100, 100,
  ]);
  const indices = new Uint32Array([
    0, 1,
    // Far away, then a NaN endpoint, then an index past the positions.
    4, 5,
    2, 3,
    4, 99,
    ...Array.from({ length: EDGE_PICK_LEAF_SEGMENTS * 2 }, (_, i) => 4 + (i % 2)),
  ]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  // A NaN in the data makes three's bounding sphere NaN too, so give it the
  // sphere a real proxy would have to reach the per-segment test at all.
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(50, 50, 50), 1000);
  const lines = attachEdgePickRaycast(new THREE.LineSegments(geometry, new THREE.LineBasicMaterial()));
  const stock = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial());
  const raycaster = new THREE.Raycaster(new THREE.Vector3(0.5, -10, 0), new THREE.Vector3(0, 1, 0));
  raycaster.params.Line.threshold = 0.1;
  const expected = summarize(raycaster.intersectObject(stock, false));
  assert.ok(expected.length >= 3, "the NaN segments and the real one all report");
  assert.deepEqual(summarize(raycaster.intersectObject(lines, false)), expected);
});

test("a proxy that only grew keeps its boxes; any other change rebuilds", () => {
  const random = rng(8);
  const first = syntheticEdgeProxy(random, { parts: 20 });
  const appended = syntheticEdgeProxy(random, { parts: 20 });
  const vertexOffset = first.edgePositions.length / 3;
  const grown = {
    edgePositions: new Float32Array([...first.edgePositions, ...appended.edgePositions]),
    edgeIndices: new Uint32Array([...first.edgeIndices, ...Array.from(appended.edgeIndices, (i) => i + vertexOffset)]),
    edgeIds: new Uint32Array([...first.edgeIds, ...appended.edgeIds]),
  };
  const runtime = {
    THREE,
    facePickGroup: new THREE.Group(),
    edgePickGroup: new THREE.Group(),
    raycastBvhOptions: { maxTriangles: 0 },
  };
  syncSelectorPickGroups(runtime, { proxy: first });
  const firstGeometry = runtime.edgePickLines.geometry;
  // Never raycast: nothing is carried to the next sync.
  syncSelectorPickGroups(runtime, { proxy: first });
  assert.notEqual(runtime.edgePickLines.geometry, firstGeometry);
  const firstTable = edgePickTable(runtime.edgePickLines.geometry);

  // Same arrays: the table is shared, not rebuilt.
  syncSelectorPickGroups(runtime, { proxy: first });
  assert.equal(edgePickTable(runtime.edgePickLines.geometry), firstTable);

  // Appended: the complete leaves are reused.
  syncSelectorPickGroups(runtime, { proxy: grown });
  const grownTable = edgePickTable(runtime.edgePickLines.geometry);
  const firstLeaves = Math.floor(firstTable.segmentCount / EDGE_PICK_LEAF_SEGMENTS);
  assert.equal(grownTable.reusedSegments, firstLeaves * EDGE_PICK_LEAF_SEGMENTS);
  // And the reused table is the one a fresh build makes.
  const fresh = buildEdgePickLines(THREE, { proxy: { ...grown, edgePositions: grown.edgePositions.slice() } });
  const freshTable = edgePickTable(fresh.geometry);
  assert.equal(freshTable.reusedSegments, 0);
  assert.deepEqual([...grownTable.leafBounds], [...freshTable.leafBounds]);
  assert.deepEqual([...grownTable.groupBounds], [...freshTable.groupBounds]);

  // Moved (a pose): not a prefix, so nothing is reused.
  const moved = { ...grown, edgePositions: grown.edgePositions.map((value, i) => (i === 3 ? value + 1 : value)) };
  syncSelectorPickGroups(runtime, { proxy: moved });
  assert.equal(edgePickTable(runtime.edgePickLines.geometry).reusedSegments, 0);

  // Shrunk (parts removed): nothing is reused.
  const priorGeometry = runtime.edgePickLines.geometry;
  const shrunk = { ...first, edgePositions: first.edgePositions.slice() };
  syncSelectorPickGroups(runtime, { proxy: shrunk });
  assert.equal(adoptEdgePickTable(runtime.edgePickLines.geometry, priorGeometry), false);

  // Picks through an adopted (prefix-reused) table match the stock scan.
  const prefix = { ...first, edgePositions: first.edgePositions.slice(), edgeIndices: first.edgeIndices.slice() };
  syncSelectorPickGroups(runtime, { proxy: prefix });
  edgePickTable(runtime.edgePickLines.geometry);
  const regrown = { ...grown, edgePositions: grown.edgePositions.slice(), edgeIndices: grown.edgeIndices.slice() };
  syncSelectorPickGroups(runtime, { proxy: regrown });
  assert.ok(edgePickTable(runtime.edgePickLines.geometry).reusedSegments > 0);
  const lines = runtime.edgePickLines;
  lines.updateMatrixWorld(true);
  const stock = stockLines(lines.geometry, lines);
  const raycaster = new THREE.Raycaster();
  const rayRandom = rng(9);
  lines.geometry.computeBoundingSphere();
  const { center, radius } = lines.geometry.boundingSphere;
  let hits = 0;
  for (let i = 0; i < 150; i += 1) {
    raycaster.ray.copy(randomRay(rayRandom, center, radius));
    raycaster.params.Line.threshold = radius * 10 ** (-3 + rayRandom() * 2);
    const expected = summarize(raycaster.intersectObject(stock, false));
    hits += expected.length ? 1 : 0;
    assert.deepEqual(summarize(raycaster.intersectObject(lines, false)), expected);
  }
  assert.ok(hits > 20, `${hits} rays hit`);
});

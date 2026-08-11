import assert from "node:assert/strict";
import test from "node:test";

import { meshImplicitCadModel } from "./mesh.js";
import { meshImplicitCadModelParallel, planeCounts, sdfEvaluatorPayload } from "./meshWorkers.js";
import { normalizeImplicitCadModel } from "./model.js";

// Small enough to bake in well under a second at these resolutions, and shaped so the mesh
// has both curved and flat regions -- a boolean cut is what produces creased normals, which
// is where a per-worker normal cache could diverge from the serial one if it were not pure.
const MODEL = {
  name: "worker test shape",
  units: "mm",
  bounds: 12,
  glsl: `
    float sdf(vec3 p) {
      float sphere = length(p) - 8.0;
      float slab = p.z - 3.0;
      return max(sphere, -slab);
    }
  `,
};

const OPTIONS = { resolution: 12, smoothNormals: true };

function assertIdentical(actual, expected, label) {
  assert.equal(actual.positions.length, expected.positions.length, `${label}: vertex count`);
  assert.equal(actual.normals.length, expected.normals.length, `${label}: normal count`);
  for (let index = 0; index < expected.positions.length; index += 1) {
    // Object.is, not a tolerance: the parallel mesher promises the SAME BYTES, and a
    // tolerance would hide exactly the drift (a differently-seeded normal cache, a slab
    // concatenated out of order) this test exists to catch.
    assert.ok(
      Object.is(actual.positions[index], expected.positions[index]),
      `${label}: position ${index} ${actual.positions[index]} != ${expected.positions[index]}`
    );
    assert.ok(
      Object.is(actual.normals[index], expected.normals[index]),
      `${label}: normal ${index} ${actual.normals[index]} != ${expected.normals[index]}`
    );
  }
}

test("parallel meshing is byte-identical to the serial mesher", async () => {
  const serial = meshImplicitCadModel(MODEL, OPTIONS);
  assert.ok(serial.triangleCount > 0);
  for (const threads of [2, 3, 4]) {
    const parallel = await meshImplicitCadModelParallel(MODEL, { ...OPTIONS, threads });
    assertIdentical(parallel, serial, `threads=${threads}`);
    assert.equal(parallel.triangleCount, serial.triangleCount);
  }
});

test("chunking does not change the output", async () => {
  // Slab outputs are concatenated in CHUNK order, not completion order. Changing the chunk
  // size changes which worker draws which slab and in what order they come back, so identical
  // output across chunk sizes is what proves the ordering is by construction.
  const serial = meshImplicitCadModel(MODEL, OPTIONS);
  for (const chunksPerWorker of [1, 2, 8]) {
    const parallel = await meshImplicitCadModelParallel(MODEL, {
      ...OPTIONS,
      threads: 3,
      chunksPerWorker,
    });
    assertIdentical(parallel, serial, `chunksPerWorker=${chunksPerWorker}`);
  }
});

test("one thread takes the serial path and still reports both phases", async () => {
  let sampled = 0;
  let polygonized = 0;
  const mesh = await meshImplicitCadModelParallel(MODEL, {
    ...OPTIONS,
    threads: 1,
    onSamplePlane: (count) => { sampled += count; },
    onPolygonizePlane: (count) => { polygonized += count; },
  });
  const planes = planeCounts(MODEL, OPTIONS);
  assertIdentical(mesh, meshImplicitCadModel(MODEL, OPTIONS), "threads=1");
  assert.equal(sampled, planes.sample);
  assert.equal(polygonized, planes.polygonize);
});

test("progress reports exactly one unit per plane, per phase", async () => {
  let sampled = 0;
  let polygonized = 0;
  await meshImplicitCadModelParallel(MODEL, {
    ...OPTIONS,
    threads: 3,
    onSamplePlane: (count = 1) => { sampled += count; },
    onPolygonizePlane: (count = 1) => { polygonized += count; },
  });
  const planes = planeCounts(MODEL, OPTIONS);
  // Denominators the caller can report BEFORE the work starts, which is what makes both
  // phases determinate. Over- or under-counting here would drive a progress bar past 100%
  // or leave it short, and the phases share a `plane` message -- so this also pins that the
  // sample phase's listeners are detached before the polygonize phase starts.
  assert.equal(sampled, planes.sample);
  assert.equal(polygonized, planes.polygonize);
  assert.equal(planes.sample, planes.polygonize + 1);
});

test("the evaluator payload a worker receives is structuredClone-able", () => {
  // Workers cannot be handed the SDF closure, so the payload has to survive the postMessage
  // boundary. A model object does not (its definition holds functions); this slice must.
  const payload = sdfEvaluatorPayload(normalizeImplicitCadModel(MODEL));
  const cloned = structuredClone(payload);
  assert.equal(cloned.glslSource, payload.glslSource);
  assert.deepEqual(cloned.uniforms, payload.uniforms);
});

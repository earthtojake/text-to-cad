import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder, MeshoptEncoder } from "meshoptimizer";

import { UNSIGNED_SHORT_VERTEX_LIMIT, weldMesh, writeGlb } from "./writeGlb.js";
import { srgbToLinear } from "./bytes.js";

/** A unit cube as a non-indexed triangle soup: 12 triangles, 36 loose vertices. */
function cubeSoup(size = 10) {
  const s = size / 2;
  const corners = [
    [-s, -s, -s], [s, -s, -s], [s, s, -s], [-s, s, -s],
    [-s, -s, s], [s, -s, s], [s, s, s], [-s, s, s],
  ];
  const quads = [
    [0, 1, 2, 3], [5, 4, 7, 6], [4, 0, 3, 7],
    [1, 5, 6, 2], [4, 5, 1, 0], [3, 2, 6, 7],
  ];
  const out = [];
  for (const [a, b, c, d] of quads) {
    for (const [i, j, k] of [[a, b, c], [a, c, d]]) {
      out.push(...corners[i], ...corners[j], ...corners[k]);
    }
  }
  return new Float32Array(out);
}

function parseGlb(bytes, { withMeshopt = false } = {}) {
  const loader = new GLTFLoader();
  if (withMeshopt) {
    loader.setMeshoptDecoder(MeshoptDecoder);
  }
  const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return new Promise((resolve, reject) => {
    loader.parse(copy, "", resolve, reject);
  });
}

function collectMeshes(gltf) {
  const meshes = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      meshes.push(node);
    }
  });
  return meshes;
}

/** World-space bounding box, so a quantized mesh is compared where it actually renders. */
function worldBounds(mesh) {
  const position = mesh.geometry.getAttribute("position");
  mesh.updateWorldMatrix(true, false);
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < position.count; i += 1) {
    const v = [position.getX(i), position.getY(i), position.getZ(i)];
    const e = mesh.matrixWorld.elements;
    const world = [
      e[0] * v[0] + e[4] * v[1] + e[8] * v[2] + e[12],
      e[1] * v[0] + e[5] * v[1] + e[9] * v[2] + e[13],
      e[2] * v[0] + e[6] * v[1] + e[10] * v[2] + e[14],
    ];
    for (let a = 0; a < 3; a += 1) {
      min[a] = Math.min(min[a], world[a]);
      max[a] = Math.max(max[a], world[a]);
    }
  }
  return { min, max };
}

test("weldMesh collapses a cube soup to 24 vertices and keeps creases", () => {
  const welded = weldMesh(cubeSoup(), null);
  // 6 faces x 4 corners: shared positions must NOT merge across faces, because their
  // normals differ. Merging them is the smooth-shading artefact this keying exists to avoid.
  assert.equal(welded.positions.length / 3, 24);
  assert.equal(welded.indices.length, 36);
});

test("weldMesh is deterministic", () => {
  const a = weldMesh(cubeSoup(), null);
  const b = weldMesh(cubeSoup(), null);
  assert.deepEqual([...a.indices], [...b.indices]);
  assert.deepEqual([...a.positions], [...b.positions]);
});

test("export preset loads in a STOCK GLTFLoader with no meshopt decoder", async () => {
  const bytes = writeGlb({ primitives: [{ positions: cubeSoup(10) }] }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const meshes = collectMeshes(gltf);
  assert.equal(meshes.length, 1);
  const geometry = meshes[0].geometry;
  assert.ok(geometry.index, "export preset must be indexed");
  assert.equal(geometry.getAttribute("position").count, 24);
  assert.equal(geometry.index.count, 36);
  const bounds = worldBounds(meshes[0]);
  bounds.min.forEach((v) => assert.ok(Math.abs(v + 5) < 1e-5, `min ${v}`));
  bounds.max.forEach((v) => assert.ok(Math.abs(v - 5) < 1e-5, `max ${v}`));
});

test("export preset declares no required extensions", async () => {
  const bytes = writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export" });
  const json = JSON.parse(
    new TextDecoder().decode(bytes.subarray(20, 20 + new DataView(
      bytes.buffer, bytes.byteOffset, bytes.byteLength
    ).getUint32(12, true)))
  );
  assert.equal(json.extensionsRequired, undefined);
  assert.equal(json.extensionsUsed, undefined);
});

test("render preset round-trips through GLTFLoader + MeshoptDecoder", async () => {
  await MeshoptEncoder.ready;
  await MeshoptDecoder.ready;
  const bytes = writeGlb(
    { primitives: [{ positions: cubeSoup(10) }] },
    { preset: "render", encoder: MeshoptEncoder }
  );
  const gltf = await parseGlb(bytes, { withMeshopt: true });
  const meshes = collectMeshes(gltf);
  assert.equal(meshes.length, 1);
  const geometry = meshes[0].geometry;
  assert.ok(geometry.index, "render preset must be indexed");
  assert.equal(geometry.getAttribute("position").count, 24);
  assert.equal(geometry.index.count, 36);

  // Quantization is lossy, but the node scale/translation must put the mesh back where it
  // belongs. A 10mm cube quantized over its own bounds should land well inside 0.01mm.
  const bounds = worldBounds(meshes[0]);
  bounds.min.forEach((v) => assert.ok(Math.abs(v + 5) < 0.01, `min ${v}`));
  bounds.max.forEach((v) => assert.ok(Math.abs(v - 5) < 0.01, `max ${v}`));
});

test("render preset refuses to run without an encoder", () => {
  assert.throws(
    () => writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "render" }),
    /requires meshoptimizer/
  );
});

test("multiple primitives become one node each, with occurrence ids", async () => {
  const bytes = writeGlb({
    primitives: [
      { positions: cubeSoup(4), name: "layer:0", occurrenceId: "toolpath:layer:0", color: "#ff0000" },
      { positions: cubeSoup(6), name: "layer:1", occurrenceId: "toolpath:layer:1", color: "#00ff00" },
      { positions: cubeSoup(8), name: "travel", occurrenceId: "toolpath:travel", color: "#0000ff" },
    ],
  }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const meshes = collectMeshes(gltf);
  assert.equal(meshes.length, 3, "one node per primitive drives per-layer visibility");
  assert.deepEqual(
    meshes.map((m) => m.userData?.cadOccurrenceId),
    ["toolpath:layer:0", "toolpath:layer:1", "toolpath:travel"]
  );
  // Per-primitive materials keep constant colour out of the vertex buffer.
  const colors = meshes.map((m) => m.material.color.getHexString());
  assert.equal(new Set(colors).size, 3, `expected 3 distinct materials, got ${colors}`);
});

test("a small primitive indexes in UNSIGNED_SHORT", async () => {
  const bytes = writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const index = collectMeshes(gltf)[0].geometry.index;
  assert.equal(index.array.constructor, Uint16Array);
  assert.ok(UNSIGNED_SHORT_VERTEX_LIMIT === 65535);
});

test("empty input produces a loadable, empty scene", async () => {
  const bytes = writeGlb({ primitives: [] }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  assert.equal(collectMeshes(gltf).length, 0);
});

test("srgbToLinear matches the sRGB piecewise transfer function", () => {
  assert.equal(srgbToLinear(0), 0);
  assert.equal(srgbToLinear(1), 1);
  // Below the knee the curve is a plain 1/12.92 slope.
  assert.ok(Math.abs(srgbToLinear(0.04) - 0.04 / 12.92) < 1e-12);
  // Mid grey is where treating sRGB as linear is most obviously wrong: 0.5 -> ~0.214.
  assert.ok(Math.abs(srgbToLinear(0.5) - 0.21404114) < 1e-6, srgbToLinear(0.5));
  // Monotonic, and always at or below the input (the curve darkens).
  for (let step = 0; step <= 20; step += 1) {
    const value = step / 20;
    assert.ok(srgbToLinear(value) <= value + 1e-12, `srgbToLinear(${value})`);
  }
});

// The end-to-end statement of what Step 2 is for: an authored sRGB hex must survive the round
// trip and come back as ITSELF. glTF says baseColorFactor is linear and three.js reads it with
// LinearSRGBColorSpace, so writing the sRGB value straight in made every generated GLB render
// brighter than authored. With the conversion, write-then-read is the identity.
test("an authored colour round-trips through GLB as the same sRGB hex", async () => {
  const authored = ["#24e6c2", "#fff45a", "#7c5cff", "#804020", "#000000", "#ffffff"];
  const bytes = writeGlb({
    primitives: authored.map((color, index) => ({
      positions: cubeSoup(4 + index),
      name: `swatch:${index}`,
      color,
    })),
  }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const readBack = collectMeshes(gltf).map((mesh) => `#${mesh.material.color.getHexString()}`);
  assert.deepEqual(readBack, authored);
});

test("an unreadable sentinel is reported as a read failure, not a lock violation", async () => {
  // Issue #269: a mandatory Windows lock made the sentinel unreadable, the catch collapsed that
  // into "", and the error then claimed the run id did not match a file that held exactly the
  // right run id. The two failures must not wear the same message.
  const { assertWriteLock, writeLockPath } = await import("./assertWriteLock.js");
  const directory = await fs.promises.mkdtemp(path.join(os.tmpdir(), "writelock-"));
  const packageDir = path.join(directory, "part.step.py");
  await fs.promises.mkdir(packageDir, { recursive: true });
  const sentinel = writeLockPath(packageDir);

  // A directory where the sentinel should be is unreadable in the same way a locked file is:
  // readFileSync throws rather than returning bytes.
  await fs.promises.mkdir(sentinel, { recursive: true });
  assert.throws(
    () => assertWriteLock(packageDir, "a".repeat(32)),
    (error) => {
      assert.match(error.message, /could not read the generation sentinel/u);
      assert.doesNotMatch(error.message, /does not match/u, "must not blame the run id");
      return true;
    }
  );
  await fs.promises.rm(sentinel, { recursive: true, force: true });

  // A readable sentinel with the wrong id still reports a mismatch.
  await fs.promises.writeFile(sentinel, "b".repeat(32));
  assert.throws(
    () => assertWriteLock(packageDir, "a".repeat(32)),
    /does not match/u
  );
  // And the matching case passes.
  await fs.promises.writeFile(sentinel, "a".repeat(32));
  assertWriteLock(packageDir, "a".repeat(32));
});

test("a missing sentinel is not described as a read failure either", async () => {
  // Three different things, three different messages: nothing ever held this lock, the
  // sentinel exists but cannot be read, the id is wrong. The first is where a degraded run
  // used to land, wearing the second's message and blaming ENOENT for a lock nobody took.
  const { assertWriteLock } = await import("./assertWriteLock.js");
  const directory = await fs.promises.mkdtemp(path.join(os.tmpdir(), "writelock-"));
  const packageDir = path.join(directory, "part.step.py");
  await fs.promises.mkdir(packageDir, { recursive: true });

  assert.throws(
    () => assertWriteLock(packageDir, "a".repeat(32)),
    (error) => {
      assert.match(error.message, /no generation lock exists/u);
      assert.doesNotMatch(error.message, /could not read/u);
      return true;
    }
  );
});

test("a parent-reported degraded lock skips the check instead of failing the build", async () => {
  // A filesystem without advisory locks stamps no run id, so this check cannot pass -- and
  // Python's own policy is that a missing lock must never fail a user's build. Only the
  // parent knows, so it says so; the child must not turn that into a lock violation.
  const { assertWriteLock } = await import("./assertWriteLock.js");
  const directory = await fs.promises.mkdtemp(path.join(os.tmpdir(), "writelock-"));
  const packageDir = path.join(directory, "part.step.py");
  await fs.promises.mkdir(packageDir, { recursive: true });

  const warnings = [];
  const realWarn = console.warn;
  console.warn = (message) => warnings.push(String(message));
  try {
    // No sentinel at all, which is exactly what a degraded run leaves behind.
    assertWriteLock(packageDir, "a".repeat(32), { degraded: true });
    assert.equal(warnings.length, 1, "the write is unguarded, so it must say so");
    assert.match(warnings[0], /without mutual exclusion/u);
  } finally {
    console.warn = realWarn;
  }

  // The flag is the PARENT's report, not a default: without it the same directory still
  // throws, so a producer that forgets to pass a run id is caught exactly as before.
  assert.throws(() => assertWriteLock(packageDir, "a".repeat(32)), /no generation lock exists/u);
});

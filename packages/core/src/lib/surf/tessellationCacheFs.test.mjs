import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { encodeComponentTessellation, tessellationCacheKey } from "./tessellationCache.js";
import {
  TessellationMeshConflictError,
  createFsTessellationCacheProvider,
  probeCachedTessellation,
  readCachedTessellationBytes,
  writeCachedTessellationBytes,
} from "./tessellationCacheFs.mjs";

const D = "1".repeat(64);
const O = "a".repeat(64);
const Q = { chordTolerance: 0.0015, angleTolerance: 0.005 };

function component() {
  return {
    positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    faceOrds: new Float32Array([1, 1, 1]),
    indices: new Uint32Array([0, 1, 2]),
    sideOrds: new Uint32Array([1, 2, 3]),
    faceRanges: [{ ord: 1, indexStart: 0, indexCount: 3 }],
    edges: [{ ord: 1, visibilityClass: "boundary",
      polyline: new Float32Array([0, 0, 0, 1, 0, 0]) }],
    bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    scale: 1,
  };
}

function payload(partColor = [1, 0, 0, 1]) {
  return encodeComponentTessellation(component(), {
    surfaceInput: D, surfaceObject: O, tessellation: Q,
    edgeClasses: [[1, "boundary"]], partColor,
  });
}

test("filesystem provider shares the immutable object/index layout and pinned reads", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cadgen-tess-fs-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const env = { CADGEN_CACHE_DIR: root };
  const key = tessellationCacheKey(D, Q);
  const bytes = payload();
  const row = writeCachedTessellationBytes(key, bytes, env);
  assert.equal(probeCachedTessellation(key, env)?.object, row.object);
  assert.ok(fs.existsSync(path.join(root, "index", "mesh", key)));
  assert.ok(fs.existsSync(path.join(root, "objects", row.object.slice(0, 2), row.object.slice(2))));
  assert.equal(fs.existsSync(path.join(root, "meshes", `${key}.tess`)), false);
  assert.deepEqual([...readCachedTessellationBytes(key, {
    expectedObject: row.object, maxBytes: row.byteLength, env,
  })], [...bytes]);
  assert.equal(readCachedTessellationBytes(key, {
    expectedObject: "b".repeat(64), maxBytes: row.byteLength, env,
  }), null);
  assert.equal(readCachedTessellationBytes(key, {
    expectedObject: row.object, maxBytes: row.byteLength - 1, env,
  }), null);

  const provider = createFsTessellationCacheProvider(env);
  assert.equal((await provider.probeMany([key]))[0].object, row.object);
  assert.deepEqual([...(await provider.getProbed(row, { maxBytes: row.byteLength }))], [...bytes]);
});

test("filesystem writes reject deterministic conflicts and corrupt or v3 bodies miss", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cadgen-tess-fs-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const env = { CADGEN_CACHE_DIR: root };
  const key = tessellationCacheKey(D, Q);
  const row = writeCachedTessellationBytes(key, payload(), env);
  assert.throws(
    () => writeCachedTessellationBytes(key, payload([0, 1, 0, 1]), env),
    TessellationMeshConflictError,
  );
  const object = path.join(root, "objects", row.object.slice(0, 2), row.object.slice(2));
  const corrupt = fs.readFileSync(object);
  corrupt[corrupt.length - 1] ^= 1;
  fs.writeFileSync(object, corrupt);
  assert.equal(readCachedTessellationBytes(key, { expectedObject: row.object, env }), null);

  const legacy = payload().slice();
  new DataView(legacy.buffer, legacy.byteOffset, legacy.byteLength).setUint32(4, 3, true);
  assert.throws(() => writeCachedTessellationBytes(key, legacy, env), /invalid TESS v4/);
});

test("filesystem body reads stay bounded when the opened object grows", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cadgen-tess-fs-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const env = { CADGEN_CACHE_DIR: root };
  const key = tessellationCacheKey(D, Q);
  const row = writeCachedTessellationBytes(key, payload(), env);
  const object = path.join(root, "objects", row.object.slice(0, 2), row.object.slice(2));
  const originalRead = fs.readSync;
  let grew = false;
  fs.readSync = function growingRead(descriptor, buffer, offset, length, position) {
    if (!grew && buffer.byteLength === row.byteLength) {
      grew = true;
      fs.appendFileSync(object, Buffer.alloc(row.byteLength * 2, 0x5a));
    }
    return originalRead.call(this, descriptor, buffer, offset, length, position);
  };
  try {
    assert.equal(readCachedTessellationBytes(key, {
      expectedObject: row.object,
      maxBytes: row.byteLength,
      env,
    }), null, "post-read fstat rejects an in-place body growth race");
  } finally {
    fs.readSync = originalRead;
  }
  assert.equal(grew, true);
  assert.equal(fs.statSync(object).size, row.byteLength * 3);
});

test("filesystem writes bound inspection and verification of CAS objects", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cadgen-tess-fs-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const env = { CADGEN_CACHE_DIR: root };
  const key = tessellationCacheKey(D, Q);
  const bytes = payload();
  const row = writeCachedTessellationBytes(key, bytes, env);
  const object = path.join(root, "objects", row.object.slice(0, 2), row.object.slice(2));
  fs.appendFileSync(object, Buffer.alloc(row.byteLength * 2, 0x5a));

  const originalReadFile = fs.readFileSync;
  fs.readFileSync = function guardedReadFile(target, ...args) {
    if (path.resolve(target) === path.resolve(object)) {
      throw new Error("CAS object inspection must not use an unbounded path read");
    }
    return originalReadFile.call(this, target, ...args);
  };
  try {
    assert.equal(writeCachedTessellationBytes(key, bytes, env).object, row.object);
  } finally {
    fs.readFileSync = originalReadFile;
  }
  assert.equal(fs.statSync(object).size, row.byteLength);
  assert.deepEqual([...fs.readFileSync(object)], [...bytes]);
});

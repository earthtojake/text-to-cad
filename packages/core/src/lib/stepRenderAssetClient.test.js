import assert from "node:assert/strict";
import test from "node:test";

import {
  STEP_TOPOLOGY_SCHEMA_VERSION
} from "../common/stepTopology.mjs";
import {
  loadRenderArrayBuffer,
  loadRenderDisplayEdgeBundle,
  loadRenderSelectorBundle,
  loadRenderTopologyIndex
} from "./stepRenderAssetClient.js";
import {
  setRenderAssetSourceScope
} from "./renderAssetSourceScope.js";

// This is the render asset client the batched snapshot renderer loads through
// (common/headlessRenderEntry.js -> common/source.js -> here). It is a near-verbatim fork of
// renderAssetClient.js with its own page-lifetime caches, so it needs its own coverage: a guard
// present in only one of the two forks is how a cross-source cache hit stayed undetected.

function pad4(buffer, byte = 0) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? Buffer.concat([buffer, Buffer.alloc(padding, byte)]) : buffer;
}

function topologyGlb(
  { cadRef = "fixtures/part", entryKind = "part" } = {},
  { schemaVersion = STEP_TOPOLOGY_SCHEMA_VERSION } = {}
) {
  const bufferViews = [];
  let binary = Buffer.alloc(0);
  function addBufferView(payload) {
    binary = pad4(binary);
    const byteOffset = binary.length;
    binary = Buffer.concat([binary, payload]);
    const index = bufferViews.length;
    bufferViews.push({ buffer: 0, byteOffset, byteLength: payload.length });
    return index;
  }

  const surfaceHalfEdges = Buffer.alloc(28);
  surfaceHalfEdges.writeUInt32LE(7, 0);
  surfaceHalfEdges.writeUInt32LE(11, 4);
  const halfEdgesView = {
    dtype: "uint32",
    bufferView: addBufferView(surfaceHalfEdges),
    byteOffset: 0,
    byteLength: surfaceHalfEdges.length,
    count: 7,
    itemSize: 4
  };
  const buffers = { littleEndian: true, views: { surfaceHalfEdges: halfEdgesView } };
  const selectorManifest = {
    schemaVersion,
    profile: "selector",
    cadRef,
    buffers
  };
  const edgeManifest = {
    schemaVersion,
    profile: "surface-edges",
    cadRef,
    classCodes: {
      none: 0,
      feature: 1,
      tangent: 2,
      seam: 3,
      degenerate: 4,
      boundary: 5,
      nonManifold: 6,
      unknown: 7
    },
    primitiveAttributes: {
      barycentric: "_CAD_EDGE_BARYCENTRIC",
      class: "_CAD_EDGE_CLASS"
    },
    halfEdgeColumns: [
      "edgeRow",
      "faceRow",
      "occurrenceRow",
      "primitiveIndex",
      "triangleIndex",
      "side",
      "classCode"
    ],
    halfEdgesView: "surfaceHalfEdges",
    buffers
  };
  const indexManifest = {
    schemaVersion,
    profile: "index",
    entryKind,
    cadRef,
    stats: {},
    tables: {},
    occurrences: []
  };
  const indexView = addBufferView(Buffer.from(JSON.stringify(indexManifest), "utf8"));
  const edgeView = addBufferView(Buffer.from(JSON.stringify(edgeManifest), "utf8"));
  const selectorView = addBufferView(Buffer.from(JSON.stringify(selectorManifest), "utf8"));
  binary = pad4(binary);
  const gltf = {
    asset: { version: "2.0" },
    buffers: [{ byteLength: binary.length }],
    bufferViews,
    meshes: [{
      primitives: [{
        attributes: {
          _CAD_EDGE_BARYCENTRIC: 0,
          _CAD_EDGE_CLASS: 1
        }
      }]
    }],
    extensionsUsed: ["STEP_topology"],
    extensions: {
      STEP_topology: {
        schemaVersion,
        entryKind,
        indexView,
        edgeView,
        selectorView,
        encoding: "utf-8"
      }
    }
  };
  const jsonChunk = pad4(Buffer.from(JSON.stringify(gltf), "utf8"), 0x20);
  const header = Buffer.alloc(12);
  const jsonHeader = Buffer.alloc(8);
  const binHeader = Buffer.alloc(8);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + jsonChunk.length + 8 + binary.length, 8);
  jsonHeader.writeUInt32LE(jsonChunk.length, 0);
  jsonHeader.write("JSON", 4, "latin1");
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.write("BIN\0", 4, "latin1");
  return Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binary]);
}

function assetUrl(extension = "glb") {
  return `/__render_asset/part.${extension}?v=${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

test("the snapshot client refuses a byte cache hit recorded for another source", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = assetUrl("bin");
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(new Uint8Array([fetchCount]), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first.step");
  assert.deepEqual([...new Uint8Array(await loadRenderArrayBuffer(url))], [1]);

  setRenderAssetSourceScope("/models/second.step");
  await assert.rejects(
    () => loadRenderArrayBuffer(url),
    /cached for source \/models\/first\.step but was requested for \/models\/second\.step/
  );
  assert.equal(fetchCount, 1);
});

test("the snapshot client refuses a parsed topology hit recorded for another source", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = assetUrl();
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(topologyGlb({ cadRef: "fixtures/first" }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first.step");
  assert.equal((await loadRenderTopologyIndex(url)).cadRef, "fixtures/first");

  setRenderAssetSourceScope("/models/second.step");
  await assert.rejects(() => loadRenderTopologyIndex(url), /refusing to reuse it/);
  await assert.rejects(() => loadRenderSelectorBundle(url), /refusing to reuse it/);
  await assert.rejects(() => loadRenderDisplayEdgeBundle(url), /refusing to reuse it/);
  assert.equal(fetchCount, 1);
});

test("repeat loads of one asset within one source still share a single fetch", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = assetUrl();
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(topologyGlb({ cadRef: "fixtures/only" }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/only.step");
  const first = await loadRenderTopologyIndex(url);
  const second = await loadRenderTopologyIndex(url);
  const selector = await loadRenderSelectorBundle(url);
  const displayEdges = await loadRenderDisplayEdgeBundle(url);

  assert.equal(second, first);
  assert.equal(selector.manifest.profile, "selector");
  assert.equal(displayEdges.manifest.profile, "surface-edges");
  assert.equal(fetchCount, 1);
});

test("two distinct assets within one source both load", async (t) => {
  const originalFetch = globalThis.fetch;
  const firstUrl = assetUrl();
  const secondUrl = assetUrl();
  const requested = [];

  globalThis.fetch = async (requestUrl) => {
    requested.push(String(requestUrl));
    return new Response(topologyGlb({ cadRef: `fixtures/${requested.length}` }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/only.step");
  assert.equal((await loadRenderTopologyIndex(firstUrl)).cadRef, "fixtures/1");
  assert.equal((await loadRenderTopologyIndex(secondUrl)).cadRef, "fixtures/2");
  assert.deepEqual(requested, [firstUrl, secondUrl]);
});

test("an undeclared source leaves the snapshot client's caching untouched", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = assetUrl();
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(topologyGlb({ cadRef: "fixtures/unscoped" }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const first = await loadRenderTopologyIndex(url);
  const second = await loadRenderTopologyIndex(url);

  assert.equal(second, first);
  assert.equal(fetchCount, 1);
});

test("a failed snapshot load leaves no source claim behind", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = assetUrl();
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return fetchCount === 1
      ? new Response("", { status: 503, statusText: "Unavailable" })
      : new Response(topologyGlb({ cadRef: "fixtures/second" }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first.step");
  await assert.rejects(() => loadRenderTopologyIndex(url), /503 Unavailable/);

  setRenderAssetSourceScope("/models/second.step");
  assert.equal((await loadRenderTopologyIndex(url)).cadRef, "fixtures/second");
  assert.equal(fetchCount, 2);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  STEP_TOPOLOGY_SCHEMA_VERSION
} from "../common/stepTopology.mjs";
import {
  gitLfsPointerDetailsFromBuffer,
  loadRender3Mf,
  loadRenderArrayBuffer,
  loadRenderGlb,
  loadRenderJson,
  loadRenderSdf,
  loadRenderDisplayEdgeBundle,
  loadRenderSelectorBundle,
  loadRenderTopologyIndex,
  peekRenderJson,
  peekRenderSdf
} from "./renderAssetClient.js";
import {
  setRenderAssetSourceScope
} from "./renderAssetSourceScope.js";

class FakeElement {
  constructor(tagName, attributes = {}, children = [], text = "") {
    this.nodeType = 1;
    this.tagName = tagName;
    this.localName = String(tagName || "").split(":").pop();
    this._attributes = { ...attributes };
    this.childNodes = children;
    this._text = String(text || "");
  }

  getAttribute(name) {
    return Object.hasOwn(this._attributes, name) ? this._attributes[name] : null;
  }

  get textContent() {
    return `${this._text}${this.childNodes.map((child) => String(child?.textContent || "")).join("")}`;
  }
}

class FakeDocument {
  constructor(documentElement) {
    this.documentElement = documentElement;
  }

  querySelector(selector) {
    return selector === "parsererror" ? null : null;
  }
}

function el(tagName, attributes = {}, children = [], text = "") {
  return new FakeElement(tagName, attributes, children, text);
}

function pad4(buffer, byte = 0) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? Buffer.concat([buffer, Buffer.alloc(padding, byte)]) : buffer;
}

function topologyGlb(manifest, buffers = {}, { schemaVersion = STEP_TOPOLOGY_SCHEMA_VERSION } = {}) {
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

  const selectorManifest = JSON.parse(JSON.stringify(manifest));
  selectorManifest.schemaVersion = schemaVersion;
  selectorManifest.profile = "selector";
  selectorManifest.buffers = { littleEndian: true, views: {} };
  for (const [name, { dtype, payload, count, itemSize }] of Object.entries(buffers)) {
    selectorManifest.buffers.views[name] = {
      dtype,
      bufferView: addBufferView(payload),
      byteOffset: 0,
      byteLength: payload.length,
      count,
      itemSize,
    };
  }
  const edgeManifest = {
    schemaVersion,
    profile: "surface-edges",
    stepHash: manifest.stepHash || "",
    classCodes: { none: 0, feature: 1, tangent: 2, seam: 3, degenerate: 4, boundary: 5, nonManifold: 6, unknown: 7 },
    primitiveAttributes: {
      barycentric: "_CAD_EDGE_BARYCENTRIC",
      class: "_CAD_EDGE_CLASS",
    },
    halfEdgeColumns: ["edgeRow", "faceRow", "occurrenceRow", "primitiveIndex", "triangleIndex", "side", "classCode"],
    halfEdgesView: "surfaceHalfEdges",
    buffers: {
      littleEndian: true,
      views: Object.fromEntries(
        Object.entries(selectorManifest.buffers.views)
          .filter(([name]) => name === "surfaceHalfEdges")
      )
    }
  };
  const indexManifest = {
    schemaVersion,
    profile: "index",
    entryKind: manifest.entryKind || "part",
    cadRef: manifest.cadRef,
    stats: manifest.stats || {},
    tables: manifest.tables?.occurrenceColumns ? { occurrenceColumns: manifest.tables.occurrenceColumns } : {},
    occurrences: manifest.occurrences || [],
    ...(manifest.assembly ? { assembly: manifest.assembly } : {}),
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
          _CAD_EDGE_CLASS: 1,
        },
      }],
    }],
    extensionsUsed: ["STEP_topology"],
    extensions: {
      STEP_topology: {
        schemaVersion,
        entryKind: indexManifest.entryKind,
        indexView,
        edgeView,
        selectorView,
        encoding: "utf-8",
      },
    },
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

function abortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

function gitLfsPointerBuffer({ oid = "a".repeat(64), size = 12345 } = {}) {
  return Buffer.from([
    "version https://git-lfs.github.com/spec/v1",
    `oid sha256:${oid}`,
    `size ${size}`,
    ""
  ].join("\n"));
}

test("abortable loads do not reuse a stale pending cache entry", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const url = `/asset-${Date.now()}-${Math.random()}.json`;

  globalThis.fetch = async (requestUrl, { signal } = {}) => new Promise((resolve, reject) => {
    const request = { requestUrl, resolve, reject, signal };
    requests.push(request);
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    signal?.addEventListener("abort", () => reject(abortError()), { once: true });
  });

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const firstController = new AbortController();
  const firstLoad = loadRenderJson(url, { signal: firstController.signal });
  assert.equal(requests.length, 1);

  firstController.abort();

  const secondController = new AbortController();
  const secondLoad = loadRenderJson(url, { signal: secondController.signal });
  assert.equal(requests.length, 2);

  requests[1].resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));

  await assert.rejects(firstLoad, { name: "AbortError" });
  assert.deepEqual(await secondLoad, { ok: true });
});

test("array buffer loads share pending fetches while aborting only the consumer", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const url = `/asset-${Date.now()}-${Math.random()}.glb`;
  const payload = new Uint8Array([1, 2, 3, 4]).buffer;

  globalThis.fetch = async (requestUrl) => new Promise((resolve) => {
    requests.push({ requestUrl, resolve });
  });

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const firstController = new AbortController();
  const secondController = new AbortController();
  const firstLoad = loadRenderArrayBuffer(url, { signal: firstController.signal });
  const secondLoad = loadRenderArrayBuffer(url, { signal: secondController.signal });
  assert.equal(requests.length, 1);

  firstController.abort();
  requests[0].resolve(new Response(payload, { status: 200 }));

  await assert.rejects(firstLoad, { name: "AbortError" });
  assert.deepEqual([...new Uint8Array(await secondLoad)], [1, 2, 3, 4]);
});

test("Git LFS pointer stubs are detected before mesh parsing", async (t) => {
  const originalFetch = globalThis.fetch;
  const oid = "b".repeat(64);
  const pointer = gitLfsPointerBuffer({ oid, size: 24992 });
  const glbUrl = `/asset-${Date.now()}-${Math.random()}.glb`;
  const threeMfUrl = `/asset-${Date.now()}-${Math.random()}.3mf`;

  assert.deepEqual(gitLfsPointerDetailsFromBuffer(pointer.buffer.slice(pointer.byteOffset, pointer.byteOffset + pointer.byteLength)), {
    oid,
    size: 24992,
  });

  globalThis.fetch = async (requestUrl) => {
    assert.ok([glbUrl, threeMfUrl].includes(String(requestUrl)));
    return new Response(pointer, { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    loadRenderGlb(glbUrl),
    /GLB render asset is a Git LFS pointer, not downloaded mesh data/
  );
  await assert.rejects(
    loadRender3Mf(threeMfUrl),
    /3MF render asset is a Git LFS pointer, not downloaded mesh data/
  );
});

test("selector bundles decode STEP_topology bufferViews from GLB", async (t) => {
  const originalFetch = globalThis.fetch;
  const glbUrl = `/topology-${Date.now()}-${Math.random()}.glb`;
  const edgeIds = Buffer.alloc(8);
  edgeIds.writeUInt32LE(7, 0);
  edgeIds.writeUInt32LE(11, 4);
  const surfaceHalfEdges = Buffer.alloc(28);
  surfaceHalfEdges.writeUInt32LE(7, 0);
  surfaceHalfEdges.writeUInt32LE(11, 4);
  const requests = [];
  const glb = topologyGlb(
    { cadRef: "fixtures/box", tables: {}, occurrences: [], shapes: [], faces: [], edges: [] },
    {
      edgeIds: { dtype: "uint32", payload: edgeIds, count: 2, itemSize: 4 },
      surfaceHalfEdges: { dtype: "uint32", payload: surfaceHalfEdges, count: 7, itemSize: 4 }
    }
  );

  globalThis.fetch = async (requestUrl) => {
    requests.push(String(requestUrl));
    assert.equal(String(requestUrl), glbUrl);
    return new Response(glb, { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const bundle = await loadRenderSelectorBundle(glbUrl);
  assert.deepEqual(Array.from(bundle.buffers.edgeIds), [7, 11]);
  const displayBundle = await loadRenderDisplayEdgeBundle(glbUrl);
  assert.deepEqual(Array.from(displayBundle.buffers.surfaceHalfEdges.slice(0, 2)), [7, 11]);
  assert.equal(displayBundle.manifest.profile, "surface-edges");
  assert.equal((await loadRenderTopologyIndex(glbUrl)).cadRef, "fixtures/box");
  assert.deepEqual(requests, [glbUrl]);
});

test("STEP_topology client rejects old schema artifacts", async (t) => {
  const originalFetch = globalThis.fetch;
  const glbUrl = `/old-topology-${Date.now()}-${Math.random()}.glb`;
  const glb = topologyGlb(
    { cadRef: "fixtures/old", tables: {}, occurrences: [], shapes: [], faces: [], edges: [] },
    {},
    { schemaVersion: STEP_TOPOLOGY_SCHEMA_VERSION - 1 }
  );

  globalThis.fetch = async () => new Response(glb, { status: 200 });
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    loadRenderTopologyIndex(glbUrl),
    new RegExp(`Unsupported STEP_topology schemaVersion ${STEP_TOPOLOGY_SCHEMA_VERSION - 1}`)
  );
});

test("SDF robot descriptions load through the render cache", async (t) => {
  const originalFetch = globalThis.fetch;
  const originalDomParser = globalThis.DOMParser;
  const url = `/robot-${Date.now()}-${Math.random()}.sdf`;
  let fetchCount = 0;

  globalThis.DOMParser = class FakeDomParser {
    parseFromString() {
      return new FakeDocument(el("sdf", { version: "1.12" }, [
        el("model", { name: "sample_robot" }, [
          el("link", { name: "base_link" })
        ])
      ]));
    }
  };
  globalThis.fetch = async (requestUrl) => {
    fetchCount += 1;
    assert.equal(String(requestUrl), url);
    return new Response("<sdf />", { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    globalThis.DOMParser = originalDomParser;
  });

  const first = await loadRenderSdf(url);
  const second = await loadRenderSdf(url);

  assert.equal(first.robotName, "sample_robot");
  assert.equal(first.rootLink, "base_link");
  assert.equal(second, first);
  assert.equal(peekRenderSdf(url), first);
  assert.equal(fetchCount, 1);
});

test("a cached render asset is not reused across source scopes", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  assert.deepEqual(await loadRenderJson(url), { ok: true });
  assert.equal(fetchCount, 1);

  setRenderAssetSourceScope("/models/second");
  await assert.rejects(
    () => loadRenderJson(url),
    /cached for source \/models\/first but was requested for \/models\/second/
  );
  assert.equal(fetchCount, 1);
});

test("a peek reports a miss instead of handing back another source's entry", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  const first = await loadRenderJson(url);
  assert.equal(peekRenderJson(url), first);

  setRenderAssetSourceScope("/models/second");
  assert.equal(peekRenderJson(url), null);
  assert.equal(fetchCount, 1);

  setRenderAssetSourceScope("/models/first");
  assert.equal(peekRenderJson(url), first);
});

test("a failed load leaves no source claim on an uncached asset", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return fetchCount === 1
      ? new Response("", { status: 503, statusText: "Unavailable" })
      : new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  await assert.rejects(() => loadRenderJson(url), /503 Unavailable/);

  setRenderAssetSourceScope("/models/second");
  assert.deepEqual(await loadRenderJson(url), { ok: true });
  assert.equal(fetchCount, 2);
});

test("an already-aborted array buffer request claims nothing", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.bin`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(new Uint8Array([9, 9, 9]), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  const controller = new AbortController();
  controller.abort();
  setRenderAssetSourceScope("/models/first");
  await assert.rejects(() => loadRenderArrayBuffer(url, { signal: controller.signal }), {
    name: "AbortError"
  });
  assert.equal(fetchCount, 0);

  setRenderAssetSourceScope("/models/second");
  assert.equal((await loadRenderArrayBuffer(url)).byteLength, 3);
  assert.equal(fetchCount, 1);
});

test("array buffer loads are scoped to their source as well", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.bin`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(new Uint8Array([1, 2, 3]), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  assert.equal((await loadRenderArrayBuffer(url)).byteLength, 3);

  setRenderAssetSourceScope("/models/second");
  await assert.rejects(() => loadRenderArrayBuffer(url), /refusing to reuse it/);
  assert.equal(fetchCount, 1);
});

test("repeat loads within one source scope still share a single fetch", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/only");
  const first = await loadRenderJson(url);
  const second = await loadRenderJson(url);

  assert.equal(second, first);
  assert.equal(fetchCount, 1);
});

test("an unset source scope leaves render asset caching untouched", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const first = await loadRenderJson(url);
  const second = await loadRenderJson(url);

  assert.equal(second, first);
  assert.equal(fetchCount, 1);
});

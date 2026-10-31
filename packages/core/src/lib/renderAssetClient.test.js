import assert from "node:assert/strict";
import test from "node:test";

import {
  gitLfsPointerDetailsFromBuffer,
  loadRender3Mf,
  loadRenderArrayBuffer,
  loadRenderGlb,
  loadRenderJson,
  loadRenderRobot,
  peekRenderJson,
  peekRenderRobot,
  ROBOT_PAYLOAD_SCHEMA_VERSION
} from "./renderAssetClient.js";
import {
  renderAssetSourceScopeForJob,
  setRenderAssetSourceScope
} from "./renderAssetSourceScope.js";

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

test("a robot payload loads through the render cache, by file and revision, and only at this build's schema", async () => {
  const file = `/robots/arm-${Date.now()}-${Math.random()}.urdf`;
  let calls = 0;
  const client = { robot: async (asked) => { calls += 1; assert.equal(asked, file); return { schemaVersion: ROBOT_PAYLOAD_SCHEMA_VERSION, kind: "urdf", articulation: {}, visuals: [] }; } };
  const first = await loadRenderRobot(file, { client, revision: "r1" });
  const second = await loadRenderRobot(file, { client, revision: "r1" });
  assert.equal(second, first);
  assert.equal(peekRenderRobot(file, { revision: "r1" }), first);
  assert.equal(peekRenderRobot(file, { revision: "r2" }), null, "a new revision of the file is read again");
  await loadRenderRobot(file, { client, revision: "r2" });
  assert.equal(calls, 2);
  const stale = { robot: async () => ({ schemaVersion: ROBOT_PAYLOAD_SCHEMA_VERSION + 1 }) };
  await assert.rejects(loadRenderRobot(`${file}-stale`, { client: stale }),
    new RegExp(`schemaVersion ${ROBOT_PAYLOAD_SCHEMA_VERSION + 1}.*reads version ${ROBOT_PAYLOAD_SCHEMA_VERSION}`));
});

test("a resolved job's scope is its document, and a resolved job that names none is refused", () => {
  assert.equal(renderAssetSourceScopeForJob({ kind: "stl", url: "/models/part.stl" }), "", "no resolved job: the unscoped default");
  assert.equal(renderAssetSourceScopeForJob({ resolved: { inputPath: " /models/part.stl " } }), "/models/part.stl");
  // A blank or non-string source is not a source: it fails closed rather than coerce into the
  // same bucket as the interactive viewer's unscoped default.
  for (const inputPath of [undefined, "", "   ", 0, false, {}, ["/models/part.stl"]]) {
    assert.throws(() => renderAssetSourceScopeForJob({ resolved: { rootPath: "/models", inputPath } }),
      /require resolved\.inputPath to scope the render asset cache/, JSON.stringify(inputPath));
  }
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

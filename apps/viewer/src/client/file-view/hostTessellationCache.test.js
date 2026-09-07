// The surface's tessellation-cache provider talks to ITS origin. An embedded
// surface whose provider fetched same-origin would look up the cache on the
// host's page and find nothing — which is exactly what the desktop app did
// before the surface installed one.
import assert from "node:assert/strict";
import test from "node:test";

import {
  configureTessellationCacheWriteBack,
  setTessellationCacheProvider,
  tessellationCacheProviderRegistered,
} from "cadgen-js/lib/surf/tessellationCache.js";

import {
  VIEWER_POST_GUARD_HEADERS,
  VIEWER_WRITE_BACK_POLICY,
  createViewerTessellationCacheProvider,
  installViewerTessellationCacheProvider,
} from "./hostTessellationCache.js";

function withFetchSpy(run) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method ?? "GET", headers: init.headers ?? {} });
    return { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) };
  };
  return run(calls).finally(() => {
    globalThis.fetch = original;
  });
}

test("an embedded surface's provider fetches the cache on its own origin", async () => {
  await withFetchSpy(async (calls) => {
    const provider = createViewerTessellationCacheProvider("http://127.0.0.1:3250/");
    await provider.get("abc-t1-l1.500000e-3-a1.000000e-1");
    await provider.put("abc-t1-l1.500000e-3-a1.000000e-1", new Uint8Array([1, 2, 3]));
    assert.equal(calls[0].url, "http://127.0.0.1:3250/__tess_cache/abc-t1-l1.500000e-3-a1.000000e-1.tess");
    assert.equal(calls[0].method, "GET");
    assert.equal(calls[1].url, calls[0].url);
    assert.equal(calls[1].method, "POST");
    // The write-back carries the server's cross-site POST guard.
    for (const call of calls) {
      assert.deepEqual(call.headers, VIEWER_POST_GUARD_HEADERS);
    }
  });
});

test("the standalone case is the empty origin: same-origin routes", async () => {
  await withFetchSpy(async (calls) => {
    const provider = createViewerTessellationCacheProvider("");
    await provider.get("k");
    assert.equal(calls[0].url, "/__tess_cache/k.tess");
  });
});

test("installing registers the page's provider with deferred write-backs", (t) => {
  t.after(() => {
    setTessellationCacheProvider(null);
    configureTessellationCacheWriteBack({ deferMs: 0 });
  });
  installViewerTessellationCacheProvider("http://127.0.0.1:3250");
  assert.equal(tessellationCacheProviderRegistered(), true);
  assert.ok(VIEWER_WRITE_BACK_POLICY.deferMs > 0, "a viewer defers its write-backs past the load");
  assert.ok(VIEWER_WRITE_BACK_POLICY.concurrency >= 1);
});

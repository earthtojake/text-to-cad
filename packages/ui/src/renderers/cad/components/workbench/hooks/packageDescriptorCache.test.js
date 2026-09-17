import assert from "node:assert/strict";
import test from "node:test";

import {
  installRuntimePackageDescriptor,
  loadPackageDescriptor
} from "./packageDescriptorCache.js";

function abortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

test("overlapping descriptor consumers own independent cancellation", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const packageUrl = `/__cad/asset?file=/package-${Date.now()}-${Math.random()}&v=tree`;
  globalThis.fetch = (url, { signal } = {}) => new Promise((resolve, reject) => {
    const request = { url, signal, resolve, reject };
    requests.push(request);
    signal?.addEventListener("abort", () => reject(abortError()), { once: true });
  });
  t.after(() => { globalThis.fetch = originalFetch; });

  const firstController = new AbortController();
  const secondController = new AbortController();
  const first = loadPackageDescriptor(packageUrl, { signal: firstController.signal });
  const second = loadPackageDescriptor(packageUrl, { signal: secondController.signal });
  assert.equal(requests.length, 2, "signal-owned descriptor reads are not shared");

  firstController.abort();
  requests[1].resolve(new Response(JSON.stringify({ kind: "assembly-package", tree: "new" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  }));

  assert.equal(await first, null);
  assert.deepEqual(await second, { kind: "assembly-package", tree: "new" });
  assert.equal(requests[1].signal.aborted, false, "cancelling the predecessor leaves the replacement alive");
});

test("an installed runtime replacement fences an older descriptor response", async (t) => {
  const originalFetch = globalThis.fetch;
  let resolveRequest;
  const packageUrl = `/__cad/asset?file=/replacement-${Date.now()}-${Math.random()}&v=tree`;
  globalThis.fetch = () => new Promise((resolve) => { resolveRequest = resolve; });
  t.after(() => { globalThis.fetch = originalFetch; });

  const pending = loadPackageDescriptor(packageUrl);
  const replacement = { kind: "assembly-package", tree: "same", viewId: "new-view" };
  installRuntimePackageDescriptor(packageUrl, replacement);
  resolveRequest(new Response(JSON.stringify({
    kind: "assembly-package", tree: "same", viewId: "old-view",
  }), { status: 200, headers: { "content-type": "application/json" } }));

  assert.equal(await pending, replacement, "the late saved-view response cannot escape after replacement");
  assert.equal(await loadPackageDescriptor(packageUrl), replacement);
});

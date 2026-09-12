import assert from "node:assert/strict";
import test from "node:test";

import { __testing } from "../../common/source.js";

const { fetchComponentGlbBuffer, COMPONENT_FETCH_ATTEMPTS } = __testing;

function stubFetch(sequence) {
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    const next = sequence[Math.min(calls.length - 1, sequence.length - 1)];
    return {
      ok: next.status === 200,
      status: next.status,
      arrayBuffer: async () => new ArrayBuffer(8)
    };
  };
  return calls;
}

test("a component GLB that 404s mid-rebuild is retried and recovers", async () => {
  const original = globalThis.fetch;
  try {
    // the package directory is being swapped: two misses, then the asset is back
    const calls = stubFetch([{ status: 404 }, { status: 404 }, { status: 200 }]);
    const buffer = await fetchComponentGlbBuffer("http://x/c.glb", "cid1");
    assert.equal(buffer.byteLength, 8);
    assert.equal(calls.length, 3, "should retry until the asset reappears");
  } finally {
    globalThis.fetch = original;
  }
});

test("a persistent 404 gives up after the attempt budget and explains why", async () => {
  const original = globalThis.fetch;
  try {
    const calls = stubFetch([{ status: 404 }]);
    await assert.rejects(
      () => fetchComponentGlbBuffer("http://x/c.glb", "cid2"),
      (error) => {
        assert.match(error.message, /Failed to load component GLB cid2: HTTP 404/);
        // the message must name BOTH plausible causes, not just the status
        assert.match(error.message, /rebuild is still in flight|descriptor is stale/);
        return true;
      }
    );
    assert.equal(calls.length, COMPONENT_FETCH_ATTEMPTS);
  } finally {
    globalThis.fetch = original;
  }
});

test("a non-404 failure is NOT retried — retrying only delays a real error", async () => {
  const original = globalThis.fetch;
  try {
    const calls = stubFetch([{ status: 500 }]);
    await assert.rejects(() => fetchComponentGlbBuffer("http://x/c.glb", "cid3"));
    assert.equal(calls.length, 1, "5xx should fail immediately");
  } finally {
    globalThis.fetch = original;
  }
});

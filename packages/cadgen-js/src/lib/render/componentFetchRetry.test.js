import assert from "node:assert/strict";
import test from "node:test";

import { __testing } from "../../common/source.js";

const { fetchComponentGlbBuffer, COMPONENT_FETCH_ATTEMPTS } = __testing;

// The retry backoff is real wall time in production and pure waiting in a test:
// two exhausted sequences used to sleep ~880 ms, most of this file's runtime, and
// made the suite's duration a function of the runner's timer resolution. Collapse
// the clock and RECORD what was asked for, so the schedule itself is asserted
// instead of merely endured.
function fakeClock(t) {
  const realSetTimeout = globalThis.setTimeout;
  const delays = [];
  globalThis.setTimeout = (fn, delay) => {
    delays.push(delay);
    queueMicrotask(fn);
    return 0;
  };
  t.after(() => { globalThis.setTimeout = realSetTimeout; });
  return delays;
}

function stubFetch(t, sequence) {
  const original = globalThis.fetch;
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
  t.after(() => { globalThis.fetch = original; });
  return calls;
}

test("a component GLB that 404s mid-rebuild is retried on a growing backoff and recovers", async (t) => {
  const delays = fakeClock(t);
  // the package directory is being swapped: two misses, then the asset is back
  const calls = stubFetch(t, [{ status: 404 }, { status: 404 }, { status: 200 }]);
  const buffer = await fetchComponentGlbBuffer("http://x/c.glb", "cid1");
  assert.equal(buffer.byteLength, 8);
  assert.equal(calls.length, 3, "should retry until the asset reappears");
  // Each wait is longer than the last: a rebuild that has not landed yet is
  // given more room, not hammered on a fixed interval.
  assert.equal(delays.length, 2);
  assert.ok(delays.every((delay) => delay > 0), `backoff must wait: ${delays}`);
  assert.ok(delays[1] > delays[0], `backoff must grow: ${delays}`);
});

test("a persistent 404 gives up after the attempt budget and explains why", async (t) => {
  fakeClock(t);
  const calls = stubFetch(t, [{ status: 404 }]);
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
});

test("a non-404 failure is NOT retried — retrying only delays a real error", async (t) => {
  const delays = fakeClock(t);
  const calls = stubFetch(t, [{ status: 500 }]);
  await assert.rejects(() => fetchComponentGlbBuffer("http://x/c.glb", "cid3"));
  assert.equal(calls.length, 1, "5xx should fail immediately");
  assert.deepEqual(delays, [], "a 5xx must not even schedule a backoff");
});

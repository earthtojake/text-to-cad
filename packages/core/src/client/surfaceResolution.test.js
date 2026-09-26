import assert from "node:assert/strict";
import test from "node:test";
import { createCadClient } from "./client.js";

import { resolveSurfaceComponents as resolveWithClient, SurfaceResolutionError } from "./surfaceResolution.js";

function resolveSurfaceComponents(descriptor, requests, options = {}) {
  const client = options.client || createCadClient();
  return resolveWithClient(descriptor, requests, { ...options, client });
}

const TREE = "a".repeat(64);
const VIEW = "b".repeat(64);
const D = "d".repeat(64);
const O = "e".repeat(64);
const descriptor = {
  tree: TREE,
  viewId: VIEW,
  surfaceProducer: { scheme: 19, surfFormat: 2, producerKey: "c".repeat(64) },
};

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status, headers: { "content-type": "application/json" },
  });
}

function ready() {
  return {
    viewId: VIEW,
    components: {
      part: {
        surfaceInput: D,
        state: "ready",
        surfaceObject: O,
        url: `/__cad/store?tree=${TREE}&surfaceInput=${D}&object=${O}`,
        byteLength: 1234,
      },
    },
  };
}

test("surface resolution forwards frozen pins and validates a ready CAS ticket", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options, body: JSON.parse(options.body) };
    return json(ready());
  };
  const result = await resolveSurfaceComponents(descriptor, [{
    cid: "part", surfaceInput: D, surfaceObject: O,
  }]);
  assert.deepEqual(result.get("part"), {
    surfaceInput: D, surfaceObject: O,
    surfUrl: `/__cad/store?tree=${TREE}&surfaceInput=${D}&object=${O}`,
    byteLength: 1234,
  });
  assert.equal(request.url, "/__cad/surfaces");
  assert.equal(request.options.headers["x-cadgen-viewer"], "1");
  assert.deepEqual(request.body, {
    tree: TREE, viewId: VIEW, producer: descriptor.surfaceProducer,
    components: [{ cid: "part", surfaceInput: D, expectedSurfaceObject: O }],
  });
});

test("pending resolution polls the same request and subscriber token", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const bodies = [];
  globalThis.fetch = async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    return bodies.length === 1 ? json({
      viewId: VIEW, job: "job-1",
      components: { part: { surfaceInput: D, state: "pending", job: "job-1" } },
    }) : json(ready());
  };
  const result = await resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }]);
  assert.equal(result.get("part").surfaceObject, O);
  assert.equal(bodies.length, 2);
  assert.equal(bodies[1].job, "job-1");
  assert.deepEqual(bodies[1].components, bodies[0].components);
});

// Settle on the events the resolver actually produces, never on a stopwatch. The
// abort used to be timed with `setTimeout(10)` and the cancel POST read after
// `setTimeout(0)`, which makes the assertion depend on how fast the runner drains
// its loop: a slow box aborts before the first poll is even in flight, and a
// loaded one reads `calls` before the cancel lands.
test("abort detaches only the known surface subscriber", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const calls = [];
  const controller = new AbortController();
  let sawFirstPoll;
  let sawCancel;
  const firstPoll = new Promise((resolve) => { sawFirstPoll = resolve; });
  const cancelled = new Promise((resolve) => { sawCancel = resolve; });
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    if (url.endsWith("/cancel")) {
      sawCancel();
      return new Response(null, { status: 204 });
    }
    if (calls.length === 2) sawFirstPoll();
    return json({
      viewId: VIEW, job: "job-cancel",
      components: { part: { surfaceInput: D, state: "pending", job: "job-cancel" } },
    });
  };
  const pending = resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }], {
    signal: controller.signal,
  });
  // The job id only exists once the first poll has answered; abort before that and
  // there is nothing to detach.
  await firstPoll;
  controller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  await cancelled;
  assert.deepEqual(calls.at(-1), {
    url: "/__cad/surfaces/cancel", body: { job: "job-cancel" },
  });
});

test("failed, replacement and mismatched ready responses never produce tickets", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => json({
    viewId: VIEW,
    components: { part: { surfaceInput: D, state: "failed", error: "bad face", code: "extract" } },
  });
  await assert.rejects(
    resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }]),
    (error) => error instanceof SurfaceResolutionError && error.code === "extract",
  );
  const replacementView = {
    ...descriptor,
    viewId: "f".repeat(64),
    surfaceProducer: { ...descriptor.surfaceProducer, producerKey: "9".repeat(64) },
    components: { part: { surfaceInput: "8".repeat(64) } },
  };
  globalThis.fetch = async () => json({ ...ready(), replacementView });
  await assert.rejects(
    resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }]),
    (error) => error instanceof SurfaceResolutionError && error.code === "replacement-view"
      && error.replacementView.viewId === replacementView.viewId,
  );
  globalThis.fetch = async () => json({
    ...ready(), components: { part: { ...ready().components.part, surfaceObject: "0".repeat(64) } },
  });
  await assert.rejects(
    resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D, surfaceObject: O }]),
    /invalid immutable URL|changed the pinned object/,
  );
});

test("independent renderer clients bind surface tickets to their own backend origins", async () => {
  const calls = [];
  const clients = ["http://127.0.0.1:4101", "http://127.0.0.1:4102"].map(origin => ({
    origin,
    requestSurfaces: async (body, options) => { calls.push({ origin, body, signal: options.signal }); return ready(); },
  }));
  const controller = new AbortController();
  const results = await Promise.all(clients.map(client => resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }], { client, signal: controller.signal })));
  assert.equal(calls.length, 2);
  for (let i=0; i<2; i++) {
    assert.equal(new URL(results[i].get("part").surfUrl).origin, clients[i].origin);
    assert.equal(calls[i].signal, controller.signal);
    assert.equal(calls[i].body.viewId, VIEW);
  }
});

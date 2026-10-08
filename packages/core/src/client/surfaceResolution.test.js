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

test("a row ready before the rest of its request is announced at once, and once", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const D2 = "f".repeat(64), O2 = "9".repeat(64);
  const row = (surfaceInput, object) => ({ surfaceInput, state: "ready", surfaceObject: object,
    url: `/__cad/store?tree=${TREE}&surfaceInput=${surfaceInput}&object=${object}`, byteLength: 10 });
  let polls = 0;
  globalThis.fetch = async () => {
    polls += 1;
    return json({ viewId: VIEW, job: "job-2", components: {
      part: row(D, O),
      other: polls === 1 ? { surfaceInput: D2, state: "pending", job: "job-2" } : row(D2, O2),
    } });
  };
  const announced = [];
  const result = await resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }, { cid: "other", surfaceInput: D2 }],
    { onReady: (cid, ticket) => announced.push([cid, polls, ticket.surfaceObject]) });
  assert.deepEqual(announced, [["part", 1, O], ["other", 2, O2]]);
  assert.equal(result.size, 2);
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
  // The job id only exists once the first poll has answered (an abort before that waits
  // for the answer: the next test); abort while a later poll waits.
  await firstPoll;
  controller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  await cancelled;
  assert.deepEqual(calls.at(-1), {
    url: "/__cad/surfaces/cancel", body: { job: "job-cancel" },
  });
});

test("an abort while the first post is in flight cancels the job its answer opens", async () => {
  // A first post aborted in flight would never learn its token, and the server would go on
  // deriving for nobody until the subscriber expired. So it is let finish, and cancelled then.
  const controller = new AbortController();
  const cancels = [];
  let posted, answer;
  const firstPost = new Promise((resolve) => { posted = resolve; });
  const client = {
    // As fetch does: an abort rejects a request in flight.
    requestSurfaces: (_body, { signal } = {}) => new Promise((resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      answer = () => resolve({ viewId: VIEW, components: { part: { surfaceInput: D, state: "pending", job: "job-early" } } });
      posted();
    }),
    cancelSurfaceRequest: async (body) => { cancels.push(body); },
  };
  const pending = resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }], { client, signal: controller.signal });
  await firstPost;
  controller.abort();
  answer();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  assert.deepEqual(cancels, [{ job: "job-early" }]);
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
    // A first post is never aborted in flight (its answer carries the token a cancel needs).
    assert.equal(calls[i].signal, undefined);
    assert.equal(calls[i].body.viewId, VIEW);
  }
});

test("a request for more components than one POST may name is sent in chunks of at most 64", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const bodies = [];
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    bodies.push(body);
    if (body.components.length < 1 || body.components.length > 64) {
      return json({ error: "surface request must name between 1 and 64 components" }, 400);
    }
    return json({ viewId: VIEW, components: Object.fromEntries(body.components.map(({ cid }) => [cid, {
      surfaceInput: D, state: "ready", surfaceObject: O,
      url: `/__cad/store?tree=${TREE}&surfaceInput=${D}&object=${O}`, byteLength: 10,
    }])) });
  };
  const requests = Array.from({ length: 150 }, (_, index) => ({ cid: `part${index}`, surfaceInput: D, surfaceObject: O }));
  const result = await resolveSurfaceComponents(descriptor, requests);
  assert.deepEqual(bodies.map((body) => body.components.length), [64, 64, 22]);
  assert.deepEqual([...result.keys()], requests.map(({ cid }) => cid));
  assert.deepEqual(bodies.flatMap((body) => body.components.map(({ cid }) => cid)), requests.map(({ cid }) => cid));
});

test("a failing chunk fails the whole request with its own error", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    return json({ viewId: VIEW, components: Object.fromEntries(body.components.map(({ cid }) => [cid, cid === "part70"
      ? { surfaceInput: D, state: "failed", error: "bad face", code: "extract" }
      : { surfaceInput: D, state: "ready", surfaceObject: O, url: `/__cad/store?tree=${TREE}&surfaceInput=${D}&object=${O}`, byteLength: 10 }])) });
  };
  const requests = Array.from({ length: 100 }, (_, index) => ({ cid: `part${index}`, surfaceInput: D, surfaceObject: O }));
  await assert.rejects(resolveSurfaceComponents(descriptor, requests), (error) => error instanceof SurfaceResolutionError && error.cid === "part70");
});

// A daemon whose worker never announces itself keeps a derivation pending for two minutes before it
// fails. Asked every 640 ms throughout, the first eight parts of a cold w16 open made 1,500 requests
// in that time (each a host call in the CAD app). The first asks stay as quick as they were.
test("a derivation pending for two minutes is asked at a tenth of its wait, at most every 5 s", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 });
  const asks = [];
  const client = {
    origin: "",
    async requestSurfaces() {
      asks.push(Date.now());
      return { viewId: VIEW, job: "job-1", components: { part: { surfaceInput: D, state: "pending", job: "job-1" } } };
    },
    async cancelSurfaceRequest() { return {}; },
  };
  const controller = new AbortController();
  const settled = resolveWithClient(descriptor, [{ cid: "part", surfaceInput: D }], { client, signal: controller.signal })
    .catch((error) => error);
  while (Date.now() < 120_000) {
    await new Promise((resolve) => setImmediate(resolve)); // the answer lands and the next wait starts
    t.mock.timers.tick(10);
  }
  controller.abort();
  assert.equal((await settled).name, "AbortError");
  const gaps = asks.slice(1).map((at, index) => at - asks[index]);
  assert.deepEqual(gaps.slice(0, 4), [80, 160, 320, 640], "the first asks are as quick as ever");
  assert.ok(asks.length < 60, `asked ${asks.length} times in two minutes`);
  assert.ok(Math.max(...gaps) <= 5000, `the longest wait was ${Math.max(...gaps)} ms`);
  assert.ok(gaps.at(-1) >= 4990, `the waits grew to 5 s, the last ${gaps.at(-1)} ms`);
});

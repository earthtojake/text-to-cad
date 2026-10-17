import assert from "node:assert/strict";
import test from "node:test";
import { createCadClient } from "./client.js";

import { resolveParts as resolveWithClient, PartResolutionError } from "./partResolution.js";
import { tessellationDecodedBytes } from "../lib/parts/tessellationCache.js";

function resolveParts(descriptor, requests, options = {}) {
  const client = options.client || createCadClient();
  return resolveWithClient(descriptor, requests, { ...options, client });
}

const TREE = "a".repeat(64);
const VIEW = "b".repeat(64);
const P = `${"d".repeat(64)}-v1`;
const O = "e".repeat(64);
const descriptor = {
  tree: TREE,
  viewId: VIEW,
  producer: { build123d: "0.9.1", ocp: "7.8.1.1", cadqueryOcp: "7.8.1.1", producerKey: "c".repeat(64) },
};

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status, headers: { "content-type": "application/json" },
  });
}

// A part's record as cadgen's store answers it: its display mesh (one triangle) and its selector
// table, each by its object.
const S = "5".repeat(64);
const MESH = { vertexCount: 3, indexCount: 3, faceCount: 1, edgeCount: 0, edgePointCount: 0 };
const record = (object = O) => ({
  glb: { object, byteLength: 1240, decodedBytes: tessellationDecodedBytes(MESH), ...MESH },
  selectors: { object: S, byteLength: 99, faceCount: 1, edgeCount: 3, vertexCount: 3 },
});
const readyRow = (part = P, object = O) => ({ part, state: "ready", record: record(object) });

function ready(object = O) {
  return { viewId: VIEW, components: { part: readyRow(P, object) } };
}

test("part resolution forwards frozen pins and answers each component with its part's row", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options, body: JSON.parse(options.body) };
    return json(ready());
  };
  const result = await resolveParts(descriptor, [{ cid: "part", part: P }]);
  assert.deepEqual(result.get("part"), { part: P, ...record() });
  assert.ok(Object.isFrozen(result.get("part")));
  // A ready row whose record is not a whole part record is no ticket.
  const broken = [undefined, { glb: record().glb }, { ...record(), schemaVersion: 1 },
    { ...record(), glb: { ...record().glb, decodedBytes: 1 } },
    { ...record(), selectors: { ...record().selectors, byteLength: 0 } }];
  for (const value of broken) {
    globalThis.fetch = async () => json({ ...ready(), components: { part: { ...readyRow(), record: value } } });
    await assert.rejects(resolveParts(descriptor, [{ cid: "part", part: P }]), /no valid part record/);
  }
  assert.equal(request.url, "/__cad/parts");
  assert.equal(request.options.headers["x-cadgen-viewer"], "1");
  assert.deepEqual(request.body, {
    tree: TREE, viewId: VIEW, producer: descriptor.producer,
    components: [{ cid: "part", part: P }],
  });
  // A component is asked for by the part its view pins, and nothing else is one.
  await assert.rejects(resolveParts(descriptor, [{ cid: "part", part: "d".repeat(64) }]), /must be a part key/);
});

test("pending resolution polls the same request and subscriber token", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const bodies = [];
  globalThis.fetch = async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    return bodies.length === 1 ? json({
      viewId: VIEW, job: "job-1",
      components: { part: { part: P, state: "pending", job: "job-1" } },
    }) : json(ready());
  };
  const result = await resolveParts(descriptor, [{ cid: "part", part: P }]);
  assert.equal(result.get("part").glb.object, O);
  assert.equal(bodies.length, 2);
  assert.equal(bodies[1].job, "job-1");
  assert.deepEqual(bodies[1].components, bodies[0].components);
});

test("a row ready before the rest of its request is announced at once, and once", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const P2 = `${"f".repeat(64)}-v1`, O2 = "9".repeat(64);
  let polls = 0;
  globalThis.fetch = async () => {
    polls += 1;
    return json({ viewId: VIEW, job: "job-2", components: {
      part: readyRow(P, O),
      other: polls === 1 ? { part: P2, state: "pending", job: "job-2" } : readyRow(P2, O2),
    } });
  };
  const announced = [];
  const deriving = [];
  const result = await resolveParts(descriptor, [{ cid: "part", part: P }, { cid: "other", part: P2 }],
    { onReady: (cid, ticket) => announced.push([cid, polls, ticket.glb.object]), onPending: (cid) => deriving.push([cid, polls]) });
  assert.deepEqual(announced, [["part", 1, O], ["other", 2, O2]]);
  assert.deepEqual(deriving, [["other", 1]], "the one cadgen was still deriving, while it was");
  assert.equal(result.size, 2);
});

// One component cadgen could not mesh is that component's failure: the ready rows beside it, before
// or after it in the response, are announced, and the request goes on for one still pending.
test("a failed component fails alone, with its own error, and the request goes on for the rest", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const P2 = `${"f".repeat(64)}-v1`, P3 = `${"7".repeat(64)}-v1`, O2 = "9".repeat(64);
  let polls = 0;
  globalThis.fetch = async () => {
    polls += 1;
    return json({ viewId: VIEW, job: "job-3", components: {
      bad: { part: P3, state: "failed", error: "component bad: OCCT failed on the component", code: "mesh" },
      part: readyRow(P, O),
      other: polls === 1 ? { part: P2, state: "pending", job: "job-3" } : readyRow(P2, O2),
    } });
  };
  const requests = [{ cid: "bad", part: P3 }, { cid: "part", part: P }, { cid: "other", part: P2 }];
  const announced = [];
  const failures = [];
  const result = await resolveParts(descriptor, requests, {
    onReady: (cid) => announced.push([cid, polls]),
    onFailed: (cid, error) => failures.push([cid, error]),
  });
  assert.deepEqual(announced, [["part", 1], ["other", 2]]);
  assert.equal(failures.length, 1, "a failure is heard once");
  const [[cid, error]] = failures;
  assert.equal(cid, "bad");
  assert.ok(error instanceof PartResolutionError);
  assert.deepEqual([error.cid, error.code, error.message], ["bad", "mesh", "component bad: OCCT failed on the component"]);
  assert.deepEqual([...result.keys()], ["part", "other"]);
  // Without `onFailed` the first failure is the request's, once the response's ready rows are heard.
  polls = 1;
  const heard = [];
  await assert.rejects(
    resolveParts(descriptor, requests.slice(0, 2), { onReady: (ready) => heard.push(ready) }),
    (rejection) => rejection instanceof PartResolutionError && rejection.cid === "bad",
  );
  assert.deepEqual(heard, ["part"]);
});

// Settle on the events the resolver actually produces, never on a stopwatch. The
// abort used to be timed with `setTimeout(10)` and the cancel POST read after
// `setTimeout(0)`, which makes the assertion depend on how fast the runner drains
// its loop: a slow box aborts before the first poll is even in flight, and a
// loaded one reads `calls` before the cancel lands.
test("abort detaches only the known part subscriber", async (t) => {
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
      components: { part: { part: P, state: "pending", job: "job-cancel" } },
    });
  };
  const pending = resolveParts(descriptor, [{ cid: "part", part: P }], {
    signal: controller.signal,
  });
  // The job id only exists once the first poll has answered (an abort before that waits
  // for the answer: the next test); abort while a later poll waits.
  await firstPoll;
  controller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  await cancelled;
  assert.deepEqual(calls.at(-1), {
    url: "/__cad/parts/cancel", body: { job: "job-cancel" },
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
    requestParts: (_body, { signal } = {}) => new Promise((resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      answer = () => resolve({ viewId: VIEW, components: { part: { part: P, state: "pending", job: "job-early" } } });
      posted();
    }),
    cancelPartRequest: async (body) => { cancels.push(body); },
  };
  const pending = resolveParts(descriptor, [{ cid: "part", part: P }], { client, signal: controller.signal });
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
    components: { part: { part: P, state: "failed", error: "bad face", code: "extract" } },
  });
  await assert.rejects(
    resolveParts(descriptor, [{ cid: "part", part: P }]),
    (error) => error instanceof PartResolutionError && error.code === "extract",
  );
  const replacementView = {
    ...descriptor,
    viewId: "f".repeat(64),
    producer: { ...descriptor.producer, producerKey: "9".repeat(64) },
    components: { part: { part: `${"8".repeat(64)}-v1` } },
  };
  globalThis.fetch = async () => json({ ...ready(), replacementView });
  await assert.rejects(
    resolveParts(descriptor, [{ cid: "part", part: P }]),
    (error) => error instanceof PartResolutionError && error.code === "replacement-view"
      && error.replacementView.viewId === replacementView.viewId,
  );
  // A ready row for another part is not this component's.
  globalThis.fetch = async () => json({ ...ready(), components: { part: readyRow(`${"0".repeat(64)}-v1`) } });
  await assert.rejects(resolveParts(descriptor, [{ cid: "part", part: P }]), /omitted part/);
});

test("independent renderer clients each ask their own backend", async () => {
  const calls = [];
  const objects = ["1".repeat(64), "2".repeat(64)];
  const clients = ["http://127.0.0.1:4101", "http://127.0.0.1:4102"].map((origin, index) => ({
    origin,
    requestParts: async (body, options) => { calls.push({ origin, body, signal: options.signal }); return ready(objects[index]); },
  }));
  const controller = new AbortController();
  const results = await Promise.all(clients.map(client => resolveParts(descriptor, [{ cid: "part", part: P }], { client, signal: controller.signal })));
  assert.deepEqual(calls.map(({ origin }) => origin), clients.map(({ origin }) => origin));
  for (let i=0; i<2; i++) {
    assert.equal(results[i].get("part").glb.object, objects[i], "each answer is its own backend's");
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
      return json({ error: "part request must name between 1 and 64 components" }, 400);
    }
    return json({ viewId: VIEW, components: Object.fromEntries(body.components.map(({ cid }) => [cid, readyRow()])) });
  };
  const requests = Array.from({ length: 150 }, (_, index) => ({ cid: `part${index}`, part: P }));
  const result = await resolveParts(descriptor, requests);
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
      ? { part: P, state: "failed", error: "bad face", code: "extract" }
      : readyRow()])) });
  };
  const requests = Array.from({ length: 100 }, (_, index) => ({ cid: `part${index}`, part: P }));
  await assert.rejects(resolveParts(descriptor, requests), (error) => error instanceof PartResolutionError && error.cid === "part70");
});

// A daemon whose worker never announces itself keeps a derivation pending for two minutes before it
// fails. Asked every 640 ms throughout, the first eight parts of a cold w16 open made 1,500 requests
// in that time (each a host call in the CAD app). The first asks stay as quick as they were.
test("a derivation pending for two minutes is asked at a tenth of its wait, at most every 5 s", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 });
  const asks = [];
  const client = {
    origin: "",
    async requestParts() {
      asks.push(Date.now());
      return { viewId: VIEW, job: "job-1", components: { part: { part: P, state: "pending", job: "job-1" } } };
    },
    async cancelPartRequest() { return {}; },
  };
  const controller = new AbortController();
  const settled = resolveWithClient(descriptor, [{ cid: "part", part: P }], { client, signal: controller.signal })
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

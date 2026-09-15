import assert from "node:assert/strict";
import test from "node:test";

import { resolveSurfaceComponents, SurfaceResolutionError } from "./surfaceResolution.js";

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

test("abort detaches only the known surface subscriber", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const calls = [];
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    if (url.endsWith("/cancel")) return new Response(null, { status: 204 });
    return json({
      viewId: VIEW, job: "job-cancel",
      components: { part: { surfaceInput: D, state: "pending", job: "job-cancel" } },
    });
  };
  const pending = resolveSurfaceComponents(descriptor, [{ cid: "part", surfaceInput: D }], {
    signal: controller.signal,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  controller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  await new Promise((resolve) => setTimeout(resolve, 0));
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

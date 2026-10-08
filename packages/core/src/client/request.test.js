import assert from "node:assert/strict";
import test from "node:test";
import { requestViewerJson } from "./request.js";
import { createCadClient } from "./client.js";

const url = "/__cad/artifact?file=part.step";

test("transport failure retains context and never claims compilation failed", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(requestViewerJson(url, { method: "POST" }, "preparing display assets"), (error) => {
    assert.deepEqual(error.failure, {
      kind: "network", url, method: "POST", operation: "preparing display assets", detail: "Failed to fetch"
    });
    assert.equal(error.cause.name, "TypeError");
    return true;
  });
});

test("HTTP failures preserve response status and structured server diagnostics", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ error: { message: "Worker unavailable" } }, { status: 503 }));
  await assert.rejects(requestViewerJson(url, {}, "checking display assets"), (error) => {
    assert.equal(error.failure.kind, "http");
    assert.equal(error.failure.status, 503);
    assert.equal(error.failure.detail, "Worker unavailable");
    return true;
  });
});

test("only an explicit failed build response is classified as compilation", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ state: "failed", error: "Unsupported surface" }, { status: 500 }));
  await assert.rejects(requestViewerJson(url, { method: "POST" }, "preparing display assets"), (error) => {
    assert.equal(error.failure.kind, "compile");
    assert.equal(error.failure.detail, "Unsupported surface");
    return true;
  });
});

test("HTML/error bodies and malformed success JSON report response failures", async (t) => {
  const mock = t.mock.method(globalThis, "fetch", async () => new Response("<html>Not found</html>", { status: 404 }));
  await assert.rejects(requestViewerJson(url, {}, "checking display assets"), (error) => {
    assert.equal(error.failure.kind, "http");
    assert.equal(error.failure.status, 404);
    return true;
  });
  mock.mock.mockImplementation(async () => new Response("{broken"));
  await assert.rejects(requestViewerJson(url, {}, "checking display assets"), (error) => {
    assert.equal(error.failure.kind, "response");
    assert.match(error.message, /unreadable JSON/);
    return true;
  });
});

test("cancellation stays cancellation, including during response decoding", async (t) => {
  const abort = new DOMException("Cancelled", "AbortError");
  const mock = t.mock.method(globalThis, "fetch", async () => { throw abort; });
  await assert.rejects(requestViewerJson(url, {}, "checking display assets"), (error) => error === abort);
  mock.mock.mockImplementation(async () => ({ ok: true, json: async () => { throw abort; } }));
  await assert.rejects(requestViewerJson(url, {}, "checking display assets"), (error) => error === abort);
});

test("a bounded GET reports timeout context but the same bound never aborts a POST", async (t) => {
  const mock = t.mock.method(globalThis, "fetch", async (_requestUrl, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true });
  }));
  await assert.rejects(
    requestViewerJson(url, { method: "GET" }, "checking display assets", { timeoutMs: 5 }),
    (error) => error.failure.kind === "timeout" && error.failure.method === "GET"
  );
  mock.mock.mockImplementation(async () => Response.json({ ok: true }));
  assert.deepEqual(
    await requestViewerJson(url, { method: "POST" }, "preparing display assets", { timeoutMs: 5 }),
    { ok: true }
  );
});

test("a bounded GET is bounded by the server's silence: a long answer that keeps arriving is read, one that stops fails", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  let source;
  // A body arriving a part at a time, which the request's signal ends, as fetch's own does.
  t.mock.method(globalThis, "fetch", async (_requestUrl, { signal }) => new Response(new ReadableStream({
    start(controller) {
      source = controller;
      signal.addEventListener("abort", () => controller.error(signal.reason), { once: true });
    }
  })));
  const encoder = new TextEncoder();
  const read = requestViewerJson(url, {}, "drawing", { timeoutMs: 10_000 });
  await settle();
  for (const part of ['{"primitives":', '[1,2,', '3]}']) {
    t.mock.timers.tick(9_000);
    source.enqueue(encoder.encode(part));
    await settle();
  }
  t.mock.timers.tick(9_000);
  source.close();
  assert.deepEqual(await read, { primitives: [1, 2, 3] });

  const stalled = requestViewerJson(url, {}, "drawing", { timeoutMs: 10_000 });
  await settle();
  source.enqueue(encoder.encode('{"primitives":'));
  await settle();
  t.mock.timers.tick(10_000);
  await assert.rejects(stalled, (error) => {
    assert.equal(error.failure.kind, "timeout");
    assert.match(error.failure.detail, /stopped sending its answer for 10 seconds/);
    return true;
  });
});

test("artifact requests preserve security header, GET/POST semantics and recover normally", async (t) => {
  globalThis.window = {};
  t.after(() => { delete globalThis.window; });
  const calls = [];
  const mock = t.mock.method(globalThis, "fetch", async (requestUrl, options) => {
    calls.push([requestUrl, options]);
    return Response.json({ state: "compiled", ok: true });
  });
  const client = createCadClient({ pollIntervalMs: 0 });
  t.after(() => client.dispose());
  assert.equal((await client.requestArtifactStatus("parts/one two.step")).state, "compiled");
  assert.equal((await client.requestArtifact("parts/one two.step")).state, "compiled");
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[1][1].headers["x-cadgen-viewer"], "1");
  assert.equal(calls[1][1].method, "POST");
  assert.equal(new URL(calls[1][0], "http://local").searchParams.has("force"), false);
  mock.mock.mockImplementation(async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(client.requestArtifactStatus("part.step"), (error) => error.failure.operation === "status");
});

import assert from "node:assert/strict";
import test from "node:test";
import { createModelingRecognitionCache, modelingRecognitionKey } from "./modelingRecognitionCache.js";

test("recognition keys bind exact components without carrying occurrence identity", () => {
  const identity = { surfaceInput: "input-a", surfaceObject: "object-a" };
  assert.equal(modelingRecognitionKey(identity, "https://one.test/a.surf"),
    modelingRecognitionKey(identity, "https://two.test/b.surf"));
  assert.notEqual(modelingRecognitionKey(identity, ""),
    modelingRecognitionKey({ ...identity, surfaceObject: "object-b" }, ""));
  assert.notEqual(modelingRecognitionKey(identity, ""),
    modelingRecognitionKey({ ...identity, surfaceInput: "input-b" }, ""));
  assert.notEqual(modelingRecognitionKey({}, "https://one.test/a.surf"),
    modelingRecognitionKey({}, "https://two.test/a.surf"));
});

test("completed recognition metadata obeys count and byte bounds", () => {
  const value = { tree: [{ label: "Feature" }] };
  const count = createModelingRecognitionCache({ maxEntries: 2 });
  count.set("a", value); count.set("b", value);
  assert.deepEqual(count.get("a"), value);
  count.set("c", value);
  assert.equal(count.get("b"), null, "oldest unvisited component is evicted");
  assert.deepEqual(count.get("a"), value);
  const oneEntryBytes = 2 * (1 + JSON.stringify(value).length);
  const bytes = createModelingRecognitionCache({ maxEntries: 256, maxBytes: oneEntryBytes * 2 - 1 });
  bytes.set("a", value); bytes.set("b", value);
  assert.equal(bytes.get("a"), null, "bytes evict before the component-count cap");
  assert.deepEqual(bytes.get("b"), value);
  assert.equal(bytes.set("oversized", { tree: [{ label: "x".repeat(1000) }] }), false);
  assert.deepEqual(bytes.get("b"), value, "an oversized result does not evict admitted metadata");
});

test("cached metadata is private on read and failures never become reusable results", () => {
  const cache = createModelingRecognitionCache();
  const value = { tree: [{ label: "Original" }] };
  cache.set("a", value);
  value.tree[0].label = "Changed owner";
  const read = cache.get("a");
  read.tree[0].label = "Changed presentation";
  assert.equal(cache.get("a").tree[0].label, "Original");
  assert.equal(cache.set("failure", { error: "Unavailable" }), false);
  assert.equal(cache.set("pending", Promise.resolve(value)), false);
  assert.equal(cache.get("failure"), null);
  assert.equal(cache.get("pending"), null);
});

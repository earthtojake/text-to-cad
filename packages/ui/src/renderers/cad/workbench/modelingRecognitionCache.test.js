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

test("a 317-component assembly reopens without recognizing its components again", () => {
  const cache = createModelingRecognitionCache();
  const components = Array.from({ length: 317 }, (_, index) => {
    const digest = index.toString(16).padStart(64, "0");
    return {
      key: modelingRecognitionKey({ surfaceInput: digest, surfaceObject: digest }, ""),
      result: { tree: [{ id: `feature-${index}`, label: "Base extrude", faces: [1, 2, 3],
        measurements: [["Depth", index + 1, "mm"]], children: [] }], hasFaces: true },
    };
  });
  const bytes = components.reduce((sum, { key, result }) => sum + 2 * (key.length + JSON.stringify(result).length), 0);
  assert.ok(bytes < 8 * 1024 * 1024, "the complete assembly fits the metadata byte budget");
  let recognized = 0;
  const open = () => {
    for (const { key, result } of components) {
      const completed = cache.get(key);
      if (completed) assert.deepEqual(completed, result);
      else { recognized += 1; cache.set(key, result); }
    }
  };
  open();
  assert.equal(recognized, 317);
  // Reopening visits the same component order and inserts every miss. With a
  // count cap below the working set, those insertions evict the whole warm tail.
  open();
  assert.equal(recognized, 317, "every exact component remains reusable on reopen");
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

test('resource service generations isolate completed recognition', () => {
  const identity = {surfaceInput:'same',surfaceObject:'same'};
  const a = {cacheKey: () => 'root:a:generation:1'}, b = {cacheKey: () => 'root:a:generation:2'};
  assert.notEqual(modelingRecognitionKey(identity, '', {resources:a}), modelingRecognitionKey(identity, '', {resources:b}));
});

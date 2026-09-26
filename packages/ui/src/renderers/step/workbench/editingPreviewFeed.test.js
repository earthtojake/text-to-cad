import test from "node:test";
import assert from "node:assert/strict";
import { observeEditingPreview } from "./editingPreviewFeed.js";
test("preview observation borrows the service lifetime", () => {
  const update = () => {}, error = () => {}, stop = () => {};
  const client = { observeEditingPreview(file, onUpdate, onError) {
    assert.equal(file, "part.step"); assert.equal(onUpdate, update); assert.equal(onError, error); return stop;
  } };
  assert.equal(observeEditingPreview("part.step", update, error, {client}), stop);
  assert.throws(() => observeEditingPreview("part.step", update, error), /workspace service/);
});

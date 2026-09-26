import assert from "node:assert/strict";
import test from "node:test";

import { resolveStepModuleFeatures } from "./stepModule.js";

/** Feature resolution runs on every posed frame; its inputs do not change between frames. */

const part = (id, name) => ({ id, occurrenceId: id, name, bounds: { min: [0, 0, 0], max: [1, 1, 1] }, transform: null });
const meshData = () => ({ parts: [part("o1.1", "wheel"), part("o1.2", "wheel"), part("o1.2.1", "spoke"), part("o2", "frame")], bounds: { min: [0, 0, 0], max: [4, 4, 4] } });
const definition = () => ({ features: [
  { id: "wheels", names: ["wheel"], partIds: [] },
  { id: "second", ref: "#o1.2", partIds: [] },
  { id: "ghost", names: ["missing"], partIds: [] },
] });

test("resolves names, occurrence selectors with their descendants, and reports a target that matched nothing", () => {
  const features = resolveStepModuleFeatures(definition(), { meshData: meshData() });
  assert.deepEqual(features.wheels.partIds, ["o1.1", "o1.2"]);
  assert.deepEqual(features.second.partIds, ["o1.2", "o1.2.1"]);
  assert.equal(features.ghost.missing, true);
  assert.equal(features.wheels.missing, false);
});

test("a frame that changed nothing resolves nothing again, and never shares a feature object between frames", () => {
  const mesh = meshData(), module = definition();
  let reads = 0;
  for (const entry of mesh.parts) Object.defineProperty(entry, "name", { get() { reads += 1; return entry.id.startsWith("o1.") && entry.id.length === 4 ? "wheel" : "other"; } });
  const first = resolveStepModuleFeatures(module, { meshData: mesh });
  const readsAfterFirst = reads;
  assert.ok(readsAfterFirst > 0);
  const second = resolveStepModuleFeatures(module, { meshData: mesh });
  assert.equal(reads, readsAfterFirst, "the second frame compared no part names");
  assert.deepEqual(second, first);
  // A render module may write on what it is given; the next frame must not see it.
  second.wheels.partIds = ["tampered"];
  second.wheels.extra = true;
  assert.deepEqual(resolveStepModuleFeatures(module, { meshData: mesh }).wheels, first.wheels);
});

test("a new mesh, new bounds, a new selector runtime or a new definition is resolved afresh", () => {
  const mesh = meshData(), module = definition();
  resolveStepModuleFeatures(module, { meshData: mesh });
  const republished = { ...mesh, parts: [...mesh.parts, part("o1.3", "wheel")] };
  assert.deepEqual(resolveStepModuleFeatures(module, { meshData: republished }).wheels.partIds, ["o1.1", "o1.2", "o1.3"]);
  assert.deepEqual(resolveStepModuleFeatures(module, { meshData: mesh }).wheels.partIds, ["o1.1", "o1.2"]);
  const runtime = { referenceByNormalizedSelector: new Map(), referenceByDisplaySelector: new Map(), referenceMap: new Map() };
  assert.deepEqual(resolveStepModuleFeatures(module, { meshData: mesh, selectorRuntime: runtime }).second.partIds, ["o1.2", "o1.2.1"]);
  assert.deepEqual(resolveStepModuleFeatures({ features: [{ id: "frame", names: ["frame"], partIds: [] }] }, { meshData: mesh }).frame.partIds, ["o2"]);
});

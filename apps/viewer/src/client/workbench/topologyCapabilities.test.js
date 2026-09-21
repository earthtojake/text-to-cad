import assert from "node:assert/strict";
import test from "node:test";

import {
  stepModuleRequiresTopology,
  stepModuleTopologyOccurrenceIds,
} from "./topologyCapabilities.js";

function definition(refs) {
  return { features: refs.map((ref, index) => ({ id: `feature-${index}`, ref })) };
}

test("part and label module targets do not force selector topology", () => {
  assert.equal(stepModuleRequiresTopology(definition(["#o1.2", "#named_part"])), false);
  assert.deepEqual(stepModuleTopologyOccurrenceIds(definition(["#o1.2", "#named_part"])), []);
});

test("entity module targets require topology and retain their occurrence scope", () => {
  const module = definition(["#o1.2.f3", "#o1.2.e4", "#o1.7.s1", "#f2"]);
  assert.equal(stepModuleRequiresTopology(module), true);
  assert.deepEqual(stepModuleTopologyOccurrenceIds(module), ["o1.2", "o1.7"]);
});

test("an opaque module selector requests topology so failure stays loud", () => {
  assert.equal(stepModuleRequiresTopology(definition(["#not a selector"])), false, "invalid token is rejected before capability resolution");
  assert.equal(stepModuleRequiresTopology(definition(["#vendor-specific"])), true);
});

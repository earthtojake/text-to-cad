import assert from "node:assert/strict";
import { test } from "node:test";

import {
  normalizeStepModuleDefinition,
  resolveStepModuleFeatures
} from "../../common/stepModule.js";

// Occurrence ids are positional: o1.13.36 was the right mirror before a rebuild
// and a bonnet extractor blade after it. Names survive renumbering.
const meshData = {
  parts: [
    { id: "o1.13.36", name: "extractor_blade:left_6", bounds: { min: [0, 0, 0], max: [1, 1, 1] } },
    { id: "o1.13.37", name: "extractor_blade:left_7", bounds: { min: [0, 0, 0], max: [1, 1, 1] } },
    { id: "o1.13.38", name: "mirror_housing:right", bounds: { min: [10, 0, 0], max: [11, 1, 1] } },
    { id: "o1.13.39", name: "mirror_glass:right", bounds: { min: [10, 0, 0], max: [11, 1, 1] } },
    { id: "o1.7.1.2", name: "spoke:front_left_0", bounds: { min: [0, 0, 0], max: [1, 1, 1] } },
    { id: "o1.7.1.3", name: "spoke:front_left_0", bounds: { min: [2, 0, 0], max: [3, 1, 1] } }
  ]
};

function featuresFor(features) {
  const definition = normalizeStepModuleDefinition({
    manifest: { schemaVersion: 1, features }
  });
  return resolveStepModuleFeatures(definition, { meshData });
}

test("a feature can target occurrences by name", () => {
  const resolved = featuresFor({
    mirror_right: { names: ["mirror_housing:right", "mirror_glass:right"] }
  });
  assert.deepEqual(resolved.mirror_right.partIds, ["o1.13.38", "o1.13.39"]);
  assert.equal(resolved.mirror_right.missing, false);
});

test("names accepts a bare string", () => {
  const resolved = featuresFor({ housing: { names: "mirror_housing:right" } });
  assert.deepEqual(resolved.housing.partIds, ["o1.13.38"]);
});

test("a repeated name matches every occurrence carrying it", () => {
  const resolved = featuresFor({ spokes: { names: "spoke:front_left_0" } });
  assert.deepEqual(resolved.spokes.partIds, ["o1.7.1.2", "o1.7.1.3"]);
});

test("a name that matches nothing reports missing", () => {
  const resolved = featuresFor({ nope: { names: "no_such_part" } });
  assert.deepEqual(resolved.nope.partIds, []);
  assert.equal(resolved.nope.missing, true, "silent non-match is the bug this replaces");
});

test("names and ref combine", () => {
  const resolved = featuresFor({
    both: { ref: "#o1.13.36", names: ["mirror_glass:right"] }
  });
  assert.deepEqual(resolved.both.partIds.sort(), ["o1.13.36", "o1.13.39"]);
});

test("ref-only features are unchanged", () => {
  const resolved = featuresFor({ byRef: { ref: "#o1.13.38" } });
  assert.deepEqual(resolved.byRef.partIds, ["o1.13.38"]);
  assert.equal(resolved.byRef.missing, false);
});

test("label stays a display string and never selects", () => {
  const resolved = featuresFor({ shown: { ref: "#o1.13.38", label: "mirror_glass:right" } });
  assert.equal(resolved.shown.label, "mirror_glass:right");
  assert.deepEqual(resolved.shown.partIds, ["o1.13.38"], "label must not match occurrences");
});

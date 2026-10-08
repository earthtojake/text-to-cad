import assert from "node:assert/strict";
import test from "node:test";

import {
  initialDisplayLodFromProbe,
  probeInitialDisplayLod,
  producedDisplayLodPlan,
} from "./initialDisplayLod.js";
import { TEST_TESSELLATION_LADDER, installTestTessellationLadder } from "@text-to-cad/core/lib/surf/testing.js";

// The ladder a cadgen server publishes, installed as a host installs it.
installTestTessellationLadder();

const MIB = 1024 * 1024;

function cachedProbes(standard) {
  const requested = [];
  return {
    requested,
    probeEntries: async ([input], tessellation) => {
      requested.push(tessellation);
      return new Map(standard ? [[input, standard]] : []);
    },
  };
}

test("a stored standard mesh opens the component without a SURF URL, sized by its body", async () => {
  const standard = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  const cache = cachedProbes(standard);
  const hit = await probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB, ...cache });
  assert.equal(hit.plan.level, 1);
  assert.equal(hit.cacheProbe, standard);
  assert.equal(hit.plan.estimatedBytes, 4 * MIB);
  assert.equal(hit.plan.fitsDecodeCap, true);
  assert.deepEqual(cache.requested, [TEST_TESSELLATION_LADDER.levels[TEST_TESSELLATION_LADDER.defaultLevel]],
    "the standard tier, and no other, is asked, by both its tolerances");
});

test("a missing, mismatched, refused or unsized standard entry leaves the component cold", async () => {
  const row = { object: "standard", surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  for (const [standard, options] of [
    [null, {}],
    [{ ...row, surfaceObject: "different" }, {}],
    [row, { rejectedCacheObjects: new Set(["standard"]) }],
    [{ ...row, decodedBytes: NaN }, {}],
  ]) {
    assert.equal(await probeInitialDisplayLod({ surfaceInput: "input", surfaceObject: "exact",
      maxInFlightBytes: 256 * MIB, ...cachedProbes(standard), ...options }), null);
  }
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB,
    signal: controller.signal, probeEntries: async (_inputs, _options, { signal }) => signal.throwIfAborted() }),
  { name: "AbortError" });
});

test("a mesh too large to admit with the rest still opens at the standard level, to load alone", () => {
  const huge = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 300 * MIB };
  const warm = initialDisplayLodFromProbe(huge, { surfaceObject: "exact", maxInFlightBytes: 256 * MIB });
  assert.deepEqual(warm.plan, { level: 1, estimatedBytes: 301 * MIB, fitsDecodeCap: false, reason: "warm" });
  assert.deepEqual(producedDisplayLodPlan(huge, { maxInFlightBytes: 256 * MIB }),
    { level: 1, estimatedBytes: 301 * MIB, fitsDecodeCap: false, reason: "produced" });
  assert.equal(producedDisplayLodPlan(null, { maxInFlightBytes: 256 * MIB }), null, "no row, no plan");
});

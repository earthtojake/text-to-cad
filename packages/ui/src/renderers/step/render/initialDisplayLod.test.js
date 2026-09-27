import assert from "node:assert/strict";
import test from "node:test";

import {
  COARSE_SURF_DECODE_EXPANSION_ESTIMATE,
  DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
  LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS,
  estimateInitialSurfDecodeBytes,
  initialDisplayLodPlan,
  probeInitialDisplayLod,
} from "./initialDisplayLod.js";

const MIB = 1024 * 1024;

function cachedProbes(standard, coarse) {
  const requested = [];
  return {
    requested,
    probeEntries: async ([input], options) => {
      const level = options ? 0 : 1;
      requested.push(level);
      const row = level ? standard : coarse;
      return new Map(row ? [[input, row]] : []);
    },
  };
}

test("warm assemblies choose standard before coarse without requiring a SURF URL", async () => {
  const standard = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  const cache = cachedProbes(standard, { ...standard, decodedBytes: MIB });
  const hit = await probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB, ...cache });
  assert.equal(hit.plan.level, 1);
  assert.equal(hit.cacheProbe, standard);
  assert.equal(hit.plan.estimatedBytes, 4 * MIB);
  assert.deepEqual(cache.requested, [1]);
});

test("a missing, mismatched, or oversized standard entry can fall back to admitted coarse", async () => {
  const coarse = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  for (const standard of [null, { ...coarse, surfaceObject: "different" },
    { ...coarse, decodedBytes: 256 * MIB }, { ...coarse, decodedBytes: NaN }]) {
    const cache = cachedProbes(standard, coarse);
    const hit = await probeInitialDisplayLod({ surfaceInput: "input", surfaceObject: "exact",
      maxInFlightBytes: 256 * MIB, ...cache });
    assert.equal(hit.plan.level, 0);
    assert.equal(hit.cacheProbe, coarse);
    assert.deepEqual(cache.requested, [1, 0]);
  }
});

test("a standard body rejected after admission falls back to coarse metadata", async () => {
  const standard = { object: "standard", surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  const coarse = { object: "coarse", surfaceObject: "exact", byteLength: MIB, decodedBytes: MIB };
  const cache = cachedProbes(standard, coarse);
  const hit = await probeInitialDisplayLod({
    surfaceInput: "input",
    maxInFlightBytes: 256 * MIB,
    rejectedCacheObjects: new Set(["standard"]),
    ...cache,
  });
  assert.equal(hit.plan.level, 0);
  assert.equal(hit.cacheProbe, coarse);
  assert.deepEqual(cache.requested, [1, 0]);
});

test("unusable cache metadata leaves cold-load admission in charge", async () => {
  const row = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 256 * MIB };
  assert.equal(await probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB,
    ...cachedProbes(row, row) }), null);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB,
    signal: controller.signal, probeEntries: async (_inputs, _options, { signal }) => signal.throwIfAborted() }),
  { name: "AbortError" });
});

test("large assemblies start coarse while small and medium packages keep the default", () => {
  assert.equal(initialDisplayLodPlan({ componentCount: 9, maxInFlightBytes: 256 * MIB }).level, 1);
  const large = initialDisplayLodPlan({
    componentCount: LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(large.level, 0);
  assert.equal(large.reason, "large-assembly");
  assert.equal(large.sourceExpansionRatio, COARSE_SURF_DECODE_EXPANSION_ESTIMATE);
});

test("any oversized leaf tries coarse only when its independent estimate fits", () => {
  assert.equal(initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 1 * MIB,
    maxInFlightBytes: 256 * MIB,
  }).level, 1, "the other leaves in the same small assembly stay at the default");
  const coarse = initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 5 * MIB,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(coarse.level, 0);
  assert.equal(coarse.reason, "component-admission");
  assert.equal(coarse.estimatedBytes, 160 * MIB);
  assert.equal(coarse.fitsDecodeCap, true);

  const refused = initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 9 * MIB,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(refused.level, 0);
  assert.equal(refused.estimatedBytes, 288 * MIB);
  assert.equal(refused.fitsDecodeCap, false);
  assert.equal(
    estimateInitialSurfDecodeBytes(5 * MIB, DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE),
    320 * MIB,
  );
});

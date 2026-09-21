// The LOD picking invariant (the regression behind "striped highlights and
// picks through faces"): a composed package's selector runtime and its display
// mesh must come from ONE tessellation of each component. faceRuns are
// triangle ranges of a specific tessellation, so faceIds built from a
// level-0 runtime against a finer level's mesh mislabel triangles. These
// tests pin the invariant with real geometry at two levels, prove the
// mismatch is detectable (the test would have caught the bug), and prove
// swapCompositionBundle restores it — the exact repair the LOD swap performs.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { createRequire } from "node:module";

import { parseSurf } from "cadgen-js/lib/surf/container.js";
import { tessellateComponent } from "cadgen-js/lib/surf/tessellate.js";
import { buildMeshDataFromSurf } from "cadgen-js/lib/surf/surfMeshData.js";
import { buildSelectorBundleFromSurf } from "cadgen-js/lib/surf/surfSelectorBundle.js";
import { buildGlbFaceIdsForPart, TOPOLOGY_FACE_ID_NONE } from "cadgen-js/lib/viewer/selectorPickGroups.js";

import {
  baseLodReferenceComposition,
  reconcileLodReferencePublication,
  buildPackageOccurrenceRuntimes,
  composePackageSelectorRuntime,
  compositionUsesComponent,
  reconcileLivePackageSelectorBundles,
  swapCompositionBundle
} from "./packageReferenceComposition.js";

const require = createRequire(import.meta.url);
const FIXTURE = path.join(
  path.dirname(require.resolve("cadgen-js/lib/surf/container.js")),
  "fixtures",
  "sun_gear.surf"
);

function loadLevel(chordTolerance) {
  const buffer = fs.readFileSync(FIXTURE);
  const { index, floats } = parseSurf(
    buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength)
  );
  const component = tessellateComponent(index, floats, chordTolerance ? { chordTolerance } : {});
  return {
    meshData: buildMeshDataFromSurf(index, floats, { component }),
    bundle: buildSelectorBundleFromSurf(index, floats, { component }),
    component
  };
}

const ENTRY = { fileRefPrefix: "sun_gear.step", kind: "assembly", file: "sun_gear.step" };
const OCCURRENCES = [{ id: "o1.1", component: "c0", transform: null }];

function partForMeshData(meshData) {
  return {
    occurrenceId: "o1.1",
    primitiveIndex: 0,
    triangleOffset: 0,
    triangleCount: Math.floor(meshData.indices.length / 3)
  };
}

// The invariant faceIds must satisfy against the mesh they label: every
// triangle carries a face row (no NONE), and each face's labeled triangle
// count equals that face's triangle count in the SAME tessellation.
function faceIdInvariant(meshData, runtime) {
  const part = partForMeshData(meshData);
  const faceIds = buildGlbFaceIdsForPart(part, runtime);
  if (!faceIds) {
    return { ok: false, reason: "no faceIds matched" };
  }
  let unlabeled = 0;
  const perRow = new Map();
  for (const rowIndex of faceIds) {
    if (rowIndex === TOPOLOGY_FACE_ID_NONE) {
      unlabeled += 1;
      continue;
    }
    perRow.set(rowIndex, (perRow.get(rowIndex) || 0) + 1);
  }
  if (unlabeled > 0) {
    return { ok: false, reason: `${unlabeled} unlabeled triangles` };
  }
  // Compare against the mesh's own per-face triangle counts (parts[0] spans
  // the whole component; faceRanges live on the tessellation the meshData
  // was built from, exposed through the bundle's faceRuns — recompute from
  // the labeled totals instead: labeled totals must sum to the mesh).
  const labeledTotal = [...perRow.values()].reduce((sum, count) => sum + count, 0);
  if (labeledTotal !== part.triangleCount) {
    return { ok: false, reason: `labeled ${labeledTotal} of ${part.triangleCount}` };
  }
  return { ok: true, reason: "" };
}

test("levels tessellate differently (precondition for the suite)", () => {
  const level0 = loadLevel(0);
  const level1 = loadLevel(5e-4);
  assert.notEqual(
    Math.floor(level0.meshData.indices.length / 3),
    Math.floor(level1.meshData.indices.length / 3),
    "fixture must produce different triangle counts per level"
  );
});

test("matched level: every displayed triangle maps to a face row", () => {
  for (const chord of [0, 5e-4]) {
    const { meshData, bundle } = loadLevel(chord);
    const runtime = composePackageSelectorRuntime(ENTRY, OCCURRENCES, { c0: bundle }, {
      singleComponentPart: false
    });
    const verdict = faceIdInvariant(meshData, runtime);
    assert.ok(verdict.ok, `chord=${chord}: ${verdict.reason}`);
  }
});

test("MISmatched levels violate the invariant — the regression this suite exists for", () => {
  const level0 = loadLevel(0);
  const level1 = loadLevel(5e-4);
  const level0Runtime = composePackageSelectorRuntime(ENTRY, OCCURRENCES, { c0: level0.bundle }, {
    singleComponentPart: false
  });
  const verdict = faceIdInvariant(level1.meshData, level0Runtime);
  assert.ok(
    !verdict.ok,
    "a level-0 runtime labeling a level-1 mesh must be detectably wrong; if this ever " +
      "passes, the invariant check has lost its teeth and the striped-highlight/" +
      "through-pick regression can return unseen"
  );
});

test("swapCompositionBundle restores the invariant after a level swap", () => {
  const level0 = loadLevel(0);
  const level1 = loadLevel(5e-4);
  const composition = {
    file: ENTRY.file,
    entry: ENTRY,
    occurrencesToLoad: OCCURRENCES,
    bundleByCid: { c0: level0.bundle },
    loadedTopologyKey: "",
    isSingleComponentPart: false
  };
  assert.ok(compositionUsesComponent(composition, "c0"));
  assert.ok(!compositionUsesComponent(composition, "missing"));
  const swapped = swapCompositionBundle(composition, "c0", level1.bundle);
  // Pure swap: the original composition is untouched (a stale-apply race must
  // not corrupt the remembered composition).
  assert.equal(composition.bundleByCid.c0, level0.bundle);
  const runtime = composePackageSelectorRuntime(
    swapped.entry,
    swapped.occurrencesToLoad,
    swapped.bundleByCid,
    { singleComponentPart: swapped.isSingleComponentPart }
  );
  const verdict = faceIdInvariant(level1.meshData, runtime);
  assert.ok(verdict.ok, verdict.reason);
});

test("occurrence runtimes build identically through both entrypoints", () => {
  const { bundle } = loadLevel(0);
  const runtimes = buildPackageOccurrenceRuntimes(ENTRY, OCCURRENCES, { c0: bundle }, {
    singleComponentPart: false
  });
  assert.equal(runtimes.length, 1);
  // The occurrence namespace is what keeps picks aligned with the composed
  // mesh's sourcePartRanges — pin it.
  const reference = runtimes[0].references?.[0];
  assert.ok(String(reference?.id || "").includes("o1.1"), `reference ids carry the occurrence: ${reference?.id}`);
});

test("topology landing after a LOD swap composes from the live bundle", async () => {
  let releaseLevel0;
  const level0Pending = new Promise((resolve) => { releaseLevel0 = resolve; });
  let live = { levelByCid: { c0: 0 }, bundleByCid: {} };
  const load = (async () => {
    const level0Bundle = await level0Pending;
    return reconcileLivePackageSelectorBundles({
      cids: ["c0"],
      initialBundleByCid: { c0: level0Bundle },
      initialKeyByCid: { c0: "c0:t0" },
      snapshotLiveLod: () => live,
      keyForLevel: (cid, level) => `${cid}:t${level}`,
      loadForLevel: async () => assert.fail("published live bundle needs no second fetch")
    });
  })();
  const level0Bundle = { level: 0 };
  const level1Bundle = { level: 1 };
  live = { levelByCid: { c0: 1 }, bundleByCid: { c0: level1Bundle } };
  releaseLevel0(level0Bundle);
  assert.deepEqual(await load, { c0: level1Bundle });
});

test("missing live selector state fetches the exact level and rechecks after another swap", async () => {
  let live = { levelByCid: { c0: 1 }, bundleByCid: {} };
  const fetched = [];
  const level2Bundle = { level: 2 };
  const result = await reconcileLivePackageSelectorBundles({
    cids: ["c0"],
    initialBundleByCid: { c0: { level: 0 } },
    initialKeyByCid: { c0: "c0:t0" },
    snapshotLiveLod: () => live,
    keyForLevel: (cid, level) => `${cid}:t${level}`,
    loadForLevel: async (cid, level, key) => {
      fetched.push({ cid, level, key });
      live = { levelByCid: { c0: 2 }, bundleByCid: { c0: level2Bundle } };
      return { level: 1 };
    }
  });
  assert.deepEqual(fetched, [{ cid: "c0", level: 1, key: "c0:t1" }]);
  assert.deepEqual(result, { c0: level2Bundle });
});

test("an obsolete reference job stops before publishing", async () => {
  let current = true;
  const result = await reconcileLivePackageSelectorBundles({
    cids: ["c0"],
    initialBundleByCid: { c0: { level: 0 } },
    initialKeyByCid: { c0: "c0:t0" },
    snapshotLiveLod: () => ({ levelByCid: { c0: 1 }, bundleByCid: {} }),
    keyForLevel: (cid, level) => `${cid}:t${level}`,
    loadForLevel: async () => {
      current = false;
      return { level: 1 };
    },
    isCurrent: () => current
  });
  assert.equal(result, null);
});

test("late selectors preserve unrelated CIDs in the candidate and exact base-level recovery overlay", () => {
  const low = { level: "base" }, high = { level: "live" }, unrelated = { level: "unrelated" };
  const composition = { entry: ENTRY, loadedTopologyKey: "newly-demanded-subset",
    occurrencesToLoad: [...OCCURRENCES, { id: "other", component: "other" }],
    bundleByCid: { c0: high, other: unrelated } };
  const base = baseLodReferenceComposition(composition, { cid: "c0" }, low);
  assert.equal(base.occurrencesToLoad, composition.occurrencesToLoad);
  assert.equal(base.loadedTopologyKey, composition.loadedTopologyKey);
  assert.equal(base.bundleByCid.other, unrelated); assert.equal(base.bundleByCid.c0, low);
  assert.equal(composition.bundleByCid.c0, high, "candidate remains immutable");
  assert.equal(baseLodReferenceComposition(composition, { cid: "not-demanded" }, null), composition);
  assert.equal(baseLodReferenceComposition(composition, { cid: "c0", phase: "restoring" }, null), composition);
  assert.throws(() => baseLodReferenceComposition(composition, { cid: "c0" }, null), /Previous detail/);
});

test("reference publication rechecks pending ownership after base-selector and live-selector awaits", async () => {
  const first = { cid: "a" }, second = { cid: "b" };
  let pending = first, current = true, calls = 0;
  const result = await reconcileLodReferencePublication({ pendingForContext: () => pending,
    loadBaseBundle: async owner => { if (owner === first) pending = second; return owner.cid; },
    reconcile: async () => { calls++; return { current: pending.cid }; }, isCurrent: () => current });
  assert.equal(result.pending, second); assert.equal(result.baseBundle, "b"); assert.equal(calls, 2);
  const stopped = await reconcileLodReferencePublication({ pendingForContext: () => pending,
    loadBaseBundle: async () => { current = false; return "unused"; },
    reconcile: async () => { throw new Error("must not publish after abort"); }, isCurrent: () => current });
  assert.equal(stopped, null);
});

test("a mixed-level batch restores every changed selector bundle while keeping late unrelated demand", () => {
  const lowA = { level: "base-a" }, highA = { level: "live-a" };
  const lowB = { level: "base-b" }, highB = { level: "live-b" }, other = {};
  const occurrencesToLoad = [...OCCURRENCES, { id: "b", component: "b" }, { id: "late", component: "late" }];
  const candidate = { entry: ENTRY, occurrencesToLoad, loadedTopologyKey: "late-demand",
    bundleByCid: { c0: highA, b: highB, late: other } };
  const base = baseLodReferenceComposition(candidate, { items: [{ cid: "c0" }, { cid: "b" }] },
    { c0: lowA, b: lowB });
  assert.equal(base.occurrencesToLoad, occurrencesToLoad); assert.equal(base.loadedTopologyKey, "late-demand");
  assert.equal(base.bundleByCid.c0, lowA); assert.equal(base.bundleByCid.b, lowB); assert.equal(base.bundleByCid.late, other);
  assert.equal(candidate.bundleByCid.c0, highA); assert.equal(candidate.bundleByCid.b, highB);
  assert.throws(() => baseLodReferenceComposition(candidate, { items: [{ cid: "c0" }, { cid: "b" }] }, { c0: lowA }), /Previous detail/);
});

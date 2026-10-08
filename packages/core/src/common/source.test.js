import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import path from "node:path";
import test from "node:test";

import {
  RENDER_TESSELLATION_FLOORS,
  loadSource as loadSourceInput,
  normalizeRenderTessellation,
  tessellationForSnapshotQuality
} from "./source.js";
import { renderAssetSourceScope } from "../lib/renderAssetSourceScope.js";
import {
  createTessellationCache, createHttpTessellationCacheProvider, encodeTessellationCacheBatch,
  tessellationCacheKey,
} from "../lib/surf/tessellationCache.js";
import { encodeMeshFixture, memoryMeshProvider, meshFixture, probeRowFor, surfFixture } from "../lib/surf/__tests__/meshFixtures.js";

// A host's mesh store that records every key probed, and meshes on request what `produce` holds.
function recordingMeshStore(requested = [], { stored = [], produce = [] } = {}) {
  const store = memoryMeshProvider(stored, { produce });
  const probeMany = store.probeMany;
  store.probeMany = async (keys) => { requested.push(...keys); return probeMany(keys); };
  return store;
}

// Composition coverage for the scoping of render asset caches.
//
// loadSource is the only place a resolved render job meets the page-lifetime render asset caches
// (common/headlessRenderEntry.js is its sole production caller), and the caches it populates live
// in lib/stepRenderAssetClient.js. These tests drive the real composition — real loadSource, real
// client, real wiring — with only globalThis.fetch stubbed, so they fail if the scope is not
// declared, if the assertion is missing from the client the snapshot batch loads through, or if a
// collision is swallowed on the way out. Unit-level coverage of the assertion itself lives in
// lib/stepRenderAssetClient.test.js and lib/renderAssetClient.test.js.
//
// The stubbed asset body is deliberately not a decodable GLB: these jobs supply meshData, so the
// property under test is which source owns the cached bytes, not topology decoding (covered in
// lib/stepRenderAssetClient.test.js). Loading the mesh itself needs the three runtime and is out
// of scope for a unit test; it reads the same byte cache asserted here.

function renderAssetUrl() {
  return `/__render_asset/part.glb?v=${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

function stepJob({ inputPath, rootPath, glbUrl }) {
  return {
    kind: "step",
    meshData: meshData(),
    resolved: {
      kind: "step",
      ...(inputPath === undefined ? {} : { inputPath }),
      ...(rootPath === undefined ? {} : { rootPath }),
      glbUrl
    }
  };
}

function stubAssetFetch(t, url) {
  const originalFetch = globalThis.fetch;
  const state = { fetchCount: 0 };
  globalThis.fetch = async (requestUrl) => {
    assert.equal(String(requestUrl), url);
    state.fetchCount += 1;
    return new Response(new Uint8Array([state.fetchCount]), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  return state;
}

function meshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2]),
    bounds: {
      min: [0, 0, 0],
      max: [1, 1, 0]
    },
    parts: []
  };
}

test("snapshot tessellation is explicit, finite and restricted to exact surfaces", async () => {
  assert.deepEqual(normalizeRenderTessellation(undefined), {});
  assert.deepEqual(normalizeRenderTessellation({ chordTolerance: .0001, angleTolerance: .025 }),
    { chordTolerance: .0001, angleTolerance: .025 });
  for (const value of [0, -1, NaN, Infinity, "0.01"]) {
    assert.throws(() => normalizeRenderTessellation({ chordTolerance: value }), /positive finite/);
  }
  assert.throws(() => normalizeRenderTessellation({ quality: "high" }), /Unknown/);
  assert.throws(() => normalizeRenderTessellation([]), /must be an object/);
  // A floor, not a preference: below it the page tessellates until the
  // renderer dies and the caller only sees a lost driver connection.
  assert.throws(() => normalizeRenderTessellation({ chordTolerance: 1e-12 }), /at least 0.00001/);
  assert.throws(() => normalizeRenderTessellation({ angleTolerance: 1e-6 }), /at least 0.005/);
  assert.deepEqual(normalizeRenderTessellation(RENDER_TESSELLATION_FLOORS), { ...RENDER_TESSELLATION_FLOORS });
  await assert.rejects(() => loadSource({ meshData: meshData(),
    quality: { tessellation: { chordTolerance: .001 } } }), /only for STEP/);
  await assert.rejects(() => loadSource({ kind: "step", meshData: meshData(),
    quality: { tessellation: { chordTolerance: .001 } } }), /exact-surface STEP package/);
});

test("snapshot quality selects bounded shared tessellation policy", () => {
  assert.deepEqual(tessellationForSnapshotQuality({}), {});
  assert.deepEqual(tessellationForSnapshotQuality({ display: { mode: "render", lighting: { quality: "preview" } } }), {});
  assert.deepEqual(
    tessellationForSnapshotQuality({ display: { mode: "render", lighting: { quality: "final" } } }),
    { chordTolerance: 0.00015, angleTolerance: 0.35 }
  );
  assert.deepEqual(tessellationForSnapshotQuality({
    display: { mode: "render", lighting: { quality: "final" } },
    quality: { tessellation: { chordTolerance: 0.001 } }
  }), { chordTolerance: 0.001 });
  assert.throws(() => tessellationForSnapshotQuality({
    display: { mode: "render", lighting: { quality: "ultra" } }
  }), /quality/i);
});

// The roller as a one-component package, bound to its fixture identity.
function rollerPackage(extra = {}) {
  const { surfaceInput, surfaceObject } = surfFixture("cam_follower_roller");
  return { kind: "step", package: {
    descriptor: { components: { roller: { surfaceInput, surfaceObject } },
      occurrences: [{ id: "o1.1", name: "roller", component: "roller" }],
      assembly: { root: { id: "o1", name: "macro", nodeType: "assembly", children: [
        { id: "o1.1", name: "roller", nodeType: "part", children: [] }
      ] } } },
    componentUrls: { roller: "/macro-fixture/roller.surf" },
    ...extra,
  } };
}

test("a package's missing meshes are asked of the host once, then read as stored ones", async (t) => {
  const oldFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => { fetches += 1; return new Response(null, { status: 404 }); };
  const requested = [];
  const store = recordingMeshStore(requested, {
    produce: [meshFixture("cam_follower_roller", 1).bytes, meshFixture("cam_follower_roller", 0).bytes],
  });
  setTessellationCacheProvider(store);
  t.after(() => { globalThis.fetch = oldFetch; setTessellationCacheProvider(null); });
  const coldStages = {};
  const canonical = await loadSource(rollerPackage(), { stageTimings: coldStages });
  assert.equal(coldStages.sourceLoad.producedCount, 1, "the default tier was meshed on request");
  assert.equal(coldStages.sourceLoad.cacheHitCount, 1);
  assert.equal(coldStages.sourceLoad.cacheMissCount, 0);
  for (const stage of ["probeMs", "produceMs", "cacheReadMs", "meshBuildMs"]) {
    assert.ok(coldStages.sourceLoad[stage] >= 0, stage);
  }
  // An explicit macro tessellation reads its own mesh, keyed by its own tolerances.
  const coarseJob = { ...rollerPackage(), quality: { tessellation: { chordTolerance: 2e-3, angleTolerance: 1.4 } } };
  const coarse = await loadSource(coarseJob);
  assert.ok(coarse.meshData.indices.length < canonical.meshData.indices.length);
  assert.notEqual(requested[0], requested[1]);
  assert.equal(store.counts.produced, 2);
  const warmStages = {};
  const warm = await loadSource(coarseJob, { stageTimings: warmStages });
  assert.equal(warmStages.sourceLoad.producedCount, undefined, "a stored mesh is asked for nothing");
  assert.equal(store.counts.produced, 2);
  assert.equal(warm.meshData.indices.length, coarse.meshData.indices.length);
  assert.equal(fetches, 0, "no SURF is read to draw a package");
});

// A body the store named but did not hand back is read again, alone, before its component is a
// miss; and one that stays unreadable says so, not that nothing meshed it.
test("a stored mesh whose batched read fails is read again alone; one that stays unreadable says so", async (t) => {
  const store = recordingMeshStore([], { produce: [meshFixture("cam_follower_roller", 1).bytes] });
  const batch = store.getManyProbed;
  let batches = 0;
  store.getManyProbed = async (rows) => { batches += 1; return batches === 1 ? null : batch(rows); };
  setTessellationCacheProvider(store);
  t.after(() => setTessellationCacheProvider(null));
  const stages = {};
  const source = await loadSource(rollerPackage(), { stageTimings: stages });
  assert.ok(source.meshData.indices.length > 0);
  assert.equal(stages.sourceLoad.cacheHitCount, 1);
  assert.deepEqual([batches, store.counts.reads], [1, 1], "the failed batch's body was read once more, alone");
  store.getManyProbed = async (rows) => rows.map(() => null);
  store.getProbed = async () => null;
  await assert.rejects(loadSource(rollerPackage()),
    /component roller: the store holds its mesh at this tessellation, but it could not be read/);
});

test("a static package reads each component's own mesh file; a component nothing meshed is an error", async (t) => {
  const oldFetch = globalThis.fetch;
  const mesh = meshFixture("cam_follower_roller", 1);
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(String(url));
    return String(url).endsWith("/roller.glb")
      ? new Response(mesh.bytes.slice(), { status: 200 })
      : new Response(null, { status: 404 });
  };
  t.after(() => { globalThis.fetch = oldFetch; setTessellationCacheProvider(null); });
  // The docs hero: no mesh store at all, a mesh beside each surf.
  setTessellationCacheProvider(null);
  const job = rollerPackage({ meshUrls: { roller: "/hero/components/roller.glb" } });
  const source = await loadSource(job);
  assert.ok(source.meshData.indices.length > 0);
  assert.deepEqual(fetched, ["/hero/components/roller.glb"], "only the mesh file is read");
  // A mesh at another tessellation is not this component's mesh at that tessellation.
  await assert.rejects(loadSource({ ...job, quality: { tessellation: { chordTolerance: 2e-3, angleTolerance: 1.4 } } }),
    /is not its mesh at this tessellation/);
  await assert.rejects(loadSource(rollerPackage()), /cadgen meshes every component before a page draws it/);
});

const WARM_COMPONENT = {
  positions: new Float32Array([0, 0, 0, 2, 0, 0, 0, 3, 0]),
  normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  indices: new Uint32Array([0, 1, 2]),
  faceRanges: [{ ord: 1, indexStart: 0, indexCount: 3 }], edges: [],
  bounds: { min: [0, 0, 0], max: [2, 3, 0] }, scale: Math.sqrt(13),
};

/** A warm package of `count` cached components, loaded through an HTTP cache provider. */
async function loadWarmPackage(t, count, providerOptions = {}) {
  const component = WARM_COMPONENT;
  const surfaceObject = "a".repeat(64);
  const components = {}, componentUrls = {}, rows = {}, bodies = {};
  const occurrences = [];
  for (let n = 0; n < count; n += 1) {
    const cid = `c${n}`, surfaceInput = createHash("sha256").update(cid).digest("hex");
    const key = tessellationCacheKey(surfaceInput);
    const body = encodeMeshFixture(component, { surfaceInput, surfaceObject });
    rows[key] = probeRowFor(body);
    bodies[key] = body;
    components[cid] = { surfaceInput, surfaceObject };
    componentUrls[cid] = `/never-fetch/${cid}.surf`;
    occurrences.push({ id: `o${n}`, component: cid });
  }
  const probes = [], batches = [];
  const oldFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = oldFetch; setTessellationCacheProvider(null); });
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    if (String(url).endsWith("/probe")) {
      probes.push(body.tessellationInputs.length);
      assert.ok(body.tessellationInputs.length <= 256);
      return new Response(JSON.stringify({ entries: Object.fromEntries(
        body.tessellationInputs.map((key) => [key, rows[key]]),
      ) }));
    }
    assert.ok(String(url).endsWith("/batch"), "a warm package never fetches SURF");
    assert.ok(body.entries.length <= 256);
    const payload = encodeTessellationCacheBatch(body.entries.map((entry) => bodies[entry.tessellationInput]));
    batches.push({ count: body.entries.length, bytes: payload.byteLength });
    return new Response(payload, { headers: { "content-length": String(payload.byteLength) } });
  };
  // Every body frames the same size here; options may be worked out from it.
  const entryBytes = 4 + ((Object.values(bodies)[0].byteLength + 3) & ~3);
  const options = typeof providerOptions === "function" ? providerOptions(entryBytes) : providerOptions;
  setTessellationCacheProvider(createHttpTessellationCacheProvider({ origin: "http://cache.test", ...options }));
  const stageTimings = {};
  const source = await loadSource({ kind: "step", package: {
    descriptor: { components, occurrences, assembly: { root: { id: "root", nodeType: "assembly",
      children: occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) } } }, componentUrls,
  } }, { stageTimings });
  assert.equal(source.meshData.parts.length, count);
  for (const part of source.meshData.parts) {
    assert.deepEqual(part.sourceMesh.vertices, component.positions);
    assert.deepEqual(part.sourceMesh.normals, component.normals);
    assert.deepEqual(part.sourceMesh.indices, component.indices);
  }
  assert.equal(stageTimings.sourceLoad.cacheHitCount, count);
  assert.equal(stageTimings.sourceLoad.cacheMissCount, 0);
  assert.equal(stageTimings.sourceLoad.cacheBatchCount, batches.length);
  assert.equal(stageTimings.sourceLoad.tessellateMs, undefined);
  assert.equal(stageTimings.sourceLoad.surfaceReadMs, undefined);
  assert.ok(stageTimings.sourceLoad.cacheReadMs >= 0);
  return { probes, batches, options };
}

test("warm packages split probes and small bodies at the host's 256-entry bound", async (t) => {
  const { probes, batches } = await loadWarmPackage(t, 513);
  assert.deepEqual(probes, [256, 256, 1]);
  assert.deepEqual(batches.map((batch) => batch.count), [256, 256, 1]);
});

test("a warm package's batches stay within the ceiling its cache's transport declares", async (t) => {
  // A ceiling of 100 bodies, header included, groups by bytes long before the 256-entry bound,
  // and every component is still read from the cache.
  const { batches, options } = await loadWarmPackage(t, 250, (entryBytes) => ({ maxBatchBytes: 12 + 100 * entryBytes }));
  assert.deepEqual(batches.map((batch) => batch.count), [100, 100, 50]);
  assert.ok(batches.every((batch) => batch.bytes <= options.maxBatchBytes));
});

test("a package draws the finish, colour and opacity cadgen composed onto its occurrences", async (t) => {
  const { surfaceInput, surfaceObject } = surfFixture("cam_follower_roller");
  setTessellationCacheProvider(memoryMeshProvider([meshFixture("cam_follower_roller", 1).bytes]));
  t.after(() => { setTessellationCacheProvider(null); });
  // The descriptor as cadgen serves it for display (`source_sidecar.apply_appearance`): the
  // assigned occurrence already carries what its material resolves to.
  const descriptor = {
    kind: "assembly-package",
    components: { "appearance-cid": { surfaceInput, surfaceObject } },
    occurrences: [{
      id: "o1.1", name: "roller", component: "appearance-cid",
      materialId: "polished", materialName: "Polished",
      material: { roughness: 0.15, metalness: 0.03, clearcoat: 0.8, clearcoatRoughness: 0.26, opacity: 0.5 },
      baseColor: "#336699", opacity: 0.5
    }],
    assembly: { root: { id: "o1", name: "appearance", nodeType: "assembly", children: [
      { id: "o1.1", name: "roller", nodeType: "part", children: [] }
    ] } }
  };
  const source = await loadSource({
    kind: "step",
    package: { descriptor, componentUrls: { "appearance-cid": "/appearance/roller.surf" } }
  });
  const [part] = source.meshData.parts;
  assert.deepEqual(part.material, descriptor.occurrences[0].material);
  assert.equal(part.materialId, "polished");
  assert.equal(part.materialName, "Polished");
  assert.equal(part.color, "#336699");
  assert.equal(part.opacity, 0.5, "the opacity is the one cadgen folded, not multiplied again here");
});

// A snapshot job carries what cadgen resolved: the articulation and the control vector it
// validated at the door (a pose NAME is resolved there too). The page plays, it checks nothing.
let tessellationCache = createTessellationCache();
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  tessellationCache = createTessellationCache({ provider });
}
const loadSource = (input, options = {}) => loadSourceInput(input, { tessellationCache, ...options });

const HINGE_ARTICULATION = {
  schemaVersion: 1,
  controls: [{ id: "swing", label: "swing", unit: "deg", min: 0, max: 120, default: 0 }],
  joints: [{ id: "swing", parent: null, kind: "revolute", origin: [0, 0, 0], axis: [0, 0, 1],
    turn: { bias: 0, terms: [["swing", 1]] } }],
  carries: { swing: ["flap"] },
  handles: [{ id: "swing", joint: "swing", dof: "turn", control: "swing", weight: 1, label: "swing", unit: "deg", min: 0, max: 120 }],
  poses: { open: { swing: 90 }, ajar: { swing: 15 } },
  opening: { swing: 0 }
};

function poseJob(controls, articulation = HINGE_ARTICULATION) {
  return {
    kind: "step",
    meshData: meshData(),
    resolved: { kind: "step", articulation, controls, inputPath: "/models/hinge.step" }
  };
}

test("a job's pose is cadgen's articulation at the control vector cadgen validated", async () => {
  const source = await loadSource(poseJob({ swing: 90 }));
  assert.equal(source.pose.articulation, HINGE_ARTICULATION);
  assert.deepEqual(source.pose.values, { swing: 90 });
});

test("a job with an articulation and no controls poses the opening", async () => {
  const source = await loadSource(poseJob(undefined));
  assert.deepEqual(source.pose.values, { swing: 0 });
});

test("control values against a model with no articulation have nothing to drive", async () => {
  await assert.rejects(() => loadSource(poseJob({ swing: 45 }, null)), /declares no kinematics/);
  assert.equal((await loadSource(poseJob(undefined, null))).pose, null);
});

test("loadSource refuses a render asset cached for a different job source", async (t) => {
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  const first = await loadSource(stepJob({
    inputPath: "/models/first/part.step",
    rootPath: "/models/first",
    glbUrl
  }));
  assert.equal(first.kind, "step");
  assert.equal(fetches.fetchCount, 1);

  await assert.rejects(
    () => loadSource(stepJob({
      inputPath: "/models/second/part.step",
      rootPath: "/models/second",
      glbUrl
    })),
    /cached for source \/models\/first\/part\.step but was requested for \/models\/second\/part\.step/
  );
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource refuses a collision between two sources under one render root", async (t) => {
  // Same directory, so the server would route this URL identically for both jobs: the scope has to
  // be the source file, not its parent, or a future URL-minting regression inside one directory
  // stays invisible.
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  await loadSource(stepJob({ inputPath: "/models/a.step", rootPath: "/models", glbUrl }));
  await assert.rejects(
    () => loadSource(stepJob({ inputPath: "/models/b.step", rootPath: "/models", glbUrl })),
    /refusing to reuse it/
  );
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource shares one render asset fetch across jobs against the same file", async (t) => {
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);
  const job = () => stepJob({
    inputPath: "/models/only/part.step",
    rootPath: "/models/only",
    glbUrl
  });

  const results = [await loadSource(job()), await loadSource(job()), await loadSource(job())];

  assert.equal(results.length, 3);
  for (const result of results) {
    assert.equal(result.kind, "step");
  }
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource still serves single-source callers that pass no resolved job", async (t) => {
  // The shape documented in packages/core/docs/render-pipeline.md for interactive viewer/docs use,
  // and the one docs/src/components/hero-step-render.tsx actually calls: no resolved packet, one
  // source per page. It must keep working unscoped — requiring a source path here would break a
  // documented public contract and the docs hero renderer.
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    glbUrl,
    cadPath: "models/part.step"
  });

  assert.equal(source.kind, "step");
  assert.equal(source.glbUrl, glbUrl);
  assert.equal(renderAssetSourceScope(), "");
  assert.equal(fetches.fetchCount, 1);

  // Repeating it reuses the cached asset, exactly as before.
  await loadSource({ kind: "step", meshData: meshData(), glbUrl, cadPath: "models/part.step" });
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource refuses to fetch a render asset for a resolved job that does not name its source", async (t) => {
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  await assert.rejects(
    () => loadSource(stepJob({ rootPath: "/models/first", glbUrl })),
    /require resolved\.inputPath to scope the render asset cache/
  );
  // A blank or non-string source is not a source: it must fail closed rather than coerce into the
  // same bucket as the interactive viewer's unscoped default.
  for (const inputPath of ["", "   ", 0, false, {}, ["/models/first/part.step"]]) {
    await assert.rejects(
      () => loadSource(stepJob({ inputPath, rootPath: "/models/first", glbUrl })),
      /require resolved\.inputPath to scope the render asset cache/
    );
  }
  assert.equal(fetches.fetchCount, 0);
});

test("loadSource leaves no source scope behind", async (t) => {
  const glbUrl = renderAssetUrl();
  stubAssetFetch(t, glbUrl);
  assert.equal(renderAssetSourceScope(), "");

  await loadSource(stepJob({
    inputPath: "/models/kept/part.step",
    rootPath: "/models/kept",
    glbUrl
  }));
  assert.equal(renderAssetSourceScope(), "");

  await assert.rejects(() => loadSource(stepJob({ glbUrl })));
  assert.equal(renderAssetSourceScope(), "");
});

test("loadSource takes an articulation and animation inline for STEP sources", async () => {
  const animation = { clips: [{ id: "swing", label: "Swing", duration: 4, loop: true, tracks: [] }] };
  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    cadPath: "part.step",
    articulation: HINGE_ARTICULATION,
    controls: { swing: 90 },
    animation
  });

  assert.equal(source.kind, "step");
  assert.deepEqual(source.pose.values, { swing: 90 });
  assert.equal(source.animation, animation);
});

test("render display source loading keeps kinematics and supplied CAD runtimes", async () => {
  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    display: { mode: "render" },
    cadPath: "hinge.step",
    glbUrl: "/unused-topology.glb",
    articulation: HINGE_ARTICULATION,
    controls: { swing: 45 },
    selectorRuntime: { stale: true },
    displayEdgeRuntime: { stale: true }
  });
  assert.equal(source.kind, "step");
  assert.deepEqual(source.selectorRuntime, { stale: true });
  assert.deepEqual(source.displayEdgeRuntime, { stale: true });
  assert.deepEqual(source.pose.values, { swing: 45 });
});

test("render-only source loading leaves STEP topology lazy", async (t) => {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => { fetches += 1; throw new Error("unexpected topology fetch"); };
  t.after(() => { globalThis.fetch = originalFetch; });

  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    display: { mode: "render" },
    glbUrl: "/unused-topology.glb"
  });

  assert.equal(source.selectorRuntime, null);
  assert.equal(source.displayEdgeRuntime, null);
  assert.equal(fetches, 0);
});

// Every other file family is drawn by its own scene builder, the one its viewer renderer
// uses (common/headlessScene.js); loadSource flattens none of them into mesh data.
test("loadSource composes STEP documents and refuses every other file family by name, fetching nothing", async (t) => {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => { fetches += 1; throw new Error("unexpected fetch"); };
  t.after(() => { globalThis.fetch = originalFetch; });
  for (const input of ["/models/part.stl", "/models/part.glb", "/models/robot.urdf",
    { kind: "3mf", meshData: meshData() }, { kind: "glb", url: "/models/part.glb" },
    { resolved: { kind: "sdf", url: "/models/robot.sdf", inputPath: "/models/robot.sdf" } }, { kind: "srdf", url: "/models/robot.srdf" }]) {
    await assert.rejects(() => loadSource(input), /loadSource composes a STEP document; a (STL|GLB|URDF|3MF|SDF|SRDF) is drawn by its own scene builder/,
      JSON.stringify(input));
  }
  assert.equal(fetches, 0);
});

test("retired render snapshot field is rejected before loading a source", async (t) => {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => { fetches += 1; throw new Error("unexpected fetch"); };
  t.after(() => { globalThis.fetch = originalFetch; });
  for (const render of [null, false, "dark", { unknown: true }]) {
    await assert.rejects(() => loadSource({ kind: "step", url: "/never.step", render }), /Unsupported snapshot field: render/);
  }
  assert.equal(fetches, 0);
});

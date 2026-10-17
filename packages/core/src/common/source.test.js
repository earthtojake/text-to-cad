import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { loadSource as loadSourceInput, packageSourceFromBaseUrl } from "./source.js";
import {
  createTessellationCache, createHttpTessellationCacheProvider, encodeTessellationCacheBatch,
} from "../lib/parts/tessellationCache.js";
import { encodeMeshFixture, memoryMeshProvider, meshFixture, partRowFor } from "../lib/parts/__tests__/meshFixtures.js";

// A host's part store that records every part probed.
function recordingMeshStore(requested = [], { stored = [] } = {}) {
  const store = memoryMeshProvider(stored);
  const probeMany = store.probeMany;
  store.probeMany = async (keys) => { requested.push(...keys); return probeMany(keys); };
  return store;
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

// The roller as a one-component package, naming its fixture part.
function rollerPackage(extra = {}, component = {}) {
  const { part } = meshFixture("cam_follower_roller");
  return { kind: "step", package: {
    descriptor: { components: { roller: { part, ...component } },
      occurrences: [{ id: "o1.1", name: "roller", component: "roller" }],
      assembly: { root: { id: "o1", name: "macro", nodeType: "assembly", children: [
        { id: "o1.1", name: "roller", nodeType: "part", children: [] }
      ] } } },
    ...extra,
  } };
}

test("a package's meshes are read from the store; one it lacks is an error, never made by the page", async (t) => {
  const oldFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => { fetches += 1; return new Response(null, { status: 404 }); };
  const requested = [];
  const roller = meshFixture("cam_follower_roller");
  const store = recordingMeshStore(requested, { stored: [roller.bytes] });
  setTessellationCacheProvider(store);
  t.after(() => { globalThis.fetch = oldFetch; setTessellationCacheProvider(null); });
  const stages = {};
  const source = await loadSource(rollerPackage(), { stageTimings: stages });
  assert.ok(source.meshData.indices.length > 0);
  assert.equal(stages.sourceLoad.cacheHitCount, 1);
  assert.equal(stages.sourceLoad.cacheMissCount, 0);
  for (const stage of ["probeMs", "cacheReadMs", "meshBuildMs"]) {
    assert.ok(stages.sourceLoad[stage] >= 0, stage);
  }
  // It asks the store for the part its component names, and for nothing else.
  assert.deepEqual(requested, [roller.part]);
  assert.equal(fetches, 0, "nothing else is read to draw a package");
  setTessellationCacheProvider(recordingMeshStore());
  await assert.rejects(loadSource(rollerPackage()), /component roller has no mesh; cadgen meshes every component/);
});

// A component cadgen could not mesh says why in its tree entry (cadgen.store.view): the page leaves
// it out on its own, as the viewer's loader does (`componentFailed`), and draws the rest. Only a
// package none of whose components is left fails, with the first failure.
test("a component cadgen could not mesh is left out and the rest drawn; with none left the load fails", async (t) => {
  const requested = [];
  const roller = meshFixture("cam_follower_roller");
  setTessellationCacheProvider(recordingMeshStore(requested, { stored: [roller.bytes] }));
  t.after(() => setTessellationCacheProvider(null));
  const failure = "MeshProductionError: ValueError: boom";
  const job = rollerPackage();
  const { descriptor } = job.package;
  descriptor.components.peg = { part: `${"1".repeat(64)}-v1`, failure };
  descriptor.occurrences.push({ id: "o1.2", name: "peg", component: "peg" });
  descriptor.assembly.root.children.push({ id: "o1.2", name: "peg", nodeType: "part", children: [] });
  const stages = {};
  const source = await loadSource(job, { stageTimings: stages });
  assert.deepEqual(source.meshData.parts.map((part) => part.occurrenceId), ["o1.1"]);
  assert.deepEqual(requested, [roller.part], "nothing is asked of the store for the part cadgen could not mesh");
  assert.equal(stages.sourceLoad.componentCount, 1);
  descriptor.components.roller.failure = failure;
  await assert.rejects(loadSource(job),
    /component roller could not be meshed \(MeshProductionError: ValueError: boom\)/);
});

// A body the store named but did not hand back is read again, alone, before its component is a
// miss; and one that stays unreadable says so, not that nothing meshed it.
test("a stored mesh whose batched read fails is read again alone; one that stays unreadable says so", async (t) => {
  const store = recordingMeshStore([], { stored: [meshFixture("cam_follower_roller").bytes] });
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
    /component roller: the store holds its mesh, but it could not be read/);
});

test("a static package reads each component's own mesh file; a component nothing meshed is an error", async (t) => {
  const oldFetch = globalThis.fetch;
  const mesh = meshFixture("cam_follower_roller");
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(String(url));
    return String(url).endsWith("/roller.glb")
      ? new Response(mesh.bytes.slice(), { status: 200 })
      : new Response(null, { status: 404 });
  };
  t.after(() => { globalThis.fetch = oldFetch; setTessellationCacheProvider(null); });
  // The docs hero: no part store at all, and each component's tree entry names its mesh file
  // beside the tree.
  setTessellationCacheProvider(null);
  const hero = (component) => packageSourceFromBaseUrl("/hero/", rollerPackage({}, component).package.descriptor);
  const job = hero({ glb: "components/roller.glb" });
  assert.deepEqual(job.package.meshUrls, { roller: "/hero/components/roller.glb" });
  const source = await loadSourceInput(job);
  assert.ok(source.meshData.indices.length > 0);
  assert.deepEqual(fetched, ["/hero/components/roller.glb"], "only the mesh file is read");
  // A file of another part is not this component's mesh.
  await assert.rejects(loadSource(hero({ glb: "components/roller.glb", part: `${"0".repeat(64)}-v1` })),
    /is not its part's mesh/);
  assert.throws(() => hero({}), /component roller declares no glb path/);
  await assert.rejects(loadSource(rollerPackage()), /cadgen meshes every component before a page draws it/);
});

const WARM_COMPONENT = {
  positions: new Float32Array([0, 0, 0, 2, 0, 0, 0, 3, 0]),
  normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  indices: new Uint32Array([0, 1, 2]),
  faceRanges: [{ ord: 1, indexStart: 0, indexCount: 3 }], edges: [],
  bounds: { min: [0, 0, 0], max: [2, 3, 0] },
};

/** A warm package of `count` stored parts, loaded through an HTTP cache provider. */
async function loadWarmPackage(t, count, providerOptions = {}) {
  const component = WARM_COMPONENT;
  const components = {}, records = {}, bodies = {};
  const occurrences = [];
  for (let n = 0; n < count; n += 1) {
    const cid = `c${n}`, part = `${createHash("sha256").update(cid).digest("hex")}-v1`;
    const body = encodeMeshFixture(component, { part });
    // A host answers each stored part's record by its key.
    const { part: _part, ...record } = partRowFor(body);
    records[part] = record;
    bodies[part] = body;
    components[cid] = { part };
    occurrences.push({ id: `o${n}`, component: cid });
  }
  const probes = [], batches = [];
  const oldFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = oldFetch; setTessellationCacheProvider(null); });
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    if (String(url).endsWith("/probe")) {
      probes.push(body.parts.length);
      assert.ok(body.parts.length <= 256);
      return new Response(JSON.stringify({ entries: Object.fromEntries(
        body.parts.map((part) => [part, records[part]]),
      ) }));
    }
    assert.ok(String(url).endsWith("/batch"), "a warm package reads nothing but the store");
    assert.ok(body.entries.length <= 256);
    const payload = encodeTessellationCacheBatch(body.entries.map((entry) => bodies[entry.part]));
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
      children: occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) } } },
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
  const { part, bytes } = meshFixture("cam_follower_roller");
  setTessellationCacheProvider(memoryMeshProvider([bytes]));
  t.after(() => { setTessellationCacheProvider(null); });
  // The descriptor as cadgen serves it for display (`source_sidecar.apply_appearance`): the
  // assigned occurrence already carries what its material resolves to.
  const descriptor = {
    kind: "assembly-package",
    components: { "appearance-cid": { part } },
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
  const source = await loadSource({ kind: "step", package: { descriptor } });
  const [occurrence] = source.meshData.parts;
  assert.deepEqual(occurrence.material, descriptor.occurrences[0].material);
  assert.equal(occurrence.materialId, "polished");
  assert.equal(occurrence.materialName, "Polished");
  assert.equal(occurrence.color, "#336699");
  assert.equal(occurrence.opacity, 0.5, "the opacity is the one cadgen folded, not multiplied again here");
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

test("loadSource takes an articulation and animation inline for STEP sources", async () => {
  const animation = { clips: [{ id: "swing", label: "Swing", duration: 4, loop: true, tracks: [] }] };
  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    cadPath: "part.step",
    articulation: HINGE_ARTICULATION,
    controls: { swing: 90 },
    sourceAnimation: animation
  });

  assert.equal(source.kind, "step");
  assert.deepEqual(source.pose.values, { swing: 90 });
  assert.equal(source.animation, animation);
});

test("render display source loading keeps kinematics and a supplied selector runtime", async () => {
  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    display: { mode: "render" },
    cadPath: "hinge.step",
    articulation: HINGE_ARTICULATION,
    controls: { swing: 45 },
    selectorRuntime: { stale: true }
  });
  assert.equal(source.kind, "step");
  assert.deepEqual(source.selectorRuntime, { stale: true });
  assert.deepEqual(source.pose.values, { swing: 45 });
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
  // A STEP is drawn from its package: a URL alone names nothing to draw.
  await assert.rejects(() => loadSource("/models/part.step"), /requires a STEP document's package/);
  assert.equal(fetches, 0);
});


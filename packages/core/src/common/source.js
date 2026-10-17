import { createHttpCadResourceProvider } from "../client/resources.js";
import {
  buildComposedPackageMeshData
} from "../lib/assembly/meshData.js";
import { buildComponentMeshData } from "../lib/parts/partMeshData.js";
import { validateSnapshotRenderJob } from "./snapshotJobValidation.js";
import {
  TESS_PROBE_MAX_KEYS,
  decodeComponentTessellation,
  tessBatchMaxBytes,
} from "../lib/parts/tessellationCache.js";
import { normalizeControlValues } from "./articulation.js";

// A render source is a STEP document: its model is composed here and built by `buildModel`
// (`cadScene.js`), in the viewer's STEP renderer and in a snapshot alike. Every other file
// family is drawn by its own scene builder, which the viewer's renderer for it and the
// snapshot CLI both call (`headlessScene.js`); none of them is flattened into mesh data here.
export const SOURCE_KIND = Object.freeze({
  STEP: "step",
  STP: "stp",
  UNKNOWN: "unknown"
});

// The families that have a scene builder of their own, refused here by name.
const FAMILY_SCENE_KINDS = Object.freeze(["glb", "gltf", "stl", "3mf", "urdf", "srdf", "sdf"]);

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeKind(value = "") {
  const kind = String(value || "").trim().toLowerCase();
  return kind === "step" || kind === "stp" ? kind : SOURCE_KIND.UNKNOWN;
}

function sourceKindFromUrl(url = "") {
  const pathname = String(url || "").split(/[?#]/, 1)[0].toLowerCase();
  if (pathname.endsWith(".step")) {
    return SOURCE_KIND.STEP;
  }
  if (pathname.endsWith(".stp")) {
    return SOURCE_KIND.STP;
  }
  return FAMILY_SCENE_KINDS.find((kind) => pathname.endsWith(`.${kind}`)) || SOURCE_KIND.UNKNOWN;
}

function refuseFamilySceneKind(rawKind) {
  const kind = String(rawKind || "").trim().toLowerCase();
  if (FAMILY_SCENE_KINDS.includes(kind)) {
    throw new Error(
      `loadSource composes a STEP document; a ${kind.toUpperCase()} is drawn by its own scene builder, `
      + "the one its viewer renderer uses (see common/headlessScene.js)"
    );
  }
}

export function sourceIsStep(sourceOrKind) {
  const kind = typeof sourceOrKind === "string" ? sourceOrKind : sourceOrKind?.kind;
  const normalized = normalizeKind(kind);
  return normalized === SOURCE_KIND.STEP || normalized === SOURCE_KIND.STP;
}

function assertStepOnlyOption(kind, value, label) {
  // An empty value means the option was not provided (a URL option defaults to
  // the empty string), so there is nothing step-only to reject — required for direct
  // non-STEP mesh sources, which reach loadSource with no step parameters at all.
  if (value === undefined || value === null || value === "") {
    return;
  }
  if (!sourceIsStep(kind)) {
    throw new Error(`${label} is supported only for STEP/STP sources`);
  }
}

// A component GLB can vanish for a moment while a concurrent `scripts/gen`
// swaps the package directory: the descriptor we already read names a
// content-addressed cid, the rebuild rewrites that tree, and a fetch landing in
// the gap 404s. The asset is normally back within a few hundred ms, so a short
// bounded retry turns a hard failure into a pause.
//
// This does NOT cover the case where a rebuild genuinely changed the geometry —
// then the cid is gone for good and the descriptor in hand is stale. Fixing
// that properly means re-reading the descriptor and recomposing, which needs a
// descriptor URL threaded into this function; there isn't one today. So the
// final error says which of the two happened instead of just reporting a 404.
const COMPONENT_FETCH_ATTEMPTS = 3;
const COMPONENT_FETCH_BACKOFF_MS = [120, 320];

async function fetchComponentMeshBuffer(url, cid, options) {
  let lastStatus = 0;
  for (let attempt = 0; attempt < COMPONENT_FETCH_ATTEMPTS; attempt += 1) {
    try { return await options.resources.readBytes(url, { signal: options.signal }); }
    catch (error) {
      if (!error.status) throw error;
      lastStatus = error.status;
      if (error.status !== 404 || attempt === COMPONENT_FETCH_ATTEMPTS - 1) break;
      await new Promise(resolve => setTimeout(resolve, COMPONENT_FETCH_BACKOFF_MS[attempt] || 320));
      options.signal?.throwIfAborted();
    }
  }
  const hint = lastStatus === 404
    ? " — the component is missing after retries, which means either a rebuild "
      + "is still in flight or this descriptor is stale relative to the package "
      + "on disk (regenerate the model)"
    : "";
  throw new Error(`Failed to load component mesh ${cid}: HTTP ${lastStatus}${hint}`);
}

async function loadPackageMeshData(packageInfo, diagnostics = null, tessellationCache = null, options = {}) {
  const measure = (name, started) => {
    if (diagnostics) diagnostics[name] = (diagnostics[name] || 0) + performance.now() - started;
  };
  // The tree as cadgen serves it for display: an assigned occurrence already carries its
  // finish, base colour and opacity, so the page draws what it is given.
  const descriptor = isObject(packageInfo.descriptor) ? packageInfo.descriptor : null;
  if (!descriptor) {
    throw new Error("Assembly render job is missing its tree (assembly.json)");
  }
  // A static package (the docs hero) ships one mesh per component beside its
  // tree; a served one reads them from the host's mesh store.
  const meshUrls = isObject(packageInfo.meshUrls) ? packageInfo.meshUrls : {};
  const components = isObject(descriptor.components) ? descriptor.components : {};
  const componentMeshDataByCid = {};
  // A component cadgen could not mesh carries why (`failure`, cadgen.store.view): it settles
  // on its own and is left out, as the viewer's loader leaves out a component whose part
  // failed (`componentFailed`), and every other component is drawn. When every component
  // failed there is nothing to draw, and the first failure is the load's.
  const failures = Object.keys(components)
    .filter((cid) => String(components[cid]?.failure || "").trim())
    .map((cid) => ({ cid, error: new Error(
      `Assembly package component ${cid} could not be meshed (${String(components[cid].failure).trim()})`) }));
  const failed = new Set(failures.map(({ cid }) => cid));
  const cids = Object.keys(components).filter((cid) => !failed.has(cid));
  if (failures.length && !cids.length) {
    throw failures[0].error;
  }
  // Each component names its part: the key its display mesh is read by.
  const partOf = (cid) => String(components[cid]?.part || "");
  if (diagnostics) diagnostics.componentCount = cids.length;
  const probeStarted = performance.now();
  const probes = await tessellationCache?.probeCachedTessellationEntries(cids.map(partOf)) || new Map();
  measure("probeMs", probeStarted);
  const misses = [];

  // Probe metadata is tiny. Full bodies are fetched only in admitted TESB
  // groups whose observed framing stays under the batch bound: the server's
  // 32 MiB, or the lower ceiling the cache's transport declares
  // (`batchMaxBytes`). Each group is decoded, copied into render-owned arrays
  // and dropped before the next group, so a warm assembly never retains all
  // raw cache bodies beside the final mesh.
  const batchMaxBytes = tessBatchMaxBytes(tessellationCache?.batchMaxBytes);
  const groups = [];
  let group = [];
  let framedBytes = 12;
  const flush = () => {
    if (group.length) groups.push(group);
    group = [];
    framedBytes = 12;
  };
  for (const cid of cids) {
    const probe = probes.get(partOf(cid));
    if (!probe) {
      misses.push(cid);
      continue;
    }
    const entryBytes = 4 + ((probe.glb.byteLength + 3) & ~3);
    if (group.length >= TESS_PROBE_MAX_KEYS
      || (group.length && framedBytes + entryBytes > batchMaxBytes)) flush();
    group.push({ cid, part: probe.part, probe });
    framedBytes += entryBytes;
    if (framedBytes >= batchMaxBytes || entryBytes + 12 > batchMaxBytes) flush();
  }
  flush();

  if (diagnostics) diagnostics.cacheBatchCount = groups.length;
  let cacheHits = 0;
  // Components the store named a mesh for whose body could not be read, even alone.
  const unreadable = new Set();
  const decodeEntry = (entry, bytes) => decodeComponentTessellation(bytes, { part: entry.part });
  for (const entries of groups) {
    const readStarted = performance.now();
    let bodies;
    if (entries.length === 1 && entries[0].probe.glb.byteLength + 16 > batchMaxBytes) {
      const entry = entries[0];
      bodies = [await tessellationCache?.getCachedEntryBytes(entry.part, { probe: entry.probe })];
    } else {
      const maxBytes = 12 + entries.reduce(
        (sum, entry) => sum + 4 + ((entry.probe.glb.byteLength + 3) & ~3),
        0,
      );
      bodies = await tessellationCache?.getCachedEntryBytesMany(entries.map((entry) => entry.probe), { maxBytes });
    }
    measure("cacheReadMs", readStarted);
    for (let index = 0; index < entries.length; index += 1) {
      const decodeStarted = performance.now();
      const entry = entries[index];
      let decoded = decodeEntry(entry, bodies?.[index]);
      measure("cacheDecodeMs", decodeStarted);
      if (!decoded) {
        // The store named this mesh: a body that did not come back is read again, alone, before
        // the component is a miss (a batch can fail as a whole where its entries would not).
        const rereadStarted = performance.now();
        const body = await tessellationCache?.getCachedEntryBytes(entry.part, { probe: entry.probe });
        measure("cacheReadMs", rereadStarted);
        decoded = decodeEntry(entry, body);
      }
      if (!decoded) {
        unreadable.add(entry.cid);
        misses.push(entry.cid);
        continue;
      }
      cacheHits += 1;
      const meshStarted = performance.now();
      componentMeshDataByCid[entry.cid] = buildComponentMeshData(decoded.component);
      measure("meshBuildMs", meshStarted);
    }
  }
  if (diagnostics) {
    diagnostics.cacheHitCount = cacheHits;
    diagnostics.cacheMissCount = misses.length;
  }
  // What the store could not answer: a static package's own mesh file, read
  // through a small pool (6 matches the browser's per-host connection budget),
  // else a component nothing has meshed, or whose stored mesh could not be read.
  const loadComponent = async (cid) => {
    const url = String(meshUrls[cid] || "").trim();
    if (!url) {
      throw new Error(unreadable.has(cid)
        ? `Assembly package component ${cid}: the store holds its mesh, but it could not be read`
        : `Assembly package component ${cid} has no mesh; cadgen meshes every component before a page draws it`);
    }
    const readStarted = performance.now();
    const bytes = new Uint8Array(await fetchComponentMeshBuffer(url, cid, options));
    measure("meshReadMs", readStarted);
    const decoded = decodeComponentTessellation(bytes, { part: partOf(cid) });
    if (!decoded) {
      throw new Error(`Assembly package component ${cid}: ${url} is not its part's mesh`);
    }
    const meshStarted = performance.now();
    componentMeshDataByCid[cid] = buildComponentMeshData(decoded.component);
    measure("meshBuildMs", meshStarted);
  };
  const POOL = 6;
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(POOL, misses.length) }, async () => {
      while (next < misses.length) {
        const cid = misses[next];
        next += 1;
        await loadComponent(cid);
      }
    }),
  );
  const composeStarted = performance.now();
  const meshData = buildComposedPackageMeshData(descriptor, componentMeshDataByCid);
  measure("composeMs", composeStarted);
  return meshData;
}

// The POSE half of a STEP source: cadgen's articulation of its kinematics at a control
// vector cadgen validated (a snapshot job's `resolved.controls`; the opening when none is
// given). This is the `stepParameters` object `buildModel` plays.
function stepPose(kind, articulation, controls) {
  assertStepOnlyOption(kind, articulation, "articulation");
  assertStepOnlyOption(kind, controls, "controls");
  if (!articulation) {
    if (controls !== undefined && controls !== null) {
      throw new Error("the model declares no kinematics, so the control values have nothing to drive");
    }
    return null;
  }
  return { articulation, values: normalizeControlValues(articulation, controls) };
}

// A render package served off a plain static host (a docs site, a CDN): no
// backend resolves meshes there, but the descriptor names every component's
// display mesh (`glb`: its part's stored GLB body, written by cadgen) relative to
// the package directory. This maps that layout to a loadSource package input.
// The caller fetches `${baseUrl}/assembly.json` itself (it may want to cache or
// inline it) and spreads extra fields (articulation, controls, sourceAnimation,
// cadPath) into the returned object.
export function packageSourceFromBaseUrl(baseUrl, descriptor) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  if (!base) {
    throw new Error("packageSourceFromBaseUrl requires the package directory URL");
  }
  const components = isObject(descriptor?.components) ? descriptor.components : null;
  if (!components) {
    throw new Error(`Tree at ${base}/assembly.json has no components`);
  }
  const meshUrls = {};
  for (const [cid, entry] of Object.entries(components)) {
    const glb = String(entry?.glb || "").trim();
    if (!glb) {
      throw new Error(`Render package component ${cid} declares no glb path`);
    }
    meshUrls[cid] = `${base}/${glb}`;
  }
  return { kind: "step", package: { descriptor, meshUrls } };
}

export async function loadSource(input, options = {}) {
  // Standalone static/snapshot composition; viewer callers supply their scoped provider.
  const resources = options.resources || createHttpCadResourceProvider({ cache: "no-store" });
  options = { ...options, resources };
  const inputObject = isObject(input) ? input : {};
  validateSnapshotRenderJob(inputObject);
  const resolved = isObject(inputObject.resolved) ? inputObject.resolved : {};
  const explicitMeshData = inputObject.meshData || options.meshData || (
    inputObject.vertices && inputObject.indices ? inputObject : null
  );
  const rawKind = inputObject.kind || resolved.kind || options.kind || (
    typeof input === "string" ? sourceKindFromUrl(input) : ""
  );
  refuseFamilySceneKind(rawKind);
  const kind = normalizeKind(rawKind);
  // What the document's sidecar means, resolved by cadgen: the articulation and the
  // control vector to pose it at, and the baked animation (`resolved.animation` in a job,
  // whose own top-level `animation` is the frame REQUEST; `sourceAnimation` for a direct
  // caller). The page reads no sidecar.
  const articulation = inputObject.articulation || resolved.articulation || options.articulation || null;
  const controls = inputObject.controls ?? resolved.controls ?? options.controls;
  const animation = inputObject.sourceAnimation || resolved.animation || options.sourceAnimation || null;
  const cadPath = String(inputObject.cadPath || resolved.inputPath || options.cadPath || "").trim();
  assertStepOnlyOption(kind, animation, "sourceAnimation");
  const pose = stepPose(kind, articulation, controls);

  // A STEP document is drawn from its package: each component's stored mesh, composed in world
  // space from the descriptor (transforms baked per occurrence). A caller that already holds
  // the mesh data passes it instead. No selector runtime is composed here: a caller that has
  // one passes it.
  const packageInfo = isObject(inputObject.package) ? inputObject.package : (
    isObject(resolved.package) ? resolved.package : null
  );
  const selectorRuntime = inputObject.selectorRuntime || options.selectorRuntime || null;
  if (!explicitMeshData && packageInfo) {
    const diagnostics = options.stageTimings ? {} : null;
    const meshData = await loadPackageMeshData(packageInfo, diagnostics, options.tessellationCache, options);
    if (diagnostics) options.stageTimings.sourceLoad = diagnostics;
    // The articulation carries the composed occurrence ids each joint moves, so a package
    // poses with no selector runtime at all.
    return { kind: SOURCE_KIND.STEP, meshData, selectorRuntime, pose, animation, resolved, cadPath };
  }
  if (!explicitMeshData) {
    throw new Error("loadSource requires a STEP document's package (package or resolved.package) or its meshData");
  }
  return { kind, meshData: explicitMeshData, selectorRuntime, pose, animation, resolved, cadPath };
}

// Exported for tests only: the component-fetch retry is the recovery path for a
// package directory being swapped mid-read, and it is not otherwise reachable
// without standing up a real package + server.
export const __testing = {
  fetchComponentMeshBuffer,
  COMPONENT_FETCH_ATTEMPTS
};

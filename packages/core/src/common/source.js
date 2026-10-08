import { createHttpCadResourceProvider } from "../client/resources.js";
import {
  buildComposedPackageMeshData
} from "../lib/assembly/meshData.js";
import { buildMeshDataFromSurf } from "../lib/surf/surfMeshData.js";
import { validateSnapshotRenderJob } from "./snapshotJobValidation.js";
import {
  TESS_PROBE_MAX_KEYS,
  decodeComponentTessellation,
  surfIndexFromCacheEntry,
  tessBatchMaxBytes,
} from "../lib/surf/tessellationCache.js";
import {
  loadRenderDisplayEdgeBundle,
  loadRenderGlb,
  loadRenderSelectorBundle
} from "../lib/stepRenderAssetClient.js";
import {
  buildDisplayEdgeRuntime,
  buildSelectorRuntime
} from "../lib/selectors/runtime.js";
import {
  isRenderAssetSourceScopeError,
  renderAssetSourceScope,
  renderAssetSourceScopeForJob,
  setRenderAssetSourceScope
} from "../lib/renderAssetSourceScope.js";
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

async function loadStepMeshFromGlb(glbUrl, options) {
  // A plain (non-package) GLB URL is a single mesh blob — assemblies are component-GLB
  // packages loaded via loadPackageMeshData, not self-contained monolith GLBs.
  return loadRenderGlb(glbUrl, options);
}

async function loadSelectorRuntime(glbUrl, { cadPath = "", resources, signal } = {}) {
  if (!glbUrl) {
    return null;
  }
  try {
    const selectorBundle = await loadRenderSelectorBundle(glbUrl, { resources, signal });
    return buildSelectorRuntime(selectorBundle, {
      copyCadPath: cadPath
    });
  } catch (error) {
    // Missing or unreadable selector topology is a normal condition and degrades to null. A
    // cross-source cache collision is not: swallowing it would render a plausible wrong image at
    // exit 0, which is the failure this scope check exists to make loud.
    if (isRenderAssetSourceScopeError(error)) {
      throw error;
    }
    return null;
  }
}

async function loadDisplayEdgeRuntime(glbUrl, options) {
  if (!glbUrl) {
    return null;
  }
  try {
    return buildDisplayEdgeRuntime(await loadRenderDisplayEdgeBundle(glbUrl, options));
  } catch (error) {
    if (isRenderAssetSourceScopeError(error)) {
      throw error;
    }
    return null;
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

// The tolerances a resolved STEP job's components are drawn at: cadgen decides them
// (cadgen.tessellation_policy.snapshot_tessellation) and names both in the job.
// A static package (the docs hero) ships one mesh per component beside its tree and
// names none: each file is drawn at the tessellation cadgen exported it at.
function resolvedTessellation(resolved) {
  const tessellation = isObject(resolved?.tessellation) ? resolved.tessellation : null;
  if (!tessellation) return null;
  const { chordTolerance, angleTolerance } = tessellation;
  if (![chordTolerance, angleTolerance].every((value) => typeof value === "number" && value > 0 && Number.isFinite(value))) {
    throw new Error(`resolved.tessellation must name a positive chordTolerance and angleTolerance; got ${JSON.stringify(tessellation)}`);
  }
  return { chordTolerance, angleTolerance };
}

async function loadPackageMeshData(packageInfo, tessellation = null, diagnostics = null, tessellationCache = null, options = {}) {
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
  const cids = Object.keys(components);
  const inputOf = (cid) => String(components[cid]?.surfaceInput || "");
  if (diagnostics) diagnostics.componentCount = cids.length;
  const probeStarted = performance.now();
  if (tessellationCache && !tessellation) {
    throw new Error("a package drawn from cadgen's mesh store names the tessellation to draw (resolved.tessellation)");
  }
  const probes = await tessellationCache?.probeCachedTessellationEntries(cids.map(inputOf), tessellation) || new Map();
  measure("probeMs", probeStarted);
  const usable = (cid) => {
    const probe = probes.get(inputOf(cid));
    const surfaceObject = String(components[cid]?.surfaceObject || "");
    return probe && (!surfaceObject || probe.surfaceObject === surfaceObject) ? probe : null;
  };
  // cadgen produces every mesh. A host that meshes on request (the snapshot
  // host) is asked once for every mesh the probe did not find.
  const unprobed = [...new Set(cids.filter((cid) => !usable(cid)).map(inputOf))];
  if (unprobed.length && tessellationCache?.produceTessellationEntries) {
    const produceStarted = performance.now();
    const produced = await tessellationCache.produceTessellationEntries(unprobed, tessellation);
    for (const [surfaceInput, row] of produced) probes.set(surfaceInput, row);
    measure("produceMs", produceStarted);
    if (diagnostics) diagnostics.producedCount = produced.size;
  }
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
    const probe = usable(cid);
    if (!probe) {
      misses.push(cid);
      continue;
    }
    const entryBytes = 4 + ((probe.byteLength + 3) & ~3);
    if (group.length >= TESS_PROBE_MAX_KEYS
      || (group.length && framedBytes + entryBytes > batchMaxBytes)) flush();
    group.push({ cid, surfaceInput: inputOf(cid), probe });
    framedBytes += entryBytes;
    if (framedBytes >= batchMaxBytes || entryBytes + 12 > batchMaxBytes) flush();
  }
  flush();

  if (diagnostics) diagnostics.cacheBatchCount = groups.length;
  let cacheHits = 0;
  // Components the store named a mesh for whose body could not be read, even alone.
  const unreadable = new Set();
  const decodeEntry = (entry, bytes) => decodeComponentTessellation(bytes, {
    surfaceInput: entry.surfaceInput,
    surfaceObject: entry.probe.surfaceObject,
    tessellationInput: entry.probe.tessellationInput,
    tessellation,
  });
  for (const entries of groups) {
    const readStarted = performance.now();
    let bodies;
    if (entries.length === 1 && entries[0].probe.byteLength + 16 > batchMaxBytes) {
      const entry = entries[0];
      bodies = [await tessellationCache?.getCachedEntryBytes(entry.surfaceInput, tessellation, { probe: entry.probe })];
    } else {
      const maxBytes = 12 + entries.reduce(
        (sum, entry) => sum + 4 + ((entry.probe.byteLength + 3) & ~3),
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
        const body = await tessellationCache?.getCachedEntryBytes(entry.surfaceInput, tessellation, { probe: entry.probe });
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
      componentMeshDataByCid[entry.cid] = buildMeshDataFromSurf(surfIndexFromCacheEntry(decoded), decoded.component);
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
        ? `Assembly package component ${cid}: the store holds its mesh at this tessellation, but it could not be read`
        : `Assembly package component ${cid} has no mesh at this tessellation; cadgen meshes every component before a page draws it`);
    }
    const readStarted = performance.now();
    const bytes = new Uint8Array(await fetchComponentMeshBuffer(url, cid, options));
    measure("meshReadMs", readStarted);
    const surfaceObject = String(components[cid]?.surfaceObject || "");
    const decoded = decodeComponentTessellation(bytes, {
      surfaceInput: inputOf(cid), ...(surfaceObject ? { surfaceObject } : {}), ...(tessellation ? { tessellation } : {}),
    });
    if (!decoded) {
      throw new Error(`Assembly package component ${cid}: ${url} is not its mesh at this tessellation`);
    }
    const meshStarted = performance.now();
    componentMeshDataByCid[cid] = buildMeshDataFromSurf(surfIndexFromCacheEntry(decoded), decoded.component);
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

async function loadMeshDataFromUrl(url, kind, options) {
  if (!sourceIsStep(kind)) throw new Error(`Unsupported render source kind: ${kind || SOURCE_KIND.UNKNOWN}; a render source is a STEP/STP document`);
  return loadStepMeshFromGlb(url, options);
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
// backend resolves component URLs or meshes there, but the descriptor already
// names every component's surf path relative to the package directory, and
// each component's mesh ships beside it as `<cid>.glb` (its stored GLB body at
// the tessellation the page draws, written by cadgen). This maps that layout to a
// loadSource package input. The caller fetches `${baseUrl}/assembly.json`
// itself (it may want to cache or inline it) and spreads extra fields
// (articulation, controls, sourceAnimation, cadPath) into the returned object.
export function packageSourceFromBaseUrl(baseUrl, descriptor) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  if (!base) {
    throw new Error("packageSourceFromBaseUrl requires the package directory URL");
  }
  const components = isObject(descriptor?.components) ? descriptor.components : null;
  if (!components) {
    throw new Error(`Tree at ${base}/assembly.json has no components`);
  }
  const componentUrls = {};
  const meshUrls = {};
  for (const [cid, entry] of Object.entries(components)) {
    const surf = String(entry?.surf || "").trim();
    if (!surf) {
      throw new Error(`Render package component ${cid} declares no surf path`);
    }
    componentUrls[cid] = `${base}/${surf}`;
    meshUrls[cid] = `${base}/${surf.replace(/\.surf$/, "")}.glb`;
  }
  return { kind: "step", package: { descriptor, componentUrls, meshUrls } };
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
  const tessellation = resolvedTessellation(resolved);
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

  let meshData = explicitMeshData;
  // Component-GLB package: the canonical assembly artifact is a directory, so there is
  // no single GLB to load. Fetch each unique component GLB and compose them in world
  // space from the descriptor (transforms baked per occurrence). Picking is not wired
  // for packages yet, so the selector runtime is left empty (renders, no selection).
  const packageInfo = isObject(inputObject.package) ? inputObject.package : (
    isObject(resolved.package) ? resolved.package : null
  );
  if (!meshData && packageInfo) {
    const diagnostics = options.stageTimings ? {} : null;
    meshData = await loadPackageMeshData(packageInfo, tessellation, diagnostics, options.tessellationCache, options);
    if (diagnostics) options.stageTimings.sourceLoad = diagnostics;
    const packageSelectorRuntime = inputObject.selectorRuntime || options.selectorRuntime || null;
    return {
      kind: "step",
      meshData,
      selectorRuntime: packageSelectorRuntime,
      displayEdgeRuntime: inputObject.displayEdgeRuntime || options.displayEdgeRuntime || null,
      // The articulation carries the composed occurrence ids each joint moves, so a package
      // poses with no selector runtime at all.
      pose,
      animation,
      resolved,
      url: "",
      glbUrl: "",
      cadPath
    };
  }
  const glbUrl = String(inputObject.glbUrl || resolved.glbUrl || options.glbUrl || "").trim();
  const url = String(typeof input === "string" ? input : inputObject.url || resolved.url || glbUrl || "").trim();

  // Render asset caches live for the whole page, so every entry a resolved job populates must be
  // tagged with the source it belongs to. This is the only place a resolved job meets those caches,
  // so it is where the scope is declared; the scope is restored afterwards so one job can never
  // leave its identity attached to another caller's loads. Callers with no resolved job keep the
  // unscoped default and are unaffected.
  const previousSourceScope = renderAssetSourceScope();
  if (glbUrl || url) {
    setRenderAssetSourceScope(renderAssetSourceScopeForJob(inputObject));
  }
  try {
    if (!meshData) {
      if (!url) {
        throw new Error("loadSource requires meshData, a source URL, or resolved.glbUrl");
      }
      meshData = await loadMeshDataFromUrl(sourceIsStep(kind) ? glbUrl || url : url, kind, options);
    }

    // Selector/display-edge runtimes ride in STEP topology GLB extras. Direct mesh
    // kinds have none, and loading them anyway re-downloads the mesh binary just to
    // fail the GLB container parse — gate by kind so "no selectors for meshes" is
    // intent, not a swallowed error (matches the CLI's mesh-input validation).
    // A still whose display mode is Render does not draw CAD edges and has no
    // pointer interaction, so it must not pull selector topology solely because
    // its source is STEP. Explicit runtimes remain an opt-in demand (the shared
    // interactive loader can carry them while switching display modes).
    const renderOnlyLoad = String(inputObject.display?.mode || "").trim().toLowerCase() === "render";
    const stepSidecarsEnabled = sourceIsStep(kind) && !renderOnlyLoad;
    const selectorRuntime = inputObject.selectorRuntime || options.selectorRuntime || (
      stepSidecarsEnabled ? await loadSelectorRuntime(glbUrl || url, { cadPath, resources, signal: options.signal }) : null
    );
    const displayEdgeRuntime = inputObject.displayEdgeRuntime || options.displayEdgeRuntime || (
      stepSidecarsEnabled ? await loadDisplayEdgeRuntime(glbUrl || url, options) : null
    );
    return {
      kind,
      meshData,
      selectorRuntime,
      displayEdgeRuntime,
      pose,
      animation,
      resolved,
      url,
      glbUrl,
      cadPath
    };
  } finally {
    setRenderAssetSourceScope(previousSourceScope);
  }
}

// Exported for tests only: the component-fetch retry is the recovery path for a
// package directory being swapped mid-read, and it is not otherwise reachable
// without standing up a real package + server.
export const __testing = {
  fetchComponentMeshBuffer,
  COMPONENT_FETCH_ATTEMPTS
};

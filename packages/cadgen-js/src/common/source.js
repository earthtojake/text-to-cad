import {
  buildComposedPackageMeshData
} from "../lib/assembly/meshData.js";
import { buildMeshDataFromGlbBuffer } from "../lib/render/glbMeshData.js";
import { buildMeshDataFromSurf } from "../lib/surf/surfMeshData.js";
import { parseSurf } from "../lib/surf/container.js";
import { tessellateComponent } from "../lib/surf/tessellate.js";
import { lodTessellationForLevel } from "../lib/surf/lodPolicy.js";
import { validateSnapshotRenderJob } from "./snapshotJobValidation.js";
import {
  SCENE_QUALITY,
  resolveSceneQuality,
  resolveRenderQuality
} from "./sceneSettings.js";
import {
  TESS_BATCH_MAX_BYTES,
  TESS_PROBE_MAX_KEYS,
  decodeComponentTessellation,
  getCachedEntryBytes,
  getCachedEntryBytesMany,
  probeCachedTessellationEntries,
  surfIndexFromCacheEntry,
  writeBackComponentEntry,
} from "../lib/surf/tessellationCache.js";
import { buildMeshDataFromStlBuffer } from "../lib/render/stlMeshData.js";
import { buildMeshDataFrom3MfBuffer } from "../lib/render/threeMfMeshData.js";
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
import {
  kinematicsModuleDefinitionFromSidecar,
  loadKinematicsModuleDefinition
} from "./kinematicsModule.js";
import {
  applySourceAppearance,
  loadSourceSidecar,
  validateSourceSidecar
} from "./sourceSidecar.js";
import {
  isRobotSourceKind,
  loadRobotMeshData,
  robotSourceKindFromUrl
} from "../lib/urdf/loadRobot.js";
import {
  hasStepParameterRenderValues,
  normalizeStepParameterRenderValues,
  stepParameterRenderState,
  stepParameterRenderValues
} from "./stepParameters.js";

export const SOURCE_KIND = Object.freeze({
  STEP: "step",
  STP: "stp",
  GLB: "glb",
  STL: "stl",
  THREE_MF: "3mf",
  UNKNOWN: "unknown"
});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeKind(value = "") {
  const kind = String(value || "").trim().toLowerCase();
  if (kind === "step" || kind === "stp" || kind === "glb" || kind === "stl" || kind === "3mf") {
    return kind;
  }
  if (isRobotSourceKind(kind)) {
    return kind;
  }
  return SOURCE_KIND.UNKNOWN;
}

function sourceKindFromUrl(url = "") {
  const pathname = String(url || "").split(/[?#]/, 1)[0].toLowerCase();
  if (pathname.endsWith(".step")) {
    return SOURCE_KIND.STEP;
  }
  if (pathname.endsWith(".stp")) {
    return SOURCE_KIND.STP;
  }
  if (pathname.endsWith(".glb") || pathname.endsWith(".gltf")) {
    return SOURCE_KIND.GLB;
  }
  if (pathname.endsWith(".stl")) {
    return SOURCE_KIND.STL;
  }
  if (pathname.endsWith(".3mf")) {
    return SOURCE_KIND.THREE_MF;
  }
  return SOURCE_KIND.UNKNOWN;
}

export function sourceIsStep(sourceOrKind) {
  const kind = typeof sourceOrKind === "string" ? sourceOrKind : sourceOrKind?.kind;
  const normalized = normalizeKind(kind);
  return normalized === SOURCE_KIND.STEP || normalized === SOURCE_KIND.STP;
}

function assertStepOnlyOption(kind, value, label) {
  // An empty value means the option was not provided (stepParameterUrl defaults to
  // the empty string), so there is nothing step-only to reject — required for direct
  // non-STEP mesh sources, which reach loadSource with no step parameters at all.
  if (value === undefined || value === null || value === "") {
    return;
  }
  if (!sourceIsStep(kind)) {
    throw new Error(`${label} is supported only for STEP/STP sources`);
  }
}

async function loadStepMeshFromGlb(glbUrl) {
  // A plain (non-package) GLB URL is a single mesh blob — assemblies are component-GLB
  // packages loaded via loadPackageMeshData, not self-contained monolith GLBs.
  return loadRenderGlb(glbUrl);
}

async function loadSelectorRuntime(glbUrl, { cadPath = "" } = {}) {
  if (!glbUrl) {
    return null;
  }
  try {
    const selectorBundle = await loadRenderSelectorBundle(glbUrl);
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

async function loadDisplayEdgeRuntime(glbUrl) {
  if (!glbUrl) {
    return null;
  }
  try {
    return buildDisplayEdgeRuntime(await loadRenderDisplayEdgeBundle(glbUrl));
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

async function fetchComponentGlbBuffer(url, cid) {
  let lastStatus = 0;
  for (let attempt = 0; attempt < COMPONENT_FETCH_ATTEMPTS; attempt += 1) {
    const response = await fetch(url, { cache: "no-store" });
    if (response.ok) {
      return response.arrayBuffer();
    }
    lastStatus = response.status;
    // Only a missing asset is worth retrying. A 4xx that is not 404, or any
    // 5xx, is a real error and retrying just delays the report.
    if (response.status !== 404 || attempt === COMPONENT_FETCH_ATTEMPTS - 1) {
      break;
    }
    const delay = COMPONENT_FETCH_BACKOFF_MS[attempt] || 320;
    await new Promise((resolve) => { setTimeout(resolve, delay); });
  }
  const hint = lastStatus === 404
    ? " — the component is missing after retries, which means either a rebuild "
      + "is still in flight or this descriptor is stale relative to the package "
      + "on disk (regenerate the model)"
    : "";
  throw new Error(`Failed to load component GLB ${cid}: HTTP ${lastStatus}${hint}`);
}

// Floors for an explicit macro tessellation request. Chord tolerance is
// RELATIVE to the component's bounding diagonal and angle tolerance is
// radians, so these sit ~100x finer than the tessellator's own defaults
// (1.5e-3 / 0.35 rad) — beyond any display need at any output size. Below
// them a job is not a render, it is a memory bomb: the page tessellates until
// the renderer dies, which reaches the caller as an opaque lost driver
// connection instead of a rejected request. Mirrored as
// MIN_RENDER_TESSELLATION in cadgen/snapshot_core.py, which refuses the same
// job before a browser is even launched (parity-tested from the Python side).
export const RENDER_TESSELLATION_FLOORS = Object.freeze({
  chordTolerance: 1e-5,
  angleTolerance: 5e-3
});

export function normalizeRenderTessellation(value) {
  if (value === undefined || value === null) return {};
  if (!isObject(value) || Array.isArray(value)) {
    throw new Error("quality.tessellation must be an object");
  }
  const result = {};
  for (const [key, raw] of Object.entries(value)) {
    if (!Object.hasOwn(RENDER_TESSELLATION_FLOORS, key)) {
      throw new Error(`Unknown quality.tessellation field: ${key}`);
    }
    if (typeof raw !== "number" || !Number.isFinite(raw) || raw <= 0) {
      throw new Error(`quality.tessellation.${key} must be a positive finite number`);
    }
    if (raw < RENDER_TESSELLATION_FLOORS[key]) {
      throw new Error(
        `quality.tessellation.${key} must be at least ${RENDER_TESSELLATION_FLOORS[key]}; ` +
        "finer sampling exhausts the renderer instead of improving the image"
      );
    }
    result[key] = raw;
  }
  return result;
}

export function tessellationForSnapshotQuality(input = {}) {
  validateSnapshotRenderJob(input);
  const explicit = input.render != null ? null : input.quality?.tessellation;
  if (explicit != null) {
    return normalizeRenderTessellation(explicit);
  }
  const quality = input.render != null
    ? resolveRenderQuality(input.render.quality)
    : resolveSceneQuality(SCENE_QUALITY.INTERACTIVE);
  // Final uses the existing finest bounded rung. Preview and CAD inspection
  // retain the canonical L1 cache request.
  return quality.snapshotLodLevel > 1
    ? lodTessellationForLevel(quality.snapshotLodLevel)
    : {};
}

async function loadPackageMeshData(packageInfo, tessellation = {}, appearance = null, diagnostics = null) {
  const measure = (name, started) => {
    if (diagnostics) diagnostics[name] = (diagnostics[name] || 0) + performance.now() - started;
  };
  const storedDescriptor = isObject(packageInfo.descriptor) ? packageInfo.descriptor : null;
  if (!storedDescriptor) {
    throw new Error("Assembly render job is missing its tree (assembly.json)");
  }
  const descriptor = applySourceAppearance(storedDescriptor, appearance);
  const componentUrls = isObject(packageInfo.componentUrls) ? packageInfo.componentUrls : {};
  const components = isObject(descriptor.components) ? descriptor.components : {};
  const componentMeshDataByCid = {};
  const cids = Object.keys(components);
  const inputs = cids.map((cid) => String(components[cid]?.surfaceInput || ""));
  if (diagnostics) diagnostics.componentCount = cids.length;
  const probeStarted = performance.now();
  const probes = await probeCachedTessellationEntries(inputs, tessellation);
  measure("probeMs", probeStarted);
  const misses = [];

  // Probe metadata is tiny. Full bodies are fetched only in admitted TESB
  // groups whose observed framing stays under the host's 32 MiB bound. Each
  // group is decoded, copied into render-owned arrays and dropped before the
  // next group, so a warm assembly never retains all raw cache bodies beside
  // the final mesh.
  const groups = [];
  let group = [];
  let framedBytes = 12;
  const flush = () => {
    if (group.length) groups.push(group);
    group = [];
    framedBytes = 12;
  };
  for (const cid of cids) {
    const component = components[cid];
    const surfaceInput = String(component?.surfaceInput || "");
    const surfaceObject = String(component?.surfaceObject || "");
    const probe = probes.get(surfaceInput);
    if (!probe || (surfaceObject && probe.surfaceObject !== surfaceObject)) {
      misses.push(cid);
      continue;
    }
    const entryBytes = 4 + ((probe.byteLength + 3) & ~3);
    if (group.length >= TESS_PROBE_MAX_KEYS
      || (group.length && framedBytes + entryBytes > TESS_BATCH_MAX_BYTES)) flush();
    group.push({ cid, surfaceInput, surfaceObject, probe });
    framedBytes += entryBytes;
    if (framedBytes >= TESS_BATCH_MAX_BYTES || entryBytes + 12 > TESS_BATCH_MAX_BYTES) flush();
  }
  flush();

  if (diagnostics) diagnostics.cacheBatchCount = groups.length;
  let cacheHits = 0;
  for (const entries of groups) {
    const readStarted = performance.now();
    let bodies;
    if (entries.length === 1 && entries[0].probe.byteLength + 16 > TESS_BATCH_MAX_BYTES) {
      const entry = entries[0];
      bodies = [await getCachedEntryBytes(entry.surfaceInput, tessellation, { probe: entry.probe })];
    } else {
      const maxBytes = 12 + entries.reduce(
        (sum, entry) => sum + 4 + ((entry.probe.byteLength + 3) & ~3),
        0,
      );
      bodies = await getCachedEntryBytesMany(entries.map((entry) => entry.probe), { maxBytes });
    }
    measure("cacheReadMs", readStarted);
    for (let index = 0; index < entries.length; index += 1) {
      const decodeStarted = performance.now();
      const entry = entries[index];
      const decoded = decodeComponentTessellation(bodies?.[index], {
        surfaceInput: entry.surfaceInput,
        surfaceObject: entry.probe.surfaceObject,
        tessellationInput: entry.probe.tessellationInput,
        tessellation,
      });
      const surrogateIndex = decoded ? surfIndexFromCacheEntry(decoded) : null;
      measure("cacheDecodeMs", decodeStarted);
      if (!decoded || !surrogateIndex) {
        misses.push(entry.cid);
        continue;
      }
      cacheHits += 1;
      const meshStarted = performance.now();
      componentMeshDataByCid[entry.cid] = buildMeshDataFromSurf(surrogateIndex, null, {
        component: decoded.component,
      });
      measure("meshBuildMs", meshStarted);
    }
  }
  // Misses load through a small pool: tessellation is CPU-bound and
  // single-threaded either way, but a many-component assembly otherwise pays
  // its per-request latency (surf fetch + write-back) serially — measured as
  // the dominant cost on a 563-component model. The pool overlaps the network
  // waits with the CPU work; 6 matches the browser's per-host connection
  // budget.
  if (diagnostics) {
    diagnostics.cacheHitCount = cacheHits;
    diagnostics.cacheMissCount = misses.length;
  }
  const loadComponent = async (cid) => {
    const descriptorComponent = components[cid];
    const surfaceInput = String(descriptorComponent?.surfaceInput || "");
    const surfaceObject = String(descriptorComponent?.surfaceObject || "");
    const url = String(componentUrls[cid] || "").trim();
    if (!url) {
      throw new Error(`Assembly package component ${cid} has no resolved URL`);
    }
    // Exact-surface artifact (design/surface-rendering.md): the resolved URL
    // points at the component GLB; its .surf sibling shares the stem.
    const surfUrl = url.replace(/\.glb(?=$|[?#])/, ".surf");
    const readStarted = performance.now();
    const { index, floats } = parseSurf(await fetchComponentGlbBuffer(surfUrl, cid));
    measure("surfaceReadMs", readStarted);
    const tessellateStarted = performance.now();
    const component = tessellateComponent(index, floats, tessellation);
    measure("tessellateMs", tessellateStarted);
    const writeStarted = performance.now();
    await writeBackComponentEntry(surfaceInput, surfaceObject, tessellation, component, index);
    measure("cacheWriteMs", writeStarted);
    const meshStarted = performance.now();
    componentMeshDataByCid[cid] = buildMeshDataFromSurf(index, floats, { component });
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

async function loadMeshDataFromUrl(url, kind) {
  if (sourceIsStep(kind)) {
    return loadStepMeshFromGlb(url);
  }
  if (kind === SOURCE_KIND.GLB) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to load GLB source: HTTP ${response.status}`);
    }
    return buildMeshDataFromGlbBuffer(await response.arrayBuffer());
  }
  if (kind === SOURCE_KIND.STL) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to load STL source: HTTP ${response.status}`);
    }
    return buildMeshDataFromStlBuffer(await response.arrayBuffer());
  }
  if (kind === SOURCE_KIND.THREE_MF) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to load 3MF source: HTTP ${response.status}`);
    }
    return buildMeshDataFrom3MfBuffer(await response.arrayBuffer());
  }
  throw new Error(`Unsupported render source kind: ${kind || SOURCE_KIND.UNKNOWN}`);
}

// A pose PRESET name in place of a values object. `--kinematics` takes either
// spelling, and the CLI cannot tell them apart on its own: the declared preset
// names live in the model's kinematics block, which is only loaded here. So the
// name travels as a bare string and is resolved against the definition.
function resolvePoseValues(definition, kinematics) {
  if (typeof kinematics !== "string") {
    return kinematics;
  }
  const name = kinematics.trim();
  const poses = isObject(definition?.manifest?.poses) ? definition.manifest.poses : {};
  if (isObject(poses[name])) {
    return poses[name];
  }
  const declared = Object.keys(poses);
  throw new Error(
    declared.length
      ? `Unknown kinematics pose: ${name}. This model declares: ${declared.join(", ")}`
      : `Unknown kinematics pose: ${name}. This model declares no poses; pass {dof: value} JSON instead`
  );
}

async function loadStepParameters({
  kind,
  kinematics,
  stepParameterUrl,
  documentHash,
  cadPath,
  selectorRuntime,
  sourceSidecar = null
}) {
  assertStepOnlyOption(kind, kinematics, "kinematics");
  assertStepOnlyOption(kind, stepParameterUrl, "stepParameterUrl");
  assertStepOnlyOption(kind, documentHash, "documentHash");
  const explicit = hasStepParameterRenderValues(kinematics);
  if (!stepParameterUrl && !sourceSidecar) {
    if (!explicit) {
      return null;
    }
    throw new Error("kinematics values require resolved.stepParameterUrl");
  }
  // stepParameterUrl is the model SIDECAR url (the .step.json); its
  // kinematics section is the one articulation mechanism.
  const definition = sourceSidecar
    ? kinematicsModuleDefinitionFromSidecar(sourceSidecar, { cadPath, url: stepParameterUrl })
    : await loadKinematicsModuleDefinition(stepParameterUrl, { cadPath, documentHash });
  if (!definition) {
    if (explicit) {
      throw new Error("model declares no kinematics, so the kinematics values have nothing to drive");
    }
    return null;
  }
  const renderParameters = normalizeStepParameterRenderValues(
    definition,
    explicit ? resolvePoseValues(definition, kinematics) : {}
  );
  return {
    definition,
    renderParameters,
    selectorRuntime,
    cadPath: cadPath || definition.cadPath || "",
    sourceUrl: stepParameterUrl
  };
}

export function stepParameterRuntime(stepParameterSource) {
  if (!stepParameterSource) {
    return null;
  }
  const { definition, renderParameters } = stepParameterSource;
  return {
    definition,
    selectorRuntime: stepParameterSource.selectorRuntime || null,
    parameterValues: stepParameterRenderValues(renderParameters),
    animationState: stepParameterRenderState(),
    cadPath: stepParameterSource.cadPath || definition.cadPath || "",
    sourceUrl: stepParameterSource.sourceUrl || definition.url || ""
  };
}

// A render package served off a plain static host (a docs site, a CDN): no
// backend resolves component URLs there, but the descriptor already names
// every component's surf path relative to the package directory. This maps
// that layout to a loadSource package input. The caller fetches
// `${baseUrl}/assembly.json` itself (it may want to cache or inline it) and
// spreads extra fields (stepParameterUrl, cadPath) into the returned object.
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
  for (const [cid, entry] of Object.entries(components)) {
    const surf = String(entry?.surf || "").trim();
    if (!surf) {
      throw new Error(`Render package component ${cid} declares no surf path`);
    }
    componentUrls[cid] = `${base}/${surf}`;
  }
  return { kind: "step", package: { descriptor, componentUrls } };
}

export async function loadSource(input, options = {}) {
  const inputObject = isObject(input) ? input : {};
  validateSnapshotRenderJob(inputObject);
  const photographicRender = inputObject.render != null;
  const resolved = isObject(inputObject.resolved) ? inputObject.resolved : {};
  const explicitMeshData = inputObject.meshData || options.meshData || (
    inputObject.vertices && inputObject.indices ? inputObject : null
  );
  const rawKind = inputObject.kind || resolved.kind || options.kind || (
    typeof input === "string" ? sourceKindFromUrl(input) : ""
  );
  const kind = normalizeKind(rawKind);
  const rawTessellation = photographicRender ? null : inputObject.quality?.tessellation;
  const tessellation = tessellationForSnapshotQuality(inputObject);
  assertStepOnlyOption(kind, rawTessellation, "quality.tessellation");
  const kinematics = inputObject.kinematics ?? options.kinematics;
  const stepParameterUrl = String(
    inputObject.stepParameterUrl || resolved.stepParameterUrl || options.stepParameterUrl || ""
  ).trim();
  const documentHash = String(
    inputObject.documentHash || resolved.documentHash || options.documentHash || ""
  ).trim();
  const inlineSourceSidecar = inputObject.sourceSidecar || resolved.sourceSidecar || options.sourceSidecar || null;

  const cadPath = String(inputObject.cadPath || resolved.inputPath || options.cadPath || "").trim();
  assertStepOnlyOption(kind, kinematics, "kinematics");
  assertStepOnlyOption(kind, stepParameterUrl, "stepParameterUrl");
  assertStepOnlyOption(kind, documentHash, "documentHash");
  assertStepOnlyOption(kind, inlineSourceSidecar, "sourceSidecar");

  const sourceSidecar = inlineSourceSidecar
    ? validateSourceSidecar(inlineSourceSidecar, { url: stepParameterUrl || cadPath, documentHash })
    : (stepParameterUrl ? await loadSourceSidecar(stepParameterUrl, { documentHash }) : null);

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
    meshData = await loadPackageMeshData(packageInfo, tessellation, sourceSidecar?.appearance, diagnostics);
    if (diagnostics) options.stageTimings.sourceLoad = diagnostics;
    const packageSelectorRuntime = photographicRender ? null : inputObject.selectorRuntime || options.selectorRuntime || null;
    return {
      kind: "step",
      meshData,
      selectorRuntime: packageSelectorRuntime,
      displayEdgeRuntime: photographicRender ? null : inputObject.displayEdgeRuntime || options.displayEdgeRuntime || null,
      // Parameter sidecars resolve features against composed occurrence ids, so
      // they stay fully functional for package sources even without a selector
      // runtime (feature refs prefix-match meshData part occurrence ids).
      stepParameterSource: await loadStepParameters({
        kind: "step",
        kinematics,
        stepParameterUrl,
        documentHash,
        cadPath,
        selectorRuntime: packageSelectorRuntime,
        sourceSidecar
      }),
      sourceSidecar,
      resolved,
      url: "",
      glbUrl: "",
      cadPath
    };
  }
  if (rawTessellation !== undefined && rawTessellation !== null) {
    throw new Error("quality.tessellation requires an exact-surface STEP package; existing mesh data cannot be retessellated");
  }
  const glbUrl = String(inputObject.glbUrl || resolved.glbUrl || options.glbUrl || "").trim();
  const url = String(typeof input === "string" ? input : inputObject.url || resolved.url || glbUrl || "").trim();

  // A robot is not one mesh: it is a description plus a mesh per link, assembled and posed.
  // Doing that here is what lets every mesh-path consumer — snapshot stills, orbit GIFs —
  // render a robot without knowing it is one.
  if (!meshData && (isRobotSourceKind(kind) || robotSourceKindFromUrl(url))) {
    const robot = await loadRobotMeshData(url, {
      kind,
      jointValues: inputObject.jointValues || resolved.jointValues || options.jointValues || null,
      urdfUrl: String(resolved.urdfUrl || inputObject.urdfUrl || "").trim()
    });
    return {
      kind,
      meshData: robot.meshData,
      selectorRuntime: null,
      displayEdgeRuntime: null,
      stepParameterSource: null,
      sourceSidecar,
      resolved,
      url,
      glbUrl: "",
      cadPath
    };
  }

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
      meshData = await loadMeshDataFromUrl(sourceIsStep(kind) ? glbUrl || url : url, kind);
    }

    // Selector/display-edge runtimes ride in STEP topology GLB extras. Direct mesh
    // kinds have none, and loading them anyway re-downloads the mesh binary just to
    // fail the GLB container parse — gate by kind so "no selectors for meshes" is
    // intent, not a swallowed error (matches the CLI's mesh-input validation).
    const stepSidecarsEnabled = sourceIsStep(kind) && !photographicRender;
    const selectorRuntime = photographicRender ? null : inputObject.selectorRuntime || options.selectorRuntime || (
      stepSidecarsEnabled ? await loadSelectorRuntime(glbUrl || url, { cadPath }) : null
    );
    const displayEdgeRuntime = photographicRender ? null : inputObject.displayEdgeRuntime || options.displayEdgeRuntime || (
      stepSidecarsEnabled ? await loadDisplayEdgeRuntime(glbUrl || url) : null
    );
    const stepParameterSource = await loadStepParameters({
      kind,
      kinematics,
      stepParameterUrl,
      documentHash,
      cadPath,
      selectorRuntime,
      sourceSidecar
    });

    return {
      kind,
      meshData,
      selectorRuntime,
      displayEdgeRuntime,
      stepParameterSource,
      sourceSidecar,
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
  fetchComponentGlbBuffer,
  COMPONENT_FETCH_ATTEMPTS
};

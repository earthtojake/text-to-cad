import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  isAbortError,
  loadRenderSurf,
  loadRenderSelectorBundle,
  loadRenderSurfSelectorBundle,
  peekRenderGlb,
  peekRenderSelectorBundle,
  peekRenderSurf,
  peekRenderTopologyIndex,
  prewarmSurfWorkers,
  releaseRenderSurfLevel,
  releaseSurfWorkers,
  surfTessellationCacheKey
} from "@text-to-cad/core/lib/renderAssetClient.js";
import {
  applyOccurrenceDisplay,
  assemblyRootFromTopology,
  buildComposedPackageMeshData
} from "@text-to-cad/core/lib/assembly/meshData.js";
import { mapWithConcurrency } from "@text-to-cad/core/lib/async/concurrency.js";
import {
  lodDefaultLevel,
  lodTessellationForLevel,
  normalizeLodLevel
} from "@text-to-cad/core/lib/surf/lodPolicy.js";
import {
  isTessellationCacheProbeMissError,
} from "@text-to-cad/core/lib/surf/tessellationCache.js";
import {
  installRuntimePackageDescriptor,
  loadPackageDescriptor,
  peekPackageDescriptor
} from "./packageDescriptorCache.js";
import {
  createProgressivePackageLoader,
  orderComponentsForProgressiveLoad,
  PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  progressiveLoadProgress,
  publishMeshCostAccounting,
  awaitingSameFileRevision,
  meshStateAfterCancelledLoad,
  shouldRetainCompleteSameFileMesh
} from "./packageProgressiveLoad.js";
import {
  createInitialDisplayPlans, probeInitialDisplayLod, producedDisplayLodPlan,
} from "../../../render/initialDisplayLod.js";
import { createSurfaceTicketBatches, createTessellationBodyBatches } from "./packageBatchReads.js";
import {
  matchingDisplayedPackageContext,
  retainedComponentMeshesForRevision
} from "./packageComponentReuse.js";
import { ASSET_STATUS, REFERENCE_STATUS } from "../../../workbench/constants.js";
import {
  entryAssetUrl,
  entryMeshAssetSignature,
  entryReferenceAssetSignature,
  entrySelectorTopologyAssetUrl,
  entryTopologyAssetUrl
} from "@text-to-cad/core/lib/entryAssets.js";
import { reclaimIdleSurfWorkers } from "@text-to-cad/core/lib/renderAssetClient.js";
import { estimateMeshRenderCost } from "@text-to-cad/core/lib/render/meshCost.js";
import { PERF_MEASURE_NAMES, perfMeasure, perfStart } from "@text-to-cad/core/lib/viewer/perfMarks.js";
import {
  composePackageSelectorRuntime,
  compositionUsesComponent,
  createPackageReferenceComposer,
  baseLodReferenceComposition,
  reconcileLodReferencePublication,
  reconcileLivePackageSelectorBundles
} from "./packageReferenceComposition.js";
import { selectRequestedAssemblyComponents } from "../../../workbench/referenceSelection.js";
import { createTopologyRequestSession } from "./topologyRequests.js";
import { viewerMemoryPolicy } from "../../../render/viewerMemoryPolicy.js";
import { syncSurfWorkerMemory } from "../../../render/surfWorkerMemoryPolicy.js";
import { componentMemoryAccounting } from "../../../render/renderMemoryAccounting.js";
import { completedPackages, renderAssetCacheStatsWithPackages } from "../../../render/completedPackageCache.js";
import { createLodSceneAdoption } from "../../../render/lodSceneAdoption.js";
import { lodStagingBuffers, syncSelectorCacheAccounting } from "../../../render/lodStagingMemory.js";
import { matchesLodPayloadRequest } from "../../../render/lodPayloadRequest.js";
import { publishedLodContext, updateLodMeshState, updateLodReferenceState } from "../../../render/lodPublication.js";
import {
  resolveSurfaceComponents,
  SurfaceResolutionError,
} from "../../../workbench/surfaceResolution.js";
// Only the STEP renderer mounts this hook, and it is only ever handed STEPs (its `matches`
// excludes every other format by extension). So where this used to ask whether an entry
// was a STEP, it asks whether there is one: the same answer for every input it receives.

// A package's first-level surfaces are fetched and decoded off the main thread, so the
// cap only bounds sockets and the worker's queue.
const COMPONENT_SURFACE_LOAD_CONCURRENCY = 8;

// Topology requests (loadReferencesForEntry) union into one session per file revision: a request
// never aborts the work in flight for the same revision, batches start at most every
// REFERENCE_BATCH_INTERVAL_MS (the first at once), and each adds at most
// REFERENCE_BATCH_NEW_PARTS parts not yet loaded, newest request first.
const REFERENCE_BATCH_INTERVAL_MS = 150;
const REFERENCE_BATCH_NEW_PARTS = 64;
// While a batch is in flight, parts requested after it started (one opened, pressed or rested on)
// do not wait for it: a second, small batch of at most this many loads beside it.
const REFERENCE_PRIORITY_NEW_PARTS = 8;

const GPU_BUFFER_ESTIMATE_MULTIPLIER = 1.15;

function syncAssetCacheMemory(excludeBuffers = []) {
  const caches = renderAssetCacheStatsWithPackages({ excludeBuffers: lodStagingBuffers(excludeBuffers) });
  syncSelectorCacheAccounting(viewerMemoryPolicy, Number(caches.selector?.typedBytes) || 0);
  const assetCaches = Object.entries(caches).reduce((sum, [name, stats]) => (
    name === "surfLeash" || name === "selector" ? sum : sum + (Number(stats?.typedBytes) || 0) + (Number(stats?.metadataBytes) || 0)
  ), 0);
  viewerMemoryPolicy.setRetained("assetCaches", assetCaches);
}

function syncDisplayedMemory(componentMeshDataByCid) {
  const { displayCpuBytes, gpuInputBytes, buffers } = componentMemoryAccounting(componentMeshDataByCid);
  viewerMemoryPolicy.setRetained("displayCpu", displayCpuBytes);
  viewerMemoryPolicy.setRetained("gpuEstimated", Math.ceil(gpuInputBytes * GPU_BUFFER_ESTIMATE_MULTIPLIER));
  syncAssetCacheMemory(buffers);
  if (typeof window !== "undefined") {
    window.__cadViewerMemory = viewerMemoryPolicy.snapshot();
  }
}

function publishMemoryLimitation(detail) {
  viewerMemoryPolicy.noteLimitation(detail);
  if (typeof window === "undefined") return;
  window.__cadViewerMemoryLimitation = detail;
  window.dispatchEvent(new CustomEvent("cad:memory-limitation", { detail }));
}

function abortLoad(controllerRef) {
  controllerRef.current?.abort();
  controllerRef.current = null;
}

function abortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

function componentSurfaceLoadConcurrency() {
  const hardwareConcurrency = typeof navigator !== "undefined"
    ? Number(navigator.hardwareConcurrency)
    : 0;
  if (!Number.isFinite(hardwareConcurrency) || hardwareConcurrency <= 0) {
    return COMPONENT_SURFACE_LOAD_CONCURRENCY;
  }
  // Bounded by cores because the worker still parses serially; going wider only queues.
  return Math.max(2, Math.min(COMPONENT_SURFACE_LOAD_CONCURRENCY, hardwareConcurrency));
}

// Component-GLB packages fan out to many small content-addressed GLBs (141 for
// falcon_heavy). They parse in the GLB worker (off the main thread), so — unlike
// a large single mesh — a higher fetch concurrency just overlaps
// I/O without stalling the UI. Cap generously but bounded so we do not flood the
// single worker's queue or open an unreasonable number of sockets.
const PACKAGE_COMPONENT_LOAD_CONCURRENCY = 8;

function packageComponentLoadConcurrency() {
  const hardwareConcurrency = typeof navigator !== "undefined"
    ? Number(navigator.hardwareConcurrency)
    : 0;
  if (!Number.isFinite(hardwareConcurrency) || hardwareConcurrency <= 0) {
    return PACKAGE_COMPONENT_LOAD_CONCURRENCY;
  }
  return Math.max(4, Math.min(PACKAGE_COMPONENT_LOAD_CONCURRENCY, Math.floor(hardwareConcurrency)));
}

function resolvePackageAssetUrl(source, reference, resources) {
  return resources.resolveDependency(source, reference, { kind: "package" });
}

function runtimeComponentIdentity(context, cid) {
  return context?.componentIdentityByCid?.[cid] || context?.descriptor?.components?.[cid] || null;
}

// Where a component's selector table is read from: the surface ticket's, else the one a
// static package lists beside its surf (`components/<cid>.selectors.json`).
function runtimeComponentSelectorsUrl(context, cid, resources) {
  const identity = runtimeComponentIdentity(context, cid);
  const component = context?.descriptor?.components?.[cid];
  return identity?.selectorsUrl
    || (component?.selectors ? resolvePackageAssetUrl(entryAssetUrl(context.entry, "glb"), component.selectors, resources) : "");
}

function createAssemblyPreviewMeshData(meshData, topologyManifest = null) {
  return {
    ...meshData,
    parts: null,
    assemblyRoot: assemblyRootFromTopology(topologyManifest)
  };
}

function completedPackageMeshState(entry, meshData) {
  return {
    file: entry.file, kind: entry.kind, meshHash: entryMeshAssetSignature(entry), meshData,
    assemblyStructureReady: true, assemblyInteractionReady: true,
    assemblyBackgroundError: "", assemblyBackgroundErrorMeshHash: "", assemblyFailedParts: [],
  };
}

// The parts the components that failed would have drawn, by the names the tree gives them: one
// component can be many parts (radial's nine cylinder heads share two).
function failedPartNames(descriptor, failures) {
  const failed = new Set(failures.map(({ cid }) => String(cid || "")));
  const names = [];
  for (const occurrence of descriptor?.occurrences || []) {
    if (!failed.has(String(occurrence?.component || ""))) continue;
    const name = String(occurrence?.name || occurrence?.id || occurrence?.component).trim();
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

// A detail swap (`applyComponentLodBatch`) changes the geometry on screen, never what the load said
// of the model: a package still arriving stays short of interaction, and one whose load failed keeps
// its error. Composed as a complete package instead, a swap that landed after a failed load took the
// alert away, and the partial model read "Updating model…" for good (the w16, at 120 of 777 parts).
function detailSwapMeshState(current, entry, meshData) {
  return {
    ...completedPackageMeshState(entry, meshData),
    assemblyInteractionReady: current.assemblyInteractionReady !== false,
    assemblyBackgroundError: current.assemblyBackgroundError || "",
    assemblyBackgroundErrorMeshHash: current.assemblyBackgroundErrorMeshHash || "",
    assemblyFailedParts: current.assemblyFailedParts || [],
  };
}

export function useCadAssets({
  initialEntry = null,
  client,
  tessellationCache,
  entryHasMesh,
  entryHasReferences,
  buildNormalizedReferenceState,
}) {
  const resources = client?.resources;
  if (!resources) throw new TypeError("CAD rendering requires CAD resources");
  const getAssemblyMeshHash = useCallback((entry) => {
    return entryMeshAssetSignature(entry);
  }, [resources]);

  const buildAssemblyPreviewMeshState = useCallback((entry, meshData, topologyManifest = null) => {
    const previewMeshData = createAssemblyPreviewMeshData(meshData, topologyManifest);
    return {
      file: entry.file,
      kind: entry.kind,
      meshHash: getAssemblyMeshHash(entry),
      meshData: previewMeshData,
      assemblyStructureReady: !!previewMeshData.assemblyRoot,
      assemblyInteractionReady: false,
      assemblyBackgroundError: "",
      assemblyBackgroundErrorMeshHash: "",
      assemblyFailedParts: []
    };
  }, [getAssemblyMeshHash, resources]);

  const restoreCompletedPackage = useCallback(entry => entryHasMesh(entry)
    ? completedPackages.get(client, entry, { descriptor: peekPackageDescriptor(entryAssetUrl(entry, "glb"), { resources }) })
    : null, [client, entryHasMesh]);

  const getCachedMeshState = useCallback((entry) => {
    if (!entryHasMesh(entry)) {
      return null;
    }
    // Complete STEP packages may exceed the per-component SURF LRU. Reuse their
    // bounded CPU working set, with fresh occurrence metadata for this mount.
    const completed = restoreCompletedPackage(entry);
    if (completed) return completedPackageMeshState(entry, completed.meshData);
    const previewMeshData = peekRenderGlb(entryAssetUrl(entry, "glb"), { resources });
    if (!previewMeshData) {
      return null;
    }
    const topologyManifest = peekRenderTopologyIndex(entryTopologyAssetUrl(entry), { resources });
    return topologyManifest ? null : buildAssemblyPreviewMeshState(entry, previewMeshData);
  }, [buildAssemblyPreviewMeshState, entryHasMesh, restoreCompletedPackage, resources]);

  // FileViewer remounts file-owned controls. Restore immutable warm assets on
  // the first render, as main's in-place tab activation did, without retaining
  // inactive scenes or copying component buffers.
  const initialPackageRef = useRef(undefined);
  if (initialPackageRef.current === undefined) initialPackageRef.current = restoreCompletedPackage(initialEntry);
  const initialPackage = initialPackageRef.current;
  const [meshEnvelope, setMeshEnvelope] = useState(() => ({
    value: initialPackage ? completedPackageMeshState(initialEntry, initialPackage.meshData) : getCachedMeshState(initialEntry),
    reference: null, receipt: null,
  }));
  const meshState = meshEnvelope.value;
  const setMeshState = useCallback(update => {
    setMeshEnvelope(previous => updateLodMeshState(previous, update));
  }, [resources]);
  const meshStateRef = useRef(meshState);
  meshStateRef.current = meshState;
  const [meshLoadInProgress, setMeshLoadInProgress] = useState(false);
  const [meshLoadTargetFile, setMeshLoadTargetFile] = useState("");
  const [meshLoadTargetHash, setMeshLoadTargetHash] = useState("");
  // The file and revision whose load failed outright; see shouldStartMeshLoad. Forgotten by the
  // caller when something outside the load changed what it would find (a build of the revision).
  const [fatalLoadFailure, setFatalLoadFailure] = useState(null);
  const clearFatalLoadFailure = useCallback(() => setFatalLoadFailure(null), []);
  const [meshLoadProgress, setMeshLoadProgress] = useState(null);
  const [status, setStatus] = useState(ASSET_STATUS.READY);
  const [error, setError] = useState("");
  const referenceState = meshEnvelope.reference;
  const setReferenceState = useCallback(update => {
    setMeshEnvelope(previous => updateLodReferenceState(previous, update));
  }, [resources]);
  const referenceStateRef = useRef(referenceState);
  referenceStateRef.current = referenceState;
  const [referenceStatus, setReferenceStatus] = useState(REFERENCE_STATUS.IDLE);
  const [referenceError, setReferenceError] = useState("");
  const [referenceLoadStage, setReferenceLoadStage] = useState("");

  const requestIdRef = useRef(0);
  const referenceRequestIdRef = useRef(0);
  const meshAbortControllerRef = useRef(null);
  const referenceAbortControllerRef = useRef(null);
  // The topology request session (see loadReferencesForEntry) and the composer whose parts
  // (one per loaded occurrence) make adding topology cost what is added, not what is loaded.
  const referenceSessionRef = useRef(null);
  const referenceComposerRef = useRef(null);
  if (!referenceComposerRef.current) referenceComposerRef.current = { key: "", composer: createPackageReferenceComposer() };

  // --- viewport LOD (packages/ui/docs/lod.md) -----------------
  // The composed package's ingredients, kept so a level swap can re-compose ONE
  // component at a finer tessellation without reloading anything else. Ref +
  // state pair: the ref is the mutable working set, the state is the reactive
  // summary the LOD hook consumes (component diagonals, occurrence centers in
  // model coordinates, and each component's surf URL).
  const lodPackageRef = useRef(initialPackage);
  const lodSceneAdoptionRef = useRef(null);
  if (!lodSceneAdoptionRef.current) {
    lodSceneAdoptionRef.current = createLodSceneAdoption({ currentContext: () => lodPackageRef.current });
  }
  useLayoutEffect(() => {
    lodSceneAdoptionRef.current.committed(meshEnvelope.receipt);
  }, [meshEnvelope.receipt, resources]);
  const onMeshSourceAdoption = useCallback((source, ok, detail) => {
    if (detail?.disposed) {
      lodSceneAdoptionRef.current.disposed(source, { recover: detail.recover === true,
        terminal: detail.terminal === true, handoff: detail.handoff === true });
      return { recovering: lodSceneAdoptionRef.current.snapshot().phase === "restoring" };
    }
    if (ok) return lodSceneAdoptionRef.current.adopted(source);
    if (detail?.cleanupFailed) setError("Scene cleanup failed. Detail work has stopped; reload the viewer.");
    return lodSceneAdoptionRef.current.failed(source, detail);
  }, [resources]);
  // Unlike lodPackageRef (the active staging/scheduler context), this ref owns
  // only the complete package whose meshState is actually displayed. Keeping
  // it separate lets A survive a failed/cancelled B and seed C without letting
  // B regain publication or LOD ownership.
  const displayedLodPackageRef = useRef(initialPackage);
  const [lodPackage, setLodPackage] = useState(null);
  useEffect(() => {
    lodSceneAdoptionRef.current.checkContext();
    if (!meshState || meshState.file !== lodPackageRef.current?.file) lodSceneAdoptionRef.current.cancel();
  }, [lodPackage, meshState?.file, resources]);
  useEffect(() => {
    const snapshot = () => lodSceneAdoptionRef.current.snapshot();
    if (typeof window !== "undefined") window.__cadLodSceneAdoption = snapshot;
    return () => {
      lodSceneAdoptionRef.current.cancel();
      if (typeof window !== "undefined" && window.__cadLodSceneAdoption === snapshot) delete window.__cadLodSceneAdoption;
    };
  }, [resources]);
  // The composed reference state's ingredients: the lazily-loaded occurrence
  // subset and the selector bundle each component's topology was built from.
  // Kept so an LOD level swap can re-compose PICKING from the same
  // tessellation the display mesh just moved to. Mesh and selector runtime
  // must always come from ONE tessellation (loadRenderSurfPayloadAtLevel's
  // contract): faceRuns carry triangle ranges of a specific tessellation, so
  // a level-N mesh read through level-M runs mislabels triangles — partial
  // face highlights and picks that resolve through the surface.
  const referenceCompositionRef = useRef(null);
  const displayedReferenceCompositionRef = useRef(null);
  const surfaceViewReplacementRef = useRef(null);
  const surfaceViewReplacementTaskRef = useRef(null);
  const componentLodNeedsSelectors = useCallback((cid) => {
    const ctx = lodPackageRef.current;
    const composition = ctx?.lodPending?.referenceComposition || referenceCompositionRef.current;
    return Boolean(ctx && composition?.file === ctx.file && compositionUsesComponent(composition, cid));
  }, [resources]);

  const buildLodPackageSummary = useCallback((entry, meshUrl, descriptor, componentMeshDataByCid, componentIdentityByCid = {}) => {
    const transformPoint = (m, p) => (Array.isArray(m) && m.length >= 12
      ? [
        m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3],
        m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7],
        m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11]
      ]
      : p);
    const transformsByCid = new Map();
    for (const occurrence of descriptor.occurrences || []) {
      const cid = String(occurrence?.component || "").trim();
      if (!transformsByCid.has(cid)) {
        transformsByCid.set(cid, []);
      }
      transformsByCid.get(cid).push(occurrence?.transform || null);
    }
    const components = Object.entries(descriptor.components || {})
      .map(([cid, component]) => {
        const bounds = componentMeshDataByCid[cid]?.bounds;
        const identity = componentIdentityByCid[cid] || component;
        if (!bounds?.min || !bounds?.max || !identity?.surfaceObject) {
          return null;
        }
        const center = [
          (bounds.min[0] + bounds.max[0]) / 2,
          (bounds.min[1] + bounds.max[1]) / 2,
          (bounds.min[2] + bounds.max[2]) / 2
        ];
        const diagonal = Math.hypot(
          bounds.max[0] - bounds.min[0],
          bounds.max[1] - bounds.min[1],
          bounds.max[2] - bounds.min[2]
        );
        const centers = (transformsByCid.get(cid) || []).map((m) => transformPoint(m, center));
        if (!centers.length || !(diagonal > 0)) {
          return null;
        }
        return {
          cid,
          descriptor,
          file: entry.file,
          diagonal,
          centers,
          surfUrl: identity.surfUrl || (component.surf ? resolvePackageAssetUrl(meshUrl, component.surf, resources) : ""),
          selectorsUrl: identity.selectorsUrl || (component.selectors ? resolvePackageAssetUrl(meshUrl, component.selectors, resources) : ""),
          identity,
          // The component's surface, and its mesh at `tessellation` when one is named: cadgen
          // meshes a level its store lacks, and `mesh` is that level's probe row.
          resolveSurface: async (signal, tessellation) => {
            let resolved;
            try {
              resolved = await resolveSurfaceComponents(descriptor, [{
                cid, surfaceInput: identity.surfaceInput, surfaceObject: identity.surfaceObject,
              }], { client, signal, tessellation });
            } catch (error) {
              if (error instanceof SurfaceResolutionError && error.replacementView) {
                surfaceViewReplacementRef.current?.(entry, meshUrl, error.replacementView);
              }
              throw error;
            }
            const { mesh = null, ...surface } = resolved.get(cid);
            const nextIdentity = Object.freeze({ ...component, ...surface });
            const context = lodPackageRef.current;
            if (context?.descriptor === descriptor) {
              context.componentIdentityByCid = {
                ...(context.componentIdentityByCid || {}), [cid]: nextIdentity,
              };
            }
            return { identity: nextIdentity, surfUrl: nextIdentity.surfUrl, selectorsUrl: nextIdentity.selectorsUrl, mesh };
          },
          meshBytes: estimateMeshRenderCost(componentMeshDataByCid[cid]).typedArrayBytes,
          meshData: componentMeshDataByCid[cid],
          level: normalizeLodLevel(componentMeshDataByCid[cid]?.lodLevel)
        };
      })
      .filter(Boolean);
    return { file: entry.file,
      modelKey: `${entry.file}:${entryMeshAssetSignature(entry) || entry.hash || ""}`,
      components };
  }, [client, resources]);

  useLayoutEffect(() => {
    if (!initialPackage) return;
    initialPackageRef.current = null;
    setLodPackage(buildLodPackageSummary(initialPackage.entry, initialPackage.meshUrl, initialPackage.descriptor,
      initialPackage.componentMeshDataByCid, initialPackage.componentIdentityByCid));
    const count = Object.keys(initialPackage.componentMeshDataByCid).length;
    publishMeshCostAccounting({ ...initialPackage, loaded: count, total: count, final: true, meshRevision: initialPackage.meshHash });
    syncDisplayedMemory(initialPackage.componentMeshDataByCid);
  }, [initialPackage, buildLodPackageSummary, resources]);

  // This preparation is called by the scheduler's sole loader lane. Batch
  // publication itself performs no asynchronous geometry/selector work.
  const prepareComponentLodPayload = useCallback((cid, level, payload, { signal } = {}) => {
    const ctx = lodPackageRef.current;
    if (!ctx || signal?.aborted || !payload?.meshData) throw abortError();
    const component = runtimeComponentIdentity(ctx, cid);
    const selectorsUrl = runtimeComponentSelectorsUrl(ctx, cid, resources);
    if (!matchesLodPayloadRequest(payload.lodRequest, ctx, cid, level, selectorsUrl)) throw abortError();
    if (payload.bundle || !componentLodNeedsSelectors(cid)) return payload;
    return loadRenderSurfSelectorBundle(selectorsUrl, { resources, tessellationCache,
      signal, tessellation: lodTessellationForLevel(level), identity: component,
    }).then(bundle => {
      if (lodPackageRef.current !== ctx || signal?.aborted) throw abortError();
      return { ...payload, bundle };
    }).finally(() => { releaseSurfWorkers().then(syncSurfWorkerMemory, syncSurfWorkerMemory); });
  }, [componentLodNeedsSelectors, resources]);

  const applyComponentLodBatch = useCallback(async (entries, { signal } = {}) => {
    const ctx = lodPackageRef.current;
    if (!ctx || signal?.aborted || meshStateRef.current?.file !== ctx.file || !entries?.length || entries.length > 4 ||
        new Set(entries.map(item => item.cid)).size !== entries.length || ctx.lodPending || lodSceneAdoptionRef.current.snapshot().pending) return false;
    const items = [];
    for (const { cid, level, payload } of entries) {
      const normalizedLevel = normalizeLodLevel(level);
      const component = runtimeComponentIdentity(ctx, cid);
      const selectorsUrl = runtimeComponentSelectorsUrl(ctx, cid, resources);
      if (!payload?.meshData || !matchesLodPayloadRequest(payload.lodRequest, ctx, cid, normalizedLevel, selectorsUrl)) return false;
      if (!payload.bundle && componentLodNeedsSelectors(cid)) return { status: "not-ready" };
      items.push({ cid, normalizedLevel, previousLevel: normalizeLodLevel(ctx.componentLodLevelByCid?.[cid]),
        component, surfUrl: selectorsUrl, payload, baseMesh: ctx.componentMeshDataByCid[cid],
        nextMesh: Object.freeze({ ...payload.meshData, lodLevel: normalizedLevel, lodKey: payload.lodRequest.key }) });
    }
    const revision = ctx.meshHash;
    const baseReferenceState = referenceStateRef.current;
    const baseReferenceComposition = referenceCompositionRef.current;
    const bundleByCid = { ...(ctx.componentLodBundleByCid || {}) };
    const bundleKeyByCid = { ...(ctx.componentLodBundleKeyByCid || {}) };
    const maps = {
      componentMeshDataByCid: { ...ctx.componentMeshDataByCid },
      componentLodBundleByCid: bundleByCid,
      componentLodBundleKeyByCid: bundleKeyByCid,
      componentLodLevelByCid: { ...(ctx.componentLodLevelByCid || {}) },
    };
    for (const item of items) {
      const { cid, payload, nextMesh, normalizedLevel } = item;
      maps.componentMeshDataByCid[cid] = nextMesh;
      maps.componentLodLevelByCid[cid] = normalizedLevel;
      if (payload.bundle) {
        bundleByCid[cid] = payload.bundle;
        bundleKeyByCid[cid] = payload.lodRequest.key;
      } else { delete bundleByCid[cid]; delete bundleKeyByCid[cid]; }
    }
    const composed = buildComposedPackageMeshData(ctx.descriptor, maps.componentMeshDataByCid, { previous: ctx.meshData });
    // Finish selector composition and other fallible preparation before any
    // state update can publish candidate geometry. A thrown preparation owns
    // no scene and can release the scheduler's lease normally.
    const references = prepareReferenceStateForLodRef.current(ctx, items);
    const pending = { items, source: composed, maps, baseSource: ctx.meshData,
      candidateSources: new WeakSet([composed]), baseSources: new WeakSet([ctx.meshData]),
      baseReferenceState, baseReferenceComposition,
      referenceComposition: references?.composition || baseReferenceComposition };
    if (ctx.lodPending || lodSceneAdoptionRef.current.snapshot().pending) return false;
    publishMeshCostAccounting({ meshData: composed, componentMeshDataByCid: maps.componentMeshDataByCid,
      loaded: Object.keys(maps.componentMeshDataByCid).length, total: Object.keys(ctx.descriptor.components || {}).length,
      publishCount: ctx.publishCount, meshRevision: ctx.meshHash, final: ctx.complete });
    ctx.lodPending = pending;
    const tracker = lodSceneAdoptionRef.current;
    const command = { retired: false, source: composed, reference: references?.state };
    const completed = tracker.expectBatch({ command, context: ctx, source: composed, descriptor: ctx.descriptor,
      items: items.map(item => ({ componentId: item.cid, componentMesh: item.nextMesh, baseMesh: item.baseMesh,
        tessellationKey: item.payload.lodRequest.key })),
      candidateSources: pending.candidateSources, baseSources: pending.baseSources,
      baseSource: pending.baseSource, signal,
      currentSource: () => pending.source, currentBaseSource: () => pending.baseSource,
      commit: (adoptedSource) => {
        pending.adopted = true;
        if (ctx.meshHash === revision) {
          Object.assign(ctx, pending.maps, { meshData: adoptedSource });
          if (pending.referenceComposition) {
            if (lodPackageRef.current === ctx) referenceCompositionRef.current = pending.referenceComposition;
            if (displayedLodPackageRef.current === ctx) displayedReferenceCompositionRef.current = pending.referenceComposition;
          }
        }
        if (ctx.lodPending === pending) delete ctx.lodPending;
        // The inactive snapshot must not keep obsolete detail levels alive.
        // Cleanup captures this newly committed CPU working set instead.
        completedPackages.delete(client, ctx.entry);
        for (const item of items) if (item.previousLevel !== item.normalizedLevel) releaseRenderSurfLevel(item.surfUrl, {
          tessellation: lodTessellationForLevel(item.previousLevel), identity: item.component,
        });
      },
      restore: recoveryCommand => {
        if (lodPackageRef.current !== ctx) return null;
        // Full renderer teardown has completed. A fresh scene adopts this
        // matching committed mesh/reference pair; no disposed record is reused.
        pending.phase = "restoring";
        referenceRequestIdRef.current += 1;
        abortLoad(referenceAbortControllerRef);
        referenceCompositionRef.current = pending.baseReferenceComposition;
        displayedReferenceCompositionRef.current = pending.baseReferenceComposition;
        const baseSource = pending.baseSource;
        recoveryCommand.source = baseSource;
        recoveryCommand.reference = pending.baseReferenceState;
        setMeshEnvelope(previous => updateLodMeshState(previous, current => (
          lodPackageRef.current === ctx && current?.file === ctx.file
            ? detailSwapMeshState(current, ctx.entry, baseSource) : current
        ), recoveryCommand));
        setError("Detail update failed; restoring the previous view.");
        return baseSource;
      },
      failed: () => {
        if (lodPackageRef.current === ctx) setError("Detail update and restoration failed. Reload the model to continue.");
      },
      onSettled: outcome => {
        if (outcome === "restored" && lodPackageRef.current === ctx) {
          referenceCompositionRef.current = pending.baseReferenceComposition;
          if (displayedLodPackageRef.current === ctx) displayedReferenceCompositionRef.current = pending.baseReferenceComposition;
        }
        if (ctx.lodPending === pending) delete ctx.lodPending;
        if (!pending.adopted) for (const item of items) if (item.previousLevel !== item.normalizedLevel) {
          releaseRenderSurfLevel(item.surfUrl, { tessellation: lodTessellationForLevel(item.normalizedLevel), identity: item.component });
        }
        if (outcome === "restored" && lodPackageRef.current === ctx) setError("Detail update failed; the previous view was restored.");
        const displayed = displayedLodPackageRef.current;
        syncAssetCacheMemory(componentMemoryAccounting(displayed?.componentMeshDataByCid).buffers);
      },
    });
    tracker.published(composed);
    setMeshEnvelope(previous => updateLodMeshState(previous, current => (
      !current || current.file !== ctx.file || lodPackageRef.current !== ctx || signal?.aborted ? current
        : detailSwapMeshState(current, ctx.entry, composed)
    ), command));
    const outcome = await completed;
    if (outcome.status === "disposed-failed") return { status: "scene-failed" };
    if (pending.adopted) return { status: outcome.status === "adopted" && !signal?.aborted ? "adopted" : "retained",
      components: items.map(item => ({ cid: item.cid, level: item.normalizedLevel, meshData: item.nextMesh })) };
    return false;
  }, [componentLodNeedsSelectors, client, resources]);

  // Rebuild the composed selector runtime with one component's bundle swapped
  // to the level the display mesh just moved to. Scoped to the composition's
  // already-loaded occurrence subset (lazy topology stays lazy).
  const prepareReferenceStateForLod = useCallback((ctx, items) => {
    const composition = ctx.lodPending?.referenceComposition || referenceCompositionRef.current;
    if (!composition || composition.file !== ctx.file) {
      return;
    }
    const changed = items.filter(item => item.payload.bundle && compositionUsesComponent(composition, item.cid));
    if (!changed.length) return;
    const bundleByCid = { ...composition.bundleByCid };
    for (const item of changed) bundleByCid[item.cid] = item.payload.bundle;
    const nextComposition = { ...composition, bundleByCid };
    const nextReferenceState = buildNormalizedReferenceState(nextComposition.entry, null, {
      selectorRuntime: composePackageSelectorRuntime(
        nextComposition.entry,
        nextComposition.occurrencesToLoad,
        nextComposition.bundleByCid,
        { singleComponentPart: nextComposition.isSingleComponentPart, composer: referenceComposerRef.current.composer }
      ),
      loadedTopologyKey: nextComposition.loadedTopologyKey,
      loadedTopologyIds: nextComposition.loadedTopologyIds
    });
    return { composition: nextComposition, state: nextReferenceState };
  }, [buildNormalizedReferenceState, resources]);
  const prepareReferenceStateForLodRef = useRef(prepareReferenceStateForLod);
  prepareReferenceStateForLodRef.current = prepareReferenceStateForLod;


  const getCachedReferenceState = useCallback((entry) => {
    if (!entryHasReferences(entry)) {
      return null;
    }
    const bundle = peekRenderSelectorBundle(entrySelectorTopologyAssetUrl(entry), { resources });
    return bundle ? buildNormalizedReferenceState(entry, bundle) : null;
  }, [buildNormalizedReferenceState, entryHasReferences, resources]);

  const cancelMeshLoad = useCallback(() => {
    lodSceneAdoptionRef.current.cancel();
    requestIdRef.current += 1;
    abortLoad(meshAbortControllerRef);
    publishMeshCostAccounting(null);
    viewerMemoryPolicy.setRetained("replacementPending", 0);
    // A load cancelled mid-way leaves a PARTIAL composition published; drop it
    // and its LOD working set so the component arrays it references can go. A
    // complete model stays (it is still the right thing to show).
    const ctx = lodPackageRef.current;
    if (ctx && ctx.complete === false) {
      lodPackageRef.current = null;
      setLodPackage(null);
      setMeshState((current) => meshStateAfterCancelledLoad(current, ctx.file));
      syncDisplayedMemory(null);
    }
    const displayed = matchingDisplayedPackageContext(
      displayedLodPackageRef.current,
      meshStateRef.current,
      meshStateRef.current?.file,
    );
    if (displayed) {
      lodPackageRef.current = displayed;
      setLodPackage(buildLodPackageSummary(
        displayed.entry,
        displayed.meshUrl,
        displayed.descriptor,
        displayed.componentMeshDataByCid,
        displayed.componentIdentityByCid,
      ));
      const displayedReferences = displayedReferenceCompositionRef.current;
      referenceCompositionRef.current = displayedReferences?.meshHash === displayed.meshHash
        ? displayedReferences
        : null;
    }
    setMeshLoadInProgress(false);
    setMeshLoadTargetFile("");
    setMeshLoadTargetHash("");
    setMeshLoadProgress(null);
  }, [buildLodPackageSummary, resources]);

  const cancelReferenceLoad = useCallback(() => {
    referenceRequestIdRef.current += 1;
    abortLoad(referenceAbortControllerRef);
    referenceSessionRef.current = null;
    setReferenceLoadStage("");
  }, [resources]);

  const loadMeshForEntry = useCallback(async (entry) => {
    const previousDisplayed = displayedLodPackageRef.current;
    if (previousDisplayed) completedPackages.set(client, previousDisplayed.entry, previousDisplayed);
    cancelMeshLoad();
    const requestId = requestIdRef.current;

    if (!entryHasMesh(entry)) {
      // The same file, rewritten, before its next revision is built: what is on screen stays,
      // and the revision replaces it when it arrives.
      if (awaitingSameFileRevision(meshStateRef.current, entry)) {
        setStatus(ASSET_STATUS.PENDING);
        setError("");
        return;
      }
      displayedLodPackageRef.current = null;
      displayedReferenceCompositionRef.current = null;
      syncDisplayedMemory(null);
      setMeshState(null);
      setStatus(ASSET_STATUS.PENDING);
      setError("");
      return;
    }

    const surfaceViewReplacement = entry?.runtimeSurfaceViewReplacement === true;
    const targetMeshHash = getAssemblyMeshHash(entry);
    const completed = surfaceViewReplacement ? null : restoreCompletedPackage(entry);
    syncAssetCacheMemory(componentMemoryAccounting(previousDisplayed?.componentMeshDataByCid).buffers);
    if (completed) {
      completed.requestId = requestId;
      lodPackageRef.current = completed;
      displayedLodPackageRef.current = completed;
      displayedReferenceCompositionRef.current = null;
      referenceCompositionRef.current = null;
      setLodPackage(buildLodPackageSummary(entry, completed.meshUrl, completed.descriptor,
        completed.componentMeshDataByCid, completed.componentIdentityByCid));
      setMeshState(completedPackageMeshState(entry, completed.meshData));
      const count = Object.keys(completed.componentMeshDataByCid).length;
      publishMeshCostAccounting({ ...completed, loaded: count, total: count, final: true, meshRevision: completed.meshHash });
      syncDisplayedMemory(completed.componentMeshDataByCid);
      setStatus(ASSET_STATUS.READY);
      setError("");
      return;
    }
    const atomicSameFileReplacement = shouldRetainCompleteSameFileMesh(
      meshStateRef.current,
      entry,
      targetMeshHash
    );
    const previousCompleteLodPackage = atomicSameFileReplacement
      ? matchingDisplayedPackageContext(displayedLodPackageRef.current, meshStateRef.current, entry.file)
      : null;
    const cachedMeshState = surfaceViewReplacement ? null : getCachedMeshState(entry);
    if (cachedMeshState && !atomicSameFileReplacement) {
      displayedLodPackageRef.current = null;
      displayedReferenceCompositionRef.current = null;
      setMeshState(cachedMeshState);
      setStatus(ASSET_STATUS.READY);
      setError("");
      if (entry?.kind !== "assembly" || cachedMeshState.assemblyInteractionReady || cachedMeshState.assemblyBackgroundError) {
        return;
      }
    }

    const controller = new AbortController();
    meshAbortControllerRef.current = controller;
    setMeshLoadInProgress(true);
    setMeshLoadTargetFile(String(entry?.file || "").trim());
    setMeshLoadTargetHash(targetMeshHash);
    setMeshLoadProgress({
      phase: "finding",
      label: "Finding model",
      done: 0,
      total: 0,
      determinate: false,
    });
    // Any new load invalidates the previous entry's LOD working set. A
    // complete same-file scene can remain rendered while its replacement is
    // decoded; it is frozen at its current LOD until the atomic commit.
    lodPackageRef.current = null;
    setLodPackage(null);
    referenceCompositionRef.current = null;
    const stageWholeReplacement = atomicSameFileReplacement || surfaceViewReplacement;
    const keepRenderedAssemblyVisible = entry?.kind === "assembly" && (
      !!cachedMeshState || atomicSameFileReplacement || (
        surfaceViewReplacement && meshStateRef.current?.file === entry.file
      )
    );
    let assemblyPreviewVisible = keepRenderedAssemblyVisible;
    if (!keepRenderedAssemblyVisible) {
      setStatus(ASSET_STATUS.LOADING);
      setError("");
    }

    try {
      // Every STEP entry is a component-GLB package (a single-component part is just a
      // package with one occurrence); compose it the same way.
      setMeshLoadProgress({
        phase: "read",
        label: "Reading model",
        done: 0,
        total: 0,
        determinate: false,
      });
      const meshUrl = entryAssetUrl(entry, "glb");
      if (!meshUrl) {
        throw new Error(`STEP file is missing GLB asset: ${entry.file || "(unknown)"}`);
      }
      // Component-GLB package: the canonical STEP artifact is a directory. Probe for
      // its assembly.json, fetch each unique component GLB once, and compose them in
      // world space. A non-package descriptor is a stale/unbuilt artifact (throws below).
      const storedPackageDescriptor = await loadPackageDescriptor(meshUrl, { resources, signal: controller.signal });
      if (controller.signal.aborted) {
        throw abortError();
      }
      // The tree joined to what cadgen resolved its appearance to (the entry's `display`,
      // per assigned occurrence): the page draws the finishes and colours it is given.
      const packageDescriptor = storedPackageDescriptor
        ? applyOccurrenceDisplay(storedPackageDescriptor, entry?.display)
        : null;
      if (packageDescriptor && packageDescriptor.kind === "assembly-package") {
        // Progressive publish (packages/ui/docs/lod.md, section 4): components are
        // fetched with bounded concurrency and the ones loaded so far are
        // re-composed and published per batch (packageProgressiveLoad.js owns
        // the batch policy), so the model paints while it loads and a cancel
        // frees what was never published. Composition is the reference-based
        // path applyComponentLodPayload uses for a level swap. The final
        // publish carries every component and is the state the single
        // post-load publish used to produce.
        let publishedOnce = false;
        const componentEntries = Object.entries(packageDescriptor.components || {});
        // Whether cadgen is meshing any part this open asked for (its store lacked it), and the
        // parts settled so far: the frame says "Meshing parts" from the first pending answer on.
        let meshing = false;
        let settledSoFar = 0;
        setMeshLoadProgress(progressiveLoadProgress(0, componentEntries.length));
        // Runtime tickets bind the geometry descriptor's opaque D to the
        // concrete O selected by either a stored mesh's probe or surface resolution.
        // They never rewrite the canonical descriptor.
        const componentIdentityByCid = new Map();
        const retainedComponentMeshByCid = retainedComponentMeshesForRevision({
          previous: previousCompleteLodPackage,
          descriptor: packageDescriptor,
          meshUrl,
        });
        for (const cid of Object.keys(retainedComponentMeshByCid)) {
          const previousIdentity = previousCompleteLodPackage?.componentIdentityByCid?.[cid]
            || previousCompleteLodPackage?.descriptor?.components?.[cid];
          if (previousIdentity?.surfaceObject) {
            componentIdentityByCid.set(cid, Object.freeze({
              ...packageDescriptor.components[cid],
              surfaceObject: previousIdentity.surfaceObject,
              surfUrl: previousIdentity.surfUrl || "",
              selectorsUrl: previousIdentity.selectorsUrl || "",
            }));
          }
        }
        // One request for many components where a lane made one each (`packageBatchReads.js`):
        // their initial tiers, probed a chunk at a time; the warm ones' bodies, read a batch at a
        // time; the cold ones' surfaces and meshes, resolved up to a request's bound at a time. Each
        // follows the order the lanes load in. A same-file revision's retained components read nothing.
        const readOrder = orderComponentsForProgressiveLoad(packageDescriptor)
          .filter(([cid]) => !retainedComponentMeshByCid[cid]);
        const readCids = readOrder.map(([cid]) => cid);
        // A warm load's isolates start once its first probe shows warm bodies, while the first batch
        // is on the wire: a batch hands its bodies over at once, and they would all start only then.
        // A cold load's start as its surfaces come (measured: started earlier, they finish later).
        let prewarmed = false;
        const prewarmForBatches = () => {
          if (prewarmed) return;
          prewarmed = true;
          prewarmSurfWorkers(Math.min(readCids.length, packageComponentLoadConcurrency()));
        };
        const staticSurfUrl = component => (component?.surf ? resolvePackageAssetUrl(meshUrl, component.surf, resources) : "");
        const staticSelectorsUrl = component => (component?.selectors ? resolvePackageAssetUrl(meshUrl, component.selectors, resources) : "");
        // A cold component opens at the standard level, as a warm one does: cadgen meshes it there in
        // the same request that derives its surface, and nothing is tessellated here.
        const coldTessellation = lodTessellationForLevel(lodDefaultLevel());
        // The first geometry waits on the first chunk's probe and the first batch's read: nothing
        // is read ahead of them until a lane is past its body read.
        let firstBodyRead;
        const pastFirstBodyRead = new Promise((resolve) => { firstBodyRead = resolve; });
        const initialPlans = createInitialDisplayPlans({
          components: readOrder,
          maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
          signal: controller.signal,
          readAheadAfter: pastFirstBodyRead,
          probeEntries: (inputs, tessellation, options) => tessellationCache.probeCachedTessellationEntries(inputs, tessellation, options),
        });
        const bodyBatches = createTessellationBodyBatches({
          order: readCids,
          rowOf: (cid) => {
            const planned = initialPlans.peek(cid);
            return planned === undefined ? undefined : planned?.cacheProbe || null;
          },
          readMany: (rows, options) => tessellationCache.getCachedEntryBytesMany(rows, options),
          // No batch asks for more than the client's transport carries in one reply.
          maxBytes: tessellationCache?.batchMaxBytes,
          // A batch's bodies are charged before they are read, as a lane's own body is.
          reserve: bytes => viewerMemoryPolicy.reserve({
            category: "workerInFlight", bytes, label: "tessellation batch", kind: "replace", recordLimitation: false,
          }),
          release: token => viewerMemoryPolicy.release(token),
          // A payload this page already holds needs no body read.
          skip: (cid, row) => Boolean(peekRenderSurf("", {
            tessellation: lodTessellationForLevel(lodDefaultLevel()),
            identity: { surfaceInput: row.surfaceInput, surfaceObject: row.surfaceObject },
          })),
          signal: controller.signal,
        });
        const surfaceTickets = createSurfaceTicketBatches({
          order: readCids,
          needs: (cid) => {
            const planned = initialPlans.peek(cid);
            if (planned === undefined) return undefined;
            return !planned ? packageDescriptor.components[cid] : false;
          },
          resolve: (requested, options) => resolveSurfaceComponents(packageDescriptor, requested, {
            ...options, client, tessellation: coldTessellation,
            onPending: () => {
              if (meshing || requestId !== requestIdRef.current || controller.signal.aborted) return;
              meshing = true;
              setMeshLoadProgress(progressiveLoadProgress(settledSoFar, componentEntries.length, undefined, { meshing }));
            },
          }),
          signal: controller.signal,
        });
        const loader = createProgressivePackageLoader({
          descriptor: packageDescriptor,
          // Atomic same-file revisions keep the old complete composition on
          // screen while staging. Seed the new composer from that exact
          // predecessor so unchanged occurrence rows and tree branches can
          // cross the revision boundary. The request-local loader is the only
          // added owner; failure clears it and success drops it with the load.
          initialComposition: previousCompleteLodPackage?.meshData || null,
          concurrency: packageComponentLoadConcurrency(),
          // The local cap controls package concurrency. A single larger
          // leaf may run alone only if reserveLoad below can charge its full
          // worker estimate to the shared Viewer memory envelope.
          allowOversizedSingle: true,
          retainedComponent: (cid) => retainedComponentMeshByCid[cid] || null,
          retryCacheProbeMiss: isTessellationCacheProbeMissError,
          // A component cadgen could not derive or mesh (its own failed row) is left out: the rest
          // of the model is drawn, and the final publish reports it as the load's background error.
          componentFailed: (error, cid) => error instanceof SurfaceResolutionError
            && !error.replacementView && error.cid === cid,
          // The component's stored mesh, as cadgen made it. Same meshData contract as the
          // component GLB this replaced.
          loadComponent: async (cid, _component, { estimatedBytes, cacheProbe }) => {
            const identity = componentIdentityByCid.get(cid);
            if (!identity?.surfaceObject) {
              throw new Error(`Component ${cid} has no resolved surface identity`);
            }
            // A warm body comes from its batch; null leaves the read to the worker, as before.
            let tessellationEntry = null;
            try {
              if (cacheProbe) tessellationEntry = await bodyBatches.take(cid, cacheProbe);
            } finally {
              firstBodyRead();
            }
            const meshData = await loadRenderSurf(
              identity.surfUrl || "",
              { resources, tessellationCache,
                      signal: controller.signal,
                tessellation: lodTessellationForLevel(lodDefaultLevel()),
                identity: { ...identity, tessellationProbe: cacheProbe || null,
                  ...(tessellationEntry ? { tessellationEntry } : {}) },
                memoryEstimateBytes: estimatedBytes,
              },
            );
            meshData.lodLevel = lodDefaultLevel();
            return meshData;
          },
          // Byte-aware admission: every component is sized by its stored mesh's probe row before
          // its decode is admitted -- a warm one's from the package's probe, a cold one's from the
          // surface request that had cadgen mesh it.
          sizeHint: async (cid, component, {
            rejectedCacheObjects = new Set(),
            skipCacheProbes = false,
          } = {}) => {
            const surfaceInput = String(component?.surfaceInput || "");
            // The first ask is the package's batched probe; one after a probed body went missing
            // asks afresh, alone, as every ask once did.
            const afresh = rejectedCacheObjects.size > 0;
            if (afresh) bodyBatches.discard(cid);
            const cached = skipCacheProbes ? null : afresh
              ? await probeInitialDisplayLod({ tessellationCache,
                surfaceInput,
                surfaceObject: component.surfaceObject,
                maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
                signal: controller.signal,
                rejectedCacheObjects,
              })
              : (await initialPlans.plan(cid)) ?? null;
            if (cached) {
              prewarmForBatches();
              componentIdentityByCid.set(cid, Object.freeze({
                ...component,
                surfaceObject: cached.cacheProbe.surfaceObject,
                surfUrl: staticSurfUrl(component),
                selectorsUrl: staticSelectorsUrl(component),
              }));
              return { sourceBytes: null, cacheProbe: cached.cacheProbe };
            }
            // Cold: the surface request has cadgen derive the surface and mesh it at the standard
            // level, and answers with the mesh's probe row. A retry after a missing body asks again,
            // alone, so a mesh the store lost is made anew.
            const ticket = afresh || skipCacheProbes
              ? (await resolveSurfaceComponents(packageDescriptor, [{
                cid, surfaceInput, surfaceObject: component.surfaceObject,
              }], { client, signal: controller.signal, tessellation: coldTessellation })).get(cid)
              : await surfaceTickets.ticket(cid, component);
            const { mesh, ...surface } = ticket;
            const plan = producedDisplayLodPlan(mesh, { maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES });
            if (!plan) throw new Error(`Component ${cid} has no standard mesh`);
            componentIdentityByCid.set(cid, Object.freeze({ ...component, ...surface }));
            return { sourceBytes: null, cacheProbe: mesh };
          },
          reserveLoad: ({ cid, estimatedBytes }) => viewerMemoryPolicy.reserve({
            category: "workerInFlight",
            bytes: estimatedBytes,
            label: cid,
            kind: "replace",
            // A miss can be transient while another admitted worker owns
            // the remaining bytes. The loader reports only a miss that is
            // still impossible after all in-flight work drains.
            recordLimitation: false
          }),
          releaseLoad: (token) => {
            viewerMemoryPolicy.release(token);
            syncSurfWorkerMemory();
          },
          recoverMemoryPressure: async () => {
            if (completedPackages.clear()) {
              syncAssetCacheMemory(componentMemoryAccounting(displayedLodPackageRef.current?.componentMeshDataByCid).buffers);
              return true;
            }
            const reclaimed = reclaimIdleSurfWorkers();
            syncSurfWorkerMemory();
            if (reclaimed.reclaimedSlots > 0 || reclaimed.fullyReleased) return true;
            // Every package decode has drained at this point. If another
            // selector/LOD consumer still owns all slots, wait for that
            // generation to finish, then retry this unchanged reservation
            // once. Generation fencing prevents this waiter from clearing a
            // replacement pool's accounting.
            const released = await releaseSurfWorkers();
            syncSurfWorkerMemory();
            return released;
          },
          onMemoryLimitation: publishMemoryLimitation,
          // Revision replacement is a transaction: loaded component arrays
          // are accounted beside the current complete scene, but only the
          // final composition is published.
          publishIntermediate: !stageWholeReplacement,
          onRetainedChange: ({ loaded, failed = 0, total, retainedBytes }) => {
            if (requestId !== requestIdRef.current || controller.signal.aborted) return;
            if (stageWholeReplacement) {
              viewerMemoryPolicy.setRetained("replacementPending", retainedBytes);
              syncAssetCacheMemory();
            }
            // A component that failed on its own is settled too.
            const settled = loaded + failed;
            settledSoFar = settled;
            setMeshLoadProgress(settled === total
              ? {
                  phase: "view",
                  label: "Preparing view",
                  done: settled,
                  total,
                  determinate: true,
                }
              : progressiveLoadProgress(settled, total, undefined, { meshing }));
          },
          // The same staleness guard every publish below re-checks: the
          // request is current and not aborted.
          isCurrent: () => requestId === requestIdRef.current && !controller.signal.aborted,
          // The LOD working set is live from the first publish, so a level
          // swap that lands mid-load is composed from and kept by later
          // batches instead of being reverted to level 0.
          swappedComponents: () => (
            lodPackageRef.current?.requestId === requestId ? publishedLodContext(lodPackageRef.current).componentMeshDataByCid : null
          ),
          onPublish: ({ meshData, componentMeshDataByCid, loaded, total, final, publishCount, failures = [] }) => {
            if (final) viewerMemoryPolicy.clearLimitation();

            // window.__cadMeshCost for the headless memory harness; not React state.
            publishMeshCostAccounting({ meshData, componentMeshDataByCid, loaded, total, publishCount, final, meshRevision: getAssemblyMeshHash(entry) });
            const nextState = completedPackageMeshState(entry, meshData);
            // A partial model is structure-ready (the tree can show) but not
            // interaction-ready: the workspace keeps the "loading" overlay
            // with the per-batch count until the final publish flips it.
            nextState.assemblyInteractionReady = final;
            // The components that failed on their own are missing from the final model, and say
            // why as a load that stopped part-way does: its background error.
            if (final && failures.length) {
              nextState.assemblyBackgroundError = [...new Set(failures.map(({ error }) => (
                error instanceof Error ? error.message : String(error)
              )))].join("; ");
              nextState.assemblyBackgroundErrorMeshHash = targetMeshHash;
              // Named, the rest of the model drawn: the viewport warns rather than fails.
              nextState.assemblyFailedParts = failedPartNames(packageDescriptor, failures);
            }
            const ctx = lodPackageRef.current;
            const componentLodLevelByCid = Object.fromEntries(
              Object.entries(componentMeshDataByCid).map(([cid, componentMeshData]) => [
                cid,
                normalizeLodLevel(componentMeshData?.lodLevel),
              ]),
            );
            if (ctx && ctx.requestId === requestId) {
              const pending = ctx.lodPending;
              if (pending?.phase === "restoring") {
                ctx.componentMeshDataByCid = componentMeshDataByCid;
                ctx.componentLodLevelByCid = componentLodLevelByCid;
                ctx.meshData = meshData;
                pending.baseSource = meshData;
                pending.baseSources.add(meshData);
              } else if (pending) {
                // Preserve unrelated progressive arrivals in both views.
                pending.maps.componentMeshDataByCid = componentMeshDataByCid;
                pending.maps.componentLodLevelByCid = componentLodLevelByCid;
                pending.source = meshData;
                pending.candidateSources.add(meshData);
                ctx.componentMeshDataByCid = { ...componentMeshDataByCid };
                ctx.componentLodLevelByCid = { ...componentLodLevelByCid };
                for (const item of pending.items) {
                  ctx.componentMeshDataByCid[item.cid] = item.baseMesh;
                  ctx.componentLodLevelByCid[item.cid] = item.previousLevel;
                }
                pending.baseSource = buildComposedPackageMeshData(packageDescriptor,
                  ctx.componentMeshDataByCid, { previous: ctx.meshData });
                ctx.meshData = pending.baseSource;
                pending.baseSources.add(pending.baseSource);
              } else {
                ctx.componentMeshDataByCid = componentMeshDataByCid;
                ctx.meshData = meshData;
                ctx.componentLodLevelByCid = componentLodLevelByCid;
              }
              ctx.complete = final;
            } else {
              lodPackageRef.current = {
                entry: surfaceViewReplacement ? { ...entry, runtimeSurfaceViewReplacement: false } : entry,
                file: entry.file,
                meshUrl,
                descriptor: packageDescriptor,
                runtimeDescriptor: storedPackageDescriptor,
                componentIdentityByCid: Object.fromEntries(componentIdentityByCid),
                componentMeshDataByCid,
                meshData,
                componentLodLevelByCid,
                requestId,
                complete: final
              };
            }
            // A part that opened warm has no SURF URL until a refinement resolves its surface
            // (`resolveSurface`, which records the exact identity here). The loader never hears of
            // it, so this publish keeps each identity resolved since: reset to the loader's, the
            // refinement's payload no longer matched its own request and was dropped as aborted,
            // which the scheduler counts as a failed load -- the part left coarse, and a warm
            // reopen never reaching standard detail.
            const identities = Object.fromEntries(componentIdentityByCid);
            for (const [cid, identity] of Object.entries(lodPackageRef.current.componentIdentityByCid || {})) {
              if (identity?.surfUrl && !identities[cid]?.surfUrl) identities[cid] = identity;
            }
            lodPackageRef.current.componentIdentityByCid = identities;
            const publishedCtx = lodPackageRef.current;
            publishedCtx.publishCount = publishCount;
            publishedCtx.meshHash = nextState.meshHash;
            syncDisplayedMemory(publishedCtx.componentMeshDataByCid);
            if (final) {
              displayedLodPackageRef.current = publishedCtx;
              displayedReferenceCompositionRef.current = null;
            } else {
              displayedLodPackageRef.current = null;
              displayedReferenceCompositionRef.current = null;
            }
            if (!publishedOnce) {
              // First publish replaces whatever was showing (requestId is the
              // guard, as the single publish had). The camera frames once per
              // model key on this state, on the box the descriptor declares
              // (`declaredBounds`); without one it frames what arrived and
              // again on the last publish. The loader put the extreme-placed
              // components in the first batch, so what is drawn spans the model.
              publishedOnce = true;
              setMeshState(nextState);
              setStatus(ASSET_STATUS.READY);
              setError("");
              setFatalLoadFailure(null);
              // A partial model is on screen: a later failure attaches to it
              // as a background error rather than blanking the viewport.
              assemblyPreviewVisible = entry?.kind === "assembly";
            } else {
              // Later publishes swap the state in place under the same guard
              // the LOD swap uses: a state for another file is never replaced.
              setMeshState((current) => (
                !current || current.file !== entry.file ? current : nextState
              ));
            }
            // The LOD scheduler and memory accounting see the model as it
            // loads; the summary only lists components with bounds (loaded).
            setLodPackage(buildLodPackageSummary(entry, meshUrl, packageDescriptor,
              publishedCtx.componentMeshDataByCid, publishedCtx.componentIdentityByCid));
            if (final) {
              setMeshLoadProgress({
                phase: "view",
                label: "Preparing view",
                done: loaded,
                total,
                determinate: true,
              });
            }
            if (stageWholeReplacement && final) {
              viewerMemoryPolicy.setRetained("replacementPending", 0);
            }
          }
        });
        try {
          await loader.run();
        } finally {
          bodyBatches.dispose();
          surfaceTickets.dispose();
          // Nothing tessellates once the load ends — a later LOD refinement
          // builds a fresh pool — so the workers' isolates go back to the
          // process instead of holding the heap each grew for the largest
          // component it decoded. Also on the failure path: an aborted load
          // is exactly when the memory is most worth returning.
          releaseSurfWorkers().then(() => {
            syncSurfWorkerMemory();
          }).catch(() => {
            syncSurfWorkerMemory();
          });
        }
        return;
      }
      // Every STEP model is a component-GLB package (handled above). A missing/non-package
      // descriptor means the artifact is stale or was never built as a package.
      throw new Error(
        `STEP file ${entry.file || "(unknown)"} is not a component-GLB package; regenerate it to produce an assembly.json package.`
      );
    } catch (err) {
      if (requestId !== requestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      if (err instanceof SurfaceResolutionError && err.replacementView && !surfaceViewReplacement) {
        return surfaceViewReplacementRef.current?.(
          entry, entryAssetUrl(entry, "glb"), err.replacementView,
        );
      }
      if (entry?.kind === "assembly" && assemblyPreviewVisible) {
        const displayed = matchingDisplayedPackageContext(
          displayedLodPackageRef.current,
          meshStateRef.current,
          entry.file,
        );
        if (displayed) {
          lodPackageRef.current = displayed;
          setLodPackage(buildLodPackageSummary(
            displayed.entry,
            displayed.meshUrl,
            displayed.descriptor,
            displayed.componentMeshDataByCid,
            displayed.componentIdentityByCid,
          ));
          const displayedReferences = displayedReferenceCompositionRef.current;
          referenceCompositionRef.current = displayedReferences?.meshHash === displayed.meshHash
            ? displayedReferences
            : null;
        }
        setMeshState((current) => {
          if (!current || current.file !== entry.file || (!atomicSameFileReplacement && current.meshHash !== getAssemblyMeshHash(entry))) {
            return current;
          }
          return {
            ...current,
            assemblyBackgroundError: err instanceof Error ? err.message : String(err),
            assemblyBackgroundErrorMeshHash: targetMeshHash
          };
        });
        setStatus(ASSET_STATUS.READY);
        return;
      }
      setFatalLoadFailure({ file: String(entry?.file || "").trim(), hash: String(targetMeshHash || "") });
      setStatus(ASSET_STATUS.ERROR);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (requestId === requestIdRef.current) {
        setMeshLoadInProgress(false);
        setMeshLoadTargetFile("");
        setMeshLoadTargetHash("");
        setMeshLoadProgress(null);
      }
      if (meshAbortControllerRef.current === controller) {
        meshAbortControllerRef.current = null;
      }
    }
  }, [buildAssemblyPreviewMeshState, buildLodPackageSummary, cancelMeshLoad, entryHasMesh, getAssemblyMeshHash, getCachedMeshState,
    client, restoreCompletedPackage]);

  surfaceViewReplacementRef.current = (entry, meshUrl, replacementView) => {
    if (!replacementView?.viewId) return Promise.resolve();
    completedPackages.delete(client, entry);
    installRuntimePackageDescriptor(meshUrl, replacementView, { resources });
    if (lodPackageRef.current?.descriptor?.viewId === replacementView.viewId) {
      return Promise.resolve();
    }
    const active = surfaceViewReplacementTaskRef.current;
    if (active?.viewId === replacementView.viewId) return active.promise;
    // An old-view selector request must not publish after the replacement
    // begins. Saved geometry is untouched; this selection lives only in the
    // existing bounded descriptor cache for the current page.
    const task = (async () => {
      cancelReferenceLoad();
      referenceCompositionRef.current = null;
      displayedReferenceCompositionRef.current = null;
      setReferenceState(null);
      setReferenceStatus(REFERENCE_STATUS.PENDING);
      setReferenceError("");
      await loadMeshForEntry({ ...entry, runtimeSurfaceViewReplacement: true });
    })().finally(() => {
      if (surfaceViewReplacementTaskRef.current?.promise === task) {
        surfaceViewReplacementTaskRef.current = null;
      }
    });
    surfaceViewReplacementTaskRef.current = { viewId: replacementView.viewId, promise: task };
    return task;
  };

  // One topology batch: compose `requestedOccurrenceIds` (every part of the batch, loaded before
  // or not) and publish it, unless the session moved on. Resolves "published", "skipped" (no
  // longer wanted) or "stale" (the session was cancelled or superseded).
  const loadReferenceBatch = useCallback(async (session, requestedOccurrenceIds) => {
    const { entry, controller } = session;
    const isCurrent = () => session.requestId === referenceRequestIdRef.current && !controller.signal.aborted;
    const batchStart = perfStart();
    try {
      // Component-GLB package: there is no whole-assembly selector bundle. Compose the
      // per-component selector runtimes (each placed by its occurrence transform and namespaced
      // by occurrence id) so nested faces/edges become pickable.
      const glbUrl = entryAssetUrl(entry, "glb");
      const packageDescriptor = glbUrl
        ? await loadPackageDescriptor(glbUrl, { resources, signal: controller.signal })
        : null;
      if (!isCurrent()) return "stale";
      if (packageDescriptor && packageDescriptor.kind === "assembly-package") {
        // Lazy topology: an assembly loads selector topology only for the occurrences the user has
        // expanded in the tree (requestedOccurrenceIds), not every component. Loading all of them up
        // front made expanding one nested node fetch + compose the whole model's topology (regressed
        // in 8b12837d). A single-component part has no tree, so it loads its one component.
        // loadRenderSelectorBundle is cache-backed, so each new expansion only fetches the
        // newly-needed component; previously loaded ones are free.
        const isSingleComponentPart = String(entry?.kind || "").trim() === "part";
        const { occurrencesToLoad, neededCids, loadedTopologyKey } = selectRequestedAssemblyComponents(
          packageDescriptor,
          requestedOccurrenceIds,
          { singleComponentPart: isSingleComponentPart }
        );
        const lodCtx = publishedLodContext(lodPackageRef.current);
        const lodBundleByCid = (lodCtx && lodCtx.file === entry.file && lodCtx.componentLodBundleByCid) || {};
        const lodLevelByCid = (lodCtx && lodCtx.file === entry.file && lodCtx.componentLodLevelByCid) || {};
        const componentIdentityByCid = {
          ...((lodCtx && lodCtx.file === entry.file && lodCtx.componentIdentityByCid) || {}),
        };
        const unresolved = [];
        for (const cid of neededCids) {
          if (componentIdentityByCid[cid]?.surfaceObject
              && componentIdentityByCid[cid]?.selectorsUrl) continue;
          const component = packageDescriptor.components?.[cid];
          const staticUrl = component?.surf ? resolvePackageAssetUrl(glbUrl, component.surf, resources) : "";
          const staticSelectors = component?.selectors ? resolvePackageAssetUrl(glbUrl, component.selectors, resources) : "";
          if (component?.surfaceObject && staticUrl && staticSelectors) {
            componentIdentityByCid[cid] = Object.freeze({ ...component, surfUrl: staticUrl, selectorsUrl: staticSelectors });
          } else if (component) {
            unresolved.push({ cid, surfaceInput: component.surfaceInput,
              surfaceObject: component.surfaceObject });
          }
        }
        if (unresolved.length) {
          const resolved = await resolveSurfaceComponents(packageDescriptor, unresolved, { client,
            resources,
            signal: controller.signal,
          });
          for (const { cid } of unresolved) {
            componentIdentityByCid[cid] = Object.freeze({
              ...packageDescriptor.components[cid], ...resolved.get(cid),
            });
          }
          if (lodCtx?.descriptor === packageDescriptor) {
            lodCtx.componentIdentityByCid = { ...componentIdentityByCid };
          }
        }
        let componentBundleByCid = {};
        const componentBundleKeyByCid = {};
        const componentSurfUrlByCid = {};
        const tessellationForLevel = lodTessellationForLevel;
        // A part's selectors at `level`: cadgen's selector table joined to the mesh on screen. A
        // mesh the store does not hold -- a part still loading cold, or one the store let go -- is
        // cadgen's to make, as a refinement's is (`useViewportLod`): the surface request names that
        // level, and the read goes on with the mesh it answered.
        const loadSelectorBundle = async (cid, level) => {
          const read = (identity, mesh = null) => loadRenderSurfSelectorBundle(identity?.selectorsUrl || "", {
            resources, tessellationCache, signal: controller.signal, tessellation: tessellationForLevel(level),
            identity: mesh ? { ...identity, tessellationProbe: mesh } : identity,
          });
          try {
            return await read(componentIdentityByCid[cid]);
          } catch (error) {
            if (controller.signal.aborted || !isTessellationCacheProbeMissError(error)) throw error;
          }
          const component = packageDescriptor.components[cid];
          const resolved = await resolveSurfaceComponents(packageDescriptor, [{
            cid, surfaceInput: component.surfaceInput,
            surfaceObject: componentIdentityByCid[cid]?.surfaceObject || component.surfaceObject,
          }], { client, signal: controller.signal, tessellation: tessellationForLevel(level) });
          const { mesh = null, ...surface } = resolved.get(cid);
          const identity = Object.freeze({ ...component, ...surface });
          componentIdentityByCid[cid] = identity;
          componentSurfUrlByCid[cid] = identity.surfUrl || "";
          return read(identity, mesh);
        };
        await mapWithConcurrency(
          neededCids,
          componentSurfaceLoadConcurrency(),
          async (cid) => {
            const component = (packageDescriptor.components || {})[cid];
            if (!component) {
              return;
            }
            const identity = componentIdentityByCid[cid];
            const surfUrl = identity?.surfUrl || "";
            componentSurfUrlByCid[cid] = surfUrl;
            const initialLevel = normalizeLodLevel(lodLevelByCid[cid]);
            componentBundleKeyByCid[cid] = surfTessellationCacheKey(
              surfUrl,
              tessellationForLevel(initialLevel),
              identity
            );
            // A component the viewport already swapped to a finer LOD level must
            // compose picking from THAT level's bundle, not the level-0 cache —
            // the displayed triangles are the level's, and faceRuns are triangle
            // ranges of one specific tessellation.
            if (lodBundleByCid[cid]) {
              componentBundleByCid[cid] = lodBundleByCid[cid];
              return;
            }
            // A bundle this session already loaded for the same concrete tessellation (the
            // key names the surf, level and identity) is the one the cache would return: reuse
            // it, so a batch fetches only its new components, not every one it composes.
            const held = session.bundleByCid.get(cid);
            if (held && held.key === componentBundleKeyByCid[cid]) {
              componentBundleByCid[cid] = held.bundle;
              return;
            }
            // Exact topology: cadgen's selector table joined client-side to the component's mesh,
            // against the concrete level now on screen so triangle ranges remain exact. One that
            // cannot be joined leaves its parts unpublished.
            componentBundleByCid[cid] = await loadSelectorBundle(cid, initialLevel).catch(() => null);
            if (componentBundleByCid[cid]) session.bundleByCid.set(cid, { key: componentBundleKeyByCid[cid], bundle: componentBundleByCid[cid] });
          }
        );
        if (!isCurrent()) {
          return "stale";
        }
        const referencePublication = await reconcileLodReferencePublication({
          pendingForContext: () => lodPackageRef.current?.file === entry.file ? lodPackageRef.current.lodPending : null,
          loadBaseBundle: async pending => {
            const bundles = {};
            for (const item of pending.items) {
              const { cid } = item;
              if (!neededCids.includes(cid)) continue;
              const existing = pending.baseReferenceComposition?.bundleByCid?.[cid] || item.baseBundle;
              if (existing) { bundles[cid] = existing; continue; }
              const level = item.previousLevel;
              const bundle = await loadSelectorBundle(cid, level);
              if (lodPackageRef.current?.lodPending === pending) item.baseBundle = bundle;
              else releaseRenderSurfLevel(componentSurfUrlByCid[cid], {
                tessellation: tessellationForLevel(level), identity: componentIdentityByCid[cid],
              });
              bundles[cid] = bundle;
            }
            return bundles;
          },
          isCurrent,
          reconcile: () => reconcileLivePackageSelectorBundles({
          cids: neededCids,
          initialBundleByCid: componentBundleByCid,
          initialKeyByCid: componentBundleKeyByCid,
          snapshotLiveLod: () => {
            const live = publishedLodContext(lodPackageRef.current);
            if (!live || live.file !== entry.file) {
              return { levelByCid: lodLevelByCid, bundleByCid: {} };
            }
            const liveLevels = live.componentLodLevelByCid || {};
            const liveBundles = live.componentLodBundleByCid || {};
            const liveKeys = live.componentLodBundleKeyByCid || {};
            const exactBundles = {};
            for (const cid of neededCids) {
              const level = normalizeLodLevel(liveLevels[cid]);
              const component = componentIdentityByCid[cid];
              const expectedKey = surfTessellationCacheKey(
                componentSurfUrlByCid[cid],
                tessellationForLevel(level),
                component
              );
              if (liveKeys[cid] === expectedKey && liveBundles[cid]) {
                exactBundles[cid] = liveBundles[cid];
              }
            }
            return { levelByCid: liveLevels, bundleByCid: exactBundles };
          },
          keyForLevel: (cid, level) => surfTessellationCacheKey(
            componentSurfUrlByCid[cid],
            tessellationForLevel(level),
            componentIdentityByCid[cid]
          ),
          loadForLevel: (cid, level) => loadSelectorBundle(cid, level).catch(() => null),
          isCurrent
          }),
        });
        if (!referencePublication) return "stale";
        // A batch publishes only what is still requested (a part let go of while it loaded would
        // make the published topology unusable until the next batch), and never takes back a part
        // another batch published meanwhile: the next batch composes both.
        if (!session.accepts(requestedOccurrenceIds)) return "skipped";
        componentBundleByCid = referencePublication.bundles;
        // A part whose selectors could not be built is not published: the batch neither composes
        // it nor reports it loaded, and the next request asks for it again (`topologyRequests.js`).
        const failedIds = occurrencesToLoad
          .filter((occurrence) => !componentBundleByCid[String(occurrence?.component || "").trim()])
          .map((occurrence) => String(occurrence?.id || "").trim());
        const failed = new Set(failedIds);
        const composedOccurrences = occurrencesToLoad.filter((occurrence) => !failed.has(String(occurrence?.id || "").trim()));
        const publishedIds = requestedOccurrenceIds.filter((id) => !failed.has(String(id || "").trim()));
        const publishedTopologyKey = !failed.size ? loadedTopologyKey
          : isSingleComponentPart ? "" : [...new Set(publishedIds)].sort().join("|");
        const publishedTopologyIds = isSingleComponentPart ? null : publishedIds;
        // A single-component part renders as a topology tree (not an assembly structure), so its
        // topology must graft onto the synthetic part root via fallbackPartId — i.e. carry NO
        // partId (an occurrence-namespaced partId would orphan it). Multi-occurrence assemblies
        // DO namespace by occurrence so each leaf part owns its faces/edges. Both keep
        // remapOccurrenceId so picks align with the composed mesh's sourcePartRanges occurrence.
        const composer = referenceComposerRef.current.composer;
        const composeStart = perfStart();
        const composedRuntime = composePackageSelectorRuntime(entry, composedOccurrences, componentBundleByCid, {
          singleComponentPart: isSingleComponentPart,
          composer
        });
        const nextReferenceState = buildNormalizedReferenceState(entry, null, {
          selectorRuntime: composedRuntime,
          loadedTopologyKey: publishedTopologyKey,
          loadedTopologyIds: publishedTopologyIds
        });
        // Remembered so an LOD swap can re-compose this exact occurrence subset
        // with one component's bundle replaced (see prepareReferenceStateForLod).
        const nextComposition = {
          file: entry.file,
          meshHash: getAssemblyMeshHash(entry),
          entry,
          occurrencesToLoad: composedOccurrences,
          bundleByCid: componentBundleByCid,
          loadedTopologyKey: publishedTopologyKey,
          loadedTopologyIds: publishedTopologyIds,
          isSingleComponentPart
        };
        const livePending = referencePublication.pending;
        if (livePending) {
          const baseComposition = baseLodReferenceComposition(nextComposition, livePending, referencePublication.baseBundle);
          livePending.baseReferenceComposition = baseComposition;
          livePending.baseReferenceState = baseComposition === nextComposition ? nextReferenceState
            : buildNormalizedReferenceState(entry, null, {
              selectorRuntime: composePackageSelectorRuntime(entry, baseComposition.occurrencesToLoad,
                baseComposition.bundleByCid, { singleComponentPart: baseComposition.isSingleComponentPart, composer }),
              loadedTopologyKey: baseComposition.loadedTopologyKey,
              loadedTopologyIds: baseComposition.loadedTopologyIds,
            });
          if (livePending.phase !== "restoring") livePending.referenceComposition = nextComposition;
        } else referenceCompositionRef.current = nextComposition;
        const displayed = matchingDisplayedPackageContext(displayedLodPackageRef.current, meshStateRef.current, entry.file);
        if (!livePending && displayed?.meshHash === nextComposition.meshHash) displayedReferenceCompositionRef.current = nextComposition;
        setReferenceState(nextReferenceState);
        syncAssetCacheMemory();
        const previouslyPublished = new Set(session.published?.ids || []);
        session.publish(publishedIds, nextReferenceState, { failed: failedIds });
        perfMeasure(PERF_MEASURE_NAMES.topologyBatch, batchStart, {
          parts: requestedOccurrenceIds.length,
          added: publishedIds.filter((id) => !previouslyPublished.has(id)).length,
          requested: session.desired.length,
          composeMs: composeStart ? performance.now() - composeStart : 0
        });
        return "published";
      }

      const bundle = await loadRenderSelectorBundle(
        entrySelectorTopologyAssetUrl(entry),
        { resources, signal: controller.signal }
      );
      if (!isCurrent()) {
        return "stale";
      }
      const nextReferenceState = buildNormalizedReferenceState(entry, bundle);
      setReferenceState(nextReferenceState);
      syncAssetCacheMemory();
      // One whole-document bundle answers every request.
      session.publish(session.desired, nextReferenceState, { whole: true });
      return "published";
    } finally {
      // A first pick can be the last consumer of the tessellation pool.
      // Reclaim its isolates after all sibling loads drain, just like initial
      // display and LOD; a topology-only interaction must not pin eight heaps.
      releaseSurfWorkers().then(syncSurfWorkerMemory, syncSurfWorkerMemory);
    }
  }, [buildNormalizedReferenceState, getAssemblyMeshHash, resources]);

  const failReferenceSession = useCallback(async (session, err) => {
    if (session.requestId !== referenceRequestIdRef.current || session.controller.signal.aborted || isAbortError(err)) {
      return;
    }
    if (err instanceof SurfaceResolutionError && err.replacementView) {
      await surfaceViewReplacementRef.current?.(
        session.entry, entryAssetUrl(session.entry, "glb"), err.replacementView,
      );
      return;
    }
    session.failed = true;
    setReferenceStatus(REFERENCE_STATUS.ERROR);
    setReferenceError(err instanceof Error ? err.message : String(err));
    setReferenceLoadStage("");
  }, [resources]);

  // Ask for the topology of `requestedOccurrenceIds` (an assembly's parts; a part file's is
  // all of it). Idempotent and cheap to repeat: requests for the same file revision union into
  // one session that never aborts work in flight — only a different file or revision, or
  // cancelReferenceLoad, starts over. Already-loaded parts stay published while more load, and a
  // request that is already what is published changes nothing.
  const loadReferencesForEntry = useCallback((entry, requestedOccurrenceIds = []) => {
    if (!entryHasReferences(entry)) {
      cancelReferenceLoad();
      referenceCompositionRef.current = null;
      setReferenceState(null);
      setReferenceStatus(REFERENCE_STATUS.DISABLED);
      setReferenceError("");
      return Promise.resolve();
    }

    const key = `${String(entry?.file || "")}\u0000${entryReferenceAssetSignature(entry) || ""}\u0000${getAssemblyMeshHash(entry) || ""}\u0000${String(entry?.fileRefPrefix || "")}\u0000${String(entry?.kind || "")}`;
    let session = referenceSessionRef.current;
    const sessionCurrent = Boolean(session && session.key === key && session.loader === loadReferenceBatch && !session.failed
      && session.requestId === referenceRequestIdRef.current && !session.controller.signal.aborted);
    if (!sessionCurrent) {
      const cachedReferenceState = getCachedReferenceState(entry);
      if (cachedReferenceState) {
        cancelReferenceLoad();
        setReferenceState(cachedReferenceState);
        setReferenceStatus(cachedReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
        setReferenceError(cachedReferenceState.disabledReason || "");
        return Promise.resolve();
      }
      cancelReferenceLoad();
      if (referenceComposerRef.current.key !== key) {
        referenceComposerRef.current.composer.reset();
        referenceComposerRef.current.key = key;
      }
      // What this revision already has on screen carries over: a new session adds to it.
      const ctx = lodPackageRef.current;
      const live = (ctx?.file === entry.file && ctx?.lodPending?.referenceComposition) || referenceCompositionRef.current;
      const carried = live && live.file === entry.file && live.meshHash === getAssemblyMeshHash(entry)
        && Array.isArray(live.loadedTopologyIds) && referenceStateRef.current?.loadedTopologyKey === live.loadedTopologyKey
        ? { ids: [...live.loadedTopologyIds], state: referenceStateRef.current } : null;
      const requestId = referenceRequestIdRef.current;
      const controller = new AbortController();
      const isCurrent = () => requestId === referenceRequestIdRef.current && !controller.signal.aborted;
      let loopStart = 0;
      session = createTopologyRequestSession({
        published: carried,
        intervalMs: REFERENCE_BATCH_INTERVAL_MS,
        budget: REFERENCE_BATCH_NEW_PARTS,
        priorityBudget: REFERENCE_PRIORITY_NEW_PARTS,
        isCurrent,
        loadBatch: (ids) => loadReferenceBatch(session, ids),
        // An interval wait ends early when the session is cancelled.
        wait: (ms) => new Promise((resolve) => {
          const timer = setTimeout(resolve, ms);
          controller.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
        }),
        onLoading: () => {
          loopStart = perfStart();
          setReferenceStatus(REFERENCE_STATUS.LOADING);
          setReferenceError("");
          setReferenceLoadStage("loading topology");
        },
        onSettled: (state) => {
          setReferenceStatus(state?.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
          setReferenceError(state?.disabledReason || "");
          setReferenceLoadStage("");
          perfMeasure(PERF_MEASURE_NAMES.topologySettled, loopStart, { parts: session.desired.length, batches: session.batches });
        },
        onFailed: (err) => failReferenceSession(session, err)
      });
      Object.assign(session, { key, loader: loadReferenceBatch, requestId, controller, entry, bundleByCid: new Map() });
      referenceAbortControllerRef.current = controller;
      referenceSessionRef.current = session;
    }
    session.entry = entry;
    const request = session.request(requestedOccurrenceIds);
    if (request.settled) {
      // Already published (a request settling back, or a revision's topology carried into a new
      // session): the status says so, whatever an interrupted load left it at.
      const state = session.published?.state;
      setReferenceStatus(state?.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
      setReferenceError(state?.disabledReason || "");
      setReferenceLoadStage("");
    }
    return request.promise || Promise.resolve();
  }, [cancelReferenceLoad, entryHasReferences, failReferenceSession, getAssemblyMeshHash, getCachedReferenceState,
    loadReferenceBatch, resources]);

  useEffect(() => () => {
    abortLoad(meshAbortControllerRef);
    abortLoad(referenceAbortControllerRef);
    const displayed = displayedLodPackageRef.current;
    if (displayed) completedPackages.set(client, displayed.entry, displayed);
    syncAssetCacheMemory();
  }, [client, resources]);

  return {
    meshState,
    setMeshState,
    lodPackage,
    applyComponentLodBatch,
    prepareComponentLodPayload,
    onMeshSourceAdoption,
    componentLodNeedsSelectors,
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadTargetHash,
    meshLoadProgress,
    status,
    setStatus,
    error,
    setError,
    referenceState,
    setReferenceState,
    referenceStatus,
    setReferenceStatus,
    referenceError,
    setReferenceError,
    referenceLoadStage,
    getCachedMeshState,
    getCachedReferenceState,
    cancelMeshLoad,
    cancelReferenceLoad,
    loadMeshForEntry,
    fatalLoadFailure,
    clearFatalLoadFailure,
    loadReferencesForEntry
  };
}

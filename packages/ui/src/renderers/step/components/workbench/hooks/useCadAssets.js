import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  isAbortError,
  loadRenderSurf,
  loadRenderSelectorBundle,
  loadRenderSurfSelectorBundle,
  peekRenderGlb,
  peekRenderSelectorBundle,
  peekRenderTopologyIndex,
  releaseRenderSurfLevel,
  releaseSurfWorkers,
  surfTessellationCacheKey
} from "@hardcore/core/lib/renderAssetClient.js";
import {
  assemblyRootFromTopology,
  buildComposedPackageMeshData
} from "@hardcore/core/lib/assembly/meshData.js";
import {
  applySourceAppearance,
  validateSourceSidecar
} from "@hardcore/core/common/sourceSidecar.js";
import { mapWithConcurrency } from "@hardcore/core/lib/async/concurrency.js";
import {
  lodTessellationForLevel,
  normalizeLodLevel
} from "@hardcore/core/lib/surf/lodPolicy.js";
import {
  isTessellationCacheProbeMissError,
} from "@hardcore/core/lib/surf/tessellationCache.js";
import {
  installRuntimePackageDescriptor,
  loadPackageDescriptor,
  peekPackageDescriptor
} from "./packageDescriptorCache.js";
import {
  createProgressivePackageLoader,
  PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  progressiveLoadProgress,
  publishMeshCostAccounting,
  shouldRetainCompleteSameFileMesh
} from "./packageProgressiveLoad.js";
import { initialDisplayLodPlan, probeInitialDisplayLod } from "../../../render/initialDisplayLod.js";
import {
  matchingDisplayedPackageContext,
  retainedComponentMeshesForRevision
} from "./packageComponentReuse.js";
import { ASSET_STATUS, REFERENCE_STATUS } from "../../../workbench/constants.js";
import {
  entryAssetUrl,
  entryMeshAssetSignature,
  entrySelectorTopologyAssetUrl,
  entrySourceSidecarUrl,
  entryTopologyAssetUrl
} from "@hardcore/core/lib/entryAssets.js";
import { reclaimIdleSurfWorkers } from "@hardcore/core/lib/renderAssetClient.js";
import { estimateMeshRenderCost } from "@hardcore/core/lib/render/meshCost.js";
import {
  composePackageSelectorRuntime,
  compositionUsesComponent,
  baseLodReferenceComposition,
  reconcileLodReferencePublication,
  reconcileLivePackageSelectorBundles
} from "./packageReferenceComposition.js";
import { selectRequestedAssemblyComponents } from "../../../workbench/referenceSelection.js";
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

const GPU_BUFFER_ESTIMATE_MULTIPLIER = 1.15;
const SURF_WORKER_TEMP_ESTIMATE_MULTIPLIER = 2;

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

async function surfContentLength(url, signal, resources) {
  try { return await resources.byteLength(url, { signal }); }
  catch (error) {
    if (isAbortError(error) || signal?.aborted) throw error;
    return null;
  }
}

function resolvePackageAssetUrl(source, reference, resources) {
  return resources.resolveDependency(source, reference, { kind: "package" });
}

function runtimeComponentIdentity(context, cid) {
  return context?.componentIdentityByCid?.[cid] || context?.descriptor?.components?.[cid] || null;
}

function runtimeComponentSurfUrl(context, cid, resources) {
  const identity = runtimeComponentIdentity(context, cid);
  const component = context?.descriptor?.components?.[cid];
  return identity?.surfUrl
    || (component?.surf ? resolvePackageAssetUrl(entryAssetUrl(context.entry, "glb"), component.surf, resources) : "");
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
    assemblyBackgroundError: "", assemblyBackgroundErrorMeshHash: "",
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
      assemblyBackgroundErrorMeshHash: ""
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
  // The file and revision whose load failed outright; see shouldStartMeshLoad.
  const [fatalLoadFailure, setFatalLoadFailure] = useState(null);
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

  // --- viewport LOD (design/unified-tessellation.md Phase 5) -----------------
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
          identity,
          resolveSurface: async (signal) => {
            let resolved;
            try {
              resolved = await resolveSurfaceComponents(descriptor, [{
                cid, surfaceInput: identity.surfaceInput, surfaceObject: identity.surfaceObject,
              }], { client, signal });
            } catch (error) {
              if (error instanceof SurfaceResolutionError && error.replacementView) {
                surfaceViewReplacementRef.current?.(entry, meshUrl, error.replacementView);
              }
              throw error;
            }
            const nextIdentity = Object.freeze({ ...component, ...resolved.get(cid) });
            const context = lodPackageRef.current;
            if (context?.descriptor === descriptor) {
              context.componentIdentityByCid = {
                ...(context.componentIdentityByCid || {}), [cid]: nextIdentity,
              };
            }
            return { identity: nextIdentity, surfUrl: nextIdentity.surfUrl };
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
    const surfUrl = runtimeComponentSurfUrl(ctx, cid, resources);
    if (!matchesLodPayloadRequest(payload.lodRequest, ctx, cid, level, surfUrl)) throw abortError();
    if (payload.bundle || !componentLodNeedsSelectors(cid)) return payload;
    return loadRenderSurfSelectorBundle(surfUrl, { resources, tessellationCache,
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
      const surfUrl = runtimeComponentSurfUrl(ctx, cid, resources);
      if (!payload?.meshData || !matchesLodPayloadRequest(payload.lodRequest, ctx, cid, normalizedLevel, surfUrl)) return false;
      if (!payload.bundle && componentLodNeedsSelectors(cid)) return { status: "not-ready" };
      items.push({ cid, normalizedLevel, previousLevel: normalizeLodLevel(ctx.componentLodLevelByCid?.[cid]),
        component, surfUrl, payload, baseMesh: ctx.componentMeshDataByCid[cid],
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
    const nextState = completedPackageMeshState(ctx.entry, composed);
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
        const restoredState = completedPackageMeshState(ctx.entry, pending.baseSource);
        recoveryCommand.source = pending.baseSource;
        recoveryCommand.reference = pending.baseReferenceState;
        setMeshEnvelope(previous => updateLodMeshState(previous, current => (
          lodPackageRef.current === ctx && current?.file === ctx.file ? restoredState : current
        ), recoveryCommand));
        setError("Detail update failed; restoring the previous view.");
        return pending.baseSource;
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
      !current || current.file !== ctx.file || lodPackageRef.current !== ctx || signal?.aborted ? current : nextState
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
        { singleComponentPart: nextComposition.isSingleComponentPart }
      ),
      loadedTopologyKey: nextComposition.loadedTopologyKey
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
      setMeshState((current) => (
        current && current.file === ctx.file && !current.assemblyInteractionReady ? null : current
      ));
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
    setReferenceLoadStage("");
  }, [resources]);

  const loadMeshForEntry = useCallback(async (entry) => {
    const previousDisplayed = displayedLodPackageRef.current;
    if (previousDisplayed) completedPackages.set(client, previousDisplayed.entry, previousDisplayed);
    cancelMeshLoad();
    const requestId = requestIdRef.current;

    if (!entryHasMesh(entry)) {
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
      const sourceSidecarUrl = entrySourceSidecarUrl(entry);
      const inlineSourceSidecar = !entry?.editingPreview && entry?.sourceSidecar && typeof entry.sourceSidecar === "object"
        ? validateSourceSidecar(entry.sourceSidecar, {
            url: sourceSidecarUrl || entry?.file,
            documentHash: entry?.documentHash,
          })
        : null;
      const storedPackageDescriptor = await loadPackageDescriptor(meshUrl, { resources, signal: controller.signal });
      if (controller.signal.aborted) {
        throw abortError();
      }
      const packageDescriptor = storedPackageDescriptor
        ? applySourceAppearance(storedPackageDescriptor, inlineSourceSidecar?.appearance)
        : null;
      if (packageDescriptor && packageDescriptor.kind === "assembly-package") {
        // Progressive publish (design/viewer-memory.md §6): components are
        // fetched with bounded concurrency and the ones loaded so far are
        // re-composed and published per batch (packageProgressiveLoad.js owns
        // the batch policy), so the model paints while it loads and a cancel
        // frees what was never published. Composition is the reference-based
        // path applyComponentLodPayload uses for a level swap. The final
        // publish carries every component and is the state the single
        // post-load publish used to produce.
        let publishedOnce = false;
        const componentEntries = Object.entries(packageDescriptor.components || {});
        setMeshLoadProgress(progressiveLoadProgress(0, componentEntries.length));
        const defaultInitialPlan = initialDisplayLodPlan({
          componentCount: componentEntries.length,
          maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
        });
        const initialPlanByCid = new Map();
        // Runtime tickets bind the geometry descriptor's opaque D to the
        // concrete O selected by either a TESS v4 hit or surface resolution.
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
            }));
          }
        }
        const loader = createProgressivePackageLoader({
          descriptor: packageDescriptor,
          // Atomic same-file revisions keep the old complete composition on
          // screen while staging. Seed the new composer from that exact
          // predecessor so unchanged occurrence rows and tree branches can
          // cross the revision boundary. The request-local loader is the only
          // added owner; failure clears it and success drops it with the load.
          initialComposition: previousCompleteLodPackage?.meshData || null,
          concurrency: packageComponentLoadConcurrency(),
          // The local cap controls package concurrency. A single larger L0
          // leaf may run alone only if reserveLoad below can charge its full
          // worker estimate to the shared Viewer memory envelope.
          allowOversizedSingle: true,
          sourceExpansionRatio: (cid) => (
            initialPlanByCid.get(cid) || defaultInitialPlan
          ).sourceExpansionRatio,
          retainedComponent: (cid) => retainedComponentMeshByCid[cid] || null,
          retryCacheProbeMiss: isTessellationCacheProbeMissError,
          // Exact-surface artifact: tessellated client-side from the .surf
          // (design/surface-rendering.md). Same meshData contract as the
          // component GLB this replaced.
          loadComponent: async (cid, _component, { estimatedBytes, cacheProbe }) => {
            const componentPlan = initialPlanByCid.get(cid) || defaultInitialPlan;
            const identity = componentIdentityByCid.get(cid);
            if (!identity?.surfaceObject) {
              throw new Error(`Component ${cid} has no resolved surface identity`);
            }
            const meshData = await loadRenderSurf(
              identity.surfUrl || "",
              { resources, tessellationCache,
                      signal: controller.signal,
                tessellation: lodTessellationForLevel(componentPlan.level),
                identity: { ...identity, tessellationProbe: cacheProbe || null },
                memoryEstimateBytes: cacheProbe
                  ? estimatedBytes
                  : estimatedBytes * SURF_WORKER_TEMP_ESTIMATE_MULTIPLIER,
              },
            );
            meshData.lodLevel = componentPlan.level;
            return meshData;
          },
          // Byte-aware admission: the .surf's content-length (a HEAD, no body)
          // sizes the component before its decode is admitted; null when the
          // server does not answer, and the loader falls back to its running
          // mean.
          sizeHint: async (cid, component, {
            rejectedCacheObjects = new Set(),
            skipCacheProbes = false,
          } = {}) => {
            const surfaceInput = String(component?.surfaceInput || "");
            const cached = !skipCacheProbes && await probeInitialDisplayLod({ resources, tessellationCache,
              surfaceInput,
              surfaceObject: component.surfaceObject,
              maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
              signal: controller.signal,
              rejectedCacheObjects,
            });
            if (cached) {
              initialPlanByCid.set(cid, cached.plan);
              componentIdentityByCid.set(cid, Object.freeze({
                ...component,
                surfaceObject: cached.cacheProbe.surfaceObject,
                surfUrl: component.surf ? resolvePackageAssetUrl(meshUrl, component.surf, resources) : "",
              }));
              return { sourceBytes: null, cacheProbe: cached.cacheProbe };
            }

            let ticket;
            const staticUrl = component.surf ? resolvePackageAssetUrl(meshUrl, component.surf, resources) : "";
            if (component.surfaceObject && staticUrl) {
              ticket = {
                surfaceInput,
                surfaceObject: component.surfaceObject,
                surfUrl: staticUrl,
                byteLength: null,
              };
            } else {
              const resolved = await resolveSurfaceComponents(packageDescriptor, [{
                cid, surfaceInput, surfaceObject: component.surfaceObject,
              }], { client, signal: controller.signal });
              ticket = resolved.get(cid);
            }
            const hint = ticket.byteLength || await surfContentLength(ticket.surfUrl, controller.signal, resources);
            const plan = initialDisplayLodPlan({
              componentCount: componentEntries.length,
              surfBytes: hint,
              maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
            });
            initialPlanByCid.set(cid, plan);
            componentIdentityByCid.set(cid, Object.freeze({ ...component, ...ticket }));
            // A tier revised by the exact SURF size may already be warm.
            const revised = skipCacheProbes ? null : (await tessellationCache.probeCachedTessellationEntries(
                [surfaceInput], lodTessellationForLevel(plan.level), { resources, signal: controller.signal },
              )).get(surfaceInput) || null;
            if (revised && revised.surfaceObject === ticket.surfaceObject
                && !rejectedCacheObjects.has(revised.object)) {
              return { sourceBytes: hint, cacheProbe: revised };
            }
            return { sourceBytes: hint, cacheProbe: null };
          },
          reserveLoad: ({ cid, estimatedBytes, cacheProbe }) => viewerMemoryPolicy.reserve({
            category: "workerInFlight",
            bytes: cacheProbe ? estimatedBytes : estimatedBytes * SURF_WORKER_TEMP_ESTIMATE_MULTIPLIER,
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
          onRetainedChange: ({ loaded, total, retainedBytes }) => {
            if (requestId !== requestIdRef.current || controller.signal.aborted) return;
            if (stageWholeReplacement) {
              viewerMemoryPolicy.setRetained("replacementPending", retainedBytes);
              syncAssetCacheMemory();
            }
            setMeshLoadProgress(loaded === total
              ? {
                  phase: "view",
                  label: "Preparing view",
                  done: loaded,
                  total,
                  determinate: true,
                }
              : progressiveLoadProgress(loaded, total));
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
          onPublish: ({ meshData, componentMeshDataByCid, loaded, total, final, publishCount }) => {
            if (final) viewerMemoryPolicy.clearLimitation();

            // window.__cadMeshCost for the headless memory harness; not React state.
            publishMeshCostAccounting({ meshData, componentMeshDataByCid, loaded, total, publishCount, final, meshRevision: getAssemblyMeshHash(entry) });
            const nextState = completedPackageMeshState(entry, meshData);
            // A partial model is structure-ready (the tree can show) but not
            // interaction-ready: the workspace keeps the "loading" overlay
            // with the per-batch count until the final publish flips it.
            nextState.assemblyInteractionReady = final;
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
            lodPackageRef.current.componentIdentityByCid = Object.fromEntries(componentIdentityByCid);
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
              // model key on this state; the loader put the extreme-placed
              // components in the first batch so that frame spans the model.
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

  const loadReferencesForEntry = useCallback(async (entry, requestedOccurrenceIds = []) => {
    cancelReferenceLoad();
    const requestId = referenceRequestIdRef.current;

    if (!entryHasReferences(entry)) {
      referenceCompositionRef.current = null;
      setReferenceState(null);
      setReferenceStatus(REFERENCE_STATUS.DISABLED);
      setReferenceError("");
      return;
    }

    const cachedReferenceState = getCachedReferenceState(entry);
    if (cachedReferenceState) {
      setReferenceState(cachedReferenceState);
      setReferenceStatus(cachedReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
      setReferenceError(cachedReferenceState.disabledReason || "");
      return;
    }

    const controller = new AbortController();
    referenceAbortControllerRef.current = controller;
    setReferenceStatus(REFERENCE_STATUS.LOADING);
    setReferenceError("");
    setReferenceLoadStage("loading topology");

    try {
      // Component-GLB package: there is no whole-assembly selector bundle. Compose the
      // per-component selector runtimes (each placed by its occurrence transform and namespaced
      // by occurrence id) so nested faces/edges become pickable.
      const glbUrl = entryAssetUrl(entry, "glb");
      const packageDescriptor = glbUrl
        ? await loadPackageDescriptor(glbUrl, { resources, signal: controller.signal })
        : null;
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
              && componentIdentityByCid[cid]?.surfUrl) continue;
          const component = packageDescriptor.components?.[cid];
          const staticUrl = component?.surf ? resolvePackageAssetUrl(glbUrl, component.surf, resources) : "";
          if (component?.surfaceObject && staticUrl) {
            componentIdentityByCid[cid] = Object.freeze({ ...component, surfUrl: staticUrl });
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
            // Exact-surface topology (design/surface-rendering.md R3): the
            // selector bundle is synthesized client-side from the .surf.
            componentBundleByCid[cid] = await loadRenderSurfSelectorBundle(
              surfUrl,
              { resources, tessellationCache,
                      signal: controller.signal,
                // A missing optional bundle after a mesh-only LOD publish is
                // recoverable. Rebuild selectors against the concrete level
                // now on screen so triangle ranges remain exact.
                tessellation: tessellationForLevel(initialLevel),
                identity
              }
            ).catch(() => null);
          }
        );
        if (requestId !== referenceRequestIdRef.current) {
          return;
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
              const identity = componentIdentityByCid[cid];
              const level = item.previousLevel;
              const url = componentSurfUrlByCid[cid];
              const bundle = await loadRenderSurfSelectorBundle(url, { resources, tessellationCache,
                      signal: controller.signal, tessellation: tessellationForLevel(level), identity,
              });
              if (lodPackageRef.current?.lodPending === pending) item.baseBundle = bundle;
              else releaseRenderSurfLevel(url, { tessellation: tessellationForLevel(level), identity });
              bundles[cid] = bundle;
            }
            return bundles;
          },
          isCurrent: () => requestId === referenceRequestIdRef.current && !controller.signal.aborted,
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
          loadForLevel: (cid, level) => loadRenderSurfSelectorBundle(
            componentSurfUrlByCid[cid],
            { resources, tessellationCache,
                    signal: controller.signal,
              tessellation: tessellationForLevel(level),
              identity: componentIdentityByCid[cid]
            }
          ).catch(() => null),
          isCurrent: () => (
            requestId === referenceRequestIdRef.current && !controller.signal.aborted
          )
          }),
        });
        if (!referencePublication) return;
        componentBundleByCid = referencePublication.bundles;
        // A single-component part renders as a topology tree (not an assembly structure), so its
        // topology must graft onto the synthetic part root via fallbackPartId — i.e. carry NO
        // partId (an occurrence-namespaced partId would orphan it). Multi-occurrence assemblies
        // DO namespace by occurrence so each leaf part owns its faces/edges. Both keep
        // remapOccurrenceId so picks align with the composed mesh's sourcePartRanges occurrence.
        const composedRuntime = composePackageSelectorRuntime(entry, occurrencesToLoad, componentBundleByCid, {
          singleComponentPart: isSingleComponentPart
        });
        const nextReferenceState = buildNormalizedReferenceState(entry, null, {
          selectorRuntime: composedRuntime,
          loadedTopologyKey
        });
        // Remembered so an LOD swap can re-compose this exact occurrence subset
        // with one component's bundle replaced (see prepareReferenceStateForLod).
        const nextComposition = {
          file: entry.file,
          meshHash: getAssemblyMeshHash(entry),
          entry,
          occurrencesToLoad,
          bundleByCid: componentBundleByCid,
          loadedTopologyKey,
          isSingleComponentPart
        };
        const livePending = referencePublication.pending;
        if (livePending) {
          const baseComposition = baseLodReferenceComposition(nextComposition, livePending, referencePublication.baseBundle);
          livePending.baseReferenceComposition = baseComposition;
          livePending.baseReferenceState = baseComposition === nextComposition ? nextReferenceState
            : buildNormalizedReferenceState(entry, null, {
              selectorRuntime: composePackageSelectorRuntime(entry, baseComposition.occurrencesToLoad,
                baseComposition.bundleByCid, { singleComponentPart: baseComposition.isSingleComponentPart }),
              loadedTopologyKey: baseComposition.loadedTopologyKey,
            });
          if (livePending.phase !== "restoring") livePending.referenceComposition = nextComposition;
        } else referenceCompositionRef.current = nextComposition;
        const displayed = matchingDisplayedPackageContext(displayedLodPackageRef.current, meshStateRef.current, entry.file);
        if (!livePending && displayed?.meshHash === nextComposition.meshHash) displayedReferenceCompositionRef.current = nextComposition;
        setReferenceState(nextReferenceState);
        syncAssetCacheMemory();
        setReferenceStatus(nextReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
        setReferenceError(nextReferenceState.disabledReason || "");
        return;
      }

      const bundle = await loadRenderSelectorBundle(
        entrySelectorTopologyAssetUrl(entry),
        { resources, signal: controller.signal }
      );
      if (requestId !== referenceRequestIdRef.current) {
        return;
      }
      const nextReferenceState = buildNormalizedReferenceState(entry, bundle);
      setReferenceState(nextReferenceState);
      syncAssetCacheMemory();
      setReferenceStatus(nextReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
      setReferenceError(nextReferenceState.disabledReason || "");
    } catch (err) {
      if (requestId !== referenceRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      if (err instanceof SurfaceResolutionError && err.replacementView) {
        await surfaceViewReplacementRef.current?.(
          entry, entryAssetUrl(entry, "glb"), err.replacementView,
        );
        return;
      }
      setReferenceStatus(REFERENCE_STATUS.ERROR);
      setReferenceError(err instanceof Error ? err.message : String(err));
    } finally {
      if (referenceAbortControllerRef.current === controller) {
        referenceAbortControllerRef.current = null;
      }
      // A first pick can be the last consumer of the tessellation pool.
      // Reclaim its isolates after all sibling loads drain, just like initial
      // display and LOD; a topology-only interaction must not pin eight heaps.
      releaseSurfWorkers().then(syncSurfWorkerMemory, syncSurfWorkerMemory);
      if (requestId === referenceRequestIdRef.current) {
        setReferenceLoadStage("");
      }
    }
  }, [buildNormalizedReferenceState, cancelReferenceLoad, entryHasReferences, getAssemblyMeshHash, getCachedReferenceState, resources]);

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
    loadReferencesForEntry
  };
}

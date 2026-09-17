// React face of viewport LOD (design/unified-tessellation.md Phase 5).
//
// Owns a lodScheduler for the current package: camera-settle events sample
// the viewer (projection, viewport height, live distances to each unique
// component's nearest visible occurrence), the scheduler picks the worst offender,
// the level-keyed loader re-tessellates it in the surf worker pool, and the
// payload swaps in through useCadAssets' re-composition. Kill switch for
// debugging: `window.__CAD_VIEWER_LOD__ = false` before loading a model.
import { useCallback, useEffect, useRef } from "react";

import { loadRenderSurfPayloadAtLevel, reclaimIdleSurfWorkers, releaseSurfWorkers, releaseRenderSurfLevel, renderAssetCacheStats } from "@hardcore/core/lib/renderAssetClient.js";
import { estimateMeshRenderCost } from "@hardcore/core/lib/render/meshCost.js";
import { LOD_DEFAULT_LEVEL, lodTessellationForLevel } from "@hardcore/core/lib/surf/lodPolicy.js";
import { normalizeSceneQuality, resolveSceneQuality, SCENE_QUALITY } from "@hardcore/core/common/sceneSettings.js";

import { createLodScheduler } from "./lodScheduler.js";
import { syncSurfWorkerMemory } from "./surfWorkerMemoryPolicy.js";
import { viewerMemoryPolicy } from "./viewerMemoryPolicy.js";
import { estimateViewportLodMemory } from "./viewportLodMemory.js";
import { lodPayloadMemory, setLodStaging, lodStagingBuffers, lodStagingSnapshot, syncSelectorCacheAccounting } from "./lodStagingMemory.js";
import { lodPayloadRequest } from "./lodPayloadRequest.js";

// LOD runs after the model is already visible. Cached component reads are
// serialized through one loader lane. A long collection window becomes pure
// latency whenever the next decode cannot join the ready batch: a 918-component
// model accumulated 33 seconds in 128 ms windows while publishing mostly
// singletons. Keep the scheduler's bounded default so fast reads can still
// coalesce without delaying the common singleton path as heavily.
export const VIEWPORT_LOD_COLLECTION_MS = 32;

function publishLodMemoryLimitation(detail) {
  if (typeof window === "undefined") return;
  window.__cadViewerMemoryLimitation = detail;
  window.__cadViewerMemory = viewerMemoryPolicy.snapshot();
  window.dispatchEvent(new CustomEvent("cad:memory-limitation", { detail }));
}

/** Report blocked camera targets, without clearing another subsystem's limit. */
export function syncViewportLodLimitation(status, policy = viewerMemoryPolicy, publish = publishLodMemoryLimitation,
  publishedLimitation = typeof window !== "undefined" ? window.__cadViewerMemoryLimitation : null) {
  const targets = status?.disposed ? [] : (status?.unmetTargets || [])
    .filter(({ reason }) => reason === "memory-denied" || reason === "memory-pressure");
  if (targets.length) {
    const detail = { source: "viewportLod", preservingCurrentView: true, unmetTargets: targets };
    policy.noteLimitation(detail);
    publish(detail);
  } else if (policy.snapshot().lastLimitation?.source === "viewportLod" ||
      (!policy.snapshot().lastLimitation && publishedLimitation?.source === "viewportLod")) {
    policy.clearLimitation();
    publish(null);
  }
}

function lodEnabled() {
  return typeof window === "undefined" || window.__CAD_VIEWER_LOD__ !== false;
}

export function viewportLodMinimumLevel(target = typeof window !== "undefined" ? window : null) {
  return Number(target?.__CAD_VIEWER_MIN_LOD__ ?? LOD_DEFAULT_LEVEL);
}

export function dispatchViewportLodStatus(status, target = typeof window !== "undefined" ? window : null,
  EventClass = typeof CustomEvent !== "undefined" ? CustomEvent : null) {
  if (!target || !EventClass || !status) return;
  target.dispatchEvent(new EventClass("cad:lod-status", { detail: status }));
}

// Reuse the same screen-error scheduler and cache ladder. A finer quality
// target changes the camera sample's effective resolution, never the model
// identity or memory admission rules. Include it in camera intent so switching
// quality can retry a previously limited target once, without retrying on every
// geometry/accounting publication.
export function viewportLodSampleForQuality(sample, quality = SCENE_QUALITY.INTERACTIVE) {
  const policy = resolveSceneQuality(quality?.id || quality);
  return {
    ...sample,
    viewportHeightPx: sample.viewportHeightPx / policy.targetPixelError,
    ...(Object.hasOwn(sample, "cameraKey")
      ? { cameraKey: JSON.stringify([sample.cameraKey, policy.id]) }
      : {})
  };
}

export function useViewportLod({ viewerRef, lodPackage, modelKey = "", applyComponentLodBatch,
  prepareComponentLodPayload, componentLodNeedsSelectors, dynamicScene = false,
  quality = SCENE_QUALITY.INTERACTIVE, tessellationCache }) {
  const qualityId = normalizeSceneQuality(quality?.id || quality, { fallback: SCENE_QUALITY.INTERACTIVE });
  const sampledQualityRef = useRef(null);
  const componentsRef = useRef(new Map());
  const displayBuffersRef = useRef(new Set());
  const refreshDisplayBuffers = () => {
    const buffers = new Set();
    for (const component of componentsRef.current.values())
      for (const buffer of lodPayloadMemory({ meshData: component.meshData }).buffers) buffers.add(buffer);
    displayBuffersRef.current = buffers;
  };
  const applyRef = useRef(applyComponentLodBatch);
  applyRef.current = applyComponentLodBatch;
  const prepareRef = useRef(prepareComponentLodPayload);
  prepareRef.current = prepareComponentLodPayload;
  const selectorsRef = useRef(componentLodNeedsSelectors);
  selectorsRef.current = componentLodNeedsSelectors;
  const schedulerRef = useRef(null);
  const visibilityRef = useRef(null);
  const lodPackageFileRef = useRef("");
  const lodPackageModelKeyRef = useRef("");

  useEffect(() => {
    const stagingOwner = Symbol("viewport-lod");
    let stagedPayloads = [];
    const syncStaging = entries => {
      const payloads = entries.map(entry => entry.payload).filter(Boolean);
      if (payloads.length === stagedPayloads.length && payloads.every((payload, i) => payload === stagedPayloads[i])) return;
      stagedPayloads = payloads;
      setLodStaging(stagingOwner, entries);
      const caches = renderAssetCacheStats({ excludeBuffers: lodStagingBuffers(displayBuffersRef.current) });
      syncSelectorCacheAccounting(viewerMemoryPolicy, Number(caches.selector?.typedBytes) || 0);
      viewerMemoryPolicy.setRetained("assetCaches", Object.entries(caches).reduce((sum, [name, stats]) =>
        name === "surfLeash" || name === "selector" ? sum : sum + (Number(stats?.typedBytes) || 0), 0));
    };
    let scheduler = null;
    const snapshot = () => ({ file: lodPackageFileRef.current, modelKey: lodPackageModelKeyRef.current,
      ...scheduler.snapshot(),
      staging: lodStagingSnapshot(), visibility: visibilityRef.current, quality: sampledQualityRef.current });
    const publishStatus = () => {
      if (!scheduler || schedulerRef.current !== scheduler) return;
      dispatchViewportLodStatus(snapshot());
    };
    scheduler = createLodScheduler({
      batchSize: typeof window !== "undefined" ? Number(window.__CAD_VIEWER_LOD_BATCH_SIZE__ || 4) : 4,
      collectionMs: VIEWPORT_LOD_COLLECTION_MS,
      onOccupiedChanged: entries => { syncStaging(entries); publishStatus(); },
      needsPreparation: (cid, _level, payload) => !payload?.bundle && selectorsRef.current?.(cid) === true,
      prepareLevel: (cid, level, payload, options) => prepareRef.current?.(cid, level, payload, options) || payload,
      reconcileLevel: ({ payload, reservedBytes, currentLevel, level }) => {
        const { cpuBytes, gpuInputBytes } = lodPayloadMemory(payload);
        const previousBytes = estimateMeshRenderCost(payload.lodRequest.baseMesh).typedArrayBytes;
        const required = Math.ceil(cpuBytes + gpuInputBytes * 1.5 + previousBytes * 2.5);
        if (required <= reservedBytes) return { ok: true };
        return viewerMemoryPolicy.reserve({ category: "replacement", bytes: required - reservedBytes,
          label: `${payload.lodRequest.cid}:staged`, kind: level < currentLevel ? "coarsen" : "refine",
          replacingBytes: previousBytes, finalBytes: gpuInputBytes, recordLimitation: false });
      },
      discardLevel: (_cid, level, payload) => {
        const request = payload.lodRequest;
        if (request) releaseRenderSurfLevel(request.url, { tessellation: lodTessellationForLevel(level), identity: request.identity });
      },
      onAdopted: entries => {
        if (typeof window !== "undefined") for (const { cid, level } of entries)
          window.dispatchEvent(new CustomEvent("cad:lod-level", { detail: { cid, level } }));
      },
      // The coarse assembly mesh is only a first-paint preview. The settled
      // viewport floor is the canonical default; the debug override can still
      // exercise lower/higher rungs without changing cache or export identity.
      minimumLevel: viewportLodMinimumLevel(),
      reserveLevel: ({ cid, currentLevel, level, direction }) => {
        const component = componentsRef.current.get(cid);
        const { currentBytes, nextMeshBytes, admissionBytes } = estimateViewportLodMemory({
          meshBytes: component?.meshBytes,
          currentLevel,
          level,
        });
        const request = {
          category: "replacement",
          bytes: admissionBytes,
          label: `${cid}@L${level}`,
          kind: direction,
          replacingBytes: currentBytes,
          finalBytes: nextMeshBytes,
        };
        const reservation = viewerMemoryPolicy.reserve({ ...request, recordLimitation: false });
        if (reservation.ok) return reservation;
        reclaimIdleSurfWorkers();
        syncSurfWorkerMemory();
        return viewerMemoryPolicy.reserve({ ...request, recordLimitation: false });
      },
      releaseLevel: (token) => viewerMemoryPolicy.release(token),
      memoryPressure: () => {
        const memory = viewerMemoryPolicy.snapshot();
        return memory.availableBytes < memory.ownedLimitBytes * 0.15;
      },
      onLimitation: (detail) => {
        const owned = { ...detail, source: "viewportLod" };
        viewerMemoryPolicy.noteLimitation(owned);
        publishLodMemoryLimitation(owned);
      },
      onIdle: (status) => {
        syncViewportLodLimitation(status);
        publishStatus();
        releaseSurfWorkers().then(syncSurfWorkerMemory, syncSurfWorkerMemory);
      },
      loadLevel: (cid, level, { signal }) => {
        const component = componentsRef.current.get(cid);
        if (!component) {
          return Promise.reject(new Error(`unknown LOD component ${cid}`));
        }
        const { workerTemporaryBytes } = estimateViewportLodMemory({
          meshBytes: component.meshBytes,
          currentLevel: component.level,
          level,
        });
        const load = () => {
          const request = lodPayloadRequest(component, level);
          return loadRenderSurfPayloadAtLevel(component.surfUrl, {
            signal, tessellationCache,
            tessellation: lodTessellationForLevel(level),
            identity: component.identity,
            selectors: selectorsRef.current?.(cid) === true,
            memoryEstimateBytes: workerTemporaryBytes,
          }).then(payload => ({ ...payload, lodRequest: request }));
        };
        return load().catch(async error => {
          if (signal.aborted || component.surfUrl || typeof component.resolveSurface !== "function") throw error;
          const resolved = await component.resolveSurface(signal);
          component.identity = resolved.identity;
          component.surfUrl = resolved.surfUrl;
          return load();
        }).finally(() => {
          syncSurfWorkerMemory();
        });
      },
      applyBatch: async (entries, { signal }) => {
        const outcome = await applyRef.current?.(entries, { signal });
        if (outcome?.status === "scene-failed" || outcome?.status === "not-ready" || outcome?.status === "retained") return outcome;
        if (outcome === false || signal.aborted) return false;
        // All measured current bytes change together, after exact scene
        // acknowledgment, before the scheduler commits levels and notifies.
        for (const adopted of outcome?.components || []) {
          const component = componentsRef.current.get(adopted.cid);
          const request = entries.find(entry => entry.cid === adopted.cid)?.payload.lodRequest;
          if (component && component.descriptor === request?.descriptor) {
            component.meshBytes = estimateMeshRenderCost(adopted.meshData).typedArrayBytes;
            component.meshData = adopted.meshData;
            component.level = adopted.level;
          }
        }
        refreshDisplayBuffers();
        return outcome;
      }
    });
    schedulerRef.current = scheduler;
    if (typeof window !== "undefined") window.__cadViewportLod = snapshot;
    return () => {
      scheduler.dispose();
      schedulerRef.current = null;
      if (typeof window !== "undefined" && window.__cadViewportLod === snapshot) delete window.__cadViewportLod;
    };
  }, [tessellationCache]);

  // The package summary is republished per progressive-load batch (useCadAssets),
  // so the same file arriving again means the model GREW: keep the levels
  // already applied. A different file (or null between loads) is a reset.
  useEffect(() => {
    const components = lodEnabled() ? lodPackage?.components || [] : [];
    const file = String(lodPackage?.file || "");
    // A new catalog revision can arrive while its predecessor remains on
    // screen. Identity belongs to the adopted package, never to that request.
    const nextModelKey = String(lodPackage?.modelKey || modelKey || file);
    const preserveLevels = !!file && file === lodPackageFileRef.current &&
      nextModelKey === lodPackageModelKeyRef.current;
    lodPackageFileRef.current = file;
    lodPackageModelKeyRef.current = nextModelKey;
    visibilityRef.current = null;
    if (!preserveLevels) sampledQualityRef.current = null;
    componentsRef.current = new Map(components.map((component) => [component.cid, component]));
    refreshDisplayBuffers();
    schedulerRef.current?.setComponents(
      components.map(({ cid, diagonal, level }) => ({ cid, diagonal, level })),
      { preserveLevels }
    );
    if (typeof window !== "undefined") dispatchViewportLodStatus(window.__cadViewportLod?.());
  }, [lodPackage, modelKey]);

  // One numeric distance map per camera/summary/capability change. The sampler
  // checks whole occurrence bounds, never just centers or material visibility.
  // The scheduler owns the debounce and does not rescan records per component.
  const onCameraMoved = useCallback(() => {
    if (!componentsRef.current.size) {
      return;
    }
    const sampler = viewerRef.current?.sampleLodCamera?.({ components: componentsRef.current, dynamicScene });
    if (!sampler) {
      return;
    }
    visibilityRef.current = sampler.visibility;
    sampledQualityRef.current = qualityId;
    const changed = schedulerRef.current?.onCameraSample(viewportLodSampleForQuality(sampler, qualityId));
    // A sample that changed nothing leaves an identical snapshot behind.
    // Publishing it anyway turns every host resample into React state, whose
    // render re-runs the effects that resample: an idle viewport would never
    // stop sampling itself. Real transitions still publish — through this
    // sample when it changes something, and through onIdle/onOccupiedChanged.
    if (changed === false) return;
    if (typeof window !== "undefined") dispatchViewportLodStatus(window.__cadViewportLod?.());
  }, [viewerRef, dynamicScene, qualityId]);

  // Initial framing can notify before the package summary reaches this hook.
  // Sample once after installing the summary too: otherwise a stationary
  // camera leaves a newly published model coarse until the user moves it.
  useEffect(() => { onCameraMoved(); }, [lodPackage, onCameraMoved]);

  return { onCameraMoved };
}

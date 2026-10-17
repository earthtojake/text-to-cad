import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  isAbortError,
  loadRenderPart,
  loadRenderPartSelectorBundle,
  partCacheKey,
  peekRenderPart,
  prewarmPartWorkers,
  releasePartWorkers
} from "@text-to-cad/core/lib/renderAssetClient.js";
import { applyOccurrenceDisplay } from "@text-to-cad/core/lib/assembly/meshData.js";
import { mapWithConcurrency } from "@text-to-cad/core/lib/async/concurrency.js";
import { viewerOriginUrl } from "@text-to-cad/core/client";
import {
  isTessellationCacheProbeMissError,
  partSelectorsPath,
} from "@text-to-cad/core/lib/parts/tessellationCache.js";
import {
  installRuntimePackageDescriptor,
  loadPackageDescriptor,
  peekPackageDescriptor
} from "./packageDescriptorCache.js";
import {
  createProgressivePackageLoader,
  orderComponentsForProgressiveLoad,
  progressiveLoadProgress,
  publishMeshCostAccounting,
  awaitingSameFileRevision,
  meshStateAfterCancelledLoad,
  shouldRetainCompleteSameFileMesh
} from "./packageProgressiveLoad.js";
import {
  createInitialDisplayPlans, probeInitialDisplay, producedDisplayPlan,
} from "../../../render/initialDisplay.js";
import { createPartTicketBatches, createTessellationBodyBatches } from "./packageBatchReads.js";
import {
  matchingDisplayedPackageContext,
  retainedComponentsForRevision
} from "./packageComponentReuse.js";
import { ASSET_STATUS, REFERENCE_STATUS } from "../../../workbench/constants.js";
import {
  entryAssetUrl,
  entryMeshAssetSignature,
  entryReferenceAssetSignature
} from "@text-to-cad/core/lib/entryAssets.js";
import { reclaimIdlePartWorkers } from "@text-to-cad/core/lib/renderAssetClient.js";
import { PERF_MEASURE_NAMES, perfMeasure, perfStart } from "@text-to-cad/core/lib/viewer/perfMarks.js";
import {
  composePackageSelectorRuntime,
  createPackageReferenceComposer,
} from "./packageReferenceComposition.js";
import { selectRequestedAssemblyComponents } from "../../../workbench/referenceSelection.js";
import { createTopologyRequestSession } from "./topologyRequests.js";
import { viewerMemoryPolicy } from "../../../render/viewerMemoryPolicy.js";
import { syncPartWorkerMemory } from "../../../render/partWorkerMemoryPolicy.js";
import { componentMemoryAccounting, syncSelectorCacheAccounting } from "../../../render/renderMemoryAccounting.js";
import { completedPackages, renderAssetCacheStatsWithPackages } from "../../../render/completedPackageCache.js";
import {
  resolveParts,
  PartResolutionError,
} from "../../../workbench/partResolution.js";
// Only the STEP renderer mounts this hook, and it is only ever handed STEPs (its `matches`
// excludes every other format by extension). So where this used to ask whether an entry
// was a STEP, it asks whether there is one: the same answer for every input it receives.

// A package's parts are fetched and decoded off the main thread, so the
// cap only bounds sockets and the worker's queue.
const COMPONENT_PART_LOAD_CONCURRENCY = 8;

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
  const caches = renderAssetCacheStatsWithPackages({ excludeBuffers });
  syncSelectorCacheAccounting(viewerMemoryPolicy, Number(caches.selector?.typedBytes) || 0);
  const assetCaches = Object.entries(caches).reduce((sum, [name, stats]) => (
    name === "partLeash" || name === "selector" ? sum : sum + (Number(stats?.typedBytes) || 0) + (Number(stats?.metadataBytes) || 0)
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

function componentPartLoadConcurrency() {
  const hardwareConcurrency = typeof navigator !== "undefined"
    ? Number(navigator.hardwareConcurrency)
    : 0;
  if (!Number.isFinite(hardwareConcurrency) || hardwareConcurrency <= 0) {
    return COMPONENT_PART_LOAD_CONCURRENCY;
  }
  // Bounded by cores because the worker still parses serially; going wider only queues.
  return Math.max(2, Math.min(COMPONENT_PART_LOAD_CONCURRENCY, hardwareConcurrency));
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

function completedPackageMeshState(entry, meshData) {
  return {
    file: entry.file, kind: entry.kind, meshHash: entryMeshAssetSignature(entry), meshData,
    assemblyStructureReady: true, assemblyInteractionReady: true,
    assemblyBackgroundError: "", assemblyBackgroundErrorMeshHash: "", assemblyFailedParts: [],
    assemblyUnmeshedParts: [],
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

// The parts whose component mesh names faces no mesher could cover (`unmeshedFaces`), drawn
// without them, by the names the tree gives them: the model is whole but for those faces, and the
// viewport says so.
function namedPartNames(descriptor, componentMeshDataByCid, named) {
  const short = new Set(Object.entries(componentMeshDataByCid || {})
    .filter(([, meshData]) => meshData?.[named]?.length).map(([cid]) => cid));
  const names = [];
  for (const occurrence of short.size ? descriptor?.occurrences || [] : []) {
    if (!short.has(String(occurrence?.component || ""))) continue;
    const name = String(occurrence?.name || occurrence?.id || occurrence?.component).trim();
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

// `previewGate` holds (`.current`) the parts gate of the build feed's preview revision on screen
// (`usePreviewRevision`): a preview entry's load waits on it for the parts the build is still
// deriving, and draws what is named meanwhile; null, or another tree's, for every other load.
export function useCadAssets({
  initialEntry = null,
  client,
  tessellationCache,
  entryHasMesh,
  entryHasReferences,
  buildNormalizedReferenceState,
  previewGate = null,
}) {
  const resources = client?.resources;
  if (!resources) throw new TypeError("CAD rendering requires CAD resources");
  const getAssemblyMeshHash = useCallback((entry) => {
    return entryMeshAssetSignature(entry);
  }, [resources]);

  // Complete STEP packages may exceed the per-component part LRU. Reuse their
  // bounded CPU working set, with fresh occurrence metadata for this mount.
  const restoreCompletedPackage = useCallback(entry => entryHasMesh(entry)
    ? completedPackages.get(client, entry, { descriptor: peekPackageDescriptor(entryAssetUrl(entry, "glb"), { resources }) })
    : null, [client, entryHasMesh]);

  // FileViewer remounts file-owned controls. Restore immutable warm assets on
  // the first render, as main's in-place tab activation did, without retaining
  // inactive scenes or copying component buffers.
  const initialPackageRef = useRef(undefined);
  if (initialPackageRef.current === undefined) initialPackageRef.current = restoreCompletedPackage(initialEntry);
  const initialPackage = initialPackageRef.current;
  const [meshState, setMeshState] = useState(() => (
    initialPackage ? completedPackageMeshState(initialEntry, initialPackage.meshData) : null
  ));
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
  const [referenceState, setReferenceState] = useState(null);
  const referenceStateRef = useRef(referenceState);
  referenceStateRef.current = referenceState;
  const [referenceStatus, setReferenceStatus] = useState(REFERENCE_STATUS.IDLE);
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

  // The package being loaded or shown: its descriptor, each component's mesh and part
  // identity, and the composition of them on screen. Topology composes from it, a same-file
  // revision reuses its unchanged components, and a closed tab keeps it (`completedPackages`).
  const packageRef = useRef(initialPackage);
  // Only the complete package whose meshState is actually displayed. Keeping it separate from
  // packageRef lets A survive a failed or cancelled B and seed C without letting B take its place.
  const displayedPackageRef = useRef(initialPackage);
  // The composed reference state's ingredients: the lazily-loaded occurrence subset and the
  // selector bundle each component's topology was built from, so a new topology session for the
  // same revision carries over what is on screen.
  const referenceCompositionRef = useRef(null);
  const displayedReferenceCompositionRef = useRef(null);
  const viewReplacementRef = useRef(null);
  const viewReplacementTaskRef = useRef(null);

  useLayoutEffect(() => {
    if (!initialPackage) return;
    initialPackageRef.current = null;
    const count = Object.keys(initialPackage.componentMeshDataByCid).length;
    publishMeshCostAccounting({ ...initialPackage, loaded: count, total: count, final: true, meshRevision: initialPackage.meshHash });
    syncDisplayedMemory(initialPackage.componentMeshDataByCid);
  }, [initialPackage, resources]);

  const cancelMeshLoad = useCallback(() => {
    requestIdRef.current += 1;
    abortLoad(meshAbortControllerRef);
    publishMeshCostAccounting(null);
    viewerMemoryPolicy.setRetained("replacementPending", 0);
    // A load cancelled mid-way leaves a PARTIAL composition published; drop it
    // so the component arrays it references can go. A complete model stays (it
    // is still the right thing to show).
    const ctx = packageRef.current;
    if (ctx && ctx.complete === false) {
      packageRef.current = null;
      setMeshState((current) => meshStateAfterCancelledLoad(current, ctx.file));
      syncDisplayedMemory(null);
    }
    const displayed = matchingDisplayedPackageContext(
      displayedPackageRef.current,
      meshStateRef.current,
      meshStateRef.current?.file,
    );
    if (displayed) {
      packageRef.current = displayed;
      const displayedReferences = displayedReferenceCompositionRef.current;
      referenceCompositionRef.current = displayedReferences?.meshHash === displayed.meshHash
        ? displayedReferences
        : null;
    }
    setMeshLoadInProgress(false);
    setMeshLoadTargetFile("");
    setMeshLoadTargetHash("");
    setMeshLoadProgress(null);
  }, [resources]);

  const cancelReferenceLoad = useCallback(() => {
    referenceRequestIdRef.current += 1;
    abortLoad(referenceAbortControllerRef);
    referenceSessionRef.current = null;
    setReferenceLoadStage("");
  }, [resources]);

  const loadMeshForEntry = useCallback(async (entry) => {
    const previousDisplayed = displayedPackageRef.current;
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
      displayedPackageRef.current = null;
      displayedReferenceCompositionRef.current = null;
      syncDisplayedMemory(null);
      setMeshState(null);
      setStatus(ASSET_STATUS.PENDING);
      setError("");
      return;
    }

    const viewReplacement = entry?.runtimeViewReplacement === true;
    // A preview revision's load (STORE.md 9b): its parts are the saved file's, by key, and the ones
    // its build has not derived yet are waited for, never asked of cadgen.
    const gate = entry?.preview === true && previewGate?.current?.tree === String(entry?.hash || "") ? previewGate.current : null;
    const targetMeshHash = getAssemblyMeshHash(entry);
    const completed = viewReplacement ? null : restoreCompletedPackage(entry);
    syncAssetCacheMemory(componentMemoryAccounting(previousDisplayed?.componentMeshDataByCid).buffers);
    if (completed) {
      completed.requestId = requestId;
      packageRef.current = completed;
      displayedPackageRef.current = completed;
      displayedReferenceCompositionRef.current = null;
      referenceCompositionRef.current = null;
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
    const previousCompletePackage = atomicSameFileReplacement
      ? matchingDisplayedPackageContext(displayedPackageRef.current, meshStateRef.current, entry.file)
      : null;

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
    // Any new load invalidates the previous entry's working set. A complete
    // same-file scene can remain rendered while its replacement is decoded,
    // until the atomic commit.
    packageRef.current = null;
    referenceCompositionRef.current = null;
    // A same-file replacement publishes whole, never a batch at a time. The old model stays until
    // the new one is whole -- unless the new one's parts are still coming: a preview whose build
    // is deriving them is drawn as they are named (`loader.publishPending`, below).
    const sameFileReplacement = atomicSameFileReplacement || viewReplacement;
    const stageWholeReplacement = sameFileReplacement && !(gate && !gate.complete);
    const keepRenderedAssemblyVisible = entry?.kind === "assembly" && (
      atomicSameFileReplacement || (viewReplacement && meshStateRef.current?.file === entry.file)
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
        // Progressive publish (packages/ui/docs/loading.md, section 2): components
        // are fetched with bounded concurrency and the ones loaded so far are
        // re-composed and published per batch (packageProgressiveLoad.js owns
        // the batch policy), so the model paints while it loads and a cancel
        // frees what was never published. The final publish carries every
        // component.
        let publishedOnce = false;
        const componentEntries = Object.entries(packageDescriptor.components || {});
        // Whether cadgen is meshing any part this open asked for (its store lacked it), and the
        // parts settled so far: the frame says "Meshing parts" from the first pending answer on.
        let meshing = false;
        let settledSoFar = 0;
        setMeshLoadProgress(progressiveLoadProgress(0, componentEntries.length));
        // Each component's part row: the record its mesh was drawn from, by a stored part's probe
        // or the request that derived it. It never rewrites the canonical descriptor.
        const componentIdentityByCid = new Map();
        // A same-file revision keeps every component whose part is already drawn, by the part's
        // key: its mesh and the row it was drawn from, whatever id the new tree gives it.
        const retainedByCid = retainedComponentsForRevision({
          previous: previousCompletePackage,
          descriptor: packageDescriptor,
          meshUrl,
        });
        for (const [cid, { row }] of Object.entries(retainedByCid)) componentIdentityByCid.set(cid, row);
        // One request for many components where a lane made one each (`packageBatchReads.js`):
        // their initial tiers, probed a chunk at a time; the warm ones' bodies, read a batch at a
        // time; the cold ones' parts, resolved up to a request's bound at a time. Each
        // follows the order the lanes load in. A same-file revision's retained components read nothing.
        const readOrder = orderComponentsForProgressiveLoad(packageDescriptor)
          .filter(([cid]) => !retainedByCid[cid]);
        const readCids = readOrder.map(([cid]) => cid);
        // A warm load's isolates start once its first probe shows warm bodies, while the first batch
        // is on the wire: a batch hands its bodies over at once, and they would all start only then.
        // A cold load's start as its parts come (measured: started earlier, they finish later).
        let prewarmed = false;
        const prewarmForBatches = () => {
          if (prewarmed) return;
          prewarmed = true;
          prewarmPartWorkers(Math.min(readCids.length, packageComponentLoadConcurrency()));
        };
        // Every component is drawn from its part's one display mesh. A cold part is derived in the
        // request that answers with its record, and nothing is tessellated here.
        // The first geometry waits on the first chunk's probe and the first batch's read: nothing
        // is read ahead of them until a lane is past its body read.
        let firstBodyRead;
        const pastFirstBodyRead = new Promise((resolve) => { firstBodyRead = resolve; });
        const initialPlans = createInitialDisplayPlans({
          components: readOrder,
          signal: controller.signal,
          readAheadAfter: pastFirstBodyRead,
          probeEntries: (parts, options) => tessellationCache.probeCachedTessellationEntries(parts, options),
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
          skip: (cid, row) => Boolean(peekRenderPart(row)),
          signal: controller.signal,
        });
        const partTickets = createPartTicketBatches({
          order: readCids,
          needs: (cid) => {
            const planned = initialPlans.peek(cid);
            if (planned === undefined) return undefined;
            return !planned ? packageDescriptor.components[cid] : false;
          },
          resolve: (requested, options) => resolveParts(packageDescriptor, requested, {
            ...options, client,
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
          initialComposition: previousCompletePackage?.meshData || null,
          concurrency: packageComponentLoadConcurrency(),
          // The local cap controls package concurrency. A single larger
          // leaf may run alone only if reserveLoad below can charge its full
          // worker estimate to the shared Viewer memory envelope.
          allowOversizedSingle: true,
          retainedComponent: (cid) => retainedByCid[cid]?.meshData || null,
          retryCacheProbeMiss: isTessellationCacheProbeMissError,
          // A component cadgen could not derive or mesh (its own failed row) is left out: the rest
          // of the model is drawn, and the final publish reports it as the load's background error.
          componentFailed: (error, cid) => error instanceof PartResolutionError
            && !error.replacementView && error.cid === cid,
          // The part's stored mesh, as cadgen made it. Same meshData contract as the
          // component GLB this replaced.
          loadComponent: async (cid, _component, { estimatedBytes, row }) => {
            // A warm body comes from its batch; null leaves the read to the worker, as before.
            let tessellationEntry = null;
            try {
              tessellationEntry = await bodyBatches.take(cid, row);
            } finally {
              firstBodyRead();
            }
            return loadRenderPart({
              resources, tessellationCache, signal: controller.signal,
              identity: { part: row.part, tessellationProbe: row,
                ...(tessellationEntry ? { tessellationEntry } : {}) },
              memoryEstimateBytes: estimatedBytes,
            });
          },
          // Byte-aware admission: every component is sized by its part's record before its decode
          // is admitted -- a warm one's from the package's probe, a cold one's from the request that
          // had cadgen derive it.
          partRow: async (cid, component, {
            rejectedCacheObjects = new Set(),
            skipCacheProbes = false,
          } = {}) => {
            // The first ask is the package's batched probe; one after a probed body went missing
            // asks afresh, alone, as every ask once did.
            const afresh = rejectedCacheObjects.size > 0;
            if (afresh) bodyBatches.discard(cid);
            // A preview's part its build has not derived yet: the feed names it when it has, and
            // nothing asks cadgen for it meanwhile -- what is named is drawn while the lane waits.
            // Once the build has named all it can, an unnamed part is a saved file's missing part.
            let waited = false;
            if (gate && !gate.has(cid) && !gate.complete) {
              loader.publishPending();
              await gate.whenNamed(cid, controller.signal);
              waited = true;
            }
            const probeAlone = () => probeInitialDisplay({ tessellationCache,
              part: component.part,
              signal: controller.signal,
              rejectedCacheObjects,
            });
            let cached = skipCacheProbes ? null : afresh || waited
              ? await probeAlone()
              : (await initialPlans.plan(cid)) ?? null;
            // A preview's part named after its chunk was probed: the store holds it now.
            if (!cached && !skipCacheProbes && !afresh && !waited && gate?.has(cid)) cached = await probeAlone();
            if (cached) {
              prewarmForBatches();
              componentIdentityByCid.set(cid, cached.cacheProbe);
              return cached.cacheProbe;
            }
            // Cold: the request has cadgen derive the part, and answers with its record. A retry
            // after a missing body asks again, alone, so a part the store lost is derived anew.
            const row = afresh || skipCacheProbes
              ? (await resolveParts(packageDescriptor, [{ cid, part: component.part }],
                { client, signal: controller.signal })).get(cid)
              : await partTickets.ticket(cid, component);
            if (!producedDisplayPlan(row)) throw new Error(`Component ${cid} has no display mesh`);
            componentIdentityByCid.set(cid, row);
            return row;
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
            syncPartWorkerMemory();
          },
          recoverMemoryPressure: async () => {
            if (completedPackages.clear()) {
              syncAssetCacheMemory(componentMemoryAccounting(displayedPackageRef.current?.componentMeshDataByCid).buffers);
              return true;
            }
            const reclaimed = reclaimIdlePartWorkers();
            syncPartWorkerMemory();
            if (reclaimed.reclaimedSlots > 0 || reclaimed.fullyReleased) return true;
            // Every package decode has drained at this point. If another
            // selector consumer still owns all slots, wait for that
            // generation to finish, then retry this unchanged reservation
            // once. Generation fencing prevents this waiter from clearing a
            // replacement pool's accounting.
            const released = await releasePartWorkers();
            syncPartWorkerMemory();
            return released;
          },
          onMemoryLimitation: (detail) => viewerMemoryPolicy.noteLimitation(detail),
          // Revision replacement is a transaction: loaded component arrays
          // are accounted beside the current complete scene, but only the
          // final composition is published.
          publishIntermediate: !sameFileReplacement,
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
            if (final) {
              nextState.assemblyUnmeshedParts = namedPartNames(packageDescriptor, componentMeshDataByCid, "unmeshedFaces");
            }
            const ctx = packageRef.current;
            if (ctx && ctx.requestId === requestId) {
              ctx.componentMeshDataByCid = componentMeshDataByCid;
              ctx.meshData = meshData;
              ctx.complete = final;
            } else {
              packageRef.current = {
                entry: viewReplacement ? { ...entry, runtimeViewReplacement: false } : entry,
                file: entry.file,
                meshUrl,
                descriptor: packageDescriptor,
                runtimeDescriptor: storedPackageDescriptor,
                componentIdentityByCid: Object.fromEntries(componentIdentityByCid),
                componentMeshDataByCid,
                meshData,
                requestId,
                complete: final
              };
            }
            packageRef.current.componentIdentityByCid = Object.fromEntries(componentIdentityByCid);
            const publishedCtx = packageRef.current;
            publishedCtx.meshHash = nextState.meshHash;
            syncDisplayedMemory(publishedCtx.componentMeshDataByCid);
            displayedPackageRef.current = final ? publishedCtx : null;
            displayedReferenceCompositionRef.current = null;
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
              // Later publishes swap the state in place: a state for another
              // file is never replaced.
              setMeshState((current) => (
                !current || current.file !== entry.file ? current : nextState
              ));
            }
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
          partTickets.dispose();
          // Nothing decodes once the load ends — a later topology load
          // builds a fresh pool — so the workers' isolates go back to the
          // process instead of holding the heap each grew for the largest
          // component it decoded. Also on the failure path: an aborted load
          // is exactly when the memory is most worth returning.
          releasePartWorkers().then(() => {
            syncPartWorkerMemory();
          }).catch(() => {
            syncPartWorkerMemory();
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
      if (err instanceof PartResolutionError && err.replacementView && !viewReplacement) {
        return viewReplacementRef.current?.(
          entry, entryAssetUrl(entry, "glb"), err.replacementView,
        );
      }
      if (entry?.kind === "assembly" && assemblyPreviewVisible) {
        const displayed = matchingDisplayedPackageContext(
          displayedPackageRef.current,
          meshStateRef.current,
          entry.file,
        );
        if (displayed) {
          packageRef.current = displayed;
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
  }, [cancelMeshLoad, entryHasMesh, getAssemblyMeshHash, client, restoreCompletedPackage]);

  viewReplacementRef.current = (entry, meshUrl, replacementView) => {
    if (!replacementView?.viewId) return Promise.resolve();
    completedPackages.delete(client, entry);
    installRuntimePackageDescriptor(meshUrl, replacementView, { resources });
    if (packageRef.current?.descriptor?.viewId === replacementView.viewId) {
      return Promise.resolve();
    }
    const active = viewReplacementTaskRef.current;
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
      await loadMeshForEntry({ ...entry, runtimeViewReplacement: true });
    })().finally(() => {
      if (viewReplacementTaskRef.current?.promise === task) {
        viewReplacementTaskRef.current = null;
      }
    });
    viewReplacementTaskRef.current = { viewId: replacementView.viewId, promise: task };
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
      // Component-GLB package: compose the per-component selector runtimes (each placed by its
      // occurrence transform and namespaced by occurrence id) so nested faces/edges become pickable.
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
        // loadRenderPartSelectorBundle is cache-backed, so each new expansion only fetches the
        // newly-needed component; previously loaded ones are free.
        const isSingleComponentPart = String(entry?.kind || "").trim() === "part";
        const { occurrencesToLoad, neededCids, loadedTopologyKey } = selectRequestedAssemblyComponents(
          packageDescriptor,
          requestedOccurrenceIds,
          { singleComponentPart: isSingleComponentPart }
        );
        const shown = packageRef.current;
        // Each part's row: the one its mesh on screen was drawn from, else one resolved here (a part
        // still loading cold).
        const componentIdentityByCid = {
          ...((shown && shown.file === entry.file && shown.componentIdentityByCid) || {}),
        };
        const unresolved = neededCids.filter((cid) => packageDescriptor.components?.[cid] && !componentIdentityByCid[cid])
          .map((cid) => ({ cid, part: packageDescriptor.components[cid].part }));
        if (unresolved.length) {
          const resolved = await resolveParts(packageDescriptor, unresolved, { client,
            signal: controller.signal,
          });
          for (const { cid } of unresolved) componentIdentityByCid[cid] = resolved.get(cid);
          if (shown?.descriptor === packageDescriptor) {
            shown.componentIdentityByCid = { ...componentIdentityByCid };
          }
        }
        const componentBundleByCid = {};
        const componentBundleKeyByCid = {};
        // A part's selectors: cadgen's selector table joined to the mesh on screen. A part the store
        // no longer holds is cadgen's to derive again, and the read goes on with the record it
        // answered.
        const loadSelectorBundle = async (cid) => {
          const read = (row) => loadRenderPartSelectorBundle(viewerOriginUrl(client.origin, partSelectorsPath(row)), {
            resources, tessellationCache, signal: controller.signal,
            identity: { part: row.part, tessellationProbe: row },
          });
          try {
            return await read(componentIdentityByCid[cid]);
          } catch (error) {
            if (controller.signal.aborted || !isTessellationCacheProbeMissError(error)) throw error;
          }
          const resolved = await resolveParts(packageDescriptor, [{
            cid, part: packageDescriptor.components[cid].part,
          }], { client, signal: controller.signal });
          componentIdentityByCid[cid] = resolved.get(cid);
          return read(componentIdentityByCid[cid]);
        };
        await mapWithConcurrency(
          neededCids,
          componentPartLoadConcurrency(),
          async (cid) => {
            const component = (packageDescriptor.components || {})[cid];
            if (!component) {
              return;
            }
            componentBundleKeyByCid[cid] = partCacheKey(componentIdentityByCid[cid]);
            // A bundle this session already loaded for the same mesh (the key names the part and
            // its mesh's object) is the one the cache would return: reuse it, so a batch fetches
            // only its new components, not every one it composes.
            const held = session.bundleByCid.get(cid);
            if (held && held.key === componentBundleKeyByCid[cid]) {
              componentBundleByCid[cid] = held.bundle;
              return;
            }
            // Exact topology: cadgen's selector table joined client-side to the component's mesh on
            // screen, so triangle ranges remain exact. One that cannot be joined leaves its parts
            // unpublished.
            componentBundleByCid[cid] = await loadSelectorBundle(cid).catch(() => null);
            if (componentBundleByCid[cid]) session.bundleByCid.set(cid, { key: componentBundleKeyByCid[cid], bundle: componentBundleByCid[cid] });
          }
        );
        if (!isCurrent()) {
          return "stale";
        }
        // A batch publishes only what is still requested (a part let go of while it loaded would
        // make the published topology unusable until the next batch), and never takes back a part
        // another batch published meanwhile: the next batch composes both.
        if (!session.accepts(requestedOccurrenceIds)) return "skipped";
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
        // DO namespace by occurrence so each leaf part owns its faces/edges. Both stamp every
        // row with its placing occurrenceId, so picks align with the composed mesh's
        // sourcePartRanges occurrence and a ref reads `<occurrence token>/<element name>`.
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
        // Remembered so a new topology session for this revision carries it over.
        const nextComposition = {
          file: entry.file,
          meshHash: getAssemblyMeshHash(entry),
          loadedTopologyKey: publishedTopologyKey,
          loadedTopologyIds: publishedTopologyIds
        };
        referenceCompositionRef.current = nextComposition;
        const displayed = matchingDisplayedPackageContext(displayedPackageRef.current, meshStateRef.current, entry.file);
        if (displayed?.meshHash === nextComposition.meshHash) displayedReferenceCompositionRef.current = nextComposition;
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
      // A missing or non-package descriptor is a stale or unbuilt artifact, as the mesh load reports.
      throw new Error(
        `STEP file ${entry.file || "(unknown)"} is not a component-GLB package; regenerate it to produce an assembly.json package.`
      );
    } finally {
      // A first pick can be the last consumer of the tessellation pool.
      // Reclaim its isolates after all sibling loads drain, just like initial
      // display; a topology-only interaction must not pin eight heaps.
      releasePartWorkers().then(syncPartWorkerMemory, syncPartWorkerMemory);
    }
  }, [buildNormalizedReferenceState, getAssemblyMeshHash, resources]);

  const failReferenceSession = useCallback(async (session, err) => {
    if (session.requestId !== referenceRequestIdRef.current || session.controller.signal.aborted || isAbortError(err)) {
      return;
    }
    if (err instanceof PartResolutionError && err.replacementView) {
      await viewReplacementRef.current?.(
        session.entry, entryAssetUrl(session.entry, "glb"), err.replacementView,
      );
      return;
    }
    session.failed = true;
    setReferenceStatus(REFERENCE_STATUS.ERROR);
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
      return Promise.resolve();
    }

    const key = `${String(entry?.file || "")}\u0000${entryReferenceAssetSignature(entry) || ""}\u0000${getAssemblyMeshHash(entry) || ""}\u0000${String(entry?.fileRefPrefix || "")}\u0000${String(entry?.kind || "")}`;
    let session = referenceSessionRef.current;
    const sessionCurrent = Boolean(session && session.key === key && session.loader === loadReferenceBatch && !session.failed
      && session.requestId === referenceRequestIdRef.current && !session.controller.signal.aborted);
    if (!sessionCurrent) {
      cancelReferenceLoad();
      if (referenceComposerRef.current.key !== key) {
        referenceComposerRef.current.composer.reset();
        referenceComposerRef.current.key = key;
      }
      // What this revision already has on screen carries over: a new session adds to it.
      const live = referenceCompositionRef.current;
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
          setReferenceLoadStage("loading topology");
        },
        onSettled: () => {
          setReferenceStatus(REFERENCE_STATUS.READY);
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
      setReferenceStatus(REFERENCE_STATUS.READY);
      setReferenceLoadStage("");
    }
    return request.promise || Promise.resolve();
  }, [cancelReferenceLoad, entryHasReferences, failReferenceSession, getAssemblyMeshHash, loadReferenceBatch,
    resources]);

  useEffect(() => () => {
    abortLoad(meshAbortControllerRef);
    abortLoad(referenceAbortControllerRef);
    const displayed = displayedPackageRef.current;
    if (displayed) completedPackages.set(client, displayed.entry, displayed);
    syncAssetCacheMemory();
  }, [client, resources]);

  // The measure request naming a face of the view on screen (`POST /__cad/measure`): the view's tree,
  // id and producer, the component the face's occurrence places and its part, and the face's ordinal.
  const faceMeasureRequest = useCallback((reference) => {
    const descriptor = packageRef.current?.descriptor;
    const occurrenceId = String(reference?.occurrenceId || "").trim();
    const face = reference?.pickData?.ordinal;
    if (!descriptor?.tree || !descriptor?.viewId || !descriptor?.producer || !occurrenceId || !Number.isInteger(face)) {
      return null;
    }
    const occurrence = (descriptor.occurrences || []).find((entry) => entry?.id === occurrenceId);
    const cid = String(occurrence?.component || "");
    const part = cid ? descriptor.components?.[cid]?.part : null;
    return part ? { tree: descriptor.tree, viewId: descriptor.viewId, producer: descriptor.producer, cid, part, face } : null;
  }, []);

  return {
    faceMeasureRequest,
    meshState,
    setMeshState,
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
    referenceLoadStage,
    cancelMeshLoad,
    cancelReferenceLoad,
    loadMeshForEntry,
    fatalLoadFailure,
    clearFatalLoadFailure,
    loadReferencesForEntry
  };
}

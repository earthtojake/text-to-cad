import { useCallback, useEffect, useRef, useState } from "react";
import {
  isAbortError,
  loadRenderDisplayEdgeBundle,
  loadRenderGlb,
  loadRenderSurf,
  loadRenderJson,
  loadRenderSelectorBundle,
  loadRenderSurfSelectorBundle,
  loadRenderSdf,
  loadRenderSrdf,
  loadRenderUrdf,
  peekRenderDisplayEdgeBundle,
  peekRenderGlb,
  peekRenderSelectorBundle,
  peekRenderSdf,
  peekRenderSrdf,
  peekRenderTopologyIndex,
  peekRenderUrdf
} from "cadgen-js/lib/renderAssetClient";
import {
  assemblyRootFromTopology,
  buildComposedPackageMeshData
} from "cadgen-js/lib/assembly/meshData";
import { mapWithConcurrency } from "cadgen-js/lib/async/concurrency";
import { primeCachedEntryBytes } from "cadgen-js/lib/surf/tessellationCache.js";
import { resolvePackageAssetUrl } from "./packageAssetUrl.js";
import { ASSET_STATUS, REFERENCE_STATUS } from "../../../workbench/constants";
import {
  entryAssetHash,
  entryAssetUrl,
  entryDisplayEdgeTopologyAssetUrl,
  entryMeshAssetHash,
  entryMeshAssetSignature,
  entryMeshAssetUrl,
  entrySelectorTopologyAssetUrl,
  entryTopologyAssetUrl,
  entryUrdfAssetHash,
  meshAssetKeyForEntry
} from "cadgen-js/lib/entryAssets";
import {
  loadRenderMeshByUrl,
  peekRenderMeshByUrl
} from "cadgen-js/lib/render/meshLoaders";
import { shouldUseGlbMeshWorkerForEntry } from "cadgen-js/lib/render/meshCost";
import { RENDER_FORMAT, entrySourceFormat } from "cadgen-js/lib/fileFormats";
import { buildDisplayEdgeRuntime, buildSelectorRuntime } from "cadgen-js/lib/selectors/runtime";
import {
  composePackageSelectorRuntime,
  compositionUsesComponent,
  swapCompositionBundle
} from "./packageReferenceComposition.js";
import { selectRequestedAssemblyComponents } from "../../../workbench/referenceSelection";

// Robot link meshes are STLs, and `loadRenderStl` parses them in the STL worker — the
// fetch and the parse both happen off the main thread. The cap used to be 3 with a
// main-thread yield either side of every mesh, which was right when parsing blocked the
// UI and is pure latency now: it serialised 13 fetches three at a time for no benefit.
const ROBOT_MESH_LOAD_CONCURRENCY = 8;

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

function robotMeshLoadConcurrency() {
  const hardwareConcurrency = typeof navigator !== "undefined"
    ? Number(navigator.hardwareConcurrency)
    : 0;
  if (!Number.isFinite(hardwareConcurrency) || hardwareConcurrency <= 0) {
    return ROBOT_MESH_LOAD_CONCURRENCY;
  }
  // Bounded by cores because the worker still parses serially; going wider only queues.
  return Math.max(2, Math.min(ROBOT_MESH_LOAD_CONCURRENCY, hardwareConcurrency));
}

// Component-GLB packages fan out to many small content-addressed GLBs (141 for
// falcon_heavy). They parse in the GLB worker (off the main thread), so — unlike
// the large robot-mesh STL path above — a higher fetch concurrency just overlaps
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

function urdfMeshUrls(urdfData) {
  return [...new Set(
    (Array.isArray(urdfData?.links) ? urdfData.links : [])
      .flatMap((link) => Array.isArray(link?.visuals) ? link.visuals : [])
      .map((visual) => String(visual?.meshUrl || "").trim())
      .filter(Boolean)
  )];
}

async function loadRenderRobotMeshes(meshUrls, { signal, onProgress } = {}) {
  const total = meshUrls.length;
  let completed = 0;
  onProgress?.(completed, total);
  return mapWithConcurrency(meshUrls, robotMeshLoadConcurrency(), async (meshUrl) => {
    if (signal?.aborted) {
      throw abortError();
    }
    const mesh = await loadRenderMeshByUrl(meshUrl, { signal, fallback: RENDER_FORMAT.STL });
    completed += 1;
    onProgress?.(completed, total);
    return mesh;
  });
}

function peekRenderMeshForEntry(entry) {
  return peekRenderMeshByUrl(entryMeshAssetUrl(entry), {
    fallback: meshAssetKeyForEntry(entry)
  });
}

function loadRenderMeshForEntry(entry, options) {
  return loadRenderMeshByUrl(entryMeshAssetUrl(entry), {
    ...options,
    fallback: meshAssetKeyForEntry(entry),
    preferWorker: shouldUseGlbMeshWorkerForEntry(entry)
  });
}

// One fetch per descriptor URL: the mesh path and the selector path both
// resolve the same descriptor when a model opens, and the URL carries a ?v=
// version token, so a keyed cache is naturally invalidated when the underlying
// file changes. Bounded to keep long sessions flat. The store descriptor
// (assembly.json) is a pure function of the STEP bytes; nothing source-derived
// is merged into it here.
const PACKAGE_DESCRIPTOR_CACHE = new Map();
const PACKAGE_DESCRIPTOR_CACHE_LIMIT = 32;

async function loadPackageDescriptor(packageAssetUrl, { signal } = {}) {
  const descriptorUrl = resolvePackageAssetUrl(packageAssetUrl, "assembly.json");
  if (PACKAGE_DESCRIPTOR_CACHE.has(descriptorUrl)) {
    return PACKAGE_DESCRIPTOR_CACHE.get(descriptorUrl);
  }
  const promise = loadRenderJson(descriptorUrl, { signal }).catch(() => null);
  if (PACKAGE_DESCRIPTOR_CACHE.size >= PACKAGE_DESCRIPTOR_CACHE_LIMIT) {
    PACKAGE_DESCRIPTOR_CACHE.clear();
  }
  PACKAGE_DESCRIPTOR_CACHE.set(descriptorUrl, promise);
  promise.then((value) => {
    // Never cache a failed/aborted resolve: the next caller should retry.
    if (!value) {
      PACKAGE_DESCRIPTOR_CACHE.delete(descriptorUrl);
    }
  });
  return promise;
}


function createAssemblyPreviewMeshData(meshData, topologyManifest = null) {
  return {
    ...meshData,
    parts: null,
    assemblyRoot: assemblyRootFromTopology(topologyManifest)
  };
}

export function useCadAssets({
  entryHasMesh,
  entryHasReferences,
  entryHasDisplayEdges = () => false,
  buildNormalizedReferenceState,
}) {
  const [meshState, setMeshState] = useState(null);
  const [meshLoadInProgress, setMeshLoadInProgress] = useState(false);
  const [meshLoadTargetFile, setMeshLoadTargetFile] = useState("");
  const [meshLoadStage, setMeshLoadStage] = useState("");
  const [status, setStatus] = useState(ASSET_STATUS.READY);
  const [error, setError] = useState("");
  const [urdfState, setUrdfState] = useState(null);
  const [urdfStatus, setUrdfStatus] = useState(ASSET_STATUS.PENDING);
  const [urdfError, setUrdfError] = useState("");
  const [urdfLoadStage, setUrdfLoadStage] = useState("");
  // The same stage, as data rather than a sentence. The loader has always COUNTED the
  // meshes it fetches; flattening that count into a string meant the one indicator the
  // user actually watches — the overlay — could only show a generic "Loading". Both are
  // set from the same call sites so they cannot disagree.
  const [urdfLoadProgress, setUrdfLoadProgress] = useState(null);
  const [referenceState, setReferenceState] = useState(null);
  const [referenceStatus, setReferenceStatus] = useState(REFERENCE_STATUS.IDLE);
  const [referenceError, setReferenceError] = useState("");
  const [referenceLoadStage, setReferenceLoadStage] = useState("");
  const [displayEdgeState, setDisplayEdgeState] = useState(null);
  const [displayEdgeStatus, setDisplayEdgeStatus] = useState(REFERENCE_STATUS.IDLE);
  const [displayEdgeError, setDisplayEdgeError] = useState("");
  const [displayEdgeLoadStage, setDisplayEdgeLoadStage] = useState("");

  const requestIdRef = useRef(0);
  const urdfRequestIdRef = useRef(0);
  const referenceRequestIdRef = useRef(0);
  const displayEdgeRequestIdRef = useRef(0);
  const meshAbortControllerRef = useRef(null);
  const urdfAbortControllerRef = useRef(null);
  const referenceAbortControllerRef = useRef(null);
  const displayEdgeAbortControllerRef = useRef(null);

  const getAssemblyMeshHash = useCallback((entry) => {
    return entryMeshAssetSignature(entry);
  }, []);

  // --- viewport LOD (design/unified-tessellation.md Phase 5) -----------------
  // The composed package's ingredients, kept so a level swap can re-compose ONE
  // component at a finer tessellation without reloading anything else. Ref +
  // state pair: the ref is the mutable working set, the state is the reactive
  // summary the LOD hook consumes (component diagonals, occurrence centers in
  // model coordinates, and each component's surf URL).
  const lodPackageRef = useRef(null);
  const [lodPackage, setLodPackage] = useState(null);
  // The composed reference state's ingredients: the lazily-loaded occurrence
  // subset and the selector bundle each component's topology was built from.
  // Kept so an LOD level swap can re-compose PICKING from the same
  // tessellation the display mesh just moved to. Mesh and selector runtime
  // must always come from ONE tessellation (loadRenderSurfPayloadAtLevel's
  // contract): faceRuns carry triangle ranges of a specific tessellation, so
  // a level-N mesh read through level-M runs mislabels triangles — partial
  // face highlights and picks that resolve through the surface.
  const referenceCompositionRef = useRef(null);

  const buildLodPackageSummary = useCallback((entry, meshUrl, descriptor, componentMeshDataByCid) => {
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
        if (!bounds?.min || !bounds?.max || !component?.surf) {
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
        return { cid, diagonal, centers, surfUrl: resolvePackageAssetUrl(meshUrl, component.surf) };
      })
      .filter(Boolean);
    return { file: entry.file, components };
  }, []);

  // Swap one component to a re-tessellated level: tag the payload's meshData
  // with the level (part of the geometry identity — see sourceMeshKey in
  // buildComposedPackageMeshData), re-compose (reference composition, cheap),
  // and publish. The old state keeps rendering until this one commits, and a
  // stale apply (entry changed underneath) is a no-op.
  const applyComponentLodPayload = useCallback((cid, level, payload) => {
    const ctx = lodPackageRef.current;
    const meshData = payload?.meshData;
    if (!ctx || !meshData) {
      return false;
    }
    meshData.lodLevel = level;
    ctx.componentMeshDataByCid = { ...ctx.componentMeshDataByCid, [cid]: meshData };
    // Remember the level's selector bundle: picking re-composes from it below,
    // and a topology load that lands AFTER this swap must prefer it over the
    // level-0 bundle cache (loadReferencesForEntry consults this map).
    if (payload.bundle) {
      ctx.componentLodBundleByCid = { ...(ctx.componentLodBundleByCid || {}), [cid]: payload.bundle };
    }
    const composed = buildComposedPackageMeshData(ctx.descriptor, ctx.componentMeshDataByCid);
    const nextState = buildComposedPackageMeshStateRef.current(ctx.entry, ctx.descriptor, composed);
    let applied = false;
    setMeshState((current) => {
      if (!current || current.file !== ctx.file) {
        return current;
      }
      applied = true;
      return nextState;
    });
    // Re-compose the reference state to the SAME tessellation, in the same
    // batch as the mesh publish, so a level-N mesh is never read through
    // level-M faceRuns (stale faceIds = striped highlights + through-picks).
    // Both publishes carry their own staleness guards, so ordering races with
    // an entry change collapse to no-ops.
    if (payload.bundle) {
      recomposeReferenceStateForLodRef.current?.(ctx, cid, payload.bundle);
    }
    return applied;
  }, []);

  // Rebuild the composed selector runtime with one component's bundle swapped
  // to the level the display mesh just moved to. Scoped to the composition's
  // already-loaded occurrence subset (lazy topology stays lazy).
  const recomposeReferenceStateForLod = useCallback((ctx, cid, bundle) => {
    const composition = referenceCompositionRef.current;
    if (!composition || composition.file !== ctx.file) {
      return;
    }
    if (!compositionUsesComponent(composition, cid)) {
      return;
    }
    const nextComposition = swapCompositionBundle(composition, cid, bundle);
    referenceCompositionRef.current = nextComposition;
    const nextReferenceState = buildNormalizedReferenceState(nextComposition.entry, null, {
      selectorRuntime: composePackageSelectorRuntime(
        nextComposition.entry,
        nextComposition.occurrencesToLoad,
        nextComposition.bundleByCid,
        { singleComponentPart: nextComposition.isSingleComponentPart }
      ),
      loadedTopologyKey: nextComposition.loadedTopologyKey
    });
    setReferenceState((current) => (
      current && current.fileRef === nextReferenceState.fileRef ? nextReferenceState : current
    ));
  }, [buildNormalizedReferenceState]);
  const recomposeReferenceStateForLodRef = useRef(recomposeReferenceStateForLod);
  recomposeReferenceStateForLodRef.current = recomposeReferenceStateForLod;

  const buildComposedPackageMeshState = useCallback((entry, descriptor, meshData) => {
    return {
      file: entry.file,
      kind: entry.kind,
      meshHash: getAssemblyMeshHash(entry),
      meshData,
      assemblyStructureReady: true,
      assemblyInteractionReady: true,
      assemblyBackgroundError: ""
    };
  }, [getAssemblyMeshHash]);
  // Defined after applyComponentLodPayload, consumed by it through a ref.
  const buildComposedPackageMeshStateRef = useRef(buildComposedPackageMeshState);
  buildComposedPackageMeshStateRef.current = buildComposedPackageMeshState;

  const buildAssemblyPreviewMeshState = useCallback((entry, meshData, topologyManifest = null) => {
    const previewMeshData = createAssemblyPreviewMeshData(meshData, topologyManifest);
    return {
      file: entry.file,
      kind: entry.kind,
      meshHash: getAssemblyMeshHash(entry),
      meshData: previewMeshData,
      assemblyStructureReady: !!previewMeshData.assemblyRoot,
      assemblyInteractionReady: false,
      assemblyBackgroundError: ""
    };
  }, [getAssemblyMeshHash]);

  const getCachedMeshState = useCallback((entry) => {
    if (!entryHasMesh(entry)) {
      return null;
    }
    // Every STEP entry — single-component part OR multi-occurrence assembly — is a
    // component-GLB package (a directory of content-addressed component GLBs + an
    // assembly.json descriptor), composed asynchronously in the browser. The synchronous
    // cache only yields the lightweight preview; the full mesh is built in loadMeshForEntry.
    if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
      const glbUrl = entryAssetUrl(entry, "glb");
      const topologyUrl = entryTopologyAssetUrl(entry);
      const previewMeshData = peekRenderGlb(glbUrl);
      if (!previewMeshData) {
        return null;
      }
      const topologyManifest = peekRenderTopologyIndex(topologyUrl);
      if (!topologyManifest) {
        return buildAssemblyPreviewMeshState(entry, previewMeshData);
      }
      return null;
    }
    const meshData = peekRenderMeshForEntry(entry);
    if (!meshData) {
      return null;
    }
    return {
      file: entry.file,
      kind: entry.kind,
      meshHash: entryMeshAssetHash(entry),
      meshData
    };
  }, [buildAssemblyPreviewMeshState, entryHasMesh]);

  const getCachedReferenceState = useCallback((entry) => {
    if (!entryHasReferences(entry)) {
      return null;
    }
    const bundle = peekRenderSelectorBundle(entrySelectorTopologyAssetUrl(entry));
    return bundle ? buildNormalizedReferenceState(entry, bundle) : null;
  }, [buildNormalizedReferenceState, entryHasReferences]);

  const buildDisplayEdgeState = useCallback((entry, bundle) => {
    return {
      file: entry.file,
      fileRef: String(entry?.file || "").trim(),
      kind: entry.kind,
      displayEdgeHash: entryAssetHash(entry, "displayEdgeTopology"),
      displayEdgeRuntime: buildDisplayEdgeRuntime(bundle)
    };
  }, []);

  const getCachedDisplayEdgeState = useCallback((entry) => {
    if (!entryHasDisplayEdges(entry)) {
      return null;
    }
    const bundle = peekRenderDisplayEdgeBundle(entryDisplayEdgeTopologyAssetUrl(entry));
    return bundle ? buildDisplayEdgeState(entry, bundle) : null;
  }, [buildDisplayEdgeState, entryHasDisplayEdges]);

  const getCachedUrdfState = useCallback((entry) => {
    const kind = String(entry?.kind || "").trim().toLowerCase();
    if (!["urdf", "srdf", "sdf"].includes(kind)) {
      return null;
    }
    const primaryAssetKey = kind === "sdf" ? "sdf" : "urdf";
    if (!entryAssetUrl(entry, primaryAssetKey)) {
      return null;
    }
    const srdfPayload = kind === "srdf"
      ? peekRenderSrdf(entryAssetUrl(entry, "srdf"), { urdfUrl: entryAssetUrl(entry, "urdf") })
      : null;
    const urdfData = kind === "srdf"
      ? srdfPayload?.urdfData
      : kind === "sdf"
        ? peekRenderSdf(entryAssetUrl(entry, "sdf"))
        : peekRenderUrdf(entryAssetUrl(entry, "urdf"));
    if (!urdfData) {
      return null;
    }
    const meshUrls = urdfMeshUrls(urdfData);
    const meshes = meshUrls.map((meshUrl) => peekRenderMeshByUrl(meshUrl, { fallback: RENDER_FORMAT.STL })).filter(Boolean);
    if (meshes.length !== meshUrls.length) {
      return null;
    }
    const meshesByUrl = new Map(meshUrls.map((meshUrl, index) => [meshUrl, meshes[index]]));
    return {
      file: entry.file,
      kind: entry.kind,
      urdfHash: entryUrdfAssetHash(entry),
      urdfData,
      meshesByUrl
    };
  }, []);

  const cancelMeshLoad = useCallback(() => {
    requestIdRef.current += 1;
    abortLoad(meshAbortControllerRef);
    setMeshLoadInProgress(false);
    setMeshLoadTargetFile("");
    setMeshLoadStage("");
  }, []);

  const cancelUrdfLoad = useCallback(() => {
    urdfRequestIdRef.current += 1;
    abortLoad(urdfAbortControllerRef);
    setUrdfLoadStage("");
    setUrdfLoadProgress(null);
  }, []);

  const cancelReferenceLoad = useCallback(() => {
    referenceRequestIdRef.current += 1;
    abortLoad(referenceAbortControllerRef);
    setReferenceLoadStage("");
  }, []);

  const cancelDisplayEdgeLoad = useCallback(() => {
    displayEdgeRequestIdRef.current += 1;
    abortLoad(displayEdgeAbortControllerRef);
    setDisplayEdgeLoadStage("");
  }, []);

  const loadMeshForEntry = useCallback(async (entry) => {
    cancelMeshLoad();
    const requestId = requestIdRef.current;

    if (!entryHasMesh(entry)) {
      setMeshState(null);
      setStatus(ASSET_STATUS.PENDING);
      setError("");
      return;
    }

    const cachedMeshState = getCachedMeshState(entry);
    if (cachedMeshState) {
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
    setMeshLoadStage(entry?.kind === "assembly" ? "loading assembly mesh" : "loading mesh");
    // Any new load invalidates the previous entry's LOD working set.
    lodPackageRef.current = null;
    setLodPackage(null);
    referenceCompositionRef.current = null;
    const keepRenderedAssemblyVisible = entry?.kind === "assembly" && !!cachedMeshState;
    let assemblyPreviewVisible = keepRenderedAssemblyVisible;
    if (!keepRenderedAssemblyVisible) {
      setStatus(ASSET_STATUS.LOADING);
      setError("");
    }

    try {
      // Every STEP entry is a component-GLB package (a single-component part is just a
      // package with one occurrence); compose it the same way. Only non-STEP meshes
      // (STL/3MF/OBJ) fall through to the monolithic single-file loader below.
      if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
        const meshUrl = entryAssetUrl(entry, "glb");
        if (!meshUrl) {
          throw new Error(`STEP file is missing GLB asset: ${entry.file || "(unknown)"}`);
        }
        // Component-GLB package: the canonical STEP artifact is a directory. Probe for
        // its assembly.json, fetch each unique component GLB once, and compose them in
        // world space. A non-package descriptor is a stale/unbuilt artifact (throws below).
        const packageDescriptor = await loadPackageDescriptor(meshUrl, { signal: controller.signal });
        if (packageDescriptor && packageDescriptor.kind === "assembly-package") {
          setMeshLoadStage("loading components");
          const componentEntries = Object.entries(packageDescriptor.components || {});
          const componentMeshDataByCid = {};
          // One batch round trip for the whole hit set BEFORE the component
          // loads, which then take their cached tessellations from it instead
          // of asking the backend one GET per component (an unprimed load of
          // a 483-component model was 483 GETs against the backend already
          // streaming its 483 surfs). Best-effort: nothing here can fail a load.
          await primeCachedEntryBytes(componentEntries.map(([cid]) => cid)).catch(() => 0);
          if (requestId !== requestIdRef.current) {
            return;
          }
          await mapWithConcurrency(componentEntries, packageComponentLoadConcurrency(), async ([cid, component]) => {
            // Exact-surface artifact: tessellated client-side from the .surf
            // (design/surface-rendering.md). Same meshData contract as the
            // component GLB this replaced.
            componentMeshDataByCid[cid] = await loadRenderSurf(resolvePackageAssetUrl(meshUrl, component.surf), {
              signal: controller.signal
            });
          });
          if (requestId !== requestIdRef.current) {
            return;
          }
          setMeshLoadStage("building assembly");
          const composed = buildComposedPackageMeshData(packageDescriptor, componentMeshDataByCid);
          setMeshState(buildComposedPackageMeshState(entry, packageDescriptor, composed));
          lodPackageRef.current = {
            entry,
            file: entry.file,
            descriptor: packageDescriptor,
            componentMeshDataByCid: { ...componentMeshDataByCid }
          };
          setLodPackage(buildLodPackageSummary(entry, meshUrl, packageDescriptor, componentMeshDataByCid));
          setStatus(ASSET_STATUS.READY);
          setError("");
          return;
        }
        // Every STEP model is a component-GLB package (handled above). A missing/non-package
        // descriptor means the artifact is stale or was never built as a package.
        throw new Error(
          `STEP file ${entry.file || "(unknown)"} is not a component-GLB package; regenerate it to produce an assembly.json package.`
        );
      }
      const meshUrl = entryMeshAssetUrl(entry);
      if (!meshUrl) {
        const assetLabel = meshAssetKeyForEntry(entry).toUpperCase();
        throw new Error(`${assetLabel} entry is missing ${assetLabel} asset: ${entry.file || "(unknown)"}`);
      }
      const meshData = await loadRenderMeshForEntry(entry, { signal: controller.signal });
      const meshHash = entryMeshAssetHash(entry);
      if (requestId !== requestIdRef.current) {
        return;
      }
      if (meshData?.sourceFormat === "dxf" && !meshData.vertices?.length) {
        // A dimensioned DRAWING has no prism BY DESIGN: it renders as 2D line
        // work drawn by the viewer itself. Publishing an empty mesh would make
        // the scene sync clear the group — wiping the line container — so this
        // matches the old no-mesh state instead.
        setMeshState(null);
        setStatus(ASSET_STATUS.PENDING);
        setError("");
        return;
      }
      setMeshLoadStage("building");
      setMeshState({
        file: entry.file,
        kind: entry.kind,
        meshHash,
        meshData
      });
      setStatus(ASSET_STATUS.READY);
    } catch (err) {
      if (requestId !== requestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      if (entry?.kind === "assembly" && assemblyPreviewVisible) {
        setMeshState((current) => {
          if (!current || current.file !== entry.file || current.meshHash !== getAssemblyMeshHash(entry)) {
            return current;
          }
          return {
            ...current,
            assemblyBackgroundError: err instanceof Error ? err.message : String(err)
          };
        });
        return;
      }
      setStatus(ASSET_STATUS.ERROR);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (requestId === requestIdRef.current) {
        setMeshLoadInProgress(false);
        setMeshLoadTargetFile("");
        setMeshLoadStage("");
      }
      if (meshAbortControllerRef.current === controller) {
        meshAbortControllerRef.current = null;
      }
    }
  }, [buildAssemblyPreviewMeshState, cancelMeshLoad, entryHasMesh, getAssemblyMeshHash, getCachedMeshState]);

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
        ? await loadPackageDescriptor(glbUrl, { signal: controller.signal })
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
        const lodCtx = lodPackageRef.current;
        const lodBundleByCid = (lodCtx && lodCtx.file === entry.file && lodCtx.componentLodBundleByCid) || {};
        const componentBundleByCid = {};
        await mapWithConcurrency(
          neededCids,
          robotMeshLoadConcurrency(),
          async (cid) => {
            const component = (packageDescriptor.components || {})[cid];
            if (!component) {
              return;
            }
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
              resolvePackageAssetUrl(glbUrl, component.surf),
              { signal: controller.signal }
            ).catch(() => null);
          }
        );
        if (requestId !== referenceRequestIdRef.current) {
          return;
        }
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
        // with one component's bundle replaced (see recomposeReferenceStateForLod).
        referenceCompositionRef.current = {
          file: entry.file,
          entry,
          occurrencesToLoad,
          bundleByCid: componentBundleByCid,
          loadedTopologyKey,
          isSingleComponentPart
        };
        setReferenceState(nextReferenceState);
        setReferenceStatus(nextReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
        setReferenceError(nextReferenceState.disabledReason || "");
        return;
      }

      const bundle = await loadRenderSelectorBundle(
        entrySelectorTopologyAssetUrl(entry),
        { signal: controller.signal }
      );
      if (requestId !== referenceRequestIdRef.current) {
        return;
      }
      const nextReferenceState = buildNormalizedReferenceState(entry, bundle);
      setReferenceState(nextReferenceState);
      setReferenceStatus(nextReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
      setReferenceError(nextReferenceState.disabledReason || "");
    } catch (err) {
      if (requestId !== referenceRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      setReferenceStatus(REFERENCE_STATUS.ERROR);
      setReferenceError(err instanceof Error ? err.message : String(err));
    } finally {
      if (referenceAbortControllerRef.current === controller) {
        referenceAbortControllerRef.current = null;
      }
      if (requestId === referenceRequestIdRef.current) {
        setReferenceLoadStage("");
      }
    }
  }, [buildNormalizedReferenceState, cancelReferenceLoad, entryHasReferences, getCachedReferenceState]);

  const loadDisplayEdgesForEntry = useCallback(async (entry) => {
    cancelDisplayEdgeLoad();
    const requestId = displayEdgeRequestIdRef.current;

    if (!entryHasDisplayEdges(entry)) {
      setDisplayEdgeState(null);
      setDisplayEdgeStatus(REFERENCE_STATUS.DISABLED);
      setDisplayEdgeError("");
      return;
    }

    // A STEP model is a component-GLB package: there is no separate display-edge bundle to
    // fetch (the package "glb" asset is a directory, so a fetch would 404). The per-component
    // edges live in the composed selector runtime, which CadViewer already uses as the display-
    // edge source via `displayEdgeRuntime || selectorRuntime`. Disable the dedicated load.
    if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
      setDisplayEdgeState(null);
      setDisplayEdgeStatus(REFERENCE_STATUS.DISABLED);
      setDisplayEdgeError("");
      return;
    }

    const cachedDisplayEdgeState = getCachedDisplayEdgeState(entry);
    if (cachedDisplayEdgeState) {
      setDisplayEdgeState(cachedDisplayEdgeState);
      setDisplayEdgeStatus(REFERENCE_STATUS.READY);
      setDisplayEdgeError("");
      return;
    }

    const controller = new AbortController();
    displayEdgeAbortControllerRef.current = controller;
    setDisplayEdgeStatus(REFERENCE_STATUS.LOADING);
    setDisplayEdgeError("");
    setDisplayEdgeLoadStage("loading edges");

    try {
      const bundle = await loadRenderDisplayEdgeBundle(
        entryDisplayEdgeTopologyAssetUrl(entry),
        { signal: controller.signal }
      );
      if (requestId !== displayEdgeRequestIdRef.current) {
        return;
      }
      setDisplayEdgeState(buildDisplayEdgeState(entry, bundle));
      setDisplayEdgeStatus(REFERENCE_STATUS.READY);
      setDisplayEdgeError("");
    } catch (err) {
      if (requestId !== displayEdgeRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      setDisplayEdgeState(null);
      setDisplayEdgeStatus(REFERENCE_STATUS.ERROR);
      setDisplayEdgeError(err instanceof Error ? err.message : String(err));
    } finally {
      if (displayEdgeAbortControllerRef.current === controller) {
        displayEdgeAbortControllerRef.current = null;
      }
      if (requestId === displayEdgeRequestIdRef.current) {
        setDisplayEdgeLoadStage("");
      }
    }
  }, [buildDisplayEdgeState, cancelDisplayEdgeLoad, entryHasDisplayEdges, getCachedDisplayEdgeState]);

  const loadUrdfForEntry = useCallback(async (entry) => {
    cancelUrdfLoad();
    const requestId = urdfRequestIdRef.current;

    const kind = String(entry?.kind || "").trim().toLowerCase();
    if (!["urdf", "srdf", "sdf"].includes(kind)) {
      setUrdfState(null);
      setUrdfStatus(ASSET_STATUS.PENDING);
      setUrdfError("");
      return;
    }
    const primaryAssetKey = kind === "sdf" ? "sdf" : "urdf";
    if (!entryAssetUrl(entry, primaryAssetKey)) {
      setUrdfState(null);
      setUrdfStatus(ASSET_STATUS.PENDING);
      setUrdfError("");
      return;
    }

    const cachedUrdfState = getCachedUrdfState(entry);
    if (cachedUrdfState) {
      setUrdfState(cachedUrdfState);
      setUrdfStatus(ASSET_STATUS.READY);
      setUrdfError("");
      return;
    }

    const controller = new AbortController();
    urdfAbortControllerRef.current = controller;
    setUrdfStatus(ASSET_STATUS.LOADING);
    setUrdfError("");
    const robotLabel = kind === "sdf" ? "Loading SDF" : kind === "srdf" ? "Loading SRDF" : "Loading URDF";
    setUrdfLoadStage(kind === "sdf" ? "loading SDF" : kind === "srdf" ? "loading SRDF" : "loading URDF");
    setUrdfLoadProgress({ phase: "robot", label: robotLabel, determinate: false });

    try {
      const payload = kind === "srdf"
        ? await loadRenderSrdf(entryAssetUrl(entry, "srdf"), {
            signal: controller.signal,
            urdfUrl: entryAssetUrl(entry, "urdf")
          })
        : kind === "sdf"
          ? { urdfData: await loadRenderSdf(entryAssetUrl(entry, "sdf"), { signal: controller.signal }) }
          : { urdfData: await loadRenderUrdf(entryAssetUrl(entry, "urdf"), { signal: controller.signal }) };
      const urdfData = payload.urdfData;
      const meshUrls = urdfMeshUrls(urdfData);
      setUrdfLoadStage(meshUrls.length ? "loading meshes" : "building robot");
      setUrdfLoadProgress({
        phase: meshUrls.length ? "meshes" : "robot",
        label: meshUrls.length ? "Loading meshes" : "Building robot",
        done: 0,
        total: meshUrls.length || null,
        determinate: meshUrls.length > 0
      });
      // The robot is published ONCE, complete. Drawing links as they arrive was tried and
      // rejected: a half-built robot on screen with the loading card already gone gives no
      // sign whether more is coming, so it reads as a broken model rather than a loading
      // one. The counted stage below is the progress signal instead.
      const meshes = await loadRenderRobotMeshes(meshUrls, {
        signal: controller.signal,
        onProgress: (completed, total) => {
          if (requestId === urdfRequestIdRef.current && total > 0) {
            setUrdfLoadStage(`loading meshes ${completed}/${total}`);
            setUrdfLoadProgress({
              phase: "meshes",
              label: "Loading meshes",
              done: completed,
              total,
              determinate: true
            });
          }
        }
      });
      if (requestId !== urdfRequestIdRef.current) {
        return;
      }
      setUrdfLoadStage("building robot");
      setUrdfLoadProgress({ phase: "robot", label: "Building robot", determinate: false });
      const meshesByUrl = new Map(meshUrls.map((meshUrl, index) => [meshUrl, meshes[index]]));
      setUrdfState({
        file: entry.file,
        kind: entry.kind,
        urdfHash: entryUrdfAssetHash(entry),
        urdfData,
        meshesByUrl,
        complete: true
      });
      setUrdfStatus(ASSET_STATUS.READY);
    } catch (err) {
      if (requestId !== urdfRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      setUrdfStatus(ASSET_STATUS.ERROR);
      setUrdfError(err instanceof Error ? err.message : String(err));
    } finally {
      if (urdfAbortControllerRef.current === controller) {
        urdfAbortControllerRef.current = null;
      }
      if (requestId === urdfRequestIdRef.current) {
        setUrdfLoadStage("");
        setUrdfLoadProgress(null);
      }
    }
  }, [cancelUrdfLoad, getCachedUrdfState]);

  useEffect(() => () => {
    abortLoad(meshAbortControllerRef);
    abortLoad(urdfAbortControllerRef);
    abortLoad(referenceAbortControllerRef);
    abortLoad(displayEdgeAbortControllerRef);
  }, []);

  return {
    meshState,
    setMeshState,
    lodPackage,
    applyComponentLodPayload,
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadStage,
    status,
    setStatus,
    error,
    setError,
    urdfState,
    setUrdfState,
    urdfStatus,
    setUrdfStatus,
    urdfError,
    setUrdfError,
    urdfLoadStage,
    urdfLoadProgress,
    referenceState,
    setReferenceState,
    referenceStatus,
    setReferenceStatus,
    referenceError,
    setReferenceError,
    referenceLoadStage,
    displayEdgeState,
    setDisplayEdgeState,
    displayEdgeStatus,
    setDisplayEdgeStatus,
    displayEdgeError,
    setDisplayEdgeError,
    displayEdgeLoadStage,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedDisplayEdgeState,
    getCachedUrdfState,
    cancelMeshLoad,
    cancelUrdfLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
    loadUrdfForEntry,
    loadReferencesForEntry,
    loadDisplayEdgesForEntry
  };
}

import { useCallback, useEffect, useRef, useState } from "react";
import {
  isAbortError,
  loadRenderDisplayEdgeBundle,
  loadRenderDxf,
  loadRenderGcode,
  loadRenderGlb,
  loadRenderSelectorBundle,
  loadRenderSdf,
  loadRenderSrdf,
  loadRenderTopologyIndex,
  loadRenderUrdf,
  peekRenderDxf,
  peekRenderDisplayEdgeBundle,
  peekRenderGcode,
  peekRenderGlb,
  peekRenderSelectorBundle,
  peekRenderSdf,
  peekRenderSrdf,
  peekRenderTopologyIndex,
  peekRenderUrdf
} from "cadjs/lib/renderAssetClient";
import {
  loadImplicitCadModule,
  peekImplicitCadModule
} from "implicitjs/loader";
import {
  assemblyRootFromTopology,
  assemblyUsesSelfContainedMesh,
  buildSelfContainedAssemblyMeshData
} from "cadjs/lib/assembly/meshData";
import { mapWithConcurrency } from "cadjs/lib/async/concurrency";
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
} from "cadjs/lib/entryAssets";
import {
  loadRenderMeshByUrl,
  peekRenderMeshByUrl
} from "cadjs/lib/render/meshLoaders";
import { shouldUseGlbMeshWorkerForEntry } from "cadjs/lib/render/meshCost";
import { RENDER_FORMAT } from "cadjs/lib/fileFormats";
import { buildDisplayEdgeRuntime } from "cadjs/lib/selectors/runtime";

const ROBOT_MESH_LOAD_CONCURRENCY = 3;

function abortLoad(controllerRef) {
  controllerRef.current?.abort();
  controllerRef.current = null;
}

function browserYield() {
  if (typeof window === "undefined" || typeof window.setTimeout !== "function") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    window.setTimeout(resolve, 0);
  });
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
  return Math.max(2, Math.min(ROBOT_MESH_LOAD_CONCURRENCY, Math.floor(hardwareConcurrency / 2)));
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
    await browserYield();
    const mesh = await loadRenderMeshByUrl(meshUrl, { signal, fallback: RENDER_FORMAT.STL });
    completed += 1;
    onProgress?.(completed, total);
    await browserYield();
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
  entryHasDxf,
  entryHasGcode,
  buildNormalizedReferenceState,
}) {
  const [meshState, setMeshState] = useState(null);
  const [meshLoadInProgress, setMeshLoadInProgress] = useState(false);
  const [meshLoadTargetFile, setMeshLoadTargetFile] = useState("");
  const [meshLoadStage, setMeshLoadStage] = useState("");
  const [status, setStatus] = useState(ASSET_STATUS.READY);
  const [error, setError] = useState("");
  const [dxfState, setDxfState] = useState(null);
  const [dxfStatus, setDxfStatus] = useState(ASSET_STATUS.PENDING);
  const [dxfError, setDxfError] = useState("");
  const [dxfLoadStage, setDxfLoadStage] = useState("");
  const [gcodeState, setGcodeState] = useState(null);
  const [gcodeStatus, setGcodeStatus] = useState(ASSET_STATUS.PENDING);
  const [gcodeError, setGcodeError] = useState("");
  const [gcodeLoadStage, setGcodeLoadStage] = useState("");
  const [implicitState, setImplicitState] = useState(null);
  const [implicitStatus, setImplicitStatus] = useState(ASSET_STATUS.PENDING);
  const [implicitError, setImplicitError] = useState("");
  const [implicitLoadStage, setImplicitLoadStage] = useState("");
  const [urdfState, setUrdfState] = useState(null);
  const [urdfStatus, setUrdfStatus] = useState(ASSET_STATUS.PENDING);
  const [urdfError, setUrdfError] = useState("");
  const [urdfLoadStage, setUrdfLoadStage] = useState("");
  const [referenceState, setReferenceState] = useState(null);
  const [referenceStatus, setReferenceStatus] = useState(REFERENCE_STATUS.IDLE);
  const [referenceError, setReferenceError] = useState("");
  const [referenceLoadStage, setReferenceLoadStage] = useState("");
  const [displayEdgeState, setDisplayEdgeState] = useState(null);
  const [displayEdgeStatus, setDisplayEdgeStatus] = useState(REFERENCE_STATUS.IDLE);
  const [displayEdgeError, setDisplayEdgeError] = useState("");
  const [displayEdgeLoadStage, setDisplayEdgeLoadStage] = useState("");

  const requestIdRef = useRef(0);
  const dxfRequestIdRef = useRef(0);
  const gcodeRequestIdRef = useRef(0);
  const implicitRequestIdRef = useRef(0);
  const urdfRequestIdRef = useRef(0);
  const referenceRequestIdRef = useRef(0);
  const displayEdgeRequestIdRef = useRef(0);
  const meshAbortControllerRef = useRef(null);
  const dxfAbortControllerRef = useRef(null);
  const gcodeAbortControllerRef = useRef(null);
  const implicitAbortControllerRef = useRef(null);
  const urdfAbortControllerRef = useRef(null);
  const referenceAbortControllerRef = useRef(null);
  const displayEdgeAbortControllerRef = useRef(null);

  const getAssemblyMeshHash = useCallback((entry) => {
    return entryMeshAssetSignature(entry);
  }, []);

  const buildSelfContainedAssemblyMeshState = useCallback((entry, topologyManifest, meshData) => {
    return {
      file: entry.file,
      kind: entry.kind,
      meshHash: getAssemblyMeshHash(entry),
      meshData: buildSelfContainedAssemblyMeshData(topologyManifest, meshData),
      assemblyStructureReady: true,
      assemblyInteractionReady: true,
      assemblyBackgroundError: ""
    };
  }, [getAssemblyMeshHash]);

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
    if (entry?.kind === "assembly") {
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
      if (assemblyUsesSelfContainedMesh(topologyManifest)) {
        return buildSelfContainedAssemblyMeshState(entry, topologyManifest, previewMeshData);
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
  }, [buildAssemblyPreviewMeshState, buildSelfContainedAssemblyMeshState, entryHasMesh]);

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

  const getCachedDxfState = useCallback((entry) => {
    if (!entryHasDxf(entry)) {
      return null;
    }
    const dxfData = peekRenderDxf(entryAssetUrl(entry, "dxf"));
    if (!dxfData) {
      return null;
    }
    return {
      file: entry.file,
      kind: entry.kind,
      dxfHash: entryAssetHash(entry, "dxf"),
      dxfData
    };
  }, [entryHasDxf]);

  const getCachedGcodeState = useCallback((entry) => {
    if (!entryHasGcode(entry)) {
      return null;
    }
    const gcodeData = peekRenderGcode(entryAssetUrl(entry, "gcode"));
    if (!gcodeData) {
      return null;
    }
    return {
      file: entry.file,
      kind: entry.kind,
      gcodeHash: entryAssetHash(entry, "gcode"),
      gcodeData
    };
  }, [entryHasGcode]);

  const getCachedImplicitState = useCallback((entry) => {
    if (String(entry?.kind || "").trim().toLowerCase() !== RENDER_FORMAT.IMPLICIT) {
      return null;
    }
    const model = peekImplicitCadModule(entryAssetUrl(entry, "implicit"));
    if (!model) {
      return null;
    }
    return {
      file: entry.file,
      kind: entry.kind,
      implicitHash: entryAssetHash(entry, "implicit"),
      model
    };
  }, []);

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

  const cancelDxfLoad = useCallback(() => {
    dxfRequestIdRef.current += 1;
    abortLoad(dxfAbortControllerRef);
    setDxfLoadStage("");
  }, []);

  const cancelGcodeLoad = useCallback(() => {
    gcodeRequestIdRef.current += 1;
    abortLoad(gcodeAbortControllerRef);
    setGcodeLoadStage("");
  }, []);

  const cancelImplicitLoad = useCallback(() => {
    implicitRequestIdRef.current += 1;
    abortLoad(implicitAbortControllerRef);
    setImplicitLoadStage("");
  }, []);

  const cancelUrdfLoad = useCallback(() => {
    urdfRequestIdRef.current += 1;
    abortLoad(urdfAbortControllerRef);
    setUrdfLoadStage("");
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
    const keepRenderedAssemblyVisible = entry?.kind === "assembly" && !!cachedMeshState;
    let assemblyPreviewVisible = keepRenderedAssemblyVisible;
    if (!keepRenderedAssemblyVisible) {
      setStatus(ASSET_STATUS.LOADING);
      setError("");
    }

    try {
      if (entry?.kind === "assembly") {
        const meshUrl = entryAssetUrl(entry, "glb");
        const topologyUrl = entryTopologyAssetUrl(entry);
        if (!meshUrl) {
          throw new Error(`STEP assembly is missing GLB asset: ${entry.file || "(unknown)"}`);
        }
        const previewMeshData = cachedMeshState?.meshData || await loadRenderGlb(meshUrl, {
          signal: controller.signal,
          preferWorker: shouldUseGlbMeshWorkerForEntry(entry)
        });
        if (requestId !== requestIdRef.current) {
          return;
        }
        if (!cachedMeshState) {
          setMeshState(buildAssemblyPreviewMeshState(entry, previewMeshData));
          setStatus(ASSET_STATUS.READY);
          setError("");
          assemblyPreviewVisible = true;
        }
        setMeshLoadStage("loading topology");
        const topologyManifest = await loadRenderTopologyIndex(topologyUrl, { signal: controller.signal });
        if (requestId !== requestIdRef.current) {
          return;
        }
        if (!cachedMeshState?.assemblyStructureReady) {
          setMeshState(buildAssemblyPreviewMeshState(entry, previewMeshData, topologyManifest));
        }
        if (assemblyUsesSelfContainedMesh(topologyManifest)) {
          setMeshLoadStage("building assembly");
          setMeshState(buildSelfContainedAssemblyMeshState(entry, topologyManifest, previewMeshData));
          setStatus(ASSET_STATUS.READY);
          setError("");
          return;
        }
        throw new Error("STEP assembly topology is not self-contained.");
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
  }, [buildAssemblyPreviewMeshState, buildSelfContainedAssemblyMeshState, cancelMeshLoad, entryHasMesh, getAssemblyMeshHash, getCachedMeshState]);

  const loadReferencesForEntry = useCallback(async (entry) => {
    cancelReferenceLoad();
    const requestId = referenceRequestIdRef.current;

    if (!entryHasReferences(entry)) {
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

  const loadDxfForEntry = useCallback(async (entry) => {
    cancelDxfLoad();
    const requestId = dxfRequestIdRef.current;

    if (!entryHasDxf(entry)) {
      setDxfState(null);
      setDxfStatus(ASSET_STATUS.PENDING);
      setDxfError("");
      return;
    }

    const cachedDxfState = getCachedDxfState(entry);
    if (cachedDxfState) {
      setDxfState(cachedDxfState);
      setDxfStatus(ASSET_STATUS.READY);
      setDxfError("");
      return;
    }

    const controller = new AbortController();
    dxfAbortControllerRef.current = controller;
    setDxfStatus(ASSET_STATUS.LOADING);
    setDxfError("");
    setDxfLoadStage("loading DXF");

    try {
      const dxfData = await loadRenderDxf(entryAssetUrl(entry, "dxf"), { signal: controller.signal });
      if (requestId !== dxfRequestIdRef.current) {
        return;
      }
      setDxfLoadStage("building preview");
      setDxfState({
        file: entry.file,
        kind: entry.kind,
        dxfHash: entryAssetHash(entry, "dxf"),
        dxfData
      });
      setDxfStatus(ASSET_STATUS.READY);
    } catch (err) {
      if (requestId !== dxfRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      setDxfStatus(ASSET_STATUS.ERROR);
      setDxfError(err instanceof Error ? err.message : String(err));
    } finally {
      if (dxfAbortControllerRef.current === controller) {
        dxfAbortControllerRef.current = null;
      }
      if (requestId === dxfRequestIdRef.current) {
        setDxfLoadStage("");
      }
    }
  }, [cancelDxfLoad, entryHasDxf, getCachedDxfState]);

  const loadGcodeForEntry = useCallback(async (entry) => {
    cancelGcodeLoad();
    const requestId = gcodeRequestIdRef.current;

    if (!entryHasGcode(entry)) {
      setGcodeState(null);
      setGcodeStatus(ASSET_STATUS.PENDING);
      setGcodeError("");
      return;
    }

    const cachedGcodeState = getCachedGcodeState(entry);
    if (cachedGcodeState) {
      setGcodeState(cachedGcodeState);
      setGcodeStatus(ASSET_STATUS.READY);
      setGcodeError("");
      return;
    }

    const controller = new AbortController();
    gcodeAbortControllerRef.current = controller;
    setGcodeStatus(ASSET_STATUS.LOADING);
    setGcodeError("");
    setGcodeLoadStage("loading G-code");

    try {
      const gcodeData = await loadRenderGcode(entryAssetUrl(entry, "gcode"), { signal: controller.signal });
      if (requestId !== gcodeRequestIdRef.current) {
        return;
      }
      setGcodeLoadStage("building preview");
      setGcodeState({
        file: entry.file,
        kind: entry.kind,
        gcodeHash: entryAssetHash(entry, "gcode"),
        gcodeData
      });
      setGcodeStatus(ASSET_STATUS.READY);
    } catch (err) {
      if (requestId !== gcodeRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      setGcodeStatus(ASSET_STATUS.ERROR);
      setGcodeError(err instanceof Error ? err.message : String(err));
    } finally {
      if (gcodeAbortControllerRef.current === controller) {
        gcodeAbortControllerRef.current = null;
      }
      if (requestId === gcodeRequestIdRef.current) {
        setGcodeLoadStage("");
      }
    }
  }, [cancelGcodeLoad, entryHasGcode, getCachedGcodeState]);

  const loadImplicitForEntry = useCallback(async (entry) => {
    cancelImplicitLoad();
    const requestId = implicitRequestIdRef.current;

    if (String(entry?.kind || "").trim().toLowerCase() !== RENDER_FORMAT.IMPLICIT) {
      setImplicitState(null);
      setImplicitStatus(ASSET_STATUS.PENDING);
      setImplicitError("");
      return;
    }

    const cachedImplicitState = getCachedImplicitState(entry);
    if (cachedImplicitState) {
      setImplicitState(cachedImplicitState);
      setImplicitStatus(ASSET_STATUS.READY);
      setImplicitError("");
      return;
    }

    const controller = new AbortController();
    implicitAbortControllerRef.current = controller;
    setImplicitStatus(ASSET_STATUS.LOADING);
    setImplicitError("");
    setImplicitLoadStage("loading implicit CAD");

    try {
      const model = await loadImplicitCadModule(entryAssetUrl(entry, "implicit"), { signal: controller.signal });
      if (requestId !== implicitRequestIdRef.current) {
        return;
      }
      setImplicitState({
        file: entry.file,
        kind: entry.kind,
        implicitHash: entryAssetHash(entry, "implicit"),
        model
      });
      setImplicitStatus(ASSET_STATUS.READY);
    } catch (err) {
      if (requestId !== implicitRequestIdRef.current || isAbortError(err) || controller.signal.aborted) {
        return;
      }
      setImplicitStatus(ASSET_STATUS.ERROR);
      setImplicitError(err instanceof Error ? err.message : String(err));
    } finally {
      if (implicitAbortControllerRef.current === controller) {
        implicitAbortControllerRef.current = null;
      }
      if (requestId === implicitRequestIdRef.current) {
        setImplicitLoadStage("");
      }
    }
  }, [cancelImplicitLoad, getCachedImplicitState]);

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
    setUrdfLoadStage(kind === "sdf" ? "loading SDF" : kind === "srdf" ? "loading SRDF" : "loading URDF");

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
      const meshes = await loadRenderRobotMeshes(meshUrls, {
        signal: controller.signal,
        onProgress: (completed, total) => {
          if (requestId === urdfRequestIdRef.current && total > 0) {
            setUrdfLoadStage(`loading meshes ${completed}/${total}`);
          }
        }
      });
      if (requestId !== urdfRequestIdRef.current) {
        return;
      }
      setUrdfLoadStage("building robot");
      const meshesByUrl = new Map(meshUrls.map((meshUrl, index) => [meshUrl, meshes[index]]));
      setUrdfState({
        file: entry.file,
        kind: entry.kind,
        urdfHash: entryUrdfAssetHash(entry),
        urdfData,
        meshesByUrl
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
      }
    }
  }, [cancelUrdfLoad, getCachedUrdfState]);

  useEffect(() => () => {
    abortLoad(meshAbortControllerRef);
    abortLoad(dxfAbortControllerRef);
    abortLoad(gcodeAbortControllerRef);
    abortLoad(implicitAbortControllerRef);
    abortLoad(urdfAbortControllerRef);
    abortLoad(referenceAbortControllerRef);
    abortLoad(displayEdgeAbortControllerRef);
  }, []);

  return {
    meshState,
    setMeshState,
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadStage,
    status,
    setStatus,
    error,
    setError,
    dxfState,
    setDxfState,
    dxfStatus,
    setDxfStatus,
    dxfError,
    setDxfError,
    dxfLoadStage,
    gcodeState,
    setGcodeState,
    gcodeStatus,
    setGcodeStatus,
    gcodeError,
    setGcodeError,
    gcodeLoadStage,
    implicitState,
    setImplicitState,
    implicitStatus,
    setImplicitStatus,
    implicitError,
    setImplicitError,
    implicitLoadStage,
    urdfState,
    setUrdfState,
    urdfStatus,
    setUrdfStatus,
    urdfError,
    setUrdfError,
    urdfLoadStage,
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
    getCachedDxfState,
    getCachedGcodeState,
    getCachedImplicitState,
    getCachedUrdfState,
    cancelMeshLoad,
    cancelDxfLoad,
    cancelGcodeLoad,
    cancelImplicitLoad,
    cancelUrdfLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
    loadDxfForEntry,
    loadGcodeForEntry,
    loadImplicitForEntry,
    loadUrdfForEntry,
    loadReferencesForEntry,
    loadDisplayEdgesForEntry
  };
}

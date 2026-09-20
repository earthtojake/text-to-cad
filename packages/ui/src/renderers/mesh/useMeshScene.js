import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { entryMeshAssetHash, entryMeshAssetUrl, meshAssetKeyForEntry } from "@hardcore/core/lib/entryAssets.js";
import { isAbortError } from "@hardcore/core/lib/renderAssetClient.js";
import { loadRenderMeshByUrl } from "@hardcore/core/lib/render/meshLoaders.js";
import { buildMeshObjects } from "@hardcore/core/lib/render/meshObjects.js";
import { createMeshScene } from "./meshScene.js";

const READING = Object.freeze({ phase: "read", label: "Reading model", done: 0, total: 0, determinate: false });
const LOADING = Object.freeze({ phase: "geometry", label: "Loading geometry", done: 0, total: 1, determinate: true });

/**
 * The entry's bytes as the scene on screen. The decode is core's and is cached
 * per file revision (parsed in a worker where there is one), so reopening a file
 * fetches and parses nothing; the scene is a set of views over it, built here
 * and owned here. A new revision of the same file replaces the scene when it is
 * ready, so the previous one stays visible meanwhile.
 *
 * @returns {{ scene: object | null, revision: string, busy: boolean, progress: object | null,
 *   error: unknown, empty: boolean }}  `empty`: the file loaded and holds no triangles.
 */
export function useMeshScene({ entry, resources }) {
  const url = entryMeshAssetUrl(entry);
  const revision = entryMeshAssetHash(entry);
  const format = meshAssetKeyForEntry(entry);
  const pending = entry?.catalogPending === true;
  const [state, setState] = useState({ scene: null, revision: "", busy: true, progress: READING, error: null, empty: false });
  const resourcesRef = useRef(resources);
  resourcesRef.current = resources;
  const sceneRef = useRef(null);
  const adopt = (scene) => {
    const previous = sceneRef.current;
    sceneRef.current = scene;
    previous?.dispose();
  };
  useEffect(() => () => adopt(null), []);
  useEffect(() => {
    if (pending) return undefined;
    if (!url) {
      adopt(null);
      const label = format.toUpperCase();
      setState({ scene: null, revision, busy: false, progress: null, empty: false,
        error: new Error(`${label} entry is missing ${label} asset: ${entry?.file || "(unknown)"}`) });
      return undefined;
    }
    const controller = new AbortController();
    setState(current => ({ ...current, busy: true, progress: current.scene ? current.progress : LOADING, error: null, empty: false }));
    loadRenderMeshByUrl(url, { resources: resourcesRef.current, signal: controller.signal, fallback: format }).then((meshData) => {
      if (controller.signal.aborted) return;
      const objects = buildMeshObjects(THREE, meshData);
      const scene = objects.length ? createMeshScene(THREE, objects) : null;
      adopt(scene);
      setState({ scene, revision, busy: false, progress: null, error: null, empty: !scene });
    }, (error) => {
      if (controller.signal.aborted || isAbortError(error)) return;
      adopt(null);
      setState({ scene: null, revision, busy: false, progress: null, error, empty: false });
    });
    return () => controller.abort();
  }, [url, revision, format, pending]);
  return state;
}

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { entryMeshAssetHash, entryMeshAssetUrl } from "@hardcore/core/lib/entryAssets.js";
import { isAbortError, loadRenderGlbDocument } from "@hardcore/core/lib/renderAssetClient.js";
import { disposeGlbDocument } from "@hardcore/core/lib/render/glbMeshData.js";
import { createGlbScene } from "./glbScene.js";

const READING = Object.freeze({ phase: "read", label: "Reading model", done: 0, total: 0, determinate: false });
const LOADING = Object.freeze({ phase: "geometry", label: "Loading geometry", done: 0, total: 1, determinate: true });

/**
 * The entry's bytes as the scene on screen. A new revision of the same file
 * replaces the scene when it is ready, so the previous one stays visible
 * meanwhile; the replaced scene, the scene of a closed file, and a document that
 * arrives after its request was abandoned are all released here. Nothing is
 * cached: a native scene is mutable animation state with exactly one owner.
 *
 * @returns {{ scene: object | null, revision: string, busy: boolean, progress: object | null, error: unknown }}
 */
export function useGlbScene({ entry, resources }) {
  const url = entryMeshAssetUrl(entry);
  const revision = entryMeshAssetHash(entry);
  const pending = entry?.catalogPending === true;
  const [state, setState] = useState({ scene: null, revision: "", busy: true, progress: READING, error: null });
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
      setState({ scene: null, revision, busy: false, progress: null,
        error: new Error(`GLB entry is missing its GLB asset: ${entry?.file || "(unknown)"}`) });
      return undefined;
    }
    const controller = new AbortController();
    setState(current => ({ ...current, busy: true, progress: current.scene ? current.progress : LOADING, error: null }));
    loadRenderGlbDocument(url, { resources: resourcesRef.current, signal: controller.signal }).then((document) => {
      if (controller.signal.aborted) { disposeGlbDocument(document); return; }
      const scene = createGlbScene(THREE, document);
      adopt(scene);
      setState({ scene, revision, busy: false, progress: null, error: null });
    }, (error) => {
      if (controller.signal.aborted || isAbortError(error)) return;
      adopt(null);
      setState({ scene: null, revision, busy: false, progress: null, error });
    });
    return () => controller.abort();
  }, [url, revision, pending]);
  return state;
}

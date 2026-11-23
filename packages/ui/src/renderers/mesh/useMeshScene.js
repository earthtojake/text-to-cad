import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { entryMeshAssetHash, entryMeshAssetUrl, meshAssetKeyForEntry } from "@cad/core/lib/entryAssets.js";
import { isAbortError } from "@cad/core/lib/renderAssetClient.js";
import { loadRenderMeshByUrl } from "@cad/core/lib/render/meshLoaders.js";
import { buildMeshScene } from "@cad/core/lib/render/meshScene.js";
import { loadStlBodies } from "@cad/core/lib/render/stlMeshWorkerClient.js";

const READING = Object.freeze({ phase: "read", label: "Reading model", done: 0, total: 0, determinate: false });
const LOADING = Object.freeze({ phase: "geometry", label: "Loading geometry", done: 0, total: 1, determinate: true });

/**
 * The entry's bytes as the scene on screen. The decode is core's and is cached
 * per file revision (parsed in a worker where there is one), so reopening a file
 * fetches and parses nothing; the scene is a set of views over it, built here
 * and owned here. A new revision of the same file replaces the scene when it is
 * ready, so the previous one stays visible meanwhile.
 *
 * An STL shows first as one body, the whole file (its row named `name`, the file's, or its one named solid's); its
 * bodies (`stlBodies.js`, split in the STL worker: on a million triangles the split takes about twice the parse) then
 * replace that scene with one a body a part, when there are several.
 *
 * @param {{ entry: object, resources: object, name?: string }} options  `name`: the file's.
 * @returns {{ scene: object | null, revision: string, busy: boolean, progress: object | null,
 *   error: unknown, empty: boolean, split: boolean }}  `empty`: the file loaded and holds no triangles. `split`: the
 *   scene is an STL's bodies, after its first.
 */
export function useMeshScene({ entry, resources, name = "" }) {
  const url = entryMeshAssetUrl(entry);
  const revision = entryMeshAssetHash(entry);
  const format = meshAssetKeyForEntry(entry);
  const [state, setState] = useState({ scene: null, revision: "", busy: true, progress: READING, error: null, empty: false, split: false });
  const nameRef = useRef(name);
  nameRef.current = name;
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
    if (!url) {
      adopt(null);
      const label = format.toUpperCase();
      setState({ scene: null, revision, busy: false, progress: null, empty: false, split: false,
        error: new Error(`${label} entry is missing ${label} asset: ${entry?.file || "(unknown)"}`) });
      return undefined;
    }
    const controller = new AbortController();
    setState(current => ({ ...current, busy: true, progress: current.scene ? current.progress : LOADING, error: null, empty: false }));
    const { signal } = controller;
    loadRenderMeshByUrl(url, { resources: resourcesRef.current, signal, fallback: format }).then((meshData) => {
      if (signal.aborted) return;
      const scene = buildMeshScene(THREE, meshData, { name: nameRef.current });
      adopt(scene);
      setState({ scene, revision, busy: false, progress: null, error: null, empty: !scene, split: false });
      if (!scene || format !== "stl" || meshData.parts?.length) return;
      // The model is on screen: now its bodies. One body is the scene already shown; a split that fails keeps it.
      loadStlBodies(meshData, { signal }).then((bodies) => {
        if (signal.aborted || !(bodies.parts?.length > 1)) return;
        const parted = buildMeshScene(THREE, bodies, { name: nameRef.current });
        adopt(parted);
        setState(current => ({ ...current, scene: parted, split: true }));
      }, () => {});
    }, (error) => {
      if (signal.aborted || isAbortError(error)) return;
      adopt(null);
      setState({ scene: null, revision, busy: false, progress: null, error, empty: false, split: false });
    });
    return () => controller.abort();
  }, [url, revision, format]);
  return state;
}

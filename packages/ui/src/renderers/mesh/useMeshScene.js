import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { entryMeshAssetHash, entryMeshAssetUrl, meshAssetKeyForEntry } from "@cad/core/lib/entryAssets.js";
import { entryKind, RENDER_FORMAT } from "@cad/core/lib/fileFormats.js";
import { isAbortError } from "@cad/core/lib/renderAssetClient.js";
import { loadRenderMeshByUrl } from "@cad/core/lib/render/meshLoaders.js";
import { buildMeshScene } from "@cad/core/lib/render/meshScene.js";

const READING = Object.freeze({ phase: "read", label: "Reading model", done: 0, total: 0, determinate: false });
const LOADING = Object.freeze({ phase: "geometry", label: "Loading geometry", done: 0, total: 1, determinate: true });

/**
 * The entry's bytes as the scene on screen. The decode is core's and is cached
 * per file revision (parsed in a worker where there is one), so reopening a file
 * fetches and parses nothing; the scene is a set of views over it, built here
 * and owned here. A new revision of the same file replaces the scene when it is
 * ready, so the previous one stays visible meanwhile.
 *
 * An OpenSCAD program's bytes are its text: its mesh is the STL the server renders of it with OpenSCAD
 * (`client.renderedMesh`, the document's `mesh` route, kept by the program's bytes), loaded as an STL once the
 * server has it; the catalog's hash of the program is its revision, so a saved edit loads the next render.
 *
 * @returns {{ scene: object | null, revision: string, busy: boolean, progress: object | null,
 *   error: unknown, empty: boolean }}  `empty`: the file loaded and holds no triangles.
 */
export function useMeshScene({ entry, resources, client }) {
  const url = entryMeshAssetUrl(entry);
  const revision = entryMeshAssetHash(entry);
  const rendered = entryKind(entry) === RENDER_FORMAT.SCAD;
  const format = rendered ? RENDER_FORMAT.STL : meshAssetKeyForEntry(entry);
  const file = entry?.file || "";
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
    if (!url) {
      adopt(null);
      const label = format.toUpperCase();
      setState({ scene: null, revision, busy: false, progress: null, empty: false,
        error: new Error(`${label} entry is missing ${label} asset: ${entry?.file || "(unknown)"}`) });
      return undefined;
    }
    if (rendered && typeof client?.renderedMesh !== "function") {
      adopt(null);
      setState({ scene: null, revision, busy: false, progress: null, empty: false,
        error: new Error(`This host cannot render OpenSCAD programs: ${file || "(unknown)"}`) });
      return undefined;
    }
    const controller = new AbortController();
    setState(current => ({ ...current, busy: true, progress: current.scene ? current.progress : LOADING, error: null, empty: false }));
    // The program's mesh is read where the server says it is, once rendered; every other mesh is its own bytes.
    const located = rendered
      ? client.renderedMesh(file, { signal: controller.signal })
      : Promise.resolve({ url });
    located.then(({ url: asset }) => loadRenderMeshByUrl(asset, { resources: resourcesRef.current, signal: controller.signal, fallback: format }))
      .then((meshData) => {
        if (controller.signal.aborted) return;
        const scene = buildMeshScene(THREE, meshData);
        adopt(scene);
        setState({ scene, revision, busy: false, progress: null, error: null, empty: !scene });
      }, (error) => {
        if (controller.signal.aborted || isAbortError(error)) return;
        adopt(null);
        setState({ scene: null, revision, busy: false, progress: null, error, empty: false });
      });
    return () => controller.abort();
  }, [url, revision, format, rendered, file, client]);
  return state;
}

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { buildFieldScene } from "@cad/core/lib/render/fieldScene.js";

const COMPILING = Object.freeze({ phase: "read", label: "Compiling field", done: 0, total: 0, determinate: false });

/**
 * The model's field as the scene on screen: one `GET <document>/field` for the file, then each
 * texture it names, built into the scene that marches it (`buildFieldScene`). The server keeps the
 * field by the model's bytes, so reopening a file compiles nothing. A new revision of the same file
 * replaces the scene when it is ready, so the previous one stays visible meanwhile, and stays, with
 * the error beside it, if that revision does not compile.
 *
 * @returns {{ scene: object | null, revision: string, busy: boolean, progress: object | null, error: unknown }}
 */
export function useFieldScene({ client, file, revision = "" }) {
  const [state, setState] = useState({ scene: null, file: "", revision: "", busy: true, progress: COMPILING, error: null });
  const sceneRef = useRef(null);
  const adopt = (scene) => {
    const previous = sceneRef.current;
    sceneRef.current = scene;
    previous?.dispose();
  };
  useEffect(() => () => adopt(null), []);
  useEffect(() => {
    if (!file) {
      adopt(null);
      setState({ scene: null, file, revision, busy: false, progress: null, error: new Error("This model has no file to read.") });
      return undefined;
    }
    const controller = new AbortController();
    const { signal } = controller;
    setState(current => ({ ...current, busy: true, progress: current.scene && current.file === file ? current.progress : COMPILING, error: null }));
    (async () => {
      const payload = await client.fieldPayload(file, { signal });
      const textures = Object.fromEntries(await Promise.all((payload.textures || []).map(
        async (texture) => [texture.name, await client.fieldTexture(file, texture.name, { signal })])));
      if (signal.aborted) return;
      const scene = buildFieldScene(THREE, payload, textures);
      adopt(scene);
      setState({ scene, file, revision, busy: false, progress: null, error: null });
    })().catch((error) => {
      if (signal.aborted) return;
      // A revision that does not compile leaves the one on screen there, the error beside it.
      setState(current => ({ scene: current.file === file ? current.scene : null, file, revision, busy: false, progress: null, error }));
    });
    return () => controller.abort();
  }, [client, file, revision]);
  return state;
}

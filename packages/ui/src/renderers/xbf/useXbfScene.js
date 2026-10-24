import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { isAbortError } from "@text-to-cad/core/lib/renderAssetClient.js";
import { loadXbfDocument, waitForXbfVersion } from "@text-to-cad/core/lib/xbf/xbfDocument.js";
import { createXbfScene } from "@text-to-cad/core/lib/xbf/xbfScene.js";

const SERVING = Object.freeze({ phase: "read", label: "Opening document", done: 0, total: 0, determinate: false });
// How long a page waits before asking an engine that stopped answering again.
const RETRY_MS = 1000;
// The least time from one ask for the next version to the next: the viewer holds an ask about this
// long, and a host whose calls share a few slots (the CAD app's) answers one at once.
const VERSION_PACE_MS = 1000;

const pause = (ms, signal) => new Promise((resolve, reject) => {
  const timer = setTimeout(resolve, ms);
  signal.addEventListener("abort", () => { clearTimeout(timer); reject(signal.reason); }, { once: true });
});

/**
 * A document the cadgen engine serves -- an `.xbf`, or a STEP -- as the scene on screen, kept current
 * with the engine.
 *
 * The viewer's server says where the page reads the file (`client.engineDocument`, through the
 * viewer, with the client's fetch); the page reads the structure and every part buffer
 * (`loadXbfDocument`) and builds the scene (`createXbfScene`, the builder a snapshot calls too).
 * Then it waits on the engine for the next version (`waitForXbfVersion`), about once a second: a
 * build that rewrites the document, or a STEP written again, answers at once, and the new version
 * is read with the old one as `previous`, so only the parts the edit changed are fetched and every
 * other part keeps its buffer and the geometry already uploaded. The new scene replaces the old when
 * it is ready, so the old one stays on screen meanwhile and the camera stays where it is. The same
 * wait hears the document's build: a build writing it answers with each stage it reaches
 * (`building`), and one that fails with its error (`failed`), until another begins or one succeeds.
 *
 * @param {{ client: { engineDocument?: Function }, file: string }} options
 * @returns {{ scene: object | null, document: object | null, revision: string, busy: boolean, progress: object | null,
 *   error: unknown, empty: boolean, update: { version: string, fetched: number, kept: number, ms: number } | null,
 *   building: object | null, failed: { model?: string, error?: string, progress?: object | null } | null }}
 *   `update`: the last version that arrived after the first, how many parts it fetched and kept, and the
 *   milliseconds from the engine's answer to its scene. `building`: the progress frame of the build
 *   writing the document now; `failed`: the last build of it that failed.
 */
export function useXbfScene({ client, file }) {
  const [state, setState] = useState({ scene: null, document: null, revision: "", busy: true, progress: SERVING, error: null, empty: false, update: null,
    building: null, failed: null });
  const held = useRef({ scene: null, document: null });
  const adopt = (scene, document) => {
    const previous = held.current;
    held.current = { scene, document };
    // The old scene first, then its document: parts the new version kept stay held by it.
    previous.scene?.dispose();
    previous.document?.release();
  };
  useEffect(() => () => adopt(null, null), []);
  useEffect(() => {
    if (!file) return undefined;
    const controller = new AbortController();
    const { signal } = controller;
    setState(current => ({ ...current, busy: true, progress: current.scene ? current.progress : SERVING, error: null, building: null, failed: null }));
    (async () => {
      if (typeof client?.engineDocument !== "function") {
        throw new Error("This viewer cannot open a cadgen engine document: its host serves no engine.");
      }
      let served = await client.engineDocument(file, { signal });
      let previous = held.current.document;
      let noticed = null;
      // The document's build as last heard, and its count (the engine's, which moves with each stage
      // and each outcome): the next wait is answered when it moves past it.
      let build = { building: null, failed: null };
      let counted = 0;
      for (;;) {
        const document = await loadXbfDocument(served.url, {
          previous, signal, fetch: served.fetch,
          onProgress: ({ done, total }) => {
            if (!previous) setState(current => ({ ...current, progress: { phase: "geometry", label: "Loading parts", done, total, determinate: true } }));
          }
        });
        if (signal.aborted) { document.release(); return; }
        const scene = createXbfScene(THREE, document);
        const update = noticed === null ? null : {
          version: document.version, fetched: document.load.fetched.length, kept: document.load.kept.length,
          ms: Math.round(performance.now() - noticed)
        };
        adopt(scene, document);
        setState({ scene, document, revision: document.version, busy: false, progress: null, error: null,
          empty: document.structure.instances.length === 0, update: update || held.current.update || null, ...build });
        held.current.update = update || held.current.update || null;
        previous = document;
        // The next version: the engine answers when a build lands or moves, else after its wait with this one.
        for (;;) {
          try {
            const asked = performance.now();
            const answer = await waitForXbfVersion(served.url, document.version, { signal, fetch: served.fetch, progress: counted });
            if (answer.progress !== null && answer.progress !== counted) {
              counted = answer.progress;
              build = { building: answer.building, failed: answer.failed };
              setState(current => ({ ...current, ...build }));
            }
            if (answer.version && answer.version !== document.version) { noticed = performance.now(); break; }
            const early = VERSION_PACE_MS - (performance.now() - asked);
            if (early > 0) await pause(early, signal);
          } catch (error) {
            if (signal.aborted || isAbortError(error)) throw error;
            // The engine went away (its daemon idled out or was stopped): ask for it again, which
            // starts it, and read the document from it as it has it now.
            await pause(RETRY_MS, signal);
            served = await client.engineDocument(file, { signal });
            noticed = performance.now();
            // An engine started afresh has heard of no build: its count starts again.
            counted = 0;
            build = { building: null, failed: null };
            break;
          }
        }
        setState(current => ({ ...current, busy: true }));
      }
    })().catch((error) => {
      if (signal.aborted || isAbortError(error)) return;
      setState(current => ({ ...current, busy: false, progress: null, error }));
    });
    return () => controller.abort();
  }, [client, file]);
  return state;
}

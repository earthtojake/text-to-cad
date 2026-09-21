import { useEffect, useRef, useState } from "react";
import { entryAssetUrl, entryMeshAssetHash } from "@hardcore/core/lib/entryAssets.js";
import { isAbortError, loadRenderDxf } from "@hardcore/core/lib/renderAssetClient.js";

const READING = Object.freeze({ phase: "read", label: "Reading model", done: 0, total: 0, determinate: false });
const LOADING = Object.freeze({ phase: "geometry", label: "Loading geometry", done: 0, total: 1, determinate: true });

/**
 * The entry's `.dxf`, parsed. A DXF is not artifact-managed — the backend never owns one —
 * so this is the whole of the load: fetch the text, parse it to millimetres, done. The parse
 * is memoized by core per file revision, so reopening a file parses nothing.
 *
 * A new revision of the same file replaces the document when it is ready, so the previous
 * one stays on screen meanwhile.
 *
 * @returns {{ dxf: object | null, revision: string, busy: boolean, progress: object | null, error: unknown }}
 */
export function useDxfDocument({ entry, resources }) {
  const url = entryAssetUrl(entry, "dxf");
  const revision = entryMeshAssetHash(entry);
  const pending = entry?.catalogPending === true;
  const [state, setState] = useState({ dxf: null, revision: "", busy: true, progress: READING, error: null });
  const resourcesRef = useRef(resources);
  resourcesRef.current = resources;
  useEffect(() => {
    if (pending) return undefined;
    if (!url) {
      setState({ dxf: null, revision, busy: false, progress: null,
        error: new Error(`DXF entry is missing its DXF asset: ${entry?.file || "(unknown)"}`) });
      return undefined;
    }
    const controller = new AbortController();
    setState(current => ({ ...current, busy: true, progress: current.dxf ? current.progress : LOADING, error: null }));
    loadRenderDxf(url, { resources: resourcesRef.current, signal: controller.signal }).then((dxf) => {
      if (controller.signal.aborted) return;
      setState({ dxf, revision, busy: false, progress: null, error: null });
    }, (error) => {
      if (controller.signal.aborted || isAbortError(error)) return;
      setState({ dxf: null, revision, busy: false, progress: null, error });
    });
    return () => controller.abort();
  }, [url, revision, pending]);
  return state;
}

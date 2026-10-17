import { useCallback, useEffect, useRef, useState } from "react";

/**
 * A press under a face or edge filter that named a PART: its faces and edges could not be picked
 * at the press. Either they were still to load, or they had landed since the press's raycast: a
 * load can land between a press and its release, and the viewport stamps a part's pick groups in
 * an effect after the commit that lists its faces as pickable (`useStepSceneSync`), so a press in
 * between finds the part. Both are one case. The press asks for the part's topology
 * (`loadTopology`, which costs nothing once it is requested) and is kept,
 * `{ partId, clientX, clientY, pointerType, multiSelect }`, to be picked again at the same point
 * once the part is among `loadedIds` and the view is `ready` -- on the commit after the press,
 * when it already is -- through `pickAtRef`, which the viewport fills in. What is under that point
 * then is activated exactly as a fresh press would be, faces-only filter and all: a part again is
 * nothing. One press waits at a time, the newest settling the one before it; `settle` drops it,
 * and so does a load that `failed`.
 *
 * @param {{
 *   pickAtRef: { current: ((clientX: number, clientY: number, pointerType: string) => string) | null },
 *   loadedIds: Set<string>,
 *   ready: boolean,
 *   failed: boolean,
 *   loadTopology: (partIds: string[]) => void,
 *   isTopologyReference: (referenceId: string) => boolean,
 *   activate: (referenceId: string, options: { multiSelect: boolean }) => void
 * }} options  `loadedIds`: the parts whose faces and edges the live composition holds; `ready`:
 *   that composition serves the view and nothing blocks interaction; `isTopologyReference`: the
 *   id names a face or edge the view can pick; `activate`: the press's activation, as the viewport
 *   would make it.
 */
export function usePendingTopologyPick({ pickAtRef, loadedIds, ready, failed, loadTopology, isTopologyReference, activate }) {
  const [pending, setPending] = useState(null);
  // The replay goes through this render's callbacks: the surface's activation is declared after
  // the hook is called.
  const latest = useRef(null);
  latest.current = { loadTopology, isTopologyReference, activate };
  const press = useCallback((partId, { clientX, clientY, pointerType = "", multiSelect = false } = {}) => {
    setPending({ partId, clientX, clientY, pointerType, multiSelect });
    latest.current.loadTopology([partId]);
  }, []);
  const settle = useCallback(() => setPending(null), []);
  useEffect(() => {
    if (!pending) return;
    if (failed) { setPending(null); return; }
    if (!ready || !loadedIds.has(pending.partId)) return;
    setPending(null);
    const referenceId = String(pickAtRef.current?.(pending.clientX, pending.clientY, pending.pointerType) || "").trim();
    if (referenceId && latest.current.isTopologyReference(referenceId)) {
      latest.current.activate(referenceId, { multiSelect: pending.multiSelect });
    }
  }, [pending, failed, ready, loadedIds, pickAtRef]);
  return { pending, press, settle };
}

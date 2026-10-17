import { useEffect, useSyncExternalStore } from "react";

// A face's exact area, which cadgen measures where a view asks for it (`POST /__cad/measure`,
// a build-pool job on the component's stored BREP) and no part's selector table carries. One view's
// faces, each asked for once and kept with the view: the Reference panel reads one through
// `useFaceArea`, and the measure tool's chip, drawn on its own frames, through `read`. A face's
// state is `none` (nothing to ask: not a face, or no view to ask about), `pending` (asked), `ready`
// (`area`, as cadgen measured it) or `failed`.

const NONE = Object.freeze({ state: "none" });
const PENDING = Object.freeze({ state: "pending" });
const FAILED = Object.freeze({ state: "failed" });

/**
 * `requestFor(reference)` is the measure request naming the face -- `{tree, viewId, producer,
 * cid, part, face}`, from the view it is a face of -- or null; `measure(body)` asks cadgen
 * (`CadClient.measureFace`).
 */
export function createFaceAreas({ requestFor, measure }) {
  const known = new Map();
  const listeners = new Set();
  const keyOf = (reference) => {
    const body = reference?.selectorType === "face" && Number.isInteger(reference?.pickData?.ordinal)
      ? requestFor?.(reference) : null;
    return body ? { body, key: `${body.tree}|${body.cid}|${body.face}` } : null;
  };
  const peek = (reference) => {
    const found = keyOf(reference);
    return found ? known.get(found.key) || NONE : NONE;
  };
  const request = (reference) => {
    const found = keyOf(reference);
    if (!found || known.has(found.key)) return;
    known.set(found.key, PENDING);
    const settle = (value) => {
      known.set(found.key, value);
      for (const listener of listeners) listener();
    };
    Promise.resolve()
      .then(() => measure(found.body))
      .then((reply) => settle(Number.isFinite(reply?.area) ? { state: "ready", area: reply.area } : FAILED),
        () => settle(FAILED));
    for (const listener of listeners) listener();
  };
  return {
    peek,
    request,
    /** `request` then `peek`: what a frame loop asks each frame. */
    read(reference) { request(reference); return peek(reference); },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
}

const noSubscription = () => () => {};

/** The face's area state for the panel showing it, asked for when the face is shown. */
export function useFaceArea(faceAreas, reference) {
  useEffect(() => { faceAreas?.request(reference); }, [faceAreas, reference]);
  return useSyncExternalStore(faceAreas?.subscribe || noSubscription, () => faceAreas?.peek(reference) || NONE);
}

import { useEffect, useRef } from "react";

// A part's named view applied to the viewport, as a machinist walks a drawing's views: seen down
// its camera, fitted to its part where the part stands (`fit`, the renderer's framing of the view's
// direction and up on the part's box), set through the viewer's own camera (`setPerspective`, as
// any camera handed it is); cut by its section through the Clip, whose settings it is
// (`store.patch({ clip })`); and, left, the camera and the Clip as they were before the first view
// was picked. From one view to the next they stay what they were before either. A view with no
// section, or one whose section its placement turns off the Clip's axes, leaves the Clip as the
// person had it. Which PMI it shows is the PMI's own (`useXbfPmi`): this moves the camera and cuts.

/**
 * @param {{ applied: { key: string, direction: number[], up: number[], bounds: { min: number[], max: number[] } | null,
 *     section: { axis: string, at: number, invert: boolean } | null } | null,
 *   viewer: () => ({ getPerspective?: () => object | null, setPerspective?: (camera: object) => boolean } | null | undefined),
 *   store: { getSnapshot: () => { display: Record<string, unknown> }, patch: (patch: object) => unknown, restore: (display: object) => unknown },
 *   fit: (applied: object) => object | null }} options
 *   `applied`: the view picked, placed (`useXbfPmi`'s `view`), or null for none; `viewer`: the
 *   viewport's handle now; `store`: the view's settings; `fit`: the camera that frames it.
 */
export function usePmiViewApplied({ applied, viewer, store, fit }) {
  // What the view replaced: the camera and the Clip before the first view was picked.
  const before = useRef(null);
  const latest = useRef(null);
  latest.current = { applied, viewer, store, fit };
  const signature = applied ? JSON.stringify([applied.key, applied.direction, applied.up, applied.section, applied.bounds]) : "";
  useEffect(() => {
    const { applied: view, viewer: handleOf, store: settings, fit: frame } = latest.current;
    const handle = handleOf();
    if (!view) {
      const was = before.current;
      before.current = null;
      if (!was) return;
      if (was.camera) handle?.setPerspective?.(was.camera);
      restoreClip(settings, was.clip);
      return;
    }
    before.current ??= { camera: handle?.getPerspective?.() || null, clip: settings.getSnapshot().display.clip };
    const camera = frame(view);
    if (camera) handle?.setPerspective?.(camera);
    if (view.section) settings.patch({ clip: { enabled: true, ...view.section } });
    else restoreClip(settings, before.current.clip);
  }, [signature]);
  // Gone with a view applied (the file closed): its cut is not left as the person's Clip.
  useEffect(() => () => {
    if (before.current) restoreClip(latest.current.store, before.current.clip);
  }, []);
}

// The Clip as it was: its settings, or none where the display had none.
function restoreClip(store, clip) {
  const { clip: now, ...display } = store.getSnapshot().display;
  if (JSON.stringify(now) === JSON.stringify(clip)) return;
  store.restore(clip === undefined ? display : { ...display, clip });
}

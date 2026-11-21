import { useCallback, useMemo, useRef, useState } from "react";

/**
 * Preview mode's one state: the viewer with its tools put away, the model drawn in Render, where its
 * routines play and it orbits on request. The shell holds it unless the renderer passes it in
 * (`useRendererShell`'s `preview`); a view outside the shell that offers Preview holds its own
 * (`useFlatPreview.jsx`).
 * `now()` is the state as last set, before React renders it: what a command preview's own crossing
 * calls (its routine played on the way in) asks of it.
 * @returns {{ previewing: boolean, set: (previewing: boolean) => void, now: () => boolean }}
 */
export function usePreviewState() {
  const [previewing, setPreviewing] = useState(false);
  const latest = useRef(false);
  const set = useCallback(next => { latest.current = Boolean(next); setPreviewing(Boolean(next)); }, []);
  const now = useCallback(() => latest.current, []);
  return useMemo(() => ({ previewing, set, now }), [previewing, set, now]);
}

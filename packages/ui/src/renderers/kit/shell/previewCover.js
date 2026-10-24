// When Preview's cover ("Preparing preview…") lifts, as one decision the shell asks again each
// time the view has been quiet for a moment (`RendererShell.jsx`).
//
// It waits while Preview's view has not presented its first frame or published geometry is still on
// its way. Then it lifts on a converged picture (every sample of the studio frame drawn), or at
// once for a view that is MOVING — the camera orbiting, a routine playing — whose picture starts
// again every frame and never converges. Motion is what the shell knows it set going, never a
// sample count that fell: more components landing starts the picture again too, and that is a picture
// still to wait for, not motion. A cap (`RendererShell`'s) lifts it whatever happens.

/**
 * @param {{ presented: boolean, loading: boolean, moving: boolean,
 *   progress: { sample: number, samples: number } | null }} view
 * @returns {"wait" | "converge" | "lift"}  `wait`: ask again after a quiet moment; `converge`: the
 *   picture is still accumulating, ask again shortly; `lift`: take the cover away.
 */
export function previewCoverStep({ presented, loading, moving, progress }) {
  if (!presented || loading) return "wait";
  if (moving) return "lift";
  if (progress && progress.sample < progress.samples) return "converge";
  return "lift";
}

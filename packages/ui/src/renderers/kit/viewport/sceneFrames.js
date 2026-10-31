/**
 * The frame a pass over the scene asks for. Shadow maps (and the Render floor shadow baked
 * from them) are re-rendered only when the pass changed what casts them: a highlight, a
 * hover, a selection or a pass that re-ran without moving anything keeps the maps it has
 * (`runtime.requestFrame`), as a frame that only moved the camera does. A runtime without
 * that kind of frame gets an ordinary one, which re-renders them.
 *
 * @param {{ requestRender?: () => void, requestFrame?: () => void } | null | undefined} runtime
 * @param {boolean} castersChanged
 */
export function requestSceneFrame(runtime, castersChanged) {
  if (!castersChanged && typeof runtime?.requestFrame === "function") runtime.requestFrame();
  else runtime?.requestRender?.();
}

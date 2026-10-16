/**
 * Draw mode's target over a flat picture (`useDrawingViewLock.js`): the picture's view follows the
 * drawing editor. The editor maps its scene to the pane as `(scene + scroll) * zoom`; the picture maps
 * its plane as `x * scale + offsetX`, `-y * scale + offsetY`. Taken together at one moment (the lock:
 * the picture's transform and the editor's viewport then), every later viewport moves the picture by
 * the same scroll and zoom, so a point under the ink stays under it — through a change of the pane's
 * size too, where the editor keeps its scroll and zoom against the pane's corner while the picture
 * would refit or keep its centre.
 */

/** The picture's view for the editor's `viewport`, given the picture's view and the editor's when they were locked together. */
export function planeViewForViewport(lock, viewport) {
  const { transform, viewport: start } = lock;
  const zoom = viewport.zoom / start.zoom;
  return {
    scale: transform.scale * zoom,
    offsetX: (transform.offsetX / start.zoom - start.scrollX + viewport.scrollX) * viewport.zoom,
    offsetY: (transform.offsetY / start.zoom - start.scrollY + viewport.scrollY) * viewport.zoom,
  };
}

/**
 * @param {{ transformRef: { current: object | null }, setView(transform: object): void, paintNow?: () => void,
 *   canvasRef: { current: HTMLCanvasElement | null } }} plane  The picture's view (`kit/plane/usePlaneView.js`).
 * @returns {import("./useDrawingViewLock.js").DrawingViewTarget}
 */
export function planeDrawingTarget(plane) {
  return {
    // The plane view sizes its canvas in its own observer, on the pane; this one, on the canvas,
    // hears of the change after that, and puts the picture back before the frame shows it refitted.
    host: plane.canvasRef,
    capture(viewport) {
      const transform = plane.transformRef.current;
      return transform ? { transform: { ...transform }, viewport: { ...viewport } } : null;
    },
    apply(lock, viewport, { resized }) {
      plane.setView(planeViewForViewport(lock, viewport));
      if (resized) plane.paintNow?.();
    }
  };
}

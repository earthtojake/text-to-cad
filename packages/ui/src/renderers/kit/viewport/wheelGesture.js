/**
 * What a wheel event does to a flat view (a board, a schematic, a drawing), as Figma and KiCad's
 * trackpad mode read it: a pinch (a ctrl-wheel, as every browser reports one) or a wheel with Cmd
 * or Ctrl held zooms about the pointer; a mouse's wheel zooms; a trackpad's two-finger scroll (or a
 * Magic Mouse's swipe, or a touchpad's on another system) pans, both ways at once.
 *
 * A mouse and a trackpad send the same event; what tells them apart:
 * - a wheel that counts in lines or pages (`deltaMode` 1 or 2: Firefox's mouse) is a mouse;
 * - one that moves sideways too (`deltaX`) is a trackpad;
 * - where the browser still sends the legacy `wheelDeltaY` (Chrome, Safari, Edge), a trackpad's is
 *   exactly -3 times its `deltaY`, a mouse's notch is 120 and its `deltaY` not a third of that;
 * - without it, a whole-pixel step of 50 or more is a mouse's notch, anything finer a trackpad's.
 * A gesture is read once, at its first event, and kept until the wheel has rested for
 * `GESTURE_GAP_MS`: a trackpad's momentum tail never turns a pan into a zoom halfway through.
 */

const LINE_HEIGHT_PX = 16;
const PAGE_HEIGHT_PX = 400;
/** How long the wheel rests before the next event starts a new gesture. */
export const GESTURE_GAP_MS = 160;

/** Whether one wheel event, alone, reads as a trackpad's scroll (not a pinch, a modifier zoom or a mouse). */
export function isTrackpadScroll(event) {
  if (event.ctrlKey || event.metaKey) return false;
  if (event.deltaMode !== 0) return false;
  if (event.deltaX !== 0) return true;
  const legacy = event.wheelDeltaY;
  if (typeof legacy === "number" && legacy !== 0) return legacy === -3 * event.deltaY;
  return !(Number.isInteger(event.deltaY) && Math.abs(event.deltaY) >= 50);
}

/** The event's deltas in CSS pixels. */
export function wheelPixels(event) {
  const unit = event.deltaMode === 1 ? LINE_HEIGHT_PX : event.deltaMode === 2 ? PAGE_HEIGHT_PX : 1;
  return { x: event.deltaX * unit, y: event.deltaY * unit };
}

/**
 * A reader of one view's wheel: `read(event)` is `{ pan: { x, y } }`, the view to move by in CSS
 * pixels (the content follows the fingers, as a page scrolls), or `{ zoom: y }`, the pixels of
 * vertical delta to zoom by (the caller's speed: `pinch` says a pinch's finer deltas).
 */
export function createWheelGesture({ now = () => performance.now() } = {}) {
  let panning = false;
  let last = -Infinity;
  return function read(event) {
    const at = now();
    const fresh = at - last > GESTURE_GAP_MS;
    last = at;
    // A pinch is a zoom whenever it comes, even in the middle of a scroll.
    if (event.ctrlKey || event.metaKey) return { zoom: wheelPixels(event).y, pinch: event.ctrlKey };
    if (fresh) panning = isTrackpadScroll(event);
    const delta = wheelPixels(event);
    return panning ? { pan: { x: -delta.x || 0, y: -delta.y || 0 } } : { zoom: delta.y, pinch: false };
  };
}

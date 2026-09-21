// Camera matrix/OrbitControls round trips can move the last floating-point
// bits forever after a gesture. Those are not new LOD work or retry intent.
// Keep this far below a visible pixel; compare against the last meaningful
// sample so a sequence of small, real movements still accumulates.
export function lodSampleNumberEqual(a, b) {
  return Object.is(a, b) || (Number.isFinite(a) && Number.isFinite(b)
    && Math.abs(a - b) <= 1e-10 * Math.max(1, Math.abs(a), Math.abs(b)));
}

/**
 * The box an FEA result's model is drawn in over its whole series. The file's positions carry one
 * frame's displacement (the first: a nonlinear run's first load step, a mode's first shape), but
 * Study opens on another (the last load step, the peak) and a scrubber or Play shows them all: a
 * rubber strap stretched to twice its length at the last step leaves the box of its first. The
 * viewport frames that box and fits the camera's near and far planes to it, so a model drawn
 * outside it is sliced off by the near plane in an oblique view (the top view, looking down the
 * other axis, still shows it whole). The box here holds every frame at the file's own deformation
 * scale, so the framing never jumps while the series plays (as a GLB's animation clips are
 * sampled into theirs at load, `createGlbScene`). A result with no series is drawn as the file
 * holds it: its box is the file's.
 */
import { DISPLACEMENT, deformationAt } from "./fea/series.js";

/**
 * `scene.bounds` grown to hold every frame of `fea`'s series at its deformation scale, as `{ min, max }`
 * in the scene's space; null where there is nothing to grow (no series, no positions).
 */
export function feaDrawnBounds(THREE, scene, fea) {
  const mesh = fea?.mesh;
  const frames = fea?.series?.frames || [];
  const geometry = mesh?.geometry;
  const position = geometry?.getAttribute("position");
  if (!scene?.bounds || !position || position.itemSize !== 3 || frames.length < 2) return null;
  const count = position.count;
  const at = position.array;
  const baked = geometry.getAttribute(DISPLACEMENT);
  const scale = Number(fea.deformationScale) || 0;
  const rest = new Float32Array(at.length);
  const bakedArray = baked?.itemSize === 3 && baked.count === count ? baked.array : null;
  for (let i = 0; i < at.length; i += 1) rest[i] = at[i] - (bakedArray ? scale * bakedArray[i] : 0);
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  const take = (vectors) => {
    for (let i = 0; i < count; i += 1) {
      for (let c = 0; c < 3; c += 1) {
        const value = rest[3 * i + c] + (vectors ? scale * vectors[3 * i + c] : 0);
        if (value < low[c]) low[c] = value;
        if (value > high[c]) high[c] = value;
      }
    }
  };
  take(bakedArray);
  for (let index = 0; index < frames.length; index += 1) {
    const { attribute } = deformationAt(fea, index);
    const vectors = attribute ? geometry.getAttribute(attribute) : null;
    if (vectors?.itemSize === 3 && vectors.count === count) take(vectors.array);
  }
  if (!low.every(Number.isFinite)) return null;
  scene.object3D?.updateWorldMatrix?.(true, true);
  const box = new THREE.Box3(new THREE.Vector3(...low), new THREE.Vector3(...high)).applyMatrix4(mesh.matrixWorld);
  box.union(new THREE.Box3(new THREE.Vector3(...scene.bounds.min), new THREE.Vector3(...scene.bounds.max)));
  return { min: box.min.toArray(), max: box.max.toArray() };
}

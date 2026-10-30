/**
 * The box an FEA result's model is drawn in over its Load ramp. The file's positions carry the
 * displacement at the file's own deformation scale, but Study may open on another (its
 * Deformation or Load) and Preview's Load ramp plays the load going on from none to the load shown:
 * the viewport frames that box and fits the camera's near and far planes to it, so a model drawn
 * outside it would be sliced off by the near plane in an oblique view. The box here holds the part
 * at rest, as the file holds it, and as drawn at the deformation and load it opens on; the positions
 * are linear in the load, so every moment of the ramp is inside it, and Preview frames the camera
 * once on it without zooming while it plays.
 */
import { DISPLACEMENT } from "./feaResult.js";

/**
 * `scene.bounds` grown to hold `fea`'s model at rest, as the file holds it and as it is drawn at
 * `scale` (the deformation shown, the file's by default) and `load` (the load shown, 1 by default),
 * as `{ min, max }` in the scene's space; null for a scene with no bounds to grow. Every result carries
 * its displacement (`readFeaResult` reads none without it).
 */
export function feaDrawnBounds(THREE, scene, fea, { scale = fea.deformationScale, load = 1 } = {}) {
  if (!scene?.bounds) return null;
  const mesh = fea.mesh;
  const at = mesh.geometry.getAttribute("position").array;
  const d = mesh.geometry.getAttribute(DISPLACEMENT).array;
  const fileScale = fea.deformationScale;
  const drawn = (Number(scale) || 0) * (Number(load) || 0);
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < at.length; i += 1) {
    const rest = at[i] - fileScale * d[i];
    const c = i % 3;
    for (const value of [rest, at[i], rest + drawn * d[i]]) {
      if (value < low[c]) low[c] = value;
      if (value > high[c]) high[c] = value;
    }
  }
  if (!low.every(Number.isFinite)) return null;
  scene.object3D?.updateWorldMatrix?.(true, true);
  const box = new THREE.Box3(new THREE.Vector3(...low), new THREE.Vector3(...high)).applyMatrix4(mesh.matrixWorld);
  box.union(new THREE.Box3(new THREE.Vector3(...scene.bounds.min), new THREE.Vector3(...scene.bounds.max)));
  return { min: box.min.toArray(), max: box.max.toArray() };
}

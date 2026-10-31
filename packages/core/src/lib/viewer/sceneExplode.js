// Explode over a family's scene (`sceneContract.js`): a GLB of several parts. The layout is a
// STEP's (`explodedView.js`: each level of the file's tree blooms radially out of its parent, over
// one 0..1 slider), and the scene moves the objects it named as its parts: each by its own share
// of the bloom, in its parent's frame, from where it was authored. The viewer's viewport and the
// parity page's headless stage both explode through this, so the two cannot differ.

import { applyExplodedViewProgress, computeExplodedViewLayout, explodedViewBounds } from "./explodedView.js";

const clamp01 = value => Math.min(Math.max(Number(value) || 0, 0), 1);

function worldBox(THREE, object, own) {
  const box = new THREE.Box3();
  object.updateWorldMatrix(true, false);
  for (const mesh of own) box.expandByObject(mesh, false);
  return box.isEmpty() ? null : { min: box.min.toArray(), max: box.max.toArray() };
}

/**
 * @param {typeof import("three")} THREE
 * @param {import("three").Object3D} root  The scene's root, its placement fixed.
 * @param {{ object: import("three").Object3D, path: string, meshes: import("three").Object3D[] }[]} parts
 *   What moves, in the file's tree order (an object before those under it). `path`: its place in
 *   that tree, "o1.2.3" (`explodedView.js` groups levels by it). `meshes`: what of it is its own,
 *   which its box is measured on.
 * @param {{ min: number[], max: number[] }} restBounds  The scene at rest: what the bloom radiates from.
 * @returns {{ parts: number, set(amount: number): { min: number[], max: number[] } }}
 *   `parts`: how many it moves (none for fewer than two). `set` places them `amount` of the way
 *   out and returns the box they make there.
 */
export function createSceneExplode(THREE, root, parts, restBounds) {
  // Where each part was authored, taken now, before anything (a routine) moves it. The layout is
  // measured the first time Explode is used, never at load: a file of thousands of nodes pays for
  // it only if it is exploded.
  const rest = parts.map(part => part.object.position.clone());
  let records = null, layout = null;
  const prepare = () => {
    parts.forEach((part, index) => part.object.position.copy(rest[index]));
    root.updateMatrixWorld(true);
    records = parts.map((part, index) => ({
      partId: part.path, mesh: part.object, object: part.object,
      partBounds: worldBox(THREE, part.object, part.meshes), rest: rest[index], explodedViewMatrix: null
    })).filter(record => record.partBounds);
    const byObject = new Map(records.map(record => [record.object, record]));
    // Each part's nearest ancestor that is a part too: it carries the part with it, so the part
    // moves by what its own offset adds to the ancestor's.
    for (const record of records) {
      for (let parent = record.object.parent; parent && parent !== root; parent = parent.parent) {
        if (byObject.has(parent)) { record.carrier = byObject.get(parent); break; }
      }
    }
    layout = computeExplodedViewLayout(records, restBounds);
  };
  const offset = new THREE.Vector3(), inherited = new THREE.Vector3(), linear = new THREE.Matrix3();
  const worldOffset = (record, into) => (record.explodedViewMatrix ? into.setFromMatrixPosition(record.explodedViewMatrix) : into.set(0, 0, 0));
  return {
    parts: parts.length > 1 ? parts.length : 0,
    set(amount) {
      const progress = clamp01(amount);
      if (!records) { if (!progress) return restBounds; prepare(); }
      applyExplodedViewProgress(THREE, layout, progress);
      // Parents first: a part's frame is where its parent now is.
      for (const record of records) {
        record.object.position.copy(record.rest);
        worldOffset(record, offset);
        if (record.carrier) offset.sub(worldOffset(record.carrier, inherited));
        if (offset.lengthSq() > 0 && record.object.parent) {
          record.object.parent.updateWorldMatrix(true, false);
          offset.applyMatrix3(linear.setFromMatrix4(record.object.parent.matrixWorld).invert());
          record.object.position.add(offset);
        }
        record.object.updateMatrixWorld(true);
      }
      root.updateMatrixWorld(true);
      return explodedViewBounds(layout, restBounds, progress) || restBounds;
    }
  };
}

import { createSurfaceLook } from "../viewer/surfaceLook.js";
import { disposeGlbDocument } from "./glbMeshData.js";

function boundsOf(THREE, root) {
  root.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(root, true);
  if (box.isEmpty()) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min: box.min.toArray(), max: box.max.toArray() };
}

/**
 * A GLB's scene (`../viewer/sceneContract.js`): the file's NATIVE glTF hierarchy,
 * always. Nodes, skins, morph targets and authored materials are the file's own;
 * the scene places them in CAD space, wears the look its host resolves, and owns
 * the document from here on (`dispose()` releases its geometry, materials and
 * textures). The ONE builder of a GLB's scene: the viewer's GLB renderer and the
 * snapshot CLI's headless stage both call it, so neither can draw a GLB the other
 * does not.
 *
 * @param {typeof import("three")} THREE
 * @param {{ scene: import("three").Object3D, clips: object[], cadRootMatrix: number[],
 *   animatedBounds: object | null, restBounds: object | null }} document  `buildGlbDocumentFromBuffer`.
 * @returns {import("../viewer/sceneContract.js").KitScene & { document: object, meshCount: number }}
 */
export function createGlbScene(THREE, document) {
  const root = new THREE.Group();
  root.name = "glb-document";
  root.matrix.fromArray(document.cadRootMatrix);
  root.matrixAutoUpdate = false;
  root.matrixWorldNeedsUpdate = true;
  root.add(document.scene);
  document.scene.traverse((object) => {
    // The viewer owns one lighting rig in both Inspect and Render. Keep the authored
    // hierarchy, but never let embedded punctual lights build a second, file-specific one.
    if (object.isLight) { object.visible = false; return; }
    if (!object.isMesh) return;
    object.castShadow = true;
    // Three caches local culling bounds. Bone deformation and morph displacement
    // leave the rest-pose box while the hierarchy and the framing box stay correct.
    if (object.isSkinnedMesh || object.morphTargetInfluences?.length) object.frustumCulled = false;
  });
  const look = createSurfaceLook(THREE, document.scene);
  // One box for framing, lighting and the floor: a routine poses the model inside
  // the box sampled over every clip at load, so playing one never re-frames it.
  const bounds = document.animatedBounds || document.restBounds || boundsOf(THREE, root);
  let disposed = false;
  return {
    document,
    meshCount: look.meshCount,
    object3D: root,
    bounds,
    restBounds: bounds,
    setSurfaceLook(next) { if (!disposed) look.apply(next); },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      look.dispose();
      disposeGlbDocument(document);
    }
  };
}

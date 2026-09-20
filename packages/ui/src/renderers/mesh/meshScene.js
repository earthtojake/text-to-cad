import { createSurfaceLook } from "@hardcore/core/lib/viewer/surfaceLook.js";

function boundsOf(THREE, objects) {
  const box = new THREE.Box3();
  for (const { geometry } of objects) {
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    box.union(geometry.boundingBox);
  }
  if (box.isEmpty()) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min: box.min.toArray(), max: box.max.toArray() };
}

/**
 * The mesh renderer's scene (`kit/scene.js`): one `Mesh` per object of the file,
 * and nothing else. A triangle mesh authors no finish, so it wears the viewer's
 * surface in Solid and the studio's in Render; all a file can say is an object's
 * colour, which "Original" keeps. An object without one is marked
 * `userData.cadSourceColor = false` and takes the viewer's surface colour.
 *
 * @param {typeof import("three")} THREE
 * @param {import("@hardcore/core/lib/render/meshObjects.js").MeshObject[]} objects  `buildMeshObjects`.
 *   The scene owns their geometries from here on.
 * @returns {import("../kit/scene.js").KitScene & { meshCount: number }}
 */
export function createMeshScene(THREE, objects) {
  const root = new THREE.Group();
  root.name = "mesh-document";
  const materials = objects.map((object) => {
    const material = new THREE.MeshPhysicalMaterial({ color: object.color || 0xffffff, side: THREE.DoubleSide });
    material.userData.cadSourceColor = Boolean(object.color);
    const mesh = new THREE.Mesh(object.geometry, material);
    mesh.name = object.name;
    mesh.castShadow = true;
    // Where "Color by part" deals this object its palette colour.
    mesh.userData.cadFillIndex = object.paletteIndex;
    root.add(mesh);
    return material;
  });
  const look = createSurfaceLook(THREE, root);
  const bounds = boundsOf(THREE, objects);
  let disposed = false;
  return {
    meshCount: objects.length,
    object3D: root,
    bounds,
    restBounds: bounds,
    // Nothing here was authored, so Render is a look like any other: the studio's
    // surface over the same colours, never a finish "kept".
    setSurfaceLook(next) { if (!disposed) look.apply(next ? { ...next, authored: false } : null); },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      look.dispose();
      for (const material of materials) material.dispose();
      for (const { geometry } of objects) geometry.dispose();
    }
  };
}

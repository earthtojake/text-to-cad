import { axisIndex, clipAxisPosition, normalizeStepClipSettings } from "@text-to-cad/core/lib/viewer/clipPlane.js";

/**
 * An FEA result's section cut: the view's Clip (`clip` in its resolved Display settings) as one
 * clipping plane on the result's mesh, so the inside of a part — a channel's walls, a tank's
 * floor, the flow's surfaces past an opening — shows in the field's own colours. Its vertex
 * colours are untouched: the plane only discards what lies past it. No cap is drawn over the cut:
 * a result is its surfaces, both sides drawn, so the cut opens onto what is inside.
 *
 * The plane is set on whatever material the mesh draws with at each frame (`onBeforeRender`),
 * so it follows a surface look that swaps the material (Inspect's stand-in, Render's own). It
 * cuts through `bounds` (the box the result is drawn in over its whole series, in the scene's
 * own space) as the slider says; the scene's placement in the viewport (`root.parent`) carries it
 * to where the mesh is drawn. Markers keep standing whole: they are the study's, not the part.
 *
 * @param {typeof import("three")} THREE
 * @param {import("three").Mesh} mesh  The result's mesh.
 * @param {import("three").Object3D} root  The scene's root: the plane is in its parent's space.
 * @returns {{ set(clip: object | null, bounds: object | null): boolean, plane(): import("three").Plane | null, dispose(): void }}
 */
export function createFeaClip(THREE, mesh, root) {
  const local = new THREE.Plane();
  const world = new THREE.Plane();
  const planes = [world];
  const none = [];
  const identity = new THREE.Matrix4();
  // Every material the mesh has drawn with, so letting go clears each.
  const touched = new Set();
  let active = false;
  let key = "";
  const own = mesh.onBeforeRender;
  const toWorld = () => world.copy(local).applyMatrix4(root.parent ? root.parent.matrixWorld : identity);
  mesh.onBeforeRender = function onBeforeRender(renderer, scene, camera, geometry, material, group) {
    if (active) toWorld();
    const wanted = active ? planes : none;
    if (material && material.clippingPlanes !== wanted) { material.clippingPlanes = wanted; touched.add(material); }
    return own.call(this, renderer, scene, camera, geometry, material, group);
  };
  return {
    /** Cut as `clip` says (null, off or at its neutral end: no cut). True when that changed what is drawn. */
    set(clip, bounds) {
      const settings = clip ? normalizeStepClipSettings(clip) : null;
      const neutral = settings?.invert ? 0 : 1;
      const cuts = Boolean(settings?.enabled && bounds && Math.abs(settings.offset - neutral) > 1e-6);
      const next = cuts ? JSON.stringify([settings.axis, settings.offset, settings.invert, bounds.min, bounds.max]) : "";
      if (next === key) return false;
      key = next;
      active = cuts;
      if (cuts) {
        // The kept half is the lower coordinates, the cut facing the default camera; invert keeps the other.
        const index = axisIndex(settings.axis);
        const normal = new THREE.Vector3().setComponent(index, settings.invert ? 1 : -1);
        const point = new THREE.Vector3().setComponent(index, clipAxisPosition(bounds, settings));
        local.setFromNormalAndCoplanarPoint(normal, point);
      }
      return true;
    },
    /** The cut where the mesh is drawn (world space), or null with none: a pick on its far side is not a pick. */
    plane() { return active ? toWorld() : null; },
    dispose() {
      mesh.onBeforeRender = own;
      active = false;
      key = "";
      for (const material of touched) if (material.clippingPlanes === planes || material.clippingPlanes === none) material.clippingPlanes = null;
      touched.clear();
    },
  };
}

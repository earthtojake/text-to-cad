import { readSourceColor } from './surfaceMaterials.js';

// Stencil winding borrows display geometry. Each part's winding pair is followed
// by its own opaque fill, preserving both color and holes. The fill writes the
// stencil back to 0 wherever it covers (Replace with ref 0, on pass and fail
// alike), and it covers the whole model on the plane, where every winding lies:
// the next part starts from a clear stencil without clearing the buffer per part
// (a full-screen clear each, which cost more than all the parts' draws).
function disposeCut(cut) {
  for (const mesh of cut.stencils) {
    mesh.removeFromParent();
    mesh.material.dispose();
  }
  cut.plane.removeFromParent();
  cut.plane.material.dispose();
}

export function disposeSectionCaps(runtime) {
  const caps = runtime?.sectionCaps;
  if (!caps) return;
  for (const cut of caps.cuts.values()) disposeCut(cut);
  caps.geometry.dispose();
  runtime.sectionCaps = null;
}

export function syncSectionCaps(runtime, clipPlane, settings = null) {
  const partColors = settings?.partColors !== false;
  const THREE = runtime?.THREE;
  const parent = runtime?.scene || runtime?.modelGroup?.parent;
  if (!THREE || !parent || !clipPlane) {
    disposeSectionCaps(runtime);
    return;
  }
  // Reuse cached bounds; uncut parts need no stencil passes. Stencils stay
  // under their display mesh, so hiding/showing a part takes effect without
  // a Clip update. With no stencil pixels its cap writes nothing.
  const records = (runtime.displayRecords || []).filter(record => {
    const mesh = record.mesh;
    if (!mesh?.geometry) return false;
    mesh.updateWorldMatrix(true, false);
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    return mesh.geometry.boundingBox?.clone().applyMatrix4(mesh.matrixWorld).intersectsPlane(clipPlane);
  });
  if (!records.length) {
    disposeSectionCaps(runtime);
    return;
  }
  const caps = runtime.sectionCaps ||= { cuts: new Map(), geometry: new THREE.PlaneGeometry(1, 1) };
  const active = new Set(records.map(record => record.mesh));
  for (const [mesh, cut] of caps.cuts) {
    if (active.has(mesh) && cut.stencils[0].geometry === mesh.geometry) continue;
    disposeCut(cut);
    caps.cuts.delete(mesh);
  }
  const size = Math.max(1, Number(runtime.modelRadius || 1) * 4);
  const bounds = runtime.modelBounds;
  const center = new THREE.Vector3();
  if (bounds?.min && bounds?.max) center.set(...bounds.min.map((value, i) => (value + bounds.max[i]) / 2));
  if (runtime.modelGroup?.position) center.add(runtime.modelGroup.position);
  for (const [index, record] of records.entries()) {
    let cut = caps.cuts.get(record.mesh);
    if (!cut) {
      const material = new THREE.MeshBasicMaterial({
        side: THREE.DoubleSide,
        stencilWrite: true, stencilRef: 0, stencilFunc: THREE.NotEqualStencilFunc,
        stencilFail: THREE.ReplaceStencilOp, stencilZFail: THREE.ReplaceStencilOp, stencilZPass: THREE.ReplaceStencilOp,
        polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
      });
      const plane = new THREE.Mesh(caps.geometry, material);
      plane.name = 'Section fill';
      plane.frustumCulled = false;
      plane.raycast = () => {};
      parent.add(plane);
      const stencils = [
        [THREE.BackSide, THREE.IncrementWrapStencilOp],
        [THREE.FrontSide, THREE.DecrementWrapStencilOp]
      ].map(([side, operation]) => {
        const stencilMaterial = new THREE.MeshBasicMaterial({
          side, colorWrite: false, depthWrite: false, depthTest: false,
          stencilWrite: true, stencilFunc: THREE.AlwaysStencilFunc,
          stencilFail: operation, stencilZFail: operation, stencilZPass: operation,
        });
        const mesh = new THREE.Mesh(record.mesh.geometry, stencilMaterial);
        mesh.name = 'Section stencil';
        mesh.raycast = () => {};
        record.mesh.add(mesh);
        return mesh;
      });
      cut = { plane, stencils };
      caps.cuts.set(record.mesh, cut);
    }
    // Never copy the live material: selection/hover can tint it and change its
    // transparency. Normal choreography color, like base display color, is stable.
    cut.plane.material.color.copy(partColors
      ? readSourceColor(THREE, record.effectStyle?.color) || record.baseColor || record.mesh.userData.cadBaseColor
        || (Array.isArray(record.mesh.material) ? record.mesh.material[0] : record.mesh.material)?.color
        || new THREE.Color(0xe9a451)
      : new THREE.Color(0xe9a451));
    cut.stencils.forEach((mesh, pass) => {
      mesh.renderOrder = 1000 + index * 3 + pass;
      mesh.material.clippingPlanes = [clipPlane];
    });
    cut.plane.renderOrder = 1002 + index * 3;
    cut.plane.scale.set(size, size, 1);
    clipPlane.projectPoint(center, cut.plane.position);
    cut.plane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), clipPlane.normal);
  }
}

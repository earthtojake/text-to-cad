// Read-only section fill using stencil winding, as in Three.js's clipping
// example: https://threejs.org/examples/webgl_clipping_stencil.html
// Borrow display geometry; never rebuild the solid or add selectable faces.
export function disposeSectionCaps(runtime) {
  const caps = runtime?.sectionCaps;
  if (!caps) return;
  for (const mesh of caps.stencils) {
    mesh.removeFromParent();
    mesh.material.dispose(); // geometry belongs to the original display mesh
  }
  caps.plane.removeFromParent();
  caps.plane.geometry.dispose();
  caps.plane.material.dispose();
  runtime.sectionCaps = null;
}

export function syncSectionCaps(runtime, clipPlane) {
  const THREE = runtime?.THREE;
  const parent = runtime?.scene || runtime?.modelGroup?.parent;
  if (!THREE || !parent || !clipPlane) {
    disposeSectionCaps(runtime);
    return;
  }
  // Only parts touched by the plane need stencil passes. Reuse cached bounds
  // so a large assembly does not redraw every uncut component twice.
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
  let caps = runtime.sectionCaps;
  if (!caps) {
    const material = new THREE.MeshBasicMaterial({
      color: 0xe9a451, side: THREE.DoubleSide,
      stencilWrite: true, stencilRef: 0, stencilFunc: THREE.NotEqualStencilFunc,
      stencilFail: THREE.ReplaceStencilOp, stencilZFail: THREE.ReplaceStencilOp, stencilZPass: THREE.ReplaceStencilOp,
      polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(1,1), material);
    plane.name = 'Section fill';
    plane.renderOrder = 1001;
    plane.frustumCulled = false;
    plane.raycast = () => {};
    plane.onAfterRender = renderer => renderer.clearStencil();
    parent.add(plane);
    caps = runtime.sectionCaps = { records: [], stencils: [], plane };
  }
  // Retain existing stencil materials as parts enter/leave the cut. Geometry
  // remains borrowed from display meshes and nothing survives disabling Clip.
  const active = new Set(records.map(record => record.mesh));
  caps.stencils = caps.stencils.filter(mesh => {
    if (active.has(mesh.parent) && mesh.geometry === mesh.parent.geometry) return true;
    mesh.removeFromParent();
    mesh.material.dispose();
    return false;
  });
  const retained = new Set(caps.stencils.map(mesh => mesh.parent));
  for (const record of records) {
    if (retained.has(record.mesh)) continue;
    for (const [side, operation] of [[THREE.BackSide, THREE.IncrementWrapStencilOp], [THREE.FrontSide, THREE.DecrementWrapStencilOp]]) {
      const material = new THREE.MeshBasicMaterial({
        side, colorWrite: false, depthWrite: false, depthTest: false,
        stencilWrite: true, stencilFunc: THREE.AlwaysStencilFunc,
        stencilFail: operation, stencilZFail: operation, stencilZPass: operation,
        clippingPlanes: [clipPlane],
      });
      const mesh = new THREE.Mesh(record.mesh.geometry, material);
      mesh.name = 'Section stencil';
      mesh.renderOrder = 1000;
      mesh.raycast = () => {};
      record.mesh.add(mesh);
      caps.stencils.push(mesh);
    }
  }
  caps.records = [...active];
  for (const mesh of caps.stencils) mesh.material.clippingPlanes = [clipPlane];
  const size = Math.max(1, Number(runtime.modelRadius || 1) * 4);
  caps.plane.scale.set(size,size,1);
  // Project the model's centre onto the cutting plane. A plane centred only
  // on the world origin could miss a translated assembly entirely.
  const bounds = runtime.modelBounds;
  const center = new THREE.Vector3();
  if (bounds?.min && bounds?.max) center.set(...bounds.min.map((value,i) => (value + bounds.max[i])/2));
  if (runtime.modelGroup?.position) center.add(runtime.modelGroup.position);
  clipPlane.projectPoint(center, caps.plane.position);
  caps.plane.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), clipPlane.normal);
}

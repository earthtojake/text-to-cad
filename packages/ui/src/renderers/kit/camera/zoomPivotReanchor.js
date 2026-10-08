export function createZoomPivotReanchor(THREE) {
  const pointer = new THREE.Vector2();
  const forward = new THREE.Vector3();
  const scratch = new THREE.Vector3();
  const center = new THREE.Vector3();

  const readModelWorldCenter = (runtime) => {
    const bounds = runtime.modelBounds;
    if (Array.isArray(bounds?.min) && Array.isArray(bounds?.max)) {
      const x = (Number(bounds.min[0]) + Number(bounds.max[0])) / 2;
      const y = (Number(bounds.min[1]) + Number(bounds.max[1])) / 2;
      const z = (Number(bounds.min[2]) + Number(bounds.max[2])) / 2;
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
        center.set(x, y, z);
        if (runtime.modelGroup?.position) center.add(runtime.modelGroup.position);
        return center;
      }
    }
    return center.copy(runtime.controls.target);
  };

  // Depth along the view axis; `forward` is the camera's direction, set by the caller.
  const depthOf = (camera, point) => Math.max(scratch.copy(point).sub(camera.position).dot(forward), 0);

  // The depth of the surface under `pointer`, 0 when the ray meets nothing. Raycast
  // acceleration remains demand-driven.
  const surfaceDepth = (runtime, camera) => {
    if (!runtime.raycaster || !runtime.modelGroup) return 0;
    runtime.raycaster.setFromCamera(pointer, camera);
    const previousFirstHitOnly = runtime.raycaster.firstHitOnly;
    runtime.raycaster.firstHitOnly = true;
    try {
      const hit = runtime.raycaster.intersectObject(runtime.modelGroup, true).find(entry => entry?.point);
      return hit ? depthOf(camera, hit.point) : 0;
    } finally {
      runtime.raycaster.firstHitOnly = previousFirstHitOnly;
    }
  };

  const clampDepth = (controls, depth) => {
    const minDepth = Math.max(Number.isFinite(controls.minDistance) ? controls.minDistance : 0, 1e-4);
    const maxDepth = Number.isFinite(controls.maxDistance) && controls.maxDistance > 0
      ? controls.maxDistance : Number.POSITIVE_INFINITY;
    return Math.min(Math.max(depth, minDepth), maxDepth);
  };

  return {
    pointer,
    apply(runtime) {
      const camera = runtime?.camera;
      const controls = runtime?.controls;
      // Orthographic pan/dolly do not depend on pivot depth.
      if (!camera?.isPerspectiveCamera || !controls?.target) return;
      camera.getWorldDirection(forward);
      // Anchor all display styles to the surface under the cursor; a miss falls back to
      // model bounds.
      let depth = surfaceDepth(runtime, camera);
      if (!(depth > 0)) depth = depthOf(camera, readModelWorldCenter(runtime));
      // Move only along the forward ray; keep camera position and view direction.
      controls.target.copy(camera.position).addScaledVector(forward, clampDepth(controls, depth));
    },
    // What a perspective pan's speed is scaled by so the surface under the cursor moves as an
    // orthographic pan moves everything. OrbitControls pans at the pivot's depth, so a surface
    // nearer than the pivot outran the cursor (twice as near, twice as fast) and Render panned
    // faster than Solid. A miss pans at the pivot, as before.
    panScale(runtime) {
      const camera = runtime?.camera;
      const controls = runtime?.controls;
      if (!camera?.isPerspectiveCamera || !controls?.target) return 1;
      const pivotDistance = camera.position.distanceTo(controls.target);
      if (!(pivotDistance > 0)) return 1;
      camera.getWorldDirection(forward);
      const depth = surfaceDepth(runtime, camera);
      return depth > 0 ? clampDepth(controls, depth) / pivotDistance : 1;
    }
  };
}

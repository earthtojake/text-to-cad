export function createZoomPivotReanchor(THREE, { renderMode = false } = {}) {
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

  return {
    pointer,
    apply(runtime) {
      const camera = runtime?.camera;
      const controls = runtime?.controls;
      // Orthographic pan/dolly do not depend on pivot depth.
      if (!camera?.isPerspectiveCamera || !controls?.target) return;
      camera.getWorldDirection(forward);
      const depthOf = point => Math.max(scratch.copy(point).sub(camera.position).dot(forward), 0);
      let depth = 0;
      // Render zoom follows the stable subject bounds. Exact surface hits in
      // Inspect can demand BVHs and materialize animated CPU geometry.
      if (!renderMode && runtime.raycaster && runtime.modelGroup) {
        runtime.raycaster.setFromCamera(pointer, camera);
        const previousFirstHitOnly = runtime.raycaster.firstHitOnly;
        runtime.raycaster.firstHitOnly = true;
        try {
          const hit = runtime.raycaster.intersectObject(runtime.modelGroup, true).find(entry => entry?.point);
          if (hit) depth = depthOf(hit.point);
        } finally {
          runtime.raycaster.firstHitOnly = previousFirstHitOnly;
        }
      }
      if (!(depth > 0)) depth = depthOf(readModelWorldCenter(runtime));
      const minDepth = Math.max(Number.isFinite(controls.minDistance) ? controls.minDistance : 0, 1e-4);
      const maxDepth = Number.isFinite(controls.maxDistance) && controls.maxDistance > 0
        ? controls.maxDistance : Number.POSITIVE_INFINITY;
      depth = Math.min(Math.max(depth, minDepth), maxDepth);
      // Move only along the forward ray; keep camera position and view direction.
      controls.target.copy(camera.position).addScaledVector(forward, depth);
    }
  };
}

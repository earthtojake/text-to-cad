// Whether the model hides a point from the camera as it stands: a ray from the eye through the
// point, its first surface (the scene's `pick`) nearer than the point by more than `tolerance`
// (millimetres: a leader's start is a node of its own face, which the ray meets at the same depth).
// What a callout's leader or extension line starts from, on a face seen from its back or behind
// another part, is drawn faint (`PmiOverlay.jsx`), as the ink the model hides is.

/**
 * A test of points against one camera's view, its ray and vectors made once.
 * @param {typeof import("three")} THREE
 * @returns {(options: { camera: object, pick: (ray: object) => { point: number[] } | null, point: number[], tolerance: number }) => boolean}
 */
export function createHiddenTest(THREE) {
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const at = new THREE.Vector3();
  return ({ camera, pick, point, tolerance }) => {
    at.set(point[0], point[1], point[2]).project(camera);
    // Off the view, or behind the eye: nothing on screen hides it.
    if (!(Math.abs(at.x) <= 1 && Math.abs(at.y) <= 1 && at.z <= 1)) return false;
    raycaster.setFromCamera(ndc.set(at.x, at.y), camera);
    const hit = pick(raycaster.ray);
    if (!hit?.point) return false;
    const { origin, direction } = raycaster.ray;
    const along = p => (p[0] - origin.x) * direction.x + (p[1] - origin.y) * direction.y + (p[2] - origin.z) * direction.z;
    return along(hit.point) < along(point) - tolerance;
  };
}

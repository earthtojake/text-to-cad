// The contract a renderer's scene exposes to the kit. It is deliberately tiny, so
// the kit never reaches into a scene: the viewport adopts `object3D`, the camera
// frames `restBounds` (else `bounds`), the look hands over a finish, and teardown
// calls `dispose()`. Everything else about a scene is its renderer's business.

/**
 * @typedef {{ min: [number, number, number], max: [number, number, number] }} SceneBounds
 *
 * @typedef {{ roughness?: number, metalness?: number, clearcoat?: number,
 *   clearcoatRoughness?: number, envMapIntensity?: number }} SurfaceFinish
 *   Plain material values (`@hardcore/core/lib/viewer/surfaceFinish.js`).
 *
 * @typedef {object} KitScene
 * @property {import("three").Object3D} object3D  What the viewport adopts under its model group.
 * @property {SceneBounds} bounds  The scene as posed now: lighting, floor and depth fit follow it.
 * @property {SceneBounds} [restBounds]  The authored placement, unmoved by any pose: what the
 *   camera frames and what 100% zoom means. Absent means `bounds` never moves.
 * @property {() => void} dispose  Release everything the scene created.
 * @property {(finish: SurfaceFinish | null) => void} [setSurfaceFinish]  Wear the viewer's
 *   finish, or (null) the finish the materials were authored with.
 * @property {(ray: import("three").Ray) => ({ id: string, point: import("three").Vector3 } | null)} [pick]
 *   Only scenes that select.
 */

/** The bounds a camera fit uses for a scene: its rest placement when it has one. */
export function sceneFramingBounds(scene) {
  return scene?.restBounds || scene?.bounds || null;
}

/** Whether a value satisfies the required half of the contract. */
export function isKitScene(scene) {
  return Boolean(scene?.object3D?.isObject3D && scene.bounds && typeof scene.dispose === "function");
}

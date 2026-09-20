// The contract a renderer's scene exposes to the kit. It is deliberately tiny, so
// the kit never reaches into a scene: the viewport adopts `object3D`, the camera
// frames `restBounds` (else `bounds`), the look hands over the surface look the
// Display tab resolved, and the scene's OWNER calls `dispose()` (the viewport only
// detaches). Everything else about a scene is its renderer's business.

/**
 * @typedef {{ min: [number, number, number], max: [number, number, number] }} SceneBounds
 *
 * @typedef {{ materialSettings: object, authored: boolean,
 *   surface: { style: "shaded" | "flat", opacity: number } | null }} SurfaceLook
 *   What surfaces wear (`@hardcore/core/lib/viewer/surfaceLook.js`): the resolved material
 *   settings (finish channels, fills, colour grading), whether photographic Render keeps
 *   what was authored, and the Surfaces section's style and opacity.
 *
 * @typedef {object} KitScene
 * @property {import("three").Object3D} object3D  What the viewport adopts under its model group.
 * @property {SceneBounds} bounds  The scene as posed now: lighting, floor and depth fit follow it.
 * @property {SceneBounds} [restBounds]  The authored placement, unmoved by any pose: what the
 *   camera frames and what 100% zoom means. Absent means `bounds` never moves.
 * @property {() => void} dispose  Release everything the scene created.
 * @property {(look: SurfaceLook) => void} [setSurfaceLook]  Wear the look the Display tab
 *   resolved. Called on adoption and whenever it changes; a scene applies it to its own materials.
 * @property {boolean} [keepsAuthoredFinish]  The scene shows authored finishes in Inspect too,
 *   so Inspect gives it a small neutral environment to reflect.
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

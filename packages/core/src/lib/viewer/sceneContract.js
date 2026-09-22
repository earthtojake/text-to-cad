// The contract a family's scene exposes to whatever shows it: the viewer's viewport
// (`@hardcore/ui` renderers/kit) and the snapshot CLI's headless stage
// (`common/headlessScene.js`). It is deliberately tiny, so neither reaches into a
// scene: the host adopts `object3D`, frames `restBounds` (else `bounds`), hands over
// the surface look it resolved, and the scene's OWNER calls `dispose()` (a host only
// detaches). Everything else about a scene is its family's business.
//
// One builder per family makes these scenes, and both hosts call the same one: the
// viewer and a snapshot cannot draw a family differently, because there is only one
// place that decides how it is drawn.

/**
 * @typedef {{ min: [number, number, number], max: [number, number, number] }} SceneBounds
 *
 * @typedef {{ materialSettings: object, authored: boolean,
 *   surface: { style: "shaded" | "flat", opacity: number } | null }} SurfaceLook
 *   What surfaces wear (`surfaceLook.js`): the resolved material settings (finish channels,
 *   fills, colour grading), whether photographic Render keeps what was authored, and the
 *   Surfaces section's style and opacity. `resolveSceneSurfaceLook` (`common/sceneSettings.js`)
 *   is the one place a look is resolved from display settings.
 *
 * @typedef {object} KitScene
 * @property {import("three").Object3D} object3D  What the host adopts under its model group.
 * @property {SceneBounds} bounds  The scene as posed now: lighting, floor and depth fit follow it.
 * @property {SceneBounds} [restBounds]  The authored placement, unmoved by any pose: what the
 *   camera frames, what 100% zoom means and what the ground is sized from. Absent means `bounds`
 *   never moves.
 * @property {() => void} dispose  Release everything the scene created.
 * @property {(look: SurfaceLook) => void} [setSurfaceLook]  Wear the look the host resolved.
 *   Called on adoption and whenever it changes; a scene applies it to its own materials.
 * @property {(receives: boolean) => void} [setShadowReception]  Whether the scene's surfaces take
 *   shadows just now. A scene WITHOUT it has the host set every one of its meshes; a scene whose
 *   surfaces do not all take shadows (unlit or see-through ones) implements it and applies its own rule.
 * @property {boolean} [keepsAuthoredFinish]  The scene shows authored finishes in Inspect too,
 *   so Inspect gives it a small neutral environment to reflect.
 * @property {(ray: import("three").Ray) => ({ id: string, point: import("three").Vector3 } | null)} [pick]
 *   Only scenes that select.
 * @property {boolean} [complete]  `false` while the scene is still ARRIVING (a large model published
 *   in pieces into one scene identity). The viewport frames what has arrived, so something is on
 *   screen at once, and frames once more when the scene is whole. Absent means whole.
 * @property {() => object[]} [placedObjects]  The things the scene has placed, each with its own
 *   `partBounds` and transforms, for the near/far fit alone (`fitCameraDepthToBounds`): a camera
 *   inside a mostly empty aggregate box can still be well outside everything visible in it. A
 *   scene that says nothing is fitted on its whole box.
 */

/** The bounds a camera fit uses for a scene: its rest placement when it has one. */
export function sceneFramingBounds(scene) {
  return scene?.restBounds || scene?.bounds || null;
}

/** Whether a value satisfies the required half of the contract. */
export function isKitScene(scene) {
  return Boolean(scene?.object3D?.isObject3D && scene.bounds && typeof scene.dispose === "function");
}

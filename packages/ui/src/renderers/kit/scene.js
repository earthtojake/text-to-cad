// The contract a renderer's scene exposes to the kit. It is core's
// (`@hardcore/core/lib/viewer/sceneContract.js`) because the snapshot CLI's headless stage
// holds the same scenes the viewport does: one builder per file family, two hosts. The
// kit's half never reaches into a scene: the viewport adopts `object3D`, the camera frames
// `restBounds` (else `bounds`), the look hands over the surface look the Display tab
// resolved, and the scene's OWNER calls `dispose()` (the viewport only detaches).

/**
 * @typedef {import("@hardcore/core/lib/viewer/sceneContract.js").SceneBounds} SceneBounds
 * @typedef {import("@hardcore/core/lib/viewer/sceneContract.js").SurfaceLook} SurfaceLook
 * @typedef {import("@hardcore/core/lib/viewer/sceneContract.js").KitScene} KitScene
 */

export { isKitScene, sceneFramingBounds } from "@hardcore/core/lib/viewer/sceneContract.js";

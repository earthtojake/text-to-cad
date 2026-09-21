// What a DXF is drawn AS. `createDxfScene` picks one from the parse and wraps it as the
// kit's scene; nothing outside this folder knows which one it got except by `kind`, which
// the renderer reads to decide its tabs, its tools and whether 2D/3D means anything.
//
// Adding a third presentation is adding a file here that satisfies this shape and a line in
// `dxfScene.js` that chooses it. Nothing else moves.

/**
 * @typedef {"layout" | "document"} DxfPresentationKind
 *   `layout`: closed cut contours, extruded into a flat pattern that folds.
 *   `document`: a dimensioned drawing, drawn as line-work, with no solid at all.
 *
 * @typedef {object} DxfPresentation
 * @property {DxfPresentationKind} kind
 * @property {import("three").Object3D} object3D  What the scene adopts.
 * @property {import("../../kit/scene.js").SceneBounds} restBounds  The box the camera frames.
 * @property {(settings: object) => void} update  Pose it for these settings, synchronously.
 * @property {(look: import("../../kit/scene.js").SurfaceLook | null) => void} [setSurfaceLook]
 *   Only a presentation with lit surfaces. Line-work is unlit and outside the look.
 * @property {() => void} dispose
 */
export {};

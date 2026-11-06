/**
 * A board in 3D, its frame: where the sheet a board's plot is laid out on (`plot2d`, page millimetres,
 * x right, y down) stands in the world a 3D view draws, and back.
 *
 * The world is z-up, as every 3D view's (`cad-z-up-v1`): x is the sheet's x, y the sheet's y negated
 * (so the world's x, y are exactly drawing2d's model space, the 2D view's plan seen from the top), and
 * z comes out of the front face. The front face is the plane z = 0, the back face z = -thickness. A
 * view from the top is then the 2D picture, and a view from below is mirrored left to right as the 2D
 * view from the back is (`plot2d/boardView.js`'s `boardMirrorX`).
 *
 * Nothing here needs three.js: vectors are plain arrays, so the maths is tested on its own and the
 * stage (`boardStage.js`) and the views share it.
 *
 * Importing this module has no environmental effects.
 */

/** A board's thickness until its file says it: KiCad's default stack-up, 1.6 mm. */
export const BOARD_THICKNESS_MM = 1.6;

/** A sheet point, `z` off the front face, in the world. */
export const sheetToWorld = ([x, y], z = 0) => [x, -y, z];
/** A world point on the sheet (its z dropped). */
export const worldToSheet = ([x, y]) => [x, -y];
/** The plane a side's face lies in. */
export const faceZ = (side, thickness = BOARD_THICKNESS_MM) => (side === "bottom" ? -thickness : 0);
/** The side a camera looking along `direction` sees: from above the front, from below the back. */
export const sideSeenAlong = direction => (direction[2] > 0 ? "bottom" : "top");

/**
 * Where a ray meets the board: the face it enters (the front coming down, the back coming up), the
 * sheet point there, the world point and how far along the ray. Null for a ray along the board or one
 * leaving it (its face behind the eye). Whether the point is inside the outline is the caller's.
 *
 * @param {{ origin: number[], direction: number[] }} ray
 * @param {number} [thickness]
 * @returns {{ side: "top" | "bottom", page: [number, number], point: [number, number, number], distance: number } | null}
 */
export function rayOnBoard({ origin, direction }, thickness = BOARD_THICKNESS_MM) {
  const dz = direction[2];
  if (!(Math.abs(dz) > 1e-9)) return null;
  const side = sideSeenAlong(direction);
  const distance = (faceZ(side, thickness) - origin[2]) / dz;
  if (!(distance >= 0)) return null;
  const point = [origin[0] + direction[0] * distance, origin[1] + direction[1] * distance, faceZ(side, thickness)];
  return { side, page: worldToSheet(point), point, distance };
}

/**
 * Where a ray meets the plane of one face (`side`'s), as a sheet point, whatever side it comes from;
 * null for a ray along the board or one whose plane is behind the eye. What a mark drawn over a 3D view
 * is laid on: the face of the side the camera sees, every point of it.
 */
export function rayToFace({ origin, direction }, side, thickness = BOARD_THICKNESS_MM) {
  const dz = direction[2];
  if (!(Math.abs(dz) > 1e-9)) return null;
  const distance = (faceZ(side, thickness) - origin[2]) / dz;
  return distance >= 0 ? worldToSheet([origin[0] + direction[0] * distance, origin[1] + direction[1] * distance]) : null;
}

/**
 * How many millimetres one CSS pixel spans at a point `depth` in front of the camera:
 * orthographic, the frustum's height over the pane's; in perspective, the same at that depth.
 * @param {{ orthographic: boolean, halfHeight?: number, fov?: number }} camera  `halfHeight`: an
 *   orthographic camera's half height in world units at its zoom; `fov`: a perspective camera's vertical field in degrees.
 */
export function millimetresPerPixel(camera, depth, paneHeight) {
  if (!(paneHeight > 0)) return 0;
  if (camera.orthographic) return (2 * camera.halfHeight) / paneHeight;
  return (2 * Math.max(depth, 0) * Math.tan(((camera.fov ?? 0) * Math.PI) / 360)) / paneHeight;
}

/**
 * The 2D view's window as a 3D camera, head on: the pane's centre on the sheet, from the side the 2D
 * view shows, square to the board, at the same millimetres per pixel. What a 3D view opens on, so its
 * first frame is the 2D picture. A perspective snapshot (`lib/perspective.js`): position, target, up
 * and the orthographic half height. `planFromCamera` of it is the window again, exactly: the round trip
 * of a 3D view nobody turned.
 *
 * @param {{ transform: { scale: number, offsetX: number, offsetY: number }, width: number, height: number,
 *   side: "top" | "bottom", mirrorX: number | null, thickness?: number, distance: number }} view
 *   `mirrorX`: the page x the 2D view mirrors about from the back (`boardMirrorX`); `distance`: how
 *   far the eye stands off the face (a perspective lens's is `perspectiveHeadOn`'s).
 */
export function headOnCamera({ transform, width, height, side, mirrorX = null, thickness = BOARD_THICKNESS_MM, distance }) {
  if (!transform || !(transform.scale > 0) || !(width > 0) || !(height > 0)) return null;
  // The pane's centre in the plan (drawing2d's model space: x right, y up), then on the sheet.
  const planX = (width / 2 - transform.offsetX) / transform.scale;
  const planY = (transform.offsetY - height / 2) / transform.scale;
  const sheetX = side === "bottom" && mirrorX != null ? 2 * mirrorX - planX : planX;
  const z = faceZ(side, thickness);
  const target = [sheetX, planY, z];
  const off = side === "bottom" ? -distance : distance;
  return { position: [target[0], target[1], z + off], target, up: [0, 1, 0], orthographicHalfHeight: height / 2 / transform.scale };
}

/**
 * A head-on camera (`headOnCamera`) for a perspective lens of vertical field `fov` (degrees): its eye on the
 * same line of sight, where the face is drawn at the window's scale (the face's half height at the target is
 * the eye's distance times tan(fov / 2)). An orthographic picture is the same from any distance; a
 * perspective one only from that one, so the lens the viewport has decides it.
 */
export function perspectiveHeadOn(camera, fov) {
  const half = (Number(fov) * Math.PI) / 360;
  if (!camera || !(camera.orthographicHalfHeight > 0) || !(half > 0 && half < Math.PI / 2)) return camera;
  const away = camera.position.map((value, axis) => value - camera.target[axis]);
  const length = Math.hypot(...away);
  if (!(length > 0)) return camera;
  const distance = camera.orthographicHalfHeight / Math.tan(half);
  return { ...camera, position: camera.target.map((value, axis) => value + (away[axis] / length) * distance) };
}

/**
 * The 3D camera as the 2D view's window: centred on the sheet point the camera is centred on (where
 * its line of sight meets the face it looks at), from that side, at the millimetres per pixel there.
 * What leaving a 3D view frames the 2D view on.
 *
 * @param {{ position: number[], target: number[], halfHeight: number, width: number, height: number,
 *   mirrorX: (side: "top" | "bottom") => number | null, thickness?: number }} camera  `halfHeight`: the
 *   view's half height in millimetres at its target.
 * @returns {{ side: "top" | "bottom", transform: { scale: number, offsetX: number, offsetY: number } } | null}
 */
export function planFromCamera({ position, target, halfHeight, width, height, mirrorX, thickness = BOARD_THICKNESS_MM }) {
  if (!(halfHeight > 0) || !(width > 0) || !(height > 0)) return null;
  const direction = target.map((value, axis) => value - position[axis]);
  const hit = rayOnBoard({ origin: position, direction }, thickness);
  const side = sideSeenAlong(direction);
  const [sheetX, sheetY] = hit ? hit.page : worldToSheet(target);
  const mirror = side === "bottom" ? mirrorX(side) : null;
  const planX = mirror == null ? sheetX : 2 * mirror - sheetX;
  const planY = -sheetY;
  const scale = height / (2 * halfHeight);
  return { side, transform: { scale, offsetX: width / 2 - planX * scale, offsetY: height / 2 + planY * scale } };
}

/**
 * The camera turned to the board's other side: what Front | Back does in 3D. The eye goes over the
 * board's left-to-right axis through its target (the world's x: y and z negated), and which way is up
 * stays as it was, so the world's up stays up on screen (the cube reads upright) and the other face is
 * seen as the 2D view sees the back: mirrored left to right, not upside down. Turned about the
 * upright axis instead, the picture is the same but the world's up points down. Position and up, the
 * target kept.
 */
export function cameraTurnedOver({ position, target, up }) {
  const offset = position.map((value, axis) => value - target[axis]);
  const turned = [offset[0], -offset[1], -offset[2]];
  return { position: turned.map((value, axis) => value + target[axis]), target: [...target], up: [...up] };
}

/**
 * The world-from-sheet matrix (column order, as three.js keeps a Matrix4's elements) for a point on
 * the face of `side`: (x, y, z) on the sheet to (x, -y, faceZ + z). Measure's points are on the sheet;
 * its camera through a 3D view is this under the view's own (`viewInverse · this`).
 */
export function sheetToWorldMatrix(side, thickness = BOARD_THICKNESS_MM) {
  return [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 0, 0, faceZ(side, thickness), 1];
}

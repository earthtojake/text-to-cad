/**
 * A board in 3D, where a part's 3D model stands: the matrix (column order, as three.js keeps a Matrix4's
 * elements) from the model's own frame (a STEP's millimetres) into the board's world (`boardFrame.js`'s:
 * x the sheet's x, y the sheet's y negated, the front face at z = 0, the back at z = -thickness).
 *
 * As KiCad's 3D view places a footprint's model: the footprint at its place on its side's face, turned
 * by its angle about the board's normal (counter-clockwise seen from the top) and, on the back, turned
 * over (half a turn about its x axis: KiCad's half turn about y then about z); then, in the footprint's
 * frame, the model's offset (millimetres), its rotation about z, then y, then x, each by the negated
 * angle as KiCad applies it, and its scale.
 *
 * Pure: plain arrays, no three.js. Importing this module has no environmental effects.
 */
import { BOARD_THICKNESS_MM, faceZ } from "./boardFrame.js";

const RADIANS = Math.PI / 180;

/** `a · b`, 4x4 column-major. */
export function multiply(a, b) {
  const out = new Array(16).fill(0);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      let sum = 0;
      for (let k = 0; k < 4; k += 1) sum += a[k * 4 + row] * b[column * 4 + k];
      out[column * 4 + row] = sum;
    }
  }
  return out;
}

const translation = ([x, y, z]) => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1];
const scaling = ([x, y, z]) => [x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0, 0, 0, 0, 1];
const about = (axis, degrees) => {
  const c = Math.cos(degrees * RADIANS), s = Math.sin(degrees * RADIANS);
  if (axis === "x") return [1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1];
  if (axis === "y") return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1];
  return [c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
};
const TURNED_OVER = [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1];
const triple = (value, fallback) => (Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? value : fallback);

/**
 * Where a footprint stands: its sheet point on its side's face, turned by its angle, turned over on the back.
 * @param {{ at: number[], rotation?: number, side?: string }} part  The payload's part (sheet millimetres).
 */
export function footprintMatrix(part, thickness = BOARD_THICKNESS_MM) {
  const side = part.side === "bottom" ? "bottom" : "top";
  const placed = multiply(translation([part.at[0], -part.at[1], faceZ(side, thickness)]), about("z", Number(part.rotation) || 0));
  return side === "bottom" ? multiply(placed, TURNED_OVER) : placed;
}

/**
 * A model of a part, from its own frame into the world: the footprint's place, then the model's offset,
 * rotation and scale in the footprint's frame (the payload's `models[]`: `offset`, `rotate`, `scale`).
 */
export function modelMatrix(part, model = {}, thickness = BOARD_THICKNESS_MM) {
  const [rx, ry, rz] = triple(model.rotate, [0, 0, 0]);
  let local = translation(triple(model.offset, [0, 0, 0]));
  local = multiply(local, about("z", -rz));
  local = multiply(local, about("y", -ry));
  local = multiply(local, about("x", -rx));
  local = multiply(local, scaling(triple(model.scale, [1, 1, 1])));
  return multiply(footprintMatrix(part, thickness), local);
}

/** A point through a matrix. */
export const placePoint = (m, [x, y, z]) => [0, 1, 2].map(row => m[row] * x + m[4 + row] * y + m[8 + row] * z + m[12 + row]);

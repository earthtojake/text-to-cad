import { xbfLinkPlacements, xbfPairMotion } from "@text-to-cad/core/lib/xbf/xbfKinematics.js";
import { xbfElementId } from "@text-to-cad/core/lib/xbf/xbfScene.js";
import { add, armOffset, subtract } from "../kit/tools/pose/jointHandleMath.js";

// What Position's knobs take hold of in an engine document: the kit's plain list, one
// handle per row of the Position section that turns or slides -- a revolute pair's angle, a
// prismatic pair's distance, a cylindrical pair's both (a coupling's joints have no row, so no
// knob) -- placed where the mechanism stands now: `pivot` on the pair's frame (a slide's where its
// child now is), `axis` the frame's Z, `toward` a point on the carried parts that gives a turning
// pair's arm its direction. `onChange` is the section's own write, so limits are decided in one
// place.

function multiply(a, b) {
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

// Each link's distance from the ground through the pairs: the farther link of a pair is the one it carries.
function linkDepths(kinematics) {
  const depth = new Map([[kinematics.ground, 0]]);
  for (let progress = true; progress;) {
    progress = false;
    for (const pair of kinematics.pairs || []) {
      if (!Array.isArray(pair.links)) continue;
      const [one, two] = pair.links;
      if (depth.has(one) && !depth.has(two)) { depth.set(two, depth.get(one) + 1); progress = true; }
      else if (depth.has(two) && !depth.has(one)) { depth.set(one, depth.get(two) + 1); progress = true; }
    }
  }
  return depth;
}

/**
 * @param {{ kinematics: object, rows: ReturnType<typeof import("./XbfPositionSection.jsx").xbfPositionRows>,
 *   values: Record<string, number[]>, scene: object, onChange: (row: object, value: number) => void }} options
 * @returns {object[]}  The kit's handles (`kit/tools/pose/useJointHandles.js`).
 */
export function xbfJointHandles({ kinematics, rows, values, scene, onChange }) {
  if (!kinematics || !rows.length || !scene) return [];
  const pairs = new Map((kinematics.pairs || []).map(pair => [pair.label, pair]));
  const placements = xbfLinkPlacements(kinematics, values);
  const depths = linkDepths(kinematics);
  const handles = [];
  for (const row of rows) {
    const pair = pairs.get(row.pair);
    if (!pair?.frames || !Array.isArray(pair.links)) continue;
    const kind = pair.type === "prismatic" || (pair.type === "cylindrical" && row.index === 1) ? "prismatic"
      : pair.type === "revolute" || pair.type === "cylindrical" ? "revolute" : null;
    if (!kind) continue;
    const [one, two] = pair.links;
    const frame = multiply(placements[one], pair.frames[0]);
    const value = values[row.pair]?.[row.index] ?? 0;
    const moved = multiply(frame, xbfPairMotion(pair.type, values[pair.label] || [value]));
    const axis = [frame[8], frame[9], frame[10]];
    const pivot = [moved[12], moved[13], moved[14]];
    const child = (depths.get(two) ?? 1) >= (depths.get(one) ?? 0) ? two : one;
    const carried = (kinematics.links[child]?.instances || []).map(index => xbfElementId(index));
    const box = scene.selectionBounds(carried);
    const centre = box ? [0, 1, 2].map(at => (box.min[at] + box.max[at]) / 2) : null;
    const limits = pair.limits?.[row.index] || [null, null];
    const continuous = kind === "revolute" && limits[0] == null && limits[1] == null;
    handles.push({
      id: row.id, label: row.label, kind: continuous ? "continuous" : kind, pivot, axis,
      toward: kind === "prismatic" ? null : add(pivot, armOffset(axis, centre ? subtract(centre, pivot) : null)),
      value, min: continuous ? null : row.min, max: continuous ? null : row.max, unit: row.unit === "deg" ? "deg" : "mm",
      onChange: next => onChange(row, next)
    });
  }
  return handles;
}

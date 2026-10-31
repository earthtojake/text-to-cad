// What Measure picks, as the person filters it from the chevron after its button
// (`MeasureFilterMenu.jsx`, the same menu Select's filter is): Vertices, Edges and Faces, each on
// its own, all ticked when a file opens. What a press takes is an ENTITY, whole, as a CAD measure
// tool takes it: the vertex within a few pixels of the pointer, else the edge, else the face under it.
// A kind left unticked is not pickable, and what is under the pointer is the next kind the filter
// allows (an edge's end with Edges unticked is still its vertex; mid-edge is the face), or nothing.
// With none ticked (or Shift held) a press takes the point on the model as it is, the one free point.
// An exact model's only: a mesh has no vertices, edges or faces of its own, and Measure there is two points on its surface.
//
// Importing this module has no environmental effects.

/** The kinds Measure snaps to, in its menu's order. */
export const MEASURE_SNAP_KINDS = Object.freeze([
  Object.freeze({ id: "vertex", label: "Vertices", key: "pick.vertices" }),
  Object.freeze({ id: "edge", label: "Edges", key: "pick.edges" }),
  Object.freeze({ id: "face", label: "Faces", key: "pick.faces" }),
]);

/** Every kind ticked: a file opens snapping to all three. */
export const MEASURE_FILTER_DEFAULT = Object.freeze(MEASURE_SNAP_KINDS.map(kind => kind.id));

/**
 * `pick` as `filter` allows it. An edge pick becomes the end of its edge the pointer is at (`vertex`, a
 * point in the pick's frame) where Vertices is ticked; stays the edge where Edges is; else falls to
 * the face under the pointer (`face()`) where Faces is, else to nothing. A face pick with Faces unticked is
 * nothing. A vertex is kept as it is. (Nothing ticked never asks: the caller takes the free point.)
 *
 * @param {{ snapKind: string, point: number[] } | null} pick
 * @param {readonly string[]} filter
 * @param {{ vertex?: number[] | null, face?: () => object | null }} [fallbacks]
 */
export function restrictMeasurePick(pick, filter, { vertex = null, face = () => null } = {}) {
  if (!pick) return pick;
  if (pick.snapKind === "edge") {
    if (vertex && filter.includes("vertex")) return { ...pick, snapKind: "vertex", point: [...vertex], geometry: null };
    if (filter.includes("edge")) return pick;
    return (filter.includes("face") ? face() : null) || null;
  }
  if (pick.snapKind === "face" && !filter.includes("face")) return null;
  return pick;
}

const endKey = (positions, index) => `${positions[index]},${positions[index + 1]},${positions[index + 2]}`;

/**
 * The ends of an edge drawn as segments (`positions`: pairs of points, flat): the points that end
 * exactly one segment. A closed edge (a circle) has none.
 *
 * @param {ArrayLike<number> | null} positions
 * @returns {number[][]}
 */
export function edgeEnds(positions) {
  if (!positions || positions.length < 6) return [];
  const count = new Map();
  for (let index = 0; index + 2 < positions.length; index += 3) {
    const key = endKey(positions, index);
    const seen = count.get(key);
    count.set(key, seen ? { ...seen, uses: seen.uses + 1 } : { uses: 1, point: [positions[index], positions[index + 1], positions[index + 2]] });
  }
  return [...count.values()].filter(end => end.uses === 1).map(end => end.point);
}

/** The pixels within which a pointer takes an edge's end over the edge, as a mesh's corner is taken. */
export const MEASURE_VERTEX_SNAP_PX = 10;

/**
 * The end (of `ends`) nearest `pointer` on screen, within `maxPx`, or null. `toScreen` maps a point to
 * screen pixels in the pointer's frame (or null when it is off screen).
 *
 * @param {number[][]} ends
 * @param {(point: number[]) => ({ x: number, y: number } | null)} toScreen
 * @param {{ x: number, y: number }} pointer
 */
export function nearestEnd(ends, toScreen, pointer, maxPx = MEASURE_VERTEX_SNAP_PX) {
  let best = null;
  for (const end of ends) {
    const at = toScreen(end);
    if (!at) continue;
    const distance = Math.hypot(at.x - pointer.x, at.y - pointer.y);
    if (distance <= maxPx && (!best || distance < best.distance)) best = { end, distance };
  }
  return best ? best.end : null;
}

/**
 * A board's airwires: every connection its nets make, each as straight lines between pins, routed
 * or not — the board as a person places it, before (or regardless of) its copper. Each net's pins
 * are joined by their shortest tree (a minimum spanning tree over pin centres), as KiCad draws a
 * ratsnest, so a net of n pins is n - 1 lines and moving a part shows at once which way its
 * connections pull.
 *
 * The plot's own ratsnest (`kind: "ratsnest"`) is KiCad's DRC: only what is still unrouted. This
 * is all of it, from the board's index (`createBoardIndex`), in page millimetres.
 */

const AIRWIRES = new WeakMap();

/** The shortest tree over `points`: pairs of indexes into them (Prim's, O(n²), no heap). */
function spanningTree(points) {
  const count = points.length;
  const joined = new Uint8Array(count);
  const distance = new Float64Array(count).fill(Infinity);
  const from = new Int32Array(count).fill(-1);
  const edges = [];
  distance[0] = 0;
  for (let step = 0; step < count; step += 1) {
    let next = -1;
    for (let index = 0; index < count; index += 1) {
      if (!joined[index] && (next < 0 || distance[index] < distance[next])) next = index;
    }
    joined[next] = 1;
    if (from[next] >= 0) edges.push([from[next], next]);
    const [x, y] = points[next];
    for (let index = 0; index < count; index += 1) {
      if (joined[index]) continue;
      const length = Math.hypot(points[index][0] - x, points[index][1] - y);
      if (length < distance[index]) { distance[index] = length; from[index] = next; }
    }
  }
  return edges;
}

/**
 * Every airwire of a board, `{ net, points: [a, b], box }` in page millimetres, made once per index.
 * A net's pins are its pads one per pin (`index.nets`' pads), so a pin drawn as several pads (a
 * USB-C shell, a tab) is one end, not a tangle of zero-length lines.
 *
 * @param {ReturnType<typeof import("./boardIndex.js").createBoardIndex>} index
 * @returns {readonly { net: string, points: number[][], box: number[] }[]}
 */
export function boardAirwires(index) {
  if (!index || index.document !== "board") return [];
  let wires = AIRWIRES.get(index);
  if (wires) return wires;
  wires = [];
  for (const net of index.nets.values()) {
    const points = net.pads.map((pad) => pad.at).filter(Boolean);
    if (points.length < 2) continue;
    for (const [a, b] of spanningTree(points)) {
      const [ax, ay] = points[a];
      const [bx, by] = points[b];
      wires.push({ net: net.name, points: [points[a], points[b]], box: [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)] });
    }
  }
  wires = Object.freeze(wires);
  AIRWIRES.set(index, wires);
  return wires;
}

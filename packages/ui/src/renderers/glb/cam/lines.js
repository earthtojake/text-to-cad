import { createScreenSpaceLineSegments, syncLineMaterialOpacity, topologyLineDepthBiasForWidth } from "@text-to-cad/core/common/renderEdges.js";
import { RAPID_COLOURS, camOpColours } from "./colours.js";
import { camOperation } from "./extras.js";

/**
 * A CAM result's toolpaths, drawn as the viewer draws its edges: the file's glTF LINES (the loader's 1px
 * `LineSegments`, one node per setup for feed moves and one for rapids) are put away and their segments
 * redrawn as screen-space lines (`LineSegments2`), one object per operation and kind, so an operation
 * takes its own colour, can be dimmed while another is isolated, and its feed moves are thick while its
 * rapids are thin and dashed.
 *
 * Each segment carries the program's time at its two ends (`_CAM_T`, seconds) and its operation
 * (`_CAM_OP`, the extras' operation `index`); GLTFLoader lowercases attribute names it does not know,
 * so they arrive as `_cam_t` and `_cam_op`. A node's extras say its setup and kind
 * (`{ setup, kind: "feed" | "rapid" }`); without them a node named for rapids is rapids, and a segment's
 * setup is its operation's. A file with no `_CAM_OP` has each segment's operation found by its time
 * (the operation whose `t0`..`t1` holds it); one with no `_CAM_T` draws every segment from the start. Where the
 * tool's axis changes along a setup (a rotary wrap, swarf, a 5-axis finish, a tapered wire) each vertex also carries
 * it (`_CAM_AXIS`, unit, in the file's axes), and the tool is stood along it as it rides.
 *
 * Segments are sorted by time within each object, so playback reveals a path up to a moment by drawing
 * its first segments (`instanceCount`), the one under way cut where the tool is.
 */

const FEED_WIDTH = 2;
const RAPID_WIDTH = 1;
const DIM = Object.freeze({ feed: 0.14, rapid: 0.08 });
const SHOWN = Object.freeze({ feed: 1, rapid: 0.75 });
// Rapids' dashes, in mm along the move.
const DASH_MM = 2;
const GAP_MM = 1.5;

const noRaycast = () => {};

/** A geometry attribute by its name as the loader writes it (lowercased) or as the file spells it. */
function attribute(geometry, name) {
  return geometry.getAttribute(name) || geometry.getAttribute(name.toUpperCase()) || null;
}

/** Whether a line object of the scene is rapids: its extras say so, or its name does. */
function lineKind(object) {
  const kind = String(object.userData?.kind || object.userData?.cam_kind || "").toLowerCase();
  if (kind === "rapid" || kind === "rapids") return "rapid";
  if (kind === "feed" || kind === "feeds") return "feed";
  return /rapid/i.test(`${object.userData?.name || ""} ${object.name || ""}`) ? "rapid" : "feed";
}

/** The file's toolpath objects: every line of the scene that is not one this module drew. */
export function camToolpathObjects(root) {
  const found = [];
  root?.traverse?.((object) => {
    if (object.userData?.camDrawn) return;
    if ((object.isLineSegments || object.isLine) && object.geometry?.getAttribute?.("position")) {
      found.push({ object, kind: lineKind(object), setup: String(object.userData?.setup ?? "") });
    }
  });
  return found;
}

/**
 * Where the scene's root sits in CAD space (mm, Z up): how many mm one of its units is, and the inverse of
 * its orientation, so a tool can be sized in mm and stood along a CAD axis. `cadRoot` is the object that
 * places the file in CAD space (the GLB scene's `object3D`); without one the root's own frame is CAD space.
 */
export function cadFrame(THREE, root, cadRoot = null) {
  const matrix = new THREE.Matrix4();
  if (cadRoot && cadRoot !== root) {
    cadRoot.updateWorldMatrix(true, false);
    root.updateWorldMatrix(true, false);
    matrix.copy(cadRoot.matrix).multiply(cadRoot.matrixWorld.clone().invert()).multiply(root.matrixWorld);
  }
  const mmPerUnit = new THREE.Vector3().setFromMatrixColumn(matrix, 0).length() || 1;
  const toLocal = matrix.clone().invert();
  return {
    mmPerUnit,
    /** CAD space (mm, Z up) to the root's frame. */
    toLocal,
    /** A CAD direction ([x, y, z]) in the root's frame, unit length. */
    direction: (vector) => new THREE.Vector3(...vector).transformDirection(toLocal),
    /** A CAD point ([x, y, z], mm) in the root's frame. */
    point: (vector) => new THREE.Vector3(...vector).applyMatrix4(toLocal),
  };
}

/** The operation whose span holds a moment, by the job's `t0`..`t1` (the last that starts at or before it). */
function operationAt(job) {
  const spans = [...(job?.operations || [])].sort((a, b) => a.t0 - b.t0);
  return (t) => {
    let found = spans[0]?.index ?? -1;
    for (const op of spans) {
      if (op.t0 <= t) found = op.index;
      else break;
    }
    return found;
  };
}

/** The first index whose value is greater than `value` in an ascending array. */
function upperBound(values, value, end = values.length) {
  let lo = 0;
  let hi = end;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (values[mid] <= value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * The file's segments in the root's frame, grouped by kind and operation, each group sorted by the time it
 * starts, and every segment once more in one list sorted by time, for where the tool is at a moment.
 */
export function readCamSegments(THREE, root, job) {
  root.updateWorldMatrix(true, true);
  const toRoot = root.matrixWorld.clone().invert();
  const opAt = operationAt(job);
  const groups = new Map();
  const point = new THREE.Vector3();
  for (const { object, kind, setup } of camToolpathObjects(root)) {
    const geometry = object.geometry;
    const position = geometry.getAttribute("position");
    const times = attribute(geometry, "_cam_t");
    const ops = attribute(geometry, "_cam_op");
    const axes = attribute(geometry, "_cam_axis");
    const index = geometry.index;
    const vertex = (i) => (index ? index.getX(i) : i);
    const count = index ? index.count : position.count;
    const pairs = object.isLineSegments ? Math.floor(count / 2) : Math.max(0, count - 1);
    const step = object.isLineSegments ? 2 : 1;
    const matrix = toRoot.clone().multiply(object.matrixWorld);
    for (let k = 0; k < pairs; k += 1) {
      const a = vertex(k * step);
      const b = vertex(k * step + 1);
      const ta = times ? times.getX(a) : 0;
      const tb = times ? times.getX(b) : ta;
      const op = ops ? Math.round(ops.getX(a)) : opAt(ta);
      const opSetup = setup || camOperation(job, op)?.setup || "";
      const key = `${kind}:${op}`;
      let group = groups.get(key);
      if (!group) {
        group = { key, kind, op, setup: opSetup, segments: [] };
        groups.set(key, group);
      }
      point.fromBufferAttribute(position, a).applyMatrix4(matrix);
      const start = point.toArray();
      point.fromBufferAttribute(position, b).applyMatrix4(matrix);
      const end = point.toArray();
      // A segment written end first (its times reversed) is stored start first, so the tool rides it forwards.
      const forwards = tb >= ta;
      const segment = { start: forwards ? start : end, end: forwards ? end : start, t0: Math.min(ta, tb), t1: Math.max(ta, tb), op, setup: opSetup, axis: null };
      if (axes) {
        const along = [a, b].map((vertexIndex) => point.fromBufferAttribute(axes, vertexIndex).transformDirection(matrix).toArray());
        segment.axis = forwards ? along : along.reverse();
      }
      group.segments.push(segment);
    }
  }
  const all = [];
  const sorted = [...groups.values()].map((group) => {
    const segments = group.segments.sort((a, b) => a.t0 - b.t0);
    all.push(...segments);
    const positions = new Float32Array(segments.length * 6);
    const starts = new Float64Array(segments.length);
    const ends = new Float64Array(segments.length);
    segments.forEach((segment, i) => {
      positions.set(segment.start, i * 6);
      positions.set(segment.end, i * 6 + 3);
      starts[i] = segment.t0;
      ends[i] = segment.t1;
    });
    return { key: group.key, kind: group.kind, op: group.op, setup: group.setup, positions, starts, ends };
  });
  all.sort((a, b) => a.t0 - b.t0);
  return { groups: sorted, timeline: { segments: all, starts: Float64Array.from(all, (segment) => segment.t0) } };
}

/** Two unit directions mixed by `share` and made unit again (the second where they are opposite). */
function mixAxes([from, to], share) {
  const mixed = from.map((value, axis) => value + (to[axis] - value) * share);
  const length = Math.hypot(...mixed);
  return length > 1e-9 ? mixed.map((value) => value / length) : [...to];
}

/**
 * Where the tool is at a moment of the program: on the segment under way, between its ends by time; in a
 * pause (a tool change), at the end of the last move; before the first, at its start. Null with no segments.
 * Only a setup's own segments when `setup` names one. `axis` (the root's frame, unit) is the tool's own where the
 * file carries it per vertex (`_CAM_AXIS`), else null: the setup's.
 */
export function toolPositionAt(timeline, t, setup = null) {
  const { segments, starts } = timeline;
  if (!segments.length) return null;
  let i = upperBound(starts, t) - 1;
  while (i >= 0 && setup && segments[i].setup !== setup) i -= 1;
  if (i < 0) {
    const first = setup ? segments.find((segment) => segment.setup === setup) : segments[0];
    return first ? { point: [...first.start], op: first.op, setup: first.setup, axis: first.axis ? [...first.axis[0]] : null } : null;
  }
  const segment = segments[i];
  const span = segment.t1 - segment.t0;
  const share = span > 0 ? Math.min(Math.max((t - segment.t0) / span, 0), 1) : 1;
  const point = segment.start.map((value, axis) => value + (segment.end[axis] - value) * share);
  return { point, op: segment.op, setup: segment.setup, axis: segment.axis ? mixAxes(segment.axis, share) : null };
}

/**
 * Draws the toolpaths over the file's own lines, which it puts away. `context` is the viewport runtime's
 * (`LineSegments2`, `LineSegmentsGeometry`, `LineMaterial` and the screen-space material registry); without
 * them nothing is drawn and the file's lines stay. Returns the paths, to `update` as the view changes and
 * `dispose` when done, or null.
 *
 * @param {typeof import("three")} THREE
 * @param {import("three").Object3D} root  The GLB's scene (the glTF scene root).
 * @param {object} job  `readCamJob(root)`.
 * @param {{ context: object, cadRoot?: import("three").Object3D | null, scheme?: "light" | "dark", pixelRatio?: number }} options
 */
export function createCamPaths(THREE, root, job, { context, cadRoot = null, scheme = "light", pixelRatio = 1 } = {}) {
  if (!root || !job || !context?.LineSegments2 || !context.LineSegmentsGeometry || !context.LineMaterial) return null;
  const frame = cadFrame(THREE, root, cadRoot);
  const { groups, timeline } = readCamSegments(THREE, root, job);
  const native = camToolpathObjects(root).map(({ object }) => ({ object, visible: object.visible }));
  const ratio = Math.min(Math.max(Number(pixelRatio) || 1, 1), 2);
  let colours = camOpColours(job, scheme);
  let rapid = RAPID_COLOURS[scheme] || RAPID_COLOURS.light;
  const drawn = [];
  for (const group of groups) {
    if (!group.starts.length) continue;
    const feed = group.kind === "feed";
    const width = (feed ? FEED_WIDTH : RAPID_WIDTH) * ratio;
    const line = createScreenSpaceLineSegments(context, group.positions, {
      color: feed ? colours[group.op] || rapid : rapid, opacity: SHOWN[group.kind], lineWidth: width, depthBias: topologyLineDepthBiasForWidth(width)
    });
    if (!line) continue;
    if (!feed) {
      line.material.dashed = true;
      line.material.dashSize = DASH_MM / frame.mmPerUnit;
      line.material.gapSize = GAP_MM / frame.mmPerUnit;
      line.computeLineDistances();
      line.material.needsUpdate = true;
    }
    line.name = `cam-${group.kind}-${group.op}`;
    line.raycast = noRaycast;
    line.userData.camDrawn = true;
    syncLineMaterialOpacity(line.material, SHOWN[group.kind]);
    root.add(line);
    drawn.push({ ...group, line, cut: null });
  }
  for (const { object } of native) object.visible = false;

  // The segment under way, drawn only up to the tool, is put back whole before another is cut.
  const restore = (entry) => {
    if (!entry.cut) return;
    const data = entry.line.geometry.attributes.instanceStart?.data;
    if (data) {
      data.array.set(entry.cut.end, entry.cut.index * 6 + 3);
      markRange(data, entry.cut.index * 6 + 3, 3);
    }
    entry.cut = null;
  };
  const cutAt = (entry, index, t) => {
    const data = entry.line.geometry.attributes.instanceStart?.data;
    if (!data) return;
    const t0 = entry.starts[index];
    const t1 = entry.ends[index];
    if (!(t < t1) || !(t1 > t0)) return;
    const share = (t - t0) / (t1 - t0);
    const offset = index * 6;
    const end = Array.from(data.array.subarray(offset + 3, offset + 6));
    const start = data.array.subarray(offset, offset + 3);
    entry.cut = { index, end };
    data.array.set(end.map((value, axis) => start[axis] + (value - start[axis]) * share), offset + 3);
    markRange(data, offset + 3, 3);
  };

  let last = "";
  return {
    frame,
    timeline,
    /** How many objects were drawn: one per operation and kind. */
    get count() { return drawn.length; },
    /** The colours for a scheme: each operation's, and the rapids'. */
    style(nextScheme) {
      colours = camOpColours(job, nextScheme);
      rapid = RAPID_COLOURS[nextScheme] || RAPID_COLOURS.light;
      for (const entry of drawn) entry.line.material.color.set(entry.kind === "feed" ? colours[entry.op] || rapid : rapid);
      last = "";
    },
    /**
     * What is shown: feed moves and rapids each on or off, an isolated set of operations (the rest dimmed), a
     * hidden set (put away, whatever is isolated), and while playback runs, the moment (`time`, program seconds)
     * the paths are drawn up to, and the setup it plays (the others' paths put away). Returns whether anything changed.
     */
    update({ toolpaths = true, rapids = true, isolate = null, hidden = null, time = null, setup = null } = {}) {
      const key = JSON.stringify([toolpaths, rapids, isolate ? [...isolate] : null, hidden ? [...hidden] : null, time, setup]);
      if (key === last) return false;
      last = key;
      for (const entry of drawn) {
        const feed = entry.kind === "feed";
        entry.line.visible = (feed ? toolpaths : rapids) && (!setup || entry.setup === setup) && !hidden?.has(entry.op);
        const dim = Boolean(isolate) && !isolate.has(entry.op);
        syncLineMaterialOpacity(entry.line.material, dim ? DIM[entry.kind] : SHOWN[entry.kind]);
        restore(entry);
        if (time === null || !Number.isFinite(time)) {
          entry.line.geometry.instanceCount = Infinity;
          continue;
        }
        // Segments that start before the moment; the last of them, if still under way, cut where the tool is.
        const shown = upperBound(entry.starts, time - 1e-9);
        entry.line.geometry.instanceCount = shown;
        if (shown > 0) cutAt(entry, shown - 1, time);
      }
      return true;
    },
    /** Where the tool is at a moment (`toolPositionAt`). */
    toolAt: (t, setup = null) => toolPositionAt(timeline, t, setup),
    dispose() {
      for (const entry of drawn) {
        entry.line.removeFromParent();
        entry.line.userData.beforeDispose?.();
        entry.line.geometry.dispose();
        entry.line.material.dispose();
      }
      drawn.length = 0;
      for (const { object, visible } of native) object.visible = visible;
    },
  };
}

/** Uploads only what changed of a line's buffer, where three can. */
function markRange(data, start, count) {
  if (typeof data.addUpdateRange === "function") data.addUpdateRange(start, count);
  data.needsUpdate = true;
}

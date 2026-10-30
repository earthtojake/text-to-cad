import { createScreenSpaceLineSegments, syncLineMaterialOpacity, topologyLineDepthBiasForWidth } from "@text-to-cad/core/common/renderEdges.js";
import { RAPID_COLOURS, camOpColours } from "./colours.js";

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
 * (`{ setup, kind: "feed" | "rapid" }`).
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

/** The file's toolpath objects: every line of the scene with a time and an operation per vertex (`_CAM_T`, `_CAM_OP`). */
export function camToolpathObjects(root) {
  const found = [];
  root?.traverse?.((object) => {
    if (object.userData?.camDrawn || !object.isLineSegments) return;
    const geometry = object.geometry;
    if (geometry?.getAttribute("position") && geometry.getAttribute("_cam_t") && geometry.getAttribute("_cam_op")) {
      found.push({ object, kind: object.userData?.kind === "rapid" ? "rapid" : "feed", setup: String(object.userData?.setup ?? "") });
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
    /** A CAD direction ([x, y, z]) in the root's frame, unit length. */
    direction: (vector) => new THREE.Vector3(...vector).transformDirection(toLocal),
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
export function readCamSegments(THREE, root) {
  root.updateWorldMatrix(true, true);
  const toRoot = root.matrixWorld.clone().invert();
  const groups = new Map();
  const point = new THREE.Vector3();
  for (const { object, kind, setup } of camToolpathObjects(root)) {
    const geometry = object.geometry;
    const position = geometry.getAttribute("position");
    const times = geometry.getAttribute("_cam_t");
    const ops = geometry.getAttribute("_cam_op");
    const index = geometry.index;
    const vertex = (i) => (index ? index.getX(i) : i);
    const pairs = Math.floor((index ? index.count : position.count) / 2);
    const matrix = toRoot.clone().multiply(object.matrixWorld);
    for (let k = 0; k < pairs; k += 1) {
      const a = vertex(k * 2);
      const b = vertex(k * 2 + 1);
      const t0 = times.getX(a);
      const t1 = times.getX(b);
      const op = Math.round(ops.getX(a));
      const key = `${kind}:${op}`;
      let group = groups.get(key);
      if (!group) {
        group = { key, kind, op, setup, segments: [] };
        groups.set(key, group);
      }
      const start = point.fromBufferAttribute(position, a).applyMatrix4(matrix).toArray();
      const end = point.fromBufferAttribute(position, b).applyMatrix4(matrix).toArray();
      group.segments.push({ start, end, t0, t1, op, setup });
    }
  }
  const all = [];
  const sorted = [...groups.values()].map((group) => {
    const segments = group.segments.sort((a, b) => a.t0 - b.t0);
    // One at a time: spread into push(), a large job's segments pass V8's argument limit (a stack overflow).
    for (const segment of segments) all.push(segment);
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

/**
 * Where the tool is at a moment of the program: on the segment under way, between its ends by time; in a
 * pause (a tool change), at the end of the last move; before the first, at its start. Null with no segments.
 * Only a setup's own segments when `setup` names one.
 */
export function toolPositionAt(timeline, t, setup = null) {
  const { segments, starts } = timeline;
  if (!segments.length) return null;
  let i = upperBound(starts, t) - 1;
  while (i >= 0 && setup && segments[i].setup !== setup) i -= 1;
  if (i < 0) {
    const first = setup ? segments.find((segment) => segment.setup === setup) : segments[0];
    return first ? { point: [...first.start], op: first.op, setup: first.setup } : null;
  }
  const segment = segments[i];
  const span = segment.t1 - segment.t0;
  const share = span > 0 ? Math.min(Math.max((t - segment.t0) / span, 0), 1) : 1;
  const point = segment.start.map((value, axis) => value + (segment.end[axis] - value) * share);
  return { point, op: segment.op, setup: segment.setup };
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
 * @param {{ context: object, cadRoot?: import("three").Object3D | null, scheme?: "light" | "dark", pixelRatio?: number,
 *   parent?: import("three").Object3D }} options  `parent`: what the lines hang from, placed where `root` is (the
 *   viewer's holder beside the scene, `camView.jsx`); the root itself by default.
 */
export function createCamPaths(THREE, root, job, { context, cadRoot = null, scheme = "light", pixelRatio = 1, parent = root } = {}) {
  if (!root || !job || !context?.LineSegments2 || !context.LineSegmentsGeometry || !context.LineMaterial) return null;
  const frame = cadFrame(THREE, root, cadRoot);
  const { groups, timeline } = readCamSegments(THREE, root);
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
    parent.add(line);
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

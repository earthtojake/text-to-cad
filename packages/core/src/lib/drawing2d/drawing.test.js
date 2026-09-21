import assert from "node:assert/strict";
import test from "node:test";

import {
  DRAWING_HAIRLINE_CSS_PX,
  DRAWING_SCHEMA_VERSION,
  clearSurface,
  drawDrawing,
  prepareDrawing
} from "./drawing.js";
import { fitTransform } from "./transform.js";

/** A `Path2D` that records what was built into it instead of rasterising it. */
class RecordingPath {
  constructor() {
    this.commands = [];
  }

  moveTo(x, y) { this.commands.push(["moveTo", x, y]); }

  lineTo(x, y) { this.commands.push(["lineTo", x, y]); }

  quadraticCurveTo(cx, cy, x, y) { this.commands.push(["quadraticCurveTo", cx, cy, x, y]); }

  bezierCurveTo(c1x, c1y, c2x, c2y, x, y) { this.commands.push(["bezierCurveTo", c1x, c1y, c2x, c2y, x, y]); }

  closePath() { this.commands.push(["closePath"]); }
}

/** A 2D context that records the calls a drawing makes, in order. */
function recordingContext() {
  const calls = [];
  const state = { fillStyle: null, strokeStyle: null, lineWidth: null, lineJoin: null, lineCap: null };
  return {
    calls,
    get lineWidth() { return state.lineWidth; },
    set lineWidth(value) { state.lineWidth = value; calls.push(["lineWidth", value]); },
    get fillStyle() { return state.fillStyle; },
    set fillStyle(value) { state.fillStyle = value; calls.push(["fillStyle", value]); },
    get strokeStyle() { return state.strokeStyle; },
    set strokeStyle(value) { state.strokeStyle = value; calls.push(["strokeStyle", value]); },
    get lineJoin() { return state.lineJoin; },
    set lineJoin(value) { state.lineJoin = value; calls.push(["lineJoin", value]); },
    get lineCap() { return state.lineCap; },
    set lineCap(value) { state.lineCap = value; calls.push(["lineCap", value]); },
    save() { calls.push(["save"]); },
    restore() { calls.push(["restore"]); },
    setTransform(...args) { calls.push(["setTransform", ...args]); },
    clearRect(...args) { calls.push(["clearRect", ...args]); },
    fillRect(...args) { calls.push(["fillRect", ...args]); },
    beginPath() { calls.push(["beginPath"]); },
    arc(...args) { calls.push(["arc", ...args]); },
    fill(...args) { calls.push(["fill", ...args]); },
    stroke(...args) { calls.push(["stroke", ...args]); }
  };
}

function payload(primitives, extra = {}) {
  return {
    schemaVersion: DRAWING_SCHEMA_VERSION,
    units: { insunits: 4, name: "Millimeters", toMillimetres: 1 },
    bounds: [0, 0, 10, 10],
    layers: [{ name: "0", color: null, count: primitives.length }],
    primitives,
    ...extra
  };
}

function prepare(primitives, extra) {
  return prepareDrawing(payload(primitives, extra), { Path2D: RecordingPath });
}

test("lines of one colour share a single stroke path", () => {
  const drawable = prepare([
    { type: "lines", layer: "0", color: null, geometry: [[0, 0, 10, 0], [10, 0, 10, 10]] },
    { type: "lines", layer: "CUT", color: "#ff0000", geometry: [[0, 0, 0, 10]] },
    { type: "lines", layer: "0", color: null, geometry: [[10, 10, 0, 10]] }
  ]);
  assert.equal(drawable.strokes.length, 2);
  assert.deepEqual(drawable.strokes.map((entry) => entry.color), [null, "#ff0000"]);
  assert.deepEqual(drawable.strokes[0].path.commands, [
    ["moveTo", 0, 0], ["lineTo", 10, 0],
    ["moveTo", 10, 0], ["lineTo", 10, 10],
    ["moveTo", 10, 10], ["lineTo", 0, 10]
  ]);
  assert.equal(drawable.primitiveCount, 3);
});

test("path commands become the matching Path2D calls", () => {
  const drawable = prepare([{
    type: "path",
    layer: "0",
    color: "#00ff00",
    geometry: [["M", 0, 0], ["L", 1, 0], ["Q", 2, 0, 2, 1], ["C", 2, 2, 1, 3, 0, 3], ["Z"]]
  }]);
  assert.deepEqual(drawable.strokes[0].path.commands, [
    ["moveTo", 0, 0],
    ["lineTo", 1, 0],
    ["quadraticCurveTo", 2, 0, 2, 1],
    ["bezierCurveTo", 2, 2, 1, 3, 0, 3],
    ["closePath"]
  ]);
});

test("one filled-paths primitive is ONE path, so its inner ring is a hole", () => {
  const drawable = prepare([{
    type: "filled-paths",
    layer: "HATCH",
    color: "#0000ff",
    geometry: [
      [["M", 0, 0], ["L", 10, 0], ["L", 10, 10], ["L", 0, 10], ["Z"]],
      [["M", 3, 3], ["L", 7, 3], ["L", 7, 7], ["L", 3, 7], ["Z"]]
    ]
  }]);
  assert.equal(drawable.fills.length, 1);
  assert.equal(drawable.fills[0].paths.length, 1);
  assert.equal(drawable.fills[0].paths[0].commands.filter(([name]) => name === "moveTo").length, 2);
});

test("two fills of one colour share a fillStyle but never share a path", () => {
  const square = [[["M", 0, 0], ["L", 1, 0], ["L", 1, 1], ["Z"]]];
  const drawable = prepare([
    { type: "filled-paths", layer: "H", color: "#0000ff", geometry: square },
    { type: "filled-paths", layer: "H", color: "#0000ff", geometry: square }
  ]);
  assert.equal(drawable.fills.length, 1);
  assert.equal(drawable.fills[0].paths.length, 2);
  assert.notEqual(drawable.fills[0].paths[0], drawable.fills[0].paths[1]);
});

test("a filled polygon is an explicitly closed ring", () => {
  const drawable = prepare([
    { type: "filled-polygon", layer: "0", color: null, geometry: [[0, 0], [4, 0], [4, 4]] }
  ]);
  assert.deepEqual(drawable.fills[0].paths[0].commands, [
    ["moveTo", 0, 0], ["lineTo", 4, 0], ["lineTo", 4, 4], ["closePath"]
  ]);
});

test("points are collected per colour as flat coordinates", () => {
  const drawable = prepare([
    { type: "point", layer: "0", color: null, geometry: [1, 2] },
    { type: "point", layer: "0", color: null, geometry: [3, 4] }
  ]);
  assert.deepEqual(drawable.points, [{ color: null, coordinates: [1, 2, 3, 4] }]);
});

test("the default pen stays null through prepare, so one payload serves both themes", () => {
  const drawable = prepare([
    { type: "lines", layer: "0", color: null, geometry: [[0, 0, 1, 1]] },
    { type: "lines", layer: "0", color: "#ffffff", geometry: [[0, 0, 1, 1]] }
  ]);
  assert.deepEqual(drawable.strokes.map((entry) => entry.color), [null, "#ffffff"]);
});

test("an unknown primitive type is refused, naming it and the schema version", () => {
  assert.throws(
    () => prepare([{ type: "nurbs-surface", layer: "0", color: null, geometry: [] }]),
    (error) => /"nurbs-surface"/.test(error.message)
      && new RegExp(`schemaVersion ${DRAWING_SCHEMA_VERSION}`).test(error.message)
      && /primitives\[0\]/.test(error.message)
  );
});

test("an unknown path command is refused, naming it", () => {
  assert.throws(
    () => prepare([{ type: "path", layer: "0", color: null, geometry: [["A", 1, 2]] }]),
    /unknown path command "A".*only M, L, Q, C and Z/s
  );
});

test("a payload from another schema version is refused with the upgrade to make", () => {
  assert.throws(
    () => prepareDrawing({ ...payload([]), schemaVersion: 2 }, { Path2D: RecordingPath }),
    /schemaVersion 2, but this build reads version 1.*Update cadgen and the app together/s
  );
  assert.throws(() => prepareDrawing(null, { Path2D: RecordingPath }), /needs a drawing payload object/);
  assert.throws(
    () => prepareDrawing({ ...payload([]), primitives: "none" }, { Path2D: RecordingPath }),
    /`primitives` must be an array/
  );
  assert.throws(
    () => prepareDrawing({ ...payload([]), bounds: [0, 0] }, { Path2D: RecordingPath }),
    /\[minX, minY, maxX, maxY\] or null/
  );
});

test("an empty drawing prepares, carrying bounds null", () => {
  const drawable = prepareDrawing({ ...payload([]), bounds: null }, { Path2D: RecordingPath });
  assert.equal(drawable.bounds, null);
  assert.equal(drawable.primitiveCount, 0);
  assert.deepEqual(drawable.strokes, []);
});

test("a runtime without Path2D is told to inject one", () => {
  const original = globalThis.Path2D;
  delete globalThis.Path2D;
  try {
    assert.throws(() => prepareDrawing(payload([])), /pass one as `prepareDrawing\(payload, \{ Path2D \}\)`/);
  } finally {
    if (original) {
      globalThis.Path2D = original;
    }
  }
});

test("drawing sets the view transform once, flipping y and folding in the pixel ratio", () => {
  const ctx = recordingContext();
  const drawable = prepare([{ type: "lines", layer: "0", color: null, geometry: [[0, 0, 10, 10]] }]);
  drawDrawing(ctx, drawable, { transform: { scale: 3, offsetX: 20, offsetY: 40 }, foreground: "#111", pixelRatio: 2 });
  assert.deepEqual(ctx.calls[1], ["setTransform", 6, 0, 0, -6, 40, 80]);
  assert.equal(ctx.calls[0][0], "save");
  assert.equal(ctx.calls.at(-1)[0], "restore");
});

test("strokes are a constant screen width, whatever the zoom", () => {
  const ctx = recordingContext();
  const drawable = prepare([{ type: "lines", layer: "0", color: null, geometry: [[0, 0, 10, 10]] }]);
  for (const scale of [0.25, 1, 64]) {
    drawDrawing(ctx, drawable, { transform: { scale, offsetX: 0, offsetY: 0 }, foreground: "#111" });
    const width = ctx.calls.filter(([name]) => name === "lineWidth").at(-1)[1];
    assert.equal(width * scale, DRAWING_HAIRLINE_CSS_PX);
  }
});

test("the default pen is painted with the theme foreground, and a hex pen is not", () => {
  const drawable = prepare([
    { type: "lines", layer: "0", color: null, geometry: [[0, 0, 1, 1]] },
    { type: "lines", layer: "CUT", color: "#ff0000", geometry: [[0, 0, 1, 1]] },
    { type: "filled-polygon", layer: "0", color: null, geometry: [[0, 0], [1, 0], [1, 1]] }
  ]);
  const light = recordingContext();
  drawDrawing(light, drawable, { transform: { scale: 1, offsetX: 0, offsetY: 0 }, foreground: "#0b0b0b" });
  assert.deepEqual(
    light.calls.filter(([name]) => name === "strokeStyle").map(([, value]) => value),
    ["#0b0b0b", "#ff0000"]
  );
  assert.deepEqual(light.calls.filter(([name]) => name === "fillStyle").map(([, value]) => value), ["#0b0b0b"]);

  const dark = recordingContext();
  drawDrawing(dark, drawable, { transform: { scale: 1, offsetX: 0, offsetY: 0 }, foreground: "#fafafa" });
  assert.deepEqual(
    dark.calls.filter(([name]) => name === "strokeStyle").map(([, value]) => value),
    ["#fafafa", "#ff0000"]
  );
});

test("fills go down before strokes, and are filled even-odd", () => {
  const ctx = recordingContext();
  const drawable = prepare([
    { type: "lines", layer: "0", color: null, geometry: [[0, 0, 1, 1]] },
    { type: "filled-polygon", layer: "0", color: "#0000ff", geometry: [[0, 0], [1, 0], [1, 1]] }
  ]);
  drawDrawing(ctx, drawable, { transform: { scale: 1, offsetX: 0, offsetY: 0 }, foreground: "#111" });
  const order = ctx.calls.map(([name]) => name);
  assert.ok(order.indexOf("fill") < order.indexOf("stroke"), `fills must precede strokes: ${order.join(",")}`);
  const fill = ctx.calls.find(([name]) => name === "fill");
  assert.equal(fill[2], "evenodd");
});

test("points are drawn as marks of a constant screen radius", () => {
  const ctx = recordingContext();
  const drawable = prepare([{ type: "point", layer: "0", color: "#00ff00", geometry: [4, 5] }]);
  drawDrawing(ctx, drawable, { transform: { scale: 8, offsetX: 0, offsetY: 0 }, foreground: "#111" });
  const arc = ctx.calls.find(([name]) => name === "arc");
  assert.equal(arc[1], 4);
  assert.equal(arc[2], 5);
  assert.ok(Math.abs(arc[3] * 8 - 1.6) < 1e-12, `expected a 1.6 CSS px radius, got ${arc[3] * 8}`);
});

test("drawing without a foreground is refused, naming the default pen", () => {
  const drawable = prepare([]);
  assert.throws(
    () => drawDrawing(recordingContext(), drawable, { transform: { scale: 1, offsetX: 0, offsetY: 0 } }),
    /default pen \(`color: null`\) has no colour of its own/
  );
  assert.throws(
    () => drawDrawing(recordingContext(), drawable, { transform: { scale: 0, offsetX: 0, offsetY: 0 }, foreground: "#111" }),
    /positive scale/
  );
});

test("clearSurface paints CSS pixels on a DPR backing store", () => {
  const filled = recordingContext();
  clearSurface(filled, { width: 300, height: 200, pixelRatio: 2, background: "#fff" });
  assert.deepEqual(filled.calls[1], ["setTransform", 2, 0, 0, 2, 0, 0]);
  assert.deepEqual(filled.calls.at(-2), ["fillRect", 0, 0, 300, 200]);

  const cleared = recordingContext();
  clearSurface(cleared, { width: 300, height: 200 });
  assert.deepEqual(cleared.calls.at(-2), ["clearRect", 0, 0, 300, 200]);
});

test("a fitted drawing paints inside its pane", () => {
  const drawable = prepare([{ type: "lines", layer: "0", color: null, geometry: [[0, 0, 10, 10]] }]);
  const transform = fitTransform(drawable.bounds, 200, 200, { margin: 10 });
  const ctx = recordingContext();
  drawDrawing(ctx, drawable, { transform, foreground: "#111" });
  const [, a, , , d, e, f] = ctx.calls[1];
  assert.equal(a, transform.scale);
  assert.equal(d, -transform.scale);
  assert.ok(e >= 10 && f <= 190, `expected the fit inside the margin, got ${e} / ${f}`);
});

import assert from "node:assert/strict";
import test from "node:test";

import { PerspectiveCamera } from "three";

import {
  MEASURE_SERIES_COLORS,
  drawMeasureDimension,
  drawMeasureSnapChip,
  drawMeasureSnapMarker,
  drawPulsingEndRing,
  measureLabelText,
  measureSeriesColor,
  screenDimensionLayout,
  screenSpaceDimensionLayout
} from "./measureDimension.js";
import { measureDimensionSegments } from "./measureLines.js";

function makePerspectiveCamera() {
  const camera = new PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  return camera;
}

function makeRect() {
  return { left: 0, top: 0, width: 800, height: 600 };
}

function mockContext() {
  const noop = () => {};
  return {
    save: noop,
    restore: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    closePath: noop,
    rect: noop,
    roundRect: noop,
    arc: noop,
    fill: noop,
    stroke: noop,
    fillRect: noop,
    strokeRect: noop,
    fillText: noop,
    measureText: () => ({ width: 30 })
  };
}

test("measureLabelText formats a plain euclidean measurement", () => {
  assert.equal(
    measureLabelText({ euclidean: 15.456, perpendicular: null, unit: "mm" }),
    "15.46 mm"
  );
});

test("measureLabelText prefixes the perpendicular value with a perpendicular sign", () => {
  assert.equal(
    measureLabelText({ euclidean: 16.2, perpendicular: 15.456, unit: "mm" }),
    "⟂ 15.46 mm"
  );
});

test("measureLabelText returns an empty string for missing measurements", () => {
  assert.equal(measureLabelText(null), "");
  assert.equal(measureLabelText({}), "");
  assert.equal(measureLabelText({ euclidean: NaN, unit: "mm" }), "");
});

test("screenSpaceDimensionLayout projects endpoints and builds stable screen-space figure", () => {
  const layout = screenSpaceDimensionLayout(
    { point: [0, 0, 0] },
    { point: [1, 0, 0] },
    null,
    makePerspectiveCamera(),
    makeRect()
  );
  assert.ok(layout);
  assert.equal(layout.rings.length, 2);
  assert.equal(layout.witnesses.length, 2);
  assert.equal(layout.dimensionLine.length, 2);
  assert.equal(layout.arrows.length, 2);
  assert.ok(Number.isFinite(layout.label.x));
  assert.ok(Number.isFinite(layout.label.y));
  assert.deepEqual(layout.rings[0], { x: 400, y: 300 });
  assert.ok(layout.rings[1].x > 400);
  assert.equal(layout.rings[1].y, 300);
});

test("screenSpaceDimensionLayout returns null for invalid or unprojectable points", () => {
  assert.equal(screenSpaceDimensionLayout(null, { point: [1, 0, 0] }, null, makePerspectiveCamera(), makeRect()), null);
  assert.equal(screenSpaceDimensionLayout({ point: [0, 0, 0] }, { point: [0, 0, 9] }, null, makePerspectiveCamera(), makeRect()), null);
});

test("screenDimensionLayout projects a world-space construction into client space", () => {
  const segments = measureDimensionSegments(
    { point: [0, 0, 0] },
    { point: [1, 0, 0] },
    null,
    { camera: makePerspectiveCamera() }
  );
  const layout = screenDimensionLayout(segments, makePerspectiveCamera(), makeRect());
  assert.ok(layout);
  assert.equal(layout.rings.length, 2);
  assert.equal(layout.witnesses.length, 2);
  assert.equal(layout.dimensionLine.length, 2);
  assert.equal(layout.ticks.length, 2);
  assert.ok(Number.isFinite(layout.label.x));
  assert.ok(Number.isFinite(layout.label.y));
  assert.deepEqual(layout.rings[0], { x: 400, y: 300 });
  assert.ok(layout.rings[1].x > 400);
  assert.equal(layout.rings[1].y, 300);
});

test("screenDimensionLayout returns null for missing segments or camera", () => {
  assert.equal(screenDimensionLayout(null, makePerspectiveCamera(), makeRect()), null);
  assert.equal(
    screenDimensionLayout(
      measureDimensionSegments({ point: [0, 0, 0] }, { point: [1, 0, 0] }, null, {
        camera: makePerspectiveCamera()
      }),
      null,
      makeRect()
    ),
    null
  );
});

test("screenDimensionLayout returns null when a construction point is behind the camera", () => {
  const segments = measureDimensionSegments(
    { point: [0, 0, 0] },
    { point: [0, 0, 9] },
    null,
    { camera: makePerspectiveCamera() }
  );
  assert.equal(screenDimensionLayout(segments, makePerspectiveCamera(), makeRect()), null);
});

test("drawMeasureDimension tolerates a missing context or layout", () => {
  assert.doesNotThrow(() => drawMeasureDimension(null, null));
  assert.doesNotThrow(() => drawMeasureDimension(mockContext(), null));
  assert.doesNotThrow(() => drawMeasureDimension(null, { rings: [], witnesses: [] }));
});

test("drawMeasureDimension draws without throwing on a valid layout", () => {
  const layout = screenSpaceDimensionLayout(
    { point: [0, 0, 0] },
    { point: [1, 0, 0] },
    null,
    makePerspectiveCamera(),
    makeRect()
  );
  assert.doesNotThrow(() => {
    drawMeasureDimension(mockContext(), layout, {
      label: "15.46 mm",
      bounds: makeRect()
    });
  });
});

test("drawMeasureDimension clamps the label chip inside the canvas bounds", () => {
  const layout = screenSpaceDimensionLayout(
    { point: [0, 0, 0] },
    { point: [1, 0, 0] },
    null,
    makePerspectiveCamera(),
    makeRect()
  );
  const calls = [];
  const context = mockContext();
  context.roundRect = (x) => {
    calls.push(x);
  };
  context.rect = (x) => {
    calls.push(x);
  };
  context.measureText = () => ({ width: 200 });
  drawMeasureDimension(context, layout, {
    label: "very long label",
    bounds: { width: 240, height: 600 }
  });
  assert.ok(calls.length > 0);
  assert.ok(calls[0] >= 4, `label chip starts at ${calls[0]}, expected >= 4`);
  assert.ok(calls[0] <= 240 - 200 - 12 - 4, `label chip starts at ${calls[0]}, expected <= ${240 - 200 - 12 - 4}`);
});

test("drawPulsingEndRing tolerates missing context or point", () => {
  assert.doesNotThrow(() => drawPulsingEndRing(null, null));
  assert.doesNotThrow(() => drawPulsingEndRing(mockContext(), null));
  assert.doesNotThrow(() => drawPulsingEndRing(mockContext(), { x: 10, y: 10 }));
});

function recordingContext() {
  const calls = [];
  const record = (name) => (...args) => calls.push({ name, args });
  return {
    calls,
    save: record("save"),
    restore: record("restore"),
    beginPath: record("beginPath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    arc: record("arc"),
    rect: record("rect"),
    roundRect: record("roundRect"),
    closePath: record("closePath"),
    fill: record("fill"),
    stroke: record("stroke"),
    fillText: record("fillText"),
    measureText: () => ({ width: 60 })
  };
}

test("drawMeasureSnapMarker draws a distinct shape per snap kind", () => {
  const shapeFor = (snapKind) => {
    const context = recordingContext();
    drawMeasureSnapMarker(context, { x: 50, y: 50 }, { snapKind, now: 0 });
    return context.calls.map((call) => call.name);
  };
  // A vertex is a filled square, an edge a filled ring, a face a hollow diamond.
  assert.ok(shapeFor("vertex").includes("rect"));
  assert.ok(shapeFor("edge").includes("arc"));
  assert.ok(shapeFor("face").includes("closePath"));
  // An unsnapped point gets the crosshair only, so it cannot be mistaken for a snap.
  const free = shapeFor("free");
  assert.ok(!free.includes("arc") && !free.includes("rect") && !free.includes("closePath"));
  assert.ok(free.includes("stroke"));
});

test("drawMeasureSnapMarker ignores unusable positions", () => {
  const context = recordingContext();
  drawMeasureSnapMarker(context, { x: NaN, y: 10 }, { snapKind: "edge" });
  drawMeasureSnapMarker(context, null, { snapKind: "edge" });
  assert.equal(context.calls.length, 0);
});

test("drawMeasureSnapChip keeps the caption inside the viewport", () => {
  const context = recordingContext();
  // Near the bottom-right corner the chip would otherwise be drawn off-screen.
  drawMeasureSnapChip(context, { x: 795, y: 595 }, "Edge  L 25.13 mm", { bounds: { width: 800, height: 600 } });
  const chip = context.calls.find((call) => call.name === "roundRect");
  assert.ok(chip);
  const [x, y, width, height] = chip.args;
  assert.ok(x + width <= 800, "chip runs past the right edge");
  assert.ok(y + height <= 600, "chip runs past the bottom edge");

  const empty = recordingContext();
  drawMeasureSnapChip(empty, { x: 10, y: 10 }, "", { bounds: { width: 800, height: 600 } });
  assert.equal(empty.calls.length, 0);
});

test("measureSeriesColor cycles the palette and tolerates junk indices", () => {
  assert.equal(measureSeriesColor(0), MEASURE_SERIES_COLORS[0]);
  assert.equal(measureSeriesColor(3), MEASURE_SERIES_COLORS[3]);
  // Wraps rather than running off the end, so the 9th measurement still has a colour.
  assert.equal(measureSeriesColor(MEASURE_SERIES_COLORS.length), MEASURE_SERIES_COLORS[0]);
  assert.equal(measureSeriesColor(MEASURE_SERIES_COLORS.length + 2), MEASURE_SERIES_COLORS[2]);
  assert.equal(measureSeriesColor(-1), MEASURE_SERIES_COLORS[MEASURE_SERIES_COLORS.length - 1]);
  assert.equal(measureSeriesColor(undefined), MEASURE_SERIES_COLORS[0]);
  assert.equal(measureSeriesColor("nope"), MEASURE_SERIES_COLORS[0]);
});

test("the series palette stays muted enough to sit over a shaded model", () => {
  for (const color of MEASURE_SERIES_COLORS) {
    assert.match(color, /^#[0-9a-f]{6}$/, `${color} is not a 6-digit hex`);
    const [r, g, b] = [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16));
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    // Mid-tone: bright enough on a dark theme, dark enough on a light one.
    const lightness = (max + min) / 2 / 255;
    assert.ok(lightness > 0.5 && lightness < 0.85, `${color} lightness ${lightness.toFixed(2)} out of range`);
    // Pastel, not saturated: no channel may dominate the way a pure hue does.
    assert.ok((max - min) / 255 < 0.45, `${color} is too saturated`);
  }
  assert.equal(new Set(MEASURE_SERIES_COLORS).size, MEASURE_SERIES_COLORS.length, "palette has duplicates");
});

test("consecutive series colours are far apart, not neighbouring hues", () => {
  // Colours are handed out in sequence, so measurements taken one after another
  // must not land on adjacent hues — that pair is the one most likely to be
  // compared, in the viewport and in the panel.
  const rgb = (color) => [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16));
  let closest = Infinity;
  for (let index = 0; index < MEASURE_SERIES_COLORS.length; index += 1) {
    const a = rgb(MEASURE_SERIES_COLORS[index]);
    const b = rgb(MEASURE_SERIES_COLORS[(index + 1) % MEASURE_SERIES_COLORS.length]);
    closest = Math.min(closest, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]));
  }
  assert.ok(closest > 80, `consecutive colours only ${closest.toFixed(0)} apart in RGB`);
});

test("the series palette is large enough to keep a full panel distinguishable", () => {
  // The panel holds 20 measurements; the palette should cover most of a screen's
  // worth before it repeats.
  assert.ok(MEASURE_SERIES_COLORS.length >= 10, "palette is too small to tell measurements apart");
});

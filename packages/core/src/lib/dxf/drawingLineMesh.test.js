import assert from "node:assert/strict";
import test from "node:test";

import {
  DXF_ENGRAVE_ELEVATION_MM,
  dxfEngraveRibbonPositions,
  drawingLinesToRibbonPositions,
} from "./drawingLineMesh.js";

// A document profile's geometry: two open dimension-style lines, no contours.
const DXF_DATA = {
  geometry: {
    lines: [
      { layer: "DIM", start: [0, 0], end: [100, 0] },
      { layer: "DIM", start: [0, -5], end: [0, 5] },
    ],
    arcs: [],
    circles: [],
  },
};

// A CUT LAYOUT that also carries markings: a closed square to prism, one
// engrave stroke (a score), and an engraved circle (lettering, in miniature).
const ENGRAVED_LAYOUT = {
  bounds: { width: 100, height: 100 },
  geometry: {
    lines: [
      { layer: "CUT", kind: "cut", start: [0, 0], end: [100, 0] },
      { layer: "CUT", kind: "cut", start: [100, 0], end: [100, 100] },
      { layer: "CUT", kind: "cut", start: [100, 100], end: [0, 100] },
      { layer: "CUT", kind: "cut", start: [0, 100], end: [0, 0] },
      { layer: "ENGRAVE", kind: "engrave", start: [20, 50], end: [80, 50] },
    ],
    arcs: [],
    circles: [
      { layer: "ENGRAVE", kind: "engrave", center: [50, 20], radius: 5 },
    ],
  },
};

test("open line work becomes ribbon triangles in the sheet plane", () => {
  const positions = drawingLinesToRibbonPositions(DXF_DATA);
  // Two segments, two triangles each, three vertices each.
  assert.equal(positions.length, 2 * 2 * 3 * 3);
  // Every vertex stays in the sheet plane (y = elevation = 0).
  for (let index = 1; index < positions.length; index += 3) {
    assert.equal(positions[index], 0);
  }
  // Ribbon width scales from the drawing diagonal but never below the floor.
  const zs = [];
  for (let index = 0; index < 18; index += 3) {
    zs.push(positions[index + 2]);
  }
  const width = Math.max(...zs) - Math.min(...zs);
  assert.ok(width >= 0.1, `hairline must be at least the 2x0.05mm floor, got ${width}`);
  assert.ok(width < 1, `hairline must stay hairline on a 100mm drawing, got ${width}`);
});

test("triangles face +Y (out of the sheet)", () => {
  const positions = drawingLinesToRibbonPositions(DXF_DATA);
  for (let t = 0; t < positions.length; t += 9) {
    const ax = positions[t], az = positions[t + 2];
    const bx = positions[t + 3], bz = positions[t + 5];
    const cx = positions[t + 6], cz = positions[t + 8];
    // y-component of the cross product in the XZ plane: (c-a) x (b-a) ... glTF
    // winding is counter-clockwise seen from +Y, i.e. cross((b-a),(c-a)).y > 0.
    const crossY = ((bz - az) * (cx - ax)) - ((bx - ax) * (cz - az));
    assert.ok(crossY > 0, `triangle at ${t} winds away from +Y (${crossY})`);
  }
});

test("degenerate and empty inputs produce empty output", () => {
  assert.equal(drawingLinesToRibbonPositions({ geometry: { lines: [] } }).length, 0);
  assert.equal(drawingLinesToRibbonPositions(null).length, 0);
  assert.equal(
    drawingLinesToRibbonPositions({
      geometry: { lines: [{ layer: "", start: [3, 3], end: [3, 3] }] },
    }).length,
    0,
  );
});

test("engraved markings on a CUT LAYOUT become ribbons — the prism never sees them", () => {
  const positions = dxfEngraveRibbonPositions(ENGRAVED_LAYOUT, 1);
  // One straight score plus a sampled circle: strictly more than the score's
  // own two triangles, and every one of them is geometry the prism drops.
  assert.ok(positions.length > 2 * 3 * 3, `expected score + circle, got ${positions.length / 9} triangles`);
});

test("markings ride ON the sheet's face, clear of it by the elevation", () => {
  const thicknessMm = 3;
  const positions = dxfEngraveRibbonPositions(ENGRAVED_LAYOUT, thicknessMm);
  const expected = (thicknessMm / 2) + DXF_ENGRAVE_ELEVATION_MM;
  for (let index = 1; index < positions.length; index += 3) {
    assert.ok(
      Math.abs(positions[index] - expected) < 1e-6,
      `marking at y=${positions[index]} is not on the face at ${expected}`,
    );
  }
  // elevationSign flips WHICH face, for a consumer whose axis map inverts the
  // sheet normal (dxfSoupToGlbPositions sends mesher +y to CAD -Z). Getting
  // this wrong buries every marking under the plate, where it renders as
  // nothing at all — the exact shape of the bug this test guards.
  const flipped = dxfEngraveRibbonPositions(ENGRAVED_LAYOUT, thicknessMm, { elevationSign: -1 });
  for (let index = 1; index < flipped.length; index += 3) {
    assert.ok(Math.abs(flipped[index] + expected) < 1e-6, `flipped marking at y=${flipped[index]}`);
  }
});

test("stroke weight follows the SHEET, not the markings' own extent", () => {
  // Same markings, a ten-times-larger sheet: a serial number in the corner of a
  // big panel must not draw at the hairline of a tiny one.
  const small = dxfEngraveRibbonPositions(ENGRAVED_LAYOUT, 1);
  const large = dxfEngraveRibbonPositions(
    { ...ENGRAVED_LAYOUT, bounds: { width: 1000, height: 1000 } },
    1,
  );
  const spread = (positions) => {
    // The straight score runs along +x, so its ribbon's width is its z spread.
    let min = Infinity;
    let max = -Infinity;
    for (let index = 2; index < 18; index += 3) {
      min = Math.min(min, positions[index]);
      max = Math.max(max, positions[index]);
    }
    return max - min;
  };
  assert.ok(spread(large) > spread(small) * 5, "a larger sheet must draw a proportionally wider hairline");
});

test("a layout with no markings produces no overlay, and never throws", () => {
  // Closed cut contours only: everything is prism, nothing is a stroke.
  const plainCut = {
    bounds: { width: 100, height: 100 },
    geometry: { ...ENGRAVED_LAYOUT.geometry, circles: [] },
  };
  plainCut.geometry.lines = plainCut.geometry.lines.filter((line) => line.kind === "cut");
  assert.equal(dxfEngraveRibbonPositions(plainCut, 1).length, 0);
  assert.equal(dxfEngraveRibbonPositions(null, 1).length, 0);
  assert.equal(dxfEngraveRibbonPositions({ geometry: {} }, 1).length, 0);
});

test("an unclassified OPEN chain is a marking too, not a dropped contour", () => {
  // A witness line, a centre mark, a decorative score: authored on the cut
  // layer but never closing, so the prism cannot use it. The extractor's
  // contract calls it a score, and the overlay is where it becomes visible.
  const positions = dxfEngraveRibbonPositions({ ...DXF_DATA, bounds: { width: 100, height: 10 } }, 1);
  assert.equal(positions.length, 2 * 2 * 3 * 3, "two open chains, two triangles each");
});

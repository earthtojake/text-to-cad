import assert from "node:assert/strict";
import { test } from "node:test";
import { Matrix4, Vector3 } from "three";

import {
  buildFoldBridgeGeometry,
  buildFoldLine,
  buildRegionPlacements,
  clipLoopByHalfPlane,
  buildFoldAdjacency,
  decomposeFoldRegions,
  foldHingeMatrix,
  foldSignedDistance,
  outerMaterialSpanAlongFold
} from "./foldRegions.js";

const PLATE = [[0, 0], [100, 0], [100, 60], [0, 60]];
const L_BLANK = [[0, 0], [100, 0], [100, 30], [30, 30], [30, 80], [0, 80]];

function fold(start, end, angleDeg, { halfThicknessMm = 1 } = {}) {
  return buildFoldLine({
    bendLine: { start, end },
    angleRadians: (angleDeg * Math.PI) / 180,
    halfThicknessMm
  });
}

function place(matrix, point2d) {
  return new Vector3(point2d[0], 0, point2d[1]).applyMatrix4(matrix).toArray();
}

test("a fold line takes its direction from its own endpoints, at any angle", () => {
  const diagonal = fold([0, 0], [10, 10], 90);
  assert.ok(Math.abs(diagonal.direction[0] - Math.SQRT1_2) < 1e-9);
  assert.ok(Math.abs(diagonal.direction[1] - Math.SQRT1_2) < 1e-9);
  // The normal is the direction turned 90 degrees, so the two are perpendicular.
  assert.ok(Math.abs((diagonal.direction[0] * diagonal.normal[0]) + (diagonal.direction[1] * diagonal.normal[1])) < 1e-9);
  // The band's flat width IS the arc length it becomes: 2 * halfWidth = radius * angle.
  assert.ok(Math.abs((2 * diagonal.halfWidth) - (diagonal.neutralRadius * Math.PI / 2)) < 1e-9);
});

test("a zero-length bend line is not a fold line", () => {
  assert.equal(fold([5, 5], [5, 5], 90), null);
});

test("half-plane clipping keeps the requested side and cuts on the band edge", () => {
  const line = fold([50, 0], [50, 60], 90);
  const positive = clipLoopByHalfPlane(PLATE, line, line.halfWidth, true);
  for (const point of positive) {
    assert.ok(foldSignedDistance(line, point) >= line.halfWidth - 1e-3);
  }
  const negative = clipLoopByHalfPlane(PLATE, line, -line.halfWidth, false);
  for (const point of negative) {
    assert.ok(foldSignedDistance(line, point) <= -line.halfWidth + 1e-3);
  }
  // Between them they account for the plate minus the band.
  assert.ok(positive.length >= 4 && negative.length >= 4);
});

test("material span along a fold is measured where the line crosses the contour", () => {
  assert.deepEqual(outerMaterialSpanAlongFold(PLATE, fold([50, 0], [50, 60], 90)), { min: 0, max: 60 });
  // A horizontal line through the same plate spans its width instead.
  const horizontal = outerMaterialSpanAlongFold(PLATE, fold([0, 30], [100, 30], 90));
  assert.deepEqual(horizontal, { min: 0, max: 100 });
});

test("the hinge agrees with the shipped vertical-bend formula", () => {
  // The vertical case is the one the X-slab mesher already drew correctly, so it is the
  // reference: the general hinge must reproduce it exactly, or every previously-good preview
  // would shift.
  const radius = 2.2;
  const angle = Math.PI / 2;
  const halfWidth = (radius * angle) / 2;
  const x = 50;
  const shipped = new Matrix4()
    .makeTranslation(x - halfWidth + (radius * Math.sin(angle)), radius * (1 - Math.cos(angle)), 0)
    .multiply(new Matrix4().makeRotationZ(angle))
    .multiply(new Matrix4().makeTranslation(-(x + halfWidth), 0, 0));
  // Same fold, expressed with the normal pointing +x so the two agree on which side is which.
  const line = {
    bendLine: { start: [x, 0], end: [x, 60] },
    origin: [x, 0],
    direction: [0, 1],
    normal: [1, 0],
    angleRadians: angle,
    neutralRadius: radius,
    halfWidth
  };
  const hinge = foldHingeMatrix(line, 1);
  for (const point of [[x + halfWidth, 0], [x + 30, 0], [x + 30, -9], [x + halfWidth, 17]]) {
    const fromHinge = place(hinge, point).map((value) => Number(value.toFixed(6)));
    const fromShipped = new Vector3(point[0], 0, point[1]).applyMatrix4(shipped).toArray()
      .map((value) => Number(value.toFixed(6)));
    assert.deepEqual(fromHinge, fromShipped, `point ${JSON.stringify(point)}`);
  }
});

test("a fold lifts the child out of the sheet whichever side it is on", () => {
  // The symmetric case that caught a handedness mistake: a U channel folded one flange up and
  // the other DOWN, because the fold's local frame flipped with the side.
  const line = fold([50, 0], [50, 60], 90);
  for (const side of [1, -1]) {
    const hinge = foldHingeMatrix(line, side);
    const entry = [50 + (line.normal[0] * line.halfWidth * side), 60 * 0.5];
    const beyond = [
      entry[0] + (line.normal[0] * 15.9 * side),
      entry[1] + (line.normal[1] * 15.9 * side)
    ];
    const [, entryY] = place(hinge, entry);
    const [, beyondY] = place(hinge, beyond);
    assert.ok(entryY > 0, `side ${side} entry must rise`);
    assert.ok(Math.abs(beyondY - (entryY + 15.9)) < 1e-6, `side ${side} must stay rigid`);
  }
});

test("the fold is rigid: distances inside the child face survive it", () => {
  const line = fold([0, 20], [100, 20], 120);
  const hinge = foldHingeMatrix(line, 1);
  const a = [10, 50];
  const b = [70, 35];
  const flat = Math.hypot(a[0] - b[0], a[1] - b[1]);
  const [ax, ay, az] = place(hinge, a);
  const [bx, by, bz] = place(hinge, b);
  assert.ok(Math.abs(Math.hypot(ax - bx, ay - by, az - bz) - flat) < 1e-6);
});

test("the curved band ends exactly where the hinge puts the child", () => {
  // The continuity that matters: a gap here is what the reported spikes were made of.
  for (const line of [
    fold([50, 0], [50, 60], 90),
    fold([0, 20], [100, 20], 90),
    fold([0, 0], [60, 60], 90),
    fold([50, 0], [50, 60], -90)
  ]) {
    const hinge = foldHingeMatrix(line, 1);
    const entry = [
      line.origin[0] + (line.normal[0] * line.halfWidth),
      line.origin[1] + (line.normal[1] * line.halfWidth)
    ];
    const hinged = place(hinge, entry);
    const bridge = buildFoldBridgeGeometry({
      foldLine: line,
      side: 1,
      span: { min: 0, max: 1 },
      halfThickness: 0,
      segments: 64
    });
    const nearest = bridge.triangles.flat().reduce((best, point) => {
      const distance = Math.hypot(point[0] - hinged[0], point[1] - hinged[1], point[2] - hinged[2]);
      return distance < best ? distance : best;
    }, Infinity);
    assert.ok(nearest < 1e-6, `band must meet the face (gap ${nearest})`);
  }
});

test("a fold splits only the face its segment crosses", () => {
  // The L blank: one fold per arm. Splitting by each fold's infinite LINE instead cut through
  // the other arm as well, and put the faces in a cycle rather than a tree.
  const folds = [fold([60, 0], [60, 30], 90), fold([0, 55], [30, 55], 90)];
  const { regions, adjacency } = decomposeFoldRegions(L_BLANK, folds);
  assert.equal(regions.length, 3, "two folds, three faces");
  assert.equal(adjacency.length, 2, "two hinges, so a tree and not a cycle");
  const { rootIndex, parents } = buildRegionPlacements(regions, folds, adjacency);
  assert.equal(parents.filter((parent) => parent === null).length, 1, "exactly one root");
  assert.ok(regions[rootIndex].area >= Math.max(...regions.map((region) => region.area)) - 1e-9);
});

test("a fold that cuts no face in two is refused, with the shortfall", () => {
  assert.throws(
    () => decomposeFoldRegions(PLATE, [fold([60, 20], [60, 60], 90)]),
    (error) => {
      assert.match(error.message, /runs edge to edge/u);
      assert.match(error.message, /20\.000 mm short/u);
      return true;
    }
  );
});

test("both faces of a two-fold plate keep their flat area", () => {
  const folds = [fold([30, 0], [30, 60], 90), fold([70, 0], [70, 60], 90)];
  const { regions } = decomposeFoldRegions(PLATE, folds);
  const bandArea = folds.reduce((total, line) => total + (2 * line.halfWidth * 60), 0);
  const total = regions.reduce((sum, region) => sum + region.area, 0);
  assert.ok(Math.abs(total - ((100 * 60) - bandArea)) < 1e-6, "faces plus bands account for the blank");
});

test("the face that stays still is the most HINGED one, not the biggest", () => {
  // Anchoring the largest face made identical bend settings fold different shapes on
  // different blanks: on a U channel whose flanges are wider than its web, the largest face
  // is a flange, so "both bends up" folded a Z. The web has two hinges; a flange has one.
  const wideFlanges = [[0, 0], [120, 0], [120, 60], [0, 60]];
  const folds = [fold([40, 0], [40, 60], 90), fold([80, 0], [80, 60], 90)];
  const { regions, adjacency } = decomposeFoldRegions(wideFlanges, folds);
  const { placements, rootIndex } = buildRegionPlacements(regions, folds, adjacency);

  // The web is the middle face, and it is NOT the largest one here.
  const largest = regions.reduce((best, region, index) => (region.area > regions[best].area ? index : best), 0);
  assert.notEqual(rootIndex, largest, "this blank's largest face is a flange, which is the point");
  const rootCentre = regions[rootIndex].centroid[0];
  assert.ok(rootCentre > 40 && rootCentre < 80, "the web must be the face that stays still");

  // Both flanges rise, to the same height: a U, not a Z.
  const heights = regions
    .map((region, index) => place(placements[index], region.centroid)[1])
    .filter((_, index) => index !== rootIndex);
  assert.ok(heights.every((height) => height > 1), `both flanges must rise, got ${heights}`);
  assert.ok(Math.abs(heights[0] - heights[1]) < 1e-6, "and rise equally");
  assert.ok(Math.abs(place(placements[rootIndex], regions[rootIndex].centroid)[1]) < 1e-6);
});

test("opposite bend directions fold a Z, and that still means opposite", () => {
  const plate = [[0, 0], [120, 0], [120, 60], [0, 60]];
  const folds = [fold([40, 0], [40, 60], 90), fold([80, 0], [80, 60], -90)];
  const { regions, adjacency } = decomposeFoldRegions(plate, folds);
  const { placements, rootIndex } = buildRegionPlacements(regions, folds, adjacency);
  const heights = regions
    .map((region, index) => place(placements[index], region.centroid)[1])
    .filter((_, index) => index !== rootIndex);
  assert.equal(heights.length, 2);
  assert.ok(heights[0] * heights[1] < 0, `one flange up and one down, got ${heights}`);
  assert.ok(Math.abs(Math.abs(heights[0]) - Math.abs(heights[1])) < 1e-6, "by the same amount");
});

test("crossing bend lines say they cross, rather than blaming a length", () => {
  // The two failures wear the same symptom -- no single face holds the fold -- and "stops N mm
  // short" about a fold that is already too long sends the reader the wrong way.
  const plate = [[0, 0], [120, 0], [120, 60], [0, 60]];
  assert.throws(
    () => decomposeFoldRegions(plate, [
      fold([60, 0], [60, 60], 90),
      fold([0, 20], [120, 20], 90)
    ]),
    (error) => {
      assert.match(error.message, /cannot fold crossing bend lines/u);
      assert.match(error.message, /bend 2 crosses bend 1/u);
      assert.doesNotMatch(error.message, /mm short/u);
      return true;
    }
  );
});

test("folds that meet end to end are not crossing", () => {
  // An L blank folded on both arms: the lines touch the same corner region but neither crosses
  // the other, so this must keep working.
  const lBlank = [[0, 0], [100, 0], [100, 30], [30, 30], [30, 80], [0, 80]];
  const { regions } = decomposeFoldRegions(lBlank, [
    fold([60, 0], [60, 30], 90),
    fold([0, 55], [30, 55], 90)
  ]);
  assert.equal(regions.length, 3);
});

test("a tab folded about the panel's own edge keeps the panel's edge", () => {
  // The fold line runs along the bottom edge, spanning only the tab: both its ends are existing
  // VERTICES sitting exactly on the line. Cutting by a band edge finds no crossing there and
  // falls back to the infinite line, which took the panel's whole bottom edge with the tab.
  const blank = [[0, 0], [70, 0], [70, -22], [110, -22], [110, 0], [180, 0], [180, 90], [0, 90]];
  const line = fold([70, 0], [110, 0], 90);
  const { regions, adjacency } = decomposeFoldRegions(blank, [line]);
  assert.equal(regions.length, 2);
  assert.equal(adjacency.length, 1);
  const [tab, panel] = regions[0].area < regions[1].area ? regions : [regions[1], regions[0]];
  // The tab is the material below the band, the full 40 wide.
  assert.ok(tab.outerLoop.every(([, y]) => y <= -line.halfWidth + 1e-6));
  // The panel keeps its corners out at x = 0 and x = 180 on y = 0: the band only bit into the
  // 40 mm the fold spans, leaving a notch, not a full-width step.
  assert.ok(panel.outerLoop.some(([x, y]) => Math.abs(x) < 1e-6 && Math.abs(y) < 1e-6));
  assert.ok(panel.outerLoop.some(([x, y]) => Math.abs(x - 180) < 1e-6 && Math.abs(y) < 1e-6));
  const notchDepth = Math.max(...panel.outerLoop.filter(([x]) => x > 69 && x < 111).map(([, y]) => y));
  assert.ok(Math.abs(notchDepth - line.halfWidth) < 1e-6, `notch is the band's half, got ${notchDepth}`);
});

test("a fold hinges the faces it separates, whatever other folds' lines run past them", () => {
  // tom's link_bracket, reduced to the three faces that matter: a body that reaches both sides of
  // the wrap bend's line, the wrap flange, and a foot at the bottom whose centroid sits RIGHT of
  // that line while the body's sits left. Only a LOCAL fold can set this up -- a fold that spans
  // the whole blank leaves each face wholly on its own side -- so it is built here rather than
  // decomposed. A rule that hinges the pair "differing in exactly one fold's side" then refuses
  // the foot, which came out a second root: flat, with its own bend band already taken out.
  const wrap = fold([16.8, 117], [16.8, 145], 90);
  const foot = fold([0, 10], [35, 10], 90);
  const folds = [wrap, foot];
  const region = (loop) => {
    const centroid = [
      loop.reduce((sum, [x]) => sum + x, 0) / loop.length,
      loop.reduce((sum, [, y]) => sum + y, 0) / loop.length
    ];
    return {
      outerLoop: loop,
      centroid,
      sides: folds.map((foldLine, foldIndex) => ({
        foldIndex,
        side: foldSignedDistance(foldLine, centroid) >= 0 ? 1 : -1
      }))
    };
  };
  const body = region([
    [-17, 10 + foot.halfWidth], [35, 10 + foot.halfWidth], [35, 117],
    [16.8 - wrap.halfWidth, 117], [16.8 - wrap.halfWidth, 145], [-17, 145]
  ]);
  const flange = region([
    [16.8 + wrap.halfWidth, 117], [27, 117], [27, 145], [16.8 + wrap.halfWidth, 145]
  ]);
  const footFace = region([
    [0, 10 - foot.halfWidth], [35, 10 - foot.halfWidth], [35, -9], [0, -9]
  ]);
  // The setup: body and foot are on opposite sides of BOTH folds, though only one hinges them.
  assert.notEqual(body.sides[0].side, footFace.sides[0].side, "straddling the wrap bend's line");
  assert.notEqual(body.sides[1].side, footFace.sides[1].side, "and hinged by the foot bend");
  const adjacency = buildFoldAdjacency([body, flange, footFace], folds);
  assert.equal(adjacency.length, 2, `one hinge per fold, got ${JSON.stringify(adjacency)}`);
  assert.deepEqual(adjacency.map((edge) => edge.foldIndex), [0, 1]);
  assert.deepEqual(adjacency.map((edge) => edge.regions), [[0, 1], [0, 2]]);
});

test("four folds in three orientations fold a panel into five faces", () => {
  // The multi_bend_test_panel fixture: two parallel verticals, a tab chord perpendicular to
  // them, and a 45-degree corner. Four folds, five faces, four hinges, and a tree.
  const blank = [[0, 0], [70, 0], [70, -22], [110, -22], [110, 0], [180, 0], [180, 56], [146, 90], [0, 90]];
  const folds = [
    fold([45, 0], [45, 90], 90),
    fold([70, 0], [110, 0], 90),
    fold([120, 0], [120, 90], 90),
    fold([180, 35], [125, 90], 90)
  ];
  const { regions, adjacency } = decomposeFoldRegions(blank, folds);
  assert.equal(regions.length, 5);
  assert.equal(adjacency.length, 4);
  const { placements, parents } = buildRegionPlacements(regions, folds, adjacency);
  assert.equal(parents.filter((parent) => !parent).length, 1, "one root");
  // Rigid: the folds move faces without stretching them.
  regions.forEach((region, index) => {
    const [a, b] = [region.outerLoop[0], region.outerLoop[1]];
    const flat = Math.hypot(a[0] - b[0], a[1] - b[1]);
    const placedA = place(placements[index], a);
    const placedB = place(placements[index], b);
    const folded = Math.hypot(placedA[0] - placedB[0], placedA[1] - placedB[1], placedA[2] - placedB[2]);
    assert.ok(Math.abs(folded - flat) < 1e-6, `face ${index} stretched ${flat} -> ${folded}`);
  });
  // Every face except the anchor leaves the sheet.
  const lifted = placements.map((matrix, index) => place(matrix, regions[index].centroid)[1]);
  assert.equal(lifted.filter((height) => Math.abs(height) < 1e-6).length, 1);
});

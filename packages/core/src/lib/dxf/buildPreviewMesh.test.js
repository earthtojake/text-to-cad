import assert from "node:assert/strict";
import test from "node:test";

import { buildDxfPreviewMeshData, computeDxfFlatStats, extractDxfScorePolylines } from "./buildPreviewMesh.js";
import { parseDxf } from "./parseDxf.js";

function dxfText(lines) {
  return `${lines.join("\n")}\n`;
}

function line(start, end) {
  return {
    kind: "cut",
    start,
    end
  };
}

function rectangle(minX, minY, maxX, maxY) {
  return [
    line([minX, minY], [maxX, minY]),
    line([maxX, minY], [maxX, maxY]),
    line([maxX, maxY], [minX, maxY]),
    line([minX, maxY], [minX, minY])
  ];
}

test("DXF preview extrudes multiple disconnected no-bend flat contours", () => {
  const dxfData = {
    geometry: {
      lines: [
        ...rectangle(0, 0, 10, 10),
        ...rectangle(5, 20, 15, 30)
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };

  const meshData = buildDxfPreviewMeshData(dxfData, 2);

  assert.equal(meshData.triangle_count > 0, true);
  assert.equal(meshData.guide_line_segments.length, 0);
  assert.deepEqual(meshData.bounds.min, [0, -1, 0]);
  assert.deepEqual(meshData.bounds.max, [15, 1, 30]);
});

test("bend guides can hover over either face", () => {
  // The guides are one-sided. A consumer whose axis mapping turns this mesher's +Y into
  // its own "down" (the CAD viewer) asks for guideElevationSign -1 so the dotted bend
  // lines sit on the face the user sees, not under the sheet.
  const dxfData = {
    geometry: {
      lines: [
        ...rectangle(0, 0, 60, 30),
        { kind: "bend", start: [30, 0], end: [30, 30] }
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };

  const above = buildDxfPreviewMeshData(dxfData, 2);
  const below = buildDxfPreviewMeshData(dxfData, 2, null, { guideElevationSign: -1 });

  assert.equal(above.guide_line_segments.length, 6);
  assert.equal(above.guide_line_segments[1] > 1, true, "default guide floats over +Y");
  assert.equal(below.guide_line_segments[1] < -1, true, "flipped guide floats over -Y");
  assert.equal(above.guide_line_segments[1], -below.guide_line_segments[1]);
});

test("open cut chains and engrave geometry become score polylines, not solids", () => {
  const dxfData = {
    geometry: {
      lines: [
        ...rectangle(0, 0, 60, 30),
        // An open V on the cut layer: two joined segments that never close.
        { kind: "cut", start: [10, 25], end: [15, 20] },
        { kind: "cut", start: [15, 20], end: [20, 25] },
        // A stroke on an engrave layer.
        { kind: "engrave", start: [30, 10], end: [50, 10] }
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };

  const meshData = buildDxfPreviewMeshData(dxfData, 2);
  assert.deepEqual(meshData.bounds.min, [0, -1, 0], "the open V does not distort the solid");

  const scores = extractDxfScorePolylines(dxfData);
  assert.equal(scores.length, 2, "one engrave stroke, one open chain");
  const openChain = scores.find((polyline) => polyline.length === 3);
  assert.ok(openChain, "the V survives as a single three-point chain");
});

test("bend radius and K-factor reshape the curved bend band", () => {
  const dxfData = {
    geometry: {
      lines: [
        ...rectangle(0, 0, 60, 30),
        { kind: "bend", start: [30, 0], end: [30, 30] }
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };
  const bends = [{ angleDeg: 90, direction: "up" }];

  const stock = buildDxfPreviewMeshData(dxfData, 2, bends);
  const wide = buildDxfPreviewMeshData(dxfData, 2, bends, { bendInsideRadiusMm: 8 });
  // A larger inside radius sweeps a larger arc, so the folded part stands taller.
  assert.ok(
    wide.bounds.max[1] > stock.bounds.max[1] + 1,
    `radius 8 should rise above the default (${wide.bounds.max[1]} vs ${stock.bounds.max[1]})`
  );

  const lowK = buildDxfPreviewMeshData(dxfData, 2, bends, { bendInsideRadiusMm: 8, bendKFactor: 0.1 });
  assert.ok(
    Math.abs(lowK.bounds.max[1] - wide.bounds.max[1]) > 1e-6,
    "moving the neutral axis changes the fold"
  );
});

test("DXF preview extrudes bulged lwpolyline contours", () => {
  const quarterBulge = Math.tan(Math.PI / 8);
  const dxfData = parseDxf(dxfText([
    "0", "SECTION",
    "2", "ENTITIES",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "4",
    "70", "1",
    "10", "0",
    "20", "0",
    "10", "10",
    "20", "0",
    "10", "10",
    "20", "10",
    "10", "0",
    "20", "10",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "4",
    "70", "1",
    "10", "7",
    "20", "5",
    "42", String(quarterBulge),
    "10", "5",
    "20", "7",
    "42", String(quarterBulge),
    "10", "3",
    "20", "5",
    "42", String(quarterBulge),
    "10", "5",
    "20", "3",
    "42", String(quarterBulge),
    "0", "ENDSEC",
    "0", "EOF"
  ]));

  const meshData = buildDxfPreviewMeshData(dxfData, 2);

  assert.equal(meshData.triangle_count > 0, true);
  assert.equal(meshData.guide_line_segments.length, 0);
  assert.deepEqual(meshData.bounds.min, [0, -1, 0]);
  assert.deepEqual(meshData.bounds.max, [10, 1, 10]);
});

test("flat stats report net area and bounding size", () => {
  const dxfData = {
    geometry: {
      lines: [...rectangle(0, 0, 100, 50)],
      arcs: [],
      circles: [
        { kind: "cut", center: [20, 25], radius: 10 }
      ]
    },
    defaultThicknessMm: 2
  };
  const stats = computeDxfFlatStats(dxfData);
  assert.equal(stats.widthMm, 100);
  assert.equal(stats.heightMm, 50);
  const expected = 100 * 50 - Math.PI * 10 * 10;
  // Tolerance covers the circle's polygonal sampling (the hole is a sampled polygon).
  assert.ok(Math.abs(stats.areaMm2 - expected) < 12, `net area ~${expected}, got ${stats.areaMm2}`);
});

// A flat pattern whose bend lines are inert crease marks must not be judged by the
// X-slab strip decomposition. That decomposition collapses each bend to the midpoint X
// of its endpoints, so a bend that is not vertical, or not full-length, became a phantom
// full-height boundary in the middle of the part -- and any hole straddling that phantom X
// was rejected as "crossing bend lines" from tens of millimetres away. The orientation
// guard missed it because it returns early at angle 0, which is the default: a crease mark
// skipped the guard and then drove the orientation-sensitive decomposition anyway.
function creasedPlate(bendStart, bendEnd, holeRect) {
  return {
    geometry: {
      lines: [
        ...rectangle(0, 0, 100, 60),
        { kind: "bend", start: bendStart, end: bendEnd },
        ...rectangle(...holeRect)
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };
}

const FOLDING = [{ direction: "up", angleDeg: 90 }];

test("a horizontal crease mark does not reject a hole tens of mm away from it", () => {
  // The reported false positive: bend along y=5, hole 25 mm above it, straddling the
  // midpoint x=50 that the bend collapses to.
  const dxfData = creasedPlate([10, 5], [90, 5], [40, 30, 60, 45]);
  const meshData = buildDxfPreviewMeshData(dxfData, 2);
  assert.ok(meshData.triangle_count > 0, "the flat pattern must still build");
  assert.equal(meshData.guide_line_segments.length, 6, "the crease mark must still draw");
});

test("moving that hole clear of the phantom boundary changed nothing before, and still does not", () => {
  // A and B in the report differ only in the hole's X. Both must build: the geometry is
  // identical in every way that matters, so the outcome must not depend on the slab math.
  const straddling = creasedPlate([10, 5], [90, 5], [40, 30, 60, 45]);
  const clear = creasedPlate([10, 5], [90, 5], [65, 30, 85, 45]);
  assert.ok(buildDxfPreviewMeshData(straddling, 2).triangle_count > 0);
  assert.ok(buildDxfPreviewMeshData(clear, 2).triangle_count > 0);
});

test("a partial-length vertical crease mark does not reject a hole either", () => {
  // The real-world shape: bend lines that are perpendicular to each other and both
  // partial-length, silently extended to full height by the decomposition.
  const dxfData = creasedPlate([50, 20], [50, 40], [40, 45, 60, 55]);
  assert.ok(buildDxfPreviewMeshData(dxfData, 2).triangle_count > 0);
});

test("a hole genuinely crossing an ACTIVE bend is still rejected", () => {
  const dxfData = creasedPlate([50, 0], [50, 60], [40, 30, 60, 45]);
  assert.throws(
    () => buildDxfPreviewMeshData(dxfData, 2, FOLDING),
    /holes crossing bend/,
    "folding a sheet through a hole is still unsupported"
  );
});

test("an ACTIVE bend clear of every hole still folds", () => {
  const dxfData = creasedPlate([50, 0], [50, 60], [65, 30, 85, 45]);
  const meshData = buildDxfPreviewMeshData(dxfData, 2, FOLDING);
  assert.ok(meshData.triangle_count > 0);
});

test("an ACTIVE bend that stops short of both edges says so, not a false hole claim", () => {
  // Was "requires vertical bend lines": a horizontal fold is fine now, but this one spans
  // x 10..90 of a 100 wide blank, so it still separates nothing. Either way the answer is about
  // the bend, never about whichever hole happened to straddle a collapsed midpoint.
  const dxfData = creasedPlate([10, 5], [90, 5], [40, 30, 60, 45]);
  assert.throws(
    () => buildDxfPreviewMeshData(dxfData, 2, FOLDING),
    (error) => {
      assert.match(error.message, /runs edge to edge/u);
      assert.match(error.message, /5\.000 mm short/u);
      assert.doesNotMatch(error.message, /hole/u);
      return true;
    }
  );
});

test("the baked artifact preview never folds, so it never reaches the strip decomposition", () => {
  // buildDxfPreviewGlb bakes with null bend settings and DEFAULT_DXF_BEND_ANGLE_DEG is 0.
  // Folding is a render-time parameter the viewer applies live. This is why the CLI could
  // not have been rescued by catching the preview error and retrying flat: flat is already
  // the only path it takes.
  const dxfData = creasedPlate([50, 0], [50, 60], [40, 30, 60, 45]);
  assert.ok(buildDxfPreviewMeshData(dxfData, 2, null).triangle_count > 0);
  assert.throws(() => buildDxfPreviewMeshData(dxfData, 2, FOLDING), /holes crossing bend/);
});


// -- a fold line has to run edge to edge -------------------------------------------------

function bentPlate(bends, { width = 100, height = 60, holeRect = null } = {}) {
  return {
    geometry: {
      lines: [
        ...rectangle(0, 0, width, height),
        ...bends.map((bend) => ({ kind: "bend", start: [bend.x, bend.y0], end: [bend.x, bend.y1] })),
        ...(holeRect ? rectangle(...holeRect) : [])
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };
}

const UP_90 = { direction: "up", angleDeg: 90 };

test("a bend line that stops short of the edge is refused, not folded anyway", () => {
  // The reported failure: with several bends the preview came out twisted into spikes, because
  // a fold line spanning the top third still hinged the whole face behind it. A fold has to cut
  // a face in two to be a hinge at all.
  const dxfData = bentPlate([{ x: 60, y0: 40, y1: 60 }]);
  assert.throws(
    () => buildDxfPreviewMeshData(dxfData, 2, [UP_90]),
    (error) => {
      assert.match(error.message, /runs edge to edge/u);
      assert.match(error.message, /bend 1/u, "the message must name the offending bend");
      assert.match(error.message, /20\.000 mm short/u, "and say how far short it stops");
      return true;
    }
  );
});

test("the offending bend is named even when an earlier bend is fine", () => {
  const dxfData = bentPlate([{ x: 40, y0: 0, y1: 60 }, { x: 80, y0: 30, y1: 60 }]);
  assert.throws(
    () => buildDxfPreviewMeshData(dxfData, 2, [UP_90, UP_90]),
    /bend 2, from \(80\.000, 30\.000\) to \(80\.000, 60\.000\)/u
  );
});

test("full-span bends still fold, one or several", () => {
  for (const bends of [
    [{ x: 50, y0: 0, y1: 60 }],
    [{ x: 30, y0: 0, y1: 60 }, { x: 70, y0: 0, y1: 60 }],
    [{ x: 25, y0: 0, y1: 60 }, { x: 50, y0: 0, y1: 60 }, { x: 75, y0: 0, y1: 60 }]
  ]) {
    const meshData = buildDxfPreviewMeshData(
      bentPlate(bends),
      2,
      bends.map(() => UP_90)
    );
    assert.ok(meshData.triangle_count > 0, `${bends.length} bend(s) must fold`);
  }
});

test("span is measured on the OUTER contour, so a cutout elsewhere is irrelevant", () => {
  // The span rule asks whether the line reaches both outer edges. A cutout that does not
  // touch the line must not enter into it -- measuring material run by run would reject this.
  const dxfData = bentPlate([{ x: 50, y0: 0, y1: 60 }], { holeRect: [20, 20, 40, 40] });
  const meshData = buildDxfPreviewMeshData(dxfData, 2, [UP_90]);
  assert.ok(meshData.triangle_count > 0);
});

test("a hole ON the fold line is still refused, by the bend-band rule", () => {
  // Two distinct rules, and this one is not the span rule: material inside the bend radius
  // cannot be folded whatever the line's length, so the band message is the right one.
  const dxfData = bentPlate([{ x: 50, y0: 0, y1: 60 }], { holeRect: [45, 20, 55, 40] });
  assert.throws(
    () => buildDxfPreviewMeshData(dxfData, 2, [UP_90]),
    /holes crossing bend radius bands/u
  );
});

test("a fold line a few hundredths short is authoring noise, not a short bend", () => {
  const dxfData = bentPlate([{ x: 50, y0: 0.02, y1: 59.98 }]);
  const meshData = buildDxfPreviewMeshData(dxfData, 2, [UP_90]);
  assert.ok(meshData.triangle_count > 0);
});

test("a partial bend left at 0 degrees is still just a crease mark", () => {
  // The edge-to-edge rule is about FOLDING. A short bend line nobody folds keeps drawing as a
  // guide over the flat plate, as it did before.
  const dxfData = bentPlate([{ x: 60, y0: 40, y1: 60 }]);
  const meshData = buildDxfPreviewMeshData(dxfData, 2, [{ direction: "up", angleDeg: 0 }]);
  assert.ok(meshData.triangle_count > 0);
  assert.equal(meshData.guide_line_segments.length, 6);
});

test("a bend at any angle folds: orientation is no longer a restriction", () => {
  // The X-slab decomposition could only represent bends parallel to Y. Faces are split along
  // each fold's own segment now, so a horizontal or diagonal fold is just a fold.
  const horizontal = {
    geometry: {
      lines: [...rectangle(0, 0, 100, 60), { kind: "bend", start: [0, 30], end: [100, 30] }],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };
  assert.ok(buildDxfPreviewMeshData(horizontal, 2, [UP_90]).triangle_count > 0, "horizontal fold");

  const diagonal = {
    geometry: {
      lines: [...rectangle(0, 0, 60, 60), { kind: "bend", start: [0, 0], end: [60, 60] }],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };
  assert.ok(buildDxfPreviewMeshData(diagonal, 2, [UP_90]).triangle_count > 0, "diagonal fold");
});

test("two folds at right angles on an L blank both fold", () => {
  // One fold per arm. The slab model cut every bend across the whole blank, so the second arm's
  // fold sliced through the first arm as well.
  const lBlank = {
    geometry: {
      lines: [
        { kind: "cut", start: [0, 0], end: [100, 0] },
        { kind: "cut", start: [100, 0], end: [100, 30] },
        { kind: "cut", start: [100, 30], end: [30, 30] },
        { kind: "cut", start: [30, 30], end: [30, 80] },
        { kind: "cut", start: [30, 80], end: [0, 80] },
        { kind: "cut", start: [0, 80], end: [0, 0] },
        { kind: "bend", start: [60, 0], end: [60, 30] },
        { kind: "bend", start: [0, 55], end: [30, 55] }
      ],
      arcs: [],
      circles: []
    },
    defaultThicknessMm: 2
  };
  const meshData = buildDxfPreviewMeshData(lBlank, 2, [UP_90, UP_90]);
  assert.ok(meshData.triangle_count > 0);
  assert.equal(meshData.guide_line_segments.length, 12, "both bends still draw a guide");
});

test("every bend guide rides on its own crease, not on an unrelated face", () => {
  // The multi_bend_test_panel shape: four folds, five faces. The guide for a fold belongs to the
  // face the fold HINGES; picking any face that merely sits on the fold's negative side left two
  // of the four dashes floating off the part, drawn with the matrix of a face that has nothing to
  // do with that bend.
  const geometry = {
    geometry: {
      lines: [
        ...[
          [[0, 0], [70, 0]], [[70, 0], [70, -22]], [[70, -22], [110, -22]], [[110, -22], [110, 0]],
          [[110, 0], [180, 0]], [[180, 0], [180, 56]], [[180, 56], [146, 90]], [[146, 90], [0, 90]],
          [[0, 90], [0, 0]]
        ].map(([start, end]) => ({ kind: "cut", start, end })),
        ...[
          [[45, 0], [45, 90]], [[70, 0], [110, 0]], [[120, 0], [120, 90]], [[180, 35], [125, 90]]
        ].map(([start, end]) => ({ kind: "bend", start, end }))
      ],
      circles: []
    }
  };
  const settings = [1, 2, 3, 4].map(() => ({ direction: "up", angleDeg: 90 }));
  const mesh = buildDxfPreviewMeshData(geometry, 2, settings);
  const guides = mesh.guide_line_segments;
  assert.equal(guides.length, 4 * 6, "one segment per bend");
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < mesh.vertices.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], mesh.vertices[index + axis]);
      max[axis] = Math.max(max[axis], mesh.vertices[index + axis]);
    }
  }
  // A guide sitting on its crease is inside the folded part's extent; a stranded one is not. The
  // slack is the elevation that floats the dashes clear of the surface.
  const slack = 1.5;
  for (let index = 0; index < guides.length; index += 3) {
    for (const axis of [0, 1, 2]) {
      const value = guides[index + axis];
      assert.ok(
        value >= min[axis] - slack && value <= max[axis] + slack,
        `guide point ${index / 3} axis ${axis} at ${value.toFixed(1)} is outside `
        + `[${min[axis].toFixed(1)}, ${max[axis].toFixed(1)}]`
      );
    }
  }
  // And each guide keeps its bend line's length: it is the same crease, moved rigidly.
  for (let index = 0; index < guides.length; index += 6) {
    const length = Math.hypot(
      guides[index + 3] - guides[index],
      guides[index + 4] - guides[index + 1],
      guides[index + 5] - guides[index + 2]
    );
    const expected = [90, 40, 90, Math.hypot(55, 55)][index / 6];
    assert.ok(Math.abs(length - expected) < 1e-4, `guide ${index / 6} length ${length} != ${expected}`);
  }
});

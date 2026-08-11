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

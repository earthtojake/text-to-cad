import assert from "node:assert/strict";
import test from "node:test";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";

import { screenLimitedPickThreshold, worldUnitsPerPixelAtDistance } from "@hardcore/core/lib/viewer/pickingThresholds.js";
import {
  classifyMeasurePick,
  measurementFromPicks
} from "@hardcore/core/lib/viewer/measurement.js";
import {
  measureHitPointFromWorldIntersection,
  measureModelOffsetFromRuntime,
  measureModelPointToWorld,
  measurePickForPosition,
  resolveViewerReferencePick,
  measureWorldPointToModel
} from "./useStepPicking.js";
import { partIdFromIntersection, shouldRaycastRecordForPick } from "./partPicking.js";

test("disabled picking never prepares surface intersections or resolves references", () => {
  const unexpected = () => assert.fail("disabled picking must not raycast or resolve a reference");
  for (const pickMode of Object.values(VIEWER_PICK_MODE)) {
    for (const hover of [false, true]) {
      assert.equal(resolveViewerReferencePick({
        pickMode, hover, suppressTopologyPicking: true,
        intersectModel: unexpected, pickTopology: unexpected, pickPart: unexpected
      }), null);
    }
  }
  // NONE also disables the picker without a separate Render/playback flag, for a press and a
  // hover alike.
  for (const hover of [false, true]) {
    assert.equal(resolveViewerReferencePick({
      pickMode: VIEWER_PICK_MODE.NONE, hover,
      intersectModel: unexpected, pickTopology: unexpected, pickPart: unexpected
    }), null);
  }
});

test("Inspect resolves parts, topology, and Measure from one surface intersection pass", () => {
  // The resolver the pointer hook runs for every press, release and hover (`pickReferenceAtPosition`).
  const intersections = [{ distance: 4, faceIndex: 3 }];
  for (const [pickMode, hover, topologyReference, expected, expectedCalls] of [
    [VIEWER_PICK_MODE.PARTS, false, "face:3", "part:1", ["surface", "part"]],
    [VIEWER_PICK_MODE.ASSEMBLY, false, "face:3", "part:1", ["surface", "part"]],
    [VIEWER_PICK_MODE.AUTO, false, "face:3", "face:3", ["surface", "topology"]],
    [VIEWER_PICK_MODE.AUTO, false, null, "part:1", ["surface", "topology", "part"]],
    [VIEWER_PICK_MODE.MEASURE, false, "face:3", "face:3", ["surface", "topology"]],
    [VIEWER_PICK_MODE.MEASURE, true, null, null, ["surface", "topology"]],
    [VIEWER_PICK_MODE.TOPOLOGY, false, "face:3", "face:3", ["surface", "topology"]],
    // A face or edge filter: a press on no topology picks nothing, a hover there lights the part.
    [VIEWER_PICK_MODE.TOPOLOGY, false, null, null, ["surface", "topology"]],
    [VIEWER_PICK_MODE.TOPOLOGY, true, null, "part:1", ["surface", "topology", "part"]]
  ]) {
    const calls = [];
    const result = resolveViewerReferencePick({
      pickMode,
      hover,
      intersectModel: () => { calls.push("surface"); return intersections; },
      pickTopology: (hits) => { assert.equal(hits, intersections); calls.push("topology"); return topologyReference; },
      pickPart: (hits) => { assert.equal(hits, intersections); calls.push("part"); return "part:1"; }
    });
    assert.equal(result, expected, `${pickMode} hover=${hover}`);
    assert.deepEqual(calls, expectedCalls, `${pickMode} hover=${hover}`);
  }
});

test("worldUnitsPerPixelAtDistance converts perspective depth to screen scale", () => {
  const camera = {
    isPerspectiveCamera: true,
    fov: 60
  };
  const unitsPerPixel = worldUnitsPerPixelAtDistance(camera, 600, 300);
  assert.ok(Number.isFinite(unitsPerPixel));
  assert.ok(Math.abs(unitsPerPixel - 0.5773502691896257) < 1e-9);
});

test("screenLimitedPickThreshold preserves the base threshold until zoom would make it too wide on screen", () => {
  const camera = {
    isPerspectiveCamera: true,
    fov: 60
  };
  const farThreshold = screenLimitedPickThreshold({
    baseThreshold: 1.5,
    thresholdScale: 1,
    maxScreenDistancePx: 10,
    camera,
    viewportHeightPx: 600,
    distance: 300
  });
  const nearThreshold = screenLimitedPickThreshold({
    baseThreshold: 1.5,
    thresholdScale: 1,
    maxScreenDistancePx: 10,
    camera,
    viewportHeightPx: 600,
    distance: 30
  });

  assert.equal(farThreshold, 1.5);
  assert.ok(nearThreshold < farThreshold);
  assert.ok(Math.abs(nearThreshold - 0.5773502691896257) < 1e-9);
});

test("screenLimitedPickThreshold falls back to the scaled base threshold when screen scaling is unavailable", () => {
  const threshold = screenLimitedPickThreshold({
    baseThreshold: 0.9,
    thresholdScale: 0.5,
    maxScreenDistancePx: 5,
    camera: null,
    viewportHeightPx: 600,
    distance: 30
  });
  assert.equal(threshold, 0.45);
});

test("measure hit point stays in world space and never converts through the mesh local frame", () => {
  const intersection = {
    point: { x: 3.25, y: -4.5, z: 10.75 },
    object: {
      worldToLocal() {
        throw new Error("worldToLocal must not be called for measure hits");
      }
    }
  };
  assert.deepEqual(measureHitPointFromWorldIntersection(intersection), [3.25, -4.5, 10.75]);
  assert.equal(measureHitPointFromWorldIntersection({ point: { x: NaN, y: 0, z: 0 } }), null);
  assert.equal(measureHitPointFromWorldIntersection({}), null);
  assert.equal(measureHitPointFromWorldIntersection(null), null);
});

test("measure picks snap onto transformed world-space references with world-space hits", () => {
  const worldEdge = [[0, 0, 0], [4, 0, 0]].flatMap(([x, y, z]) => [-y + 10, x + 20, z - 5]);
  const reference = { id: "topology|1|edge|2", selectorType: "edge", pickData: { selectorType: "edge" } };
  const pick = measurePickForPosition({
    reference,
    worldHitPoint: [10, 22, -5],
    referenceId: "topology|1|edge|2",
    bypassTopology: false,
    edgeSegments: worldEdge
  });
  assert.deepEqual(pick, {
    referenceId: "topology|1|edge|2",
    reference,
    snapKind: "edge",
    point: [10, 22, -5],
    geometry: { kind: "line", direction: [0, 1, 0] }
  });
});

test("measure picks snap in the model frame and report the point back in world space", () => {
  // Selector geometry sits at the model origin while the viewer draws the model
  // re-centred. Snapping without reconciling the two lands the measurement a
  // whole offset away from the surface the user clicked.
  const modelOffset = [0, 0, -10];
  const edgeAtModelTop = [0, 0, 20, 40, 0, 20];
  const pick = measurePickForPosition({
    reference: { id: "e1", selectorType: "edge", pickData: { selectorType: "edge" } },
    worldHitPoint: [12, 3, 10],
    referenceId: "e1",
    edgeSegments: edgeAtModelTop,
    modelOffset
  });
  assert.equal(pick.snapKind, "edge");
  assert.deepEqual(pick.point, [12, 0, 10]);
});

test("measureModelOffsetFromRuntime reads the offset applied to the pick groups", () => {
  assert.deepEqual(measureModelOffsetFromRuntime(null), [0, 0, 0]);
  assert.deepEqual(measureModelOffsetFromRuntime({}), [0, 0, 0]);
  assert.deepEqual(
    measureModelOffsetFromRuntime({ facePickGroup: { position: { x: 1, y: -2, z: 3 } } }),
    [1, -2, 3]
  );
  assert.deepEqual(
    measureModelOffsetFromRuntime({ modelGroup: { position: { x: 0, y: 0, z: -10 } } }),
    [0, 0, -10]
  );
  assert.deepEqual(
    measureModelOffsetFromRuntime({ facePickGroup: { position: { x: NaN, y: 1, z: 2 } } }),
    [0, 1, 2]
  );
});

test("measure frame conversions round-trip", () => {
  const offset = [1, -2, 3];
  assert.deepEqual(measureModelPointToWorld(measureWorldPointToModel([10, 10, 10], offset), offset), [10, 10, 10]);
  assert.equal(measureWorldPointToModel(null, offset), null);
  assert.equal(measureModelPointToWorld([0, 0], offset), null);
});

test("shift bypasses topology and classifies the tap as a free point", () => {
  const reference = {
    id: "topology|1|face|3",
    selectorType: "face",
    pickData: { selectorType: "face", surfaceType: "plane", normal: [0, 0, 1] }
  };
  const pick = measurePickForPosition({
    reference,
    worldHitPoint: [1, 2, 3],
    referenceId: "topology|1|face|3",
    bypassTopology: true
  });
  assert.deepEqual(pick, {
    referenceId: "",
    reference: null,
    snapKind: "free",
    point: [1, 2, 3],
    geometry: null
  });
});

test("measure taps without a reference classify the surface point as free", () => {
  const pick = measurePickForPosition({
    reference: null,
    worldHitPoint: [0.5, 2, -2.25],
    referenceId: "",
    bypassTopology: false
  });
  assert.deepEqual(pick, {
    referenceId: "",
    reference: null,
    snapKind: "free",
    point: [0.5, 2, -2.25],
    geometry: null
  });
  assert.equal(measurePickForPosition({ reference: null, worldHitPoint: null }), null);
});

test("measure clicks on empty space produce no pick", () => {
  const emptyHit = measurePickForPosition({
    reference: null,
    worldHitPoint: null,
    referenceId: "",
    bypassTopology: false
  });
  assert.equal(emptyHit, null);
  assert.equal(
    measurePickForPosition({
      reference: null,
      worldHitPoint: null,
      referenceId: "",
      bypassTopology: true
    }),
    null
  );
});

test("measure tap payload keeps the resolved reference for face-to-face distance", () => {
  const facePick = (id, normal, point) => measurePickForPosition({
    reference: { id, selectorType: "face", pickData: { selectorType: "face", surfaceType: "plane", normal } },
    worldHitPoint: point,
    referenceId: id
  });
  // Two DISTINCT parallel faces. Reusing one reference for both picks would be
  // two points on a single face, which has no perpendicular distance.
  const pickA = facePick("topology|1|face|3", [0, 0, 1], [0, 0, 2]);
  const pickB = facePick("topology|1|face|9", [0, 0, -1], [0, 0, 7]);
  assert.equal(pickA.snapKind, "face");
  assert.equal(pickA.reference.id, "topology|1|face|3");

  const measurement = measurementFromPicks(pickA, pickB);
  assert.equal(measurement.perpendicular, 5);
  assert.equal(measurement.euclidean, 5);
});


test("partIdFromIntersection reads a per-occurrence mesh's partId", () => {
  const hit = { object: { userData: { partId: "o1.5" } } };
  assert.equal(partIdFromIntersection(hit), "o1.5");
});

test("partIdFromIntersection returns the mesh's userData.partId, else null", () => {
  assert.equal(partIdFromIntersection({ object: { userData: { partId: "o1.2" } } }), "o1.2");
  assert.equal(partIdFromIntersection({ object: { userData: {} } }), null);
  assert.equal(partIdFromIntersection({}), null);
});

test("partIdFromIntersection resolves a stable occurrence id from an instanced hit", () => {
  const hit = { instanceId: 1, object: { userData: { partIds: ["o1.2", "o1.5"] } } };
  assert.equal(partIdFromIntersection(hit), "o1.5");
});

test("shouldRaycastRecordForPick applies bucket-level focus/hidden to per-mesh records", () => {
  const focusIds = new Set(["o1.5"]);
  // in focus -> kept; out of focus -> dropped
  assert.equal(shouldRaycastRecordForPick({ mesh: { visible: true }, partId: "o1.5" }, { focusIds, hiddenIds: new Set() }), true);
  assert.equal(shouldRaycastRecordForPick({ mesh: { visible: true }, partId: "o1.9" }, { focusIds, hiddenIds: new Set() }), false);
  // hidden -> dropped even with no focus
  assert.equal(
    shouldRaycastRecordForPick({ mesh: { visible: true }, partId: "o1.5" }, { focusIds: new Set(), hiddenIds: new Set(["o1.5"]) }),
    false
  );
  // invisible -> dropped
  assert.equal(shouldRaycastRecordForPick({ mesh: { visible: false }, partId: "o1.5" }, { focusIds: new Set(), hiddenIds: new Set() }), false);
})

test("a fitted arc centre comes back out of the model frame with the point", () => {
  // Radius survives a translation untouched; the centre is a position and does not.
  const arc = [];
  for (let index = 0; index < 32; index += 1) {
    const a = (2 * Math.PI * index) / 32;
    const b = (2 * Math.PI * (index + 1)) / 32;
    arc.push(35 + (4 * Math.cos(a)), 20 + (4 * Math.sin(a)), 20);
    arc.push(35 + (4 * Math.cos(b)), 20 + (4 * Math.sin(b)), 20);
  }
  const pick = measurePickForPosition({
    reference: { id: "e1", selectorType: "edge", pickData: { selectorType: "edge" } },
    worldHitPoint: [39, 20, 10],
    referenceId: "e1",
    edgeSegments: arc,
    modelOffset: [0, 0, -10]
  });
  assert.equal(pick.geometry.kind, "arc");
  assert.ok(Math.abs(pick.geometry.radius - 4) < 1e-6);
  assert.ok(Math.abs(pick.geometry.center[2] - 10) < 1e-6);
  assert.ok(Math.abs(pick.point[2] - 10) < 1e-6);
});

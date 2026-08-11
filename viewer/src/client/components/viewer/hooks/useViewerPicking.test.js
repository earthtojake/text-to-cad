import assert from "node:assert/strict";
import test from "node:test";

import { screenLimitedPickThreshold, worldUnitsPerPixelAtDistance } from "cadjs/lib/viewer/pickingThresholds.js";
import {
  createViewerContextMenuGestureState,
  VIEWER_CONTEXT_MENU_SUPPRESSION_MS
} from "./viewerContextMenuGesture.js";
import { partIdFromIntersection, shouldRaycastRecordForPick } from "./partPicking.js";

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

test("viewer context menu gesture suppression blocks one menu event", () => {
  let time = 1000;
  const gesture = createViewerContextMenuGestureState({
    now: () => time
  });

  gesture.suppressNextContextMenu();
  assert.equal(gesture.isSuppressed(), true);
  assert.equal(gesture.consumeSuppression(), true);
  assert.equal(gesture.isSuppressed(), false);
  assert.equal(gesture.consumeSuppression(), false);
});

test("viewer context menu gesture suppression expires", () => {
  let time = 2000;
  const gesture = createViewerContextMenuGestureState({
    now: () => time
  });

  gesture.suppressNextContextMenu();
  assert.equal(gesture.isSuppressed(), true);

  time += VIEWER_CONTEXT_MENU_SUPPRESSION_MS + 1;

  assert.equal(gesture.isSuppressed(), false);
  assert.equal(gesture.consumeSuppression(), false);
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
});

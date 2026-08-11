import assert from "node:assert/strict";
import test from "node:test";

import { viewportFitScale } from "./viewportCameraKit.js";

// The framed area of a viewport with a top bar and no side sheets, then the same
// window with a sheet open. Only the ratio between two scales is used, so these
// read as "how much further back the camera has to sit than it did before".
const wide = { aspect: 1120 / 756, height: 800, framedHeight: 756 };
const narrow = { aspect: 355 / 756, height: 800, framedHeight: 756 };

test("perspective fit scale is fixed while the framed area stays wider than tall", () => {
  // The vertical field of view is what frames the model, so extra width changes
  // nothing -- and a resize that only adds width must not move the camera.
  const square = viewportFitScale({ fov: 48, aspect: 1 });
  assert.ok(Math.abs(viewportFitScale({ fov: 48, aspect: 2.4 }) - square) < 1e-9);
  assert.ok(Math.abs(viewportFitScale({ fov: 48, aspect: 1.4 }) - square) < 1e-9);
  assert.ok(Math.abs(square - 1 / Math.sin((48 * Math.PI) / 360)) < 1e-9);
});

test("perspective fit scale grows once the framed area is taller than wide", () => {
  const half = viewportFitScale({ fov: 48, aspect: 0.5 });
  assert.ok(half > viewportFitScale({ fov: 48, aspect: 1 }));
  // Width is the limiting dimension now, so halving it pulls the camera back
  // by close to 2x -- exactly 2x only in the small-angle limit.
  assert.ok(half / viewportFitScale({ fov: 48, aspect: 1 }) > 1.8);
});

test("orthographic fit scale tracks the smaller framed dimension", () => {
  // R * height / min(framedWidth, framedHeight), expressed per unit radius.
  assert.ok(Math.abs(viewportFitScale({ orthographic: true, ...wide }) - 800 / 756) < 1e-9);
  assert.ok(Math.abs(viewportFitScale({ orthographic: true, ...narrow }) - 800 / 355) < 1e-9);
});

test("closing a sheet undoes the scale change that opening it made", () => {
  // Reframing is applied as a ratio, so a viewport that comes back to where it
  // started has to leave the camera where it started.
  const opened = viewportFitScale({ orthographic: true, ...narrow }) / viewportFitScale({ orthographic: true, ...wide });
  const closed = viewportFitScale({ orthographic: true, ...wide }) / viewportFitScale({ orthographic: true, ...narrow });
  assert.ok(opened > 2);
  assert.ok(Math.abs(opened * closed - 1) < 1e-12);
});

test("degenerate viewports fall back instead of producing a non-finite scale", () => {
  for (const metrics of [
    {},
    { aspect: 0 },
    { aspect: Number.NaN },
    { orthographic: true, aspect: 0, height: 0, framedHeight: 0 },
    { orthographic: true, aspect: Number.NaN, height: Number.NaN, framedHeight: Number.NaN },
    { fov: 0, aspect: 1 },
    { fov: Number.NaN, aspect: 1 }
  ]) {
    const scale = viewportFitScale(metrics);
    assert.ok(Number.isFinite(scale) && scale > 0, `bad scale for ${JSON.stringify(metrics)}`);
  }
});

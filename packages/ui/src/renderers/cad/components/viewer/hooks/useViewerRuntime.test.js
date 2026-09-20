import assert from "node:assert/strict";
import test from "node:test";

import { viewerDepthSettings, viewerLogarithmicDepthBuffer } from "../renderDepthPolicy.js";

test("all interactive presets use one shadow-compatible depth policy", () => {
  assert.equal(viewerLogarithmicDepthBuffer(false), false);
  assert.equal(viewerLogarithmicDepthBuffer(true), false);
});

test("depth fitting includes Grid independently of Floor and omits disabled guides", () => {
  const runtime = { gridConfig: { size: 800 }, gridHelper: { position: { x: 10, y: 20, z: 0 } } };
  assert.deepEqual(viewerDepthSettings(runtime).gridBounds, { min: [-390, -380, 0], max: [410, 420, 0] });
  assert.equal(viewerDepthSettings(runtime).groundZ, null);
  runtime.photographicStudio = { ground: { position: { z: -5 } } };
  assert.equal(viewerDepthSettings(runtime).groundZ, -5);
  runtime.gridHelper = null;
  assert.equal(viewerDepthSettings(runtime).gridBounds, null);
});

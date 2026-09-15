import assert from "node:assert/strict";
import test from "node:test";

import { viewerLogarithmicDepthBuffer } from "../renderDepthPolicy.js";

test("CAD keeps logarithmic depth while photographic Render uses shadow-compatible depth", () => {
  assert.equal(viewerLogarithmicDepthBuffer(false), true);
  assert.equal(viewerLogarithmicDepthBuffer(true), false);
});

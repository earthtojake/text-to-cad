import assert from "node:assert/strict";
import test from "node:test";

import { requestSceneFrame } from "./sceneFrames.js";

function runtime() {
  const calls = [];
  return { calls, requestRender: () => calls.push("render"), requestFrame: () => calls.push("frame") };
}

test("a pass that changed what casts shadows re-renders them; any other keeps the maps", () => {
  const value = runtime();
  requestSceneFrame(value, true);
  requestSceneFrame(value, false);
  assert.deepEqual(value.calls, ["render", "frame"]);
});

test("a runtime without a shadow-keeping frame gets an ordinary one", () => {
  const calls = [];
  requestSceneFrame({ requestRender: () => calls.push("render") }, false);
  assert.deepEqual(calls, ["render"]);
  assert.doesNotThrow(() => requestSceneFrame(null, false));
});

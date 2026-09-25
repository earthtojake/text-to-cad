import assert from "node:assert/strict";
import test from "node:test";

import { readShellState, scopeShellCamera, shellStatesEqual, writeShellState, SHELL_STATE_VERSION } from "./shellState.js";

const camera = { position: [10, -20, 30], target: [0, 0, 0], up: [0, 0, 1], zoom: 1.5, projection: "orthographic" };

test("a missing, foreign or older record restores nothing and never throws", () => {
  for (const raw of [undefined, null, "x", [], { version: 0, camera }, { version: 1, fileSession: { slices: {} } }]) {
    const state = readShellState(raw);
    assert.equal(state.version, SHELL_STATE_VERSION);
    assert.equal(state.camera, null);
    assert.equal(state.display.mode, "solid");
    assert.deepEqual([state.tool, state.renderer], ["", {}]);
  }
});

test("the record discards camera framing while preserving display, tool and renderer state", () => {
  const display = readShellState({ version: 1, display: { mode: "render", surfaces: { colorMode: "single", color: "#00c040" } } }).display;
  const written = writeShellState({ camera, display, tool: "orbit", renderer: { clip: "glb:1" } });
  const copy = JSON.parse(JSON.stringify(written));
  const state = readShellState(copy);
  assert.equal(written.camera, null);
  assert.equal(state.camera, null);
  assert.equal(readShellState({ ...copy, camera }).camera, null);
  assert.deepEqual([state.display.mode, state.display.surfaces.colorMode, state.display.surfaces.color], ["render", "single", "#00c040"]);
  assert.deepEqual([state.tool, state.renderer], ["orbit", { clip: "glb:1" }]);
  assert.equal(shellStatesEqual(written, writeShellState({ camera, display, tool: "orbit", renderer: { clip: "glb:1" } })), true);
  assert.equal(shellStatesEqual(written, writeShellState({ camera, display, tool: "draw" })), false);
});

test("display settings this build cannot read are the defaults, and the stored record is not rewritten", () => {
  const raw = { version: 1, display: { mode: "no-such-mode", surfaces: 7 } };
  const before = JSON.stringify(raw);
  assert.equal(readShellState(raw).display.mode, "solid");
  assert.equal(JSON.stringify(raw), before);
});

test("a stored camera is scoped to the model it framed", () => {
  const scoped = scopeShellCamera(camera, "parts/plate.glb", "cad");
  assert.deepEqual([scoped.modelKey, scoped.sceneScaleMode, scoped.coordinateSystem], ["parts/plate.glb", "cad", "cad-z-up-v1"]);
  assert.equal(scopeShellCamera(null, "x", "cad"), null);
});

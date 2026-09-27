import assert from "node:assert/strict";
import test from "node:test";

import { createToolModes } from "./toolModes.js";

const modes = createToolModes({
  defaultMode: "pick",
  modes: { pick: {}, ruler: { toggles: true }, ink: { toggles: true }, play: {}, handles: {} }
});

test("an unknown tool falls back to the default tool", () => {
  assert.equal(modes.normalize("ruler"), "ruler");
  assert.equal(modes.normalize("laser"), "pick");
  assert.equal(modes.normalize(undefined), "pick");
  assert.equal(modes.defaultMode, "pick");
});

test("Display is not a tool: its old mode id is unknown, so it is the default tool", () => {
  assert.equal(modes.normalize("display"), "pick");
  assert.equal(modes.next("ink", "display"), "pick");
});

test("a toggling session ends when its tool is asked for again; other tools stay", () => {
  assert.equal(modes.next("pick", "ink"), "ink");
  assert.equal(modes.next("ink", "ink"), "pick");
  assert.equal(modes.next("ruler", "ruler"), "pick");
  assert.equal(modes.next("play", "play"), "play");
  assert.equal(modes.next("ink", "nonsense"), "pick");
});

test("the tool in hand is never recorded: the machine answers no question about a saved tab", () => {
  assert.equal("persisted" in modes, false);
  assert.equal("restore" in modes, false);
});

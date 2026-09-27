import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveInteractionPixelRatioCap
} from "./renderQuality.js";

test("interaction quality uses the lower cap for mesh-only scenes", () => {
  assert.equal(resolveInteractionPixelRatioCap({
    idlePixelRatioCap: 2,
    interactionPixelRatioCap: 1.25,
    screenSpaceLineMaterials: new Set()
  }), 1.25);
});

test("interaction quality preserves idle density while screen-space lines are visible", () => {
  assert.equal(resolveInteractionPixelRatioCap({
    idlePixelRatioCap: 2,
    interactionPixelRatioCap: 1.25,
    screenSpaceLineMaterials: new Set([{}])
  }), 2);
});

test("interaction quality can use an explicit nested screen-space line count", () => {
  assert.equal(resolveInteractionPixelRatioCap({
    idlePixelRatioCap: 2,
    interactionPixelRatioCap: 1.25,
    screenSpaceLineMaterialCount: 4
  }), 2);
});

test("interaction quality can be pinned for edge-rendered CAD scenes", () => {
  assert.equal(resolveInteractionPixelRatioCap({
    idlePixelRatioCap: 2,
    interactionPixelRatioCap: 1.25,
    preservePixelRatio: true
  }), 2);
});

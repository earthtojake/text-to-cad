// The tube runtime's lazy boundary, asserted on a pristine module registry:
// node --test gives each test FILE its own process, so nothing here has loaded
// tubeDeformation.js before the first test runs. Nothing in this file may
// import it statically, or the test would prove the opposite of its claim.
import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { loadSourceAnimation } from "./renderModule.js";
import { evaluateAnimationClip } from "./animationRuntime.js";
import { loadTubeDeformation, requireTubeDeformation, tubeDeformation } from "./tubeDeformationChunk.js";

const MESH_DATA = { parts: [{ id: "o1", label: "rope" }] };
const line = (start, end) => ({ kind: "line", start, end });
const REST = { segments: [line([0, 0, 0], [10, 0, 0])], normal: [0, 0, 1] };
const BENT = { segments: [line([0, 0, 0], [10, 4, 0])], normal: [0, 0, 1] };

const TUBE_SOURCE = `
export const clips = {
  flex: {
    duration: 1,
    update(t, m) {
      m.get("rope").deformTube({
        rest: ${JSON.stringify(REST)},
        path: ${JSON.stringify(BENT)}
      });
    }
  }
};
`;

const RIGID_SOURCE = `
export const clips = {
  spin: { duration: 1, update(t, m) { m.get("rope").rotate([0, 0, 1], 90 * t); } }
};
`;

// FIRST, while nothing has loaded it: a document that declares no animation
// cannot reach deformTube, so it must not drag the tube chunk into the page.
test("a document with no animation never loads the tube runtime", async () => {
  assert.equal(tubeDeformation(), null);
  assert.throws(() => requireTubeDeformation("deformTube"), /loadTubeDeformation/u);
  assert.equal(await loadSourceAnimation({}), null);
  assert.equal(tubeDeformation(), null, "an unanimated document fetched the tube chunk");
});

test("compiling an animation loads the runtime before any clip can run", async () => {
  const rigid = await loadSourceAnimation({ animation: { language: "javascript", source: RIGID_SOURCE } });
  assert.deepEqual(Object.keys(rigid.clips), ["spin"]);
  // Declaring an animation is the gate, not calling deformTube: a clip may
  // reach for a tube at any t, so the runtime is there before the first frame.
  assert.notEqual(tubeDeformation(), null);
});

test("a deformTube clip produces exactly what the eager runtime produced", async () => {
  const { clips } = await loadSourceAnimation({ animation: { language: "javascript", source: TUBE_SOURCE } });
  const frame = evaluateAnimationClip(THREE, MESH_DATA, clips.flex, 0.5);
  const [[partId, deformation]] = [...frame.deformations];
  assert.equal(partId, "o1");

  // The same spec through the module's own entry point: the lazy boundary must
  // change nothing about the numbers the renderer draws from.
  const { normalizeTubeDeformation } = await loadTubeDeformation();
  assert.deepEqual(deformation, normalizeTubeDeformation({ rest: REST, path: BENT }));
});

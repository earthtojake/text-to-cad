import assert from "node:assert/strict";
import test from "node:test";

import { stepMotionSources } from "./useStepMotion.js";

test("a STEP's motion comes from its catalog entry: the articulation and the routines cadgen resolved", () => {
  const animation = { clips: [{ id: "swing", label: "Swing", duration: 4, loop: true, tracks: [] }] };
  const articulation = { schemaVersion: 2, controls: [], joints: [], carries: {}, handles: [], poses: {}, opening: {} };
  const entry = { file: "/models/arm/hinge.step", hash: "h1", documentHash: "d1", animation,
    poseUrl: "/__cad/asset?file=hinge.step.json&v=1", articulation };
  const sources = stepMotionSources(entry);
  assert.equal(sources.moduleUrl, entry.poseUrl);
  assert.equal(sources.articulation, articulation);
  assert.equal(sources.sourceAnimation, animation);
  assert.equal(sources.animationKey, "/models/arm/hinge.step:d1", "a routine is keyed by the document it was baked for");
  const still = stepMotionSources({ file: "/models/block.step", hash: "h2" });
  assert.deepEqual([still.sourceAnimation, still.animationKey, still.articulation], [null, "", null], "no routine, no key; nothing to pose");
});

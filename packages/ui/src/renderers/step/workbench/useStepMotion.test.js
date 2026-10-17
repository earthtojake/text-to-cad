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
  // A routine is keyed by its keyframes, not by the document: a build's preview and the file it
  // saves carry the same clips under different trees, and are one routine; a changed clip is another.
  assert.match(sources.animationKey, /^\/models\/arm\/hinge\.step:[0-9a-f]{16}$/);
  const saved = stepMotionSources({ ...entry, hash: "h2", documentHash: "d2", animation: JSON.parse(JSON.stringify(animation)) });
  assert.equal(saved.animationKey, sources.animationKey, "the same keyframes under another tree are the same routine");
  const changed = stepMotionSources({ ...entry, animation: { clips: [{ ...animation.clips[0], duration: 5 }] } });
  assert.notEqual(changed.animationKey, sources.animationKey);
  // A routine that bends a tube plays the document's skins, which its URL names: another document's are another key.
  assert.notEqual(stepMotionSources({ ...entry, tubeSkinsUrl: "/__cad/skins?document=d1" }).animationKey, sources.animationKey);
  const still = stepMotionSources({ file: "/models/block.step", hash: "h2" });
  assert.deepEqual([still.sourceAnimation, still.animationKey, still.articulation], [null, "", null], "no routine, no key; nothing to pose");
});

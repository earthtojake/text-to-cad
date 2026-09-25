import assert from "node:assert/strict";
import test from "node:test";

import { stepMotionSources } from "./useStepMotion.js";

test("a STEP's motion comes from its sidecar, or from an edit's preview while one is shown", () => {
  const sidecar = { animation: { source: "export default {}" } };
  const entry = { file: "arm/hinge.step", rootRelativeFile: "arm/hinge.step", hash: "h1", documentHash: "d1", sourceSidecar: sidecar,
    assets: { stepModule: { url: "/__cad/store/module", hash: "m1" } } };
  const sources = stepMotionSources(entry);
  assert.equal(sources.cadPath, sources.moduleUrl ? "arm/hinge" : "");
  assert.equal(sources.sourceAnimation, sidecar.animation);
  assert.equal(sources.animationKey, "arm/hinge.step:d1", "a routine is keyed by the document it was compiled from");
  const preview = stepMotionSources({ ...entry, editingPreview: true, previewKinematics: {}, previewAnimation: { source: "x" } });
  assert.equal(preview.moduleUrl, "preview:h1");
  assert.equal(preview.cadPath, "arm/hinge");
  assert.deepEqual(preview.sourceAnimation, { source: "x" });
  const still = stepMotionSources({ file: "block.step", hash: "h2" });
  assert.deepEqual([still.sourceAnimation, still.animationKey], [null, ""], "no routine, no key");
});

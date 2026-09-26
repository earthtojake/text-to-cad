import assert from "node:assert/strict";
import test from "node:test";


import {
  BUILDABLE_STEP_ARTIFACT_ERROR_CODES,
  stepArtifactCanGenerate,
  stepArtifactGenerationInProgress,
  stepArtifactIssueShouldSuppress,
  stepArtifactStatusMessage
} from "./stepArtifactStatus.js";
import { buildViewerMeshAlert } from "./viewerAlerts.js";
import { stepFileStatusItems } from "./fileStatusItems.js";

test("stepArtifactCanGenerate allows buildable STEP artifact warnings", () => {
  for (const code of BUILDABLE_STEP_ARTIFACT_ERROR_CODES) {
    assert.equal(stepArtifactCanGenerate({
      file: "parts/bracket.step",
      artifact: {
        ok: false,
        error: code
      }
    }), true, code);
  }
});

test("stepArtifactCanGenerate respects backend generation availability", () => {
  const entry = {
    file: "parts/bracket.step",
    artifact: {
      ok: false,
      error: "missing_glb"
    }
  };

  assert.equal(
    stepArtifactCanGenerate(entry, { generationAvailable: false }),
    false
  );
});

test("stepArtifactGenerationInProgress matches viewer retries and lock-file outputs", () => {
  const entry = {
    file: "parts/bracket.step",
    artifact: {
      ok: false,
      error: "missing_step_hash"
    }
  };

  assert.equal(stepArtifactGenerationInProgress({
    entry,
    generationState: { status: "loading", file: "parts/bracket.step" }
  }), true);
  assert.equal(stepArtifactGenerationInProgress({
    entry,
    activeGenerationFiles: ["parts/.bracket.step.glb"]
  }), true);
  assert.equal(stepArtifactGenerationInProgress({
    entry,
    activeGenerationFiles: [".bracket.step.glb"]
  }), false);
  assert.equal(stepArtifactGenerationInProgress({
    entry,
    activeGenerationFiles: ["parts/other.step"]
  }), false);
});


test("the viewer card and the Status tab word a failed artifact the same way", () => {
  // One message table serves both: the alert over the viewport and the file's Status row.
  const artifact = { ok: false, error: "missing_source_path" };
  const entry = { file: "part.step", kind: "part", artifact };
  assert.equal(stepArtifactStatusMessage(artifact), "Generated GLB metadata is missing its source path.");
  assert.equal(buildViewerMeshAlert(entry, false, "", null)?.message, `“part.step”: ${stepArtifactStatusMessage(artifact)}`);
  assert.ok(stepFileStatusItems({ entry }).some(item => item.message === stepArtifactStatusMessage(artifact)));
});

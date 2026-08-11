import assert from "node:assert/strict";
import test from "node:test";

import { RENDER_FORMAT } from "cadjs/lib/fileFormats.js";

import {
  BUILDABLE_STEP_ARTIFACT_ERROR_CODES,
  stepArtifactCanGenerate,
  stepArtifactGenerationInProgress,
  stepArtifactIssueShouldSuppress
} from "./stepArtifactStatus.js";

test("stepArtifactCanGenerate allows buildable STEP artifact warnings", () => {
  for (const code of BUILDABLE_STEP_ARTIFACT_ERROR_CODES) {
    assert.equal(stepArtifactCanGenerate({
      file: "parts/bracket.step",
      artifact: {
        ok: false,
        error: code,
        sourceKind: "python"
      }
    }, RENDER_FORMAT.STEP), true, code);
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
    stepArtifactCanGenerate(entry, RENDER_FORMAT.STEP, { generationAvailable: false }),
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


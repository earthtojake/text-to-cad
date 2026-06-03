import assert from "node:assert/strict";
import test from "node:test";

import { RENDER_FORMAT } from "cadjs/lib/fileFormats.js";

import {
  BUILDABLE_STEP_ARTIFACT_ERROR_CODES,
  STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD,
  runStepArtifactGenerationWithRetries,
  stepArtifactCanGenerate,
  stepArtifactGenerationFileRefs,
  stepArtifactGenerationFailureCount,
  stepArtifactGenerationInProgress,
  stepArtifactIssueShouldSuppress,
  validateGeneratedStepArtifactPayload
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

test("stepArtifactGenerationFailureCount normalizes persisted state", () => {
  assert.equal(stepArtifactGenerationFailureCount(null), 0);
  assert.equal(stepArtifactGenerationFailureCount({ failureCount: -1 }), 0);
  assert.equal(stepArtifactGenerationFailureCount({ failureCount: 2.9 }), 2);
  assert.equal(stepArtifactGenerationFailureCount({ failureCount: "3" }), 3);
});

test("stepArtifactGenerationFileRefs tracks STEP files and generated GLB artifacts", () => {
  const refs = stepArtifactGenerationFileRefs({
    file: "parts/bracket.step",
    artifact: {
      stepPath: "models/parts/bracket.step",
      glbPath: "models/parts/.bracket.step.glb",
      sourcePath: "models/parts/bracket.py"
    }
  });

  assert.equal(refs.includes("parts/bracket.step"), true);
  assert.equal(refs.includes("parts/.bracket.step.glb"), true);
  assert.equal(refs.includes("models/parts/bracket.step"), true);
  assert.equal(refs.includes("models/parts/.bracket.step.glb"), true);
  assert.equal(refs.includes("models/parts/bracket.py"), false);
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

test("stepArtifactIssueShouldSuppress hides regenerable issues while generation can resolve them", () => {
  const entry = {
    file: "parts/bracket.step",
    artifact: {
      ok: false,
      error: "missing_step_hash"
    }
  };

  assert.equal(stepArtifactIssueShouldSuppress({ entry }), true);
  assert.equal(stepArtifactIssueShouldSuppress({
    entry,
    generationState: { status: "error", failureCount: STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD }
  }), false);
  assert.equal(stepArtifactIssueShouldSuppress({
    entry,
    generationAvailable: false
  }), false);
  assert.equal(stepArtifactIssueShouldSuppress({
    entry,
    generationAvailable: false,
    activeGenerationFiles: ["parts/.bracket.step.glb"]
  }), true);
});

test("validateGeneratedStepArtifactPayload rejects non-renderable generation results", () => {
  assert.throws(
    () => validateGeneratedStepArtifactPayload({
      entry: {
        file: "parts/bracket.step"
      }
    }, { file: "parts/bracket.step" }),
    /Generated STEP artifact is not renderable: parts\/bracket\.step/
  );
});

test("validateGeneratedStepArtifactPayload rejects persistent regenerable artifact statuses", () => {
  assert.throws(
    () => validateGeneratedStepArtifactPayload({
      entry: {
        file: "parts/bracket.step",
        url: "/models/parts/.bracket.step.glb?v=hash",
        hash: "hash",
        artifact: {
          ok: false,
          error: "missing_step_hash"
        }
      }
    }, { file: "parts/bracket.step" }),
    /Generated STEP artifact still reports missing_step_hash: parts\/bracket\.step/
  );
});

test("validateGeneratedStepArtifactPayload accepts renderable current generation results", () => {
  assert.doesNotThrow(() => validateGeneratedStepArtifactPayload({
    entry: {
      file: "parts/bracket.step",
      url: "/models/parts/.bracket.step.glb?v=hash",
      hash: "hash",
      artifact: {
        ok: true
      }
    }
  }, { file: "parts/bracket.step" }));
});

test("runStepArtifactGenerationWithRetries retries hidden failures until success", async () => {
  const states = [];
  const errors = [];
  let callCount = 0;
  const payload = { entry: { url: "/models/parts/.bracket.step.glb" } };

  const result = await runStepArtifactGenerationWithRetries({
    key: "parts/bracket.step:hash:missing_step_hash",
    file: "parts/bracket.step",
    generate: async () => {
      callCount += 1;
      if (callCount < STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD) {
        throw new Error(`failed ${callCount}`);
      }
      return payload;
    },
    onState: (state) => states.push(state),
    onFinalError: (message) => errors.push(message)
  });

  assert.equal(callCount, STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD);
  assert.equal(result.status, "ready");
  assert.equal(result.payload, payload);
  assert.deepEqual(errors, []);
  assert.equal(states.at(-1).status, "ready");
  assert.equal(states.at(-1).failureCount, 0);
  assert.deepEqual(
    states.filter((state) => state.error).map((state) => state.error),
    ["failed 1", "failed 2"]
  );
});

test("runStepArtifactGenerationWithRetries surfaces final error only after threshold", async () => {
  const states = [];
  const errors = [];
  let callCount = 0;

  const result = await runStepArtifactGenerationWithRetries({
    key: "parts/bracket.step:hash:missing_glb",
    file: "parts/bracket.step",
    generate: async () => {
      callCount += 1;
      throw new Error(`failed ${callCount}`);
    },
    onState: (state) => states.push(state),
    onFinalError: (message, state) => errors.push({ message, state })
  });

  assert.equal(callCount, STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD);
  assert.equal(result.status, "error");
  assert.equal(result.state.status, "error");
  assert.equal(result.state.failureCount, STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD);
  assert.deepEqual(errors.map((error) => error.message), ["failed 3"]);
  assert.equal(
    states.filter((state) => state.status === "error").length,
    1
  );
});

test("runStepArtifactGenerationWithRetries resumes from existing failures", async () => {
  const states = [];
  const errors = [];
  let callCount = 0;

  const result = await runStepArtifactGenerationWithRetries({
    key: "parts/bracket.step:hash:stale_step_artifact",
    file: "parts/bracket.step",
    initialFailureCount: STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD - 1,
    generate: async () => {
      callCount += 1;
      throw new Error("still failing");
    },
    onState: (state) => states.push(state),
    onFinalError: (message) => errors.push(message)
  });

  assert.equal(callCount, 1);
  assert.equal(result.status, "error");
  assert.equal(states[0].attempt, STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD);
  assert.equal(states.at(-1).failureCount, STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD);
  assert.deepEqual(errors, ["still failing"]);
});

test("runStepArtifactGenerationWithRetries treats invalid success payloads as failures", async () => {
  const states = [];
  let callCount = 0;

  const result = await runStepArtifactGenerationWithRetries({
    key: "parts/bracket.step:hash:missing_glb",
    file: "parts/bracket.step",
    generate: async () => {
      callCount += 1;
      return { entry: { file: "parts/bracket.step" } };
    },
    validatePayload: (payload) => {
      if (!payload?.entry?.url) {
        throw new Error("Generated STEP artifact is not renderable.");
      }
    },
    onState: (state) => states.push(state)
  });

  assert.equal(callCount, STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD);
  assert.equal(result.status, "error");
  assert.equal(states.at(-1).error, "Generated STEP artifact is not renderable.");
});

test("runStepArtifactGenerationWithRetries stops when a request becomes stale", async () => {
  const states = [];
  let current = true;
  let callCount = 0;

  const result = await runStepArtifactGenerationWithRetries({
    key: "parts/bracket.step:hash:missing_glb",
    file: "parts/bracket.step",
    generate: async () => {
      callCount += 1;
      current = false;
      throw new Error("stale request failure");
    },
    isCurrent: () => current,
    onState: (state) => states.push(state),
    onFinalError: () => {
      throw new Error("stale requests must not publish final errors");
    }
  });

  assert.equal(callCount, 1);
  assert.equal(result.status, "cancelled");
  assert.deepEqual(states.map((state) => state.status), ["loading"]);
});

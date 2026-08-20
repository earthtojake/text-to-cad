import assert from "node:assert/strict";
import test from "node:test";

import {
  FILE_STATUS_LEVELS,
  buildFileStatusItems,
  fileStatusWarningOrErrorItems,
  fileStatusHasWarningsOrErrors,
  formatFileStatusItemForAgent,
  mostIntenseFileStatusLevel,
  sdfFileStatusItems,
  stepFileStatusItems,
  viewerAlertFileStatusItem
} from "./fileStatusItems.js";
import { BUILDABLE_STEP_ARTIFACT_ERROR_CODES } from "./stepArtifactStatus.js";

const viewerServerInfo = {
  directoryRoot: "/project/text-to-cad",
  rootDir: "models",
  rootPath: "/project/text-to-cad/models",
};

const failedStepArtifactGenerationState = Object.freeze({
  status: "error",
  failureCount: 3
});

test("stepFileStatusItems treats missing STEP source files as warnings", () => {
  const items = stepFileStatusItems({
    entry: {
      file: "step/parts/cylindrical_cap.step",
      kind: "part"
    },
    stepSourceStatus: {
      file: "models/step/parts/cylindrical_cap.step",
      stepPath: "models/step/parts/cylindrical_cap.step",
      sourceKind: "python",
      sourcePath: "models/step/parts/cylindrical_cap.py",
      step: {
        ok: false,
        status: "missing",
        missing: true,
        stale: false,
        message: "STEP file is missing."
      }
    },
    stepArtifactGenerationState: failedStepArtifactGenerationState,
    viewerServerInfo
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].level, FILE_STATUS_LEVELS.WARNING);
  assert.equal(items[0].title, "STEP file missing");
  assert.equal(
    items[0].message,
    "STEP file was not generated for this Python script; only the render package is available."
  );
  assert.deepEqual(items[0].details.map((item) => item.label), [
    "STEP file",
    "Source kind",
    "Python source"
  ]);
});

test("stepFileStatusItems marks missing STEP artifacts as errors", () => {
  const items = stepFileStatusItems({
    entry: {
      file: "tom/STEP/tom.step",
      kind: "assembly",
      artifact: {
        ok: false,
        error: "missing_glb",
        stale: false,
        sourceKind: "python",
        stepPath: "models/tom/STEP/tom.step",
        packagePath: "models/tom/STEP/__cadgen__/models/tom.step",
        artifactHash: "",
        currentHash: "new-hash",
        message: "Render package is missing."
      }
    },
    stepArtifactGenerationState: failedStepArtifactGenerationState,
    viewerServerInfo
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].level, FILE_STATUS_LEVELS.ERROR);
  assert.equal(items[0].title, "STEP artifact missing");
  assert.equal(items[0].message, "Generated GLB is missing.");
  assert.equal(items[0].details.find((item) => item.label === "Code")?.value, "missing_glb");
  assert.equal(items[0].details.find((item) => item.label === "Render package")?.value, "tom/STEP/__cadgen__/models/tom.step");
});

test("stepFileStatusItems reads artifact warnings from current-file status", () => {
  const items = stepFileStatusItems({
    entry: {
      file: "tom/STEP/tom.step",
      kind: "assembly"
    },
    stepSourceStatus: {
      artifact: {
        ok: false,
        error: "missing_glb",
        sourceKind: "step",
        stepPath: "models/tom/STEP/tom.step",
        packagePath: "models/tom/STEP/__cadgen__/models/tom.step"
      },
      step: {
        ok: true,
        status: "current",
        missing: false,
        stale: false
      }
    },
    stepArtifactGenerationState: failedStepArtifactGenerationState,
    viewerServerInfo
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].title, "STEP artifact missing");
  assert.equal(items[0].details.find((item) => item.label === "Render package")?.value, "tom/STEP/__cadgen__/models/tom.step");
});

test("stepFileStatusItems keeps renderable STEP artifact issues as warnings", () => {
  const renderableArtifactCases = [
    ["stale_step_artifact", true, "STEP artifact stale", "Generated GLB doesn't match the hash of the STEP file."],
    ["missing_glb", false, "STEP artifact missing", "Generated GLB is missing."],
    ["missing_step_topology", false, "STEP artifact metadata warning", "Generated GLB is missing STEP topology metadata."],
    ["missing_selector_topology", false, "STEP artifact metadata warning", "Generated GLB is missing selector topology metadata."],
    ["missing_edge_topology", false, "STEP artifact metadata warning", "Generated GLB is missing surface edge topology metadata."],
    ["missing_surface_edge_attributes", false, "STEP artifact metadata warning", "Generated GLB is missing surface edge render attributes."],
    ["unsupported_step_topology", false, "STEP artifact metadata warning", "Generated GLB topology metadata is unsupported."],
    ["missing_source_path", false, "STEP artifact metadata warning", "Generated GLB metadata is missing its source path."],
    ["missing_step_hash", false, "STEP artifact metadata warning", "Generated GLB is missing the hash of the STEP file."]
  ];

  for (const [error, stale, title, message] of renderableArtifactCases) {
    const items = stepFileStatusItems({
      entry: {
        file: "step/parts/part.step",
        kind: "part",
        url: "/models/step/parts/.part.step.glb?v=hash",
        hash: "glb-hash",
        artifact: {
          ok: false,
          error,
          stale
        }
      },
      stepArtifactGenerationState: failedStepArtifactGenerationState
    });

    assert.equal(items.length, 1);
    assert.equal(items[0].level, FILE_STATUS_LEVELS.WARNING);
    assert.equal(items[0].title, title);
    assert.equal(items[0].message, message);
  }
});

test("stepFileStatusItems marks non-renderable STEP artifact issues as errors", () => {
  const items = stepFileStatusItems({
    entry: {
      file: "step/parts/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_source_path",
        message: "GLB STEP_topology is missing required sourcePath identity."
      }
    },
    stepArtifactGenerationState: failedStepArtifactGenerationState
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].level, FILE_STATUS_LEVELS.ERROR);
  assert.equal(items[0].title, "STEP artifact unavailable");
  assert.equal(items[0].message, "Generated GLB metadata is missing its source path.");
});

test("stepFileStatusItems trims obsolete regeneration prompts from artifact messages", () => {
  const items = stepFileStatusItems({
    entry: {
      file: "step/parts/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "unsupported_step_topology",
        message: "STEP topology schema is unsupported.\nRegenerate STEP artifacts with legacy instructions:"
      }
    },
    stepArtifactGenerationState: failedStepArtifactGenerationState
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].message, "Generated GLB topology metadata is unsupported.");
});

test("parser warnings normalize to status items", () => {
  assert.equal(sdfFileStatusItems({
    staticMetadata: {
      warnings: ["Unsupported geometry was skipped."]
    }
  })[0].title, "SDF warning");
});

test("generated source status explains missing generator source", () => {
  const items = buildFileStatusItems({
    entry: {
      file: "robots/robot.urdf",
      kind: "urdf",
      sourceKind: "python",
      sourceStatus: {
        ok: false,
        status: "missing",
        stale: false,
        sourceKind: "python",
        sourcePath: "models/robots/robot_urdf.py",
        message: "Python generator source is unavailable."
      }
    },
    fileSheetKind: "urdf",
    viewerServerInfo
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].level, FILE_STATUS_LEVELS.WARNING);
  assert.equal(items[0].title, "Generator source missing");
  assert.equal(
    items[0].message,
    "This file records a Python generator path, but that source file is not available."
  );
  assert.equal(items[0].details.find((item) => item.label === "Python source")?.value, "robots/robot_urdf.py");
});

test("viewer alerts normalize to status items", () => {
  const item = viewerAlertFileStatusItem({
    severity: "error",
    summary: "Mesh load failed",
    title: "Failed to load render mesh",
    message: "404",
    resolution: "Reload the page.",
    command: "python -m cadgen.step_artifact_cli --repo-root . --step model.step"
  });

  assert.equal(item.level, FILE_STATUS_LEVELS.ERROR);
  assert.equal(item.title, "Failed to load render mesh");
  assert.equal(item.details.find((detail) => detail.label === "Resolution")?.value, "Reload the page.");
  assert.equal(item.details.find((detail) => detail.label === "Command")?.mono, true);
});

test("buildFileStatusItems combines producers and exposes the most intense level", () => {
  const items = buildFileStatusItems({
    entry: {
      file: "step/parts/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true,
        message: "GLB was generated from older source."
      }
    },
    fileSheetKind: "step",
    stepArtifactGenerationState: failedStepArtifactGenerationState,
    viewerAlert: {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: "404"
    }
  });

  assert.equal(fileStatusHasWarningsOrErrors(items), true);
  assert.equal(mostIntenseFileStatusLevel(items), FILE_STATUS_LEVELS.ERROR);
  assert.deepEqual(items.map((item) => item.level), [
    FILE_STATUS_LEVELS.ERROR,
    FILE_STATUS_LEVELS.ERROR
  ]);
  assert.equal(items[0].message, "Generated GLB doesn't match the hash of the STEP file.");
});

test("stepFileStatusItems hides regenerable STEP artifact issues until three generation failures", () => {
  for (const code of BUILDABLE_STEP_ARTIFACT_ERROR_CODES) {
    const entry = {
      file: "step/parts/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: code,
        message: "GLB STEP_topology is missing STEP file identity."
      }
    };

    assert.deepEqual(stepFileStatusItems({ entry }), [], code);

    assert.deepEqual(stepFileStatusItems({
      entry,
      stepArtifactGenerationState: { status: "loading", failureCount: 2 }
    }), [], code);

    assert.deepEqual(stepFileStatusItems({
      entry,
      stepArtifactGenerationState: failedStepArtifactGenerationState,
      activeGenerationFiles: ["step/parts/.part.step.glb"]
    }), [], code);

    assert.equal(stepFileStatusItems({
      entry,
      stepArtifactGenerationState: failedStepArtifactGenerationState
    })[0]?.code, code);

    assert.deepEqual(stepFileStatusItems({
      entry,
      stepArtifactGenerationAvailable: false,
      activeGenerationFiles: ["step/parts/.part.step.glb"]
    }), [], code);

    assert.equal(stepFileStatusItems({
      entry,
      stepArtifactGenerationAvailable: false
    })[0]?.code, code);
  }
});

test("stepFileStatusItems does not hide non-regenerable STEP artifact issues", () => {
  const items = stepFileStatusItems({
    entry: {
      file: "step/parts/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "invalid_step_artifact_schema",
        message: "Generated STEP artifact cannot be read."
      }
    }
  });

  assert.equal(items.length, 1);
  assert.equal(items[0].code, "invalid_step_artifact_schema");
});

test("fileStatusWarningOrErrorItems renders errors before warnings", () => {
  const items = fileStatusWarningOrErrorItems([
    {
      level: "warning",
      title: "Generated source warning",
      message: "Source metadata is incomplete."
    },
    {
      level: "info",
      title: "Neutral status",
      message: "This should be omitted."
    },
    {
      level: "error",
      title: "Failed to load render mesh",
      message: "Mesh load failed."
    }
  ]);

  assert.deepEqual(items.map((item) => item.level), [
    FILE_STATUS_LEVELS.ERROR,
    FILE_STATUS_LEVELS.WARNING
  ]);
});

test("formatFileStatusItemForAgent copies status items with details", () => {
  const item = stepFileStatusItems({
    entry: {
      file: "step/parts/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true,
        sourceKind: "step",
        stepPath: "models/step/parts/part.step",
        packagePath: "models/step/parts/__cadgen__/models/part.step",
        artifactHash: "old-hash",
        currentHash: "new-hash"
      }
    },
    stepArtifactGenerationState: failedStepArtifactGenerationState,
    viewerServerInfo
  })[0];

  assert.equal(formatFileStatusItemForAgent(item), [
    "CAD Viewer issue",
    "Level: Error",
    "Title: STEP artifact stale",
    "Description: Generated GLB doesn't match the hash of the STEP file.",
    "Source: catalog",
    "Code: stale_step_artifact",
    "",
    "Details:",
    "- Code: stale_step_artifact",
    "- STEP file: step/parts/part.step",
    "- Render package: step/parts/__cadgen__/models/part.step",
    "- Source kind: step",
    "- Artifact hash: old-hash",
    "- Current hash: new-hash"
  ].join("\n"));
});

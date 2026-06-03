import assert from "node:assert/strict";
import test from "node:test";
import {
  buildCadCommand,
  buildViewerDxfAlert,
  buildViewerMeshAlert,
  CAD_BUILD_COMMANDS
} from "./viewerAlerts.js";

test("buildCadCommand returns portable rebuild commands for generated CAD assets", () => {
  assert.equal(
    buildCadCommand("fun/part.step", { file: "fun/part.step", kind: "step" }),
    `${CAD_BUILD_COMMANDS.step} fun/part.step`
  );
  assert.equal(
    buildCadCommand("fun/generated.step", {
      file: "fun/generated.step",
      kind: "step",
      sourceKind: "python",
      source: { file: "fun/generated.py" }
    }),
    ""
  );
  assert.equal(buildCadCommand("flat/panel.dxf", { file: "flat/panel.dxf", kind: "dxf" }), "");
  assert.equal(buildCadCommand("robots/arm.urdf", { file: "robots/arm.urdf", kind: "urdf" }), "");
  assert.equal(
    buildCadCommand("robots/arm.srdf", { file: "robots/arm.srdf", kind: "srdf" }),
    ""
  );
  assert.equal(
    buildCadCommand("meshes/part.glb", { file: "meshes/part.glb", kind: "glb" }),
    ""
  );
  assert.equal(
    buildCadCommand("toolpaths/part.gcode", { file: "toolpaths/part.gcode", kind: "gcode" }),
    ""
  );
});

test("buildViewerMeshAlert reports missing sidecar meshes without rebuild commands", () => {
  assert.deepEqual(
    buildViewerMeshAlert({ file: "meshes/part.stl", kind: "stl" }, false, ""),
    {
      severity: "error",
      summary: "Mesh unavailable",
      title: "No mesh data is available",
      message: "The selected entry is listed in the CAD catalog but no renderable mesh data could be loaded for it.",
      resolution: "Confirm the STL exists in the repo and reload the page.",
      command: ""
    }
  );
});

test("buildViewerMeshAlert reports STEP artifact errors only when no mesh rendered", () => {
  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_source_path",
        message: "Topology source path is missing."
      }
    }, false, ""),
    {
      severity: "error",
      compact: true,
      summary: "STEP artifact unavailable",
      title: "STEP artifact unavailable",
      message: "Generated GLB metadata is missing its source path.",
      command: `${CAD_BUILD_COMMANDS.step} fun/part.step`
    }
  );

  assert.equal(
    buildViewerMeshAlert({
      file: "fun/part.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_source_path",
        message: "Topology source path is missing."
      }
    }, true, ""),
    null
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/stale.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true,
        message: "STEP artifact is stale."
      }
    }, false, ""),
    {
      severity: "error",
      compact: true,
      summary: "STEP artifact stale",
      title: "STEP artifact stale",
      message: "Generated GLB doesn't match the hash of the STEP file.",
      command: `${CAD_BUILD_COMMANDS.step} fun/stale.step`
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/renderable-stale.step",
      kind: "part",
      url: "/models/fun/.renderable-stale.step.glb?v=hash",
      hash: "glb-hash",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true,
        message: "STEP artifact is stale."
      }
    }, false, ""),
    {
      severity: "warning",
      blocking: false,
      compact: true,
      summary: "STEP artifact stale",
      title: "STEP artifact stale",
      message: "Generated GLB doesn't match the hash of the STEP file.",
      command: `${CAD_BUILD_COMMANDS.step} fun/renderable-stale.step`
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/renderable-stale.step",
      kind: "part",
      url: "/models/fun/.renderable-stale.step.glb?v=hash",
      hash: "glb-hash",
      artifact: {
        ok: false,
        error: "stale_step_artifact",
        stale: true,
        message: "STEP artifact is stale."
      }
    }, false, "GLB parser failed"),
    {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: "GLB parser failed",
      resolution: "Try reloading the page. If the problem persists, rebuild the render assets for this entry.",
      command: `${CAD_BUILD_COMMANDS.step} fun/renderable-stale.step`
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/generated.step",
      kind: "part",
      sourceKind: "python",
      source: { file: "fun/generated.py" },
      artifact: {
        ok: false,
        error: "missing_glb",
        sourceKind: "python",
        message: "GLB artifact is missing."
      }
    }, false, ""),
    {
      severity: "error",
      compact: true,
      summary: "STEP artifact missing",
      title: "STEP artifact missing",
      message: "Generated GLB is missing.",
      command: ""
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/missing.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_glb",
        message: "GLB artifact is missing."
      }
    }, false, ""),
    {
      severity: "error",
      compact: true,
      summary: "STEP artifact missing",
      title: "STEP artifact missing",
      message: "Generated GLB is missing.",
      command: `${CAD_BUILD_COMMANDS.step} fun/missing.step`
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/missing.step",
      kind: "part",
      artifact: {
        ok: false,
        error: "missing_glb",
        message: "Generated GLB is missing."
      }
    }, false, "STEP artifact generation is not enabled for this CAD Viewer backend"),
    {
      severity: "error",
      compact: true,
      summary: "STEP artifact missing",
      title: "STEP artifact missing",
      message: "Generated GLB is missing.",
      command: `${CAD_BUILD_COMMANDS.step} fun/missing.step`
    }
  );
});

test("buildViewerDxfAlert distinguishes DXF load, preview, and missing data states", () => {
  assert.equal(buildViewerDxfAlert("", false, "", ""), null);

  assert.deepEqual(
    buildViewerDxfAlert("flat/panel.dxf", false, "network failed", ""),
    {
      severity: "error",
      summary: "DXF load failed",
      title: "Failed to load DXF flat pattern",
      message: "network failed",
      resolution: "Try reloading the page. If the problem persists, rebuild the CAD assets for this entry.",
      command: ""
    }
  );

  assert.deepEqual(
    buildViewerDxfAlert("flat/panel.dxf", true, "", "bad bend"),
    {
      severity: "warning",
      summary: "DXF 3D preview unavailable",
      title: "Failed to build the DXF 3D preview",
      message: "bad bend",
      resolution: "The flat pattern can still be shown, but the 3D extrusion preview could not be built from the current DXF geometry.",
      command: ""
    }
  );

  assert.equal(buildViewerDxfAlert("flat/panel.dxf", true, "", ""), null);
});

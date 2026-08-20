import assert from "node:assert/strict";
import test from "node:test";
import {
  buildCadCommand,
  buildViewerMeshAlert
} from "./viewerAlerts.js";
import { RENDER_FORMAT } from "cadjs/lib/fileFormats.js";
import { rebuildCommandForEntry } from "cadjs/lib/renderCapabilities.js";

test("buildCadCommand returns portable rebuild commands for generated CAD assets", () => {
  assert.equal(
    buildCadCommand("fun/part.step", { file: "fun/part.step", kind: "step" }),
    rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/part.step")
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
      command: rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/part.step")
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
      command: rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/stale.step")
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/renderable-stale.step",
      kind: "part",
      url: "/models/step/parts/.renderable-stale.step.glb?v=hash",
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
      command: rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/renderable-stale.step")
    }
  );

  assert.deepEqual(
    buildViewerMeshAlert({
      file: "fun/renderable-stale.step",
      kind: "part",
      url: "/models/step/parts/.renderable-stale.step.glb?v=hash",
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
      command: rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/renderable-stale.step")
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
      command: rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/missing.step")
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
      command: rebuildCommandForEntry(RENDER_FORMAT.STEP, "fun/missing.step")
    }
  );
});

test("a DXF entry reports through the ordinary mesh alert", () => {
  // DXF has no alert builder of its own any more. Its geometry is a baked package GLB, so a
  // missing or failed one is exactly a missing mesh, and buildViewerMeshAlert already names
  // the DXF rebuild command for it.
  const entry = { file: "flat/panel.dxf", kind: "dxf" };
  assert.equal(buildViewerMeshAlert(entry, true, ""), null);
  assert.deepEqual(
    buildViewerMeshAlert(entry, false, "network failed"),
    {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: "network failed",
      resolution: "Try reloading the page. If the problem persists, rebuild the render assets for this entry.",
      command: ""
    }
  );
});


test("a failed artifact build reports its own reason, not \"no mesh data\"", () => {
  // The generic card told the user only that nothing loaded. The reason -- which entity the
  // DXF builder rejected -- was already on the artifact record and simply never shown, so a
  // drawing that can never render looked identical to one needing a rebuild.
  const entry = { file: "drawings/plate.dxf", kind: "dxf" };
  const artifact = { status: "error", error: "dxf-artifact.mjs failed (exit 1): Unsupported DXF entity HATCH" };

  const alert = buildViewerMeshAlert(entry, false, "", artifact);

  assert.equal(alert.severity, "error");
  assert.equal(alert.title, "Render artifact build failed");
  assert.match(alert.message, /Unsupported DXF entity HATCH/);
});

test("an artifact error is not raised once a mesh is in hand", () => {
  // A stale error alongside a rendered mesh would be noise: the entry is on screen.
  const entry = { file: "drawings/plate.dxf", kind: "dxf" };
  const artifact = { status: "error", error: "boom" };

  assert.equal(buildViewerMeshAlert(entry, true, "", artifact), null);
});

test("an artifact error falls back to a message when the record carries none", () => {
  const entry = { file: "drawings/plate.dxf", kind: "dxf" };

  const alert = buildViewerMeshAlert(entry, false, "", { status: "error", error: "" });

  assert.equal(alert.title, "Render artifact build failed");
  assert.ok(alert.message.length > 0);
});

test("a drawing with no mesh is not an error, but a failed build still is", () => {
  // A dimensioned drawing encloses nothing to extrude, so it bakes no mesh BY DESIGN. Reporting
  // "no mesh data is available" told the user to rebuild assets that were already complete.
  const drawing = { file: "plans/panel.dxf.py", kind: "dxf", drawingProfile: "drawing" };
  assert.equal(buildViewerMeshAlert(drawing, false, ""), null);
  // A cut layout with no mesh is still a real problem.
  const layout = { file: "parts/bracket.dxf.py", kind: "dxf", drawingProfile: "cut" };
  assert.equal(buildViewerMeshAlert(layout, false, "")?.summary, "Mesh unavailable");
  // And a drawing whose BUILD failed reports the build failure, which outranks the mesh card.
  const failed = buildViewerMeshAlert(drawing, false, "", { status: "error", error: "bad entity" });
  assert.equal(failed?.summary, "Build failed");
  assert.match(failed?.message, /bad entity/u);
});

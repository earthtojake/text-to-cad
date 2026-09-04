import assert from "node:assert/strict";
import test from "node:test";
import {
  buildViewerMeshAlert
} from "./viewerAlerts.js";

test("buildViewerMeshAlert reports missing sidecar meshes", () => {
  assert.deepEqual(
    buildViewerMeshAlert({ file: "meshes/part.stl", kind: "stl" }, false, ""),
    {
      severity: "error",
      summary: "Mesh unavailable",
      title: "No mesh data is available",
      message: "The selected entry is listed in the CAD catalog but no renderable mesh data could be loaded for it."
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
      message: "Generated GLB metadata is missing its source path."
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
        error: "missing_glb",
        message: "STEP artifact is missing."
      }
    }, false, ""),
    {
      severity: "error",
      compact: true,
      summary: "STEP artifact missing",
      title: "STEP artifact missing",
      message: "Generated GLB is missing."
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
        error: "missing_glb",
        message: "STEP artifact is missing."
      }
    }, false, ""),
    {
      severity: "warning",
      blocking: false,
      compact: true,
      summary: "STEP artifact missing",
      title: "STEP artifact missing",
      message: "Generated GLB is missing."
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
        error: "missing_glb",
        message: "STEP artifact is missing."
      }
    }, false, "GLB parser failed"),
    {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: "GLB parser failed"
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
      message: "Generated GLB is missing."
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
      message: "Generated GLB is missing."
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
      message: "network failed"
    }
  );
});


test("a failed compile reports its own reason, not \"no mesh data\"", () => {
  // The generic card told the user only that nothing loaded. The reason -- which entity the
  // DXF builder rejected -- was already on the artifact record and simply never shown, so a
  // drawing that can never render looked identical to one needing a rebuild.
  const entry = { file: "drawings/plate.dxf", kind: "dxf" };
  const artifact = { status: "failed", error: "dxf-artifact.mjs failed (exit 1): Unsupported DXF entity HATCH" };

  const alert = buildViewerMeshAlert(entry, false, "", artifact);

  assert.equal(alert.severity, "error");
  assert.equal(alert.title, "Compile failed");
  assert.match(alert.message, /Unsupported DXF entity HATCH/);
});

test("an artifact error is not raised once a mesh is in hand", () => {
  // A stale error alongside a rendered mesh would be noise: the entry is on screen.
  const entry = { file: "drawings/plate.dxf", kind: "dxf" };
  const artifact = { status: "failed", error: "boom" };

  assert.equal(buildViewerMeshAlert(entry, true, "", artifact), null);
});

test("a failed compile with no reason still says it could not be compiled", () => {
  const entry = { file: "drawings/plate.dxf", kind: "dxf" };

  const alert = buildViewerMeshAlert(entry, false, "", { status: "failed", error: "" });

  assert.equal(alert.title, "Compile failed");
  assert.ok(alert.message.length > 0);
});

test("a meshless DXF is not an error, but a failed build still is", () => {
  // A dimensioned drawing encloses nothing to extrude, so it has no mesh BY DESIGN — and the
  // profile is decided from the PARSED file now, which this alert path cannot see, so every
  // meshless DXF stays quiet: a layout's mesh comes from the same parse, and a genuinely
  // broken file reports through loadError.
  const drawing = { file: "plans/panel.dxf.py", kind: "dxf" };
  assert.equal(buildViewerMeshAlert(drawing, false, ""), null);
  const layout = { file: "parts/bracket.dxf.py", kind: "dxf" };
  assert.equal(buildViewerMeshAlert(layout, false, ""), null);
  // A parse/load failure still reports.
  assert.equal(buildViewerMeshAlert(layout, false, "bad DXF")?.summary, "Mesh load failed");
  // And a drawing whose BUILD failed reports the build failure, which outranks the mesh card.
  const failed = buildViewerMeshAlert(drawing, false, "", { status: "failed", error: "bad entity" });
  assert.equal(failed?.summary, "Compile failed");
  assert.match(failed?.message, /bad entity/u);
});

test("buildViewerMeshAlert puts a failed compile's own reason under a plain title", () => {
  assert.deepEqual(
    buildViewerMeshAlert(
      { file: "STEP/moonwatch.step", kind: "part" },
      false,
      "",
      { status: "failed", error: "component be20a9eae6b94690 build failed: Unextractable: surface domain does not cover face UV" }
    ),
    {
      severity: "error",
      summary: "Compile failed",
      title: "Compile failed",
      message: "component be20a9eae6b94690 build failed: Unextractable: surface domain does not cover face UV"
    }
  );
  assert.deepEqual(
    buildViewerMeshAlert({ file: "STEP/moonwatch.step", kind: "part" }, false, "", { status: "failed", error: "" }),
    {
      severity: "error",
      summary: "Compile failed",
      title: "Compile failed",
      message: "The document could not be compiled."
    }
  );
});

import assert from "node:assert/strict";
import test from "node:test";
import {
  buildViewerEditAlert,
  buildViewerMeshAlert,
} from "./viewerAlerts.js";

const step = { file: "STEP/moonwatch.step", kind: "part" };

test("connection failure explains recovery without blaming the compiler", () => {
  const alert = buildViewerMeshAlert(step, false, "", {
    status: "failed", error: "Failed to fetch",
    failure: { kind: "network", method: "GET", operation: "checking display assets", url: "/__cad/artifact?file=STEP%2Fmoonwatch.step" }
  });
  assert.equal(alert.summary, "Connection lost");
  assert.match(alert.title, /reach the viewer/);
  assert.match(alert.message, /checking display assets.*moonwatch.step/);
  assert.match(alert.message, /viewer is running/);
  assert.match(alert.details, /Request: GET/);
  assert.equal(alert.reload, true);
});

test("disconnected POST warns that the build may still be running", () => {
  const alert = buildViewerMeshAlert(step, false, "", {
    status: "failed", error: "Load failed", failure: { kind: "network", method: "POST" }
  });
  assert.match(alert.recovery, /may still be running/);
  assert.doesNotMatch(alert.title, /compil/i);
});

test("worker-unavailable HTTP errors identify the service and retain diagnostics", () => {
  const alert = buildViewerMeshAlert(step, false, "", {
    status: "failed", error: "Worker unavailable", failure: { kind: "http", status: 503 }
  });
  assert.equal(alert.summary, "Viewer service failed");
  assert.equal(alert.title, "Couldn’t prepare the model");
  assert.equal(alert.reason, undefined);
  assert.match(alert.details, /HTTP status: 503/);
  assert.match(alert.details, /Worker unavailable/);
});

test("compile failure preserves the full diagnostic, context and useful recovery", () => {
  const reason = "Unsupported DXF entity HATCH\n" + "compiler diagnostic ".repeat(500).trim();
  const alert = buildViewerMeshAlert({ file: "drawings/plate.dxf", kind: "dxf" }, false, "", { status: "failed", error: reason });
  assert.equal(alert.summary, "Compile failed");
  assert.equal(alert.reason, reason);
  assert.ok(alert.details.endsWith(reason));
  assert.match(alert.message, /plate.dxf/);
  assert.match(alert.recovery, /terminal output/);
  assert.match(alert.recovery, /rebuild/);
});

test("missing compiler diagnostic is stated honestly", () => {
  const alert = buildViewerMeshAlert(step, false, "", { status: "failed", error: "" });
  assert.match(alert.reason, /No diagnostic was returned/);
  assert.match(alert.recovery, /terminal output/);
});

test("a failed replacement stays actionable without blocking usable geometry", () => {
  const alert = buildViewerMeshAlert(step, true, "", { status: "failed", error: "Invalid edge loop" });
  assert.equal(alert.blocking, false);
  assert.match(alert.message, /existing model remains visible/i);
  assert.equal(alert.reason, "Invalid edge loop");
});

test("worker protocol failures identify the viewer service without blaming the source", () => {
  const diagnostic = "artifact request failed or lost its protocol; no cold retry: worker exited";
  const alert = buildViewerMeshAlert(step, false, "", { status: "failed", error: diagnostic });
  assert.equal(alert.summary, "Viewer service failed");
  assert.equal(alert.title, "Couldn’t prepare the model");
  assert.match(alert.message, /viewer (?:couldn’t finish processing|did not respond while preparing) this model/);
  assert.doesNotMatch(alert.recovery, /correct|rebuild the source/i);
  assert.equal(alert.reason, undefined);
  assert.ok(alert.details.endsWith(diagnostic));
});

test("status and timeout failures also identify the processing service", () => {
  for (const kind of ["status", "timeout"]) {
    const alert = buildViewerMeshAlert(step, false, "", {
      status: "failed",
      error: "Request did not complete",
      failure: { kind, detail: "Request did not complete" }
    });
    assert.equal(alert.summary, "Viewer service failed");
    assert.match(alert.message, /viewer (?:couldn’t finish processing|did not respond while preparing) this model/);
    assert.match(alert.details, /Request did not complete/);
  }
});

test("failed STEP artifact explains what is missing and retains a renderable fallback", () => {
  for (const [code, reason] of [["missing_glb", "Generated GLB is missing"], ["missing_step_topology", "missing STEP topology metadata"]]) {
    const entry = { ...step, artifact: { ok: false, error: code, message: "Original diagnostic" } };
    const alert = buildViewerMeshAlert(entry, false, "");
    assert.equal(alert.severity, "error");
    assert.ok(alert.message.includes(reason));
    assert.match(alert.details, /Original diagnostic/);
    assert.equal(buildViewerMeshAlert(entry, true, ""), null);
    const fallback = { ...entry, url: "/models/.part.step.glb", hash: "glb-hash" };
    const warning = buildViewerMeshAlert(fallback, false, "");
    assert.equal(warning.severity, "warning");
    assert.equal(warning.blocking, false);
    const failedFallback = buildViewerMeshAlert(fallback, false, "GLB parser failed");
    assert.equal(failedFallback.summary, "Mesh load failed");
    assert.match(failedFallback.reason, /GLB parser failed/);
  }
});

test("mesh errors also recognize browser transport messages", () => {
  for (const kind of ["stl", "3mf", "glb", "dxf"]) {
    const entry = { file: `parts/panel.${kind}`, kind };
    const alert = buildViewerMeshAlert(entry, false, "Failed to fetch");
    assert.equal(alert.summary, "Connection lost");
    assert.match(alert.message, /loading geometry/);
    assert.equal(buildViewerMeshAlert(entry, false, "Invalid file header").reason, "Invalid file header");
  }
});

test("missing geometry gives file context and a next step", () => {
  const alert = buildViewerMeshAlert({ file: "meshes/part.stl", kind: "stl" }, false, "");
  assert.equal(alert.summary, "Mesh unavailable");
  assert.match(alert.message, /meshes\/part.stl/);
  assert.match(alert.recovery, /saved completely/);
  // Nothing loaded and nothing raised is "no geometry", for every file this renderer opens.
  assert.equal(buildViewerMeshAlert({ file: "plans/panel.step", kind: "step" }, false, "").summary, "Mesh unavailable");
  assert.equal(buildViewerMeshAlert(null, false, "failure"), null);
});

test("edit alerts keep disconnects and healthy preview expiry quiet", () => {
  assert.equal(buildViewerEditAlert({ state: "disconnected", error: "Connection closed" }, false, false), null);
  assert.equal(buildViewerEditAlert({
    state: "done",
    error: "Preview geometry is no longer available in the cache",
    previewUnavailable: true,
    saved: { tree: "saved" }
  }, false, true), null);

  const blocked = buildViewerEditAlert({
    state: "done",
    error: "Preview geometry is no longer available in the cache",
    previewUnavailable: true
  }, false, false);
  assert.equal(blocked.summary, "Open failed");
  assert.equal(blocked.blocking, undefined);
});

test("a failed save explains that the updated model is visible and keeps the diagnostic", () => {
  const alert = buildViewerEditAlert({
    state: "failed",
    error: "Disk full\nwrite trace",
    file: "STEP/moonwatch.step",
    revision: 8
  }, true, true);
  assert.equal(alert.summary, "Update failed");
  assert.equal(alert.message, "The updated model is visible, but the STEP file could not be written.");
  assert.equal(alert.title, "Couldn’t write the STEP file");
  assert.equal(alert.blocking, false);
  assert.equal(alert.reason, "Disk full\nwrite trace");
  assert.match(alert.details, /Revision: 8/);
});

test("edit worker failures are distinct from invalid-model failures", () => {
  const worker = buildViewerEditAlert({
    state: "failed",
    error: "artifact request failed or lost its protocol; no cold retry"
  }, false, true);
  assert.equal(worker.summary, "Viewer service failed");
  assert.equal(worker.kind, "service");
  assert.equal(worker.blocking, false);
  assert.equal(worker.reason, undefined);
  assert.match(worker.details, /no cold retry/);

  const invalid = buildViewerEditAlert({ state: "failed", error: "Fillet radius is too large" }, false, false);
  assert.equal(invalid.summary, "Open failed");
  assert.match(invalid.recovery, /correct the model/i);
  assert.equal(invalid.reason, "Fillet radius is too large");
});

test("progressive geometry is valid while loading but cannot mask a failed first load", () => {
  assert.equal(buildViewerMeshAlert(step, true, "", null, { partial: true }), null);
  const failed = buildViewerMeshAlert(step, true, "Decode failed", null, { partial: true });
  assert.notEqual(failed.blocking, false);
  assert.equal(failed.severity, "error");
  assert.doesNotMatch(failed.message, /existing model remains visible/);
});

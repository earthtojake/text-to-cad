import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPLICIT_EXPORT_FORMATS,
  STEP_EXPORT_FORMATS,
  isImportedStepEntry,
  exportItemLabel,
  requestModelExport,
} from "./modelExport.js";

test("STEP export formats are the four supported kinds", () => {
  assert.deepEqual([...STEP_EXPORT_FORMATS].sort(), ["3mf", "glb", "step", "stl"]);
});

test("isImportedStepEntry is false for a generator-backed entry, true for an imported one", () => {
  assert.equal(isImportedStepEntry({ source: { sourcePath: "/m/tom.step.py" } }), false);
  assert.equal(isImportedStepEntry({ source: null }), true);
  assert.equal(isImportedStepEntry({}), true);
});

test("exportItemLabel: a native format is a download, everything else is an export", () => {
  assert.equal(exportItemLabel("step"), "Download STEP");
  assert.equal(exportItemLabel("dxf"), "Download DXF");
  assert.equal(exportItemLabel("3mf"), "Export 3MF");
  assert.equal(exportItemLabel("stl"), "Export STL");
  assert.equal(exportItemLabel("glb"), "Export GLB");
});

test("an implicit model exports to mesh formats only", () => {
  // There is no "Download IMPLICIT": the .implicit.js source IS the native file, and the
  // mesh comes from the server-side export CLI rather than from the baked render package.
  assert.deepEqual([...IMPLICIT_EXPORT_FORMATS].sort(), ["3mf", "glb", "stl"]);
});

test("requestModelExport preserves an absolute file ref (leading slash kept)", async () => {
  // Regression: catalog entry.file refs are absolute; stripping the leading "/" made the
  // server resolve a bogus relative path → "STEP file not found".
  const absolute = "/Users/me/models/mech/widget.step";
  let capturedUrl = "";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    capturedUrl = String(url);
    return {
      ok: true,
      json: async () => ({ ok: true, path: "/dest/widget.glb", filename: "widget.glb", format: "glb" }),
    };
  };
  try {
    const result = await requestModelExport({ file: absolute, format: "glb" });
    assert.equal(result.ok, true);
    assert.ok(capturedUrl.includes(encodeURIComponent(absolute)), `absolute ref not preserved: ${capturedUrl}`);
    assert.ok(capturedUrl.startsWith("/__cad/export?"), `unexpected route: ${capturedUrl}`);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("requestModelExport surfaces a cancelled dialog without throwing", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ ok: false, cancelled: true }) });
  try {
    const result = await requestModelExport({ file: "/m/x.step", format: "stl" });
    assert.deepEqual(result, { cancelled: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

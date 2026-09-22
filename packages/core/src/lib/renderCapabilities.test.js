import assert from "node:assert/strict";
import test from "node:test";

import { RENDER_FORMAT } from "./fileFormats.js";
import {
  ASSET_KIND,
  PARAMETER_SOURCE,
  RENDER_CAPABILITIES,
  assetKindForRenderFormat,
  hasCapability,
  isArtifactManagedFormat,
  renderCapabilities,
  renderFormatLabel,
  supportsTool
} from "./renderCapabilities.js";

// Every format drawn in a 3D viewport. DXF is the one that is not: its pane is a 2D
// canvas with no scene and no toolbar, so the viewport rules below do not reach it.
const VIEWPORT_FORMATS = Object.values(RENDER_FORMAT).filter(
  (format) => format !== RENDER_FORMAT.DXF
);

test("every render format has a capability row", () => {
  for (const format of Object.values(RENDER_FORMAT)) {
    assert.ok(RENDER_CAPABILITIES[format], `missing capability row for ${format}`);
  }
});

test("rows are complete: no format is missing a field another format declares", () => {
  // A half-filled row is the bug this table exists to prevent — a format silently
  // opting out of a capability by omission rather than by declaring false.
  const fields = new Set();
  for (const row of Object.values(RENDER_CAPABILITIES)) {
    Object.keys(row).forEach((key) => fields.add(key));
  }
  for (const [format, row] of Object.entries(RENDER_CAPABILITIES)) {
    for (const field of fields) {
      assert.ok(field in row, `${format} is missing capability "${field}"`);
    }
  }
});

test("every row declares the same tool set", () => {
  const tools = new Set();
  for (const row of Object.values(RENDER_CAPABILITIES)) {
    Object.keys(row.tools).forEach((tool) => tools.add(tool));
  }
  for (const [format, row] of Object.entries(RENDER_CAPABILITIES)) {
    for (const tool of tools) {
      assert.equal(typeof row.tools[tool], "boolean", `${format} tool "${tool}" is not a boolean`);
    }
  }
});

test("asset kinds are known", () => {
  const kinds = new Set(Object.values(ASSET_KIND));
  for (const [format, row] of Object.entries(RENDER_CAPABILITIES)) {
    assert.ok(kinds.has(row.assetKind), `${format} has unknown asset kind ${row.assetKind}`);
  }
  assert.equal(assetKindForRenderFormat(RENDER_FORMAT.STL), ASSET_KIND.MESH);
  assert.equal(assetKindForRenderFormat(RENDER_FORMAT.URDF), ASSET_KIND.ROBOT);
  // A drawing is not a mesh and never was one: a DXF loads the backend's 2D payload.
  assert.equal(assetKindForRenderFormat(RENDER_FORMAT.DXF), ASSET_KIND.DRAWING);
});

test("orbit and screenshot are available to every format with a viewport", () => {
  // These act on the viewport, not the geometry. Gating them per format is what
  // produced the same dead-button bug for two formats independently. DXF is not an
  // exception to that rule, it is outside it: a drawing has no viewport to act on.
  for (const format of VIEWPORT_FORMATS) {
    assert.equal(supportsTool(format, "orbit"), true, `${format} lost orbit`);
    assert.equal(supportsTool(format, "screenshot"), true, `${format} lost screenshot`);
  }
});

test("topology capabilities imply part capabilities", () => {
  // Face/edge/vertex references live on parts; a format claiming topology without parts
  // would wire selection to nothing.
  for (const [format, row] of Object.entries(RENDER_CAPABILITIES)) {
    if (row.topology) {
      assert.equal(row.parts, true, `${format} claims topology without parts`);
    }
  }
});

test("STEP keeps the full capability set", () => {
  const step = renderCapabilities(RENDER_FORMAT.STEP);
  assert.equal(step.parts, true);
  assert.equal(step.topology, true);
  assert.equal(step.exploded, true);
  assert.equal(step.displayModes, true);
  assert.equal(step.clip, true);
  assert.equal(step.params, PARAMETER_SOURCE.SIDECAR);
  assert.equal(step.artifactManaged, true);
});

test("a plain mesh is the minimal row", () => {
  for (const format of [RENDER_FORMAT.STL, RENDER_FORMAT.THREE_MF, RENDER_FORMAT.GLB]) {
    const row = renderCapabilities(format);
    assert.equal(row.parts, false);
    assert.equal(row.topology, false);
    assert.equal(row.measure, false);
    assert.equal(row.params, null);
    assert.equal(row.artifactManaged, false);
  }
});

test("Measure is a STEP tool", () => {
  // It snaps to B-rep faces, edges and vertices. A mesh offers only triangle corners,
  // which measured little anyone wanted, so no other format has the tool.
  for (const format of Object.values(RENDER_FORMAT)) {
    assert.equal(hasCapability(format, "measure"), format === RENDER_FORMAT.STEP, format);
  }
  assert.equal(hasCapability(RENDER_FORMAT.STEP, "measure"), true);
  assert.equal(hasCapability(RENDER_FORMAT.URDF, "measure"), false);
  assert.equal(hasCapability(RENDER_FORMAT.DXF, "measure"), false);
});

test("STEP is the only artifact-managed format", () => {
  // A SUBSET of owns_entry in cadgen/viewer/artifact.py: a format listed here that the
  // server does not own blocks forever, so a format the viewer renders from its own file
  // belongs out. A DXF is one of those — `owns_dxf_path` always answers False, and the
  // renderer parses the file itself.
  const managed = Object.values(RENDER_FORMAT).filter((format) => isArtifactManagedFormat(format));
  assert.deepEqual(managed, [RENDER_FORMAT.STEP]);
});

test("every viewport format gets the whole toolbar: the tools act on the viewport, not the geometry", () => {
  // Select and draw were off for plain meshes and for robots, so opening an STL lost
  // buttons that have nothing to do with what the file contains. Select is inert
  // without `topology` — it stays visible so the toolbar keeps one shape.
  for (const format of VIEWPORT_FORMATS) {
    for (const tool of ["select", "draw", "orbit", "screenshot"]) {
      assert.equal(supportsTool(format, tool), true, `${format} is missing the ${tool} tool`);
    }
  }
  // ...and the one format that is not a viewport claims none of them, rather than
  // advertising four buttons its pane does not have.
  for (const tool of ["select", "draw", "orbit", "screenshot"]) {
    assert.equal(supportsTool(RENDER_FORMAT.DXF, tool), false, `DXF still claims ${tool}`);
  }
  // An unrecognised format still gets the viewport tools: they cannot misbehave without
  // geometry-level capabilities behind them.
  assert.equal(supportsTool("totally-unknown", "draw"), true);
});

test("projection is a theme trait for every format", () => {
  for (const format of Object.values(RENDER_FORMAT)) {
    assert.equal(hasCapability(format, "themeProjection"), true, `${format} ignores the theme projection`);
  }
});

test("no format advertises export capabilities: the CLIs own exporting", () => {
  for (const format of Object.values(RENDER_FORMAT)) {
    const row = renderCapabilities(format);
    assert.equal("exportFormats" in row, false, `${format} still advertises exportFormats`);
    assert.equal("clientMeshExport" in row, false, `${format} still advertises clientMeshExport`);
  }
});

test("labels are present for the formats that surface one", () => {
  assert.equal(renderFormatLabel(RENDER_FORMAT.THREE_MF), "3MF");
  assert.equal(renderFormatLabel(RENDER_FORMAT.GLB), "GLB");
  assert.equal(renderFormatLabel(RENDER_FORMAT.STL), "STL");
});

test("aliases resolve to their real format", () => {
  assert.equal(renderCapabilities("stp").sheetKind, RENDER_FORMAT.STEP);
  assert.equal(renderCapabilities("gltf").iconKind, renderCapabilities(RENDER_FORMAT.GLB).iconKind);
  assert.equal(renderCapabilities("  STEP  ").parts, true);
});

test("unknown formats fall back to the conservative row instead of throwing", () => {
  const row = renderCapabilities("totally-unknown");
  assert.equal(row.parts, false);
  assert.equal(row.topology, false);
  assert.equal(hasCapability("", "parts"), false);
});

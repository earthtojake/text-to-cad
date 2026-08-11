import assert from "node:assert/strict";
import test from "node:test";

import { RENDER_FORMAT } from "./fileFormats.js";
import {
  PARAMETER_SOURCE,
  RENDER_CAPABILITIES,
  VIEWPORT_CONTENT,
  exportFormatsForRenderFormat,
  hasCapability,
  isArtifactManagedFormat,
  renderCapabilities,
  renderFormatLabel,
  supportsTool,
  viewportContentKind
} from "./renderCapabilities.js";

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

test("viewport content kinds are known", () => {
  const kinds = new Set(Object.values(VIEWPORT_CONTENT));
  for (const [format, row] of Object.entries(RENDER_CAPABILITIES)) {
    assert.ok(kinds.has(row.content), `${format} has unknown content kind ${row.content}`);
  }
  assert.equal(viewportContentKind(RENDER_FORMAT.IMPLICIT), VIEWPORT_CONTENT.IMPLICIT);
  assert.equal(viewportContentKind(RENDER_FORMAT.STL), VIEWPORT_CONTENT.MESH);
  assert.equal(viewportContentKind(RENDER_FORMAT.URDF), VIEWPORT_CONTENT.ROBOT);
});

test("orbit and screenshot are available to every format", () => {
  // These act on the viewport, not the geometry. Gating them per format is what
  // produced the same dead-button bug for implicit and DXF independently.
  for (const format of Object.values(RENDER_FORMAT)) {
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
    assert.equal(row.params, null);
    assert.equal(row.artifactManaged, false);
  }
});

test("implicit renders live: parameters from its module, never artifact-managed", () => {
  const implicit = renderCapabilities(RENDER_FORMAT.IMPLICIT);
  assert.equal(implicit.params, PARAMETER_SOURCE.MODULE);
  assert.equal(implicit.animations, true);
  assert.equal(implicit.artifactManaged, false);
  assert.deepEqual([...implicit.exportFormats], ["stl", "glb", "3mf"]);
});

test("artifact-managed formats are exactly STEP and DXF", () => {
  // A SUBSET of owns_entry in viewer/server_py/artifact.py, which also owns implicit
  // entries — the server builds implicit packages for export and snapshot, but the viewer
  // raymarches the model live and must never wait on that build. A format listed here that
  // the server does not own blocks forever; implicit is the reverse case and belongs out.
  const managed = Object.values(RENDER_FORMAT).filter((format) => isArtifactManagedFormat(format));
  assert.deepEqual(managed.sort(), [RENDER_FORMAT.DXF, RENDER_FORMAT.STEP].sort());
});

test("every format gets the whole toolbar: the tools act on the viewport, not the geometry", () => {
  // Select, pan and draw were off for plain meshes and for robots, so opening an STL lost
  // three buttons that have nothing to do with what the file contains. Select is inert
  // without `topology` — it stays visible so the toolbar keeps one shape.
  for (const format of Object.values(RENDER_FORMAT)) {
    for (const tool of ["select", "pan", "draw", "orbit", "screenshot"]) {
      assert.equal(supportsTool(format, tool), true, `${format} is missing the ${tool} tool`);
    }
  }
  // An unrecognised format still gets the viewport tools: they cannot misbehave without
  // geometry-level capabilities behind them.
  assert.equal(supportsTool("totally-unknown", "pan"), true);
});

test("only DXF offers the plan view today", () => {
  const planView = Object.values(RENDER_FORMAT).filter((format) => hasCapability(format, "planView"));
  assert.deepEqual(planView, [RENDER_FORMAT.DXF]);
});

test("projection is a theme trait for every format", () => {
  for (const format of Object.values(RENDER_FORMAT)) {
    assert.equal(hasCapability(format, "themeProjection"), true, `${format} ignores the theme projection`);
  }
});

test("export formats match the routes the server implements", () => {
  assert.deepEqual([...exportFormatsForRenderFormat(RENDER_FORMAT.STEP)], ["step", "3mf", "stl", "glb"]);
  assert.deepEqual([...exportFormatsForRenderFormat(RENDER_FORMAT.DXF)], ["dxf"]);
  assert.deepEqual([...exportFormatsForRenderFormat(RENDER_FORMAT.STL)], []);
});

test("labels are present for the formats that surface one", () => {
  assert.equal(renderFormatLabel(RENDER_FORMAT.THREE_MF), "3MF");
  assert.equal(renderFormatLabel(RENDER_FORMAT.GLB), "GLB");
  assert.equal(renderFormatLabel(RENDER_FORMAT.STL), "STL");
});

test("aliases resolve to their real format", () => {
  assert.equal(renderCapabilities("stp").sheetKind, RENDER_FORMAT.STEP);
  assert.equal(renderCapabilities("gltf").content, VIEWPORT_CONTENT.MESH);
  assert.equal(renderCapabilities("  STEP  ").parts, true);
});

test("unknown formats fall back to the conservative row instead of throwing", () => {
  const row = renderCapabilities("totally-unknown");
  assert.equal(row.parts, false);
  assert.equal(row.topology, false);
  assert.equal(hasCapability("", "parts"), false);
});

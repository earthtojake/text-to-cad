import assert from "node:assert/strict";
import test from "node:test";

import { RENDER_FORMAT } from "./fileFormats.js";
import { ENTRY_ICON_KIND, RENDER_CAPABILITIES, entryIconKindForRenderFormat, renderCapabilities } from "./renderCapabilities.js";

test("every render format has a capability row, and every row the same columns", () => {
  const fields = new Set(Object.values(RENDER_CAPABILITIES).flatMap((row) => Object.keys(row)));
  for (const format of Object.values(RENDER_FORMAT)) {
    const row = RENDER_CAPABILITIES[format];
    assert.ok(row, `missing capability row for ${format}`);
    for (const field of fields) assert.ok(field in row, `${format} is missing capability "${field}"`);
  }
});

test("each format's file-list glyph comes from its row", () => {
  const kinds = new Set(Object.values(ENTRY_ICON_KIND));
  for (const [format, row] of Object.entries(RENDER_CAPABILITIES)) {
    assert.ok(kinds.has(row.iconKind), `${format} has unknown icon kind ${row.iconKind}`);
  }
  assert.equal(entryIconKindForRenderFormat(RENDER_FORMAT.XBF), ENTRY_ICON_KIND.STEP, "a STEP opens as an engine document");
  assert.equal(entryIconKindForRenderFormat(RENDER_FORMAT.SRDF), ENTRY_ICON_KIND.ROBOT);
});

test("aliases resolve to their real format", () => {
  assert.equal(renderCapabilities("stp"), renderCapabilities(RENDER_FORMAT.STEP));
  assert.equal(renderCapabilities("gltf").iconKind, renderCapabilities(RENDER_FORMAT.GLB).iconKind);
  assert.equal(renderCapabilities("  STL  ").iconKind, ENTRY_ICON_KIND.STL_MESH);
});

test("unknown formats fall back to the default row instead of throwing", () => {
  assert.equal(renderCapabilities("totally-unknown").iconKind, ENTRY_ICON_KIND.STEP);
  assert.equal(renderCapabilities("").iconKind, ENTRY_ICON_KIND.STEP);
});

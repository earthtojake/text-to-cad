import assert from "node:assert/strict";
import test from "node:test";

import {
  entrySourceFormat,
  fileExtensionFromPath,
  isCadFile,
  isMeshRenderFormat,
  isPlotRenderFormat,
  meshAssetKeyForEntry,
  normalizeRenderFormat,
  renderFormatFromPath,
  RENDER_FORMAT
} from "./fileFormats.js";

test("entrySourceFormat maps manifest kinds to stable render formats", () => {
  assert.equal(entrySourceFormat({ kind: "part" }), RENDER_FORMAT.STEP);
  assert.equal(entrySourceFormat({ kind: "assembly" }), RENDER_FORMAT.STEP);
  assert.equal(entrySourceFormat({ kind: "dxf" }), RENDER_FORMAT.DXF);
  assert.equal(entrySourceFormat({ kind: "stl" }), RENDER_FORMAT.STL);
  assert.equal(entrySourceFormat({ kind: "3mf" }), RENDER_FORMAT.THREE_MF);
  assert.equal(entrySourceFormat({ kind: "glb" }), RENDER_FORMAT.GLB);
  assert.equal(entrySourceFormat({ kind: "gltf" }), RENDER_FORMAT.GLB);
  assert.equal(entrySourceFormat({ kind: "urdf" }), RENDER_FORMAT.URDF);
  assert.equal(entrySourceFormat({ kind: "srdf" }), RENDER_FORMAT.SRDF);
  assert.equal(entrySourceFormat({ kind: "sdf" }), RENDER_FORMAT.SDF);
  assert.equal(entrySourceFormat({ kind: "kicad_pcb" }), RENDER_FORMAT.KICAD_PCB);
  assert.equal(entrySourceFormat({ kind: "kicad_sch" }), RENDER_FORMAT.KICAD_SCH);
  assert.equal(entrySourceFormat({ kind: "harness" }), RENDER_FORMAT.HARNESS);
});

test("a KiCad board and schematic are plots: CAD files with their own asset, not meshes", () => {
  for (const [path, format] of [["boards/blinky.kicad_pcb", RENDER_FORMAT.KICAD_PCB], ["blinky.KICAD_SCH", RENDER_FORMAT.KICAD_SCH]]) {
    assert.equal(renderFormatFromPath(path), format, path);
    assert.equal(isCadFile(path), true, path);
    assert.equal(isPlotRenderFormat(format), true, format);
    assert.equal(isMeshRenderFormat(format), false, format);
    assert.equal(normalizeRenderFormat(format), format);
    assert.equal(meshAssetKeyForEntry({ kind: format }), format);
  }
  // A project file is not one: only the board and the schematic are drawn.
  assert.equal(renderFormatFromPath("blinky.kicad_pro"), "");
  assert.equal(isPlotRenderFormat(RENDER_FORMAT.DXF), false);
});

test("a wiring harness is its two suffixes together; a plain .yml is no CAD file", () => {
  for (const path of ["harness/cable.harness.yml", "CABLE.HARNESS.YML", "https://example.test/w/cable.harness.yml?download=1#top"]) {
    assert.equal(renderFormatFromPath(path), RENDER_FORMAT.HARNESS, path);
    assert.equal(isCadFile(path), true, path);
  }
  assert.equal(fileExtensionFromPath("w/cable.harness.yml?v=2"), ".harness.yml");
  assert.equal(isPlotRenderFormat(RENDER_FORMAT.HARNESS), true);
  assert.equal(normalizeRenderFormat(RENDER_FORMAT.HARNESS), RENDER_FORMAT.HARNESS);
  assert.equal(meshAssetKeyForEntry({ kind: "harness" }), RENDER_FORMAT.HARNESS);
  // Only the pair is a harness: a plain YAML file, a hidden one with no name before the pair,
  // and a name that merely contains it are not.
  for (const path of ["config.yml", "w/.harness.yml", "cable.harness.yml.bak", "cable.harness"]) {
    assert.equal(renderFormatFromPath(path), "", path);
  }
  assert.equal(fileExtensionFromPath("config.yml"), ".yml");
});

test("the mesh format predicate stays narrow", () => {
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.STL), true);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.THREE_MF), true);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.GLB), true);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.STEP), false);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.URDF), false);
});

test("normalizeRenderFormat preserves tab-state format aliases and defaults", () => {
  assert.equal(normalizeRenderFormat("stp"), RENDER_FORMAT.STEP);
  assert.equal(normalizeRenderFormat("gltf"), RENDER_FORMAT.GLB);
  assert.equal(normalizeRenderFormat("srdf"), RENDER_FORMAT.SRDF);
  assert.equal(normalizeRenderFormat("3mf"), RENDER_FORMAT.THREE_MF);
  assert.equal(normalizeRenderFormat("unknown"), RENDER_FORMAT.STEP);
  assert.equal(normalizeRenderFormat("unknown", { defaultFormat: RENDER_FORMAT.DXF }), RENDER_FORMAT.DXF);
});

test("meshAssetKeyForEntry chooses native mesh keys and STEP GLB sidecars", () => {
  assert.equal(meshAssetKeyForEntry({ kind: "stl" }), "stl");
  assert.equal(meshAssetKeyForEntry({ kind: "3mf" }), "3mf");
  assert.equal(meshAssetKeyForEntry({ kind: "glb" }), "glb");
  assert.equal(meshAssetKeyForEntry({ kind: "part" }), "glb");
  assert.equal(meshAssetKeyForEntry({ kind: "assembly" }), "glb");
  assert.equal(meshAssetKeyForEntry({ kind: "dxf" }), "dxf");
});

test("every entry renders its own source format; nothing is package-baked", () => {
  // A DXF's render asset is the .dxf itself — parsed and prism-meshed in the client
  // (design/standalone-viewer.md Phase A) — and no kind is baked into a package any
  // more, so the source format IS the asset format everywhere.
  assert.equal(entrySourceFormat({ kind: "dxf" }), RENDER_FORMAT.DXF);
  assert.equal(entrySourceFormat({ kind: "part" }), RENDER_FORMAT.STEP);
  assert.equal(entrySourceFormat({ kind: "stl" }), RENDER_FORMAT.STL);
  assert.equal(entrySourceFormat({ kind: "urdf" }), RENDER_FORMAT.URDF);
});

test("file extension parsing handles URLs, queries, and supported render formats", () => {
  assert.equal(fileExtensionFromPath("/assets/bracket.step.glb?v=1"), ".glb");
  assert.equal(fileExtensionFromPath("fixtures/plate.dxf#top"), ".dxf");
  assert.equal(fileExtensionFromPath("https://example.test/robot.srdf?download=1"), ".srdf");
  assert.equal(renderFormatFromPath("/assets/bracket.stp"), RENDER_FORMAT.STEP);
  assert.equal(renderFormatFromPath("/assets/bracket.gltf"), RENDER_FORMAT.GLB);
  assert.equal(renderFormatFromPath("/assets/unknown"), "");
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  entrySourceFormat,
  fileExtensionFromPath,
  fileSheetKindForEntry,
  isMeshRenderFormat,
  isRobotRenderFormat,
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
  assert.equal(entrySourceFormat({ kind: "gcode" }), RENDER_FORMAT.GCODE);
  assert.equal(entrySourceFormat({ kind: "implicit" }), RENDER_FORMAT.IMPLICIT);
  assert.equal(entrySourceFormat({ kind: "urdf" }), RENDER_FORMAT.URDF);
  assert.equal(entrySourceFormat({ kind: "srdf" }), RENDER_FORMAT.SRDF);
  assert.equal(entrySourceFormat({ kind: "sdf" }), RENDER_FORMAT.SDF);
});

test("fileSheetKindForEntry preserves specialized sheet routing", () => {
  assert.equal(fileSheetKindForEntry({ kind: "part" }), "step");
  assert.equal(fileSheetKindForEntry({ kind: "assembly" }), "step");
  assert.equal(fileSheetKindForEntry({ kind: "stl" }), "mesh");
  assert.equal(fileSheetKindForEntry({ kind: "3mf" }), "mesh");
  assert.equal(fileSheetKindForEntry({ kind: "glb" }), "mesh");
  assert.equal(fileSheetKindForEntry({ kind: "gcode" }), "gcode");
  assert.equal(fileSheetKindForEntry({ kind: "urdf" }), "urdf");
  assert.equal(fileSheetKindForEntry({ kind: "srdf" }), "srdf");
  assert.equal(fileSheetKindForEntry({ kind: "sdf" }), "sdf");
  assert.equal(fileSheetKindForEntry({ kind: "dxf" }), "dxf");
  assert.equal(fileSheetKindForEntry({ kind: "implicit" }), "implicit");
});

test("mesh and robot format predicates stay narrow", () => {
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.STL), true);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.THREE_MF), true);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.GLB), true);
  assert.equal(isMeshRenderFormat(RENDER_FORMAT.STEP), false);
  assert.equal(isRobotRenderFormat(RENDER_FORMAT.URDF), true);
  assert.equal(isRobotRenderFormat(RENDER_FORMAT.SRDF), true);
  assert.equal(isRobotRenderFormat(RENDER_FORMAT.SDF), true);
});

test("normalizeRenderFormat preserves tab-state format aliases and defaults", () => {
  assert.equal(normalizeRenderFormat("stp"), RENDER_FORMAT.STEP);
  assert.equal(normalizeRenderFormat("gltf"), RENDER_FORMAT.GLB);
  assert.equal(normalizeRenderFormat("srdf"), RENDER_FORMAT.SRDF);
  assert.equal(normalizeRenderFormat("3mf"), RENDER_FORMAT.THREE_MF);
  assert.equal(normalizeRenderFormat("gcode"), RENDER_FORMAT.GCODE);
  assert.equal(normalizeRenderFormat("implicit"), RENDER_FORMAT.IMPLICIT);
  assert.equal(normalizeRenderFormat("unknown"), RENDER_FORMAT.STEP);
  assert.equal(normalizeRenderFormat("unknown", { defaultFormat: RENDER_FORMAT.DXF }), RENDER_FORMAT.DXF);
});

test("meshAssetKeyForEntry chooses native mesh keys and STEP GLB sidecars", () => {
  assert.equal(meshAssetKeyForEntry({ kind: "stl" }), "stl");
  assert.equal(meshAssetKeyForEntry({ kind: "3mf" }), "3mf");
  assert.equal(meshAssetKeyForEntry({ kind: "glb" }), "glb");
  assert.equal(meshAssetKeyForEntry({ kind: "part" }), "glb");
  assert.equal(meshAssetKeyForEntry({ kind: "assembly" }), "glb");
});

test("file extension parsing handles URLs, queries, and supported render formats", () => {
  assert.equal(fileExtensionFromPath("/assets/bracket.step.glb?v=1"), ".glb");
  assert.equal(fileExtensionFromPath("fixtures/plate.dxf#top"), ".dxf");
  assert.equal(fileExtensionFromPath("https://example.test/robot.srdf?download=1"), ".srdf");
  assert.equal(renderFormatFromPath("/assets/bracket.stp"), RENDER_FORMAT.STEP);
  assert.equal(renderFormatFromPath("/assets/bracket.gltf"), RENDER_FORMAT.GLB);
  assert.equal(renderFormatFromPath("/assets/toolpath.gcode?download=1"), RENDER_FORMAT.GCODE);
  assert.equal(renderFormatFromPath("/assets/orb.implicit.js?download=1"), RENDER_FORMAT.IMPLICIT);
  assert.equal(renderFormatFromPath("/assets/orb.implicit.mjs#preview"), RENDER_FORMAT.IMPLICIT);
  assert.equal(renderFormatFromPath("/assets/unknown"), "");
});

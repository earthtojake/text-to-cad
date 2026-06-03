import {
  isRobotRenderFormat,
  normalizeFormat,
  RENDER_FORMAT
} from "cadjs/lib/fileFormats.js";

export const ENTRY_ICON_KIND = Object.freeze({
  LOADING: "loading",
  ASSEMBLY: "assembly",
  DXF: "dxf",
  GCODE: "gcode",
  IMPLICIT: "implicit",
  ROBOT: "robot",
  STEP_PART: "step-part",
  STL_MESH: "stl-mesh",
  THREE_MF_MESH: "3mf-mesh",
  GLB_MESH: "glb-mesh"
});

export function entryIconKind(entry, {
  sourceFormat = "",
  status = {}
} = {}) {
  const normalizedSourceFormat = normalizeFormat(sourceFormat || entry?.kind);
  const normalizedKind = normalizeFormat(entry?.kind);
  const safeStatus = status || {};

  if (safeStatus.artifactGenerating || safeStatus.loading) {
    return ENTRY_ICON_KIND.LOADING;
  }
  if (normalizedKind === "assembly") {
    return ENTRY_ICON_KIND.ASSEMBLY;
  }
  if (normalizedSourceFormat === RENDER_FORMAT.DXF || normalizedKind === RENDER_FORMAT.DXF) {
    return ENTRY_ICON_KIND.DXF;
  }
  if (normalizedSourceFormat === RENDER_FORMAT.GCODE || normalizedKind === RENDER_FORMAT.GCODE) {
    return ENTRY_ICON_KIND.GCODE;
  }
  if (normalizedSourceFormat === RENDER_FORMAT.IMPLICIT || normalizedKind === RENDER_FORMAT.IMPLICIT) {
    return ENTRY_ICON_KIND.IMPLICIT;
  }
  if (isRobotRenderFormat(normalizedSourceFormat) || normalizedKind === "srdf") {
    return ENTRY_ICON_KIND.ROBOT;
  }
  if (normalizedSourceFormat === RENDER_FORMAT.STL || normalizedKind === RENDER_FORMAT.STL) {
    return ENTRY_ICON_KIND.STL_MESH;
  }
  if (normalizedSourceFormat === RENDER_FORMAT.THREE_MF || normalizedKind === RENDER_FORMAT.THREE_MF) {
    return ENTRY_ICON_KIND.THREE_MF_MESH;
  }
  if (normalizedSourceFormat === RENDER_FORMAT.GLB || normalizedSourceFormat === "gltf" || normalizedKind === RENDER_FORMAT.GLB || normalizedKind === "gltf") {
    return ENTRY_ICON_KIND.GLB_MESH;
  }
  return ENTRY_ICON_KIND.STEP_PART;
}

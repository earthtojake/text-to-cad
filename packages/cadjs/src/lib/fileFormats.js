export const RENDER_FORMAT = Object.freeze({
  STEP: "step",
  STL: "stl",
  THREE_MF: "3mf",
  GLB: "glb",
  GCODE: "gcode",
  DXF: "dxf",
  IMPLICIT: "implicit",
  URDF: "urdf",
  SRDF: "srdf",
  SDF: "sdf"
});

export const MESH_RENDER_FORMATS = Object.freeze([
  RENDER_FORMAT.STL,
  RENDER_FORMAT.THREE_MF,
  RENDER_FORMAT.GLB
]);

export const ROBOT_RENDER_FORMATS = Object.freeze([
  RENDER_FORMAT.URDF,
  RENDER_FORMAT.SRDF,
  RENDER_FORMAT.SDF
]);

export function normalizeFormat(value) {
  return String(value || "").trim().toLowerCase();
}

export function normalizeRenderFormat(value, { defaultFormat = RENDER_FORMAT.STEP } = {}) {
  const normalized = normalizeFormat(value || defaultFormat);
  if (normalized === "stp") {
    return RENDER_FORMAT.STEP;
  }
  if (normalized === "gltf") {
    return RENDER_FORMAT.GLB;
  }
  if (
    normalized === RENDER_FORMAT.STEP ||
    normalized === RENDER_FORMAT.STL ||
    normalized === RENDER_FORMAT.THREE_MF ||
    normalized === RENDER_FORMAT.GLB ||
    normalized === RENDER_FORMAT.GCODE ||
    normalized === RENDER_FORMAT.DXF ||
    normalized === RENDER_FORMAT.IMPLICIT ||
    normalized === RENDER_FORMAT.URDF ||
    normalized === RENDER_FORMAT.SRDF ||
    normalized === RENDER_FORMAT.SDF
  ) {
    return normalized;
  }
  return defaultFormat;
}

export function entryKind(entry) {
  return normalizeFormat(entry?.kind);
}

export function entrySourceFormat(entry) {
  const kind = entryKind(entry);
  if (kind === RENDER_FORMAT.DXF) {
    return RENDER_FORMAT.DXF;
  }
  if (kind === RENDER_FORMAT.STL) {
    return RENDER_FORMAT.STL;
  }
  if (kind === RENDER_FORMAT.THREE_MF) {
    return RENDER_FORMAT.THREE_MF;
  }
  if (kind === RENDER_FORMAT.GLB || kind === "gltf") {
    return RENDER_FORMAT.GLB;
  }
  if (kind === RENDER_FORMAT.GCODE) {
    return RENDER_FORMAT.GCODE;
  }
  if (kind === RENDER_FORMAT.IMPLICIT) {
    return RENDER_FORMAT.IMPLICIT;
  }
  if (kind === RENDER_FORMAT.URDF) {
    return RENDER_FORMAT.URDF;
  }
  if (kind === RENDER_FORMAT.SRDF) {
    return RENDER_FORMAT.SRDF;
  }
  if (kind === RENDER_FORMAT.SDF) {
    return RENDER_FORMAT.SDF;
  }
  return RENDER_FORMAT.STEP;
}

export function isMeshRenderFormat(format) {
  return MESH_RENDER_FORMATS.includes(normalizeFormat(format));
}

export function isRobotRenderFormat(format) {
  return ROBOT_RENDER_FORMATS.includes(normalizeFormat(format));
}

export function meshAssetKeyForFormat(format) {
  const normalized = normalizeFormat(format);
  return isMeshRenderFormat(normalized) ? normalized : RENDER_FORMAT.GLB;
}

export function meshAssetKeyForEntry(entry) {
  return meshAssetKeyForFormat(entrySourceFormat(entry));
}

export function fileSheetKindForEntry(entry) {
  if (!entry) {
    return "";
  }
  const kind = entryKind(entry);
  if (kind === RENDER_FORMAT.DXF) {
    return RENDER_FORMAT.DXF;
  }
  if (kind === RENDER_FORMAT.URDF) {
    return RENDER_FORMAT.URDF;
  }
  if (kind === RENDER_FORMAT.SRDF) {
    return RENDER_FORMAT.SRDF;
  }
  if (kind === RENDER_FORMAT.SDF) {
    return RENDER_FORMAT.SDF;
  }
  if (kind === RENDER_FORMAT.GCODE) {
    return RENDER_FORMAT.GCODE;
  }
  if (kind === RENDER_FORMAT.IMPLICIT) {
    return RENDER_FORMAT.IMPLICIT;
  }
  if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
    return RENDER_FORMAT.STEP;
  }
  if (isMeshRenderFormat(entrySourceFormat(entry))) {
    return "mesh";
  }
  return "";
}

export function fileExtensionFromPath(value, { baseUrl = "" } = {}) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }

  let pathname = rawValue;
  try {
    pathname = new URL(rawValue, baseUrl || "http://localhost/").pathname;
  } catch {
    pathname = rawValue.split("?")[0].split("#")[0];
  }

  const normalizedPath = pathname.toLowerCase();
  const slashIndex = normalizedPath.lastIndexOf("/");
  const dotIndex = normalizedPath.lastIndexOf(".");
  return dotIndex > slashIndex ? normalizedPath.slice(dotIndex) : "";
}

export function renderFormatFromExtension(extension) {
  const normalized = normalizeFormat(extension).replace(/^\./, "");
  if (normalized === "step" || normalized === "stp") {
    return RENDER_FORMAT.STEP;
  }
  if (normalized === "stl") {
    return RENDER_FORMAT.STL;
  }
  if (normalized === "3mf") {
    return RENDER_FORMAT.THREE_MF;
  }
  if (normalized === "glb" || normalized === "gltf") {
    return RENDER_FORMAT.GLB;
  }
  if (normalized === "gcode") {
    return RENDER_FORMAT.GCODE;
  }
  if (normalized === "implicit" || normalized === "implicit.js" || normalized === "implicit.mjs") {
    return RENDER_FORMAT.IMPLICIT;
  }
  if (normalized === "dxf") {
    return RENDER_FORMAT.DXF;
  }
  if (normalized === "urdf") {
    return RENDER_FORMAT.URDF;
  }
  if (normalized === "srdf") {
    return RENDER_FORMAT.SRDF;
  }
  if (normalized === "sdf") {
    return RENDER_FORMAT.SDF;
  }
  return "";
}

export function renderFormatFromPath(value, options = {}) {
  const rawValue = String(value || "").trim();
  let pathname = rawValue;
  try {
    pathname = new URL(rawValue, options.baseUrl || "http://localhost/").pathname;
  } catch {
    pathname = rawValue.split("?")[0].split("#")[0];
  }
  const normalizedPath = pathname.toLowerCase();
  if (normalizedPath.endsWith(".implicit.js") || normalizedPath.endsWith(".implicit.mjs")) {
    return RENDER_FORMAT.IMPLICIT;
  }
  return renderFormatFromExtension(fileExtensionFromPath(value, options));
}

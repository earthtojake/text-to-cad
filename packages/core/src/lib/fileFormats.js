export const RENDER_FORMAT = Object.freeze({
  STEP: "step",
  STL: "stl",
  THREE_MF: "3mf",
  GLB: "glb",
  DXF: "dxf",
  URDF: "urdf",
  SRDF: "srdf",
  SDF: "sdf",
  // A cadgen engine document (`cad.engine`): served by the engine, drawn by its own renderer.
  XBF: "xbf"
});

export const MESH_RENDER_FORMATS = Object.freeze([
  RENDER_FORMAT.STL,
  RENDER_FORMAT.THREE_MF,
  RENDER_FORMAT.GLB
]);

export function normalizeFormat(value) {
  return String(value || "").trim().toLowerCase();
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

export function meshAssetKeyForFormat(format) {
  const normalized = normalizeFormat(format);
  // A DXF's render asset is its own file (the server flattens it to a 2D payload;
  // nothing bakes a mesh for it), so its key is itself, never a baked GLB relation.
  return isMeshRenderFormat(normalized) || normalized === RENDER_FORMAT.DXF
    ? normalized
    : RENDER_FORMAT.GLB;
}

export function meshAssetKeyForEntry(entry) {
  return meshAssetKeyForFormat(entrySourceFormat(entry));
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
  return renderFormatFromExtension(fileExtensionFromPath(value, options));
}

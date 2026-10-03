export const RENDER_FORMAT = Object.freeze({
  STEP: "step",
  STL: "stl",
  THREE_MF: "3mf",
  GLB: "glb",
  DXF: "dxf",
  KICAD_PCB: "kicad_pcb",
  KICAD_SCH: "kicad_sch",
  HARNESS: "harness",
  URDF: "urdf",
  SRDF: "srdf",
  SDF: "sdf"
});

export const MESH_RENDER_FORMATS = Object.freeze([
  RENDER_FORMAT.STL,
  RENDER_FORMAT.THREE_MF,
  RENDER_FORMAT.GLB
]);

// Formats the viewer shows as a PLOT: the picture the document's own tool draws of it (KiCad's
// plot of a board or a schematic, WireViz's diagram of a wiring harness), served as SVG sheets
// by `GET /__cad/plot`. Like a DXF, the render asset is the file itself; nothing bakes a mesh
// for it.
export const PLOT_RENDER_FORMATS = Object.freeze([
  RENDER_FORMAT.KICAD_PCB,
  RENDER_FORMAT.KICAD_SCH,
  RENDER_FORMAT.HARNESS
]);

// A document whose type is TWO suffixes: `cable.harness.yml` is a wiring harness, while a plain
// `.yml` is no CAD file at all. To everything here each is one extension, as it is to the viewer
// server (`cadgen.viewer.content_types.COMPOUND_EXTENSIONS`), and only when a name comes before
// it: `.harness.yml` alone is a hidden `.yml`.
const COMPOUND_EXTENSIONS = Object.freeze([".harness.yml"]);
const COMPOUND_FORMATS = Object.freeze({ "harness.yml": RENDER_FORMAT.HARNESS });

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
    normalized === RENDER_FORMAT.DXF ||
    normalized === RENDER_FORMAT.KICAD_PCB ||
    normalized === RENDER_FORMAT.KICAD_SCH ||
    normalized === RENDER_FORMAT.HARNESS ||
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
  if (isPlotRenderFormat(kind)) {
    return kind;
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

export function isPlotRenderFormat(format) {
  return PLOT_RENDER_FORMATS.includes(normalizeFormat(format));
}

export function meshAssetKeyForFormat(format) {
  const normalized = normalizeFormat(format);
  // A DXF's render asset is its own file (the server flattens it to a 2D payload;
  // nothing bakes a mesh for it), and so is a plot's (its tool draws it as SVG), so
  // their key is themselves, never a baked GLB relation.
  return isMeshRenderFormat(normalized) || normalized === RENDER_FORMAT.DXF || isPlotRenderFormat(normalized)
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
  const name = normalizedPath.slice(slashIndex + 1);
  const compound = COMPOUND_EXTENSIONS.find((extension) => name.length > extension.length && name.endsWith(extension));
  if (compound) {
    return compound;
  }
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
  if (normalized === RENDER_FORMAT.KICAD_PCB || normalized === RENDER_FORMAT.KICAD_SCH) {
    return normalized;
  }
  if (Object.hasOwn(COMPOUND_FORMATS, normalized)) {
    return COMPOUND_FORMATS[normalized];
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

/**
 * Does this path name a file the CAD Viewer renders?
 *
 * The one authority on that question for the two apps that ask it. The shared
 * entry menu (`apps/web/src/client/shell/entry-menu.js`) offers `Copy
 * reference` only for a file a selector can point into, and "which formats
 * are CAD" must not become a list either app keeps of its own.
 */
export function isCadFile(value, options = {}) {
  return renderFormatFromPath(value, options) !== "";
}

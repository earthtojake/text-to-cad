import { DOCUMENT_TYPE_REGISTRY } from "./documentTypes.generated.js";

// The document types, from the library's registry (`cad.registry`, generated into
// `documentTypes.generated.js`): each type's format is its `wire` spelling, the one the server's
// API names it by (the id, but `3mf` for `threemf`). An earlier id (`aliases`: `xbf`, a model's
// file) names the type it is now (`documentKind`).
const TYPES = Object.freeze(Object.fromEntries(
  DOCUMENT_TYPE_REGISTRY.documentTypes.map((type) => [type.id, type])
));
const KIND_ALIASES = Object.freeze(Object.fromEntries(
  Object.entries(DOCUMENT_TYPE_REGISTRY.aliases || {}).map(([alias, id]) => [alias, TYPES[id].wire])
));

export const RENDER_FORMAT = Object.freeze({
  STEP: TYPES.step.wire,
  STL: TYPES.stl.wire,
  THREE_MF: TYPES.threemf.wire,
  GLB: TYPES.glb.wire,
  DXF: TYPES.dxf.wire,
  URDF: TYPES.urdf.wire,
  SRDF: TYPES.srdf.wire,
  // A model's document (`cad.engine`), held by the engine or its `.xbf` opened from disk: served by the
  // engine, drawn by its own renderer.
  MODEL: TYPES.model.wire,
  KICAD_PCB: TYPES.kicad_pcb.wire,
  // A KiCad schematic, drawn from its files as a board is, a sheet at a time (`packages/ui/src/renderers/schematic`).
  KICAD_SCH: TYPES.kicad_sch.wire
});

export const MESH_RENDER_FORMATS = Object.freeze(
  DOCUMENT_TYPE_REGISTRY.documentTypes.filter((type) => type.view === "mesh").map((type) => type.wire)
);

// A file's format by its extension: every type's extensions but a model's (its `.xbf`), which the
// engine serves as a document and no client reads by its extension; and `.gltf`, read as a GLB.
const FORMAT_BY_EXTENSION = Object.freeze(Object.fromEntries([
  ...DOCUMENT_TYPE_REGISTRY.documentTypes
    .filter((type) => !type.held)
    .flatMap((type) => type.extensions.map((extension) => [extension.slice(1), type.wire])),
  ["gltf", TYPES.glb.wire]
]));

// Formats the viewer shows as a PLOT: a KiCad board or schematic drawn from its files, as geometry per layer,
// by its document's `plot` (`GET /api/v1/documents/kicad_pcb/<id>/plot`). Like a DXF, the render asset is the file itself; nothing bakes a mesh
// for it.
export const PLOT_RENDER_FORMATS = Object.freeze(
  DOCUMENT_TYPE_REGISTRY.documentTypes.filter((type) => type.view === "plot").map((type) => type.wire)
);

export function normalizeFormat(value) {
  return String(value || "").trim().toLowerCase();
}

// A document's kind as it is now: an earlier one (`xbf`, which a released server or page may say) the kind it
// names (`model`), any other as given.
export function documentKind(value) {
  const normalized = normalizeFormat(value);
  return KIND_ALIASES[normalized] || normalized;
}

export function entryKind(entry) {
  return normalizeFormat(entry?.kind);
}

export function entrySourceFormat(entry) {
  const kind = entryKind(entry);
  // A catalog kind is a format of its own but for the engine's documents, which open as STEP's do.
  const format = FORMAT_BY_EXTENSION[kind];
  return format && format !== RENDER_FORMAT.STEP ? format : RENDER_FORMAT.STEP;
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
  // nothing bakes a mesh for it), and so is a plot's (the server draws the board from it),
  // so their key is themselves, never a baked GLB relation.
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
  const dotIndex = normalizedPath.lastIndexOf(".");
  return dotIndex > slashIndex ? normalizedPath.slice(dotIndex) : "";
}

export function renderFormatFromExtension(extension) {
  return FORMAT_BY_EXTENSION[normalizeFormat(extension).replace(/^\./, "")] || "";
}

export function renderFormatFromPath(value, options = {}) {
  return renderFormatFromExtension(fileExtensionFromPath(value, options));
}

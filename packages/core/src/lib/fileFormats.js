import { DOCUMENT_TYPE_REGISTRY } from "./documentTypes.generated.js";

// The document types, from the library's registry (`cad.registry`, generated into
// `documentTypes.generated.js`): each type's format is its `wire` spelling, the one the server's
// API names it by (the id, but `3mf` for `threemf`).
const TYPES = Object.freeze(Object.fromEntries(
  DOCUMENT_TYPE_REGISTRY.documentTypes.map((type) => [type.id, type])
));

export const RENDER_FORMAT = Object.freeze({
  STEP: TYPES.step.wire,
  STL: TYPES.stl.wire,
  THREE_MF: TYPES.threemf.wire,
  GLB: TYPES.glb.wire,
  DXF: TYPES.dxf.wire,
  URDF: TYPES.urdf.wire,
  SRDF: TYPES.srdf.wire,
  SDF: TYPES.sdf.wire,
  // A cadgen engine document (`cad.engine`): served by the engine, drawn by its own renderer.
  XBF: TYPES.xbf.wire,
  KICAD_PCB: TYPES.kicad_pcb.wire,
  // A KiCad schematic, drawn from its files as a board is, a sheet at a time (`packages/ui/src/renderers/schematic`).
  KICAD_SCH: TYPES.kicad_sch.wire
});

export const MESH_RENDER_FORMATS = Object.freeze(
  DOCUMENT_TYPE_REGISTRY.documentTypes.filter((type) => type.view === "mesh").map((type) => type.wire)
);

// A file's format by its extension: every type's extensions but the engine's own document's, which
// the engine serves as a document and no client reads by its extension; and `.gltf`, read as a GLB.
const FORMAT_BY_EXTENSION = Object.freeze(Object.fromEntries([
  ...DOCUMENT_TYPE_REGISTRY.documentTypes
    .filter((type) => type.id !== "xbf")
    .flatMap((type) => type.extensions.map((extension) => [extension.slice(1), type.wire])),
  ["gltf", TYPES.glb.wire]
]));

// A document type with no file of its own is read as the file type whose bytes it is served in, by
// the registry's MIME type: an implicit's source is a GLB. A model's names none (the engine serves its
// structure and parts, as a STEP's), so it has no format here and opens as the engine's document.
const FORMAT_BY_FILELESS_KIND = Object.freeze(Object.fromEntries(
  DOCUMENT_TYPE_REGISTRY.documentTypes
    .filter((type) => type.extensions.length === 0 && type.mime)
    .flatMap((type) => {
      const file = DOCUMENT_TYPE_REGISTRY.documentTypes.find((other) => other.extensions.length && other.mime === type.mime);
      return file ? [[type.wire, file.wire]] : [];
    })
));
// The file format each MIME type names: the first type with a file that carries it.
const FORMAT_BY_MIME = Object.freeze(Object.fromEntries(
  DOCUMENT_TYPE_REGISTRY.documentTypes
    .filter((type) => type.extensions.length && type.mime)
    .reverse()
    .map((type) => [type.mime, type.wire])
));
const MIME_BY_KIND = Object.freeze(Object.fromEntries(
  DOCUMENT_TYPE_REGISTRY.documentTypes.map((type) => [type.wire, type.mime])
));

// Formats the viewer shows as a PLOT: a KiCad board or schematic drawn from its files, as geometry per layer,
// by its document's `plot` (`GET /api/v1/documents/kicad_pcb/<id>/plot`). Like a DXF, the render asset is the file itself; nothing bakes a mesh
// for it.
export const PLOT_RENDER_FORMATS = Object.freeze(
  DOCUMENT_TYPE_REGISTRY.documentTypes.filter((type) => type.view === "plot").map((type) => type.wire)
);

export function normalizeFormat(value) {
  return String(value || "").trim().toLowerCase();
}

export function entryKind(entry) {
  return normalizeFormat(entry?.kind);
}

export function entrySourceFormat(entry) {
  const kind = entryKind(entry);
  // A catalog kind is a format of its own but for the engine's documents, which open as STEP's do;
  // a document with no file of its own is the format its bytes are served in (an implicit's, a GLB).
  const format = FORMAT_BY_EXTENSION[kind] || FORMAT_BY_FILELESS_KIND[kind];
  return format && format !== RENDER_FORMAT.STEP ? format : RENDER_FORMAT.STEP;
}

/**
 * The format a document with no file of its own is served in (`GET /api/v1/documents/<kind>/<id>/source`),
 * by its kind: `glb` for an implicit's. "" for a kind with a file, and for a model's, which the engine
 * serves as its document.
 */
export function filelessDocumentFormat(kind) {
  return FORMAT_BY_FILELESS_KIND[normalizeFormat(kind)] || "";
}

/** The MIME type of a document kind's bytes (`cad.registry`), "" for one that names none. */
export function documentMime(kind) {
  return MIME_BY_KIND[normalizeFormat(kind)] || "";
}

/** The file format whose bytes a MIME type names (`model/gltf-binary`: `glb`), "" for any other. */
export function renderFormatFromMime(mime) {
  return FORMAT_BY_MIME[String(mime || "").trim().toLowerCase()] || "";
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

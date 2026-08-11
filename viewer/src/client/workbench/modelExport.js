import { entryKind } from "cadjs/lib/fileFormats.js";
import { exportFormatsForRenderFormat } from "cadjs/lib/renderCapabilities.js";
import { refreshCadCatalog } from "./cadManifestStore.js";

// "Export model" formats for a STEP/assembly entry, in dropdown/menu order.
export const STEP_EXPORT_FORMATS = Object.freeze(["step", "3mf", "stl", "glb"]);

// A generated `.dxf.py` drawing exports its native format only.
export const DXF_EXPORT_FORMATS = Object.freeze(["dxf"]);

// An `.implicit.js` model exports to mesh formats only — its own source is the "native"
// file and there is nothing to download. The mesh is produced by the shipped implicitjs
// export CLI, run SERVER-side (cadgen.implicit_export): unlike the baked render package it
// is live-valued, so the exporter's own resolution/params defaults apply.
export const IMPLICIT_EXPORT_FORMATS = Object.freeze(["stl", "glb", "3mf"]);

const EMPTY_EXPORT_FORMATS = Object.freeze([]);

const EXPORT_FORMAT_LABELS = Object.freeze({
  step: "STEP",
  "3mf": "3MF",
  stl: "STL",
  glb: "GLB",
  dxf: "DXF",
});

export function exportFormatLabel(format) {
  const normalized = String(format || "").trim().toLowerCase();
  return EXPORT_FORMAT_LABELS[normalized] || normalized.toUpperCase();
}

// An imported model's STEP file is its own source (no `.step.py` generator), so exporting it
// to STEP is just downloading the original. Generated models carry a `source` generator.
export function isImportedStepEntry(entry) {
  return !(entry?.source && entry.source.sourcePath);
}

// Menu label for one export format. STEP/DXF are the entry's native type, so they read as
// "Download <FORMAT>"; every other format is "Export <FORMAT>".
export function exportItemLabel(format) {
  const normalized = String(format || "").trim().toLowerCase();
  if (normalized === "step" || normalized === "dxf") {
    return `Download ${exportFormatLabel(normalized)}`;
  }
  return `Export ${exportFormatLabel(normalized)}`;
}

function normalizedFileRef(value) {
  // Keep a leading "/" intact: catalog `entry.file` refs are absolute in dynamic-root mode,
  // and the server resolves absolute refs directly (stripping the slash would turn an
  // absolute path into a bogus relative one → "STEP file not found"). Mirrors
  // downloadUrlForFileAsset, which sends the ref as-is.
  return String(value || "").trim().replace(/\\/g, "/");
}

function normalizedFormat(value) {
  const format = String(value || "").trim().toLowerCase().replace(/^\./, "");
  return STEP_EXPORT_FORMATS.includes(format)
    || DXF_EXPORT_FORMATS.includes(format)
    || IMPLICIT_EXPORT_FORMATS.includes(format)
    ? format
    : "";
}

// Request a server-side export of one model — STEP/assembly, `.dxf.py` drawing, or
// `.implicit.js` model — to `format`, written to a path the user picks via the OS-native
// save dialog. ONE route for all three: the server picks the producer from the source file,
// so nothing about which geometry runtime meshes it reaches the browser. Resolves to one of:
//   { cancelled: true }                       — user dismissed the save dialog (not an error)
//   { ok, path, filename, format }            — written directly to the chosen path
//   { ok, fallback, downloadUrl, filename }   — no native dialog; fetch the file to download it
// Throws on a genuine failure.
export async function requestModelExport({ file, format } = {}) {
  const fileRef = normalizedFileRef(file);
  const exportFormat = normalizedFormat(format);
  if (!fileRef) {
    throw new Error("Missing model file");
  }
  if (!exportFormat) {
    throw new Error(`Unsupported export format: ${format || "(missing)"}`);
  }
  const response = await fetch(
    `/__cad/export?file=${encodeURIComponent(fileRef)}&format=${encodeURIComponent(exportFormat)}`,
    { method: "POST" }
  );
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (payload?.cancelled) {
    return { cancelled: true };
  }
  if (!response.ok || !payload?.ok) {
    throw new Error(String(payload?.error || `Export failed with HTTP ${response.status}`));
  }
  if (payload.catalogChanged || payload.fallback) {
    // The export landed inside the viewer root, so the catalog gained/updated an entry —
    // refresh so the new file shows up in the tree without a manual rescan.
    refreshCadCatalog({ markRefreshing: false }).catch(() => {});
  }
  return payload;
}

// The single answer to "what can this entry export to?", read from the capability table.
// Both menus (the toolbar dropdown and the file context menu) used to re-derive this from
// entry.kind independently, which is how implicit ended up in one and not the other.
// Returns an empty list for entries with nothing to export.
export function exportFormatsForEntry(entry) {
  if (!entry) {
    return EMPTY_EXPORT_FORMATS;
  }
  const kind = entryKind(entry);
  // Only GENERATED drawings export; a raw imported .dxf is already the deliverable.
  if (kind === "dxf" && entry?.sourceKind !== "python") {
    return EMPTY_EXPORT_FORMATS;
  }
  // A STEP part/assembly reports its kind as part/assembly, not "step".
  if (kind === "part" || kind === "assembly") {
    return exportFormatsForRenderFormat("step");
  }
  return exportFormatsForRenderFormat(kind);
}

export function entryCanExport(entry) {
  return exportFormatsForEntry(entry).length > 0;
}

import { refreshCadCatalog } from "./cadManifestStore.js";

export const IMPLICIT_EXPORT_FORMATS = Object.freeze(["stl", "glb", "3mf"]);
export const DEFAULT_IMPLICIT_EXPORT_RESOLUTION = 96;

function normalizedFileRef(value) {
  return String(value || "").trim().replace(/\\/g, "/").replace(/^\/+/, "");
}

function normalizedFormat(value) {
  const format = String(value || "").trim().toLowerCase().replace(/^\./, "");
  return IMPLICIT_EXPORT_FORMATS.includes(format) ? format : "";
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export async function requestImplicitCadExport({
  file,
  format,
  parameterValues = null,
  animationState = null,
  resolution = DEFAULT_IMPLICIT_EXPORT_RESOLUTION,
} = {}) {
  const fileRef = normalizedFileRef(file);
  const exportFormat = normalizedFormat(format);
  if (!fileRef) {
    throw new Error("Missing implicit CAD file");
  }
  if (!exportFormat) {
    throw new Error(`Unsupported implicit CAD export format: ${format || "(missing)"}`);
  }
  const response = await fetch(
    `/__cad/implicit-export?file=${encodeURIComponent(fileRef)}&format=${encodeURIComponent(exportFormat)}`,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        format: exportFormat,
        resolution,
        ...(isObject(parameterValues) ? { parameterValues } : {}),
        ...(isObject(animationState) ? { animationState } : {}),
      }),
    }
  );
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok || !payload?.ok) {
    throw new Error(String(payload?.error || `Implicit CAD export failed with HTTP ${response.status}`));
  }
  if (payload.catalog) {
    refreshCadCatalog({ markRefreshing: false }).catch(() => {});
  }
  return payload;
}

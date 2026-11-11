import {
  entrySourceFormat,
  meshAssetKeyForEntry,
  RENDER_FORMAT
} from "./fileFormats.js";

export { meshAssetKeyForEntry } from "./fileFormats.js";

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizedKind(entry) {
  return normalizeString(entry?.kind).toLowerCase();
}

function primaryAsset(entry) {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  const url = normalizeString(entry.url);
  if (!url) {
    return null;
  }
  return {
    url,
    hash: normalizeString(entry.hash),
    bytes: Number.isFinite(Number(entry.bytes)) && Number(entry.bytes) >= 0 ? Number(entry.bytes) : 0,
  };
}

function relationAsset(entry, key) {
  const relation = entry?.relations?.[key];
  if (!relation || typeof relation !== "object") {
    return null;
  }
  const url = normalizeString(relation.url);
  return url
    ? {
        url,
        hash: normalizeString(relation.hash),
        bytes: Number.isFinite(Number(relation.bytes)) && Number(relation.bytes) >= 0 ? Number(relation.bytes) : 0,
      }
    : null;
}

export function entryAsset(entry, key) {
  const assetKey = normalizeString(key).toLowerCase();
  const kind = normalizedKind(entry);
  const sourceFormat = entrySourceFormat(entry);
  if (assetKey === "urdf" && kind === "srdf") {
    return relationAsset(entry, "urdf");
  }
  if (
    assetKey === kind ||
    assetKey === sourceFormat ||
    (sourceFormat === RENDER_FORMAT.STEP && assetKey === "glb") ||
    (kind === "srdf" && assetKey === "srdf")
  ) {
    return primaryAsset(entry);
  }
  return null;
}

export function entryAssetUrl(entry, key) {
  return normalizeString(entryAsset(entry, key)?.url);
}

export function entryAssetHash(entry, key) {
  return normalizeString(entryAsset(entry, key)?.hash);
}

export function entryMeshAssetUrl(entry) {
  return entryAssetUrl(entry, meshAssetKeyForEntry(entry));
}

export function entryMeshAssetHash(entry) {
  return entryAssetHash(entry, meshAssetKeyForEntry(entry));
}

export function entryUrdfAssetHash(entry) {
  return [
    entryAssetHash(entry, "urdf"),
    entryAssetHash(entry, "srdf"),
    entryAssetHash(entry, "sdf")
  ].filter(Boolean).join(":");
}

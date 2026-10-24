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

export function entryAssetBytes(entry, key) {
  const bytes = Number(entryAsset(entry, key)?.bytes);
  return Number.isFinite(bytes) && bytes >= 0 ? bytes : 0;
}

export function entryMeshAssetUrl(entry) {
  return entryAssetUrl(entry, meshAssetKeyForEntry(entry));
}

export function entryMeshAssetHash(entry) {
  return entryAssetHash(entry, meshAssetKeyForEntry(entry));
}

export function entryMeshAssetBytes(entry) {
  return entryAssetBytes(entry, meshAssetKeyForEntry(entry));
}

export function entryUrdfAssetHash(entry) {
  return [
    entryAssetHash(entry, "urdf"),
    entryAssetHash(entry, "srdf"),
    entryAssetHash(entry, "sdf")
  ].filter(Boolean).join(":");
}

export function entryMeshAssetSignature(entry) {
  const mesh = String(
    entry?.kind === "assembly"
      ? entryAssetHash(entry, "glb")
      : entryMeshAssetHash(entry)
  );
  const appearance = entrySourceFormat(entry) === RENDER_FORMAT.STEP
    ? normalizeString(entry?.appearanceHash)
    : "";
  return appearance ? `${mesh}:${appearance}` : mesh;
}

export function entryReferenceAssetSignature(entry) {
  return normalizeString(entry?.hash);
}

export function entryHasMesh(entry) {
  if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
    return Boolean(
      entryAssetUrl(entry, "glb") &&
      entryAssetHash(entry, "glb")
    );
  }
  const meshKey = meshAssetKeyForEntry(entry);
  return Boolean(entryAssetUrl(entry, meshKey) && entryAssetHash(entry, meshKey));
}

export function entryHasReferences(entry) {
  return entrySourceFormat(entry) === RENDER_FORMAT.STEP && entryHasMesh(entry);
}

export function entryPoseUrl(entry) {
  // The sidecar URL of a STEP model with kinematics: it versions the articulation
  // cadgen resolved from that sidecar, which travels inline on the entry
  // (`articulation`).
  return entrySourceFormat(entry) === RENDER_FORMAT.STEP
    ? normalizeString(entry?.poseUrl)
    : "";
}

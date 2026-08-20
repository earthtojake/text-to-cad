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
    (sourceFormat === RENDER_FORMAT.STEP && ["glb", "topology", "selectortopology", "displayedgetopology"].includes(assetKey)) ||
    (kind === "srdf" && assetKey === "srdf")
  ) {
    return primaryAsset(entry);
  }
  // A DXF or implicit entry's own file is not renderable geometry, so its `url` stays the
  // source/exchange artifact and the scanner publishes the package's baked mesh as a `glb`
  // relation. Resolving it here is what lets entryMeshAssetUrl and the mesh loaders treat
  // those entries as ordinary GLB with no per-format branch.
  if (assetKey === RENDER_FORMAT.GLB) {
    return relationAsset(entry, RENDER_FORMAT.GLB);
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

export function entryTopologyAssetUrl(entry) {
  return entryAssetUrl(entry, "topology") || entryAssetUrl(entry, "glb");
}

export function entrySelectorTopologyAssetUrl(entry) {
  return entryAssetUrl(entry, "selectorTopology") || entryTopologyAssetUrl(entry);
}

export function entryDisplayEdgeTopologyAssetUrl(entry) {
  return entryAssetUrl(entry, "displayEdgeTopology") || entryTopologyAssetUrl(entry);
}

export function entryUrdfAssetHash(entry) {
  return [
    entryAssetHash(entry, "urdf"),
    entryAssetHash(entry, "srdf"),
    entryAssetHash(entry, "sdf")
  ].filter(Boolean).join(":");
}

export function entryMeshAssetSignature(entry) {
  return String(
    entry?.kind === "assembly"
      ? entryAssetHash(entry, "glb")
      : entryMeshAssetHash(entry)
  );
}

export function entryReferenceAssetSignature(entry) {
  return entryAssetHash(entry, "selectorTopology") || normalizeString(entry?.hash);
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

export function entryHasUrdf(entry) {
  const kind = normalizeString(entry?.kind).toLowerCase();
  if (kind === RENDER_FORMAT.SDF) {
    return Boolean(entryAssetUrl(entry, "sdf") && entryAssetHash(entry, "sdf"));
  }
  return Boolean(entryAssetUrl(entry, "urdf") && entryAssetHash(entry, "urdf"));
}

export function entryHasReferences(entry) {
  return Boolean(
    entrySourceFormat(entry) === RENDER_FORMAT.STEP &&
    entryAssetUrl(entry, "glb") &&
    entryAssetHash(entry, "selectorTopology")
  );
}

export function entryHasDisplayEdges(entry) {
  return Boolean(
    entrySourceFormat(entry) === RENDER_FORMAT.STEP &&
    entryAssetUrl(entry, "glb") &&
    entryAssetHash(entry, "displayEdgeTopology")
  );
}

export function entryHasDxf(entry) {
  return Boolean(entryAssetUrl(entry, "dxf") && entryAssetHash(entry, "dxf"));
}

/** A dimensioned DRAWING rather than a cut layout: a document with nothing to bake.
 *
 * Both arrive with no `glb` relation, so without asking this the viewer cannot tell a drawing
 * from a cut layout whose flat pattern has not been built yet -- and it waits forever for a mesh
 * that is never coming (issue #246). The server reads the profile from the package descriptor.
 */
export function entryIsDrawingDocument(entry) {
  return Boolean(
    entrySourceFormat(entry) === RENDER_FORMAT.DXF &&
    normalizeString(entry?.drawingProfile) === "drawing"
  );
}

export function entryHasImplicitCad(entry) {
  return Boolean(entryAssetUrl(entry, "implicit") && entryAssetHash(entry, "implicit"));
}

export function entryStepModuleUrl(entry) {
  return entrySourceFormat(entry) === RENDER_FORMAT.STEP
    ? normalizeString(entry?.moduleUrl)
    : "";
}

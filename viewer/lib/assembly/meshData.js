import { mergeBounds, transformBounds, transformPoint } from "../urdf/kinematics.js";

const IDENTITY_TRANSFORM = Object.freeze([
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  0, 0, 0, 1
]);

function toTransformArray(value) {
  if (!Array.isArray(value) || value.length !== 16) {
    return [...IDENTITY_TRANSFORM];
  }
  return value.map((component, index) => Number.isFinite(Number(component)) ? Number(component) : IDENTITY_TRANSFORM[index]);
}

function normalizeVector(vector) {
  const x = Number(vector?.[0] || 0);
  const y = Number(vector?.[1] || 0);
  const z = Number(vector?.[2] || 0);
  const length = Math.hypot(x, y, z);
  if (length <= 1e-9) {
    return [0, 0, 1];
  }
  return [x / length, y / length, z / length];
}

function transformVector(transform, vector) {
  const matrix = toTransformArray(transform);
  return normalizeVector([
    (matrix[0] * vector[0]) + (matrix[1] * vector[1]) + (matrix[2] * vector[2]),
    (matrix[4] * vector[0]) + (matrix[5] * vector[1]) + (matrix[6] * vector[2]),
    (matrix[8] * vector[0]) + (matrix[9] * vector[1]) + (matrix[10] * vector[2])
  ]);
}

function copyTransformedVertices(target, targetOffset, source, transform) {
  for (let index = 0; index < source.length; index += 3) {
    const point = transformPoint(transform, [source[index], source[index + 1], source[index + 2]]);
    target[targetOffset + index] = point[0];
    target[targetOffset + index + 1] = point[1];
    target[targetOffset + index + 2] = point[2];
  }
}

function copyTransformedNormals(target, targetOffset, source, transform, count) {
  if (!source || source.length < count * 3) {
    return;
  }
  for (let index = 0; index < count * 3; index += 3) {
    const vector = transformVector(transform, [source[index], source[index + 1], source[index + 2]]);
    target[targetOffset + index] = vector[0];
    target[targetOffset + index + 1] = vector[1];
    target[targetOffset + index + 2] = vector[2];
  }
}

function copyColors(target, targetOffset, source, count) {
  if (!source || source.length < count * 3) {
    return;
  }
  for (let index = 0; index < count * 3; index += 1) {
    target[targetOffset + index] = source[index];
  }
}

function sourceMeshForPart(meshesBySourcePath, sourcePath) {
  if (meshesBySourcePath instanceof Map) {
    return meshesBySourcePath.get(sourcePath) || null;
  }
  if (meshesBySourcePath && typeof meshesBySourcePath === "object") {
    return meshesBySourcePath[sourcePath] || null;
  }
  return null;
}

function meshKeyForPart(part) {
  return String(part?.sourcePath || part?.id || part?.occurrenceId || "").trim();
}

function meshUrlForPart(part) {
  return String(part?.assets?.glb?.url || part?.meshUrl || "").trim();
}

function labelForSourcePath(sourcePath) {
  const basename = String(sourcePath || "").trim().split("/").filter(Boolean).pop() || "";
  return basename.replace(/\.(?:step|stp|stl|glb)$/i, "");
}

function isOpaqueAssemblyLabel(value) {
  const normalized = String(value || "").trim();
  return !normalized ||
    normalized.includes("=>") ||
    /^o?\d+(?:[.:]\d+)*$/i.test(normalized) ||
    /^\[?[0-9:.[\]-]+\]?$/.test(normalized);
}

function closeTo(value, target, tolerance = 2) {
  return Math.abs(Number(value) - target) <= tolerance;
}

function inferredNativePartLabelFromBounds(bounds) {
  const min = bounds?.min;
  const max = bounds?.max;
  if (!Array.isArray(min) || !Array.isArray(max) || min.length < 3 || max.length < 3) {
    return "";
  }
  const dx = Number(max[0]) - Number(min[0]);
  const dy = Number(max[1]) - Number(min[1]);
  const dz = Number(max[2]) - Number(min[2]);
  const cx = (Number(min[0]) + Number(max[0])) / 2;
  const cy = (Number(min[1]) + Number(max[1])) / 2;
  const minZ = Number(min[2]);

  if (dz > 220 && dx < 65 && dy > 240) {
    return cx < 0 ? "left_side_plate" : "right_side_plate";
  }
  if (dz > 220 && dx > 180 && dy < 70) {
    return cy < 0 ? "front_panel" : "rear_panel";
  }
  if (closeTo(dx, 180, 4) && closeTo(dy, 204, 4) && dz >= 65 && dz <= 75) {
    return "bottom_tray";
  }
  if (closeTo(dx, 180, 4) && closeTo(dy, 200, 4) && dz <= 8) {
    return `equipment_shelf_z${Math.round(minZ)}`;
  }
  if (dx < 45 && dy > 120 && dz > 100 && minZ < 15) {
    return cx < 0 ? "left_axle_insert" : "right_axle_insert";
  }
  if (closeTo(dx, 240, 4) && closeTo(dy, 256, 4) && dz <= 10 && closeTo(minZ, 240, 3)) {
    return "top_lid";
  }
  if (closeTo(dx, 240, 4) && closeTo(dy, 226, 6) && dz > 90 && minZ >= 250) {
    return "upper_compute_bay";
  }
  if (closeTo(dx, 128, 8) && closeTo(dy, 256, 6) && dz <= 10 && minZ >= 245) {
    return cx < 0 ? "left_overwheel_pod" : "right_overwheel_pod";
  }
  if (closeTo(dx, 172, 8) && closeTo(dy, 76, 8) && dz >= 45 && minZ >= 350) {
    return "upper_perception_pod";
  }
  return "";
}

function displayNameForPart(part, sourcePath, key) {
  const explicitName = String(part?.displayName || part?.name || "").trim();
  if (!isOpaqueAssemblyLabel(explicitName)) {
    return explicitName;
  }
  const sourceLabel = labelForSourcePath(sourcePath);
  if (sourceLabel) {
    return sourceLabel;
  }
  const inferredLabel = inferredNativePartLabelFromBounds(part?.bbox);
  if (inferredLabel) {
    return inferredLabel;
  }
  return String(part?.occurrenceId || part?.instancePath || key || "").trim();
}

export function assemblyRootFromTopology(topologyManifest) {
  const root = topologyManifest?.assembly?.root;
  return root && typeof root === "object" ? root : null;
}

export function flattenAssemblyLeafParts(root) {
  const leafParts = [];
  const stack = root ? [root] : [];
  while (stack.length) {
    const node = stack.pop();
    const children = Array.isArray(node?.children) ? node.children : [];
    if (children.length) {
      for (let index = children.length - 1; index >= 0; index -= 1) {
        stack.push(children[index]);
      }
      continue;
    }
    if (String(node?.nodeType || "").trim() === "part") {
      leafParts.push(node);
    }
  }
  return leafParts;
}

export function flattenAssemblyNodes(root) {
  const nodes = [];
  const stack = root ? [root] : [];
  while (stack.length) {
    const node = stack.pop();
    nodes.push(node);
    const children = Array.isArray(node?.children) ? node.children : [];
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return nodes;
}

export function findAssemblyNode(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId || normalizedNodeId === "root") {
    return root || null;
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (String(node?.id || "").trim() === normalizedNodeId) {
      return node;
    }
    const children = Array.isArray(node?.children) ? node.children : [];
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return null;
}

export function descendantLeafPartIds(node) {
  return flattenAssemblyLeafParts(node)
    .map((part) => String(part?.id || "").trim())
    .filter(Boolean);
}

export function representativeAssemblyLeafPartId(node) {
  const nodeId = String(node?.id || "").trim();
  if (!node) {
    return "";
  }
  if (String(node?.nodeType || "").trim() === "part") {
    return nodeId;
  }
  const declaredLeafPartIds = Array.isArray(node?.leafPartIds)
    ? node.leafPartIds.map((id) => String(id || "").trim()).filter(Boolean)
    : [];
  if (declaredLeafPartIds.length) {
    return declaredLeafPartIds[0];
  }
  return descendantLeafPartIds(node)[0] || nodeId;
}

export function buildAssemblyLeafToNodePickMap(nodes) {
  const map = new Map();
  for (const node of Array.isArray(nodes) ? nodes : []) {
    const nodeId = String(node?.id || "").trim();
    if (!nodeId) {
      continue;
    }
    const leafPartIds = Array.isArray(node?.leafPartIds) && node.leafPartIds.length
      ? node.leafPartIds
      : descendantLeafPartIds(node);
    for (const leafPartId of leafPartIds) {
      const normalizedLeafPartId = String(leafPartId || "").trim();
      if (normalizedLeafPartId) {
        map.set(normalizedLeafPartId, nodeId);
      }
    }
  }
  return map;
}

export function leafPartIdsForAssemblySelection(partId, {
  assemblyPartMap,
  fallbackPartId = "",
  validLeafPartIds = []
} = {}) {
  const normalizedPartId = String(partId || "").trim();
  const validLeafPartIdSet = validLeafPartIds instanceof Set
    ? validLeafPartIds
    : new Set(
      (Array.isArray(validLeafPartIds) ? validLeafPartIds : [])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
  const leafIdIsValid = (id) => {
    return !validLeafPartIdSet.size || validLeafPartIdSet.has(id);
  };
  const normalizeLeafIds = (leafPartIds) => {
    const seen = new Set();
    const result = [];
    for (const leafPartId of Array.isArray(leafPartIds) ? leafPartIds : []) {
      const normalizedLeafPartId = String(leafPartId || "").trim();
      if (!normalizedLeafPartId || seen.has(normalizedLeafPartId) || !leafIdIsValid(normalizedLeafPartId)) {
        continue;
      }
      seen.add(normalizedLeafPartId);
      result.push(normalizedLeafPartId);
    }
    return result;
  };

  if (normalizedPartId) {
    const selectedNode = assemblyPartMap instanceof Map
      ? assemblyPartMap.get(normalizedPartId) || null
      : null;
    const selectedLeafPartIds = selectedNode
      ? normalizeLeafIds(descendantLeafPartIds(selectedNode))
      : normalizeLeafIds([normalizedPartId]);
    if (selectedLeafPartIds.length) {
      return selectedLeafPartIds;
    }
  }

  const normalizedFallbackPartId = String(fallbackPartId || "").trim();
  return normalizeLeafIds([normalizedFallbackPartId]);
}

export function assemblyBreadcrumb(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root) {
    return [];
  }
  const path = [];
  function visit(node) {
    path.push(node);
    if (!normalizedNodeId || normalizedNodeId === "root" || String(node?.id || "").trim() === normalizedNodeId) {
      return true;
    }
    for (const child of Array.isArray(node?.children) ? node.children : []) {
      if (visit(child)) {
        return true;
      }
    }
    path.pop();
    return false;
  }
  return visit(root) ? [...path] : [root];
}

export function assemblyCompositionMeshRequests(topologyManifest) {
  const root = assemblyRootFromTopology(topologyManifest);
  const requests = [];
  for (const part of flattenAssemblyLeafParts(root)) {
    const sourcePath = String(part?.sourcePath || "").trim();
    const key = meshKeyForPart(part);
    if (!key) {
      continue;
    }
    requests.push({
      key,
      sourcePath,
      meshUrl: meshUrlForPart(part)
    });
  }
  return requests;
}

export function buildAssemblyMeshData(topologyManifest, meshesBySourcePath) {
  const assemblyRoot = assemblyRootFromTopology(topologyManifest);
  if (!assemblyRoot) {
    throw new Error("Assembly topology is missing assembly.root");
  }
  const manifestParts = flattenAssemblyLeafParts(assemblyRoot);
  let totalVertexCount = 0;
  let totalIndexCount = 0;
  let hasSourceColors = false;
  for (const part of manifestParts) {
    const key = meshKeyForPart(part);
    const sourceMesh = sourceMeshForPart(meshesBySourcePath, key);
    if (!sourceMesh) {
      throw new Error(`Missing source mesh for assembly part ${key || "(unknown)"}`);
    }
    totalVertexCount += Math.floor((sourceMesh.vertices?.length || 0) / 3);
    totalIndexCount += sourceMesh.indices?.length || 0;
    hasSourceColors ||= manifestPartUsesSourceColors(part) && sourceMeshHasColors(sourceMesh);
  }

  const vertices = new Float32Array(totalVertexCount * 3);
  const normals = new Float32Array(totalVertexCount * 3);
  const colors = hasSourceColors ? new Float32Array(totalVertexCount * 3).fill(1) : new Float32Array(0);
  const indices = new Uint32Array(totalIndexCount);
  const parts = [];
  let vertexOffset = 0;
  let indexOffset = 0;

  for (const manifestPart of manifestParts) {
    const sourcePath = String(manifestPart?.sourcePath || "").trim();
    const key = meshKeyForPart(manifestPart);
    const sourceMesh = sourceMeshForPart(meshesBySourcePath, key);
    const sourceVertices = sourceMesh.vertices || new Float32Array(0);
    const sourceNormals = sourceMesh.normals || new Float32Array(0);
    const sourceColors = sourceMesh.colors || new Float32Array(0);
    const sourceIndices = sourceMesh.indices || new Uint32Array(0);
    const transform = toTransformArray(manifestPart?.worldTransform || manifestPart?.transform);
    const vertexCount = Math.floor(sourceVertices.length / 3);
    const triangleCount = Math.floor(sourceIndices.length / 3);
    const partHasSourceColors = manifestPartUsesSourceColors(manifestPart) && sourceMeshHasColors(sourceMesh);
    const partVertexOffset = vertexOffset;
    const partTriangleOffset = Math.floor(indexOffset / 3);
    const positionOffset = partVertexOffset * 3;

    copyTransformedVertices(vertices, positionOffset, sourceVertices, transform);
    copyTransformedNormals(normals, positionOffset, sourceNormals, transform, vertexCount);
    if (hasSourceColors && partHasSourceColors) {
      copyColors(colors, positionOffset, sourceColors, vertexCount);
    }
    for (let index = 0; index < sourceIndices.length; index += 1) {
      indices[indexOffset + index] = sourceIndices[index] + partVertexOffset;
    }

    const bounds = manifestPart?.bbox || transformBounds(sourceMesh.bounds, transform);
    const displayName = displayNameForPart(manifestPart, sourcePath, key);
    parts.push({
      ...manifestPart,
      id: String(manifestPart?.id || manifestPart?.occurrenceId || "").trim(),
      occurrenceId: String(manifestPart?.occurrenceId || manifestPart?.id || "").trim(),
      name: displayName,
      label: displayName,
      nodeType: "part",
      sourceKind: String(manifestPart?.sourceKind || "").trim(),
      sourcePath,
      partSourcePath: sourcePath,
      sourceBounds: sourceMesh.bounds,
      bounds,
      transform,
      hasSourceColors: partHasSourceColors,
      vertexOffset: partVertexOffset,
      vertexCount,
      triangleOffset: partTriangleOffset,
      triangleCount,
      edgeIndexOffset: 0,
      edgeIndexCount: 0
    });

    vertexOffset += vertexCount;
    indexOffset += sourceIndices.length;
  }

  return {
    vertices,
    indices,
    normals,
    colors,
    edge_indices: new Uint32Array(0),
    bounds: mergeBounds(parts.map((part) => part.bounds)),
    parts,
    assemblyRoot,
    has_source_colors: hasSourceColors
  };
}

function manifestPartUsesSourceColors(part) {
  return part?.useSourceColors !== false;
}

function sourceMeshHasColors(sourceMesh) {
  return !!sourceMesh?.has_source_colors &&
    sourceMesh.colors?.length > 0 &&
    sourceMesh.colors.length === sourceMesh.vertices?.length;
}

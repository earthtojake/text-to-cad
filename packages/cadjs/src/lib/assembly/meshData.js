import { mergeBounds } from "../urdf/kinematics.js";

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

export function assemblyMeshDescriptor(topologyManifest) {
  const mesh = topologyManifest?.assembly?.mesh;
  return mesh && typeof mesh === "object" ? mesh : null;
}

export function assemblyUsesSelfContainedMesh(topologyManifest) {
  return String(assemblyMeshDescriptor(topologyManifest)?.addressing || "").trim() === "gltf-node-extras";
}

export function assemblyRootFromTopology(topologyManifest) {
  const root = topologyManifest?.assembly?.root;
  return root && typeof root === "object" ? root : null;
}

function toVectorArray(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const vector = value.slice(0, 3).map((component) => Number(component));
  return vector.every((component) => Number.isFinite(component)) ? vector : null;
}

function normalizeMateEndpoint(endpoint) {
  if (!endpoint || typeof endpoint !== "object") {
    return null;
  }
  const result = {
    part: String(endpoint.part || "").trim(),
    frame: String(endpoint.frame || "").trim()
  };
  const position = toVectorArray(endpoint.position);
  const orientation = toVectorArray(endpoint.orientation);
  if (position) {
    result.position = position;
  }
  if (orientation) {
    result.orientation = orientation;
  }
  const axes = endpoint.axes && typeof endpoint.axes === "object" ? endpoint.axes : null;
  if (axes) {
    const normalizedAxes = {};
    for (const key of ["x", "y", "z"]) {
      const axis = toVectorArray(axes[key]);
      if (axis) {
        normalizedAxes[key] = axis;
      }
    }
    if (Object.keys(normalizedAxes).length) {
      result.axes = normalizedAxes;
    }
  }
  return result.position || result.orientation || result.part || result.frame ? result : null;
}

export function assemblyMatesFromTopology(topologyManifest) {
  const mates = topologyManifest?.assemblyMates;
  if (!Array.isArray(mates)) {
    return [];
  }
  return mates
    .filter((mate) => mate && typeof mate === "object")
    .map((mate, index) => {
      const id = String(mate.id || `m${index + 1}`).trim() || `m${index + 1}`;
      return {
        id,
        label: String(mate.label || id).trim() || id,
        sourceLabel: String(mate.sourceLabel || mate.name || "").trim(),
        type: String(mate.type || mate.relation || "mate").trim(),
        relation: String(mate.relation || mate.type || "mate").trim(),
        fixed: String(mate.fixed || "").trim(),
        moving: String(mate.moving || "").trim(),
        parameters: mate.parameters && typeof mate.parameters === "object" ? mate.parameters : {},
        fixedEndpoint: normalizeMateEndpoint(mate.fixedEndpoint),
        movingEndpoint: normalizeMateEndpoint(mate.movingEndpoint)
      };
    });
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

export function rootAssemblyInspectionNodeId(root) {
  return String(root?.id || "").trim() || "root";
}

export function normalizeAssemblyInspectionNodeId(root, nodeId) {
  if (!root) {
    return "";
  }
  const rootId = rootAssemblyInspectionNodeId(root);
  const normalizedNodeId = String(nodeId || "").trim();
  if (!normalizedNodeId || normalizedNodeId === "root" || normalizedNodeId === rootId) {
    return rootId;
  }
  const node = findAssemblyNode(root, normalizedNodeId);
  return String(node?.id || "").trim() || rootId;
}

export function assemblyInspectionNode(root, nodeId) {
  if (!root) {
    return null;
  }
  return findAssemblyNode(root, normalizeAssemblyInspectionNodeId(root, nodeId)) || root;
}

export function selectableAssemblyNodeIdsForInspection(root, nodeId) {
  const inspectedNode = assemblyInspectionNode(root, nodeId);
  if (String(inspectedNode?.nodeType || "").trim() !== "assembly") {
    return [];
  }
  return (Array.isArray(inspectedNode?.children) ? inspectedNode.children : [])
    .map((node) => String(node?.id || "").trim())
    .filter(Boolean);
}

export function treeSelectableAssemblyNodeIdsForInspection(root, nodeId) {
  const inspectedNode = assemblyInspectionNode(root, nodeId);
  if (!inspectedNode) {
    return [];
  }
  const rootId = rootAssemblyInspectionNodeId(root);
  const inspectedNodeId = normalizeAssemblyInspectionNodeId(root, nodeId);
  return flattenAssemblyNodes(inspectedNode)
    .map((node) => String(node?.id || "").trim())
    .filter((id) => id && id !== rootId && id !== inspectedNodeId);
}

export function focusedLeafPartIdsForAssemblyInspection(root, nodeId) {
  const inspectedNodeId = normalizeAssemblyInspectionNodeId(root, nodeId);
  const rootId = rootAssemblyInspectionNodeId(root);
  if (!root || !inspectedNodeId || inspectedNodeId === rootId) {
    return [];
  }
  return descendantLeafPartIds(assemblyInspectionNode(root, inspectedNodeId));
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

export function resolveAssemblyPickedPartId(partId, {
  pickPartIdMap,
  validLeafPartIds = []
} = {}) {
  const normalizedPartId = String(partId || "").trim();
  if (!normalizedPartId) {
    return "";
  }
  const validLeafPartIdSet = validLeafPartIds instanceof Set
    ? validLeafPartIds
    : new Set(
      (Array.isArray(validLeafPartIds) ? validLeafPartIds : [])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
  const mappedPartId = pickPartIdMap instanceof Map
    ? String(pickPartIdMap.get(normalizedPartId) || "").trim()
    : "";
  if (mappedPartId) {
    return mappedPartId;
  }
  if (validLeafPartIdSet.size && validLeafPartIdSet.has(normalizedPartId)) {
    return normalizedPartId;
  }
  return mappedPartId || normalizedPartId;
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

function meshPartId(part) {
  return String(part?.occurrenceId || part?.id || "").trim();
}

function meshPartNumericValue(part, key) {
  return Math.max(0, Math.floor(Number(part?.[key]) || 0));
}

function meshPartIdMatches(part, ids) {
  const partIds = [
    String(part?.occurrenceId || "").trim(),
    String(part?.id || "").trim()
  ].filter(Boolean);
  return partIds.some((partId) => ids.has(partId));
}

function meshPartIdHasPrefix(part, prefixes) {
  const partIds = [
    String(part?.occurrenceId || "").trim(),
    String(part?.id || "").trim()
  ].filter(Boolean);
  return partIds.some((partId) => prefixes.some((prefix) => partId.startsWith(prefix)));
}

function meshPartsForTopologyLeaf(meshData, manifestPart) {
  const allParts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  const ids = new Set(
    [manifestPart?.occurrenceId, manifestPart?.id]
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const exactParts = allParts.filter((part) => meshPartIdMatches(part, ids));
  if (exactParts.length) {
    return exactParts;
  }
  const prefixes = [...ids].map((id) => `${id}.`);
  return prefixes.length ? allParts.filter((part) => meshPartIdHasPrefix(part, prefixes)) : [];
}

export function buildSelfContainedAssemblyMeshData(topologyManifest, meshData) {
  const assemblyRoot = assemblyRootFromTopology(topologyManifest);
  if (!assemblyRoot) {
    throw new Error("Assembly topology is missing assembly.root");
  }
  const manifestParts = flattenAssemblyLeafParts(assemblyRoot);
  const partSources = [];
  const meshlessLeafPartIds = [];
  for (const manifestPart of manifestParts) {
    const partId = String(manifestPart?.id || manifestPart?.occurrenceId || "").trim();
    const occurrenceId = String(manifestPart?.occurrenceId || manifestPart?.id || "").trim();
    const sourceParts = meshPartsForTopologyLeaf(meshData, manifestPart);
    if (!sourceParts.length) {
      const meshlessLeafPartId = occurrenceId || partId;
      if (meshlessLeafPartId) {
        meshlessLeafPartIds.push(meshlessLeafPartId);
      }
      continue;
    }
    partSources.push({
      manifestPart,
      sourceParts
    });
  }
  if (!partSources.length) {
    throw new Error("Assembly topology did not match any renderable GLB nodes");
  }
  let totalVertexCount = 0;
  let totalIndexCount = 0;
  for (const { sourceParts } of partSources) {
    for (const sourcePart of sourceParts) {
      totalVertexCount += meshPartNumericValue(sourcePart, "vertexCount");
      totalIndexCount += meshPartNumericValue(sourcePart, "triangleCount") * 3;
    }
  }
  const sourceVertices = meshData?.vertices || new Float32Array(0);
  const sourceNormals = meshData?.normals || new Float32Array(0);
  const sourceColors = meshData?.colors || new Float32Array(0);
  const sourceSurfaceEdgeBarycentric = meshData?.surfaceEdgeBarycentric || new Float32Array(0);
  const sourceSurfaceEdgeClass = meshData?.surfaceEdgeClass || new Uint8Array(0);
  const sourceIndices = meshData?.indices || new Uint32Array(0);
  const hasSourceColors = sourceColors.length === sourceVertices.length && sourceColors.length > 0;
  const hasSurfaceEdgeAttributes =
    sourceSurfaceEdgeBarycentric.length === sourceVertices.length &&
    sourceSurfaceEdgeClass.length === sourceVertices.length &&
    sourceVertices.length > 0;
  const vertices = new Float32Array(totalVertexCount * 3);
  const normals = new Float32Array(totalVertexCount * 3);
  const colors = hasSourceColors ? new Float32Array(totalVertexCount * 3) : new Float32Array(0);
  const surfaceEdgeBarycentric = hasSurfaceEdgeAttributes ? new Float32Array(totalVertexCount * 3) : new Float32Array(0);
  const surfaceEdgeClass = hasSurfaceEdgeAttributes ? new Uint8Array(totalVertexCount * 3) : new Uint8Array(0);
  const indices = new Uint32Array(totalIndexCount);
  const parts = [];
  let vertexOffset = 0;
  let indexOffset = 0;

  for (const { manifestPart, sourceParts } of partSources) {
    const partId = String(manifestPart?.id || manifestPart?.occurrenceId || "").trim();
    const occurrenceId = String(manifestPart?.occurrenceId || manifestPart?.id || "").trim();
    const firstMeshPart = sourceParts[0];
    const partVertexOffset = vertexOffset;
    const partTriangleOffset = Math.floor(indexOffset / 3);
    const sourcePartRanges = [];

    for (const sourcePart of sourceParts) {
      const sourceVertexOffset = meshPartNumericValue(sourcePart, "vertexOffset");
      const sourceVertexCount = meshPartNumericValue(sourcePart, "vertexCount");
      const sourceTriangleOffset = meshPartNumericValue(sourcePart, "triangleOffset");
      const sourceTriangleCount = meshPartNumericValue(sourcePart, "triangleCount");
      const rangeTriangleOffset = Math.floor(indexOffset / 3) - partTriangleOffset;
      sourcePartRanges.push({
        occurrenceId: meshPartId(sourcePart),
        primitiveIndex: meshPartNumericValue(sourcePart, "primitiveIndex"),
        triangleOffset: rangeTriangleOffset,
        triangleCount: sourceTriangleCount
      });
      const sourcePositionStart = sourceVertexOffset * 3;
      const sourcePositionEnd = sourcePositionStart + sourceVertexCount * 3;
      vertices.set(sourceVertices.subarray(sourcePositionStart, sourcePositionEnd), vertexOffset * 3);
      if (sourceNormals.length >= sourcePositionEnd) {
        normals.set(sourceNormals.subarray(sourcePositionStart, sourcePositionEnd), vertexOffset * 3);
      }
      if (hasSourceColors && sourceColors.length >= sourcePositionEnd) {
        colors.set(sourceColors.subarray(sourcePositionStart, sourcePositionEnd), vertexOffset * 3);
      }
      if (hasSurfaceEdgeAttributes && sourceSurfaceEdgeBarycentric.length >= sourcePositionEnd) {
        surfaceEdgeBarycentric.set(sourceSurfaceEdgeBarycentric.subarray(sourcePositionStart, sourcePositionEnd), vertexOffset * 3);
      }
      if (hasSurfaceEdgeAttributes && sourceSurfaceEdgeClass.length >= sourcePositionEnd) {
        surfaceEdgeClass.set(sourceSurfaceEdgeClass.subarray(sourcePositionStart, sourcePositionEnd), vertexOffset * 3);
      }
      const sourceIndexStart = sourceTriangleOffset * 3;
      const sourceIndexEnd = sourceIndexStart + sourceTriangleCount * 3;
      for (let index = sourceIndexStart; index < sourceIndexEnd; index += 1) {
        indices[indexOffset] = sourceIndices[index] - sourceVertexOffset + vertexOffset;
        indexOffset += 1;
      }
      vertexOffset += sourceVertexCount;
    }

    const sourcePath = String(manifestPart?.sourcePath || "").trim();
    const displayName = String(
      manifestPart?.displayName ||
      manifestPart?.instancePath ||
      manifestPart?.occurrenceId ||
      sourcePath ||
      firstMeshPart?.label ||
      firstMeshPart?.name ||
      meshPartId(firstMeshPart)
    ).trim();
    const sourceBounds = mergeBounds(sourceParts.map((part) => part.bounds));
    parts.push({
      ...firstMeshPart,
      ...manifestPart,
      id: partId || occurrenceId || meshPartId(firstMeshPart),
      occurrenceId: occurrenceId || partId || meshPartId(firstMeshPart),
      name: displayName,
      label: displayName,
      nodeType: "part",
      sourceKind: String(manifestPart?.sourceKind || "").trim(),
      sourcePath,
      partSourcePath: sourcePath,
      sourceBounds,
      bounds: manifestPart?.bbox || sourceBounds,
      transform: toTransformArray(manifestPart?.worldTransform || manifestPart?.transform),
      hasSourceColors: manifestPartUsesSourceColors(manifestPart) && (
        hasSourceColors || sourceParts.some((part) => !!part.hasSourceColors || !!part.color)
      ),
      vertexOffset: partVertexOffset,
      vertexCount: vertexOffset - partVertexOffset,
      triangleOffset: partTriangleOffset,
      triangleCount: Math.floor(indexOffset / 3) - partTriangleOffset,
      sourcePartRanges,
      edgeIndexOffset: 0,
      edgeIndexCount: 0
    });
  }
  return {
    ...meshData,
    vertices,
    indices,
    normals,
    colors,
    surfaceEdgeBarycentric,
    surfaceEdgeClass,
    edge_indices: new Uint32Array(0),
    parts,
    bounds: mergeBounds(parts.map((part) => part.bounds)) || meshData?.bounds,
    assemblyRoot,
    assemblyMates: assemblyMatesFromTopology(topologyManifest),
    meshlessLeafPartIds,
    partTransformsBaked: true,
    has_source_colors: hasSourceColors
  };
}

function manifestPartUsesSourceColors(part) {
  return part?.useSourceColors !== false;
}

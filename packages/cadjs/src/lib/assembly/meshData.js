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

// An occurrence override colour arrives as linear-RGB floats (the descriptor authors it in the
// renderer's working space). The baked composer wrote those floats straight into vertex colours;
// the shared-geometry composer instead drives them through the material via part.color, which the
// viewer parses as an sRGB hex string (readSourceColor -> new THREE.Color, decoded back to linear).
// Encoding linear -> sRGB hex here makes that round-trip land on the same linear albedo the baked
// path shaded, so a flat override renders pixel-identically without baking per-occurrence vertices.
function linearChannelToSrgbByte(channel) {
  const clamped = Math.min(1, Math.max(0, Number(channel) || 0));
  const srgb = clamped <= 0.0031308
    ? clamped * 12.92
    : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
  return Math.round(Math.min(1, Math.max(0, srgb)) * 255);
}

function linearRgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) {
    return null;
  }
  const hex = rgb
    .slice(0, 3)
    .map((channel) => linearChannelToSrgbByte(channel).toString(16).padStart(2, "0"))
    .join("");
  return `#${hex}`;
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

function directChildAssemblyNodeIds(node) {
  return (Array.isArray(node?.children) ? node.children : [])
    .map((child) => String(child?.id || "").trim())
    .filter(Boolean);
}

export function selectableAssemblyNodeIdsForInspection(root, nodeId) {
  const inspectedNode = assemblyInspectionNode(root, nodeId);
  return directChildAssemblyNodeIds(inspectedNode);
}

export function treeSelectableAssemblyNodeIdsForInspection(root, nodeId) {
  const inspectedNode = assemblyInspectionNode(root, nodeId);
  return directChildAssemblyNodeIds(inspectedNode);
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

// --- Component-GLB package composition ------------------------------------------
//
// A package's component GLBs are meshed once in their LOCAL frame and instanced N
// times by the assembly descriptor. Composition keeps one component-local copy of
// each unique component's geometry (shared across every occurrence via sourceMesh /
// sourceMeshKey) and places each occurrence with its 16-float transform applied as
// the render Mesh's matrix — never baked into vertices. Only occurrence *bounds* are
// pre-transformed here (transformPointInto), so auto-zoom and picking see world-space
// extents without duplicating vertex data per occurrence.

function transformPointInto(out, base, matrix, x, y, z) {
  out[base] = matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3];
  out[base + 1] = matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7];
  out[base + 2] = matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11];
}

function matrixDeterminant3(matrix) {
  return (
    matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9]) -
    matrix[1] * (matrix[4] * matrix[10] - matrix[6] * matrix[8]) +
    matrix[2] * (matrix[4] * matrix[9] - matrix[5] * matrix[8])
  );
}

function componentMeshDataFor(componentMeshDataByCid, cid) {
  if (!componentMeshDataByCid) {
    return null;
  }
  if (typeof componentMeshDataByCid.get === "function") {
    return componentMeshDataByCid.get(cid) || null;
  }
  return componentMeshDataByCid[cid] || null;
}

/**
 * Compose a renderable meshData from an assembly-package descriptor plus a map of
 * already-parsed component meshDatas (one per unique component cid, each from
 * buildMeshDataFromGlbBuffer on its component GLB). Each occurrence's transform is
 * baked into the copied vertices/normals (partTransformsBaked: true), so the result
 * is drop-in for the same renderer path the monolithic .step.glb uses.
 *
 * Output parts carry occurrenceId = the assembly occurrence id and componentId =
 * the source component cid; sourcePartRanges keep the COMPONENT-LOCAL occurrenceId +
 * primitiveIndex so picks resolve against that component's own selector runtime
 * (the occurrence id then namespaces the resolved selector).
 */
// World-space AABB of a component's local box under an occurrence transform (row-major
// 4x4). Used for per-occurrence bounds now that vertices are no longer world-baked.
function boundsForTransformedBox(box, matrix) {
  if (!box || !Array.isArray(box.min) || !Array.isArray(box.max) || !Array.isArray(matrix) || matrix.length !== 16) {
    return box || null;
  }
  const [nx, ny, nz] = box.min;
  const [xx, xy, xz] = box.max;
  const corners = [
    [nx, ny, nz], [xx, ny, nz], [nx, xy, nz], [xx, xy, nz],
    [nx, ny, xz], [xx, ny, xz], [nx, xy, xz], [xx, xy, xz]
  ];
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  const out = [0, 0, 0];
  for (const [x, y, z] of corners) {
    transformPointInto(out, 0, matrix, x, y, z);
    for (let a = 0; a < 3; a += 1) {
      if (out[a] < min[a]) min[a] = out[a];
      if (out[a] > max[a]) max[a] = out[a];
    }
  }
  return Number.isFinite(min[0]) ? { min, max } : (box || null);
}

export function buildComposedPackageMeshData(descriptor, componentMeshDataByCid) {
  const occurrences = Array.isArray(descriptor?.occurrences) ? descriptor.occurrences : [];
  if (!occurrences.length) {
    throw new Error("Assembly package descriptor has no occurrences");
  }

  const placements = [];
  const missingComponentIds = [];
  for (const occurrence of occurrences) {
    const cid = String(occurrence?.component || "").trim();
    const componentMeshData = componentMeshDataFor(componentMeshDataByCid, cid);
    const sourceParts = Array.isArray(componentMeshData?.parts) ? componentMeshData.parts : [];
    if (!componentMeshData || !sourceParts.length) {
      if (cid) {
        missingComponentIds.push(cid);
      }
      continue;
    }
    placements.push({ occurrence, componentMeshData, sourceParts });
  }
  if (!placements.length) {
    throw new Error("Assembly package matched no renderable component GLBs");
  }

  // Shared-geometry package rendering. Baking each occurrence's transform into fresh
  // world-space vertices inflates GPU memory ~12x on large packages (falcon_heavy: 114k
  // unique -> 1.4M composed) and stalls the main thread. Instead, every occurrence renders
  // as a THREE.Mesh over its component's OWN geometry — uploaded once per cid (cadScene
  // caches by sourceMeshKey) and placed by its occurrence transform at render time
  // (partTransformsBaked: false). The top-level arrays hold each unique component's geometry
  // ONCE, only for the render gate + the whole-mesh fallback (which per-part packages never
  // hit). Selectors are unaffected: sourcePartRanges are component-local triangle offsets and
  // the per-occurrence selector runtime is built + placed from the occurrence transform
  // elsewhere; mirrored occurrences render correctly because the surface material is DoubleSide.

  // One copy of each unique component's geometry (component-local) for the gate/fallback.
  const uniqueComponents = new Map();
  for (const placement of placements) {
    const cid = String(placement.occurrence?.component || "").trim();
    if (cid && !uniqueComponents.has(cid)) {
      uniqueComponents.set(cid, placement.componentMeshData);
    }
  }
  let uniqueVertexCount = 0;
  let uniqueIndexCount = 0;
  for (const component of uniqueComponents.values()) {
    uniqueVertexCount += Math.floor((component?.vertices?.length || 0) / 3);
    uniqueIndexCount += component?.indices?.length || 0;
  }
  const vertices = new Float32Array(uniqueVertexCount * 3);
  const normals = new Float32Array(uniqueVertexCount * 3);
  const indices = new Uint32Array(uniqueIndexCount);
  {
    let uniqueVertexOffset = 0;
    let uniqueIndexOffset = 0;
    for (const component of uniqueComponents.values()) {
      const cv = component?.vertices || new Float32Array(0);
      const cn = component?.normals || new Float32Array(0);
      const ci = component?.indices || new Uint32Array(0);
      vertices.set(cv, uniqueVertexOffset * 3);
      if (cn.length === cv.length) {
        normals.set(cn, uniqueVertexOffset * 3);
      }
      for (let i = 0; i < ci.length; i += 1) {
        indices[uniqueIndexOffset + i] = ci[i] + uniqueVertexOffset;
      }
      uniqueVertexOffset += Math.floor(cv.length / 3);
      uniqueIndexOffset += ci.length;
    }
  }

  const parts = [];
  for (const { occurrence, componentMeshData, sourceParts } of placements) {
    // Component geometry loads in CAD units (mm) and the occurrence transform is authored in
    // mm, so it places each (local-frame) component directly. Applied as the Mesh matrix.
    const matrix = toTransformArray(occurrence?.transform);
    const mirrored = matrixDeterminant3(matrix) < 0;
    const occurrenceId = String(occurrence?.id || "").trim();
    const cid = String(occurrence?.component || "").trim();
    const overrideColor = toVectorArray(occurrence?.color);
    // Optional per-occurrence PBR overrides (descriptor "material") and
    // opacity (4th color channel or material.opacity). linearRgbToHex drops
    // alpha by design, so opacity must ride separately.
    const overrideMaterial =
      occurrence?.material && typeof occurrence.material === "object" && !Array.isArray(occurrence.material)
        ? occurrence.material
        : null;
    // NB: toVectorArray keeps only RGB, so alpha must come from the raw
    // descriptor color array.
    const rawColor = occurrence?.color;
    const overrideAlpha = Array.isArray(rawColor) && rawColor.length >= 4 && Number.isFinite(Number(rawColor[3]))
      ? Number(rawColor[3])
      : null;
    const overrideOpacity = overrideAlpha !== null && overrideAlpha < 0.999
      ? overrideAlpha
      : (overrideMaterial && Number.isFinite(Number(overrideMaterial.opacity)) ? Number(overrideMaterial.opacity) : null);
    const sourceVertices = componentMeshData?.vertices || new Float32Array(0);
    const sourceColors = componentMeshData?.colors || new Float32Array(0);
    const hasComponentColors = sourceColors.length === sourceVertices.length && sourceColors.length > 0;
    // A per-occurrence override colour drives the material (part.color) — it can't bake into
    // shared vertices. A component's own COLOR_0 rides on the shared geometry and is used only
    // when there is no override.
    const useComponentVertexColors = !overrideColor && hasComponentColors;

    // Selector face ranges: triangle offsets into the COMPONENT's own geometry (the render
    // mesh via sourceMesh), so buildGlbFaceIdsForPart maps render triangles -> faces. These are
    // component-local (unchanged by placement), so face selection is preserved.
    const sourcePartRanges = sourceParts.map((sourcePart) => ({
      occurrenceId: occurrenceId || meshPartId(sourcePart),
      primitiveIndex: meshPartNumericValue(sourcePart, "primitiveIndex"),
      triangleOffset: meshPartNumericValue(sourcePart, "triangleOffset"),
      triangleCount: meshPartNumericValue(sourcePart, "triangleCount")
    }));

    const bounds = boundsForTransformedBox(componentMeshData?.bounds, matrix);
    const displayName = String(occurrence?.name || occurrenceId || cid || meshPartId(sourceParts[0])).trim();
    parts.push({
      id: occurrenceId || cid,
      occurrenceId: occurrenceId || cid,
      componentId: cid,
      name: displayName,
      label: displayName,
      nodeType: "part",
      transform: matrix,
      mirrored,
      bounds,
      sourceBounds: bounds,
      color: (overrideColor && linearRgbToHex(overrideColor)) || sourceParts[0]?.color || null,
      material: overrideMaterial,
      opacity: overrideOpacity !== null ? overrideOpacity : undefined,
      hasSourceColors: useComponentVertexColors,
      // Shared component geometry: cadScene caches one BufferGeometry per sourceMeshKey and
      // reuses it across every occurrence of this cid (+ colour mode).
      sourceMesh: componentMeshData,
      sourceMeshKey: `${cid}:${useComponentVertexColors ? "src" : "flat"}`,
      vertexCount: Math.floor(sourceVertices.length / 3),
      triangleCount: Math.floor((componentMeshData?.indices?.length || 0) / 3),
      sourcePartRanges,
      edgeIndexOffset: 0,
      edgeIndexCount: 0
    });
  }

  return {
    vertices,
    indices,
    normals,
    colors: new Float32Array(0),
    surfaceEdgeBarycentric: new Float32Array(0),
    surfaceEdgeClass: new Float32Array(0),
    edge_indices: new Uint32Array(0),
    parts,
    assemblyRoot: buildPackageAssemblyRoot(descriptor, parts),
    bounds: mergeBounds(parts.map((part) => part.bounds)),
    assemblyMates: assemblyMatesFromTopology(descriptor),
    missingComponentIds,
    // Each occurrence is placed by its transform at render time over shared component
    // geometry (each part carries its own sourceMesh above); nothing here is baked into
    // world space.
    partTransformsBaked: false,
    has_source_colors: false
  };
}

// The package descriptor records a flat list of occurrences (the assembly hierarchy is collapsed
// at emit time), so synthesize a one-level assembly tree — a root node whose children are the
// placed parts — so the viewer's structure tree is expandable and every occurrence is selectable.
function enrichPackageAssemblyNode(node, partById) {
  const rawChildren = Array.isArray(node?.children) ? node.children : [];
  const children = rawChildren.map((child) => enrichPackageAssemblyNode(child, partById));
  const nodeType = String(node?.nodeType || "").trim() || (children.length ? "subassembly" : "part");
  const id = String(node?.id || "").trim();
  const name = String(node?.name || node?.label || id).trim();
  const declaredLeafIds = Array.isArray(node?.leafPartIds)
    ? node.leafPartIds.map((leafId) => String(leafId || "").trim()).filter(Boolean)
    : [];
  const leafPartIds = declaredLeafIds.length
    ? declaredLeafIds
    : (children.length
      ? children.flatMap((child) => child.leafPartIds)
      : (id ? [id] : []));
  const out = { id, occurrenceId: id, name, label: name, nodeType, leafPartIds, children };
  if (nodeType === "part") {
    // Enrich the leaf with its composed render part (transform/bounds/color drive highlighting).
    const part = partById.get(id);
    if (part) {
      out.componentId = part.componentId;
      out.transform = part.transform;
      out.bounds = part.bounds;
      out.sourceBounds = part.sourceBounds;
      out.color = part.color;
    }
  } else {
    out.transform = [...IDENTITY_TRANSFORM];
    out.bounds = mergeBounds(children.map((child) => child.bounds));
  }
  return out;
}

function buildPackageAssemblyRoot(descriptor, parts) {
  // A single-component part has no internal assembly structure: it renders as a topology
  // tree (solids/faces/edges) exactly like a monolithic STEP part. Returning null lets
  // buildStepTreeRoot fall through to buildStepPartRoot instead of showing a spurious
  // one-node "assembly" wrapper (which the part view can't render → "No assembly tree").
  if (String(descriptor?.entryKind || "").trim() === "part") {
    return null;
  }
  const partList = Array.isArray(parts) ? parts : [];
  const partById = new Map(partList.map((part) => [String(part.id), part]));
  // Preferred: the nested hierarchy the descriptor records (subassembly grouping over leaves),
  // so the structure tree can drill into / isolate subassemblies just like a monolithic STEP.
  const descriptorRoot = descriptor?.assembly?.root;
  if (descriptorRoot && typeof descriptorRoot === "object") {
    return enrichPackageAssemblyNode(descriptorRoot, partById);
  }
  // Fallback (legacy descriptor without a hierarchy): a flat root over the placed parts.
  if (!partList.length) {
    return null;
  }
  const children = partList.map((part) => ({
    id: part.id,
    occurrenceId: part.occurrenceId,
    componentId: part.componentId,
    name: part.name,
    label: part.label,
    nodeType: "part",
    transform: part.transform,
    bounds: part.bounds,
    sourceBounds: part.sourceBounds,
    color: part.color,
    leafPartIds: [part.id],
    children: []
  }));
  const rootName = String(descriptor?.rootName || "").trim() || "assembly";
  return {
    id: rootName,
    name: rootName,
    label: rootName,
    nodeType: "assembly",
    transform: [...IDENTITY_TRANSFORM],
    bounds: mergeBounds(children.map((child) => child.bounds)),
    leafPartIds: children.map((child) => child.id),
    children
  };
}

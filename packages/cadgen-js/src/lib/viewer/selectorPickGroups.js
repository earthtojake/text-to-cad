import { ensureFacePickBvh } from "./raycastBvh.js";

export const TOPOLOGY_FACE_ID_NONE = 0xffffffff;

export function buildFacePickMesh(THREE, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  if (!(proxy.facePositions instanceof Float32Array) || !(proxy.faceIndices instanceof Uint32Array) || !proxy.faceIndices.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(proxy.facePositions, 3));
  geometry.setIndex(new THREE.BufferAttribute(proxy.faceIndices, 1));
  const material = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
    colorWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.faceIds = proxy.faceIds || new Uint32Array(0);
  mesh.frustumCulled = false;
  return mesh;
}

function faceRunColumnIndexes(selectorRuntime) {
  const columns = Array.isArray(selectorRuntime?.proxy?.faceRunColumns) && selectorRuntime.proxy.faceRunColumns.length
    ? selectorRuntime.proxy.faceRunColumns
    : ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"];
  return {
    stride: columns.length,
    occurrenceRow: Math.max(0, columns.indexOf("occurrenceRow")),
    primitiveIndex: Math.max(0, columns.indexOf("primitiveIndex")),
    triangleStart: Math.max(0, columns.indexOf("triangleStart")),
    triangleCount: Math.max(0, columns.indexOf("triangleCount")),
    faceRow: Math.max(0, columns.indexOf("faceRow"))
  };
}

export function buildGlbFaceIdsForPart(part, selectorRuntime) {
  const runs = selectorRuntime?.proxy?.faceRuns;
  const triangleCount = Math.max(0, Math.floor(Number(part?.triangleCount || 0)));
  if (!(runs instanceof Uint32Array) || !runs.length || triangleCount <= 0) {
    return null;
  }
  const occurrenceId = String(part?.occurrenceId || part?.id || "").trim();
  if (!occurrenceId) {
    return null;
  }
  const primitiveIndex = Math.max(0, Math.floor(Number(part?.primitiveIndex || 0)));
  const columns = faceRunColumnIndexes(selectorRuntime);
  const faceIds = new Uint32Array(triangleCount);
  faceIds.fill(TOPOLOGY_FACE_ID_NONE);
  const sourcePartRanges = Array.isArray(part?.sourcePartRanges)
    ? part.sourcePartRanges
      .map((range) => ({
        occurrenceId: String(range?.occurrenceId || "").trim(),
        primitiveIndex: Math.max(0, Math.floor(Number(range?.primitiveIndex || 0))),
        triangleOffset: Math.max(0, Math.floor(Number(range?.triangleOffset || 0))),
        triangleCount: Math.max(0, Math.floor(Number(range?.triangleCount || 0)))
      }))
      .filter((range) => range.occurrenceId && range.triangleCount > 0)
    : [];
  let matched = false;
  for (let offset = 0; offset + columns.stride <= runs.length; offset += columns.stride) {
    const runOccurrenceId = selectorRuntime?.occurrenceIdByRowIndex?.get?.(Number(runs[offset + columns.occurrenceRow]));
    const triangleStart = Number(runs[offset + columns.triangleStart]);
    const runTriangleCount = Number(runs[offset + columns.triangleCount]);
    const faceRow = Number(runs[offset + columns.faceRow]);
    if (
      !Number.isInteger(triangleStart) ||
      !Number.isInteger(runTriangleCount) ||
      !Number.isInteger(faceRow) ||
      triangleStart < 0 ||
      runTriangleCount <= 0 ||
      faceRow < 0
    ) {
      continue;
    }
    if (sourcePartRanges.length) {
      for (const range of sourcePartRanges) {
        if (runOccurrenceId !== range.occurrenceId || Number(runs[offset + columns.primitiveIndex]) !== range.primitiveIndex) {
          continue;
        }
        if (triangleStart >= range.triangleCount) {
          continue;
        }
        const start = range.triangleOffset + triangleStart;
        const end = Math.min(range.triangleOffset + triangleStart + runTriangleCount, range.triangleOffset + range.triangleCount, triangleCount);
        if (end <= start || start >= triangleCount) {
          continue;
        }
        faceIds.fill(faceRow, start, end);
        matched = true;
      }
      continue;
    }
    if (runOccurrenceId !== occurrenceId || Number(runs[offset + columns.primitiveIndex]) !== primitiveIndex || triangleStart >= triangleCount) {
      continue;
    }
    const end = Math.min(triangleStart + runTriangleCount, triangleCount);
    faceIds.fill(faceRow, triangleStart, end);
    matched = true;
  }
  return matched ? faceIds : null;
}

export function buildGlbFaceIdsForMesh(meshData, selectorRuntime) {
  const triangleCount = Math.floor((meshData?.indices?.length || 0) / 3);
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  if (triangleCount <= 0 || !parts.length) {
    return null;
  }
  const faceIds = new Uint32Array(triangleCount);
  faceIds.fill(TOPOLOGY_FACE_ID_NONE);
  let matched = false;
  for (const part of parts) {
    const partFaceIds = buildGlbFaceIdsForPart(part, selectorRuntime);
    if (!partFaceIds) {
      continue;
    }
    const triangleOffset = Math.max(0, Math.floor(Number(part?.triangleOffset || 0)));
    const end = Math.min(triangleOffset + partFaceIds.length, faceIds.length);
    if (end <= triangleOffset) {
      continue;
    }
    faceIds.set(partFaceIds.subarray(0, end - triangleOffset), triangleOffset);
    matched = true;
  }
  return matched ? faceIds : null;
}

function sourcePartForRecord(record, partId) {
  const sourcePart = record?.sourcePart || record?.part || null;
  const sourcePartId = String(sourcePart?.id || sourcePart?.occurrenceId || "").trim();
  return sourcePartId && sourcePartId === partId ? sourcePart : null;
}

export function syncDisplayMeshFaceIds(runtime, meshData, selectorRuntime) {
  const records = Array.isArray(runtime?.displayRecords) ? runtime.displayRecords : [];
  if (!records.length) {
    return;
  }
  const partsById = new Map(
    (Array.isArray(meshData?.parts) ? meshData.parts : [])
      .map((part) => [String(part?.id || ""), part])
      .filter(([partId]) => partId)
  );
  for (const record of records) {
    const mesh = record?.mesh;
    if (!mesh?.userData) {
      continue;
    }
    let faceIds = null;
    const partId = String(record?.partId || "").trim();
    if (partId && partId !== "__model__") {
      const part = partsById.get(partId) || sourcePartForRecord(record, partId);
      faceIds = part ? buildGlbFaceIdsForPart(part, selectorRuntime) : null;
    } else {
      faceIds = buildGlbFaceIdsForMesh(meshData, selectorRuntime);
    }
    if (faceIds) {
      mesh.userData.faceIds = faceIds;
    } else {
      delete mesh.userData.faceIds;
    }
  }
}

export function buildEdgePickLines(THREE, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  if (!(proxy.edgePositions instanceof Float32Array) || !(proxy.edgeIndices instanceof Uint32Array) || !proxy.edgeIndices.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(proxy.edgePositions, 3));
  geometry.setIndex(new THREE.BufferAttribute(proxy.edgeIndices, 1));
  const material = new THREE.LineBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
  });
  const lines = new THREE.LineSegments(geometry, material);
  lines.userData.edgeIds = proxy.edgeIds || new Uint32Array(0);
  lines.frustumCulled = false;
  return lines;
}

export function buildVertexPickPoints(THREE, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  if (!(proxy.vertexPositions instanceof Float32Array) || !proxy.vertexPositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(proxy.vertexPositions, 3));
  const material = new THREE.PointsMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0,
    size: 1.5,
    sizeAttenuation: false,
    depthWrite: false,
    toneMapped: false,
  });
  const points = new THREE.Points(geometry, material);
  points.userData.vertexIds = proxy.vertexIds || new Uint32Array(0);
  points.frustumCulled = false;
  return points;
}

function clearPickGroup(group, clearSceneGroup) {
  if (typeof clearSceneGroup === "function") {
    clearSceneGroup(group);
    return;
  }
  while (group?.children?.length) {
    group.remove(group.children[0]);
  }
}

export function syncSelectorPickGroups(runtime, selectorRuntime, modelOffset = null, {
  clearSceneGroup = null
} = {}) {
  if (!runtime?.THREE || !runtime?.facePickGroup || !runtime?.edgePickGroup || !runtime?.vertexPickGroup) {
    return;
  }

  clearPickGroup(runtime.facePickGroup, clearSceneGroup);
  clearPickGroup(runtime.edgePickGroup, clearSceneGroup);
  clearPickGroup(runtime.vertexPickGroup, clearSceneGroup);
  runtime.facePickMesh = null;
  runtime.edgePickLines = null;
  runtime.vertexPickPoints = null;
  runtime.edgePickObjects = [];

  const facePickMesh = buildFacePickMesh(runtime.THREE, selectorRuntime);
  if (facePickMesh) {
    runtime.facePickMesh = facePickMesh;
    runtime.facePickGroup.add(facePickMesh);
  }

  const edgePickLines = buildEdgePickLines(runtime.THREE, selectorRuntime);
  if (edgePickLines) {
    runtime.edgePickLines = edgePickLines;
    runtime.edgePickGroup.add(edgePickLines);
    runtime.edgePickObjects = [edgePickLines];
  }

  const vertexPickPoints = buildVertexPickPoints(runtime.THREE, selectorRuntime);
  if (vertexPickPoints) {
    runtime.vertexPickPoints = vertexPickPoints;
    runtime.vertexPickGroup.add(vertexPickPoints);
  }

  if (modelOffset) {
    runtime.facePickGroup.position.copy(modelOffset);
    runtime.edgePickGroup.position.copy(modelOffset);
    runtime.vertexPickGroup.position.copy(modelOffset);
  } else {
    runtime.facePickGroup.position.set(0, 0, 0);
    runtime.edgePickGroup.position.set(0, 0, 0);
    runtime.vertexPickGroup.position.set(0, 0, 0);
  }
  runtime.facePickGroup.updateMatrixWorld(true);
  runtime.edgePickGroup.updateMatrixWorld(true);
  runtime.vertexPickGroup.updateMatrixWorld(true);
  ensureFacePickBvh(runtime, selectorRuntime);
}

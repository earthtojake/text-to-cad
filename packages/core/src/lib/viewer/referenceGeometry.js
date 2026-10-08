export const REFERENCE_HOVER_COLOR = "#8dc5ff";
export const REFERENCE_SELECTED_COLOR = "#4f9dff";
export const REFERENCE_CORNER_COLOR = "#2563eb";
export const REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER = 3;
export const REFERENCE_HOVER_HIGHLIGHT_WIDTH_MULTIPLIER = REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER;
export const REFERENCE_HOVER_FILL_OPACITY = 0.3;
export const REFERENCE_SELECTED_FILL_OPACITY = 0.24;

function isPlanarFaceReference(reference) {
  const surfaceType = String(reference?.pickData?.surfaceType || reference?.pickData?.surface?.type || "")
    .trim()
    .toLowerCase();
  return !surfaceType || surfaceType.includes("plane") || surfaceType.includes("planar");
}

export function faceFillOffset(runtime, reference) {
  if (!isPlanarFaceReference(reference)) {
    return [0, 0, 0];
  }
  const normal = Array.isArray(reference?.pickData?.normal) ? reference.pickData.normal : null;
  if (!runtime?.camera || !runtime?.modelGroup || !normal || normal.length < 3) {
    return [0, 0, 0];
  }
  const normalLength = Math.hypot(normal[0], normal[1], normal[2]);
  if (normalLength <= 1e-9) {
    return [0, 0, 0];
  }
  const normalizedNormal = [
    normal[0] / normalLength,
    normal[1] / normalLength,
    normal[2] / normalLength
  ];
  const center = Array.isArray(reference?.pickData?.center) ? reference.pickData.center : [0, 0, 0];
  const modelOffset = runtime.modelGroup.position;
  const worldCenter = [
    Number(center[0] || 0) + Number(modelOffset?.x || 0),
    Number(center[1] || 0) + Number(modelOffset?.y || 0),
    Number(center[2] || 0) + Number(modelOffset?.z || 0)
  ];
  const toCamera = [
    runtime.camera.position.x - worldCenter[0],
    runtime.camera.position.y - worldCenter[1],
    runtime.camera.position.z - worldCenter[2]
  ];
  const facingSign =
    ((normalizedNormal[0] * toCamera[0]) + (normalizedNormal[1] * toCamera[1]) + (normalizedNormal[2] * toCamera[2])) >= 0
      ? 1
      : -1;
  const magnitude = Math.max(Number(runtime.modelRadius || 1) * 0.00075, 0.015);
  return [
    normalizedNormal[0] * facingSign * magnitude,
    normalizedNormal[1] * facingSign * magnitude,
    normalizedNormal[2] * facingSign * magnitude
  ];
}

export function buildFaceFillGeometryFromProxy(runtime, THREE, selectorRuntime, reference) {
  const proxy = selectorRuntime?.proxy || {};
  const triangleStart = Number(reference?.pickData?.triangleStart || 0);
  const triangleCount = Number(reference?.pickData?.triangleCount || 0);
  if (!(proxy.facePositions instanceof Float32Array) || !(proxy.faceIndices instanceof Uint32Array) || triangleCount <= 0) {
    return null;
  }
  const indexSlice = proxy.faceIndices.slice(triangleStart * 3, (triangleStart + triangleCount) * 3);
  if (!indexSlice.length) {
    return null;
  }
  const offset = faceFillOffset(runtime, reference);
  const positions = new Float32Array(indexSlice.length * 3);
  let writeOffset = 0;
  for (const vertexIndex of indexSlice) {
    const sourceIndex = Number(vertexIndex) * 3;
    positions[writeOffset] = proxy.facePositions[sourceIndex] + offset[0];
    positions[writeOffset + 1] = proxy.facePositions[sourceIndex + 1] + offset[1];
    positions[writeOffset + 2] = proxy.facePositions[sourceIndex + 2] + offset[2];
    writeOffset += 3;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geometry;
}

/**
 * A display mesh's face ids as runs, sorted by face row: `rows[i]` covers triangles
 * `starts[i]` to `ends[i]`. Built once per `faceIds` array (the scene sync replaces the array
 * whenever the ids change, and never writes into one it has published) and kept beside it, so
 * the fill of one face is a binary search per record rather than a walk over every triangle
 * on screen -- which, for each highlighted face on every hover, was the cost of a highlight.
 */
const faceRunIndexByFaceIds = new WeakMap();

export function faceRunIndex(faceIds) {
  const cached = faceRunIndexByFaceIds.get(faceIds);
  if (cached) {
    return cached;
  }
  const count = faceIds.length;
  let runCount = 0;
  for (let index = 0; index < count; index += 1) {
    if (index === 0 || faceIds[index] !== faceIds[index - 1]) runCount += 1;
  }
  const runRows = new Uint32Array(runCount);
  const runStarts = new Uint32Array(runCount);
  const runEnds = new Uint32Array(runCount);
  let run = -1;
  for (let index = 0; index < count; index += 1) {
    if (index === 0 || faceIds[index] !== faceIds[index - 1]) {
      run += 1;
      runRows[run] = faceIds[index];
      runStarts[run] = index;
    }
    runEnds[run] = index + 1;
  }
  // By row, and by position within a row: a face split into several runs keeps its order.
  const order = Array.from({ length: runCount }, (_, index) => index)
    .sort((left, right) => (runRows[left] - runRows[right]) || (runStarts[left] - runStarts[right]));
  const index = {
    rows: Uint32Array.from(order, (position) => runRows[position]),
    starts: Uint32Array.from(order, (position) => runStarts[position]),
    ends: Uint32Array.from(order, (position) => runEnds[position])
  };
  faceRunIndexByFaceIds.set(faceIds, index);
  return index;
}

function firstRunOfRow(index, rowIndex) {
  let low = 0;
  let high = index.rows.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (index.rows[middle] < rowIndex) low = middle + 1;
    else high = middle;
  }
  return low;
}

/**
 * The fill of one face, read off the display meshes on screen: every triangle whose face id is
 * the face's row, in record order and triangle order, through each mesh's live matrix.
 */
export function buildFaceFillGeometryFromDisplayMeshes(runtime, THREE, reference) {
  const rowIndex = Number(reference?.rowIndex);
  if (!Number.isInteger(rowIndex) || !Array.isArray(runtime?.displayRecords)) {
    return null;
  }
  const offset = faceFillOffset(runtime, reference);
  const vertex = new THREE.Vector3();
  const fillPositions = [];
  // A row outside what a Uint32Array holds is on no triangle.
  const searchable = rowIndex >= 0 && rowIndex <= 0xffffffff;
  for (const record of runtime.displayRecords) {
    const mesh = record?.mesh;
    const geometry = mesh?.geometry;
    const faceIds = mesh?.userData?.faceIds;
    const positions = geometry?.getAttribute?.("position");
    const indices = geometry?.getIndex?.();
    if (!(faceIds instanceof Uint32Array) || !positions || !indices || !indices.count || !searchable) {
      continue;
    }
    const triangleCount = Math.min(faceIds.length, Math.floor(indices.count / 3));
    const runs = faceRunIndex(faceIds);
    for (let run = firstRunOfRow(runs, rowIndex); run < runs.rows.length && runs.rows[run] === rowIndex; run += 1) {
      const end = Math.min(runs.ends[run], triangleCount);
      for (let triangleIndex = runs.starts[run]; triangleIndex < end; triangleIndex += 1) {
        for (let corner = 0; corner < 3; corner += 1) {
          const sourceIndex = indices.getX((triangleIndex * 3) + corner);
          vertex.set(positions.getX(sourceIndex), positions.getY(sourceIndex), positions.getZ(sourceIndex));
          vertex.applyMatrix4(mesh.matrix);
          fillPositions.push(vertex.x + offset[0], vertex.y + offset[1], vertex.z + offset[2]);
        }
      }
    }
  }
  if (!fillPositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(fillPositions), 3));
  return geometry;
}

/** The display record a reference belongs to, by longest matching part id.
 *
 * Same matching rule the selector transforms use: a record's ``partId`` either IS the
 * reference's occurrence id or is one of its ancestors (``o1`` owns ``o1.3``), and the most
 * specific owner wins. Returns null for a reference nothing on screen claims. */
export function displayRecordForReference(runtime, reference) {
  const occurrenceId = String(reference?.occurrenceId || reference?.pickData?.occurrenceId || "").trim();
  if (!occurrenceId || !Array.isArray(runtime?.displayRecords)) {
    return null;
  }
  let best = null;
  let bestLength = -1;
  for (const record of runtime.displayRecords) {
    const partId = String(record?.partId || "").trim();
    if (!partId || partId === "__model__") {
      continue;
    }
    if (occurrenceId !== partId && !occurrenceId.startsWith(`${partId}.`)) {
      continue;
    }
    if (partId.length > bestLength) {
      best = record;
      bestLength = partId.length;
    }
  }
  return best;
}

/** The exploded-view offset applied to a reference's part, or null when it has none.
 *
 * Selector geometry is world-at-REST: the exploded view moves the display mesh through
 * ``record.explodedViewMatrix`` and never touches the pick proxy, so a highlight sliced out of
 * that proxy needs this matrix to sit on the part the user is actually pointing at. Face fills
 * do not: they are rebuilt from the live display meshes, whose matrices already carry it.
 *
 * Deliberately NOT ``composeDisplayRecordEffectMatrix``: a parameter effect is already baked
 * into the transformed selector runtime the highlight reads, and applying it twice would send
 * the highlight to double the displacement. The exploded offset is the part no runtime carries.
 */
export function referenceExplodedViewMatrix(runtime, reference) {
  const record = displayRecordForReference(runtime, reference);
  const matrix = record?.explodedViewMatrix;
  return matrix?.elements?.length === 16 ? matrix : null;
}

export function buildEdgeLinePositionsFromProxy(selectorRuntime, reference) {
  const proxy = selectorRuntime?.proxy || {};
  const segmentStart = Number(reference?.pickData?.segmentStart || 0);
  const segmentCount = Number(reference?.pickData?.segmentCount || 0);
  if (!(proxy.edgePositions instanceof Float32Array) || !(proxy.edgeIndices instanceof Uint32Array) || segmentCount <= 0) {
    return null;
  }
  const indexSlice = proxy.edgeIndices.slice(segmentStart * 2, (segmentStart + segmentCount) * 2);
  if (!indexSlice.length) {
    return null;
  }
  const linePositions = new Float32Array(segmentCount * 6);
  let writeOffset = 0;
  for (let index = 0; index + 1 < indexSlice.length; index += 2) {
    const startIndex = indexSlice[index] * 3;
    const endIndex = indexSlice[index + 1] * 3;
    linePositions[writeOffset] = proxy.edgePositions[startIndex];
    linePositions[writeOffset + 1] = proxy.edgePositions[startIndex + 1];
    linePositions[writeOffset + 2] = proxy.edgePositions[startIndex + 2];
    linePositions[writeOffset + 3] = proxy.edgePositions[endIndex];
    linePositions[writeOffset + 4] = proxy.edgePositions[endIndex + 1];
    linePositions[writeOffset + 5] = proxy.edgePositions[endIndex + 2];
    writeOffset += 6;
  }
  return writeOffset === linePositions.length ? linePositions : linePositions.subarray(0, writeOffset);
}

export function buildAdjacentEdgeLinePositions(selectorRuntime, reference) {
  const selectors = Array.isArray(reference?.pickData?.adjacentSelectors) ? reference.pickData.adjacentSelectors : [];
  if (!selectors.length) {
    return null;
  }
  const positions = [];
  for (const selector of selectors) {
    const edgeReference =
      selectorRuntime?.referenceByDisplaySelector?.get?.(selector) ||
      selectorRuntime?.referenceByNormalizedSelector?.get?.(selector) ||
      null;
    const edgePositions = buildEdgeLinePositionsFromProxy(selectorRuntime, edgeReference);
    if (!edgePositions?.length) {
      continue;
    }
    positions.push(...edgePositions);
  }
  return positions.length ? positions : null;
}

export function buildFaceBoundaryLinePositions(selectorRuntime, reference) {
  return buildAdjacentEdgeLinePositions(selectorRuntime, reference);
}

export function createReferenceEdgeGeometryFromPoints(THREE, points) {
  if (!Array.isArray(points) || points.length < 2) {
    return null;
  }
  const linePositions = [];
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1];
    const end = points[index];
    if (!Array.isArray(start) || !Array.isArray(end) || start.length < 3 || end.length < 3) {
      continue;
    }
    linePositions.push(
      Number(start[0]),
      Number(start[1]),
      Number(start[2]),
      Number(end[0]),
      Number(end[1]),
      Number(end[2])
    );
  }
  if (!linePositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(linePositions), 3));
  return geometry;
}

export function buildVertexMarkerMesh(runtime, THREE, reference, {
  color,
  opacity,
  renderOrder = 27
} = {}) {
  const center = Array.isArray(reference?.pickData?.center) ? reference.pickData.center : null;
  if (!center || center.length < 3) {
    return null;
  }
  const radius = Math.max(Number(runtime?.modelRadius || 1) * 0.0045, 0.2);
  const geometry = new THREE.SphereGeometry(radius, 16, 16);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthTest: true,
    depthWrite: false,
    toneMapped: false
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(center[0], center[1], center[2]);
  mesh.renderOrder = renderOrder;
  return mesh;
}

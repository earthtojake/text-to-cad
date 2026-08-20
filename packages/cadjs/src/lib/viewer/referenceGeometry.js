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

export function buildFaceFillGeometryFromDisplayMeshes(runtime, THREE, reference) {
  const rowIndex = Number(reference?.rowIndex);
  if (!Number.isInteger(rowIndex) || !Array.isArray(runtime?.displayRecords)) {
    return null;
  }
  const offset = faceFillOffset(runtime, reference);
  const vertex = new THREE.Vector3();
  const fillPositions = [];
  for (const record of runtime.displayRecords) {
    const mesh = record?.mesh;
    const geometry = mesh?.geometry;
    const faceIds = mesh?.userData?.faceIds;
    const positions = geometry?.getAttribute?.("position");
    const indices = geometry?.getIndex?.();
    if (!(faceIds instanceof Uint32Array) || !positions || !indices || !indices.count) {
      continue;
    }
    const triangleCount = Math.min(faceIds.length, Math.floor(indices.count / 3));
    for (let triangleIndex = 0; triangleIndex < triangleCount; triangleIndex += 1) {
      if (Number(faceIds[triangleIndex]) !== rowIndex) {
        continue;
      }
      for (let corner = 0; corner < 3; corner += 1) {
        const sourceIndex = indices.getX((triangleIndex * 3) + corner);
        vertex.set(positions.getX(sourceIndex), positions.getY(sourceIndex), positions.getZ(sourceIndex));
        vertex.applyMatrix4(mesh.matrix);
        fillPositions.push(vertex.x + offset[0], vertex.y + offset[1], vertex.z + offset[2]);
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

export function createReferenceFaceLoopGeometry(THREE, loops) {
  if (!Array.isArray(loops) || !loops.length) {
    return null;
  }
  const linePositions = [];
  for (const loop of loops) {
    if (!Array.isArray(loop) || loop.length < 2) {
      continue;
    }
    for (let index = 0; index < loop.length; index += 1) {
      const start = loop[index];
      const end = loop[(index + 1) % loop.length];
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
  }
  if (!linePositions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(linePositions), 3));
  return geometry;
}

export function createReferenceFaceBoundaryGeometry(THREE, reference) {
  const pickData = reference?.pickData || {};
  const loopsMeta = Array.isArray(pickData?.loopsMeta) ? pickData.loopsMeta : [];
  const boundaryLoops = loopsMeta
    .filter((loopEntry) => Array.isArray(loopEntry?.points) && loopEntry.points.length >= 2)
    .map((loopEntry) => loopEntry.points);
  if (boundaryLoops.length) {
    return createReferenceFaceLoopGeometry(THREE, boundaryLoops);
  }

  const fallbackLoops = Array.isArray(pickData?.loops)
    ? pickData.loops.filter((loop) => Array.isArray(loop) && loop.length >= 2)
    : [];
  return createReferenceFaceLoopGeometry(THREE, fallbackLoops);
}

function selectOuterLoopPoints(pickData = {}) {
  const loopsMeta = Array.isArray(pickData?.loopsMeta) ? pickData.loopsMeta : [];
  const explicitOuter = loopsMeta.find((loop) => loop?.isOuter && Array.isArray(loop?.points) && loop.points.length >= 3);
  if (explicitOuter) {
    return explicitOuter.points;
  }
  const loops = Array.isArray(pickData?.loops) ? pickData.loops : [];
  return loops.find((loop) => Array.isArray(loop) && loop.length >= 3) || null;
}

function isFinitePoint2(point) {
  return Array.isArray(point) && point.length >= 2 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]));
}

function isFinitePoint3(point) {
  return Array.isArray(point) && point.length >= 3 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1])) && Number.isFinite(Number(point[2]));
}

function distanceSquared2d(a, b) {
  const dx = Number(a[0]) - Number(b[0]);
  const dy = Number(a[1]) - Number(b[1]);
  return dx * dx + dy * dy;
}

function distanceSquared3d(a, b) {
  const dx = Number(a[0]) - Number(b[0]);
  const dy = Number(a[1]) - Number(b[1]);
  const dz = Number(a[2]) - Number(b[2]);
  return dx * dx + dy * dy + dz * dz;
}

function sanitizeLoopPair(loop3d, loop2d) {
  const count = Math.min(
    Array.isArray(loop3d) ? loop3d.length : 0,
    Array.isArray(loop2d) ? loop2d.length : 0
  );
  const points3d = [];
  const points2d = [];
  for (let index = 0; index < count; index += 1) {
    const point3d = loop3d[index];
    const point2d = loop2d[index];
    if (!isFinitePoint3(point3d) || !isFinitePoint2(point2d)) {
      continue;
    }
    const normalized3d = [Number(point3d[0]), Number(point3d[1]), Number(point3d[2])];
    const normalized2d = [Number(point2d[0]), Number(point2d[1])];
    const previous3d = points3d[points3d.length - 1];
    const previous2d = points2d[points2d.length - 1];
    if (previous3d && previous2d) {
      const duplicate3d = distanceSquared3d(previous3d, normalized3d) <= 1e-10;
      const duplicate2d = distanceSquared2d(previous2d, normalized2d) <= 1e-10;
      if (duplicate3d || duplicate2d) {
        continue;
      }
    }
    points3d.push(normalized3d);
    points2d.push(normalized2d);
  }

  if (points3d.length >= 3 && distanceSquared3d(points3d[0], points3d[points3d.length - 1]) <= 1e-10) {
    points3d.pop();
    points2d.pop();
  }

  if (points3d.length < 3 || points2d.length < 3) {
    return null;
  }
  return { loop3d: points3d, loop2d: points2d };
}

function averagePoint3(points) {
  if (!Array.isArray(points) || !points.length) {
    return [0, 0, 0];
  }
  let x = 0;
  let y = 0;
  let z = 0;
  let count = 0;
  for (const point of points) {
    if (!isFinitePoint3(point)) {
      continue;
    }
    x += Number(point[0]);
    y += Number(point[1]);
    z += Number(point[2]);
    count += 1;
  }
  if (!count) {
    return [0, 0, 0];
  }
  return [x / count, y / count, z / count];
}

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function length(vector) {
  return Math.hypot(vector[0], vector[1], vector[2]);
}

function normalizeVector3(vector) {
  const magnitude = length(vector);
  if (magnitude <= 1e-9) {
    return null;
  }
  return [vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude];
}

function cross3(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ];
}

function normalizeAngleAround(angle, center) {
  let adjusted = angle;
  while (adjusted - center > Math.PI) {
    adjusted -= Math.PI * 2;
  }
  while (adjusted - center < -Math.PI) {
    adjusted += Math.PI * 2;
  }
  return adjusted;
}

function projectLoopsWithFrame(loops, origin, xDir, yDir) {
  return loops.map((loop) => loop.map((point) => {
    const relative = subtract(point, origin);
    return [dot(relative, xDir), dot(relative, yDir)];
  }));
}

function projectFaceLoopsTo2d(loops, surface) {
  if (!Array.isArray(loops) || !loops.length) {
    return null;
  }

  const sanitizedLoops = loops.map((loop) => (Array.isArray(loop) ? loop.filter(isFinitePoint3) : []));
  const hasAnyValidLoop = sanitizedLoops.some((loop) => loop.length >= 3);
  if (!hasAnyValidLoop) {
    return null;
  }

  if (surface?.type === "PLANE" && Array.isArray(surface?.origin) && Array.isArray(surface?.xDir) && Array.isArray(surface?.yDir)) {
    const origin = surface.origin;
    const xDir = surface.xDir;
    const yDir = surface.yDir;
    return projectLoopsWithFrame(sanitizedLoops, origin, xDir, yDir);
  }
  if (
    surface?.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface?.origin) &&
    Array.isArray(surface?.axis) &&
    Array.isArray(surface?.xDir) &&
    Array.isArray(surface?.yDir) &&
    Number(surface?.radius) > 0
  ) {
    const origin = surface.origin;
    const axis = surface.axis;
    const xDir = surface.xDir;
    const yDir = surface.yDir;
    const radius = Number(surface.radius);
    return sanitizedLoops.map((loop) => {
      let previousAngle = null;
      return loop.map((point) => {
        const relative = subtract(point, origin);
        const axial = dot(relative, axis);
        const radial = [
          relative[0] - axis[0] * axial,
          relative[1] - axis[1] * axial,
          relative[2] - axis[2] * axial
        ];
        const rawAngle = Math.atan2(dot(radial, yDir), dot(radial, xDir));
        const angle = previousAngle === null ? rawAngle : normalizeAngleAround(rawAngle, previousAngle);
        previousAngle = angle;
        return [angle * radius, axial];
      });
    });
  }

  const allPoints = sanitizedLoops.flat();
  const origin = isFinitePoint3(surface?.origin) ? surface.origin : averagePoint3(allPoints);
  let normal = normalizeVector3(surface?.normal || []);
  if (!normal) {
    for (let index = 2; index < allPoints.length; index += 1) {
      const a = allPoints[index - 2];
      const b = allPoints[index - 1];
      const c = allPoints[index];
      const ab = subtract(b, a);
      const ac = subtract(c, a);
      normal = normalizeVector3(cross3(ab, ac));
      if (normal) {
        break;
      }
    }
  }
  if (!normal) {
    normal = [0, 0, 1];
  }

  let axis = Math.abs(normal[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0];
  let xDir = normalizeVector3(cross3(axis, normal));
  if (!xDir) {
    axis = [1, 0, 0];
    xDir = normalizeVector3(cross3(axis, normal));
  }
  if (!xDir) {
    return null;
  }
  const yDir = normalizeVector3(cross3(normal, xDir));
  if (!yDir) {
    return null;
  }

  return projectLoopsWithFrame(sanitizedLoops, origin, xDir, yDir);
}

export function buildFallbackFaceFanGeometry(THREE, loop3d, centroid = null) {
  if (!Array.isArray(loop3d) || loop3d.length < 3) {
    return null;
  }

  const cleanedLoop = loop3d.filter(isFinitePoint3).map((point) => [Number(point[0]), Number(point[1]), Number(point[2])]);
  if (cleanedLoop.length < 3) {
    return null;
  }

  const center = isFinitePoint3(centroid) ? centroid.map((value) => Number(value)) : averagePoint3(cleanedLoop);
  const fillPositions = [];
  for (let index = 0; index < cleanedLoop.length; index += 1) {
    const a = cleanedLoop[index];
    const b = cleanedLoop[(index + 1) % cleanedLoop.length];
    fillPositions.push(
      center[0], center[1], center[2],
      a[0], a[1], a[2],
      b[0], b[1], b[2]
    );
  }
  if (!fillPositions.length) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(fillPositions), 3));
  return geometry;
}

export function createReferenceFaceFillGeometry(THREE, reference) {
  const pickData = reference?.pickData;
  const loops3d = Array.isArray(pickData?.loops) ? pickData.loops : [];
  if (!loops3d.length) {
    return null;
  }

  const projectedLoops = projectFaceLoopsTo2d(loops3d, pickData?.surface || {});
  if (!projectedLoops) {
    return buildFallbackFaceFanGeometry(
      THREE,
      selectOuterLoopPoints(pickData) || loops3d[0],
      pickData?.centroid || null
    );
  }

  const loopEntries = loops3d
    .map((loop3d, index) => {
      const cleaned = sanitizeLoopPair(loop3d, projectedLoops[index] || []);
      if (!cleaned) {
        return null;
      }
      return {
        index,
        ...cleaned
      };
    })
    .filter((entry) => entry && Array.isArray(entry.loop3d) && entry.loop3d.length >= 3 && Array.isArray(entry.loop2d) && entry.loop2d.length >= 3);
  if (!loopEntries.length) {
    return buildFallbackFaceFanGeometry(
      THREE,
      selectOuterLoopPoints(pickData) || loops3d[0],
      pickData?.centroid || null
    );
  }

  const preferredOuterIndex = Number.isInteger(pickData?.outerLoopIndex) ? pickData.outerLoopIndex : 0;
  const outerEntry = loopEntries.find((entry) => entry.index === preferredOuterIndex) || loopEntries[0];
  if (!outerEntry) {
    return null;
  }
  const contourLoop3d = [...outerEntry.loop3d];
  let contour2d = outerEntry.loop2d.map((point) => new THREE.Vector2(Number(point[0]), Number(point[1])));
  if (contour2d.length < 3) {
    return buildFallbackFaceFanGeometry(THREE, contourLoop3d, pickData?.centroid || null);
  }

  let contourClockwise = THREE.ShapeUtils.isClockWise(contour2d);
  if (contourClockwise) {
    contour2d = [...contour2d].reverse();
    contourLoop3d.reverse();
    contourClockwise = false;
  }

  const holeEntries = loopEntries.filter((entry) => entry.index !== outerEntry.index);
  const holeData = [];
  for (const holeEntry of holeEntries) {
    let holeLoop3d = [...holeEntry.loop3d];
    let hole2d = holeEntry.loop2d.map((point) => new THREE.Vector2(Number(point[0]), Number(point[1])));
    if (hole2d.length < 3) {
      continue;
    }
    const holeClockwise = THREE.ShapeUtils.isClockWise(hole2d);
    if (holeClockwise === contourClockwise) {
      hole2d = [...hole2d].reverse();
      holeLoop3d.reverse();
    }
    holeData.push({
      loop2d: hole2d,
      loop3d: holeLoop3d
    });
  }

  const triangulated = THREE.ShapeUtils.triangulateShape(
    contour2d,
    holeData.map((entry) => entry.loop2d)
  );
  if (!Array.isArray(triangulated) || !triangulated.length) {
    return buildFallbackFaceFanGeometry(THREE, contourLoop3d, pickData?.centroid || null);
  }

  const vertexPoints3d = [
    ...contourLoop3d,
    ...holeData.flatMap((entry) => entry.loop3d)
  ];
  if (!vertexPoints3d.length) {
    return null;
  }

  const fillPositions = [];
  for (const triangle of triangulated) {
    if (!Array.isArray(triangle) || triangle.length !== 3) {
      continue;
    }
    for (const vertexIndex of triangle) {
      const point = vertexPoints3d[vertexIndex];
      if (!Array.isArray(point) || point.length < 3) {
        continue;
      }
      fillPositions.push(
        Number(point[0]),
        Number(point[1]),
        Number(point[2])
      );
    }
  }
  if (!fillPositions.length) {
    return null;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(fillPositions), 3));
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

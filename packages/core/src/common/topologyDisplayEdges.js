function isFloat32Array(value) {
  return value instanceof Float32Array;
}

function isUint32Array(value) {
  return value instanceof Uint32Array;
}

function pointDistance(left, right) {
  return Math.hypot(
    Number(right?.[0] || 0) - Number(left?.[0] || 0),
    Number(right?.[1] || 0) - Number(left?.[1] || 0),
    Number(right?.[2] || 0) - Number(left?.[2] || 0)
  );
}

function boundsForPolylines(polylines) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const positions of polylines) {
    for (let offset = 0; offset + 2 < positions.length; offset += 3) {
      min[0] = Math.min(min[0], positions[offset]);
      min[1] = Math.min(min[1], positions[offset + 1]);
      min[2] = Math.min(min[2], positions[offset + 2]);
      max[0] = Math.max(max[0], positions[offset]);
      max[1] = Math.max(max[1], positions[offset + 1]);
      max[2] = Math.max(max[2], positions[offset + 2]);
    }
  }
  if (!Number.isFinite(min[0]) || !Number.isFinite(max[0])) {
    return null;
  }
  return { min, max };
}

function stitchToleranceForPolylines(polylines) {
  const bounds = boundsForPolylines(polylines);
  if (!bounds) {
    return 1e-5;
  }
  return Math.max(1e-5, pointDistance(bounds.min, bounds.max) * 1e-7);
}

function pointFromProxy(proxy, vertexIndex) {
  const offset = Number(vertexIndex) * 3;
  if (
    !Number.isInteger(vertexIndex) ||
    offset < 0 ||
    offset + 2 >= proxy.edgePositions.length
  ) {
    return null;
  }
  return [
    proxy.edgePositions[offset],
    proxy.edgePositions[offset + 1],
    proxy.edgePositions[offset + 2]
  ];
}

function normalizePartIdSet(value) {
  return new Set(
    (Array.isArray(value) ? value : [value])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
}

function normalizeVisibilityClassSet(value) {
  const values = (Array.isArray(value) ? value : [value])
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean);
  return values.length ? new Set(values) : null;
}

function occurrenceMatchesPartIds(occurrenceId, partIds) {
  const normalizedOccurrenceId = String(occurrenceId || "").trim();
  if (!normalizedOccurrenceId || !partIds?.size) {
    return false;
  }
  for (const partId of partIds) {
    if (normalizedOccurrenceId === partId || normalizedOccurrenceId.startsWith(`${partId}.`)) {
      return true;
    }
  }
  return false;
}

function edgeRowMatchesPartIds(row, partIds) {
  return occurrenceMatchesPartIds(row?.occurrenceId || row?.partId || row?.id, partIds);
}

function edgeRowPassesPartFilter(row, includePartIds, excludePartIds) {
  if (includePartIds.size && !edgeRowMatchesPartIds(row, includePartIds)) {
    return false;
  }
  if (excludePartIds.size && edgeRowMatchesPartIds(row, excludePartIds)) {
    return false;
  }
  return true;
}

function edgeRowPassesVisibilityClassFilter(row, visibilityClasses) {
  if (!visibilityClasses?.size) {
    return true;
  }
  const visibilityClass = String(row?.visibilityClass || "feature").trim().toLowerCase() || "feature";
  return visibilityClasses.has(visibilityClass);
}

function edgeRowPassesFilters(row, includePartIds, excludePartIds, visibilityClasses) {
  return (
    edgeRowPassesPartFilter(row, includePartIds, excludePartIds) &&
    edgeRowPassesVisibilityClassFilter(row, visibilityClasses)
  );
}

function pushPoint(target, point, tolerance = 1e-7) {
  if (!point) {
    return;
  }
  const last = target.length >= 3
    ? [target[target.length - 3], target[target.length - 2], target[target.length - 1]]
    : null;
  if (!last || pointDistance(last, point) > tolerance) {
    target.push(point[0], point[1], point[2]);
  }
}

function buildTopologyPolylinesForRun(proxy, segmentStart, segmentCount) {
  const polylines = [];
  let current = [];
  let lastPoint = null;
  for (let segmentIndex = segmentStart; segmentIndex < segmentStart + segmentCount; segmentIndex += 1) {
    const startVertexIndex = Number(proxy.edgeIndices[segmentIndex * 2]);
    const endVertexIndex = Number(proxy.edgeIndices[(segmentIndex * 2) + 1]);
    const startPoint = pointFromProxy(proxy, startVertexIndex);
    const endPoint = pointFromProxy(proxy, endVertexIndex);
    if (!startPoint || !endPoint || pointDistance(startPoint, endPoint) <= 1e-10) {
      continue;
    }
    if (lastPoint && pointDistance(lastPoint, startPoint) > 1e-5) {
      if (current.length >= 6) {
        polylines.push(new Float32Array(current));
      }
      current = [];
      lastPoint = null;
    }
    if (!lastPoint) {
      pushPoint(current, startPoint);
    }
    pushPoint(current, endPoint);
    lastPoint = endPoint;
  }
  if (current.length >= 6) {
    polylines.push(new Float32Array(current));
  }
  return polylines;
}

function buildTopologyPolylinesForEdgeId(proxy, edgeIds, rowIndex, segmentCount) {
  const polylines = [];
  let runStart = -1;
  let runCount = 0;
  const flushRun = () => {
    if (runStart >= 0 && runCount > 0) {
      polylines.push(...buildTopologyPolylinesForRun(proxy, runStart, runCount));
    }
    runStart = -1;
    runCount = 0;
  };
  for (let segmentIndex = 0; segmentIndex < segmentCount; segmentIndex += 1) {
    if (Number(edgeIds[segmentIndex]) === rowIndex) {
      if (runStart < 0) {
        runStart = segmentIndex;
      }
      runCount += 1;
    } else {
      flushRun();
    }
  }
  flushRun();
  return polylines;
}

function polylinePoint(positions, vertexIndex) {
  const offset = vertexIndex * 3;
  return [
    positions[offset],
    positions[offset + 1],
    positions[offset + 2]
  ];
}

function polylineStart(positions) {
  return polylinePoint(positions, 0);
}

function polylineEnd(positions) {
  return polylinePoint(positions, Math.floor(positions.length / 3) - 1);
}

function reversePolyline(positions) {
  const reversed = [];
  for (let offset = positions.length - 3; offset >= 0; offset -= 3) {
    reversed.push(positions[offset], positions[offset + 1], positions[offset + 2]);
  }
  return reversed;
}

function appendPolyline(target, source, { skipFirst = true, tolerance = 1e-7 } = {}) {
  const startOffset = skipFirst ? 3 : 0;
  for (let offset = startOffset; offset + 2 < source.length; offset += 3) {
    pushPoint(target, [source[offset], source[offset + 1], source[offset + 2]], tolerance);
  }
}

function closePolylineIfNeeded(positions, tolerance) {
  if (positions.length < 12) {
    return positions;
  }
  const start = polylineStart(positions);
  const end = polylineEnd(positions);
  if (pointDistance(start, end) > tolerance) {
    return positions;
  }
  const output = Array.from(positions);
  output[output.length - 3] = output[0];
  output[output.length - 2] = output[1];
  output[output.length - 1] = output[2];
  return new Float32Array(output);
}

export function stitchTopologyDisplayEdgePolylines(polylines) {
  if (!Array.isArray(polylines) || polylines.length <= 1) {
    return polylines || [];
  }
  const tolerance = stitchToleranceForPolylines(polylines);
  const chains = polylines
    .filter((positions) => positions?.length >= 6)
    .map((positions) => Array.from(positions));
  for (let index = 0; index < chains.length; index += 1) {
    let changed = true;
    while (changed) {
      changed = false;
      for (let candidateIndex = index + 1; candidateIndex < chains.length; candidateIndex += 1) {
        const current = chains[index];
        const candidate = chains[candidateIndex];
        const currentStart = polylineStart(current);
        const currentEnd = polylineEnd(current);
        const candidateStart = polylineStart(candidate);
        const candidateEnd = polylineEnd(candidate);
        let merged = null;
        if (pointDistance(currentEnd, candidateStart) <= tolerance) {
          merged = [...current];
          appendPolyline(merged, candidate, { tolerance });
        } else if (pointDistance(currentEnd, candidateEnd) <= tolerance) {
          merged = [...current];
          appendPolyline(merged, reversePolyline(candidate), { tolerance });
        } else if (pointDistance(currentStart, candidateEnd) <= tolerance) {
          merged = [...candidate];
          appendPolyline(merged, current, { tolerance });
        } else if (pointDistance(currentStart, candidateStart) <= tolerance) {
          merged = reversePolyline(candidate);
          appendPolyline(merged, current, { tolerance });
        }
        if (merged) {
          chains[index] = merged;
          chains.splice(candidateIndex, 1);
          changed = true;
          break;
        }
      }
    }
  }
  return chains
    .filter((positions) => positions.length >= 6)
    .map((positions) => closePolylineIfNeeded(new Float32Array(positions), tolerance));
}

export function hasTopologyDisplayEdgeProxy(selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  return (
    isFloat32Array(proxy.edgePositions) &&
    isUint32Array(proxy.edgeIndices) &&
    proxy.edgePositions.length >= 6 &&
    proxy.edgeIndices.length >= 2
  );
}

export function hasTopologyDisplayEdgeClassification(selectorRuntime) {
  return hasTopologyDisplayEdgeProxy(selectorRuntime);
}

export function shouldUseTopologyDisplayEdges(selectorRuntime) {
  return !selectorRuntime?.surfaceEdgeRendering &&
    hasTopologyDisplayEdgeProxy(selectorRuntime);
}

export function buildTopologyDisplayEdgePositions(selectorRuntime, {
  includePartIds = [],
  excludePartIds = [],
  visibilityClasses = null
} = {}) {
  if (!hasTopologyDisplayEdgeProxy(selectorRuntime)) {
    return null;
  }
  const proxy = selectorRuntime.proxy;
  const segmentCount = Math.floor(proxy.edgeIndices.length / 2);
  if (segmentCount <= 0) {
    return null;
  }
  const includePartIdSet = normalizePartIdSet(includePartIds);
  const excludePartIdSet = normalizePartIdSet(excludePartIds);
  const hasPartFilter = includePartIdSet.size > 0 || excludePartIdSet.size > 0;
  const visibilityClassSet = normalizeVisibilityClassSet(visibilityClasses);
  const edgeRows = Array.isArray(selectorRuntime.edges) ? selectorRuntime.edges : [];
  const hasVisibilityClassFilter = Boolean(visibilityClassSet?.size && edgeRows.length);
  const hasEdgeRowFilter = hasPartFilter || hasVisibilityClassFilter;
  const edgeIds = isUint32Array(proxy.edgeIds) ? proxy.edgeIds : null;
  const linePositions = new Float32Array(segmentCount * 6);
  let writeOffset = 0;

  const writeSegment = (segmentIndex) => {
    const startVertexIndex = Number(proxy.edgeIndices[segmentIndex * 2]);
    const endVertexIndex = Number(proxy.edgeIndices[(segmentIndex * 2) + 1]);
    const startPoint = pointFromProxy(proxy, startVertexIndex);
    const endPoint = pointFromProxy(proxy, endVertexIndex);
    if (!startPoint || !endPoint || pointDistance(startPoint, endPoint) <= 1e-10) {
      return;
    }
    linePositions[writeOffset] = startPoint[0];
    linePositions[writeOffset + 1] = startPoint[1];
    linePositions[writeOffset + 2] = startPoint[2];
    linePositions[writeOffset + 3] = endPoint[0];
    linePositions[writeOffset + 4] = endPoint[1];
    linePositions[writeOffset + 5] = endPoint[2];
    writeOffset += 6;
  };

  if (hasEdgeRowFilter) {
    if (!edgeRows.length) {
      return null;
    }
    for (let rowIndex = 0; rowIndex < edgeRows.length; rowIndex += 1) {
      const row = edgeRows[rowIndex];
      if (!edgeRowPassesFilters(row, includePartIdSet, excludePartIdSet, visibilityClassSet)) {
        continue;
      }
      const start = Number(row?.segmentStart || 0);
      const count = Number(row?.segmentCount || 0);
      if (Number.isInteger(start) && Number.isInteger(count) && start >= 0 && count > 0 && start + count <= segmentCount) {
        for (let segmentIndex = start; segmentIndex < start + count; segmentIndex += 1) {
          writeSegment(segmentIndex);
        }
        continue;
      }
      if (edgeIds) {
        for (let segmentIndex = 0; segmentIndex < segmentCount; segmentIndex += 1) {
          if (Number(edgeIds[segmentIndex]) === rowIndex) {
            writeSegment(segmentIndex);
          }
        }
      }
    }
  } else {
    for (let segmentIndex = 0; segmentIndex < segmentCount; segmentIndex += 1) {
      writeSegment(segmentIndex);
    }
  }

  if (writeOffset <= 0) {
    return null;
  }
  return writeOffset === linePositions.length ? linePositions : linePositions.subarray(0, writeOffset);
}

export function buildTopologyDisplayEdgePolylines(selectorRuntime, {
  includePartIds = [],
  excludePartIds = [],
  visibilityClasses = null
} = {}) {
  if (!hasTopologyDisplayEdgeProxy(selectorRuntime)) {
    return [];
  }
  const proxy = selectorRuntime.proxy;
  const segmentCount = Math.floor(proxy.edgeIndices.length / 2);
  if (segmentCount <= 0) {
    return [];
  }

  const edgeRows = Array.isArray(selectorRuntime.edges) ? selectorRuntime.edges : [];
  const edgeIds = isUint32Array(proxy.edgeIds) ? proxy.edgeIds : null;
  const includePartIdSet = normalizePartIdSet(includePartIds);
  const excludePartIdSet = normalizePartIdSet(excludePartIds);
  const hasPartFilter = includePartIdSet.size > 0 || excludePartIdSet.size > 0;
  const visibilityClassSet = normalizeVisibilityClassSet(visibilityClasses);
  const hasVisibilityClassFilter = Boolean(visibilityClassSet?.size && edgeRows.length);
  const hasEdgeRowFilter = hasPartFilter || hasVisibilityClassFilter;
  const polylines = [];

  if (edgeRows.length) {
    for (let rowIndex = 0; rowIndex < edgeRows.length; rowIndex += 1) {
      const row = edgeRows[rowIndex];
      if (!row) {
        continue;
      }
      if (!edgeRowPassesFilters(row, includePartIdSet, excludePartIdSet, visibilityClassSet)) {
        continue;
      }
      const start = Number(row.segmentStart || 0);
      const count = Number(row.segmentCount || 0);
      if (Number.isInteger(start) && Number.isInteger(count) && start >= 0 && count > 0 && start + count <= segmentCount) {
        polylines.push(...buildTopologyPolylinesForRun(proxy, start, count));
      } else if (edgeIds) {
        polylines.push(...buildTopologyPolylinesForEdgeId(proxy, edgeIds, rowIndex, segmentCount));
      }
    }
    return stitchTopologyDisplayEdgePolylines(polylines);
  }

  if (hasEdgeRowFilter) {
    return [];
  }

  for (let segmentIndex = 0; segmentIndex < segmentCount; segmentIndex += 1) {
    const rowIndex = edgeIds ? Number(edgeIds[segmentIndex]) : -1;
    void rowIndex;

    polylines.push(...buildTopologyPolylinesForRun(proxy, segmentIndex, 1));
  }

  return stitchTopologyDisplayEdgePolylines(polylines);
}

import { buildCadRefToken } from "../cadRefs.js";

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function toRows(manifest, rowKey, columnsKey) {
  const columns = manifest?.tables?.[columnsKey];
  const rows = manifest?.[rowKey];
  if (!Array.isArray(columns) || !Array.isArray(rows)) {
    return [];
  }
  return rows
    .filter(Array.isArray)
    .map((row) => Object.fromEntries(columns.map((column, index) => [column, row[index]])));
}

function relationArray(manifest, buffers, relationKey, viewKey) {
  const direct = manifest?.relations?.[relationKey];
  if (Array.isArray(direct) || ArrayBuffer.isView(direct)) {
    return direct;
  }
  const viewName = manifest?.relations?.[viewKey];
  if (typeof viewName === "string" && buffers?.[viewName]) {
    return buffers[viewName];
  }
  return [];
}

function typedBufferView(manifest, buffers, manifestSectionKey, viewKey) {
  const viewName = manifest?.[manifestSectionKey]?.[viewKey];
  if (typeof viewName === "string" && buffers?.[viewName]) {
    return buffers[viewName];
  }
  return new Uint32Array(0);
}

function selectorPrefix(singleOccurrenceId, selector) {
  if (!singleOccurrenceId || !selector.startsWith(`${singleOccurrenceId}.`)) {
    return selector;
  }
  const suffix = selector.slice(singleOccurrenceId.length + 1);
  return suffix.startsWith("s") || suffix.startsWith("f") || suffix.startsWith("e") ? suffix : selector;
}

function selectorTypeLabel(selectorType) {
  if (selectorType === "occurrence") {
    return "Occurrence";
  }
  if (selectorType === "shape") {
    return "Shape";
  }
  if (selectorType === "face") {
    return "Face";
  }
  return "Edge";
}

function transformPoint(transform, point) {
  if (!Array.isArray(point) || point.length < 3) {
    return point;
  }
  if (!Array.isArray(transform) || transform.length < 16) {
    return [Number(point[0]), Number(point[1]), Number(point[2])];
  }
  const x = Number(point[0]);
  const y = Number(point[1]);
  const z = Number(point[2]);
  return [
    (transform[0] * x) + (transform[1] * y) + (transform[2] * z) + transform[3],
    (transform[4] * x) + (transform[5] * y) + (transform[6] * z) + transform[7],
    (transform[8] * x) + (transform[9] * y) + (transform[10] * z) + transform[11],
  ];
}

function normalizeVector(vector) {
  const x = Number(vector?.[0] || 0);
  const y = Number(vector?.[1] || 0);
  const z = Number(vector?.[2] || 0);
  const magnitude = Math.hypot(x, y, z);
  if (magnitude <= 1e-9) {
    return null;
  }
  return [x / magnitude, y / magnitude, z / magnitude];
}

function transformVector(transform, vector) {
  if (!Array.isArray(vector) || vector.length < 3 || !Array.isArray(transform) || transform.length < 16) {
    return normalizeVector(vector || []);
  }
  return normalizeVector([
    (transform[0] * vector[0]) + (transform[1] * vector[1]) + (transform[2] * vector[2]),
    (transform[4] * vector[0]) + (transform[5] * vector[1]) + (transform[6] * vector[2]),
    (transform[8] * vector[0]) + (transform[9] * vector[1]) + (transform[10] * vector[2]),
  ]);
}

function transformBBox(transform, bbox) {
  if (!isObject(bbox)) {
    return bbox;
  }
  const min = Array.isArray(bbox.min) ? bbox.min : [0, 0, 0];
  const max = Array.isArray(bbox.max) ? bbox.max : [0, 0, 0];
  const corners = [
    [min[0], min[1], min[2]],
    [min[0], min[1], max[2]],
    [min[0], max[1], min[2]],
    [min[0], max[1], max[2]],
    [max[0], min[1], min[2]],
    [max[0], min[1], max[2]],
    [max[0], max[1], min[2]],
    [max[0], max[1], max[2]],
  ].map((point) => transformPoint(transform, point));
  const xs = corners.map((point) => point[0]);
  const ys = corners.map((point) => point[1]);
  const zs = corners.map((point) => point[2]);
  return {
    min: [Math.min(...xs), Math.min(...ys), Math.min(...zs)],
    max: [Math.max(...xs), Math.max(...ys), Math.max(...zs)],
  };
}

function transformParams(transform, params) {
  if (!isObject(params)) {
    return params;
  }
  const pointKeys = new Set(["origin", "center", "location"]);
  const vectorKeys = new Set(["axis", "direction", "normal"]);
  return Object.fromEntries(Object.entries(params).map(([key, value]) => {
    if (pointKeys.has(key) && Array.isArray(value) && value.length === 3) {
      return [key, transformPoint(transform, value)];
    }
    if (vectorKeys.has(key) && Array.isArray(value) && value.length === 3) {
      return [key, transformVector(transform, value)];
    }
    return [key, value];
  }));
}

function transformPointList(transform, points) {
  if (!Array.isArray(points)) {
    return points;
  }
  return points.map((point) => (
    Array.isArray(point) && point.length >= 3 ? transformPoint(transform, point) : point
  ));
}

function transformLoopMetadata(transform, loopsMeta) {
  if (!Array.isArray(loopsMeta)) {
    return loopsMeta;
  }
  return loopsMeta.map((loop) => (
    isObject(loop) && Array.isArray(loop.points)
      ? { ...loop, points: transformPointList(transform, loop.points) }
      : loop
  ));
}

function transformSurface(transform, surface) {
  if (!isObject(surface)) {
    return surface;
  }
  const pointKeys = new Set(["origin", "center", "location"]);
  const vectorKeys = new Set(["axis", "direction", "normal", "xDir", "yDir"]);
  return Object.fromEntries(Object.entries(surface).map(([key, value]) => {
    if (pointKeys.has(key) && Array.isArray(value) && value.length === 3) {
      return [key, transformPoint(transform, value)];
    }
    if (vectorKeys.has(key) && Array.isArray(value) && value.length === 3) {
      return [key, transformVector(transform, value)];
    }
    return [key, value];
  }));
}

function transformPositions(values, transform) {
  if (!(values instanceof Float32Array) || !Array.isArray(transform) || transform.length < 16) {
    return values;
  }
  const next = new Float32Array(values.length);
  for (let index = 0; index < values.length; index += 3) {
    const point = transformPoint(transform, [values[index], values[index + 1], values[index + 2]]);
    next[index] = point[0];
    next[index + 1] = point[1];
    next[index + 2] = point[2];
  }
  return next;
}

function transformPickData(pickData, transform) {
  if (!isObject(pickData) || !Array.isArray(transform) || transform.length < 16) {
    return pickData;
  }
  return {
    ...pickData,
    bbox: pickData.bbox ? transformBBox(transform, pickData.bbox) : pickData.bbox,
    center: Array.isArray(pickData.center) ? transformPoint(transform, pickData.center) : pickData.center,
    normal: Array.isArray(pickData.normal) ? transformVector(transform, pickData.normal) : pickData.normal,
    params: pickData.params ? transformParams(transform, pickData.params) : pickData.params,
    points: transformPointList(transform, pickData.points),
    loops: Array.isArray(pickData.loops)
      ? pickData.loops.map((loop) => transformPointList(transform, loop))
      : pickData.loops,
    loopsMeta: transformLoopMetadata(transform, pickData.loopsMeta),
    surface: transformSurface(transform, pickData.surface),
    centroid: Array.isArray(pickData.centroid) ? transformPoint(transform, pickData.centroid) : pickData.centroid,
    transform,
  };
}

function referenceIdForRow(displaySelector, selectorType, partId) {
  if (partId) {
    return `topology|${partId}|${selectorType}|${displaySelector}`;
  }
  return displaySelector;
}

function referenceSummary(selectorType, row) {
  if (selectorType === "occurrence") {
    return String(row.name || row.sourceName || row.id || "").trim();
  }
  if (selectorType === "shape") {
    const name = String(row.name || row.sourceName || "").trim();
    const detail = `${row.kind || "shape"}${row.volume ? ` volume=${row.volume}` : row.area ? ` area=${row.area}` : ""}`;
    return name ? `${name} ${detail}` : detail;
  }
  if (selectorType === "face") {
    return `${row.surfaceType || "face"} area=${row.area ?? 0}`;
  }
  return `${row.curveType || "edge"} length=${row.length ?? 0}`;
}

function sourceOccurrenceMatchesFilter(sourceOccurrenceId, filterOccurrenceId) {
  const sourceId = String(sourceOccurrenceId || "").trim();
  const filterId = String(filterOccurrenceId || "").trim();
  return !filterId || sourceId === filterId || sourceId.startsWith(`${filterId}.`);
}

function remapSourceOccurrenceId(sourceOccurrenceId, remapOccurrencePrefix) {
  const sourceId = String(sourceOccurrenceId || "").trim();
  if (!sourceId || !remapOccurrencePrefix || typeof remapOccurrencePrefix !== "object") {
    return "";
  }
  if (!sourceOccurrenceMatchesFilter(sourceId, remapOccurrencePrefix.sourceOccurrenceId)) {
    return "";
  }
  const sourceRootId = String(remapOccurrencePrefix.sourceRootOccurrenceId || "").trim();
  const targetRootId = String(remapOccurrencePrefix.targetRootOccurrenceId || "").trim();
  if (!sourceRootId || !targetRootId) {
    return "";
  }
  if (sourceId === sourceRootId) {
    return targetRootId;
  }
  const sourceRootPrefix = `${sourceRootId}.`;
  if (sourceId.startsWith(sourceRootPrefix)) {
    return `${targetRootId}.${sourceId.slice(sourceRootPrefix.length)}`;
  }
  return "";
}

function selectorForRow(selectorType, row, rowIndex, singleOccurrenceId, remapOccurrenceId = "", remapOccurrencePrefix = null) {
  if (!row || !Number.isFinite(Number(rowIndex))) {
    return "";
  }
  if (remapOccurrencePrefix && typeof remapOccurrencePrefix === "object") {
    const sourceOccurrenceId = selectorType === "occurrence"
      ? String(row?.id || "").trim()
      : String(row?.occurrenceId || "").trim();
    const occurrenceId = remapSourceOccurrenceId(sourceOccurrenceId, remapOccurrencePrefix);
    if (!occurrenceId) {
      return "";
    }
    if (selectorType === "occurrence") {
      return occurrenceId;
    }
    const selectorKind = selectorType === "shape"
      ? "s"
      : selectorType === "face"
        ? "f"
        : "e";
    return `${occurrenceId}.${selectorKind}${rowIndex + 1}`;
  }
  const occurrenceId = String(remapOccurrenceId || "").trim();
  if (occurrenceId) {
    if (selectorType === "occurrence") {
      return occurrenceId;
    }
    const selectorKind = selectorType === "shape"
      ? "s"
      : selectorType === "face"
        ? "f"
        : "e";
    return `${occurrenceId}.${selectorKind}${rowIndex + 1}`;
  }
  return selectorPrefix(singleOccurrenceId, String(row?.id || "").trim());
}

function selectorWithRemappedOccurrence(selector, singleOccurrenceId, remapOccurrenceId = "", remapOccurrencePrefix = null) {
  const normalizedSelector = String(selector || "").trim();
  if (!normalizedSelector) {
    return "";
  }
  const match = normalizedSelector.match(/^(.*)\.([sfe]\d+)$/i);
  if (!match) {
    return selectorPrefix(singleOccurrenceId, normalizedSelector);
  }
  const occurrenceId = String(match[1] || "").trim();
  const selectorToken = String(match[2] || "").trim();
  if (!occurrenceId || !selectorToken) {
    return selectorPrefix(singleOccurrenceId, normalizedSelector);
  }
  if (remapOccurrencePrefix && typeof remapOccurrencePrefix === "object") {
    const remappedOccurrenceId = remapSourceOccurrenceId(occurrenceId, remapOccurrencePrefix);
    return remappedOccurrenceId ? `${remappedOccurrenceId}.${selectorToken}` : "";
  }
  const targetOccurrenceId = String(remapOccurrenceId || "").trim();
  if (targetOccurrenceId) {
    return `${targetOccurrenceId}.${selectorToken}`;
  }
  return selectorPrefix(singleOccurrenceId, normalizedSelector);
}

function occurrenceIdForReference(selectorType, row, singleOccurrenceId, remapOccurrenceId = "", remapOccurrencePrefix = null) {
  if (selectorType === "occurrence") {
    return "";
  }
  const occurrenceId = String(row?.occurrenceId || "").trim();
  if (!occurrenceId) {
    return "";
  }
  if (remapOccurrencePrefix && typeof remapOccurrencePrefix === "object") {
    return remapSourceOccurrenceId(occurrenceId, remapOccurrencePrefix);
  }
  return String(remapOccurrenceId || "").trim() || selectorPrefix(singleOccurrenceId, occurrenceId);
}

function buildAdjacencySelectors(row, relationRows, targetRows, singleOccurrenceId, idKey, startKey, countKey, targetSelectorType, remapOccurrenceId, remapOccurrencePrefix) {
  const start = Number(row?.[startKey] || 0);
  const count = Number(row?.[countKey] || 0);
  const selectors = [];
  const end = Math.min(relationRows?.length || 0, start + count);
  for (let index = start; index < end; index += 1) {
    const rowIndex = relationRows[index];
    const targetRowIndex = Number(rowIndex);
    const targetRow = targetRows[targetRowIndex];
    const selector = selectorForRow(
      targetSelectorType,
      targetRow,
      targetRowIndex,
      singleOccurrenceId,
      remapOccurrenceId,
      remapOccurrencePrefix
    ) || String(targetRow?.[idKey] || "").trim();
    if (selector) {
      selectors.push(selector);
    }
  }
  return selectors;
}

function buildReference({
  selectorType,
  row,
  rowIndex,
  singleOccurrenceId,
  copyCadPath,
  partId,
  selectorTransform,
  relationRows,
  targetRows,
  targetKey,
  startKey,
  countKey,
  remapOccurrenceId = "",
  remapOccurrencePrefix = null,
  targetSelectorType = "",
}) {
  const normalizedSelector = selectorForRow(selectorType, row, rowIndex, singleOccurrenceId, remapOccurrenceId, remapOccurrencePrefix);
  const displaySelector = normalizedSelector;
  const id = referenceIdForRow(displaySelector, selectorType, partId);
  const summary = referenceSummary(selectorType, row);
  const copyText = buildCadRefToken({ cadPath: copyCadPath, selector: displaySelector });
  const adjacentSelectors = relationRows && targetRows
    ? buildAdjacencySelectors(
      row,
      relationRows,
      targetRows,
      singleOccurrenceId,
      targetKey,
      startKey,
      countKey,
      targetSelectorType,
      remapOccurrenceId,
      remapOccurrencePrefix
    )
    : [];
  return {
    id,
    selectorType,
    normalizedSelector,
    displaySelector,
    label: `${selectorTypeLabel(selectorType)} ${displaySelector}`,
    summary,
    shortSummary: summary,
    copyText,
    partId,
    occurrenceId: occurrenceIdForReference(selectorType, row, singleOccurrenceId, remapOccurrenceId, remapOccurrencePrefix),
    shapeId: selectorWithRemappedOccurrence(row.shapeId, singleOccurrenceId, remapOccurrenceId, remapOccurrencePrefix),
    rowIndex,
    pickData: {
      selectorType,
      rowIndex,
      name: row.name || null,
      sourceName: row.sourceName || null,
      kind: row.kind || null,
      bbox: row.bbox || null,
      surfaceType: row.surfaceType || null,
      center: row.center || null,
      normal: row.normal || null,
      params: row.params || null,
      triangleStart: row.triangleStart ?? 0,
      triangleCount: row.triangleCount ?? 0,
      segmentStart: row.segmentStart ?? 0,
      segmentCount: row.segmentCount ?? 0,
      adjacentSelectors,
      transform: selectorTransform || null,
    },
  };
}

function buildLeafOccurrenceIds(shapes) {
  return [...new Set(
    shapes
      .map((row) => String(row.occurrenceId || "").trim())
      .filter(Boolean)
  )].sort();
}

function transformRows(rows, transform) {
  if (!Array.isArray(transform) || transform.length < 16) {
    return rows;
  }
  return rows.map((row) => ({
    ...row,
    transform: Array.isArray(row.transform) ? row.transform : transform,
    bbox: row.bbox ? transformBBox(transform, row.bbox) : row.bbox,
    center: Array.isArray(row.center) ? transformPoint(transform, row.center) : row.center,
    normal: Array.isArray(row.normal) ? transformVector(transform, row.normal) : row.normal,
    params: row.params ? transformParams(transform, row.params) : row.params,
  }));
}

function transformRow(row, transform) {
  if (!row || !Array.isArray(transform) || transform.length < 16) {
    return row;
  }
  return {
    ...row,
    bbox: row.bbox ? transformBBox(transform, row.bbox) : row.bbox,
    center: Array.isArray(row.center) ? transformPoint(transform, row.center) : row.center,
    normal: Array.isArray(row.normal) ? transformVector(transform, row.normal) : row.normal,
    params: row.params ? transformParams(transform, row.params) : row.params,
  };
}

function applySequentialRelationStarts(rows, relationSpecs) {
  const specs = Array.isArray(relationSpecs?.[0]) ? relationSpecs : [relationSpecs];
  const nextStarts = specs.map(() => 0);
  return rows.map((row) => {
    const nextRow = { ...row };
    specs.forEach(([startKey, countKey], specIndex) => {
      const count = Math.max(0, Number(row?.[countKey] || 0));
      nextRow[startKey] = nextStarts[specIndex];
      nextRow[countKey] = count;
      nextStarts[specIndex] += count;
    });
    return nextRow;
  });
}

export function buildSelectorRuntime(bundle, {
  copyCadPath = "",
  partId = "",
  transform = null,
  remapOccurrenceId = "",
  remapOccurrencePrefix = null,
} = {}) {
  const manifest = bundle?.manifest || {};
  const buffers = bundle?.buffers || {};
  const faceRelations = relationArray(manifest, buffers, "faceEdgeRows", "faceEdgeRowsView");
  const edgeRelations = relationArray(manifest, buffers, "edgeFaceRows", "edgeFaceRowsView");
  const occurrences = transformRows(toRows(manifest, "occurrences", "occurrenceColumns"), transform);
  const shapes = transformRows(toRows(manifest, "shapes", "shapeColumns"), transform);
  const faces = applySequentialRelationStarts(
    transformRows(toRows(manifest, "faces", "faceColumns"), transform),
    [["edgeStart", "edgeCount"]]
  );
  const edges = applySequentialRelationStarts(
    transformRows(toRows(manifest, "edges", "edgeColumns"), transform),
    [["faceStart", "faceCount"]]
  );
  const leafOccurrenceIds = buildLeafOccurrenceIds(shapes);
  const singleOccurrenceId = leafOccurrenceIds.length === 1 ? leafOccurrenceIds[0] : "";
  const selectorBuffers = {
    facePositions: transformPositions(buffers.facePositions, transform),
    faceIndices: buffers.faceIndices || new Uint32Array(0),
    faceIds: buffers.faceIds || new Uint32Array(0),
    faceRuns: typedBufferView(manifest, buffers, "faceProxy", "runsView"),
    faceRunColumns: Array.isArray(manifest?.faceProxy?.runColumns) ? manifest.faceProxy.runColumns : [],
    edgePositions: transformPositions(buffers.edgePositions, transform),
    edgeIndices: buffers.edgeIndices || new Uint32Array(0),
    edgeIds: buffers.edgeIds || new Uint32Array(0),
    faceEdgeRows: faceRelations,
    edgeFaceRows: edgeRelations,
  };

  const references = [];
  references.push(...occurrences.map((row, rowIndex) => buildReference({
    selectorType: "occurrence",
    row,
    rowIndex,
    singleOccurrenceId,
    copyCadPath,
    partId,
    selectorTransform: transform,
    remapOccurrenceId,
    remapOccurrencePrefix,
  })));
  references.push(...shapes.map((row, rowIndex) => buildReference({
    selectorType: "shape",
    row,
    rowIndex,
    singleOccurrenceId,
    copyCadPath,
    partId,
    selectorTransform: transform,
    remapOccurrenceId,
    remapOccurrencePrefix,
  })));
  references.push(...faces.map((row, rowIndex) => buildReference({
    selectorType: "face",
    row,
    rowIndex,
    singleOccurrenceId,
    copyCadPath,
    partId,
    selectorTransform: transform,
    relationRows: faceRelations,
    targetRows: edges,
    targetKey: "id",
    startKey: "edgeStart",
    countKey: "edgeCount",
    remapOccurrenceId,
    remapOccurrencePrefix,
    targetSelectorType: "edge",
  })));
  references.push(...edges.map((row, rowIndex) => buildReference({
    selectorType: "edge",
    row,
    rowIndex,
    singleOccurrenceId,
    copyCadPath,
    partId,
    selectorTransform: transform,
    relationRows: edgeRelations,
    targetRows: faces,
    targetKey: "id",
    startKey: "faceStart",
    countKey: "faceCount",
    remapOccurrenceId,
    remapOccurrencePrefix,
    targetSelectorType: "face",
  })));
  const visibleReferences = references.filter((reference) => String(reference?.normalizedSelector || "").trim());
  const referenceMap = new Map(visibleReferences.map((reference) => [reference.id, reference]));
  const referenceByNormalizedSelector = new Map(
    visibleReferences.map((reference) => [reference.normalizedSelector, reference])
  );
  const referenceByDisplaySelector = new Map(
    visibleReferences.map((reference) => [reference.displaySelector, reference])
  );
  const faceReferenceByRowIndex = new Map(
    visibleReferences
      .filter((reference) => reference.selectorType === "face")
      .map((reference) => [reference.rowIndex, reference])
  );
  const edgeReferenceByRowIndex = new Map(
    visibleReferences
      .filter((reference) => reference.selectorType === "edge")
      .map((reference) => [reference.rowIndex, reference])
  );
  const occurrenceIdByRowIndex = new Map(
    occurrences.map((row, rowIndex) => [
      rowIndex,
      selectorForRow("occurrence", row, rowIndex, singleOccurrenceId, remapOccurrenceId, remapOccurrencePrefix) || String(row?.id || "").trim()
    ])
  );
  return {
    schemaVersion: Number(manifest.schemaVersion || 1),
    surfaceEdgeRendering: Boolean(manifest?.capabilities?.surfaceEdgeRendering),
    capabilities: manifest.capabilities || null,
    cadPath: copyCadPath || String(manifest.cadRef || "").trim(),
    stepHash: String(manifest.stepHash || ""),
    bbox: transform ? transformBBox(transform, manifest.bbox || {}) : manifest.bbox,
    occurrences,
    shapes,
    faces,
    edges,
    vertices: [],
    references: visibleReferences,
    referenceMap,
    referenceByNormalizedSelector,
    referenceByDisplaySelector,
    faceReferenceByRowIndex,
    edgeReferenceByRowIndex,
    vertexReferenceByRowIndex: new Map(),
    occurrenceIdByRowIndex,
    faceReferenceMap: new Map(visibleReferences.filter((reference) => reference.selectorType === "face").map((reference) => [reference.id, reference])),
    edgeReferenceMap: new Map(visibleReferences.filter((reference) => reference.selectorType === "edge").map((reference) => [reference.id, reference])),
    vertexReferenceMap: new Map(),
    singleOccurrenceId,
    proxy: selectorBuffers,
  };
}

export function buildDisplayEdgeRuntime(bundle, {
  transform = null,
} = {}) {
  const manifest = bundle?.manifest || {};
  if (String(manifest.profile || "") === "surface-edges") {
    const edgeRendering = manifest.edgeRendering && typeof manifest.edgeRendering === "object"
      ? manifest.edgeRendering
      : {};
    return {
      schemaVersion: Number(manifest.schemaVersion || 1),
      surfaceEdgeRendering: true,
      edgeRendering: {
        visibilityClasses: Array.isArray(edgeRendering.visibilityClasses)
          ? edgeRendering.visibilityClasses.map((item) => String(item || "").trim()).filter(Boolean)
          : [],
        generatedVisibilityClasses: Array.isArray(edgeRendering.generatedVisibilityClasses)
          ? edgeRendering.generatedVisibilityClasses.map((item) => String(item || "").trim()).filter(Boolean)
          : [],
        visibilityClassCounts: edgeRendering.visibilityClassCounts || {},
        generatedVisibilityClassCounts: edgeRendering.generatedVisibilityClassCounts || {},
      },
      stepHash: String(manifest.stepHash || ""),
      bbox: transform ? transformBBox(transform, manifest.bbox || {}) : manifest.bbox,
      edges: [],
      proxy: {
        edgePositions: new Float32Array(0),
        edgeIndices: new Uint32Array(0),
        edgeIds: new Uint32Array(0),
      },
    };
  }
  const buffers = bundle?.buffers || {};
  const edgeProxy = manifest?.edgeProxy || {};
  const edgePositionView = String(edgeProxy.positionsView || "edgePositions");
  const edgeIndexView = String(edgeProxy.indicesView || "edgeIndices");
  const edgeIdView = String(edgeProxy.edgeIdsView || "edgeIds");
  const edgePositions = buffers[edgePositionView] instanceof Float32Array
    ? buffers[edgePositionView]
    : new Float32Array(0);
  const edgeIndices = buffers[edgeIndexView] instanceof Uint32Array
    ? buffers[edgeIndexView]
    : new Uint32Array(0);
  const edgeIds = buffers[edgeIdView] instanceof Uint32Array
    ? buffers[edgeIdView]
    : new Uint32Array(0);
  return {
    schemaVersion: Number(manifest.schemaVersion || 1),
    stepHash: String(manifest.stepHash || ""),
    bbox: transform ? transformBBox(transform, manifest.bbox || {}) : manifest.bbox,
    edges: transformRows(toRows(manifest, "edges", "edgeColumns"), transform),
    proxy: {
      edgePositions: transformPositions(edgePositions, transform),
      edgeIndices,
      edgeIds,
    },
  };
}

function normalizedTransformEntries(value) {
  const entries = value instanceof Map
    ? [...value.entries()]
    : isObject(value)
      ? Object.entries(value)
      : [];
  return entries
    .map(([key, transform]) => [
      String(key || "").trim(),
      Array.isArray(transform) && transform.length >= 16
        ? transform.slice(0, 16).map((component) => Number(component))
        : null
    ])
    .filter(([key, transform]) => key && transform && transform.every(Number.isFinite));
}

function transformForOccurrenceId(transformEntries, occurrenceId) {
  const normalizedOccurrenceId = String(occurrenceId || "").trim();
  const modelTransform = transformEntries.find(([key]) => key === "__model__" || key === "*" || key === "__all__")?.[1] || null;
  let best = null;
  for (const [partId, transform] of transformEntries) {
    if (partId === "__model__" || partId === "*" || partId === "__all__") {
      continue;
    }
    if (
      normalizedOccurrenceId &&
      (
        normalizedOccurrenceId === partId ||
        normalizedOccurrenceId.startsWith(`${partId}.`)
      ) &&
      (!best || partId.length > best[0].length)
    ) {
      best = [partId, transform];
    }
  }
  return best?.[1] || modelTransform;
}

function rowOccurrenceId(row, selectorType) {
  return selectorType === "occurrence"
    ? String(row?.id || "").trim()
    : String(row?.occurrenceId || row?.partId || "").trim();
}

function transformRowsByOccurrence(rows, selectorType, transformEntries) {
  const transforms = [];
  const nextRows = (Array.isArray(rows) ? rows : []).map((row) => {
    const transform = transformForOccurrenceId(transformEntries, rowOccurrenceId(row, selectorType));
    transforms.push(transform);
    return transform ? transformRow(row, transform) : row;
  });
  return { rows: nextRows, transforms };
}

function transformReference(reference, transform) {
  if (!transform) {
    return reference;
  }
  return {
    ...reference,
    pickData: transformPickData(reference.pickData, transform),
  };
}

function transformIndexedProxy({ positions, indices, ids, rowTransforms, elementSize }) {
  if (!(positions instanceof Float32Array) || !(indices instanceof Uint32Array) || !indices.length || !(ids instanceof Uint32Array) || !ids.length) {
    return { positions, indices, ids };
  }
  const elementCount = Math.floor(indices.length / elementSize);
  const nextPositions = new Float32Array(elementCount * elementSize * 3);
  const nextIndices = new Uint32Array(elementCount * elementSize);
  const nextIds = new Uint32Array(elementCount);
  let writeVertex = 0;
  for (let elementIndex = 0; elementIndex < elementCount; elementIndex += 1) {
    const rowIndex = Number(ids[elementIndex]);
    const transform = Number.isInteger(rowIndex) ? rowTransforms[rowIndex] || null : null;
    nextIds[elementIndex] = Number.isInteger(rowIndex) ? rowIndex : 0;
    for (let vertex = 0; vertex < elementSize; vertex += 1) {
      const sourceVertex = Number(indices[(elementIndex * elementSize) + vertex]);
      const sourceOffset = sourceVertex * 3;
      const nextOffset = writeVertex * 3;
      const point = [
        positions[sourceOffset],
        positions[sourceOffset + 1],
        positions[sourceOffset + 2],
      ];
      const transformedPoint = transform ? transformPoint(transform, point) : point;
      nextPositions[nextOffset] = transformedPoint[0];
      nextPositions[nextOffset + 1] = transformedPoint[1];
      nextPositions[nextOffset + 2] = transformedPoint[2];
      nextIndices[(elementIndex * elementSize) + vertex] = writeVertex;
      writeVertex += 1;
    }
  }
  return {
    positions: nextPositions,
    indices: nextIndices,
    ids: nextIds,
  };
}

export function buildTransformedSelectorRuntime(selectorRuntime, transformByPartId = null) {
  const transformEntries = normalizedTransformEntries(transformByPartId);
  if (!selectorRuntime || !transformEntries.length) {
    return selectorRuntime || null;
  }

  const occurrencesResult = transformRowsByOccurrence(selectorRuntime.occurrences, "occurrence", transformEntries);
  const shapesResult = transformRowsByOccurrence(selectorRuntime.shapes, "shape", transformEntries);
  const facesResult = transformRowsByOccurrence(selectorRuntime.faces, "face", transformEntries);
  const edgesResult = transformRowsByOccurrence(selectorRuntime.edges, "edge", transformEntries);
  const referenceTransforms = {
    occurrence: occurrencesResult.transforms,
    shape: shapesResult.transforms,
    face: facesResult.transforms,
    edge: edgesResult.transforms,
    vertex: [],
  };
  const references = (Array.isArray(selectorRuntime.references) ? selectorRuntime.references : [])
    .map((reference) => transformReference(
      reference,
      referenceTransforms[reference?.selectorType]?.[Number(reference?.rowIndex)] || null
    ));
  const referenceMap = new Map(references.map((reference) => [reference.id, reference]));
  const referenceByNormalizedSelector = new Map(references.map((reference) => [reference.normalizedSelector, reference]));
  const referenceByDisplaySelector = new Map(references.map((reference) => [reference.displaySelector, reference]));
  const faceReferenceByRowIndex = new Map(
    references
      .filter((reference) => reference.selectorType === "face")
      .map((reference) => [reference.rowIndex, reference])
  );
  const edgeReferenceByRowIndex = new Map(
    references
      .filter((reference) => reference.selectorType === "edge")
      .map((reference) => [reference.rowIndex, reference])
  );
  const proxy = selectorRuntime.proxy || {};
  const faceProxy = transformIndexedProxy({
    positions: proxy.facePositions,
    indices: proxy.faceIndices,
    ids: proxy.faceIds,
    rowTransforms: facesResult.transforms,
    elementSize: 3,
  });
  const edgeProxy = transformIndexedProxy({
    positions: proxy.edgePositions,
    indices: proxy.edgeIndices,
    ids: proxy.edgeIds,
    rowTransforms: edgesResult.transforms,
    elementSize: 2,
  });

  return {
    ...selectorRuntime,
    bbox: selectorRuntime.bbox ? transformBBox(transformEntries.find(([key]) => key === "__model__" || key === "*" || key === "__all__")?.[1], selectorRuntime.bbox) : selectorRuntime.bbox,
    occurrences: occurrencesResult.rows,
    shapes: shapesResult.rows,
    faces: facesResult.rows,
    edges: edgesResult.rows,
    references,
    referenceMap,
    referenceByNormalizedSelector,
    referenceByDisplaySelector,
    faceReferenceByRowIndex,
    edgeReferenceByRowIndex,
    faceReferenceMap: new Map(references.filter((reference) => reference.selectorType === "face").map((reference) => [reference.id, reference])),
    edgeReferenceMap: new Map(references.filter((reference) => reference.selectorType === "edge").map((reference) => [reference.id, reference])),
    proxy: {
      ...proxy,
      facePositions: faceProxy.positions,
      faceIndices: faceProxy.indices,
      faceIds: faceProxy.ids,
      edgePositions: edgeProxy.positions,
      edgeIndices: edgeProxy.indices,
      edgeIds: edgeProxy.ids,
    },
  };
}

export function buildTransformedDisplayEdgeRuntime(displayEdgeRuntime, transformByPartId = null) {
  const transformEntries = normalizedTransformEntries(transformByPartId);
  if (!displayEdgeRuntime || !transformEntries.length) {
    return displayEdgeRuntime || null;
  }

  const edgesResult = transformRowsByOccurrence(displayEdgeRuntime.edges, "edge", transformEntries);
  const proxy = displayEdgeRuntime.proxy || {};
  const edgeProxy = transformIndexedProxy({
    positions: proxy.edgePositions,
    indices: proxy.edgeIndices,
    ids: proxy.edgeIds,
    rowTransforms: edgesResult.transforms,
    elementSize: 2,
  });
  const modelTransform = transformEntries.find(([key]) => key === "__model__" || key === "*" || key === "__all__")?.[1] || null;

  return {
    ...displayEdgeRuntime,
    bbox: modelTransform && displayEdgeRuntime.bbox ? transformBBox(modelTransform, displayEdgeRuntime.bbox) : displayEdgeRuntime.bbox,
    edges: edgesResult.rows,
    proxy: {
      ...proxy,
      edgePositions: edgeProxy.positions,
      edgeIndices: edgeProxy.indices,
      edgeIds: edgeProxy.ids,
    },
  };
}

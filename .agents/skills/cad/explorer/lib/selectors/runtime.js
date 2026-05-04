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
    return `${row.kind || "shape"}${row.volume ? ` volume=${row.volume}` : row.area ? ` area=${row.area}` : ""}`;
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
    copyText: summary ? `${copyText} ${summary}` : copyText,
    partId,
    occurrenceId: row.occurrenceId ? selectorPrefix(singleOccurrenceId, String(row.occurrenceId)) : "",
    shapeId: row.shapeId ? selectorPrefix(singleOccurrenceId, String(row.shapeId)) : "",
    rowIndex,
    pickData: {
      selectorType,
      rowIndex,
      kind: row.kind || "",
      surfaceType: row.surfaceType || "",
      curveType: row.curveType || "",
      length: row.length ?? null,
      area: row.area ?? null,
      volume: row.volume ?? null,
      bbox: row.bbox || null,
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

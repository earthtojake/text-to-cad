// A component's selector table, joined to its stored mesh.
//
// cadgen derives every selector fact once, from the exact BREP, into a table it
// stores in the part's record beside its display mesh (cadgen/_internal/selector_table.py,
// cadgen/store/parts.py) and serves by part (`/__tess_cache/<part>.selectors.json`):
// each element's name that a ref ends in (`f:`, `e:`, `v:` and its lineage, the
// feature that made it and its number there -- `f:dial.extrude1.3` -- or, where no
// construction names it, its geometric token, 12 hex), an edge's exact length and
// centre, parameters, plane normals, an edge's referenceable flags and relevance,
// face-edge and edge-vertex adjacency, each edge's chain and each face's tangent
// group -- no face's area or centroid, which cadgen measures when a view asks
// (`POST /__cad/measure`, `CadClient.measureFace`). The page
// joins those rows to the mesh it draws -- by ORDINAL, which the table and the
// mesh's face and edge tables share -- so a face's triangle range and an edge's
// segment range are its range on screen, and composes a ref as
// `occurrenceId + "/" + name` (selectors/runtime.js). Nothing here decides a
// fact: a row the table lacks is a row the page does not have.

import { meshEdgePolylines, meshFaceRanges } from "./tessellationCache.js";

// The table's wire schema (cadgen/_internal/selector_table.py
// SELECTOR_TABLE_SCHEMA_VERSION): a table of another is refused, never read
// halfway. tests/python/global/test_artifact_version_policy.py holds both equal.
// 2: element rows carry no id, localId, occurrenceId or shapeId column (an
// occurrence's rows are the part's, placed by the page). 3: element rows lead with
// their name. 4: a shape row carries no volume. 5: a face's and an edge's bbox is its display
// mesh's, within the display chord of the exact box. 6: a face row carries no area, centre,
// relevance or flags, and a shape row no area.
export const SELECTOR_TABLE_SCHEMA_VERSION = 6;

const TABLES = Object.freeze({
  occurrences: "occurrenceColumns", shapes: "shapeColumns", faces: "faceColumns",
  edges: "edgeColumns", vertices: "vertexColumns",
});
const RELATIONS = Object.freeze(["faceEdgeRows", "edgeFaceRows", "edgeVertexRows", "vertexEdgeRows"]);
const FACE_RUN_COLUMNS = Object.freeze(["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"]);

/** The table cadgen stored, from its bytes or text: this schema, with the tables it declares. */
export function parseSelectorTable(source) {
  const text = typeof source === "string" ? source
    : new TextDecoder("utf-8", { fatal: true }).decode(source instanceof ArrayBuffer ? new Uint8Array(source) : source);
  const table = JSON.parse(text);
  if (!table || typeof table !== "object" || Array.isArray(table)) {
    throw new TypeError("A selector table is a JSON object");
  }
  if (table.schemaVersion !== SELECTOR_TABLE_SCHEMA_VERSION) {
    throw new TypeError(`Selector table schema ${table.schemaVersion} is not this client's ${SELECTOR_TABLE_SCHEMA_VERSION}`);
  }
  for (const [rows, columns] of Object.entries(TABLES)) {
    const declared = table.tables?.[columns];
    if (!Array.isArray(declared) || !Array.isArray(table[rows])
        || table[rows].some((row) => !Array.isArray(row) || row.length !== declared.length)) {
      throw new TypeError(`Selector table ${rows} rows do not match their columns`);
    }
  }
  for (const name of RELATIONS) {
    if (!Array.isArray(table.relations?.[name])) throw new TypeError(`Selector table lacks ${name}`);
  }
  return table;
}

function column(table, columns, name) {
  const index = table.tables[columns].indexOf(name);
  if (index < 0) throw new TypeError(`Selector table ${columns} lack ${name}`);
  return index;
}

/**
 * The selector bundle `buildSelectorRuntime` reads: the table's rows, each face's
 * triangle range and each edge's segment range in `component` (a decoded stored
 * mesh, `decodeComponentTessellation`), the face runs and edge proxy over that
 * mesh, and the relations as typed arrays.
 */
export function joinSelectorTable(table, component) {
  if (!component?.faceTable) throw new TypeError("Joining a selector table needs the component's mesh");
  const faceOrdinal = column(table, "faceColumns", "ordinal");
  const edgeOrdinal = column(table, "edgeColumns", "ordinal");
  const rangeByOrd = new Map(meshFaceRanges(component).map((range) => [range.ord, range]));
  const polylineByOrd = new Map(meshEdgePolylines(component).map((edge) => [edge.ord, edge.polyline]));

  const faceRowByOrd = new Map(table.faces.map((row, index) => [row[faceOrdinal], index]));
  const faces = table.faces.map((row) => {
    const range = rangeByOrd.get(row[faceOrdinal]);
    return [...row, range ? range.indexStart / 3 : 0, range ? range.indexCount / 3 : 0];
  });

  const edgePositions = [];
  const edgeIndices = [];
  const edgeIds = [];
  const edges = table.edges.map((row, edgeRow) => {
    const polyline = polylineByOrd.get(row[edgeOrdinal]) || new Float32Array(0);
    const pointBase = edgePositions.length / 3;
    const segmentStart = edgeIds.length;
    for (const value of polyline) edgePositions.push(value);
    const pointCount = polyline.length / 3;
    for (let i = 0; i + 1 < pointCount; i += 1) {
      edgeIndices.push(pointBase + i, pointBase + i + 1);
      edgeIds.push(edgeRow);
    }
    return [...row, segmentStart, edgeIds.length - segmentStart];
  });

  // One run per face range of the mesh: (occurrenceRow, primitiveIndex, triangleStart,
  // triangleCount, faceRow), what buildGlbFaceIdsForPart resolves a triangle to a face by.
  const runs = [];
  for (const range of rangeByOrd.values()) {
    const faceRow = faceRowByOrd.get(range.ord);
    if (faceRow === undefined) continue;
    runs.push(0, 0, range.indexStart / 3, range.indexCount / 3, faceRow);
  }

  const manifest = {
    ...table,
    stats: {
      ...(table.stats || {}),
      faceProxyRunCount: runs.length / FACE_RUN_COLUMNS.length,
      edgeProxyPointCount: edgePositions.length / 3,
      edgeProxySegmentCount: edgeIds.length,
    },
    tables: {
      ...table.tables,
      faceColumns: [...table.tables.faceColumns, "triangleStart", "triangleCount"],
      edgeColumns: [...table.tables.edgeColumns, "segmentStart", "segmentCount"],
    },
    faces,
    edges,
    faceProxy: { source: "part", runsView: "faceRuns", runColumns: [...FACE_RUN_COLUMNS] },
    edgeProxy: { positionsView: "edgePositions", indicesView: "edgeIndices", edgeIdsView: "edgeIds" },
    relations: Object.fromEntries(RELATIONS.map((name) => [`${name}View`, name])),
    buffers: { littleEndian: true },
  };
  return {
    manifest,
    buffers: {
      faceRuns: Uint32Array.from(runs),
      edgePositions: Float32Array.from(edgePositions),
      edgeIndices: Uint32Array.from(edgeIndices),
      edgeIds: Uint32Array.from(edgeIds),
      ...Object.fromEntries(RELATIONS.map((name) => [name, Uint32Array.from(table.relations[name])])),
    },
  };
}

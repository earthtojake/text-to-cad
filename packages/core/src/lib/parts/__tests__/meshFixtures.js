// Test-only access to stored parts: the committed fixture parts (`../fixtures`, written by cadgen
// through make_fixtures.py), the row a host's part store answers for a mesh, and in-memory stores
// serving parts as a host does. cadgen is the only producer in the product; nothing here ships.

import { createHash } from "node:crypto";
import fs from "node:fs";

import { decodeComponentTessellation, isPartKey, partRow } from "../tessellationCache.js";
import { encodeMeshFixture, partMeshFacts, testPartKey } from "../testing.js";

export { encodeMeshFixture, testPartKey };

const FIXTURES = new URL("../fixtures/", import.meta.url);
const MANIFEST = JSON.parse(fs.readFileSync(new URL("fixtures.json", FIXTURES), "utf8"));

export function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

/** One fixture component's selector table, as cadgen stores it (parsed). */
export function selectorTableFixture(name) {
  return JSON.parse(fs.readFileSync(new URL(`${name}.selectors.json`, FIXTURES), "utf8"));
}

// A selector table's facts for a row: a fixture's own, else a stand-in no test reads.
const NO_TABLE = Object.freeze({ object: "e".repeat(64), byteLength: 2, faceCount: 0, edgeCount: 0, vertexCount: 0 });

/**
 * The row a host's part store answers a probe with, for a valid mesh body: the part it names, its
 * mesh's facts and address, and `selectors` (a selector table's facts, a stand-in when omitted).
 */
export function partRowFor(bytes, selectors = NO_TABLE) {
  const decoded = decodeComponentTessellation(bytes);
  if (!decoded) throw new TypeError("not a valid stored mesh body");
  const row = partRow(decoded.part, { glb: { object: sha256Hex(bytes), ...partMeshFacts(bytes) }, selectors });
  if (!row) throw new TypeError("not a valid part record");
  return row;
}

/** One fixture component's stored display mesh, with its part and its row. */
export function meshFixture(name) {
  const bytes = new Uint8Array(fs.readFileSync(new URL(`${name}.glb`, FIXTURES)));
  const table = fs.readFileSync(new URL(`${name}.selectors.json`, FIXTURES));
  const { stats } = JSON.parse(table.toString("utf8"));
  const selectors = { object: sha256Hex(table), byteLength: table.byteLength, faceCount: stats.faceCount,
    edgeCount: stats.edgeCount, vertexCount: stats.vertexCount };
  return { bytes, part: MANIFEST[name].part, row: partRowFor(bytes, selectors) };
}

/**
 * A part store in memory, answering as a host's /__tess_cache/ routes do: probes, exact reads and
 * batches over `bodies`; every read and request is counted.
 */
export function memoryMeshProvider(bodies = []) {
  const stored = new Map();
  const add = (bytes) => {
    const row = partRowFor(bytes);
    stored.set(row.part, { row, bytes });
  };
  for (const bytes of bodies) add(bytes);
  const counts = { probes: 0, reads: 0, batches: 0 };
  const read = (row) => {
    const entry = stored.get(row?.part);
    return entry && entry.row.glb.object === row.glb.object ? entry.bytes.slice() : null;
  };
  return {
    counts,
    add,
    async probeMany(parts) {
      counts.probes += 1;
      return parts.map((part) => stored.get(part)?.row || null);
    },
    async getProbed(row) {
      counts.reads += 1;
      return read(row);
    },
    async getManyProbed(rows) {
      counts.batches += 1;
      return rows.map(read);
    },
  };
}

/**
 * A part store that holds a part for every key it is asked: `name`'s stored mesh (its display
 * geometry), re-encoded to name the part. For loaders under test that open many distinct
 * components; every read is counted.
 */
export function everyKeyMeshProvider(name = "sun_gear") {
  const decoded = decodeComponentTessellation(meshFixture(name).bytes);
  const bodies = new Map();
  const counts = { probes: 0, reads: 0, batches: 0 };
  const bodyFor = (part) => {
    if (!bodies.has(part)) {
      if (!isPartKey(part)) return null;
      bodies.set(part, encodeMeshFixture(decoded.component, { part }));
    }
    return bodies.get(part);
  };
  const read = (row) => {
    const bytes = bodyFor(row?.part);
    return bytes && sha256Hex(bytes) === row.glb.object ? bytes.slice() : null;
  };
  return {
    counts,
    async probeMany(parts) {
      counts.probes += 1;
      return parts.map((part) => (bodyFor(part) ? partRowFor(bodyFor(part)) : null));
    },
    async getProbed(row) {
      counts.reads += 1;
      return read(row);
    },
    async getManyProbed(rows) {
      counts.batches += 1;
      return rows.map(read);
    },
  };
}

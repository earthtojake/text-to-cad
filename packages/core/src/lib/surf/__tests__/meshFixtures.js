// Test-only access to stored component meshes: the committed fixture pairs
// (`../fixtures`, written by cadgen through make_fixtures.py), the probe row a
// host's mesh store answers for a body, and in-memory stores serving bodies as
// a host does. cadgen is the only producer in the product; nothing here ships.

import { createHash } from "node:crypto";
import fs from "node:fs";

import { lodTessellationForLevel } from "../lodPolicy.js";
import { installTestTessellationLadder } from "../testing.js";
import {
  MESH_INDEX_SCHEMA,
  decodeComponentTessellation,
  tessellationPayloadFacts,
} from "../tessellationCache.js";
import { encodeMeshFixture } from "../testing.js";

export { encodeMeshFixture };

const FIXTURES = new URL("../fixtures/", import.meta.url);
const MANIFEST = JSON.parse(fs.readFileSync(new URL("fixtures.json", FIXTURES), "utf8"));

export function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

/** One fixture component's SURF bytes and the identity its meshes are bound to. */
export function surfFixture(name) {
  const bytes = new Uint8Array(fs.readFileSync(new URL(`${name}.surf`, FIXTURES)));
  const { surfaceInput, surfaceObject } = MANIFEST[name];
  return { bytes, arrayBuffer: () => bytes.slice().buffer, surfaceInput, surfaceObject };
}

/** One fixture component's stored mesh at a viewer LOD level, with its probe row. */
export function meshFixture(name, level = 1) {
  installTestTessellationLadder();
  const bytes = new Uint8Array(fs.readFileSync(new URL(`${name}.l${level}.glb`, FIXTURES)));
  const { surfaceInput, surfaceObject } = MANIFEST[name];
  return { bytes, surfaceInput, surfaceObject, tessellation: lodTessellationForLevel(level), row: probeRowFor(bytes) };
}

/** The index record a host's mesh store answers a probe with, for a valid body. */
export function probeRowFor(bytes) {
  const facts = tessellationPayloadFacts(bytes);
  if (!facts) throw new TypeError("not a valid stored mesh body");
  return Object.freeze({
    schemaVersion: MESH_INDEX_SCHEMA,
    object: sha256Hex(bytes),
    byteLength: facts.byteLength,
    decodedBytes: facts.decodedBytes,
    surfaceInput: facts.surfaceInput,
    surfaceObject: facts.surfaceObject,
    tessellationInput: facts.tessellationInput,
    renderIdentity: facts.renderIdentity,
    quality: facts.quality,
    tessellatorVersion: facts.tessellatorVersion,
    payloadVersion: facts.payloadVersion,
    vertexCount: facts.vertexCount,
    indexCount: facts.indexCount,
    faceCount: facts.faceCount,
    edgeCount: facts.edgeCount,
    edgePointCount: facts.edgePointCount,
  });
}

/**
 * A mesh store in memory, answering as a host's /__tess_cache/ routes do: probes, exact reads and
 * batches over `bodies`. `produce`, when given, is the bodies a produce request makes (a host that
 * meshes on request); every read and request is counted.
 */
export function memoryMeshProvider(bodies = [], { produce = null } = {}) {
  const stored = new Map();
  const add = (bytes) => {
    const row = probeRowFor(bytes);
    stored.set(row.tessellationInput, { row, bytes });
  };
  for (const bytes of bodies) add(bytes);
  const pending = new Map((produce || []).map((bytes) => [probeRowFor(bytes).tessellationInput, bytes]));
  const counts = { probes: 0, reads: 0, batches: 0, produced: 0 };
  const read = (row) => {
    const entry = stored.get(row?.tessellationInput);
    return entry && entry.row.object === row.object ? entry.bytes.slice() : null;
  };
  return {
    counts,
    add,
    async probeMany(keys) {
      counts.probes += 1;
      return keys.map((key) => stored.get(key)?.row || null);
    },
    async getProbed(row) {
      counts.reads += 1;
      return read(row);
    },
    async getManyProbed(rows) {
      counts.batches += 1;
      return rows.map(read);
    },
    ...(produce ? {
      async produceMany(keys) {
        return keys.map((key) => {
          const bytes = pending.get(key);
          if (!bytes) return stored.get(key)?.row || null;
          counts.produced += 1;
          pending.delete(key);
          add(bytes);
          return stored.get(key).row;
        });
      },
    } : {}),
  };
}

/**
 * A mesh store that holds a mesh for every key it is asked: `name`'s stored mesh (its level-1
 * geometry), re-encoded for the key's surface input and tolerances and bound to `surfaceObject`.
 * For loaders under test that open many distinct components; every read is counted.
 */
export function everyKeyMeshProvider(name = "sun_gear", { surfaceObject = "a".repeat(64) } = {}) {
  const fixture = meshFixture(name, 1);
  const decoded = decodeComponentTessellation(fixture.bytes, { surfaceInput: fixture.surfaceInput });
  const bodies = new Map();
  const counts = { probes: 0, reads: 0, batches: 0 };
  const bodyFor = (key) => {
    if (!bodies.has(key)) {
      const match = /^([0-9a-f]{64})-t\d+-p\d+-l([0-9a-f]{16})-a([0-9a-f]{16})$/.exec(String(key));
      if (!match) return null;
      const f64 = (hex) => new DataView(Uint8Array.from(hex.match(/../g), (pair) => parseInt(pair, 16)).buffer).getFloat64(0);
      bodies.set(key, encodeMeshFixture(decoded.component, {
        surfaceInput: match[1], surfaceObject,
        tessellation: { chordTolerance: f64(match[2]), angleTolerance: f64(match[3]) },
        partColor: decoded.partColor,
      }));
    }
    return bodies.get(key);
  };
  const read = (row) => {
    const bytes = bodyFor(row?.tessellationInput);
    return bytes && sha256Hex(bytes) === row.object ? bytes.slice() : null;
  };
  return {
    counts,
    async probeMany(keys) {
      counts.probes += 1;
      return keys.map((key) => (bodyFor(key) ? probeRowFor(bodyFor(key)) : null));
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

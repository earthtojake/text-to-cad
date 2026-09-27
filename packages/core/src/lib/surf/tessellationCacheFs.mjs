// Node filesystem provider for the same immutable object/index mesh store used
// by cadgen's Python viewer and snapshot hosts. Objects are published before a
// validated input index; reads bind L to the probed M and verify both bytes and
// v4 provenance. This module is the only filesystem-touching JS cache layer.

import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  TESS_MESH_INDEX_SCHEMA,
  TESS_MAX_INDEX_BYTES,
  tessellationPayloadFacts,
  validateTessellationProbeRow,
} from "./tessellationCache.js";

export class TessellationMeshConflictError extends Error {
  constructor(message = "tessellation producer returned different bytes for the same immutable input") {
    super(message);
    this.name = "TessellationMeshConflictError";
  }
}

export function tessellationCacheEnabled(env = process.env) {
  return env.CADGEN_MESH_CACHE !== "0";
}

export function cadgenCacheRootDir(env = process.env) {
  const override = (env.CADGEN_CACHE_DIR || "").trim();
  if (override) {
    const expanded = override.replace(/^~(?=$|[/\\])/, os.homedir());
    const resolved = path.resolve(expanded);
    if (!path.isAbsolute(expanded)) env.CADGEN_CACHE_DIR = resolved;
    return resolved;
  }
  if (process.platform === "win32") {
    const localAppData = (env.LOCALAPPDATA || "").trim();
    if (localAppData) return path.join(localAppData, "cadgen");
  } else {
    const xdgCacheHome = (env.XDG_CACHE_HOME || "").trim();
    if (xdgCacheHome) return path.join(xdgCacheHome, "cadgen");
  }
  return path.join(os.homedir(), ".cache", "cadgen");
}

export function tessellationCacheDir(env = process.env) {
  return path.join(cadgenCacheRootDir(env), "index", "mesh");
}

function digestBytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function objectPath(digest, env = process.env) {
  return path.join(cadgenCacheRootDir(env), "objects", digest.slice(0, 2), digest.slice(2));
}

function indexPath(key, env = process.env) {
  return path.join(tessellationCacheDir(env), key);
}

function tempPath(target) {
  return path.join(path.dirname(target), `.${path.basename(target)}.${process.pid}.${randomUUID()}.tmp`);
}

function writeAtomic(target, bytes) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temp = tempPath(target);
  try {
    fs.writeFileSync(temp, bytes, { flag: "wx" });
    fs.renameSync(temp, target);
  } finally {
    try { fs.unlinkSync(temp); } catch { /* already renamed or never created */ }
  }
}

function readBoundedJson(target) {
  const descriptor = fs.openSync(target, "r");
  try {
    const stat = fs.fstatSync(descriptor);
    if (!stat.isFile() || stat.size <= 0 || stat.size > TESS_MAX_INDEX_BYTES) return null;
    const bytes = Buffer.allocUnsafe(stat.size);
    if (fs.readSync(descriptor, bytes, 0, bytes.length, 0) !== bytes.length) return null;
    return JSON.parse(bytes.toString("utf8"));
  } finally {
    fs.closeSync(descriptor);
  }
}

export function probeCachedTessellation(key, env = process.env) {
  if (!tessellationCacheEnabled(env)) return null;
  try {
    const row = validateTessellationProbeRow(readBoundedJson(indexPath(key, env)), { tessellationInput: key });
    if (!row) return null;
    const stat = fs.statSync(objectPath(row.object, env));
    return stat.isFile() && stat.size === row.byteLength ? row : null;
  } catch {
    return null;
  }
}

function readExactObjectBytes(target, byteLength, maxBytes = byteLength) {
  if (!Number.isSafeInteger(byteLength) || byteLength <= 0
    || !Number.isSafeInteger(maxBytes) || maxBytes < byteLength) return null;
  let descriptor;
  try {
    descriptor = fs.openSync(target, "r");
    const stat = fs.fstatSync(descriptor);
    if (!stat.isFile() || stat.size !== byteLength || stat.size > maxBytes) return null;
    // Allocate only the admitted immutable body's exact size. Reading through
    // the already-open descriptor prevents a path replacement from expanding
    // this allocation; the second fstat rejects in-place growth or truncation.
    const buffer = Buffer.allocUnsafe(byteLength);
    let offset = 0;
    while (offset < buffer.byteLength) {
      const read = fs.readSync(descriptor, buffer, offset, buffer.byteLength - offset, offset);
      if (read <= 0) return null;
      offset += read;
    }
    const finalStat = fs.fstatSync(descriptor);
    if (!finalStat.isFile() || finalStat.size !== byteLength) return null;
    return new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  } catch {
    return null;
  } finally {
    if (descriptor !== undefined) {
      try { fs.closeSync(descriptor); } catch { /* already closed or invalid */ }
    }
  }
}

export function readCachedTessellationBytes(key, {
  expectedObject,
  maxBytes,
  env = process.env,
} = {}) {
  const row = probeCachedTessellation(key, env);
  if (!row || (expectedObject !== undefined && row.object !== expectedObject)) return null;
  const limit = maxBytes === undefined ? row.byteLength : Number(maxBytes);
  if (!Number.isSafeInteger(limit) || limit < row.byteLength) return null;
  const bytes = readExactObjectBytes(objectPath(row.object, env), row.byteLength, limit);
  if (!bytes || digestBytes(bytes) !== row.object || !tessellationPayloadFacts(bytes, row)) return null;
  return bytes;
}

function recordForPayload(key, bytes) {
  const facts = tessellationPayloadFacts(bytes, { tessellationInput: key });
  if (!facts) throw new TypeError("invalid TESS v4 payload");
  const row = validateTessellationProbeRow({
    schemaVersion: TESS_MESH_INDEX_SCHEMA,
    object: digestBytes(bytes),
    ...facts,
  }, { tessellationInput: key });
  if (!row) throw new TypeError("invalid TESS v4 mesh record");
  return row;
}

function putObject(row, bytes, env) {
  const target = objectPath(row.object, env);
  const existing = readExactObjectBytes(target, row.byteLength);
  if (existing && digestBytes(existing) === row.object) return;
  writeAtomic(target, bytes);
  const verified = readExactObjectBytes(target, row.byteLength);
  if (!verified || digestBytes(verified) !== row.object) {
    throw new Error(`tessellation object address mismatch for ${row.object}`);
  }
}

export function writeCachedTessellationBytes(key, bytes, env = process.env) {
  if (!tessellationCacheEnabled(env)) return null;
  const payload = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const row = recordForPayload(key, payload);
  const prior = probeCachedTessellation(key, env);
  if (prior && (prior.object !== row.object || prior.surfaceObject !== row.surfaceObject)
    && readCachedTessellationBytes(key, { expectedObject: prior.object, env })) {
    throw new TessellationMeshConflictError();
  }
  putObject(row, payload, env);
  writeAtomic(indexPath(key, env), JSON.stringify(row));
  return row;
}

export function createFsTessellationCacheProvider(env = process.env) {
  return {
    async probeMany(keys) {
      return keys.map((key) => probeCachedTessellation(key, env));
    },
    async getProbed(row, { maxBytes } = {}) {
      const validated = validateTessellationProbeRow(row);
      return validated ? readCachedTessellationBytes(validated.tessellationInput, {
        expectedObject: validated.object,
        maxBytes,
        env,
      }) : null;
    },
    async put(key, bytes) {
      return writeCachedTessellationBytes(key, bytes, env);
    },
  };
}

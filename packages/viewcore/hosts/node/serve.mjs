#!/usr/bin/env node
// The view core as a job server: the engine's pool jobs (meshing a part, its table, its measure, a pick's facts,
// reading an .xbf, exporting one, drawing a still) answered by the core in one long-lived Node process, over its standard streams.
//
//   node serve.mjs [VIEWCORE_WASM]
//
// One process, one thread, one job at a time, in the order asked. Several run side by side; none shares anything.
// It exits 0 when its input closes or a `close` job is answered.
//
// A frame, either way:
//   8 bytes   N, the length of the rest of the frame (unsigned, big-endian)
//   4 bytes   H, the header's length (unsigned, big-endian)
//   H bytes   the header: one JSON object, UTF-8
//   N-4-H     the payloads, end to end; the header's "payloads" lists their lengths in order
//
// A request's header: {"id": any, "job": NAME, ..., "payloads": [lengths]}. Its answer carries the same "id" and
// either {"ok": true, ..., "payloads": [lengths]} or {"ok": false, "job": NAME, "error": TEXT}: a job the kernel
// refuses, an unknown job and a frame this cannot read are each an answer, never the server's end. A frame longer
// than MAX_FRAME is passed over as it comes, unbuffered, and answered so. A job the module faults on (a WebAssembly
// trap: bytes OCCT reads out of bounds) is refused, and the module is started again from its compiled code before
// the next, its kept parts, documents and buffers let go; so is a module left over RENEW_BYTES by a job.
//
// Jobs (README.md says each one's engine counterpart):
//   about      {}                                             -> {abi, occt, memoryBytes}
//   mesh       {tolerance?, angle?} + [shape bytes]           -> {unmeshed: {ordinal: text}, seconds} + [XBM2 buffer]
//   table      {key?, unmeshed: [ordinals], measure?} + [shape bytes] -> [table JSON, measure JSON if asked]
//   measured   {keys?: [..]} + [shape bytes, ...]             -> [measure JSON, ...] in the order given
//   fact       {key?, method, args} + [shape bytes]           -> [JSON]; method one of face, edge, vertex (args:
//              [ordinal]), groups ([]), elements ([[unmeshed ordinals]]), measured ([])
//   read_xbf   {path}                                         -> {path, version: [mtime_ns as text, size],
//              parts: [{key, name}, ...]} + [structure JSON, each part's shape bytes in the parts' order]
//   export     {path, format: step | stl | threemf | glb}     -> [the file's bytes]
//   render     {scene, keys?} + [the buffers the scene names, in order] -> {width, height, format, seconds} + [the
//              picture: RGBA bytes, or a PNG where scene.format is "png"]. `keys` names buffers to keep, by their
//              place: one sent with a key is kept under it (the last KEPT_BYTES of them), one sent empty with a key
//              is the one kept; where a key names nothing kept the answer is {missing: [keys]} and no picture
//   forget     {keys?}                                        -> {kept, keptBytes}: those buffers (or all) let go
//   close      {}                                             -> {} and the process ends
// A part named by "key" keeps its topology for the next job naming it (the last KEPT parts), as an engine pool
// process does; an .xbf read stays open for an export of the same file as it stood (the last DOCUMENTS).
import { createHash } from "node:crypto";
import { realpathSync, readFileSync, statSync } from "node:fs";
import { basename, extname } from "node:path";

import { isFault } from "../web/viewcore.js";
import { DEFAULT_WASM, EXPORTS, loadCore } from "./viewcore.mjs";

const MAX_FRAME = 512 * 2 ** 20; // a still's meshes sent whole, or a large part's shape bytes, with room
const RENEW_BYTES = 512 * 2 ** 20; // a module's memory never shrinks: past this after a job, it is started again
const KEPT = 32;
const DOCUMENTS = 2;
const KEPT_BYTES = 768 * 2 ** 20; // a still's buffers kept by key: meshes, the environment
const KINDS = { face: 0, edge: 1, vertex: 2 };

const core = await loadCore(process.argv[2] || DEFAULT_WASM);
const parts = new Map(); // key -> Doc of one part, the least recently used first
const documents = new Map(); // "realpath\0mtime_ns\0size" -> { doc, path, version }
const buffers = new Map(); // key -> a still's buffer (its own copy), the least recently used first
let buffersBytes = 0;

/** A still's buffers, in the scene's order: each as sent, or the one kept under its key; the keys nothing answers. */
function stillBuffers(keys, payloads) {
  if (keys === undefined || keys === null) return { parts: payloads, missing: [] };
  if (!Array.isArray(keys) || keys.length > payloads.length || !keys.every((k) => k === null || typeof k === "string"))
    throw new Error("keys is a list of keys (or null), one for each buffer it names");
  const missing = [];
  const parts = payloads.map((sent, at) => {
    const key = keys[at] ?? null;
    if (key === null) return sent;
    if (sent.byteLength) {
      const old = buffers.get(key);
      if (old) { buffersBytes -= old.byteLength; buffers.delete(key); }
      const own = Uint8Array.from(sent); // the frame's bytes are not held past the job
      buffers.set(key, own);
      buffersBytes += own.byteLength;
      return own;
    }
    const kept = buffers.get(key);
    if (!kept) { missing.push(key); return sent; }
    buffers.delete(key);
    buffers.set(key, kept);
    return kept;
  });
  // The budget, kept after the still's own buffers are in hand: the oldest go first, never one this still uses.
  const used = new Set(keys.filter((k) => k !== null));
  for (const [key, held] of buffers) {
    if (buffersBytes <= KEPT_BYTES) break;
    if (used.has(key)) continue;
    buffers.delete(key);
    buffersBytes -= held.byteLength;
  }
  return { parts, missing };
}

/**
 * The part of `key` and these bytes, kept (or opened for this job alone where no key names it). A part is kept under
 * its key and its bytes' digest, so the same key sent with other bytes is another part, never the one kept.
 */
function part(key, bytes) {
  if (key === undefined || key === null) return { doc: core.openShape(bytes), kept: false };
  if (typeof key !== "string") throw new Error("key is a part's key, a string");
  const id = `${key}\0${createHash("sha256").update(bytes).digest("hex")}`;
  let doc = parts.get(id);
  if (doc) parts.delete(id); else doc = core.openShape(bytes);
  parts.set(id, doc);
  while (parts.size > KEPT) {
    const [oldest, held] = parts.entries().next().value;
    parts.delete(oldest);
    held.close();
  }
  return { doc, kept: true };
}

/** `work(doc)` on the part; a part opened for the job alone is closed after it, and a kept one a failure drops. */
function withPart(key, bytes, work) {
  const { doc, kept } = part(key, bytes);
  try {
    return work(doc);
  } catch (error) {
    if (kept) for (const [id, held] of parts) if (held === doc) { parts.delete(id); doc.close(); break; }
    throw error;
  } finally {
    if (!kept) doc.close();
  }
}

/** The .xbf at `path` as it stands, opened once for the jobs that follow on the same file. */
function document(path) {
  const real = realpathSync(path);
  const stat = statSync(real, { bigint: true });
  const version = [String(stat.mtimeNs), Number(stat.size)];
  const id = `${real}\0${version[0]}\0${version[1]}`;
  let held = documents.get(id);
  if (held) documents.delete(id);
  else held = { doc: core.openXbf(readFileSync(real), basename(real, extname(real))), path: real, version };
  documents.set(id, held);
  while (documents.size > DOCUMENTS) {
    const [oldest, gone] = documents.entries().next().value;
    documents.delete(oldest);
    gone.doc.close();
  }
  return held;
}

const one = (payloads, job) => {
  if (payloads.length !== 1) throw new Error(`${job} takes one payload, a part's shape bytes (${payloads.length} given)`);
  return payloads[0];
};
const ordinal = (value) => Number.isInteger(value) && value >= 1 && value < 2 ** 31;
const ordinals = (value, what) => {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || !value.every(ordinal)) throw new Error(`${what} is a list of ordinals, each 1 to 2^31 - 1`);
  return value;
};

const JOBS = {
  about: () => ({ header: { abi: core.x.vc_abi_version(), occt: core.occtVersion, memoryBytes: core.memoryBytes } }),

  mesh(header, payloads) {
    const bytes = one(payloads, "mesh");
    const own = (header.tolerance ?? null) !== null || (header.angle ?? null) !== null;
    return withPart(undefined, bytes, (doc) => {
      const started = performance.now();
      const buffer = own ? doc.meshAt(0, header.tolerance ?? 0, header.angle ?? 0) : doc.mesh(0);
      const seconds = (performance.now() - started) / 1000;
      return { header: { unmeshed: doc.unmeshed(0), seconds }, payloads: [buffer] };
    });
  },

  table(header, payloads) {
    const bytes = one(payloads, "table");
    return withPart(header.key, bytes, (doc) => {
      const answers = [doc.tableBytes(0, ordinals(header.unmeshed, "unmeshed"))];
      if (header.measure) answers.push(doc.measureBytes(0));
      return { payloads: answers };
    });
  },

  measured(header, payloads) {
    const keys = header.keys ?? [];
    if (!Array.isArray(keys) || (keys.length && keys.length !== payloads.length)) throw new Error("measured takes a key for each payload, or none");
    return { payloads: payloads.map((bytes, at) => withPart(keys[at], bytes, (doc) => doc.measureBytes(0))) };
  },

  fact(header, payloads) {
    const bytes = one(payloads, "fact");
    const args = header.args ?? [];
    if (!Array.isArray(args)) throw new Error("args is a list");
    return withPart(header.key, bytes, (doc) => {
      switch (header.method) {
        case "face": case "edge": case "vertex":
          if (!ordinal(args[0])) throw new Error(`${header.method} takes an ordinal, 1 to 2^31 - 1`);
          if (header.method === "face" && args[1] === false) throw new Error("a face without its check is its table's row: ask elements");
          return { payloads: [doc.factBytes(0, KINDS[header.method], args[0])] };
        case "groups": return { payloads: [doc.groupsBytes(0)] };
        case "elements": return { payloads: [doc.tableBytes(0, ordinals(args[0], "elements' argument"))] };
        case "measured": return { payloads: [doc.measureBytes(0)] };
        default: throw new Error(`no method ${JSON.stringify(header.method)}: face, edge, vertex, groups, elements or measured`);
      }
    });
  },

  read_xbf(header) {
    if (typeof header.path !== "string") throw new Error("read_xbf takes a path");
    const { doc, path, version } = document(header.path);
    const structure = doc.structureBytes();
    const listed = JSON.parse(new TextDecoder().decode(structure)).prototypes.map(({ index, key, name }) => ({ index, key, name }));
    return {
      header: { path, version, parts: listed.map(({ key, name }) => ({ key, name })) },
      payloads: [structure, ...listed.map(({ index }) => doc.shapeBytes(index))],
    };
  },

  export(header) {
    if (typeof header.path !== "string") throw new Error("export takes a path");
    if (!Object.hasOwn(EXPORTS, header.format)) throw new Error(`no format ${JSON.stringify(header.format)}: ${Object.keys(EXPORTS).join(", ")}`);
    return { payloads: [document(header.path).doc.exportBytes(header.format)] };
  },

  render(header, payloads) {
    const scene = header.scene;
    if (scene === null || typeof scene !== "object" || Array.isArray(scene)) throw new Error("render takes a scene");
    const { parts, missing } = stillBuffers(header.keys, payloads);
    if (missing.length) return { header: { missing } };
    const started = performance.now();
    const picture = core.render(scene, parts);
    const seconds = (performance.now() - started) / 1000;
    return { header: { width: scene.width, height: scene.height, format: scene.format ?? "rgba", seconds }, payloads: [picture] };
  },

  forget(header) {
    const keys = header.keys ?? [...buffers.keys()];
    if (!Array.isArray(keys)) throw new Error("forget takes a list of keys, or none for all");
    for (const key of keys) {
      const held = buffers.get(key);
      if (held) { buffers.delete(key); buffersBytes -= held.byteLength; }
    }
    return { header: { kept: buffers.size, keptBytes: buffersBytes } };
  },

  close: () => ({ header: {}, last: true }),
};

function frame(header, payloads = []) {
  const head = Buffer.from(JSON.stringify({ ...header, payloads: payloads.map((p) => p.byteLength) }), "utf8");
  const sizes = Buffer.alloc(12);
  sizes.writeBigUInt64BE(BigInt(4 + head.length + payloads.reduce((n, p) => n + p.byteLength, 0)), 0);
  sizes.writeUInt32BE(head.length, 8);
  return [sizes, head, ...payloads.map((p) => Buffer.from(p.buffer, p.byteOffset, p.byteLength))];
}

function send(chunks) {
  return new Promise((resolve, reject) => {
    process.stdout.write(Buffer.concat(chunks), (error) => (error ? reject(error) : resolve()));
  });
}

/** One frame's body answered; false once the server should end. */
async function answer(body) {
  let id = null, job = null;
  try {
    if (body.length < 4) throw new Error("malformed frame: no header length");
    const headLength = body.readUInt32BE(0);
    if (4 + headLength > body.length) throw new Error("malformed frame: the header is longer than the frame");
    let header;
    try { header = JSON.parse(body.toString("utf8", 4, 4 + headLength)); } catch { throw new Error("malformed frame: the header is no JSON"); }
    if (header === null || typeof header !== "object" || Array.isArray(header)) throw new Error("malformed frame: the header is no object");
    id = header.id ?? null;
    job = typeof header.job === "string" ? header.job : null;
    const lengths = header.payloads ?? [];
    if (!Array.isArray(lengths) || !lengths.every((n) => Number.isInteger(n) && n >= 0)) throw new Error("malformed frame: payloads is a list of lengths");
    if (lengths.reduce((n, l) => n + l, 0) !== body.length - 4 - headLength) throw new Error("malformed frame: the payloads' lengths are not the frame's");
    const payloads = [];
    let at = 4 + headLength;
    for (const length of lengths) { payloads.push(body.subarray(at, at + length)); at += length; }
    if (!job || !Object.hasOwn(JOBS, job)) throw new Error(`no job ${JSON.stringify(header.job)}: ${Object.keys(JOBS).join(", ")}`);
    const found = JOBS[job](header, payloads);
    await send(frame({ id, ok: true, ...(found.header || {}) }, found.payloads || []));
    if (core.memoryBytes > RENEW_BYTES) await renew();
    return !found.last;
  } catch (error) {
    let said = String(error?.message || error);
    if (isFault(error)) {
      await renew();
      said = `the view core faulted on this job (${said}) and was started again; the parts, documents and buffers it kept are let go`;
    } else if (core.memoryBytes > RENEW_BYTES) {
      await renew();
    }
    await send(frame({ id, ok: false, job, error: said }));
    return true;
  }
}

/** The module started again from its compiled code: what it kept is let go with its memory. */
async function renew() {
  parts.clear();
  documents.clear();
  buffers.clear();
  buffersBytes = 0;
  await core.renew();
}

// The input read frame by frame: the chunks of a frame not yet whole are held as they came and joined once, when
// the frame is whole (joining at every chunk would copy a large frame over and over); an oversized frame is let by.
const pending = []; // chunks held, in order
let pendingBytes = 0;
let need = 8; // the bytes the next step waits for: a frame's length, then the whole frame
let skipping = 0n;
let open = true;
const passedOver = () => send(frame({ id: null, ok: false, job: null, error: `a frame longer than ${MAX_FRAME} bytes was passed over` }));
/** The first `count` bytes held, taken out as one buffer. */
function take(count) {
  const joined = pending.length === 1 ? pending[0] : Buffer.concat(pending, pendingBytes);
  pending.length = 0;
  const rest = joined.subarray(count);
  if (rest.length) pending.push(rest);
  pendingBytes = rest.length;
  return joined.subarray(0, count);
}
for await (let chunk of process.stdin) {
  if (skipping > 0n) {
    const passed = BigInt(chunk.length) < skipping ? BigInt(chunk.length) : skipping;
    skipping -= passed;
    chunk = chunk.subarray(Number(passed));
    if (skipping > 0n) continue;
    await passedOver();
  }
  if (chunk.length) pending.push(chunk), pendingBytes += chunk.length;
  while (open && pendingBytes >= need) {
    if (need === 8) {
      const length = take(8).readBigUInt64BE(0);
      if (length > BigInt(MAX_FRAME)) {
        const here = BigInt(pendingBytes);
        if (here >= length) { take(Number(length)); await passedOver(); continue; }
        skipping = length - here;
        pending.length = 0, pendingBytes = 0;
        break;
      }
      need = Number(length);
      if (need === 0) { need = 8; open = await answer(Buffer.alloc(0)); }
      continue;
    }
    const body = take(need);
    need = 8;
    open = await answer(body);
  }
  if (!open) break;
}
process.exit(0);

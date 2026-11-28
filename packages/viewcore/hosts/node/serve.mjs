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
// than MAX_FRAME is passed over as it comes, unbuffered, and answered so.
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
//   render     {scene} + [the buffers the scene names, in order] -> {width, height, format, seconds} + [the picture:
//              RGBA bytes, or a PNG where scene.format is "png"]
//   close      {}                                             -> {} and the process ends
// A part named by "key" keeps its topology for the next job naming it (the last KEPT parts), as an engine pool
// process does; an .xbf read stays open for an export of the same file as it stood (the last DOCUMENTS).
import { realpathSync, readFileSync, statSync } from "node:fs";
import { basename, extname } from "node:path";

import { DEFAULT_WASM, EXPORTS, loadCore } from "./viewcore.mjs";

const MAX_FRAME = 2 ** 31; // more than the module's memory could take in
const KEPT = 32;
const DOCUMENTS = 2;
const KINDS = { face: 0, edge: 1, vertex: 2 };

const core = await loadCore(process.argv[2] || DEFAULT_WASM);
const parts = new Map(); // key -> Doc of one part, the least recently used first
const documents = new Map(); // "realpath\0mtime_ns\0size" -> { doc, path, version }

/** The part of `key` and these bytes, kept (or opened for this job alone where no key names it). */
function part(key, bytes) {
  if (key === undefined || key === null) return { doc: core.openShape(bytes), kept: false };
  let doc = parts.get(key);
  if (doc) parts.delete(key); else doc = core.openShape(bytes);
  parts.set(key, doc);
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
    if (kept) { parts.delete(key); doc.close(); }
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
const ordinals = (value, what) => {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || !value.every(Number.isInteger)) throw new Error(`${what} is a list of ordinals`);
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
          if (!Number.isInteger(args[0])) throw new Error(`${header.method} takes an ordinal`);
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
    const started = performance.now();
    const picture = core.render(scene, payloads);
    const seconds = (performance.now() - started) / 1000;
    return { header: { width: scene.width, height: scene.height, format: scene.format ?? "rgba", seconds }, payloads: [picture] };
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
    return !found.last;
  } catch (error) {
    await send(frame({ id, ok: false, job, error: String(error?.message || error) }));
    return true;
  }
}

// The input read frame by frame: what has come and is not yet a whole frame is held; an oversized frame is let by.
let held = Buffer.alloc(0);
let skipping = 0n;
let open = true;
for await (let chunk of process.stdin) {
  if (skipping > 0n) {
    const passed = BigInt(chunk.length) < skipping ? BigInt(chunk.length) : skipping;
    skipping -= passed;
    chunk = chunk.subarray(Number(passed));
    if (skipping > 0n) continue;
    await send(frame({ id: null, ok: false, job: null, error: `a frame longer than ${MAX_FRAME} bytes was passed over` }));
  }
  held = held.length ? Buffer.concat([held, chunk]) : chunk;
  while (open && held.length >= 8) {
    const length = held.readBigUInt64BE(0);
    if (length > BigInt(MAX_FRAME)) {
      const here = BigInt(held.length - 8);
      if (here >= length) { held = held.subarray(8 + Number(length)); await send(frame({ id: null, ok: false, job: null, error: `a frame longer than ${MAX_FRAME} bytes was passed over` })); continue; }
      skipping = length - here;
      held = Buffer.alloc(0);
      break;
    }
    const whole = 8 + Number(length);
    if (held.length < whole) break;
    const body = held.subarray(8, whole);
    held = held.subarray(whole);
    open = await answer(body);
  }
  if (!open) break;
}
process.exit(0);

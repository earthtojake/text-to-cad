// An `.xbf` read in the page by the view core (a WebAssembly module, OCCT inside, running in Workers), as the
// viewer's CAD service reads an engine document (prototype). The engine's document routes a page reads -- the
// structure, a part's buffer, an element's facts, a part's groups, its table, its measures, the look -- are
// answered by a fetch of this module's own over the core's answers, so the viewer's loading code
// (`lib/xbf/xbfDocument.js`) reads the document unchanged, as `bundle.js` answers it from a view bundle's files.
//
// The core answers what the engine does for what it holds (`vc_structure`'s prototypes and instances, `vc_mesh`'s
// XBM2 buffer, `vc_fact`, `vc_groups`, `vc_elements`, `vc_measure`): a part is named to it by its prototype's
// index, a route names it by its geometry key, and the structure maps one to the other. What the engine's answers
// hold beyond what the core gives is made here, each such field listed in `VIEW_CORE_SYNTHESIZED`.
//
// The core runs in `workers` Workers (the host's `worker.js` protocol), each holding the document: the module is
// compiled once, in the page, and handed to each. A part's mesh goes to the least busy worker; everything else
// to the first. A read of anything else -- another document (a preview of a model's parameters), a route this
// does not answer -- goes to `fallback` (the engine's fetch) where there is one, counted (`stats.passthrough`).

// The engine's tessellation (`cad/engine/mesh_format.py`'s TESSELLATION): what its structure names and every part
// URL carries. The core meshes by the same rule (`viewcore.h`'s vc_mesh).
export const VIEW_CORE_TESSELLATION = '0.25-28.5';

/**
 * What an answer of this module holds that the core does not give (yet), as the engine's has it: each made here.
 * The core's own answers are passed on as they are.
 */
export const VIEW_CORE_SYNTHESIZED = Object.freeze([
  'structure.path: the document\'s id (a model\'s, as a view bundle writes it) or the path the caller gives',
  'structure.version: the version the caller gives (the envelope\'s), else a digest of the .xbf bytes',
  'structure.id: the document id the caller gives',
  'structure.parameters[].writable / reason / source: false, "no_worker", null (only the live worker that built the '
    + 'model knows a value\'s bytes in its script)',
  'structure: no exportRevision (the engine\'s check that an export reads what the page shows)',
  'structure.prototypes[].unmeshed / unmeshedCheck: not given (the part buffers carry their unmeshed faces)',
  'faces/<n>.meshed: from the part\'s own buffer, once this page meshed it (else null)',
  'faces|edges|vertices/<n>.made_by: null (provenance is the live worker\'s that built the model)',
  '/api/v1/look and /api/v1/look/environment: static copies of the engine\'s (or the fallback\'s answer)',
]);

import { readXbmPart, xbmUnmeshedFaces } from '../lib/xbf/xbm.js';

const ELEMENT_KIND = Object.freeze({ faces: 'face', edges: 'edge', vertices: 'vertex' });
const DOC_ROUTE = /^(.*)\/api\/v1\/documents\/([a-z0-9]+)\/([^/?#]+)(?:\/(.*))?$/;
function abortError() {
  return new DOMException('The operation was aborted.', 'AbortError');
}

const now = () => (typeof performance === 'undefined' ? Date.now() : performance.now());

/**
 * The engine's structure from the core's (`vc_structure`: the document's own, every field the engine's but where it
 * lives) and what the caller knows of the document.
 * @param {object} core
 * @param {{ id?: string, path?: string, version?: string }} document
 */
export function viewCoreStructure(core, { id = '', path = '', version = '' } = {}) {
  const found = { ...core, path: path || id, version };
  if (id) found.id = id;
  if (Array.isArray(core.parameters)) {
    found.parameters = core.parameters.map(row => ({ ...row, writable: false, reason: 'no_worker', source: null }));
  }
  return found;
}

/** A digest of `bytes` as hex (its first 16 characters: a version where the caller gives none). */
async function digestOf(bytes) {
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return [...hash.slice(0, 8)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

/** The faces a part's XBM2 buffer says its mesher left without triangles (its face rows with no triangles). */
function unmeshedOf(buffer) {
  try { return new Set(xbmUnmeshedFaces(readXbmPart(buffer.slice().buffer))); } catch { return null; }
}

/**
 * A connection to the core in `count` Workers: each started from `workerUrl` (the host's `worker.js`), handed the
 * compiled module, and given its own copy of the document. Answers `{ call(op, args, { worker, transfer }), ready,
 * workers, dispose }`.
 */
export function connectViewCoreWorkers({ workerUrl, wasmUrl, count = 1, bytes, stem = '', Worker: WorkerImpl = globalThis.Worker }) {
  if (typeof WorkerImpl !== 'function') throw new Error('The view core runs in a Worker, which this page has none of.');
  const n = Math.max(1, Math.min(16, Math.floor(Number(count) || 1)));
  const workers = [];
  let nextId = 1;
  const pending = new Map();
  for (let at = 0; at < n; at += 1) {
    const worker = new WorkerImpl(workerUrl, { type: 'module' });
    const state = { worker, busy: 0, at, doc: 0, initMs: 0, openMs: 0, phase: 'created' };
    // The worker says when its handler is set: nothing is sent to it before (a module worker loading its imports).
    state.loaded = new Promise(resolve => { state.onLoaded = resolve; });
    worker.onmessage = (event) => {
      if (event.data?.ready === true) { state.phase = 'loaded'; state.onLoaded(); return; }
      const waiting = pending.get(event.data?.id);
      if (!waiting) return;
      pending.delete(event.data.id);
      state.busy -= 1;
      if (event.data.ok) waiting.resolve(event.data); else waiting.reject(new Error(`view core: ${event.data.error}`));
    };
    worker.onerror = (event) => {
      console.error(`view core worker ${at}: ${event.message || 'failed'}`);
      for (const [id, waiting] of pending) if (waiting.state === state) { pending.delete(id); waiting.reject(new Error(`view core worker: ${event.message || 'failed'}`)); }
    };
    workers.push(state);
  }
  const send = (state, message, transfer = []) => new Promise((resolve, reject) => {
    const id = nextId++;
    state.busy += 1;
    pending.set(id, { resolve, reject, state });
    state.loaded.then(() => state.worker.postMessage({ id, ...message }, transfer));
  });
  const started = now();
  // The module compiled once (streamed where the server says application/wasm), and each worker handed it.
  const compiled = (async () => {
    const response = await fetch(wasmUrl);
    if (!response.ok) throw new Error(`view core: ${wasmUrl} answered ${response.status}`);
    const streaming = (response.headers.get('content-type') || '').startsWith('application/wasm') && WebAssembly.compileStreaming;
    return streaming ? WebAssembly.compileStreaming(response) : WebAssembly.compile(await response.arrayBuffer());
  })();
  const source = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  // Each worker its own copy, made now (a copy made once another has taken the bytes would be empty); the last
  // takes the bytes themselves.
  const copies = workers.map((_, at) => (at === workers.length - 1 ? source : source.slice()));
  const opened = workers.map(async (state, at) => {
    const module = await compiled;
    state.phase = 'init';
    const init = await send(state, { op: 'init', module });
    state.phase = 'open';
    state.initMs = now() - started;
    state.init = init.result;
    const copy = copies[at];
    const open = await send(state, { op: 'open', bytes: copy, stem }, [copy.buffer]);
    state.doc = open.result.doc;
    state.phase = 'ready';
    state.openMs = now() - started;
    state.openCoreMs = open.ms;
    return state;
  });
  const first = opened[0];
  const all = Promise.all(opened);
  all.catch(() => {});
  return {
    workers,
    ready: all,
    compileMs: compiled.then(() => now() - started),
    /** One call: on the first worker, or (`spread`) the least busy of those ready. */
    async call(op, args = {}, { spread = false } = {}) {
      let state = await first;
      if (spread) {
        const ready = workers.filter(candidate => candidate.doc);
        state = ready.reduce((best, candidate) => (candidate.busy < best.busy ? candidate : best), ready[0] || state);
      }
      const reply = await send(state, { op, doc: state.doc, ...args });
      return { result: reply.result, ms: reply.ms, worker: state.at };
    },
    dispose() {
      for (const { worker } of workers) worker.terminate();
      for (const waiting of pending.values()) waiting.reject(abortError());
      pending.clear();
    },
  };
}

/**
 * The engine's document routes over the core: a fetch that answers them at the document's API URL.
 *
 * @param {object} options
 * @param {{ call: Function, ready?: Promise<unknown>, dispose?: Function }} options.core  `connectViewCoreWorkers`' answer.
 * @param {string} options.url  The document's API URL (`…/api/v1/documents/xbf/<id>`): what the page reads it at.
 * @param {ArrayBuffer | Uint8Array} [options.bytes]  The `.xbf`'s bytes, for a version where none is given.
 * @param {{ id?: string, name?: string, path?: string, version?: string }} [options.document]
 * @param {{ json?: string, environment?: string }} [options.look]  Where the look's two answers are, as static files.
 * @param {typeof fetch} [options.fallback]  What answers every other read (the engine's fetch), if anything.
 * @param {typeof fetch} [options.fetch]  What reads the look's static files.
 */
export function createViewCoreFetch({ core, url, bytes, document = {}, look = {}, fallback = null, fetch: fetchStatic = globalThis.fetch }) {
  const match = DOC_ROUTE.exec(String(url).split(/[?#]/)[0]);
  if (!match) throw new Error(`a view core document is read at its API URL (…/api/v1/documents/<kind>/<id>), not ${JSON.stringify(url)}`);
  const base = new URL(match[1] || '/', globalThis.location?.href || 'http://view-core.invalid');
  const docId = decodeURIComponent(match[3]);
  const docPath = new URL(String(url), globalThis.location?.href || 'http://view-core.invalid').pathname.replace(/\/$/, '');
  const stats = { started: now(), structureAt: null, firstPartAt: null, partsAt: null, parts: 0, partsTotal: null,
    meshCoreMs: 0, calls: {}, passthrough: [], workers: [] };
  const record = (op, ms) => { const held = stats.calls[op] || (stats.calls[op] = { n: 0, coreMs: 0 }); held.n += 1; held.coreMs += ms; };
  let disposed = false;

  // The structure, read once: the engine's, made from the core's.
  let structureHeld = null;
  const structure = () => structureHeld || (structureHeld = (async () => {
    const reply = await core.call('structure');
    record('structure', reply.ms);
    const version = document.version || (bytes ? await digestOf(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)) : '');
    const found = viewCoreStructure(reply.result, { ...document, id: document.id || docId, version });
    stats.partsTotal = new Set(found.prototypes.map(prototype => String(prototype.key))).size;
    return found;
  })());
  /** The prototype index the core knows a part by, from its geometry key. */
  const indexOf = async (key) => {
    const found = (await structure()).prototypes.find(prototype => String(prototype.key) === key);
    if (!found) throw Object.assign(new Error(`no part ${key}`), { status: 404 });
    return found.index;
  };
  const meshes = new Map();
  const unmeshed = new Map();
  const mesh = (key) => {
    let held = meshes.get(key);
    if (!held) {
      held = (async () => {
        const reply = await core.call('mesh', { part: await indexOf(key) }, { spread: true });
        record('mesh', reply.ms);
        stats.meshCoreMs += reply.ms;
        stats.parts += 1;
        const at = now();
        if (stats.firstPartAt === null) stats.firstPartAt = at;
        if (stats.partsTotal !== null && stats.parts >= stats.partsTotal) stats.partsAt = at;
        unmeshed.set(key, unmeshedOf(reply.result));
        return reply.result;
      })();
      meshes.set(key, held);
      held.catch(() => { if (meshes.get(key) === held) meshes.delete(key); });
    }
    // Each answer its own copy: a reader may hand its buffer on (to a worker) and detach it.
    return held.then(buffer => buffer.slice());
  };
  const jsonCall = async (op, args) => {
    const reply = await core.call(op, args);
    record(op, reply.ms);
    return reply.result;
  };

  const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
  const notFound = (error) => json({ error }, 404);

  async function answer(pathname, searchParams, init) {
    if (pathname === `${base.pathname.replace(/\/$/, '')}/api/v1/look` && look.json) return fetchStatic(look.json, { signal: init.signal });
    if (pathname === `${base.pathname.replace(/\/$/, '')}/api/v1/look/environment` && look.environment) return fetchStatic(look.environment, { signal: init.signal });
    if (pathname !== docPath && !pathname.startsWith(`${docPath}/`)) return null;
    const route = pathname.slice(docPath.length + 1).split('/').filter(Boolean).map(decodeURIComponent);
    const method = init.method || 'GET';
    const [head, key, element, ordinal] = route;
    if (method !== 'GET') return null;
    if (route.length === 1 && head === 'structure') {
      const found = await structure();
      if (stats.structureAt === null) stats.structureAt = now();
      return json(found);
    }
    if (route.length === 1 && head === 'measure') {
      const found = await structure();
      const keys = [...new Map(found.prototypes.map(prototype => [String(prototype.key), prototype.index]))];
      const measures = await Promise.all(keys.map(([, part]) => jsonCall('measure', { part })));
      return json(Object.fromEntries(keys.map(([name], at) => [name, measures[at]])));
    }
    if (route.length === 1 && head === 'kinematics') {
      const found = (await structure()).kinematics;
      return found ? json(found) : json({ error: 'the document has no joints', hint: "a model's joints are its assembly's mates" }, 404);
    }
    if (head !== 'parts' || !key) return null;
    if (route.length === 2) {
      const tessellation = searchParams.get('tessellation');
      const meshedAt = (await structure()).tessellation || VIEW_CORE_TESSELLATION;
      if (tessellation && tessellation !== meshedAt) return notFound(`this core meshes at ${meshedAt}, not ${tessellation}`);
      return new Response(await mesh(key), { headers: { 'content-type': 'application/octet-stream' } });
    }
    if (route.length === 3 && element === 'groups') return json(await jsonCall('groups', { part: await indexOf(key) }));
    if (route.length === 3 && element === 'elements') return json(await jsonCall('elements', { part: await indexOf(key) }));
    if (route.length === 3 && element === 'volume') return json(await jsonCall('measure', { part: await indexOf(key) }));
    if (route.length === 4 && ELEMENT_KIND[element] && /^\d+$/.test(ordinal)) {
      const kind = ELEMENT_KIND[element];
      let found;
      try {
        found = await jsonCall('fact', { part: await indexOf(key), kind, ordinal: Number(ordinal) });
      } catch (error) {
        return notFound(String(error?.message || error));
      }
      if (kind === 'face') {
        const held = meshes.has(key) ? (await meshes.get(key), unmeshed.get(key)) : null;
        found = { ...found, meshed: held ? !held.has(Number(ordinal)) : null };
      }
      return json({ ...found, made_by: null });
    }
    return null;
  }

  async function viewCoreFetch(input, init = {}) {
    const signal = init.signal || (typeof Request !== 'undefined' && input instanceof Request ? input.signal : undefined);
    if (signal?.aborted || disposed) throw abortError();
    const text = typeof input === 'string' || input instanceof URL ? String(input) : input.url;
    const target = new URL(text, globalThis.location?.href || 'http://view-core.invalid');
    let found = null;
    if (target.origin === base.origin) {
      try {
        found = await answer(target.pathname, target.searchParams, { ...init, signal });
      } catch (error) {
        if (error?.name === 'AbortError') throw error;
        if (error?.status === 404) return notFound(error.message);
        return json({ error: String(error?.message || error) }, 500);
      }
    }
    if (signal?.aborted) throw abortError();
    if (found) return found;
    stats.passthrough.push(`${init.method || 'GET'} ${target.pathname}`);
    if (fallback) return fallback(input, init);
    return notFound(`the view core answers no ${target.pathname}`);
  }
  viewCoreFetch.stats = stats;
  viewCoreFetch.dispose = () => { disposed = true; core.dispose?.(); };
  return viewCoreFetch;
}

/** The formats the core writes a document as (`vc_step`, `vc_stl`, `vc_3mf`, `vc_glb`), by the viewer's names. */
export const VIEW_CORE_EXPORTS = Object.freeze(['step', 'stl', 'threemf', 'glb']);
const EXPORT_SUFFIX = Object.freeze({ step: '.step', stl: '.stl', threemf: '.3mf', glb: '.glb', xbf: '.xbf', original: '.xbf' });
const EXPORT_TYPE = Object.freeze({ step: 'model/step', stl: 'model/stl', threemf: 'model/3mf', glb: 'model/gltf-binary',
  xbf: 'application/octet-stream', original: 'application/octet-stream' });

/**
 * A document's exports made by the core in the page (the `ExportService` the viewer's Export asks), as the engine's
 * export route makes them: a STEP, an STL, a 3MF or a GLB of the whole document written by the core, and the `.xbf`
 * itself (`xbf`, `original`). Each job is ready when it is made: its file a blob of this page, named `export<suffix>`
 * as the engine names a job's file. Any other format is `fallback`'s (the engine's service), where there is one.
 * @param {{ call: Function }} options.core  `connectViewCoreWorkers`' answer.
 * @param {Uint8Array} [options.bytes]  The `.xbf`'s bytes: what `xbf` and `original` download.
 * @param {import('./types.js').ExportService | null} [options.fallback]
 */
export function createViewCoreExports({ core, bytes = null, fallback = null }) {
  const files = new Map();
  let next = 1;
  const stamp = () => Date.now();
  return {
    // The page's own: no server restarts under it.
    epoch: async (signal) => (fallback ? fallback.epoch(signal) : 'view-core'),
    async create(request, signal) {
      const format = request?.format;
      const own = VIEW_CORE_EXPORTS.includes(format) || ((format === 'xbf' || format === 'original') && bytes);
      if (!own) {
        if (fallback) return fallback.create(request, signal);
        throw Object.assign(new Error(`the view core writes no ${format}`), { status: 400 });
      }
      const made = VIEW_CORE_EXPORTS.includes(format)
        ? (await core.call('exportBytes', { format })).result
        : bytes;
      if (signal?.aborted) throw signal.reason;
      const id = `core-${next++}`;
      const url = URL.createObjectURL(new Blob([made], { type: EXPORT_TYPE[format] }));
      const at = stamp();
      const job = { id, requestId: request.requestId, epoch: request.epoch, filename: `export${EXPORT_SUFFIX[format]}`,
        state: 'ready', stage: 'ready', sequence: 1, createdAt: at, finishedAt: at, expiresAt: 0, bytes: made.byteLength };
      files.set(id, { job, url });
      return job;
    },
    async status(id, sequence, signal) {
      const held = files.get(id);
      if (held) return held.job;
      if (fallback) return fallback.status(id, sequence, signal);
      throw Object.assign(new Error(`no export ${id}`), { status: 404 });
    },
    fileUrl: (id) => files.get(id)?.url ?? fallback?.fileUrl(id) ?? '',
    /** Each export's file let go. */
    dispose() { for (const { url } of files.values()) URL.revokeObjectURL(url); files.clear(); },
  };
}

/**
 * Open an `.xbf`'s bytes in the core (`workers` Workers) and answer where the page reads it, as a CAD client's
 * `engineDocument` does: `{ doc, kind, url, fetch, final: true }`, with its `exports` (`createViewCoreExports`). The
 * document as it stands: no engine is waited on for a next version of it.
 */
export function openViewCoreDocument({ bytes, url, workerUrl, wasmUrl, workers = 1, document = {}, look = {}, fallback = null,
  exports: otherExports = null, Worker: WorkerImpl }) {
  const source = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  // The version is worked out before the bytes go to the workers (the last one takes them).
  const held = source.slice();
  // The name the document goes by where its file names none (the engine's: the file's stem).
  const core = connectViewCoreWorkers({ workerUrl, wasmUrl, count: workers, bytes: source, stem: document.name || '', Worker: WorkerImpl });
  const fetch = createViewCoreFetch({ core, url, bytes: held, document, look, fallback });
  core.ready.then(states => {
    fetch.stats.workers = states.map(state => ({ initMs: Math.round(state.initMs), openMs: Math.round(state.openMs),
      openCoreMs: Math.round(state.openCoreMs || 0), occt: state.init?.occt, memoryBytes: state.init?.memoryBytes }));
  }, () => {});
  core.compileMs.then(ms => { fetch.stats.compileMs = Math.round(ms); }, () => {});
  // Where each worker is (created, loaded, init, open, ready): what a page that waits says it waits on.
  Object.defineProperty(fetch.stats, 'phases', { enumerable: true, get: () => core.workers.map(state => state.phase) });
  // Its exports: what the core writes made here, any other the given service's (`otherExports`, the engine's).
  const exports = createViewCoreExports({ core, bytes: held, fallback: otherExports });
  return { doc: document.id || '', kind: 'xbf', url, fetch, final: true, core, exports };
}

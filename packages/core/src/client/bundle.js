// A view bundle as the viewer's CAD service: the answers a page reads of one document, written ahead
// of time as files in one folder (a share's view, which `cad share` has the server write; the engine's
// documentation, "View bundle", gives the layout and the manifest), answered here with no engine behind the page.
//
// The bundle is read through one small abstraction, its source: the bytes of a path of the bundle
// (`read(path)`). A share's is `share.js`'s; the files held in the page, by path (`viewBundleMemorySource`), are
// another, for a bundle that reached it some other way. Nothing here assumes one request per file, or any request
// at all. A source with something to let go of (`dispose`) is let go of with the service.
//
// The service answers what the viewer's renderers ask of a CAD client, from the bundle alone:
//
// - the catalog, which is the bundle's one document: a model by its id, a file by its own name
//   (`/<name>`: the bundle holds the file's name and no path of the computer it was made on);
// - an engine document's reads (a model's, an `.xbf`'s, a STEP's: `engineDocument`), at the API URL a
//   page reads them at, answered by a fetch of the bundle's own that maps each route to its file. The
//   structure is the engine's answer, put back together: the bundle keeps the mechanism in
//   `kinematics.json` alone, and each prototype's element names in a file named by its content
//   (`names/<sha256>.json`, shared by the prototypes whose names are the same), so a colour edit changes
//   a small `structure.json` and a part's names travel only when they change. A part's buffer is
//   `parts/<key>/<tessellation>.xbm`; one element's facts, and a part's groups, come out of the part's
//   one table (`parts/<key>/elements.json`), read once, so nothing is asked per element. The document is
//   `final`: there is no engine to wait on for a next version;
// - a drawing's (`drawing`), a robot's (`robot`) and a mesh file's bytes, through the service's
//   resources, which read bundle paths (a mesh file's `source.<ext>`, a robot's `parts/<digest>.glb`
//   and `meshes/<sha256>.<format>`, as its structure names them).
//
// Whatever needs an engine is no method here, so the viewer leaves out what calls it: saving or
// previewing a model's parameters, exports, a version to wait on, the library, the projects, the
// person's settings and everything under `/api/v1/local`. A path the manifest does not list is
// answered 404, and a file whose size is not what the manifest says fails loudly.

import { retainGlbMeshWorker } from '../lib/render/glbMeshWorkerClient.js';
import { retainStlMeshWorker } from '../lib/render/stlMeshWorkerClient.js';
import { scopeCadResources } from './resources.js';

/** The one layout this reader reads: a manifest of another `format` is refused whole. */
export const VIEW_BUNDLE_FORMAT = 'view-bundle/1';
export const VIEW_BUNDLE_MANIFEST = 'manifest.json';
/**
 * The origin an engine document of a bundle is read under (its API URL's): a name no network has, so
 * nothing outside the bundle's own fetch can answer it.
 */
export const VIEW_BUNDLE_ORIGIN = 'http://view-bundle.invalid';

// The documents a bundle holds that a page reads as the engine's own (structure, parts, tables, look).
const ENGINE_KINDS = new Set(['xbf', 'step']);
// Every kind a manifest may name (the API's), and the renderer's: KiCad's have no bundle yet.
const KINDS = new Set([...ENGINE_KINDS, 'stl', 'glb', '3mf', 'dxf', 'urdf', 'srdf']);
// A part's elements, as the API's routes name them, and as a table keys them.
const ELEMENT_ROUTES = new Set(['faces', 'edges', 'vertices']);
// What a prototype's names file holds, in the order the engine's structure gives them.
const ELEMENT_NAMES = ['faceNames', 'edgeNames', 'vertexNames'];
const decoder = new TextDecoder();

function abortError() {
  return new DOMException('The operation was aborted.', 'AbortError');
}

/** A missing file of a bundle, as an HTTP answer would say it: its `status` is 404. */
function missingFile(path, detail = '') {
  return Object.assign(new Error(`The view bundle holds no ${path}${detail}.`), { status: 404, code: 'view-bundle-missing' });
}

/**
 * A name (a part's key, a tessellation) as one segment of a bundle's path, as the layout spells it: ASCII
 * letters, digits, `.`, `_` and `-` as they are, every other byte `~` and its two hex digits (a STEP part's
 * key `step-0a1b-0:1:2` is `step-0a1b-0~3A1~3A2`).
 * @param {string} name
 */
export function viewBundleSegment(name) {
  let spelled = '';
  for (const char of String(name)) {
    if (/^[A-Za-z0-9._-]$/.test(char)) spelled += char;
    else for (const byte of new TextEncoder().encode(char)) spelled += `~${byte.toString(16).toUpperCase().padStart(2, '0')}`;
  }
  if (spelled === '' || spelled === '.' || spelled === '..') throw new Error(`${JSON.stringify(name)} names no file of a view bundle`);
  return spelled;
}

/**
 * A bundle held in the page: its files by their paths in the bundle (`manifest.json`, `structure.json`,
 * `parts/<key>/<tessellation>.xbm`…), each an ArrayBuffer, a typed array or a Blob. Every read is a copy of
 * its own, so a reader that hands the bytes on (to a worker, which may detach them) takes nothing from the
 * next.
 * @param {Map<string, ArrayBuffer | ArrayBufferView | Blob> | Record<string, ArrayBuffer | ArrayBufferView | Blob>} files
 * @returns {import('./types.js').ViewBundleSource}
 */
export function viewBundleMemorySource(files) {
  const held = new Map(files instanceof Map ? files : Object.entries(files || {}));
  return {
    async read(path, { signal } = {}) {
      if (signal?.aborted) throw abortError();
      const value = held.get(path);
      if (value === undefined) throw missingFile(path);
      if (typeof Blob !== 'undefined' && value instanceof Blob) return value.arrayBuffer();
      if (value instanceof ArrayBuffer) return value.slice(0);
      if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength).slice().buffer;
      throw new TypeError(`The view bundle's ${path} is no bytes.`);
    },
  };
}

/**
 * The manifest a bundle's reader believes: its `format` this reader's, its document's `id`, `kind`, `name`
 * and `version`, and every other file by its path, each with its size. Anything else is refused, saying what.
 * @returns {import('./types.js').ViewBundleManifest}
 */
export function readViewBundleManifest(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('This is no view bundle: its manifest.json is not an object.');
  if (value.format !== VIEW_BUNDLE_FORMAT) {
    throw new Error(`This view bundle's format is ${JSON.stringify(value.format ?? null)}; this viewer reads ${VIEW_BUNDLE_FORMAT}.`);
  }
  const document = value.document;
  const named = key => typeof document?.[key] === 'string' && document[key] !== '';
  if (!named('id') || !named('kind') || !named('name') || !named('version')) {
    throw new Error("This view bundle's manifest names no document (its id, kind, name and version).");
  }
  if (!KINDS.has(document.kind)) throw new Error(`This viewer shows no view bundle of a ${document.kind}.`);
  const files = value.files;
  if (!files || typeof files !== 'object' || Array.isArray(files)
    || !Object.values(files).every(entry => entry && Number.isSafeInteger(entry.bytes) && entry.bytes >= 0)) {
    throw new Error("This view bundle's manifest lists no files, each with its size.");
  }
  return value;
}

/**
 * Open the bundle `source` holds: its manifest read and checked, then the service that answers the viewer
 * from it (`createViewBundleClient`).
 * @param {import('./types.js').ViewBundleSource} source
 * @param {{ signal?: AbortSignal }} [options]
 */
export async function openViewBundle(source, { signal } = {}) {
  let text;
  try {
    text = decoder.decode(await source.read(VIEW_BUNDLE_MANIFEST, { signal }));
  } catch (error) {
    if (error?.status === 404) throw Object.assign(new Error('This is no view bundle: it has no manifest.json.'), { status: 404, cause: error });
    throw error;
  }
  let parsed;
  try { parsed = JSON.parse(text); } catch { throw new Error('This is no view bundle: its manifest.json is not JSON.'); }
  return createViewBundleClient(source, readViewBundleManifest(parsed));
}

/** The catalog's row of a bundle's document, as an envelope's `entry` gives it to a page. */
function entryOf(manifest) {
  const { id, kind, name, version } = manifest.document;
  // A model has no file: it is named by its id, as a page names it. A file is named by its own name, which
  // is what the bundle keeps of where it was.
  if (kind === 'xbf') return { id, file: id, name, sourcePath: null, kind: 'xbf', sourceFormat: 'model', url: '', hash: `model:${version}`, bytes: 0 };
  const source = Object.keys(manifest.files).find(path => /^source\.[^/]+$/.test(path));
  return { id, file: `/${name}`, name, kind, hash: version,
    ...(source ? { url: source, bytes: manifest.files[source].bytes } : {}) };
}

/**
 * The viewer's CAD service over one view bundle (`manifest`, already read: `openViewBundle` reads it). Disposing
 * it disposes `source` too, where the source has something to let go of.
 * @param {import('./types.js').ViewBundleSource} source
 * @param {import('./types.js').ViewBundleManifest} manifest
 * @returns {import('./types.js').CadViewBundleClient}
 */
export function createViewBundleClient(source, manifest) {
  const document = manifest.document;
  const entry = entryOf(manifest);
  const files = manifest.files;
  const lifetime = new AbortController();
  const sessions = new Set();
  let disposed = false;

  /** The bytes of `path`, as the manifest lists it: a path it does not list is a 404, a size it does not say a failure. */
  async function read(path, { signal } = {}) {
    if (disposed) throw abortError();
    const listed = Object.hasOwn(files, path) ? files[path] : null;
    if (!listed) throw missingFile(path);
    const combined = signal ? AbortSignal.any([signal, lifetime.signal]) : lifetime.signal;
    const bytes = await source.read(path, { signal: combined });
    if (combined.aborted) throw abortError();
    if (bytes.byteLength !== listed.bytes) {
      throw new Error(`The view bundle's ${path} is ${bytes.byteLength} bytes; its manifest says ${listed.bytes}. It may be being written: open it again.`);
    }
    return bytes;
  }
  const readJson = async (path, options) => JSON.parse(decoder.decode(await read(path, options)));
  // A part's table and the bundle's measures are read once each, however many of their answers are asked for.
  const tables = new Map();
  function once(path, signal) {
    let held = tables.get(path);
    if (!held) {
      held = readJson(path);
      tables.set(path, held);
      held.catch(() => { if (tables.get(path) === held) tables.delete(path); });
    }
    if (!signal) return held;
    // The read is shared: one asker giving up stops waiting for it, and leaves it to the others.
    return new Promise((resolve, reject) => {
      const stop = () => reject(abortError());
      if (signal.aborted) { stop(); return; }
      signal.addEventListener('abort', stop, { once: true });
      held.then(resolve, reject).finally(() => signal.removeEventListener('abort', stop));
    });
  }

  // ---- the API a page reads an engine document at, answered from the bundle ----------------------------
  const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
  const refused = (what) => json({ error: `A view bundle holds no answer to ${what}: that needs an engine.` }, 404);
  const bytesAnswer = (path, bytes) => new Response(bytes, { headers: { 'content-type': files[path]?.type || 'application/octet-stream' } });
  const fileAnswer = async (path, signal) => bytesAnswer(path, await read(path, { signal }));
  /**
   * The structure as the engine answered it. Where the bundle keeps the mechanism apart (`kinematics.json`, the
   * structure holding no `kinematics`) it is put back, and so are the element names each prototype keeps in a file
   * (`names`: each file read once, all of them at once), the file's name removed. A structure that holds both
   * itself (a bundle written before they moved) is answered as its bytes.
   */
  async function structureAnswer(signal) {
    const bytes = await read('structure.json', { signal });
    const structure = JSON.parse(decoder.decode(bytes));
    if (!structure || typeof structure !== 'object' || Array.isArray(structure)) return bytesAnswer('structure.json', bytes);
    const mechanism = !Object.hasOwn(structure, 'kinematics') && Object.hasOwn(files, 'kinematics.json');
    const prototypes = Array.isArray(structure.prototypes) ? structure.prototypes : [];
    const named = [...new Set(prototypes.filter(prototype => typeof prototype?.names === 'string').map(prototype => prototype.names))];
    if (!mechanism && !named.length) return bytesAnswer('structure.json', bytes);
    const [kinematics, ...held] = await Promise.all([mechanism ? once('kinematics.json', signal) : null,
      ...named.map(path => once(path, signal))]);
    const names = new Map(named.map((path, index) => {
      const kept = held[index];
      if (!kept || typeof kept !== 'object' || Array.isArray(kept)) throw new Error(`The view bundle's ${path} holds no element names.`);
      return [path, Object.fromEntries(ELEMENT_NAMES.filter(name => Object.hasOwn(kept, name)).map(name => [name, kept[name]]))];
    }));
    const restored = { ...structure };
    if (named.length) {
      restored.prototypes = prototypes.map(prototype => {
        if (typeof prototype?.names !== 'string') return prototype;
        const { names: path, ...rest } = prototype;
        return { ...rest, ...names.get(path) };
      });
    }
    if (mechanism) restored.kinematics = kinematics;
    return json(restored);
  }
  /** What a part's table says of one of its elements, or of its groups: its answer's body. */
  async function fromTable(key, route, ordinal, signal) {
    const table = await once(`parts/${viewBundleSegment(key)}/elements.json`, signal);
    if (route === 'groups') return table.groups;
    const fact = table?.[route]?.[String(ordinal)];
    if (!fact) throw missingFile(`parts/${viewBundleSegment(key)}/elements.json`, `'s ${route} ${ordinal}`);
    return fact;
  }

  async function answer(url, signal) {
    const { pathname, searchParams } = url;
    if (pathname === '/api/v1/look') return fileAnswer('look.json', signal);
    if (pathname === '/api/v1/look/environment') return fileAnswer('look/environment.hdr', signal);
    if (pathname === `/api/v1/documents/${encodeURIComponent(document.id)}/thumbnail`) return fileAnswer('thumbnail.png', signal);
    const at = /^\/api\/v1\/documents\/[a-z0-9]+\/([^/]+)\/(.+)$/.exec(pathname);
    if (!at || decodeURIComponent(at[1]) !== document.id) return refused(pathname);
    const route = at[2].split('/').map(segment => decodeURIComponent(segment));
    const [head, key, element, ordinal] = route;
    if (route.length === 1) {
      if (head === 'structure') return structureAnswer(signal);
      const file = { kinematics: 'kinematics.json', measure: 'measure.json', drawing: 'drawing.json' }[head];
      if (file) return fileAnswer(file, signal);
      if (head === 'source') {
        const held = Object.keys(files).find(path => /^source\.[^/]+$/.test(path));
        return held ? fileAnswer(held, signal) : refused(pathname);
      }
      return refused(pathname);
    }
    if (head !== 'parts') return refused(pathname);
    if (route.length === 2) {
      // A part's buffer, at the tessellation the structure names; a robot's primitive, by its digest.
      const tessellation = searchParams.get('tessellation');
      return fileAnswer(tessellation ? `parts/${viewBundleSegment(key)}/${viewBundleSegment(tessellation)}.xbm`
        : `parts/${viewBundleSegment(key)}.glb`, signal);
    }
    if (route.length === 3 && element === 'elements') return fileAnswer(`parts/${viewBundleSegment(key)}/elements.json`, signal);
    if (route.length === 3 && element === 'groups') return json(await fromTable(key, 'groups', null, signal));
    if (route.length === 3 && element === 'volume') {
      const measures = await once('measure.json', signal);
      return measures?.[key] ? json(measures[key]) : refused(pathname);
    }
    if (route.length === 4 && ELEMENT_ROUTES.has(element) && /^\d+$/.test(ordinal)) return json(await fromTable(key, element, ordinal, signal));
    return refused(pathname);
  }

  /** The fetch an engine document of the bundle is read with: every route of its API URL, answered here. */
  async function engineFetch(input, init = {}) {
    const signal = init.signal || (typeof Request !== 'undefined' && input instanceof Request ? input.signal : undefined);
    if (signal?.aborted) throw abortError();
    const url = new URL(typeof input === 'string' || input instanceof URL ? String(input) : input.url, VIEW_BUNDLE_ORIGIN);
    if (url.origin !== VIEW_BUNDLE_ORIGIN || (init.method && init.method !== 'GET')) return refused(`${init.method || 'GET'} ${url.href}`);
    try {
      return await answer(url, signal);
    } catch (error) {
      if (error?.name === 'AbortError') throw error;
      if (error?.status === 404) return json({ error: error.message }, 404);
      throw error;
    }
  }

  // ---- resources: what a renderer's loaders read (a mesh file, a robot's meshes) -------------------------
  /** The bundle's path a resource URL names: a path in the bundle, or one under the bundle's origin. */
  function pathOf(url) {
    const text = String(url);
    const resolved = new URL(text.startsWith(VIEW_BUNDLE_ORIGIN) ? text : `${VIEW_BUNDLE_ORIGIN}/${text.replace(/^\.?\//, '')}`);
    if (resolved.origin !== VIEW_BUNDLE_ORIGIN) throw missingFile(text);
    return decodeURIComponent(resolved.pathname.slice(1));
  }
  const provider = {
    cacheKey: url => `view-bundle:${document.id}:${document.version}:${pathOf(url)}`,
    readBytes: (url, options = {}) => read(pathOf(url), options).then(bytes => {
      if (options.maxBytes && bytes.byteLength > options.maxBytes) throw new Error('CAD resource exceeds its byte limit');
      return bytes;
    }),
    readJson: (url, options) => readJson(pathOf(url), options),
    async byteLength(url) { const listed = files[pathOf(url)]; return listed ? listed.bytes : null; },
    // A file a mesh names beside it (a GLB's external buffer) is the bundle's own, never another host's.
    resolveDependency(from, reference) {
      const base = new URL(`${VIEW_BUNDLE_ORIGIN}/${pathOf(from)}`);
      const resolved = new URL(String(reference), base);
      if (resolved.origin !== VIEW_BUNDLE_ORIGIN) throw new Error(`a model may load only a file beside it, not ${reference}`);
      return decodeURIComponent(resolved.pathname.slice(1));
    },
    // A worker is handed the bytes, its own copy: the bundle is no URL a worker could fetch.
    async workerTicket(url, options = {}) { return { kind: 'bytes', bytes: await provider.readBytes(url, options) }; },
  };
  const resources = scopeCadResources(provider, lifetime.signal);

  const catalog = Object.freeze({ entries: [entry], revision: document.version });
  const snapshot = Object.freeze({ entries: Object.freeze([entry]), revision: 1, hydrated: true, refreshing: false, error: '',
    engineGone: false, engineRefused: false, catalogRevision: document.version });
  const names = path => path === entry.file || path === document.id;
  const notHere = path => Object.assign(new Error(`File does not exist: ${path}`), { code: 'cad-file-missing' });
  const own = async (file, what) => {
    if (!names(file)) throw notHere(file);
    if (disposed) throw abortError();
    return what;
  };

  return {
    manifest,
    file: entry.file,
    resources,
    getSnapshot: () => snapshot,
    // The bundle is one document as it stood: nothing it holds changes, so there is nothing to hear.
    subscribe: () => () => {},
    refresh: async () => catalog,
    async resolveEntry(path) { return own(path, entry); },
    entryOf: path => (names(path) ? entry : null),
    async engineDocument(file) {
      await own(file, null);
      if (!ENGINE_KINDS.has(document.kind)) throw new Error(`A view bundle of a ${document.kind} is no engine document.`);
      // Read as the document written down, which is what an .xbf is: whatever kind the manifest names, the
      // page reads it as a file's document (its parameters are the values it was made with, to read).
      return { doc: document.id, kind: document.kind, url: `${VIEW_BUNDLE_ORIGIN}/api/v1/documents/xbf/${encodeURIComponent(document.id)}`,
        fetch: engineFetch, final: true };
    },
    async drawing(file, { signal } = {}) {
      await own(file, null);
      return readJson('drawing.json', { signal });
    },
    async robot(file, { signal } = {}) {
      await own(file, null);
      return readJson('structure.json', { signal });
    },
    createRenderSession() {
      if (disposed) throw new Error('This view bundle has been closed.');
      const controller = new AbortController();
      const releases = [retainGlbMeshWorker(), retainStlMeshWorker()];
      let done = false;
      const session = { resources, signal: controller.signal, dispose() {
        if (done) return;
        done = true;
        controller.abort();
        for (const release of releases) release();
        sessions.delete(session);
      } };
      sessions.add(session);
      return session;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      lifetime.abort();
      for (const session of [...sessions]) session.dispose();
      tables.clear();
      source.dispose?.();
    },
  };
}

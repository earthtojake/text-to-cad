/**
 * The viewer API of one build, read-only, over its export: what `cadgen.viewer` answered when
 * the build was made (`export.json`, `exportIndex.ts`), and nothing else. Mounted by the server
 * at `/b/:build/__cad/*` and `/b/:build/__tess_cache/*`; the viewer page builds its client with
 * `createCadClient({ origin: '<page origin>/b/<build>' })`, so every request the shared client
 * makes of a local `cadgen viewer` lands here with the same path, query and body.
 *
 * Every answer has the shape the local viewer gives, so the client cannot tell the two apart:
 * recorded JSON as recorded; a file the export lacks answered as the viewer answers a missing
 * file; bytes as a redirect to the object store, where the browser fetches them; the shared
 * tessellation cache as always empty and accepting nothing; and the routes a hosted build has
 * no business with (Reveal, the file chooser, the clipboard, shutdown, live surfaces) absent.
 * Nothing here runs cadgen, touches a sandbox or wakes compute: viewing is reading.
 */

import { CAD_EXTENSIONS, extensionOf, listFolder, normalizeVirtualPath, recordedJson, recordedObject, searchFolder, type ExportIndex, type ExportObject } from './exportIndex.ts';

export interface ViewerApiRequest {
  method: string;
  /** The request path, with or without the `/b/<build>` prefix it was mounted under. */
  path: string;
  query: URLSearchParams;
  body?: Uint8Array;
  /** The request headers (lower-cased names), for the guard the viewer's POST routes keep. */
  headers?: Record<string, string | undefined>;
}
export interface ViewerApiContext {
  /** Where the browser fetches an object by its sha256: a URL on this server or a CORS-enabled store. */
  objectUrl(sha256: string): string;
  /** Keep a copied prompt's sketch (a PNG) and answer the https URL that names it. */
  saveSketch(png: Uint8Array, name: string): Promise<string>;
}
export interface ViewerApiResponse {
  status: number;
  headers?: Record<string, string>;
  json?: unknown;
  body?: Uint8Array;
  /** A redirect's target (`status` 302); `headers` carries its cache policy. */
  redirect?: string;
}

/** The guard the viewer's POST routes keep: a custom header no cross-site form can send. */
export const POST_GUARD_HEADER = 'x-cadgen-viewer';
export const SKETCH_MAX_BYTES = 20 * 1024 * 1024;
const SMALL_BODY_MAX_BYTES = 4096;
const TESS_METADATA_MAX_BYTES = 256 * 1024;
const TESS_BATCH_MAX_NAMES = 256;
const TESS_CACHE_NAME = /^[A-Za-z0-9][A-Za-z0-9.+_-]*\.tess$/;
const TESS_CACHE_BATCH_MAGIC = 0x42534554; // "TESB", little-endian
const TESS_CACHE_BATCH_VERSION = 1;
const SHA256 = /^[0-9a-f]{64}$/;
const MAX_SAFE_BYTES = /^[0-9]{1,16}$/;
const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const IMMUTABLE = 'public, max-age=31536000, immutable';
const STEP = /\.(?:step|stp)$/i;

const json = (status: number, value: unknown): ViewerApiResponse => ({ status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }, json: value });
const empty = (status: number, headers: Record<string, string> = {}): ViewerApiResponse => ({ status, headers: { ...headers, 'content-length': '0' } });
const notFound = () => json(404, { error: 'Not found' });
const notFoundPost = () => json(404, { ok: false, error: 'Not found' });
const badRequest = (error: string) => json(400, { error });
const NOT_ABSOLUTE = 'name the file by its absolute path';

/** The route path, with the `/b/<build>` mount prefix removed when the server passed it along. */
export function viewerApiPath(path: string): string {
  const text = String(path || '');
  const match = /^\/b\/[^/]+(\/__(?:cad|tess_cache)\/.*)$/.exec(text);
  return match ? match[1] : text;
}

/** The request's `file`, as the client spells it: a virtual path, or '' for none. */
function fileParam(query: URLSearchParams): string { return String(query.get('file') ?? ''); }
/** A virtual path the viewer takes as absolute: the client sends none that is not. */
const absolute = (file: string) => file.startsWith('/');

function redirectTo(ctx: ViewerApiContext, entry: ExportObject): ViewerApiResponse {
  return { status: 302, redirect: ctx.objectUrl(entry.object), headers: { location: ctx.objectUrl(entry.object), 'cache-control': IMMUTABLE } };
}

function parseJsonBody(body: Uint8Array | undefined): unknown {
  try { return JSON.parse(new TextDecoder().decode(body ?? new Uint8Array())); } catch { return undefined; }
}

/** `{"<field>": [...]}` with at most `TESS_BATCH_MAX_NAMES` items, as the viewer's tess routes read a request. */
function tessItems(body: Uint8Array | undefined, field: string): unknown[] | null {
  if ((body?.byteLength ?? 0) > TESS_METADATA_MAX_BYTES) return null;
  const parsed = parseJsonBody(body);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || Object.keys(parsed).length !== 1 || !Object.hasOwn(parsed, field)) return null;
  const items = (parsed as Record<string, unknown>)[field];
  return Array.isArray(items) && items.length <= TESS_BATCH_MAX_NAMES ? items : null;
}

/** The batch container (`TESB`) holding `count` misses: every entry of length zero. */
export function emptyTessBatch(count: number): Uint8Array {
  const bytes = new Uint8Array(12 + 4 * count);
  const view = new DataView(bytes.buffer);
  view.setUint32(0, TESS_CACHE_BATCH_MAGIC, true);
  view.setUint32(4, TESS_CACHE_BATCH_VERSION, true);
  view.setUint32(8, count, true);
  return bytes;
}

function tessCacheName(path: string): string | null {
  let name: string;
  try { name = decodeURIComponent(path.slice('/__tess_cache/'.length)); } catch { return null; }
  return TESS_CACHE_NAME.test(name) && !name.includes('..') ? name : null;
}

function getRoute(index: ExportIndex, path: string, query: URLSearchParams, ctx: ViewerApiContext): ViewerApiResponse {
  if (path.startsWith('/__tess_cache/')) {
    // Always a miss: a hosted build keeps no shared cache, and the client tessellates from the surfaces.
    if (!tessCacheName(path)) return empty(403);
    const object = query.get('object'), limit = query.get('maxBytes');
    if (!object || !SHA256.test(object) || !limit || !MAX_SAFE_BYTES.test(limit) || Number(limit) <= 0) return empty(400);
    return empty(404);
  }
  if (!path.startsWith('/__cad/')) return notFound();
  const file = fileParam(query);
  switch (path) {
    case '/__cad/server':
      return json(200, recordedJson(index, '/__cad/server', ''));
    case '/__cad/catalog': {
      // The catalog of the file named: its row, or (a file the export lacks, or none named) no row.
      const key = file ? normalizeVirtualPath(file) : '';
      return json(200, recordedJson(index, '/__cad/catalog', key) ?? recordedJson(index, '/__cad/catalog', ''));
    }
    case '/__cad/artifact': {
      if (!file || !absolute(file)) return badRequest(NOT_ABSOLUTE);
      const recorded = recordedJson(index, '/__cad/artifact', normalizeVirtualPath(file));
      if (recorded !== undefined) return json(200, recorded);
      return json(200, STEP.test(file) ? { state: 'failed', error: `Artifact source not found: ${file}` } : { state: 'compiled' });
    }
    case '/__cad/preview': {
      if (!file || !absolute(file)) return badRequest(NOT_ABSOLUTE);
      if (!STEP.test(file)) return badRequest('A build status requires a STEP output path');
      const key = normalizeVirtualPath(file);
      return json(200, recordedJson(index, '/__cad/preview', key) ?? { output: key, file: key, state: 'disconnected', revision: null });
    }
    case '/__cad/drawing': {
      if (!file) return badRequest('GET /__cad/drawing needs ?file=<the absolute path of a .dxf>');
      if (!absolute(file)) return badRequest(NOT_ABSOLUTE);
      if (extensionOf(file) !== 'dxf') return badRequest(`/__cad/drawing renders DXF drawings; ${file.slice(file.lastIndexOf('/') + 1)} is not a .dxf file`);
      const recorded = recordedJson(index, '/__cad/drawing', normalizeVirtualPath(file));
      return recorded === undefined ? notFound() : json(200, recorded);
    }
    case '/__cad/asset': {
      if (!file || !absolute(file)) return badRequest(NOT_ABSOLUTE);
      const entry = recordedObject(index, '/__cad/asset', normalizeVirtualPath(file));
      return entry ? redirectTo(ctx, entry) : notFound();
    }
    case '/__cad/store': {
      // `file=/<tree>/assembly.json` and `file=/<tree>/components/<cid>.surf`, or the object form
      // (`object=<sha256>`): each a recorded object, else the viewer's 404.
      const object = query.get('object');
      const entry = object !== null ? recordedObject(index, '/__cad/store', object) : recordedObject(index, '/__cad/store', file.replace(/\\/g, '/'));
      return entry ? redirectTo(ctx, entry) : notFound();
    }
    case '/__cad/folder':
    case '/__cad/search': {
      const folder = String(query.get('path') ?? '');
      if (!folder || !absolute(folder)) return badRequest(NOT_ABSOLUTE);
      const listing = path === '/__cad/folder' ? listFolder(index, folder) : searchFolder(index, folder, String(query.get('q') ?? ''));
      return listing ? json(200, listing) : json(404, { error: `No folder at ${folder}` });
    }
    case '/__cad/recents':
      return json(200, { recents: [] });
    case '/__cad/thumbnail':
      return notFound();
    case '/__cad/version':
      return json(200, { notice: null });
    case '/__cad/analytics':
      return json(200, { ask: false, sharing: false, reason: 'unavailable', policy: '' });
    case '/__cad/features':
      return json(200, { quickEdit: true });
    default:
      return notFound();
  }
}

async function postRoute(index: ExportIndex, path: string, query: URLSearchParams, body: Uint8Array | undefined, ctx: ViewerApiContext): Promise<ViewerApiResponse> {
  const length = body?.byteLength ?? 0;
  if (path === '/__tess_cache/probe') {
    if (length > TESS_METADATA_MAX_BYTES) return empty(413, { connection: 'close' });
    return tessItems(body, 'tessellationInputs') ? json(200, { entries: {} }) : badRequest('bad tessellation probe request');
  }
  if (path === '/__tess_cache/batch') {
    if (length > TESS_METADATA_MAX_BYTES) return empty(413, { connection: 'close' });
    const entries = tessItems(body, 'entries');
    if (!entries) return badRequest('bad batch request');
    return { status: 200, headers: { 'content-type': 'application/octet-stream', 'cache-control': 'no-store' }, body: emptyTessBatch(entries.length) };
  }
  if (path.startsWith('/__tess_cache/')) {
    // A write-back is accepted and kept nowhere: the next read is a miss again.
    return tessCacheName(path) ? empty(204) : empty(403);
  }
  if (!path.startsWith('/__cad/')) return empty(405, { allow: 'POST' });
  switch (path) {
    case '/__cad/artifact': {
      // Nothing to compile: the export records a built document. A STEP the export lacks is one the
      // viewer could not find either.
      const file = fileParam(query);
      if (!file || !absolute(file)) return json(400, { ok: false, error: NOT_ABSOLUTE });
      const recorded = recordedJson(index, '/__cad/artifact', normalizeVirtualPath(file));
      if (recorded !== undefined) return json(200, { ok: true, ...(recorded as object) });
      return STEP.test(file) ? json(500, { ok: false, state: 'failed', error: `Artifact source not found: ${file}` }) : json(200, { ok: true, state: 'compiled' });
    }
    case '/__cad/features': {
      if (length > SMALL_BODY_MAX_BYTES) return empty(413, { connection: 'close' });
      const change = length ? parseJsonBody(body) : {};
      if (!change || typeof change !== 'object' || Array.isArray(change) || !Object.values(change).every(value => typeof value === 'boolean')) {
        return json(400, { ok: false, error: 'a features change is {feature: on or off}' });
      }
      return json(200, { quickEdit: true, ...(change as Record<string, boolean>) });
    }
    case '/__cad/sketches': {
      if (length > SKETCH_MAX_BYTES) return empty(413, { connection: 'close' });
      if (!body || !PNG_SIGNATURE.every((byte, at) => body[at] === byte)) return json(400, { ok: false, error: 'A sketch is a PNG image of at most 20 MiB' });
      const saved = await ctx.saveSketch(body, String(query.get('name') ?? ''));
      return json(200, { ok: true, path: saved });
    }
    case '/__cad/surfaces':
    case '/__cad/surfaces/cancel':
    case '/__cad/pick':
    case '/__cad/reveal':
    case '/__cad/clipboard':
    case '/__cad/shutdown':
    case '/__cad/recents':
    case '/__cad/analytics':
    case '/__cad/analytics/activity':
      return notFoundPost();
    default:
      return empty(405, { allow: 'POST' });
  }
}

/**
 * Answer one request of a build's viewer API from its export. `req.path` is the route (`/__cad/…`
 * or `/__tess_cache/…`), with or without the `/b/<build>` prefix; `req.headers`, when the server
 * passes them, carry the guard every POST needs.
 */
export async function handleViewerApi(index: ExportIndex, req: ViewerApiRequest, ctx: ViewerApiContext): Promise<ViewerApiResponse> {
  const method = String(req.method || '').toUpperCase();
  const path = viewerApiPath(req.path);
  if (method === 'GET' || method === 'HEAD') {
    const answer = getRoute(index, path, req.query, ctx);
    if (method === 'GET') return answer;
    const { json: _json, body: _body, ...head } = answer;
    return head;
  }
  if (method === 'POST') {
    if (req.headers && !req.headers[POST_GUARD_HEADER]) {
      return json(403, { error: `missing ${POST_GUARD_HEADER} header (cross-site POST blocked); send '${POST_GUARD_HEADER}: 1'` });
    }
    return postRoute(index, path, req.query, req.body, ctx);
  }
  return empty(405, { allow: 'GET, HEAD, POST' });
}

/** Whether `path` names a file the viewer shows, by its extension: the page's own routing uses it. */
export function isViewablePath(path: string): boolean { return CAD_EXTENSIONS.has(extensionOf(path)); }

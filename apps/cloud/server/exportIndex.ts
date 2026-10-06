/**
 * A build's export (`cadgen viewer export`): `export.json` as the server reads it, and the
 * lookups the compat viewer API makes in it. Nothing here touches the object store or the
 * network; an index is plain data about one immutable build.
 *
 * Paths are virtual: POSIX, relative to the exported folder, with a leading slash
 * (`/STEP/bracket.step`). `routes` holds what `cadgen.viewer` answered, by request key: the
 * `file` query the client sends (`''` for a request with none), or an object's hash for the
 * store's object form.
 */

export const EXPORT_SCHEMA = 1;

export interface ExportFile { path: string; kind: string; bytes: number; sha256: string }
export interface ExportObject { object: string; type: string; bytes: number }
export type JsonRoute = '/__cad/server' | '/__cad/catalog' | '/__cad/artifact' | '/__cad/preview' | '/__cad/drawing';
export type ObjectRoute = '/__cad/asset' | '/__cad/store';
export interface ExportRoutes {
  '/__cad/server': Record<string, unknown>;
  '/__cad/catalog': Record<string, unknown>;
  '/__cad/artifact': Record<string, unknown>;
  '/__cad/preview': Record<string, unknown>;
  '/__cad/drawing': Record<string, unknown>;
  '/__cad/asset': Record<string, ExportObject>;
  '/__cad/store': Record<string, ExportObject>;
}
export interface ExportIndex {
  schema: typeof EXPORT_SCHEMA;
  /** The cadgen that made the export. */
  cadgen: string;
  /** Every regular file under the exported folder, sources included. */
  files: ExportFile[];
  /** The files the viewer shows, in order; the first is the build's primary file. */
  views: string[];
  routes: ExportRoutes;
}

/** The CAD files the viewer lists and shows, by extension (`cadgen.viewer.scanner.SOURCE_EXTENSIONS`). */
export const CAD_EXTENSIONS = new Set(['step', 'stp', 'stl', '3mf', 'glb', 'dxf', 'urdf', 'srdf', 'sdf']);
const JSON_ROUTES: JsonRoute[] = ['/__cad/server', '/__cad/catalog', '/__cad/artifact', '/__cad/preview', '/__cad/drawing'];
const OBJECT_ROUTES: ObjectRoute[] = ['/__cad/asset', '/__cad/store'];
const SHA256 = /^[0-9a-f]{64}$/;

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

function fail(message: string): never { throw new Error(`export.json: ${message}`); }

function isObjectEntry(value: unknown): value is ExportObject {
  return isRecord(value) && typeof value.object === 'string' && SHA256.test(value.object) && typeof value.type === 'string'
    && Number.isSafeInteger(value.bytes) && (value.bytes as number) >= 0;
}

/** Parse and validate one `export.json`; a malformed index throws with what is wrong. */
export function parseExportIndex(source: string | Uint8Array | unknown): ExportIndex {
  const value = typeof source === 'string' ? JSON.parse(source) : source instanceof Uint8Array ? JSON.parse(new TextDecoder().decode(source)) : source;
  if (!isRecord(value)) fail('not an object');
  if (value.schema !== EXPORT_SCHEMA) fail(`schema ${JSON.stringify(value.schema)} is not ${EXPORT_SCHEMA}`);
  if (typeof value.cadgen !== 'string') fail('no cadgen version');
  if (!Array.isArray(value.files) || !value.files.every(file => isRecord(file) && typeof file.path === 'string' && file.path.startsWith('/')
    && typeof file.kind === 'string' && Number.isSafeInteger(file.bytes) && typeof file.sha256 === 'string' && SHA256.test(file.sha256))) fail('files must list {path, kind, bytes, sha256}');
  if (!Array.isArray(value.views) || !value.views.length || !value.views.every(view => typeof view === 'string' && view.startsWith('/'))) fail('views must name at least one virtual path');
  if (!isRecord(value.routes)) fail('no routes');
  for (const route of JSON_ROUTES) if (!isRecord(value.routes[route])) fail(`no ${route} answers`);
  for (const route of OBJECT_ROUTES) {
    const answers = value.routes[route];
    if (!isRecord(answers) || !Object.values(answers).every(isObjectEntry)) fail(`${route} answers must be {object, type, bytes}`);
  }
  return value as unknown as ExportIndex;
}

/** The one spelling of a virtual path: forward slashes, one leading slash, no trailing one. */
export function normalizeVirtualPath(path: string): string {
  const slashed = String(path || '').replace(/\\/g, '/').replace(/\/+/g, '/');
  const trimmed = slashed.replace(/\/+$/, '');
  return trimmed ? (trimmed.startsWith('/') ? trimmed : `/${trimmed}`) : '/';
}

export function fileEntry(index: ExportIndex, path: string): ExportFile | undefined {
  const wanted = normalizeVirtualPath(path);
  return index.files.find(file => file.path === wanted);
}

/** A recorded JSON answer, or undefined when the export has none for the key. */
export function recordedJson(index: ExportIndex, route: JsonRoute, key: string): unknown {
  const answers = index.routes[route];
  return Object.hasOwn(answers, key) ? answers[key] : undefined;
}

/** A recorded object (its hash, type and size), by the key the client sends; the store's keys take a leading slash or none. */
export function recordedObject(index: ExportIndex, route: ObjectRoute, key: string): ExportObject | undefined {
  const answers = index.routes[route];
  const spellings = route === '/__cad/store' ? [key, key.replace(/^\/+/, ''), `/${key.replace(/^\/+/, '')}`] : [key];
  for (const spelling of spellings) if (Object.hasOwn(answers, spelling)) return answers[spelling];
  return undefined;
}

/** The build's primary file: the first view. */
export function primaryView(index: ExportIndex): string { return index.views[0]; }

export function extensionOf(path: string): string {
  const name = path.slice(path.lastIndexOf('/') + 1);
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}

const isCadFile = (path: string) => CAD_EXTENSIONS.has(extensionOf(path));
const collate = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });
const byName = (a: string, b: string) => collate.compare(a, b) || (a < b ? -1 : a > b ? 1 : 0);
const parentOf = (path: string) => { const index = path.lastIndexOf('/'); return index > 0 ? path.slice(0, index) : '/'; };

/** Every folder the files imply, the root included. */
function folders(index: ExportIndex): Set<string> {
  const found = new Set<string>(['/']);
  for (const file of index.files) {
    let folder = parentOf(file.path);
    while (folder !== '/' && !found.has(folder)) { found.add(folder); folder = parentOf(folder); }
  }
  return found;
}

export interface FolderListing { path: string; entries: { name: string; kind: 'directory' | 'file' }[]; truncated: boolean }
export interface SearchListing { path: string; results: string[]; truncated: boolean }
export const SEARCH_LIMIT = 200;

/** One folder's subfolders and CAD files, as `GET /__cad/folder` lists them; null when there is no such folder. */
export function listFolder(index: ExportIndex, path: string): FolderListing | null {
  const folder = normalizeVirtualPath(path);
  const known = folders(index);
  if (!known.has(folder)) return null;
  const prefix = folder === '/' ? '/' : `${folder}/`;
  const children = [...known].filter(item => item !== folder && parentOf(item) === folder).map(item => item.slice(prefix.length));
  const files = index.files.filter(file => parentOf(file.path) === folder && isCadFile(file.path)).map(file => file.path.slice(prefix.length));
  return {
    path: folder,
    entries: [...children.sort(byName).map(name => ({ name, kind: 'directory' as const })), ...files.sort(byName).map(name => ({ name, kind: 'file' as const }))],
    truncated: false,
  };
}

/** The CAD files under a folder whose path below it holds `query`, shallower first, as `GET /__cad/search` finds them. */
export function searchFolder(index: ExportIndex, path: string, query: string): SearchListing | null {
  const folder = normalizeVirtualPath(path);
  if (!folders(index).has(folder)) return null;
  const prefix = folder === '/' ? '/' : `${folder}/`;
  const needle = String(query || '').trim().toLowerCase();
  const matches = index.files.filter(file => file.path.startsWith(prefix) && isCadFile(file.path) && file.path.slice(prefix.length).toLowerCase().includes(needle))
    .map(file => file.path)
    .sort((a, b) => (a.split('/').length - b.split('/').length) || byName(a, b));
  return { path: folder, results: matches.slice(0, SEARCH_LIMIT), truncated: matches.length > SEARCH_LIMIT };
}

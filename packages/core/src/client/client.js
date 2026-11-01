import { createExportService } from './exports.js';
import { encodeBase64 } from './base64.js';
import { isEngineGone, isEngineRefused, requestViewerJson, ViewerRequestError } from "./request.js";
import { retainGlbMeshWorker } from '../lib/render/glbMeshWorkerClient.js';
import { retainStlMeshWorker } from '../lib/render/stlMeshWorkerClient.js';
import { applyViewerOriginToEntries, normalizeViewerOrigin, viewerOriginUrl } from './origin.js';
import { isDocumentId } from '../lib/cadRefs.js';
import { createHttpCadResourceProvider, scopeCadResources } from './resources.js';
export * from './origin.js';

/**
 * @param {string} path
 * @param {{origin?: string, file?: string, params?: Record<string, string | number | boolean | null | undefined>}} options
 * @returns {string}
 */
export function cadApiUrl(path, { origin = '', file = '', params = {} } = {}) {
  const url = new URL(path, 'http://cad.local');
  if (file) url.searchParams.set('file', file);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && String(value) !== '') url.searchParams.set(key, String(value));
  }
  return viewerOriginUrl(origin, `${url.pathname}${url.search}`);
}

function abortError() {
  return new DOMException('The operation was aborted.', 'AbortError');
}

// The longest a drawing's 202 may ask the client to wait before it asks again.
const DRAWING_RETRY_MAX_MS = 5000;
// The longest an engine document's 202 (the engine still reading it) may have the client wait.
const ENGINE_RETRY_MAX_MS = 5000;

/** `ms` of waiting that `signal` ends early, as an AbortError. */
function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(abortError()); return; }
    const done = () => { signal?.removeEventListener('abort', stop); resolve(); };
    const timer = setTimeout(done, ms);
    const stop = () => { clearTimeout(timer); reject(abortError()); };
    signal?.addEventListener('abort', stop, { once: true });
  });
}

// A file is named by its absolute path, `/`-separated on every platform; a document known by its id
// alone (a model's) by its id. A catalog row carries its document's id: rows join by it, so one
// file however its path is spelled (a symlink, a case variant) is one row.
const normalizedFile = (file) => String(file || '').replace(/\\/g, '/');
const entryKey = (entry) => entry.id || normalizedFile(entry.file);

/** Whether `error` says the file a view asked for is not there (`resolveEntry`). */
export function isMissingFileError(error) {
  return error?.code === 'cad-file-missing';
}

// A guarded JSON change: the viewer refuses a POST, PUT, PATCH or DELETE without its header (no
// cross-site form can send one).
const JSON_POST = Object.freeze({ 'content-type': 'application/json', 'x-cadgen-viewer': '1' });
// The engine's API (`cad_server/viewer/kinds.py`): every route the page calls is under it.
export const API = '/api/v1';

/**
 * Documents' envelopes (`GET /api/v1/documents/<id>`, `?path=`) as the catalog the client keeps: their
 * rows and, for the one asked for, its row's digest. A model's row carries the script that builds it
 * (the envelope's `source.path`) as `script`, where the envelope names one: its file menu acts on it.
 */
const scriptOf = (envelope) => (envelope?.source?.type === 'script' && typeof envelope.source.path === 'string' && envelope.source.path
  ? envelope.source.path : null);
const rowOfEnvelope = (envelope) => (envelope?.entry && scriptOf(envelope) ? { ...envelope.entry, script: scriptOf(envelope) } : envelope?.entry);
const catalogOf = (envelopes) => ({ entries: envelopes.map(rowOfEnvelope).filter(Boolean),
  revision: envelopes.length === 1 ? envelopes[0]?.revision ?? '' : '' });
/**
 * A Recents row as the library reads it (`CadRecent`): the API names a row's document kind `kind`
 * and its record's (`file`, `model`, `shape`) `record`; the library's `kind` is the record's.
 */
export const libraryRow = (row) => ({ ...row, kind: row.record, documentKind: row.kind });
const libraryRows = (reply) => (Array.isArray(reply?.documents) ? reply.documents.map(libraryRow) : []);

/**
 * An explicit connection to a CAD Viewer, which serves files by absolute path. Its catalog holds
 * the files on screen, each read as it is asked for. Construction never starts requests.
 * @param {import("./types.js").CadClientOptions} options
 * @returns {import("./types.js").CadClient}
 */
export function createCadClient({ origin = '', fetch: fetchImpl = globalThis.fetch, pollIntervalMs = 2000, shouldPoll = () => true, resources: resourceProvider } = {}) {
  origin = normalizeViewerOrigin(origin);
  let disposed = false;
  const resourceLifetime = new AbortController();
  const resources = scopeCadResources(resourceProvider || createHttpCadResourceProvider({ origin, fetch: fetchImpl }), resourceLifetime.signal);
  let snapshot = { entries: [], revision: 0, hydrated: false, refreshing: false, error: '', engineGone: false, engineRefused: false, catalogRevision: '' };
  const listeners = new Set();
  const requests = new Set();
  const sessions = new Set();
  let pollTimer = null;
  let refreshSequence = 0;
  // The newest answer applied for each file: an older one that lands later changes nothing.
  const publishedSequences = new Map();
  const activeFiles = new Map();
  // Each path a view asked for, and the id of the document the server answered it with.
  const aliases = new Map();
  // Why the server has no row for an id it was asked for (the engine's words) and the state it
  // names for it (`unsaved`, `detached`, or ''), by that id.
  const missing = new Map();
  let preferredFile = '';
  /** The key of the row `file` names: its document's id once the server said it. */
  const keyOf = (file) => (isDocumentId(file) ? file : aliases.get(normalizedFile(file)) || normalizedFile(file));
  /** The row of `file` in `entries`: by its document's id, else by the path it carries. */
  const rowOf = (entries, file) => entries.find((entry) => entryKey(entry) === keyOf(file))
    || entries.find((entry) => normalizedFile(entry.file) === normalizedFile(file));
  const pendingRefreshes = new Map();
  let server = null;

  function publish(patch) {
    if (disposed) return;
    snapshot = { ...snapshot, ...patch, revision: snapshot.revision + 1 };
    for (const listener of listeners) listener();
  }

  async function request(path, { signal, file = '', params = {}, method = 'GET', headers = {}, body, timeoutMs = 0, idempotent = false, operation = 'request' } = {}) {
    if (disposed || signal?.aborted) throw abortError();
    const controller = new AbortController();
    const abort = () => controller.abort(signal?.reason);
    signal?.addEventListener('abort', abort, { once: true });
    requests.add(controller);
    try {
      const payload = await requestViewerJson(cadApiUrl(path, { origin, file, params }), {
        method, headers, signal: controller.signal, cache: 'no-store',
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      }, operation, { timeoutMs, idempotent, fetch: fetchImpl });
      if (disposed || controller.signal.aborted) throw abortError();
      return payload;
    } catch (error) {
      if (operation === 'catalog' && error?.failure?.kind === 'timeout') {
        throw new ViewerRequestError({ ...error.failure, detail: `Timed out loading CAD catalog after ${timeoutMs / 1000}s` }, error);
      }
      throw error;
    } finally {
      signal?.removeEventListener('abort', abort);
      requests.delete(controller);
    }
  }

  function publishCatalog(catalog, { sequence = ++refreshSequence, file = '' } = {}) {
    const asked = normalizedFile(file);
    if (sequence < (publishedSequences.get(asked) || 0)) return;
    publishedSequences.set(asked, sequence);
    const incoming = applyViewerOriginToEntries(catalog?.entries, origin);
    // The document the path asked for is the row the server answered: its id joins every spelling.
    if (asked && incoming.length === 1 && incoming[0].id && !isDocumentId(asked)) aliases.set(asked, incoming[0].id);
    // An id the engine no longer holds (deleted while it was on screen): its row goes with it.
    let gone = '';
    if (isDocumentId(asked)) {
      if (typeof catalog?.missing === 'string' && !incoming.length) {
        missing.set(asked, { text: catalog.missing, state: typeof catalog.missingState === 'string' ? catalog.missingState : '' });
        gone = asked;
      } else missing.delete(asked);
    }
    const answered = new Set(incoming.map(entryKey));
    // The catalog is the files on screen: an answer brings one, and keeps the others shown.
    const shown = new Set([...activeFiles.keys(), preferredFile].map(keyOf));
    const previous = new Map(snapshot.entries.map((entry) => [entryKey(entry), entry]));
    const entries = [
      ...snapshot.entries.filter((entry) => !answered.has(entryKey(entry)) && shown.has(entryKey(entry)) && entryKey(entry) !== gone),
      ...incoming.map((entry) => {
        const before = previous.get(entryKey(entry));
        return before && JSON.stringify(before) === JSON.stringify(entry) ? before : entry;
      }),
    ];
    // The server's digest of the catalog just applied: a host that watches for change compares it.
    const catalogRevision = typeof catalog?.revision === 'string' ? catalog.revision : snapshot.catalogRevision;
    const changed = entries.length !== snapshot.entries.length || entries.some((entry, index) => entry !== snapshot.entries[index]);
    if (changed || !snapshot.hydrated || snapshot.refreshing || snapshot.error || snapshot.engineGone || catalogRevision !== snapshot.catalogRevision) {
      publish({ entries: changed ? entries : snapshot.entries, hydrated: true, refreshing: false, error: '', engineGone: false, engineRefused: false, catalogRevision });
    }
  }

  async function refresh({ file = preferredFile, signal, markRefreshing = !snapshot.hydrated } = {}) {
    // A file-specific refresh must not inherit a different view's request or cancellation.
    if (!signal && pendingRefreshes.has(file)) return pendingRefreshes.get(file);
    const sequence = ++refreshSequence;
    if (markRefreshing) publish({ refreshing: true, error: '' });
    const work = (async () => {
      try {
        // A document named by its id is read by id (its envelope; an id no document has is a 404
        // saying why, and the state the engine names for it); a file by its path, which registers it.
        let catalog;
        if (isDocumentId(file)) {
          try {
            catalog = catalogOf([await request(`${API}/documents/${encodeURIComponent(file)}`, { signal, timeoutMs: 10_000, operation: 'catalog' })]);
          } catch (error) {
            const failure = error?.failure;
            if (failure?.status !== 404 || isEngineGone(error)) throw error;
            catalog = { entries: [], revision: '', missing: failure.detail,
              ...(typeof failure.payload?.state === 'string' ? { missingState: failure.payload.state } : {}) };
          }
        } else {
          // The path rides in the query even empty: a page with no file asks the cheapest read there is.
          const reply = await request(`${API}/documents?path=${encodeURIComponent(file)}`, { signal, timeoutMs: 10_000, operation: 'catalog' });
          catalog = catalogOf(Array.isArray(reply?.documents) ? reply.documents : []);
        }
        publishCatalog(catalog, { sequence, file });
        return catalog;
      } catch (error) {
        if (!disposed && !signal?.aborted && error?.name !== 'AbortError' && sequence === refreshSequence) {
          publish({ hydrated: true, refreshing: false, error: error instanceof Error ? error.message : String(error),
            engineGone: isEngineGone(error), engineRefused: isEngineRefused(error) });
        }
        throw error;
      }
    })();
    if (!signal) {
      pendingRefreshes.set(file, work);
      void work.finally(() => { if (pendingRefreshes.get(file) === work) pendingRefreshes.delete(file); }).catch(() => {});
    }
    return work;
  }

  function stopPolling() {
    if (pollTimer !== null) clearTimeout(pollTimer);
    pollTimer = null;
  }
  function schedulePoll() {
    if (disposed || !listeners.size || pollTimer !== null || !(pollIntervalMs > 0)) return;
    pollTimer = setTimeout(async () => {
      pollTimer = null;
      // Keep the original interval cadence; a slow request is shared by refresh.
      schedulePoll();
      if (!shouldPoll()) return;
      // Read again the files on screen.
      const files = activeFiles.size ? [...activeFiles.keys()] : [preferredFile];
      for (const file of files) {
        if (disposed || !listeners.size) break;
        try { await refresh({ file, markRefreshing: false }); } catch { /* snapshot reports connection failures */ }
      }
    }, pollIntervalMs);
  }

  // Where each document a view reads is read (its kind's API, `/api/v1/documents/<kind>/<id>`), by
  // the path or the id the view names it by: the server's answer, once.
  const apis = new Map();
  /** The API of the document `file` names: a file opened by its path (`POST /api/v1/documents`), an id's envelope. */
  async function documentApi(file, { signal, operation }) {
    const key = isDocumentId(file) ? file : normalizedFile(file);
    if (apis.has(key)) return apis.get(key);
    const reply = isDocumentId(file)
      ? await request(`${API}/documents/${encodeURIComponent(file)}`, { signal, timeoutMs: 10_000, operation })
      // An open is safe to give up on and ask again: its 10 s is the time the server may stay silent.
      : await request(`${API}/documents`, { method: 'POST', headers: JSON_POST, body: { path: file }, signal, operation,
        timeoutMs: 10_000, idempotent: true });
    apis.set(key, reply.api);
    return reply.api;
  }

  const client = {
    // An export is made by its document's route (`POST /api/v1/documents/<id>/exports`): a file
    // shown by its path is its row's document.
    exports: createExportService({ origin, fetch: fetchImpl,
      documentOf: (doc) => (isDocumentId(doc) ? doc : rowOf(snapshot.entries, doc)?.id || '') }),
    origin,
    resources,
    getSnapshot: () => snapshot,
    subscribe(listener) {
      if (disposed) throw new Error('This CAD client has been disposed.');
      listeners.add(listener);
      if (listeners.size === 1) {
        void refresh().catch(() => {});
        schedulePoll();
      }
      return () => { listeners.delete(listener); if (!listeners.size) stopPolling(); };
    },
    refresh,
    async resolveEntry(path, { signal } = {}) {
      preferredFile = path;
      let entry = rowOf(snapshot.entries, path);
      if (!entry) {
        await refresh({ file: path, signal });
        entry = rowOf(snapshot.entries, path);
      }
      if (signal?.aborted || disposed) throw abortError();
      if (!entry) {
        // An id the engine does not hold says why, and names the command that builds it again, and
        // its state, the engine's (`unsaved`, `detached`), where it names one.
        const why = missing.get(path);
        throw Object.assign(new Error(why?.text || `File does not exist: ${path}`), { code: 'cad-file-missing', ...(why?.state ? { state: why.state } : {}) });
      }
      return entry;
    },
    // The row of the document `path` names (its path, or its id), joined by its document's id.
    entryOf(path) {
      return path ? rowOf(snapshot.entries, path) ?? null : null;
    },
    async serverInfo({ signal, fresh = false } = {}) {
      if (!server || fresh) {
        const next = await request(`${API}/server`, { signal, operation: 'server' });
        if (server && server.identityToken !== next.identityToken) {
          resources.invalidate();
          publish({});
        }
        server = next;
      }
      return server;
    },
    // One folder's subfolders and CAD files, and the CAD files nested under a folder whose path
    // below it holds `query` (bounded by the server, which says when it stopped early).
    folder(path, { signal } = {}) {
      return request(`${API}/local/folder`, { params: { path }, signal, timeoutMs: 10_000, operation: 'folder' });
    },
    search(path, query, { signal } = {}) {
      // `q` rides in the query even empty: it is what makes the read a search.
      return request(`${API}/local/folder?q=${encodeURIComponent(query ?? '')}`, { params: { path }, signal, timeoutMs: 10_000, operation: 'search' });
    },
    // What every CAD view on this machine shares, and the host's own effects, through this client's
    // fetch: the web page's own server, or the CAD app's through its tunnel. The home's library of
    // models and their pictures, Open with the desktop's chooser, Reveal, the person's analytics
    // answer and language, and whether a newer text-to-cad is out.
    recents({ signal } = {}) {
      return request(`${API}/documents`, { signal, operation: 'recents' }).then(libraryRows);
    },
    changeRecents(change) {
      return request(`${API}/documents`, { method: 'PATCH', headers: JSON_POST, body: change, operation: 'recents' }).then(libraryRows);
    },
    async keepThumbnail(png, path) {
      return client.changeRecents({ action: 'thumbnail', path, png: encodeBase64(new Uint8Array(await png.arrayBuffer())) });
    },
    async thumbnail(model, { signal } = {}) {
      // A document's picture, by its id; the picture's name (its content's) keeps an older one out of any cache.
      const response = await fetchImpl(client.thumbnailUrl(model), { signal, cache: 'no-store' });
      if (!response.ok) return null;
      return `data:image/png;base64,${encodeBase64(new Uint8Array(await response.arrayBuffer()))}`;
    },
    thumbnailUrl(model) {
      return cadApiUrl(`${API}/documents/${encodeURIComponent(model.id)}/thumbnail`, { origin, params: { v: model.thumbnail } });
    },
    pick() {
      return request(`${API}/local/pick`, { method: 'POST', headers: { 'x-cadgen-viewer': '1' }, operation: 'pick' }).then((reply) => reply.path ?? null);
    },
    async reveal(path) {
      const response = await fetchImpl(cadApiUrl(`${API}/local/reveal`, { origin }), { method: 'POST', headers: JSON_POST, body: JSON.stringify({ path }) });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.error || 'Could not reveal this file in the file manager.');
      }
    },
    // The person's settings (`/api/v1/settings`): whether usage stats are shared, and the language.
    consent(share) {
      return (share === undefined ? request(`${API}/settings`, { operation: 'consent' })
        : request(`${API}/settings`, { method: 'PUT', headers: JSON_POST, body: { telemetry: { share } }, operation: 'consent' }))
        .then((settings) => settings.telemetry);
    },
    language(locale) {
      return (locale === undefined ? request(`${API}/settings`, { operation: 'language' })
        : request(`${API}/settings`, { method: 'PUT', headers: JSON_POST, body: { language: { locale } }, operation: 'language' }))
        .then((settings) => settings.language);
    },
    // Who the engine is, this start of it (`instance`), whether a newer text-to-cad is out and where
    // an update is (`GET /api/v1/server`); and the update button's click (`POST /api/v1/local/update`),
    // which answers the notice, the release, the instance and the update.
    version() {
      return request(`${API}/server`, { operation: 'version' });
    },
    startUpdate() {
      return request(`${API}/local/update`, { method: 'POST', headers: { 'x-cadgen-viewer': '1' }, operation: 'update' });
    },
    reportActivity(activity) {
      void Promise.resolve(fetchImpl(cadApiUrl(`${API}/local/activity`, { origin }), { method: 'POST', headers: JSON_POST, body: JSON.stringify(activity) })).catch(() => {});
    },
    async drawing(file, { signal } = {}) {
      // A `.dxf` flattened to 2D render primitives on the SERVER: ezdxf does the
      // reading, the client only paints. A plain GET of the document's `drawing`, derived data
      // cached by content hash: unchanged bytes are served from the store. Bytes the
      // server has not drawn yet it renders off the request, answering
      // 202 { state: 'drawing', retryMs } until it has, and the client asks
      // again after `retryMs`. Each request's 10 s is the time the server may
      // stay silent (`requestViewerJson`), so a drawing that takes a minute to
      // render or to arrive opens, and a server that stopped answering fails.
      if (!file) throw new Error('Missing file');
      const api = await documentApi(file, { signal, operation: 'drawing' });
      for (;;) {
        const reply = await request(`${api}/drawing`, { signal, timeoutMs: 10_000, operation: 'drawing' });
        if (reply?.state !== 'drawing') return reply;
        await pause(Math.min(Math.max(Number(reply.retryMs) || 0, 0), DRAWING_RETRY_MAX_MS), signal);
        if (disposed) throw abortError();
      }
    },
    async robot(file, { signal } = {}) {
      // A robot description resolved on the SERVER (cad_server.robot_payload): the articulation
      // the page plays and the visuals it draws, each mesh by a URL this server answers -- its
      // document's `structure`. Derived data cached by the description's bytes, so a second
      // request is one object read; a cold read validates, resolves frames and meshes primitives
      // within the 10 s.
      if (!file) throw new Error('Missing file');
      const api = await documentApi(file, { signal, operation: 'robot' });
      return request(`${api}/structure`, { signal, timeoutMs: 10_000, operation: 'robot' });
    },
    async engineDocument(file, { signal, onProgress } = {}) {
      // A document the cadgen ENGINE reads -- an `.xbf`, or a STEP, or a model it holds -- is served
      // by the engine: the client opens it (`POST /api/v1/documents`, `cad_server.viewer.documents`)
      // and answers where the page reads it, its kind's API through this server
      // (`/api/v1/documents/<kind>/<id>`), so the reads travel as every request does (over the CAD
      // app's tunnel too). Answered with the fetch they are made with. The engine's first read of a
      // large STEP takes a while: the server answers 202 { state: 'reading', retryMs, building }
      // until the engine holds it -- `building` the last frame of its import, where the engine says
      // one (its reader parsing the file, then collecting its parts, counted), handed to
      // `onProgress` -- and the client asks again after `retryMs`; each request's 10 s is the time the
      // server may stay silent (an open is safe to give up on and ask again).
      if (!file) throw new Error('Missing file');
      for (;;) {
        const reply = await request(`${API}/documents`, { method: 'POST', headers: JSON_POST, signal, operation: 'engine-document',
          body: isDocumentId(file) ? { id: file } : { path: file }, timeoutMs: 10_000, idempotent: true });
        if (reply?.state !== 'reading') return { doc: reply.id, kind: reply.kind, url: viewerOriginUrl(origin, reply.api), fetch: fetchImpl };
        if (reply.building && typeof reply.building === 'object' && typeof onProgress === 'function') onProgress(reply.building);
        await pause(Math.min(Math.max(Number(reply.retryMs) || 0, 0), ENGINE_RETRY_MAX_MS), signal);
        if (disposed) throw abortError();
      }
    },
    async engineHolds(file, { signal } = {}) {
      // Whether the engine holds a read of the document now (its envelope's `held`), asked without starting one.
      if (!file) throw new Error('Missing file');
      const envelope = isDocumentId(file)
        ? await request(`${API}/documents/${encodeURIComponent(file)}`, { signal, timeoutMs: 10_000, operation: 'engine-document' })
        : (await request(`${API}/documents`, { params: { path: file }, signal, timeoutMs: 10_000, operation: 'engine-document' }))?.documents?.[0];
      return envelope?.held === true;
    },
    createRenderSession({ file = '' } = {}) {
      if (disposed) throw new Error('This CAD client has been disposed.');
      if (file) activeFiles.set(file, (activeFiles.get(file) || 0) + 1);
      const controller = new AbortController();
      const releases = [retainGlbMeshWorker(), retainStlMeshWorker()];
      let sessionDisposed = false;
      const session = { resources, signal: controller.signal, dispose() {
        if (sessionDisposed) return;
        sessionDisposed = true;
        if (file) {
          const remaining = (activeFiles.get(file) || 0) - 1;
          if (remaining > 0) activeFiles.set(file, remaining); else activeFiles.delete(file);
        }
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
      resourceLifetime.abort();
      refreshSequence += 1;
      stopPolling();
      for (const request of requests) request.abort();
      requests.clear();
      for (const session of [...sessions]) session.dispose();
      pendingRefreshes.clear();
      listeners.clear();
    }
  };
  return client;
}

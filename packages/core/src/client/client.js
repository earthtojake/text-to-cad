import { requestViewerJson, ViewerRequestError } from "./request.js";
import { retainSurfWorkerPool } from '../lib/surf/surfWorkerClient.js';
import { retainGlbMeshWorker } from '../lib/render/glbMeshWorkerClient.js';
import { retainStlMeshWorker } from '../lib/render/stlMeshWorkerClient.js';
import { applyViewerOriginToEntries, normalizeViewerOrigin, viewerOriginUrl } from './origin.js';
import { createHttpTessellationCacheProvider, createTessellationCache } from '../lib/surf/tessellationCache.js';

import { resolveSurfaceComponents } from './surfaceResolution.js';
import { observeEditingPreview } from './editingPreviewFeed.js';
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

// A file is named by its absolute path, `/`-separated on every platform.
const normalizedFile = (file) => String(file || '').replace(/\\/g, '/');
const entryKey = (entry) => normalizedFile(entry.file);

/** Whether `error` says the file a view asked for is not there (`resolveEntry`). */
export function isMissingFileError(error) {
  return error?.code === 'cad-file-missing';
}

/**
 * An explicit connection to a CAD Viewer, which serves files by absolute path. Its catalog holds
 * the files on screen, each read as it is asked for. Construction never starts requests.
 * @param {import("./types.js").CadClientOptions} options
 * @returns {import("./types.js").CadClient}
 */
export function createCadClient({ origin = '', workspaceId = 'local', fetch: fetchImpl = globalThis.fetch, pollIntervalMs = 2000, shouldPoll = () => true, resources: resourceProvider, editingPreviewFeed = null, maxBatchBytes } = {}) {
  origin = normalizeViewerOrigin(origin);
  let disposed = false;
  const resourceLifetime = new AbortController();
  const resources = scopeCadResources(resourceProvider || createHttpCadResourceProvider({ origin, fetch: fetchImpl }), resourceLifetime.signal);
  let snapshot = { entries: [], revision: 0, hydrated: false, refreshing: false, error: '', catalogRevision: '' };
  const listeners = new Set();
  const requests = new Set();
  const sessions = new Set();
  let pollTimer = null;
  let refreshSequence = 0;
  // The newest answer applied for each file: an older one that lands later changes nothing.
  const publishedSequences = new Map();
  const activeFiles = new Map();
  let preferredFile = '';
  const pendingRefreshes = new Map();
  let tessellationCache = null;
  let server = null;

  function publish(patch) {
    if (disposed) return;
    snapshot = { ...snapshot, ...patch, revision: snapshot.revision + 1 };
    for (const listener of listeners) listener();
  }

  async function request(path, { signal, file = '', params = {}, method = 'GET', headers = {}, body, timeoutMs = 0, operation = 'request' } = {}) {
    if (disposed || signal?.aborted) throw abortError();
    const controller = new AbortController();
    const abort = () => controller.abort(signal?.reason);
    signal?.addEventListener('abort', abort, { once: true });
    requests.add(controller);
    try {
      const payload = await requestViewerJson(cadApiUrl(path, { origin, file, params }), {
        method, headers, signal: controller.signal, cache: 'no-store',
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      }, operation, { timeoutMs, fetch: fetchImpl });
      if (disposed || controller.signal.aborted) throw abortError();
      return payload;
    } catch (error) {
      if (path === '/__cad/catalog' && error?.failure?.kind === 'timeout') {
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
    const answered = new Set(incoming.map(entryKey));
    // The catalog is the files on screen: an answer brings one, and keeps the others shown.
    const shown = new Set([...activeFiles.keys(), preferredFile].map(normalizedFile));
    const previous = new Map(snapshot.entries.map((entry) => [entryKey(entry), entry]));
    const entries = [
      ...snapshot.entries.filter((entry) => !answered.has(entryKey(entry)) && shown.has(entryKey(entry))),
      ...incoming.map((entry) => {
        const before = previous.get(entryKey(entry));
        return before && JSON.stringify(before) === JSON.stringify(entry) ? before : entry;
      }),
    ];
    // The server's digest of the catalog just applied: a host that watches for change compares it.
    const catalogRevision = typeof catalog?.revision === 'string' ? catalog.revision : snapshot.catalogRevision;
    const changed = entries.length !== snapshot.entries.length || entries.some((entry, index) => entry !== snapshot.entries[index]);
    if (changed || !snapshot.hydrated || snapshot.refreshing || snapshot.error || catalogRevision !== snapshot.catalogRevision) {
      publish({ entries: changed ? entries : snapshot.entries, hydrated: true, refreshing: false, error: '', catalogRevision });
    }
  }

  async function refresh({ file = preferredFile, signal, markRefreshing = !snapshot.hydrated } = {}) {
    // A file-specific refresh must not inherit a different view's request or cancellation.
    if (!signal && pendingRefreshes.has(file)) return pendingRefreshes.get(file);
    const sequence = ++refreshSequence;
    if (markRefreshing) publish({ refreshing: true, error: '' });
    const work = (async () => {
      try {
        const catalog = await request('/__cad/catalog', { file, signal, timeoutMs: 10_000, operation: 'catalog' });
        publishCatalog(catalog, { sequence, file });
        return catalog;
      } catch (error) {
        if (!disposed && !signal?.aborted && error?.name !== 'AbortError' && sequence === refreshSequence) {
          publish({ hydrated: true, refreshing: false, error: error instanceof Error ? error.message : String(error) });
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

  const client = {
    origin,
    resources,
    get workspaceId() { return workspaceId; },
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
      const match = (entries) => entries.find((entry) => entryKey(entry) === normalizedFile(path));
      let entry = match(snapshot.entries);
      if (!entry) {
        await refresh({ file: path, signal });
        entry = match(snapshot.entries);
      }
      if (signal?.aborted || disposed) throw abortError();
      if (!entry) throw Object.assign(new Error(`File does not exist: ${path}`), { code: 'cad-file-missing' });
      return entry;
    },
    async serverInfo({ signal, fresh = false } = {}) {
      if (!server || fresh) {
        const next = await request('/__cad/server', { signal, operation: 'server' });
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
      return request('/__cad/folder', { params: { path }, signal, timeoutMs: 10_000, operation: 'folder' });
    },
    search(path, query, { signal } = {}) {
      return request('/__cad/search', { params: { path, q: query }, signal, timeoutMs: 10_000, operation: 'search' });
    },
    requestArtifactStatus(file, { signal } = {}) {
      if (!file) return Promise.reject(new Error('Missing file'));
      return request('/__cad/artifact', { file, signal, timeoutMs: 10_000, operation: 'status' });
    },
    // Starts the file's compile and answers at once (`compiling`, or `compiled` when there is
    // nothing to build); the build is followed through `requestArtifactStatus`.
    requestArtifact(file, { force = false, signal } = {}) {
      if (!file) return Promise.reject(new Error('Missing file'));
      return request('/__cad/artifact', {
        file, signal, method: 'POST', operation: 'compile', params: force ? { force: '1' } : {}, headers: { 'x-cadgen-viewer': '1' }
      });
    },
    drawing(file, { signal } = {}) {
      // A `.dxf` flattened to 2D render primitives on the SERVER: ezdxf does the
      // reading, the client only paints. One plain GET, because the route is
      // derived data cached by content hash — a second request for unchanged
      // bytes is served from the store. The 10 s bound is the house value for a
      // GET that can do real work (a cold 10k-entity drawing is ~0.7 s).
      if (!file) return Promise.reject(new Error('Missing file'));
      return request('/__cad/drawing', { file, signal, timeoutMs: 10_000, operation: 'drawing' });
    },
    requestSurfaces(body, { signal } = {}) {
      return request('/__cad/surfaces', {
        body, signal, method: 'POST', operation: 'surfaces',
        headers: { 'content-type': 'application/json', 'x-cadgen-viewer': '1' },
      });
    },
    cancelSurfaceRequest(body, { signal } = {}) {
      return request('/__cad/surfaces/cancel', {
        body, signal, method: 'POST', operation: 'cancel-surfaces',
        headers: { 'content-type': 'application/json', 'x-cadgen-viewer': '1' },
      });
    },
    editingPreview(file, { after = '', signal } = {}) {
      return request('/__cad/preview', { file, signal, params: { after }, operation: 'preview' });
    },
    resolveSurfaceComponents(descriptor, requested, options) {
      return resolveSurfaceComponents(descriptor, requested, { ...options, client });
    },
    // A host that already hears a file's build feed (on a call it makes anyway) hands it in as
    // `editingPreviewFeed`, and nothing here asks the route.
    observeEditingPreview(file, onUpdate, onError, options) {
      if (editingPreviewFeed) return editingPreviewFeed(file, onUpdate, onError);
      return observeEditingPreview(file, onUpdate, onError, { ...options, client });
    },
    createRenderSession({ file = '' } = {}) {
      if (disposed) throw new Error('This CAD client has been disposed.');
      if (file) activeFiles.set(file, (activeFiles.get(file) || 0) + 1);
      const controller = new AbortController();
      const releases = [retainSurfWorkerPool(), retainGlbMeshWorker(), retainStlMeshWorker()];
      tessellationCache ??= createTessellationCache({
        provider: createHttpTessellationCacheProvider({ origin, headers: { 'x-cadgen-viewer': '1' }, fetch: fetchImpl, maxBatchBytes }),
        writeBack: { deferMs: 1500, concurrency: 2 }
      });
      const cache = tessellationCache.createSession({ signal: controller.signal });
      let sessionDisposed = false;
      const session = { resources, tessellationCache: cache, signal: controller.signal, dispose() {
        if (sessionDisposed) return;
        sessionDisposed = true;
        if (file) {
          const remaining = (activeFiles.get(file) || 0) - 1;
          if (remaining > 0) activeFiles.set(file, remaining); else activeFiles.delete(file);
        }
        controller.abort(); cache.dispose();
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
      tessellationCache?.dispose();
      pendingRefreshes.clear();
      listeners.clear();
    }
  };
  return client;
}

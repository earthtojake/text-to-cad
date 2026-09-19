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

const normalizedFile = (file) => String(file || '').replace(/\\/g, '/').replace(/^\/+/, '');
const entryKey = (entry) => normalizedFile(entry.rootRelativeFile || entry.file);
const matchesFile = (entry, file) => [entry.rootRelativeFile, entry.file].some((value) => normalizedFile(value) === normalizedFile(file));

/**
 * An explicit connection to one served root. Construction never starts requests.
 * @param {import("./types.js").CadClientOptions} options
 * @returns {import("./types.js").CadClient}
 */
export function createCadClient({ origin = '', workspaceId = '', fetch: fetchImpl = globalThis.fetch, pollIntervalMs = 2000, shouldPoll = () => true, resources: resourceProvider } = {}) {
  origin = normalizeViewerOrigin(origin);
  let disposed = false;
  const resourceLifetime = new AbortController();
  const resources = scopeCadResources(resourceProvider || createHttpCadResourceProvider({ origin, fetch: fetchImpl }), resourceLifetime.signal);
  let snapshot = { entries: [], revision: 0, hydrated: false, refreshing: false, error: '', rootId: workspaceId };
  const listeners = new Set();
  const requests = new Set();
  const sessions = new Set();
  let pollTimer = null;
  let refreshSequence = 0;
  let publishedCatalogSequence = 0;
  const entrySequences = new Map();
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
    let incoming = applyViewerOriginToEntries(catalog?.entries, origin);
    if (sequence < publishedCatalogSequence) {
      // Two views can hydrate different files concurrently. A late response
      // cannot replace the newer directory listing, but its requested entry
      // is still useful if no newer response hydrated that same file.
      const selected = file && incoming.find((entry) => matchesFile(entry, file));
      if (!selected || selected.catalogPending || !snapshot.entries.some((entry) => entryKey(entry) === entryKey(selected))
        || sequence < (entrySequences.get(entryKey(selected)) || 0)) return;
      incoming = snapshot.entries.map((entry) => entryKey(entry) === entryKey(selected) ? selected : entry);
    } else publishedCatalogSequence = sequence;
    const previous = new Map(snapshot.entries.map((entry) => [entryKey(entry), entry]));
    const entries = incoming.map((entry) => {
      const key = entryKey(entry);
      const before = previous.get(key);
      // Partial catalogs intentionally carry path-only placeholders for other
      // files. They must not erase a view another request already resolved.
      if (entry.catalogPending && before && !before.catalogPending) return before;
      if (!entry.catalogPending) entrySequences.set(key, Math.max(sequence, entrySequences.get(key) || 0));
      return before && JSON.stringify(before) === JSON.stringify(entry) ? before : entry;
    });
    const presentKeys = new Set(entries.map(entryKey));
    for (const key of entrySequences.keys()) if (!presentKeys.has(key)) entrySequences.delete(key);
    const rootId = workspaceId || catalog?.rootId || snapshot.rootId;
    const changed = entries.length !== snapshot.entries.length || entries.some((entry, index) => entry !== snapshot.entries[index]);
    if (changed || !snapshot.hydrated || snapshot.refreshing || snapshot.error || rootId !== snapshot.rootId) {
      publish({ entries: changed ? entries : snapshot.entries, rootId, hydrated: true, refreshing: false, error: '' });
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
      // Hydrate the files currently displayed, as main's URL-aware poll did.
      // A directory-only poll can otherwise keep returning placeholders forever.
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
    get workspaceId() { return workspaceId || snapshot.rootId; },
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
      const match = (entries) => entries.find((entry) => matchesFile(entry, path));
      let entry = match(snapshot.entries);
      if (!entry || entry.catalogPending) {
        await refresh({ file: path, signal });
        entry = match(snapshot.entries);
      }
      if (signal?.aborted || disposed) throw abortError();
      if (!entry) throw new Error(`CAD file was not found in this workspace: ${path}`);
      if (entry.catalogPending) throw new Error(`CAD file metadata is unavailable: ${path}`);
      return entry;
    },
    async serverInfo({ signal, fresh = false } = {}) {
      if (!server || fresh) {
        const next = await request('/__cad/server', { signal, operation: 'server' });
        if (server && (server.identityToken !== next.identityToken || server.rootId !== next.rootId)) {
          resources.invalidate();
          publish({});
        }
        server = next;
      }
      if (!snapshot.rootId && server?.rootId) publish({ rootId: server.rootId });
      return server;
    },
    requestArtifactStatus(file, { signal } = {}) {
      if (!file) return Promise.reject(new Error('Missing file'));
      return request('/__cad/artifact', { file, signal, timeoutMs: 10_000, operation: 'status' });
    },
    async requestArtifact(file, { force = false, signal } = {}) {
      if (!file) throw new Error('Missing file');
      const payload = await request('/__cad/artifact', {
        file, signal, method: 'POST', operation: 'compile', params: force ? { force: '1' } : {}, headers: { 'x-cadgen-viewer': '1' }
      });
      if (payload?.catalog) publishCatalog(payload.catalog);
      return payload;
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
    observeEditingPreview(file, onUpdate, onError, options) {
      return observeEditingPreview(file, onUpdate, onError, { ...options, client });
    },
    createRenderSession({ file = '' } = {}) {
      if (disposed) throw new Error('This CAD client has been disposed.');
      if (file) activeFiles.set(file, (activeFiles.get(file) || 0) + 1);
      const controller = new AbortController();
      const releases = [retainSurfWorkerPool(), retainGlbMeshWorker(), retainStlMeshWorker()];
      tessellationCache ??= createTessellationCache({
        provider: createHttpTessellationCacheProvider({ origin, headers: { 'x-cadgen-viewer': '1' }, fetch: fetchImpl }),
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

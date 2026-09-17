import { requestViewerJson, ViewerRequestError } from "./request.js";
import { retainSurfWorkerPool } from '../lib/surf/surfWorkerClient.js';
import { retainGlbMeshWorker } from '../lib/render/glbMeshWorkerClient.js';
import { retainStlMeshWorker } from '../lib/render/stlMeshWorkerClient.js';
import { applyViewerOriginToEntries, normalizeViewerOrigin, viewerOriginUrl } from './origin.js';
import { createHttpTessellationCacheProvider, createTessellationCache } from '../lib/surf/tessellationCache.js';

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

/**
 * An explicit connection to one served root. Construction never starts requests.
 * @param {import("./types.js").CadClientOptions} options
 * @returns {import("./types.js").CadClient}
 */
export function createCadClient({ origin = '', workspaceId = '', fetch: fetchImpl = globalThis.fetch, pollIntervalMs = 2000, shouldPoll = () => true } = {}) {
  origin = normalizeViewerOrigin(origin);
  let disposed = false;
  let snapshot = { entries: [], revision: 0, hydrated: false, refreshing: false, error: '', rootId: workspaceId };
  const listeners = new Set();
  const requests = new Set();
  const sessions = new Set();
  let pollTimer = null;
  let refreshSequence = 0;
  let pendingRefresh = null;
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

  function publishCatalog(catalog) {
    const entries = applyViewerOriginToEntries(catalog?.entries, origin);
    const rootId = workspaceId || catalog?.rootId || snapshot.rootId;
    const changed = JSON.stringify(entries) !== JSON.stringify(snapshot.entries);
    if (changed || !snapshot.hydrated || snapshot.refreshing || snapshot.error || rootId !== snapshot.rootId) {
      publish({ entries: changed ? entries : snapshot.entries, rootId, hydrated: true, refreshing: false, error: '' });
    }
  }

  async function refresh({ file = '', signal, markRefreshing = !snapshot.hydrated } = {}) {
    // A file-specific refresh must not inherit a different view's request or cancellation.
    if (!file && !signal && pendingRefresh) return pendingRefresh;
    const sequence = ++refreshSequence;
    if (markRefreshing) publish({ refreshing: true, error: '' });
    const work = (async () => {
      try {
        const catalog = await request('/__cad/catalog', { file, signal, timeoutMs: 10_000, operation: 'catalog' });
        if (sequence === refreshSequence) publishCatalog(catalog);
        return catalog;
      } catch (error) {
        if (!disposed && !signal?.aborted && error?.name !== 'AbortError' && sequence === refreshSequence) {
          publish({ hydrated: true, refreshing: false, error: error instanceof Error ? error.message : String(error) });
        }
        throw error;
      }
    })();
    if (!file && !signal) {
      pendingRefresh = work;
      void work.finally(() => { if (pendingRefresh === work) pendingRefresh = null; }).catch(() => {});
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
      try { await refresh({ markRefreshing: false }); } catch { /* snapshot reports connection failures */ }
    }, pollIntervalMs);
  }

  const client = {
    origin,
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
      const normalized = String(path || '').replace(/\\/g, '/').replace(/^\/+/, '');
      const match = (entries) => entries.find((entry) => [entry.rootRelativeFile, entry.file].some((value) => String(value || '').replace(/\\/g, '/').replace(/^\/+/, '') === normalized));
      let entry = match(snapshot.entries);
      if (!entry) {
        const catalog = await refresh({ file: path, signal });
        entry = match(applyViewerOriginToEntries(catalog.entries, origin));
      }
      if (signal?.aborted || disposed) throw abortError();
      if (!entry) throw new Error(`CAD file was not found in this workspace: ${path}`);
      return entry;
    },
    async serverInfo({ signal, fresh = false } = {}) {
      if (!server || fresh) server = await request('/__cad/server', { signal, operation: 'server' });
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
    createRenderSession() {
      if (disposed) throw new Error('This CAD client has been disposed.');
      const controller = new AbortController();
      const releases = [retainSurfWorkerPool(), retainGlbMeshWorker(), retainStlMeshWorker()];
      const cache = createTessellationCache({
        provider: createHttpTessellationCacheProvider({ origin, headers: { 'x-cadgen-viewer': '1' }, fetch: fetchImpl, signal: controller.signal }),
        writeBack: { deferMs: 1500, concurrency: 2 }
      });
      let sessionDisposed = false;
      const session = { tessellationCache: cache, signal: controller.signal, dispose() {
        if (sessionDisposed) return;
        sessionDisposed = true;
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
      refreshSequence += 1;
      stopPolling();
      for (const request of requests) request.abort();
      requests.clear();
      for (const session of [...sessions]) session.dispose();
      listeners.clear();
    }
  };
  return client;
}

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

  async function request(path, { signal, file = '', params = {}, method = 'GET', headers = {}, timeoutMs = 0 } = {}) {
    if (disposed || signal?.aborted) throw abortError();
    const controller = new AbortController();
    const abort = () => controller.abort();
    let timedOut = false;
    const timeout = timeoutMs > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs) : null;
    signal?.addEventListener('abort', abort, { once: true });
    requests.add(controller);
    try {
      const response = await fetchImpl(cadApiUrl(path, { origin, file, params }), {
        method, headers, signal: controller.signal, cache: 'no-store'
      });
      if (disposed || controller.signal.aborted) throw abortError();
      let payload;
      try { payload = await response.json(); } catch (error) { if (response.ok) throw error; }
      if (disposed || controller.signal.aborted) throw abortError();
      if (!response.ok) throw new Error(payload?.error || payload?.result?.error || payload?.result?.validation?.error?.message || (
        path === '/__cad/catalog' ? `Failed to read CAD catalog: ${response.status} ${response.statusText}` : `CAD request failed: ${response.status} ${response.statusText}`
      ));
      return payload;
    } catch (error) {
      if (timedOut && !disposed && !signal?.aborted) throw new Error(`Timed out loading CAD catalog after ${timeoutMs / 1000}s`);
      throw error;
    } finally {
      if (timeout !== null) clearTimeout(timeout);
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
        const catalog = await request('/__cad/catalog', { file, signal, timeoutMs: 10_000 });
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
    async serverInfo({ signal } = {}) {
      if (!server) server = await request('/__cad/server', { signal });
      if (!snapshot.rootId && server?.rootId) publish({ rootId: server.rootId });
      return server;
    },
    requestDesignOutline(file, { signal } = {}) {
      if (!file) return Promise.reject(new Error('Missing file'));
      return request('/__cad/design-outline', { file, signal });
    },
    requestArtifactStatus(file, { signal } = {}) {
      if (!file) return Promise.reject(new Error('Missing file'));
      return request('/__cad/artifact', { file, signal });
    },
    async requestArtifact(file, { force = false, signal } = {}) {
      if (!file) throw new Error('Missing file');
      const payload = await request('/__cad/artifact', {
        file, signal, method: 'POST', params: force ? { force: '1' } : {}, headers: { 'x-cadgen-viewer': '1' }
      });
      if (payload?.catalog) publishCatalog(payload.catalog);
      return payload;
    },
    createRenderSession() {
      if (disposed) throw new Error('This CAD client has been disposed.');
      const controller = new AbortController();
      const releases = [retainSurfWorkerPool(), retainGlbMeshWorker(), retainStlMeshWorker()];
      const cache = createTessellationCache({
        provider: createHttpTessellationCacheProvider({ origin, headers: { 'x-cadgen-viewer': '1' }, fetch: fetchImpl, signal: controller.signal }),
        writeBack: { deferMs: 1500, concurrency: 2 }
      });
      const session = { tessellationCache: cache, signal: controller.signal, dispose() {
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

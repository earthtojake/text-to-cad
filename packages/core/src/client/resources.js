import { viewerOriginUrl } from './origin.js';
import { resolvePackageAssetUrl } from './assetUrl.js';
import { resolveCadAssetMeshUrl } from '../lib/urdf/meshAssetUrl.js';

let nextProviderId = 1;
const providerIds = new WeakMap();

/** URL caches are scoped to their provider; exact content-addressed meshes keep their own keys. */
export function cadResourceCacheKey(resources, url) {
  if (!resources) return url;
  if (resources.cacheKey) return resources.cacheKey(url);
  if (!providerIds.has(resources)) providerIds.set(resources, nextProviderId++);
  return `resource:${providerIds.get(resources)}:${url}`;
}

function aborted(signal) { signal?.throwIfAborted(); }
function failure(url, response) {
  return Object.assign(new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`), { status: response.status });
}

/** Read bounded bytes before transferring them to a worker. The ticket never owns cached arrays. */
async function responseBytes(response, maxBytes = Infinity) {
  const length = Number(response.headers?.get('content-length'));
  if (Number.isFinite(length) && length > maxBytes) throw new Error('CAD resource exceeds its byte limit');
  if (!Number.isFinite(maxBytes) || !response.body?.getReader) {
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > maxBytes) throw new Error('CAD resource exceeds its byte limit');
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) throw new Error('CAD resource exceeds its byte limit');
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes.buffer;
}

/**
 * Explicit HTTP composition for one root, or a static docs/snapshot consumer.
 * A custom fetch stays on its owning thread; default HTTP keeps worker URL reads.
 * @param {{origin?:string, fetch?:typeof globalThis.fetch, headers?:Record<string,string>, cache?:RequestCache, signal?:AbortSignal}} options
 * @returns {import('./types.js').CadResourceProvider}
 */
export function createHttpCadResourceProvider({ origin = '', fetch: fetchImpl = globalThis.fetch, headers = {}, cache, signal: lifetimeSignal } = {}) {
  const id = nextProviderId++;
  const workerUrlSafe = fetchImpl === globalThis.fetch;
  const requestHeaders = { ...headers };
  const resourceUrl = url => viewerOriginUrl(origin, url);
  let providerOrigin = '';
  try {
    const parsed = new URL(origin || globalThis.location?.origin || globalThis.window?.location?.origin || '');
    if (parsed.origin !== 'null') providerOrigin = parsed.origin;
  } catch { /* A static non-browser caller has no implicit origin. */ }
  const headersFor = url => {
    const resolved = resourceUrl(url);
    if (!providerOrigin) return /^[a-z][a-z0-9+.-]*:|^\/\//i.test(resolved) ? {} : requestHeaders;
    const own = new URL(providerOrigin).origin;
    return new URL(resolved, own).origin === own ? requestHeaders : {};
  };
  async function request(url, { signal, method = 'GET' } = {}) {
    aborted(signal); aborted(lifetimeSignal);
    const combined = signal && lifetimeSignal ? AbortSignal.any([signal, lifetimeSignal]) : signal || lifetimeSignal;
    const response = await fetchImpl(resourceUrl(url), { signal: combined, method, headers: headersFor(url), ...(cache ? { cache } : {}) });
    aborted(combined);
    if (!response.ok) throw failure(url, response);
    return response;
  }
  const provider = {
    get signal() { return lifetimeSignal; },
    cacheKey: url => `http-resource:${id}:${resourceUrl(url)}`,
    async readJson(url, options) { const response = await request(url, options); const value = await response.json(); aborted(options?.signal); aborted(lifetimeSignal); return value; },
    async readText(url, options) { const response = await request(url, options); const value = await response.text(); aborted(options?.signal); aborted(lifetimeSignal); return value; },
    async readBytes(url, options = {}) { const response = await request(url, options); const bytes = await responseBytes(response, options.maxBytes); aborted(options.signal); aborted(lifetimeSignal); return bytes; },
    async byteLength(url, options) {
      const response = await request(url, { ...options, method: 'HEAD' });
      const value = Number(response.headers.get('content-length'));
      return Number.isSafeInteger(value) && value > 0 ? value : null;
    },
    resolveDependency(source, reference, { kind = 'relative' } = {}) {
      if (kind === 'package') {
        const resolved = resolvePackageAssetUrl(source, reference);
        if (resolved) return resourceUrl(resolved);
      }
      if (kind === 'robot' || kind === 'relative') {
        const resolved = resolveCadAssetMeshUrl(reference, resourceUrl(source));
        if (resolved) return resolved;
      }
      const base = new URL(resourceUrl(source), globalThis.window?.location?.href || 'http://cad.local/');
      const resolved = kind === 'robot' && String(reference).startsWith('package://')
        ? new URL(String(reference).slice('package://'.length).replace(/^\/+/, ''), new URL('/', base))
        : new URL(kind === 'package' ? `${String(source).replace(/\/+$/, '')}/${reference}` : reference, base);
      return /^[a-z][a-z0-9+.-]*:/i.test(resourceUrl(source)) || /^(https?:)?\/\//i.test(reference) ? resolved.href : `${resolved.pathname}${resolved.search}`;
    },
    async workerTicket(url, options = {}) {
      aborted(options.signal); aborted(lifetimeSignal);
      return workerUrlSafe
        ? { kind: 'url', url: resourceUrl(url), ...(cache ? { cache } : {}), ...(Object.keys(headersFor(url)).length ? { headers: { ...headersFor(url) } } : {}), ...(options.maxBytes ? { maxBytes: options.maxBytes } : {}) }
        : { kind: 'bytes', bytes: await provider.readBytes(url, options) };
    },
  };
  return provider;
}

/** Worker-side reader: only explicit tickets cross this boundary. */
export async function readCadWorkerTicket(ticket, { signal } = {}) {
  aborted(signal);
  if (ticket?.kind === 'bytes' && ticket.bytes instanceof ArrayBuffer) return ticket.bytes;
  if (ticket?.kind !== 'url' || !ticket.url) throw new TypeError('CAD worker requires a resource ticket');
  const response = await fetch(ticket.url, { signal, headers: ticket.headers, ...(ticket.cache ? { cache: ticket.cache } : {}) });
  if (!response.ok) throw failure(ticket.url, response);
  return responseBytes(response, ticket.maxBytes);
}

/** A workspace borrows a provider but owns cancellation and its cache generation. */
export function scopeCadResources(provider, signal) {
  const id = nextProviderId++;
  let generation = 0;
  let active = new AbortController();
  const generationSignal = () => AbortSignal.any([signal, active.signal, ...(provider.signal ? [provider.signal] : [])]);
  let currentSignal = generationSignal();
  const scoped = {
    get signal() { return currentSignal; },
    cacheKey: url => `workspace-resource:${id}:${generation}:${cadResourceCacheKey(provider, url)}`,
    resolveDependency(...args) { aborted(signal); return provider.resolveDependency(...args); },
    invalidate() { active.abort(); active = new AbortController(); generation += 1; currentSignal = generationSignal(); },
  };
  for (const method of ['readJson', 'readText', 'readBytes', 'byteLength', 'workerTicket']) {
    scoped[method] = async (url, options = {}) => {
      aborted(signal); aborted(options.signal);
      const combined = AbortSignal.any([currentSignal, ...(options.signal ? [options.signal] : [])]);
      const value = await provider[method](url, { ...options, signal: combined });
      aborted(combined);
      return value;
    };
  }
  return scoped;
}

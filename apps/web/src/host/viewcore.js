import { openViewCoreDocument, VIEW_CORE_SYNTHESIZED } from "@cad/core/client";
import { isDocumentId } from "@cad/core/lib/cadRefs.js";

// Where the build puts the view core beside the page (`scripts/viewcoreAssets.mjs`), when it has one to put.
const ASSETS = "/viewcore/";

/**
 * How many view core workers the page's address asks for (`?viewcore=N`, prototype): 0 for none, the engine's
 * reads as ever. `?viewcore=1` is one worker.
 * @param {string} [href]
 */
export function viewCoreWorkers(href = globalThis.location?.href || "") {
  let asked = null;
  try { asked = new URL(href).searchParams.get("viewcore"); } catch { return 0; }
  if (asked === null) return 0;
  const count = Number(asked || 1);
  return Number.isInteger(count) && count > 0 ? Math.min(count, 16) : 0;
}

/**
 * `client` with a model's `.xbf` read in the page by the view core (`workers` Workers) instead of the engine: its
 * envelope and the `.xbf`'s bytes (`<api>/source`) are the engine's, and everything the page reads of the document
 * after is answered by the core (`@cad/core`'s `openViewCoreDocument`). Every other document, and every other
 * method, is the client's own. Where the core is not packaged, or the bytes cannot be had, the engine's read is
 * used, said in the console.
 * @template T
 * @param {T} client
 * @param {{ workers?: number, fetch?: typeof fetch }} [options]
 * @returns {T}
 */
export function withViewCore(client, { workers = 1, fetch: fetchImpl = globalThis.fetch } = {}) {
  let manifest = null;
  const packaged = () => manifest || (manifest = fetchImpl(`${ASSETS}manifest.json`, { cache: "no-store" })
    .then(response => (response.ok && /json/.test(response.headers.get("content-type") || "") ? response.json() : null))
    .catch(() => null));
  const opened = [];
  const timeline = { workers, documents: opened, synthesized: VIEW_CORE_SYNTHESIZED };
  globalThis.__viewcore = timeline;
  const wrapped = Object.create(client);
  wrapped.engineDocument = async (file, options = {}) => {
    const { signal } = options;
    const assets = await packaged();
    if (!assets?.wasm || !assets?.worker) {
      console.warn("viewcore: this build packages no view core; reading the document from the engine.");
      return client.engineDocument(file, options);
    }
    const started = performance.now();
    const envelopeUrl = isDocumentId(file) ? `/api/v1/documents/${encodeURIComponent(file)}` : `/api/v1/documents?path=${encodeURIComponent(file)}`;
    const reply = await fetchImpl(envelopeUrl, { signal, cache: "no-store" });
    const body = reply.ok ? await reply.json() : null;
    const envelope = isDocumentId(file) ? body : body?.documents?.[0];
    if (!envelope || envelope.kind !== "xbf" || typeof envelope.api !== "string") return client.engineDocument(file, options);
    const source = await fetchImpl(`${envelope.api}/source`, { signal });
    if (!source.ok) {
      console.warn(`viewcore: ${envelope.api}/source answered ${source.status}; reading the document from the engine.`);
      return client.engineDocument(file, options);
    }
    const bytes = new Uint8Array(await source.arrayBuffer());
    const fetchedAt = performance.now();
    const served = openViewCoreDocument({
      bytes, url: envelope.api, workerUrl: assets.worker, wasmUrl: assets.wasm, workers,
      document: { id: envelope.id, name: envelope.name, version: envelope.version, path: envelope.id },
      look: assets.look || {}, fallback: fetchImpl,
    });
    opened.push({ file, id: envelope.id, bytes: bytes.byteLength, startedAt: started, sourceAt: fetchedAt, stats: served.fetch.stats });
    signal?.addEventListener("abort", () => served.fetch.dispose(), { once: true });
    return { doc: envelope.id, kind: "xbf", url: envelope.api, fetch: served.fetch, final: true };
  };
  return wrapped;
}

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
  // A document read by the core exports by it too (`openViewCoreDocument`'s `exports`): its STEP, STL, 3MF and GLB are
  // made in the page; every other export, and every other document's, is the client's.
  const served = new Map();
  if (client.exports) {
    const own = (request) => served.get(String(request?.source?.doc || ""));
    const byJob = new Map();
    wrapped.exports = {
      epoch: (signal) => client.exports.epoch(signal),
      async create(request, signal) {
        const held = own(request);
        const job = await (held || client.exports).create(request, signal);
        if (held) byJob.set(job.id, held);
        return job;
      },
      status: (id, sequence, signal) => (byJob.get(id) || client.exports).status(id, sequence, signal),
      fileUrl: (id) => (byJob.get(id) || client.exports).fileUrl(id),
    };
  }
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
    const opening = openViewCoreDocument({
      bytes, url: envelope.api, workerUrl: assets.worker, wasmUrl: assets.wasm, workers,
      document: { id: envelope.id, name: envelope.name, version: envelope.version, path: envelope.id },
      look: assets.look || {}, fallback: fetchImpl, exports: client.exports || null,
    });
    opened.push({ file, id: envelope.id, bytes: bytes.byteLength, startedAt: started, sourceAt: fetchedAt, stats: opening.fetch.stats });
    // Its exports, asked by the document's id or the file's path: the core's (a DXF, the engine's).
    for (const name of new Set([String(envelope.id), String(file)])) served.set(name, opening.exports);
    signal?.addEventListener("abort", () => {
      opening.fetch.dispose();
      opening.exports.dispose();
      for (const name of new Set([String(envelope.id), String(file)])) served.delete(name);
    }, { once: true });
    return { doc: envelope.id, kind: "xbf", url: envelope.api, fetch: opening.fetch, final: true };
  };
  return wrapped;
}

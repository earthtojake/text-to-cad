import { viewerOriginUrl } from './origin.js';

export class ExportRequestError extends Error {
  /** @param {string} message @param {number} status */
  constructor(message, status) { super(message); this.name = 'ExportRequestError'; this.status = status; }
}
/** @param {number} ms @param {AbortSignal} signal @returns {Promise<void>} */
export function exportPause(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}
/** Job transport only. Handing a finished file to the browser's downloads belongs to the host. A job
 * is made by its document's route (`POST /api/v1/documents/<id>/exports`: `documentOf` names the
 * document of the request's `source.doc`, a file's path or a document's id), and read in its own
 * family (`/api/v1/exports`: the session's epoch, a job's state and its file).
 * @param {{ origin?: string, fetch?: typeof globalThis.fetch, documentOf?: (doc: string) => string }} [options]
 * @returns {import('./types.js').ExportService}
 */
export function createExportService({ origin = '', fetch: fetchImpl = globalThis.fetch, documentOf = (doc) => doc } = {}) {
  const url = (path) => viewerOriginUrl(origin, '/api/v1/exports' + path);
  async function response(target, body, signal) {
    const answer = await fetchImpl(target, { signal, cache: 'no-store', ...(body === undefined ? {} : {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-cad-viewer': '1' }, body: JSON.stringify(body),
    }) });
    if (!answer.ok) {
      let message = `Export request failed (${answer.status}).`;
      try { message = (await answer.json()).error || message; } catch { /* retain status */ }
      throw new ExportRequestError(message, answer.status);
    }
    return answer;
  }
  const json = async (target, body, signal) => (await response(target, body, signal)).json();
  return {
    // The session's epoch, which a new request names: a request the page kept across a reload is
    // then refused by a server that has restarted since, never run again by it.
    epoch: async signal => (await json(url(''), undefined, signal)).epoch,
    create: (request, signal) => json(viewerOriginUrl(origin,
      `/api/v1/documents/${encodeURIComponent(documentOf(request.source.doc) || request.source.doc)}/exports`), request, signal),
    status: (id, sequence, signal) => json(url('/' + encodeURIComponent(id) + (sequence === undefined ? '' : `?after=${sequence}&wait=25`)), undefined, signal),
    // A plain same-origin URL: the page's session cookie authenticates it, so no token rides in it.
    fileUrl: id => url('/' + encodeURIComponent(id) + '/file'),
  };
}

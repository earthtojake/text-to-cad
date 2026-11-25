import { cadApiUrl } from './client.js';

/**
 * Prepare a Quick Edit snapshot: small packets inline, larger packets by path, without rendering.
 * `read` fetches a JSON file.
 * @typedef {{ name: string, input: string, views: object[], annotation: object | null, references?: string[] }} PromptFilesRequest
 *   `references`: what the prompt names in the file, a board's selectors, which the packet carries for its snapshot to light.
 * @typedef {{ snapshot: string, inline?: never } | { inline: string, snapshot?: never }} PromptFiles
 * @param {{ origin?: string, fetch?: typeof globalThis.fetch }} [options]
 * `folders` asks the viewer server for the folders a message names files by: the workspace it was started
 * in (`start`: an agent app's, for a CAD app card) and the person's home.
 * @returns {{ create(request: PromptFilesRequest): Promise<PromptFiles>, read(path: string): Promise<Blob>,
 *   folders(): Promise<{ start?: string, home?: string }> }}
 */
export function createHttpPromptFiles({ origin = '', fetch: fetchImpl = globalThis.fetch } = {}) {
  const headers = { 'x-cad-viewer': '1' };
  const answer = async response => {
    const body = await response.json().catch(() => null);
    if (!body?.ok) throw new Error(body?.error || `The prompt's files could not be made (${response.status}).`);
    return body;
  };
  return {
    async create(request) {
      const body = await answer(await fetchImpl(cadApiUrl('/api/v1/local/prompt-files', { origin }), {
        method: 'POST', headers: { ...headers, 'content-type': 'application/json' }, body: JSON.stringify({ ...request, acceptInline: true }),
      }));
      if (typeof body.inline === "string") return { inline: body.inline };
      if (typeof body.snapshot === "string") return { snapshot: body.snapshot };
      throw new Error("The prompt response has neither inline JSON nor a snapshot path.");
    },
    async folders() {
      const response = await fetchImpl(cadApiUrl('/api/v1/server', { origin }), { headers });
      const body = response.ok ? await response.json().catch(() => null) : null;
      const text = value => (typeof value === 'string' && value ? value : undefined);
      return { start: text(body?.start), home: text(body?.home) };
    },
    async read(path) {
      const name = String(path).split(/[\\/]/).pop();
      const response = await fetchImpl(cadApiUrl(`/api/v1/local/prompt-files/${encodeURIComponent(name)}`, { origin }), { headers });
      if (!response.ok) throw new Error(`The prompt file ${name} could not be read (${response.status}).`);
      return response.blob();
    },
  };
}

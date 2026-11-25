import { cadApiUrl } from './client.js';

/**
 * How a Quick Edit's message names the files on the viewer server's computer: `folders` asks the server for the
 * workspace it was last launched in (`start`: an agent app's, for a CAD app card) and the person's home, which the
 * message names each file from (`displayPath`). A Quick Edit's snapshot packet is the page's own
 * (`@cad/core/prompt`'s `snapshotPacket`): nothing is asked of the server for it.
 * @param {{ origin?: string, fetch?: typeof globalThis.fetch }} [options]
 * @returns {{ folders(): Promise<{ start?: string, home?: string }> }}
 */
export function createHttpPromptFiles({ origin = '', fetch: fetchImpl = globalThis.fetch } = {}) {
  return {
    async folders() {
      const response = await fetchImpl(cadApiUrl('/api/v1/server', { origin }), { headers: { 'x-cad-viewer': '1' } });
      const body = response.ok ? await response.json().catch(() => null) : null;
      const text = value => (typeof value === 'string' && value ? value : undefined);
      return { start: text(body?.start), home: text(body?.home) };
    },
  };
}

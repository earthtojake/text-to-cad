import { cadApiUrl } from './client.js';

/**
 * The viewer server's store for a picture a copied prompt names by path (`POST /__cad/sketches`,
 * a Quick Edit's sketch): `save(png, name)` answers the saved file's absolute path. It speaks to
 * the server over `fetch` at `origin` as the CAD client does, whatever carries that fetch.
 * @param {{ origin?: string, fetch?: typeof globalThis.fetch }} [options]
 * @returns {{ save(image: Blob, name: string): Promise<string> }}
 */
export function createHttpAttachmentStore({ origin = '', fetch: fetchImpl = globalThis.fetch } = {}) {
  return {
    async save(image, name) {
      if (image?.type !== 'image/png') throw new Error('A saved picture is a PNG.');
      const response = await fetchImpl(cadApiUrl('/__cad/sketches', { origin, params: { name } }), {
        method: 'POST', headers: { 'content-type': 'image/png', 'x-cadgen-viewer': '1' }, body: image,
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || typeof body?.path !== 'string') throw new Error(body?.error || 'The sketch could not be saved.');
      return body.path;
    },
  };
}

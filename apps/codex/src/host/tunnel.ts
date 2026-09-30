import type { Root, Server } from './server';

/**
 * The origin the CAD client builds its URLs against. The page's own address is the host's
 * sandbox, not a server, so every request URL is absolute on this placeholder and travels as a
 * `cad_http` call; the server reads only its path and query.
 */
export const TUNNEL_ORIGIN = 'http://cad.invalid';

const NULL_BODY = new Set([101, 103, 204, 205, 304]);

export function encodeBase64(bytes: Uint8Array): string {
  const native = (bytes as Uint8Array & { toBase64?: () => string }).toBase64;
  if (typeof native === 'function') return native.call(bytes);
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(binary);
}

export function decodeBase64(text: string): Uint8Array<ArrayBuffer> {
  const native = (Uint8Array as unknown as { fromBase64?: (value: string) => Uint8Array<ArrayBuffer> }).fromBase64;
  if (typeof native === 'function') return native(text);
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

/**
 * A `fetch` over `cad_http`, scoped to one root. It is a distinct function (never a patched
 * `window.fetch`), so the CAD client hands workers bytes rather than URLs they could not reach.
 */
export function createTunnelFetch(server: Pick<Server, 'http'>, root: Pick<Root, 'kind' | 'path'>): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init);
    const method = request.method.toUpperCase();
    const body = method === 'GET' || method === 'HEAD' ? '' : encodeBase64(new Uint8Array(await request.arrayBuffer()));
    const headers: Record<string, string> = {};
    request.headers.forEach((value, name) => { headers[name] = value; });
    let reply;
    try {
      reply = await server.http({ root: { kind: root.kind, path: root.path }, method, url: request.url, headers, body }, { signal: request.signal });
    } catch (error) {
      if (request.signal.aborted) throw request.signal.reason ?? error;
      // What fetch itself throws for a request that never got a response.
      throw new TypeError(error instanceof Error ? error.message : String(error));
    }
    const bytes = method === 'HEAD' || NULL_BODY.has(reply.status) ? null : decodeBase64(reply.body || '');
    return new Response(bytes, { status: reply.status, headers: reply.headers });
  };
}

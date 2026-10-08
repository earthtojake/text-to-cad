import { createCadClient, encodeBase64 } from '@text-to-cad/core/client';
import type { CadClientOptions } from '@text-to-cad/core/client';
import type { HttpReply, Server } from './server';

/**
 * The origin the CAD client builds its URLs against. The page's own address is the host's
 * sandbox, not a server, so every request URL is absolute on this placeholder and travels as a
 * `cad_http` call; the server reads only its path and query.
 */
export const TUNNEL_ORIGIN = 'http://cad.invalid';

const NULL_BODY = new Set([101, 103, 204, 205, 304]);

/**
 * The most body one `cad_http` reply carries (`cadgen/mcp/tunnel.py`'s `MAX_REPLY_BYTES`): the
 * most one batched read asks for, and one part of a longer body. A reply crosses the host's
 * JSON-RPC channel as one message, its body base64, 4/3 of its size, and a host reads its
 * server's messages with a ceiling: the MCP TypeScript SDK's stdio reader stops at 10 MiB unless
 * a host sets more (Claude Code reads 16 MiB, Claude Desktop sets 32 MiB), and a longer message
 * closes the connection, which ends the server and every view on it. 4 MiB is a message under
 * 5.6 MB, and loads as fast as 8 MiB did.
 */
export const TUNNEL_REPLY_MAX_BYTES = 4 * 1024 * 1024;

/**
 * A `cad_http` reply. `encoding: 'gzip'`: the server gzipped a JSON body for the trip
 * (`cadgen/mcp/tunnel.py`), and its headers describe the inflated body.
 */
type TunnelReply = HttpReply & { encoding?: string };

export function decodeBase64(text: string): Uint8Array<ArrayBuffer> {
  const native = (Uint8Array as unknown as { fromBase64?: (value: string) => Uint8Array<ArrayBuffer> }).fromBase64;
  if (typeof native === 'function') return native(text);
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

/** The bytes a gzip stream holds. */
async function gunzip(bytes: Uint8Array<ArrayBuffer>): Promise<Uint8Array<ArrayBuffer>> {
  const source = new ReadableStream<Uint8Array<ArrayBuffer>>({
    start(controller) { controller.enqueue(bytes); controller.close(); },
  });
  return new Uint8Array(await new Response(source.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
}

/** A reply's body as the route wrote it: inflated when it travelled gzipped. */
async function replyBody(reply: TunnelReply): Promise<Uint8Array<ArrayBuffer>> {
  const bytes = decodeBase64(reply.body || '');
  if (reply.encoding === undefined) return bytes;
  if (reply.encoding === 'gzip') return gunzip(bytes);
  throw new TypeError(`cad_http answered in an encoding this page cannot read: ${reply.encoding}`);
}

/** The range a part says it is (`content-range: bytes <first>-<last>/<length>`), or null. */
function partOf(reply: TunnelReply) {
  const match = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(reply.headers['content-range'] || '');
  const [first, last, length] = (match || []).slice(1).map(Number);
  return reply.status === 206 && match && first <= last && last < length ? { first, last, length } : null;
}

/**
 * The whole of a body answered a part at a time: the first part, then a range of at most
 * `TUNNEL_REPLY_MAX_BYTES` at a time as the reader reads on. A part that is not the next part of
 * the same body (its `etag`: the body changed meanwhile) fails the read, as a broken connection
 * would; what the reader verifies of a body (a tessellation's digest) it verifies of the whole.
 */
function wholeOfParts(first: TunnelReply, ask: (range: string) => Promise<TunnelReply>): Response {
  const { length } = partOf(first)!;
  let reply = first;
  let offset = 0;
  const body = new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (offset) reply = await ask(`bytes=${offset}-${Math.min(length, offset + TUNNEL_REPLY_MAX_BYTES) - 1}`);
      const part = partOf(reply);
      const bytes = part && part.first === offset && part.length === length && reply.headers.etag === first.headers.etag
        ? await replyBody(reply) : null;
      if (!bytes || !first.headers.etag || bytes.byteLength !== part!.last - offset + 1) throw new TypeError('cad_http answered a part of another body');
      offset += bytes.byteLength;
      controller.enqueue(bytes);
      if (offset === length) controller.close();
    },
  });
  const headers: Record<string, string> = { ...first.headers, 'content-length': String(length) };
  delete headers['content-range'];
  return new Response(body, { status: 200, headers });
}

/**
 * A `fetch` over `cad_http`. It is a distinct function (never a patched
 * `window.fetch`), so the CAD client hands workers bytes rather than URLs they could not reach.
 * A GET asks for its first `TUNNEL_REPLY_MAX_BYTES` and gets the rest in parts (`wholeOfParts`).
 */
export function createTunnelFetch(server: Pick<Server, 'http'>): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init);
    const method = request.method.toUpperCase();
    const body = method === 'GET' || method === 'HEAD' ? '' : encodeBase64(new Uint8Array(await request.arrayBuffer()));
    const headers: Record<string, string> = {};
    request.headers.forEach((value, name) => { headers[name] = value; });
    const send = async (range?: string): Promise<TunnelReply> => {
      try {
        return await server.http({ method, url: request.url, headers: range ? { ...headers, range } : headers, body }, { signal: request.signal });
      } catch (error) {
        if (request.signal.aborted) throw request.signal.reason ?? error;
        // What fetch itself throws for a request that never got a response.
        throw new TypeError(error instanceof Error ? error.message : String(error));
      }
    };
    const reply = await send(method === 'GET' ? `bytes=0-${TUNNEL_REPLY_MAX_BYTES - 1}` : undefined);
    if (method === 'GET' && partOf(reply)) return wholeOfParts(reply, send);
    const bytes = method === 'HEAD' || NULL_BODY.has(reply.status) ? null : await replyBody(reply);
    return new Response(bytes, { status: reply.status, headers: reply.headers });
  };
}

/** A CAD client whose requests travel over `cad_http` (`tunnel`), its batched reads within `TUNNEL_REPLY_MAX_BYTES`. */
export function createTunnelClient(tunnel: typeof fetch, options: Omit<CadClientOptions, 'origin' | 'fetch' | 'maxBatchBytes'> = {}) {
  return createCadClient({ ...options, origin: TUNNEL_ORIGIN, fetch: tunnel, maxBatchBytes: TUNNEL_REPLY_MAX_BYTES });
}

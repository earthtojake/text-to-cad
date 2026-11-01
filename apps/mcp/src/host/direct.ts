import { TUNNEL_ORIGIN } from './tunnel';
import type { Launch } from './server';

/**
 * The engine reached directly, over HTTP, where the host carries no `tools/call` back to CAD's
 * server (`host/channel.ts`): the launch's `engine` origin, authenticated with the link its
 * `browser` page carries (`?token=`), sent as a Bearer credential -- never a cookie, and never in a
 * URL. The engine answers a link-bearing request from another origin with that origin's CORS
 * allowance and nothing wider (`cad_server/viewer/engine_app.py`); the host's sandbox must also let
 * the page fetch it (the inline resource's `connectDomains` names the engine's origin), or the
 * probe fails and the card links the page instead.
 */
export interface EngineReach { origin: string; link: string; page: string }

/** Where the engine is and the link that opens it, from a launch that carries them; else null. */
export function engineReach(launch: Pick<Launch, 'browser' | 'engine'>): EngineReach | null {
  if (typeof launch.browser !== 'string' || typeof launch.engine !== 'string') return null;
  try {
    const page = new URL(launch.browser);
    const origin = new URL(launch.engine).origin;
    const link = page.searchParams.get('token');
    return link && page.origin === origin ? { origin, link, page: page.href } : null;
  } catch {
    return null;
  }
}

/**
 * A `fetch` with the tunnel's shape: the CAD client still builds its URLs on `TUNNEL_ORIGIN`, and
 * each is sent to the engine's origin instead, path and query unchanged (as the tunnel's server reads
 * only those), so a change of transport changes no caller. The tunnel's own header (`x-cadgen-app`, a session's capability) stays home.
 */
export function createDirectFetch(reach: Pick<EngineReach, 'origin' | 'link'>, fetchImpl: typeof fetch = globalThis.fetch): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init);
    const target = new URL(request.url);
    const method = request.method.toUpperCase();
    const headers = new Headers(request.headers);
    headers.delete('x-cadgen-app');
    headers.set('authorization', `Bearer ${reach.link}`);
    const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer();
    try {
      return await fetchImpl(`${reach.origin}${target.pathname}${target.search}`, {
        method, headers, body, signal: request.signal, credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
      });
    } catch (error) {
      if (request.signal.aborted) throw request.signal.reason ?? error;
      throw new TypeError('The CAD engine could not be reached.');
    }
  };
}

/** How long the probe waits for the engine before the card links its page instead. */
export const PROBE_MS = 5_000;

/**
 * Whether this page can reach the engine directly: one cheap authenticated read (`/api/v1/server`,
 * what the engine is), answered by the CAD Viewer itself. A sandbox's CSP, a host's network rules,
 * an engine gone or a link refused all come out as false.
 */
export async function probeEngine(reach: Pick<EngineReach, 'origin' | 'link'>, fetchImpl: typeof fetch = globalThis.fetch,
  timeoutMs = PROBE_MS): Promise<boolean> {
  const timer = new AbortController();
  const stop = setTimeout(() => timer.abort(), timeoutMs);
  try {
    const response = await createDirectFetch(reach, fetchImpl)(`${TUNNEL_ORIGIN}/api/v1/server`, { signal: timer.signal });
    if (!response.ok) return false;
    const answer = await response.json() as { app?: unknown };
    return answer?.app === 'cad-viewer';
  } catch {
    return false;
  } finally {
    clearTimeout(stop);
  }
}

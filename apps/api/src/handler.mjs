/**
 * api.texttocad.dev: what cadgen talks to -- the version feed its daily check reads, and the receiver
 * cadgen's telemetry is sent to -- served by this site (`app/v1/[...route]/route.ts`; the domain is this
 * project's too). A plain fetch handler over a `store` (PostHog's, posthog.mjs), so the host it runs on and
 * the service behind it can change without a release of anything that calls it (README.md).
 *
 *   GET    /v1/versions        the version feed (versions.mjs) -> 200, the same for everyone
 *   POST   /v1/events          a batch of counts (events.mjs) -> 204
 *   POST   /v1/forget          {install}: forget everything sent under an install id -> 204
 *   GET    /v1/health          -> 200, or 503 naming a missing setting (posthog.mjs: SETTINGS)
 *                              or PostHog's status when it will not take the project's keys
 *
 * It keeps no IP address and passes on nothing the batch does not name. The one thing it adds is the
 * country the host places the request in, on each of the batch's events: never the address it came from,
 * nor anything finer.
 */
import { Invalid, isUuid, MAX_BYTES, rowsOf } from './events.mjs';

const COUNTRY = /^[A-Z]{2}$/; // ISO 3166-1 alpha-2, as the host gives it; anything else is no country
const JSON_TYPE = /^application\/json\s*(?:;|$)/i; // a parameter, such as `; charset=utf-8`, is still JSON

// No CORS headers, so no page can read a reply. A page can still make its visitors' browsers post here
// (a form, `sendBeacon`, a no-cors fetch): `handle` refuses every POST a browser sends.
const reply = (status, body, cache = 'no-store') => new Response(body === undefined ? null : JSON.stringify(body), {
  status,
  headers: { 'cache-control': cache, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
});

// An error by its code and kind only: a service's message can quote what it was sent, an install id among
// them, and the host's logs keep each line beside the caller's IP address.
const codeOf = error => error?.code ?? error?.name ?? 'error';

async function json(request) {
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BYTES) throw new Invalid('the batch is too large');
  try { return JSON.parse(text); } catch { throw new Invalid('the body is not JSON'); }
}

/**
 * @param {Request} request
 * @param {{ insert(rows: object[], context: { country: string | null }): Promise<void>, forget(id: string): Promise<void>,
 *   ready(): Promise<void> }} store `ready`: throws when the service will not take a batch (health asks).
 * @param {{ missing?: string[], country?: string | null, versions?: object }} [options] `missing`: settings the host
 *   lacks, by name (health says so). `country`: where the host places the request, from its IP address.
 *   `versions`: the version feed (versions.mjs).
 */
export async function handle(request, store, { missing = [], country, versions } = {}) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace(/\/+$/, '');
  try {
    // Unhealthy without its settings, or with a service that will not take its keys: a deploy's check fails
    // rather than shipping an API that drops every batch or cannot delete what an opt-out asks it to. The
    // service's answer by its code alone.
    // One feed for everyone, never a reply to anything a request says: the edge keeps it until the next
    // deploy, which is the next release. It asks no service, so it answers even when telemetry cannot.
    if (path === '/v1/versions' && request.method === 'GET' && versions) {
      return reply(200, versions, 'public, s-maxage=86400');
    }
    if (path === '/v1/health' && request.method === 'GET') {
      if (missing.length) return reply(503, { ok: false, missing });
      try {
        await store.ready();
      } catch (error) {
        return reply(503, { ok: false, error: codeOf(error) });
      }
      return reply(200, { ok: true });
    }
    // No browser posts here. cadgen posts from Python's urllib, which sends no Origin header, while a
    // browser sends one with every POST, a form's, `sendBeacon`'s and a no-cors fetch's included. And only
    // JSON is read, which a page can post to another site only after a CORS preflight nothing here approves.
    if (request.method === 'POST') {
      if (request.headers.has('origin')) return reply(403, { error: 'not from a browser' });
      if (!JSON_TYPE.test(request.headers.get('content-type') ?? '')) return reply(415, { error: 'the body must be application/json' });
    }
    if (path === '/v1/events' && request.method === 'POST') {
      const rows = rowsOf(await json(request));
      await store.insert(rows, { country: COUNTRY.test(country ?? '') ? country : null });
      return reply(204);
    }
    // The id rides in the body, never the path: the host's request logs keep each path beside the
    // caller's IP address, and must never pair the two.
    if (path === '/v1/forget' && request.method === 'POST') {
      const { install } = await json(request) ?? {};
      if (!isUuid(install)) return reply(400, { error: 'not an install id' });
      await store.forget(install);
      return reply(204);
    }
    return reply(404, { error: 'not found' });
  } catch (error) {
    if (error instanceof Invalid) return reply(400, { error: error.message });
    console.error('telemetry request failed:', codeOf(error));
    return reply(500, { error: 'internal error' });
  }
}

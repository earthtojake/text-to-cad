/**
 * api.texttocad.dev: what cadgen talks to -- the version feed its daily check reads, and the receiver
 * cadgen's telemetry is sent to -- served by this project's one function (`api/v1.js`, which vercel.json
 * sends every /v1 path to). A plain fetch handler over a `store` (PostHog's, posthog.mjs), so the host it runs on and
 * the service behind it can change without a release of anything that calls it (README.md).
 *
 *   GET    /v1/versions        the version feed, PyPI's latest (versions.mjs) -> 200, the same for everyone,
 *                              or 503 while PyPI cannot be read and nothing has been
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
const FEED_CACHE = 'public, s-maxage=3600, stale-while-revalidate=86400, stale-if-error=604800';

// No CORS headers, so no page can read a reply. A page can still make its visitors' browsers post here
// (a form, `sendBeacon`, a no-cors fetch): `handle` refuses every POST a browser sends.
const reply = (status, body, cache = 'no-store') => new Response(body === undefined ? null : JSON.stringify(body), {
  status,
  headers: { 'cache-control': cache, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
});

// An error by its code or its name only: a service's message can quote what it was sent, an install id among
// them, and the host's logs keep each line beside the caller's IP address. Only a string code counts:
// `AbortSignal.timeout` rejects with a `TimeoutError` whose legacy numeric `code` is 23, which reads as nothing.
const codeOf = error => (typeof error?.code === 'string' && error.code) || (typeof error?.name === 'string' && error.name) || 'error';

// A refused request is logged, because the host's per-status counts are not ours to read: every released
// client is accepted, so a 400 is a garbage request or a bug that is losing a real person's counts. The
// line names a reason and nothing a request carried. `Invalid` messages name a field's path (`events[2].count`),
// a vocabulary or a rule, never the value that broke it -- except an unknown field, which names the caller's
// own key: kept only when it is a plain name (what a newer client adds), else left out.
const PLAIN_NAME = /^[a-z][a-z_]{0,31}$/;
const KEPT_MESSAGE = /^[A-Za-z0-9_.,:'\[\] -]{1,200}$/;
export function reasonOf(message) {
  const reason = String(message).replace(/\bunknown field (.*)$/s, (_, key) => (PLAIN_NAME.test(key) ? `unknown field ${key}` : 'unknown field'));
  return KEPT_MESSAGE.test(reason) ? reason : 'invalid';
}
// The release that sent it, when it says so as a release does (`0.7.17`): a version nothing else could be.
const RELEASE = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;
const senderOf = batch => {
  const parts = [];
  if (Number.isInteger(batch?.schema) && batch.schema >= 0 && batch.schema < 100) parts.push(`schema ${batch.schema}`);
  if (typeof batch?.version === 'string' && RELEASE.test(batch.version)) parts.push(`cadgen ${batch.version}`);
  return parts.length ? ` (${parts.join(', ')})` : '';
};
// Which endpoint, by a name of ours: a path is the caller's to choose.
const ENDPOINTS = new Set(['/v1/events', '/v1/forget']);
const refuse = (status, path, reason, batch) => {
  console.warn(`telemetry ${ENDPOINTS.has(path) ? path : 'request'} refused ${status}: ${reason}${senderOf(batch)}`);
  return reply(status, { error: reason });
};

async function json(request) {
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BYTES) throw new Invalid('the batch is too large');
  try { return JSON.parse(text); } catch { throw new Invalid('the body is not JSON'); }
}

/**
 * @param {Request} request
 * @param {{ insert(rows: object[], context: { country: string | null }): Promise<void>, forget(id: string): Promise<void>,
 *   ready(): Promise<void> }} store `ready`: throws when the service will not take a batch (health asks).
 * @param {{ missing?: string[], country?: string | null, versions?: () => Promise<object | null> }} [options] `missing`: settings the host
 *   lacks, by name (health says so). `country`: where the host places the request, from its IP address.
 *   `versions`: the version feed (versions.mjs).
 */
export async function handle(request, store, { missing = [], country, versions } = {}) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace(/\/+$/, '');
  let batch; // what /v1/events parsed, for the line a refusal logs
  try {
    // Unhealthy without its settings, or with a service that will not take its keys: a deploy's check fails
    // rather than shipping an API that drops every batch or cannot delete what an opt-out asks it to. The
    // service's answer by its code alone.
    // One feed for everyone, never a reply to anything a request says: PyPI's, which the edge keeps an hour
    // and serves on while PyPI or the function fails. It asks no telemetry service, so it answers even when
    // telemetry cannot. With no feed at all, a 503 the edge keeps nowhere.
    if (path === '/v1/versions' && request.method === 'GET' && versions) {
      const feed = await versions();
      return feed ? reply(200, feed, FEED_CACHE) : reply(503, { error: 'no version feed' });
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
      if (request.headers.has('origin')) return refuse(403, path, 'not from a browser');
      if (!JSON_TYPE.test(request.headers.get('content-type') ?? '')) return refuse(415, path, 'the body must be application/json');
    }
    if (path === '/v1/events' && request.method === 'POST') {
      batch = await json(request);
      const rows = rowsOf(batch);
      await store.insert(rows, { country: COUNTRY.test(country ?? '') ? country : null });
      return reply(204);
    }
    // The id rides in the body, never the path: the host's request logs keep each path beside the
    // caller's IP address, and must never pair the two.
    if (path === '/v1/forget' && request.method === 'POST') {
      const { install } = await json(request) ?? {};
      if (!isUuid(install)) return refuse(400, path, 'not an install id');
      await store.forget(install);
      return reply(204);
    }
    return reply(404, { error: 'not found' });
  } catch (error) {
    if (error instanceof Invalid) return refuse(400, path, reasonOf(error.message), batch);
    console.error('telemetry request failed:', codeOf(error));
    return reply(500, { error: 'internal error' });
  }
}

/**
 * api.texttocad.dev: what text-to-cad talks to -- the version feed its hourly check reads, and the receiver
 * text-to-cad's telemetry is sent to -- served by this project's one function (`api/v1.js`, which vercel.json
 * sends every /v1 path to). A plain fetch handler over a `store` (PostHog's, posthog.mjs), so the host it runs on and
 * the service behind it can change without a release of anything that calls it (README.md).
 *
 *   GET    /v1/releases        the version feed, PyPI's latest and the latest of each major (versions.mjs) ->
 *                              200, the same for everyone, or 503 while PyPI cannot be read and nothing has been
 *   GET    /v1/versions        the frozen feed of 0.7.12 to 0.11.11: the latest below 0.12.0, likewise
 *   POST   /v1/events          a batch of counts (events.mjs) -> 204, or 503 for a schema newer than this
 *                              receiver reads (`Later`), which the sender keeps and sends again
 *   POST   /v1/forget          {install}: forget everything sent under an install id -> 204, or 429 past
 *                              the limit per address and per install id (limit.mjs)
 *   POST   /v1/install         one report of where a run of the install command failed, with no working cad
 *                              to count it (install.mjs) -> 204, or 429 past the limit per address
 *   GET    /v1/health          -> 200, or 503 naming a missing setting (posthog.mjs: SETTINGS)
 *                              or PostHog's status when it will not take the project's keys
 *
 * It keeps no IP address and passes on nothing the batch does not name. The one thing it adds is the
 * country the host places the request in, on each of the batch's events and on a report of a failed install:
 * never the address it came from, nor anything finer.
 */
import { Invalid, isUuid, Later, MAX_BYTES, rowsOf } from './events.mjs';
import { MAX_REPORT_BYTES, reportOf } from './install.mjs';
import { withoutNoise } from './noise.mjs';

const COUNTRY = /^[A-Z]{2}$/; // ISO 3166-1 alpha-2, as the host gives it; anything else is no country
const JSON_TYPE = /^application\/json\s*(?:;|$)/i; // a parameter, such as `; charset=utf-8`, is still JSON
// The feed is the brake on a release: a hold, or a release's hour coming to an end, reaches the edge within six
// minutes of the function knowing it (five fresh, one more served stale while it refreshes). A failing PyPI or
// function never blanks it: the edge serves the last answer on for a week.
const FEED_CACHE = 'public, s-maxage=300, stale-while-revalidate=60, stale-if-error=604800';
const LATER_SECONDS = 3600; // when a sender may try a schema this receiver does not read yet again

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
  if (typeof batch?.version === 'string' && RELEASE.test(batch.version)) parts.push(`release ${batch.version}`);
  return parts.length ? ` (${parts.join(', ')})` : '';
};
// Which endpoint, by a name of ours: a path is the caller's to choose.
const ENDPOINTS = new Set(['/v1/events', '/v1/forget', '/v1/install']);
const refuse = (status, path, reason, batch) => {
  console.warn(`telemetry ${ENDPOINTS.has(path) ? path : 'request'} refused ${status}: ${reason}${senderOf(batch)}`);
  return reply(status, { error: reason });
};

async function json(request, most = MAX_BYTES, what = 'batch') {
  const text = await request.text();
  if (new TextEncoder().encode(text).length > most) throw new Invalid(`the ${what} is too large`);
  try { return JSON.parse(text); } catch { throw new Invalid('the body is not JSON'); }
}

// One more request under `key`, or the 429 that refuses it and says when to ask again: nothing is queued.
function limited(limiter, key, path) {
  const taken = limiter.take(key);
  if (taken.ok) return null;
  const refused = refuse(429, path, 'too many requests');
  refused.headers.set('retry-after', String(taken.retryAfter));
  return refused;
}

/**
 * @param {Request} request
 * @param {{ insert(rows: object[], context: { country: string | null }): Promise<void>,
 *   report(report: object, context: { country: string | null }): Promise<void>, forget(id: string): Promise<void>,
 *   ready(): Promise<void> }} store `report`: takes one report of a failed install. `ready`: throws when the service
 *   will not take a batch (health asks).
 * @param {{ missing?: string[], country?: string | null, versions?: () => Promise<object | null>,
 *   releases?: () => Promise<object | null> }} [options] `missing`: settings the host
 *   lacks, by name (health says so). `country`: where the host places the request, from its IP address.
 *   `releases` and `versions`: the version feed's two addresses (versions.mjs). `limiter`: how often one caller may
 *   ask to forget (limit.mjs), by `client`, the address the host says the request came from, and by install id.
 *   `installLimiter`: how often one `client` may report a failed install.
 */
export async function handle(request, store, { missing = [], country, versions, releases, limiter, installLimiter, client } = {}) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace(/\/+$/, '');
  const placed = COUNTRY.test(country ?? '') ? country : null;
  let batch; // what /v1/events parsed, for the line a refusal logs
  try {
    // Unhealthy without its settings, or with a service that will not take its keys: a deploy's check fails
    // rather than shipping an API that drops every batch or cannot delete what an opt-out asks it to. The
    // service's answer by its code alone.
    // One feed for everyone at each address, never a reply to anything a request says: PyPI's, which the edge
    // keeps five minutes and serves on while PyPI or the function fails. It asks no telemetry service, so it
    // answers even when telemetry cannot. With no feed at all, a 503 the edge keeps nowhere.
    const feedOf = path === '/v1/releases' ? releases : path === '/v1/versions' ? versions : undefined;
    if (feedOf && request.method === 'GET') {
      const feed = await feedOf();
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
    // No browser posts here. text-to-cad posts from Python's urllib, and its install command from curl, wget or
    // PowerShell too, none of which sends an Origin header, while a browser sends one with every POST, a form's,
    // `sendBeacon`'s and a no-cors fetch's included. And only JSON is read, which a page can post to another site
    // only after a CORS preflight nothing here approves.
    if (request.method === 'POST') {
      if (request.headers.has('origin')) return refuse(403, path, 'not from a browser');
      if (!JSON_TYPE.test(request.headers.get('content-type') ?? '')) return refuse(415, path, 'the body must be application/json');
    }
    if (path === '/v1/events' && request.method === 'POST') {
      batch = await json(request);
      // Crashes that are never text-to-cad's bug go no further (noise.mjs), counted in one line by name.
      const { rows, dropped } = withoutNoise(rowsOf(batch));
      if (dropped.size) console.info(`telemetry dropped ${[...dropped].map(([name, n]) => `${name} ${n}`).join(', ')}${senderOf(batch)}`);
      if (rows.length) await store.insert(rows, { country: placed });
      return reply(204);
    }
    // Where a run of the install command failed, from a computer with no working cad to count it: one report, under
    // an id made for that run alone, so nothing here is kept under an id that lasts and there is nothing to forget.
    // Open to anyone, so one address may report only so often (limit.mjs): a run reports at most once.
    if (path === '/v1/install' && request.method === 'POST') {
      const refused = installLimiter && client ? limited(installLimiter, `address ${client}`, path) : null;
      if (refused) return refused;
      await store.report(reportOf(await json(request, MAX_REPORT_BYTES, 'report')), { country: placed });
      return reply(204);
    }
    // The id rides in the body, never the path: the host's request logs keep each path beside the
    // caller's IP address, and must never pair the two.
    // Each deletion spends the service's personal key, so one caller -- an address, or an install id from
    // anywhere -- may ask only so often (limit.mjs): beyond that, a 429 saying when to ask again, which a
    // client takes as a deletion it still owes.
    if (path === '/v1/forget' && request.method === 'POST') {
      if (limiter && client) {
        const refused = limited(limiter, `address ${client}`, path);
        if (refused) return refused;
      }
      const { install } = await json(request) ?? {};
      if (!isUuid(install)) return refuse(400, path, 'not an install id');
      if (limiter) {
        const refused = limited(limiter, `install ${install.toLowerCase()}`, path);
        if (refused) return refused;
      }
      await store.forget(install);
      return reply(204);
    }
    return reply(404, { error: 'not found' });
  } catch (error) {
    if (error instanceof Invalid) return refuse(400, path, reasonOf(error.message), batch);
    // A newer release's schema, before this receiver reads it: kept by the sender, never lost.
    if (error instanceof Later) {
      console.warn(`telemetry ${path} deferred 503: a schema newer than this receiver reads${senderOf(batch)}`);
      const later = reply(503, { error: 'schema not read yet' });
      later.headers.set('retry-after', String(LATER_SECONDS));
      return later;
    }
    console.error('telemetry request failed:', codeOf(error));
    return reply(500, { error: 'internal error' });
  }
}

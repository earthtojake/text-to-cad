/**
 * api.texttocad.dev: what cadgen talks to -- the version feed its daily check reads, and the receiver
 * CAD's anonymous analytics are sent to -- served by this site (`app/v1/[...route]/route.ts`; the
 * domain is this project's too). A plain fetch handler over a `store`, so the host it runs on and the
 * database behind it can change without a release of anything that calls it (README.md).
 *
 *   GET    /v1/versions        the version feed (versions.mjs) -> 200, the same for everyone
 *   POST   /v1/events          a batch of counts (events.mjs) -> 204
 *   POST   /v1/forget          {install}: forget everything sent under an install id -> 204
 *   GET    /v1/prune           the daily cron: drop rows past retention (CRON_SECRET) -> 200
 *   GET    /v1/health          -> 200, or 503 naming a missing setting (DATABASE_URL, CRON_SECRET)
 *                              or the database's error code when it cannot take a batch
 *
 * It stores no IP address and nothing the batch does not name; each row's one time is when it
 * arrived (`received_at`). The one thing it adds is where installs are, as totals only: the
 * country the host places the request in counts toward that country's installs this week and
 * this month, and is kept nowhere else.
 */
import { Invalid, isUuid, MAX_BYTES, rowsOf } from './events.mjs';

export const RETENTION_DAYS = 395; // thirteen months: a year compared with the one before

const COUNTRY = /^[A-Z]{2}$/; // ISO 3166-1 alpha-2, as the host gives it
const NO_COUNTRY = 'ZZ'; // where the host could not tell (CLDR's unknown region): totals still add up to the installs
const PERIODS = ['week', 'month'];
const JSON_TYPE = /^application\/json\s*(?:;|$)/i; // a parameter, such as `; charset=utf-8`, is still JSON

// No CORS headers, so no page can read a reply. A page can still make its visitors' browsers post here
// (a form, `sendBeacon`, a no-cors fetch): `handle` refuses every POST a browser sends.
const reply = (status, body, cache = 'no-store') => new Response(body === undefined ? null : JSON.stringify(body), {
  status,
  headers: { 'cache-control': cache, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
});

// An error by its code and kind only: a database error's message can quote a row's values, an install id
// among them, and the host's logs keep each line beside the caller's IP address.
const codeOf = error => error?.code ?? error?.name ?? 'error';

// The country totals are a side count: their failure never costs a batch, and is logged by its code alone.
async function quietly(work, fallback) {
  try {
    return await work();
  } catch (error) {
    console.error('analytics country totals failed:', codeOf(error));
    return fallback;
  }
}

async function json(request) {
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BYTES) throw new Invalid('the batch is too large');
  try { return JSON.parse(text); } catch { throw new Invalid('the body is not JSON'); }
}

/**
 * @param {Request} request
 * @param {{ insert(rows: object[]): Promise<void>, seen(id: string): Promise<{ week: boolean, month: boolean }>,
 *   tally(country: string, periods: string[]): Promise<void>, forget(id: string): Promise<void>, prune(days: number): Promise<number>,
 *   ready(): Promise<void> }} store `ready`: throws when the database cannot take a batch (health asks).
 * @param {{ cronSecret?: string, missing?: string[], country?: string | null, versions?: object }} [options] `missing`:
 *   settings the host lacks, by name (health says so). `country`: where the host places the request, from its IP
 *   address. `versions`: the version feed (versions.mjs).
 */
export async function handle(request, store, { cronSecret, missing = [], country, versions } = {}) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace(/\/+$/, '');
  try {
    // Unhealthy without its settings, or with a database that cannot take a batch (unreachable, or a schema
    // change that schema.sql was not re-run for): a deploy's check fails rather than shipping an API that
    // drops every batch or never prunes what the privacy policy says it deletes. The database's error by its
    // code alone.
    // One feed for everyone, never a reply to anything a request says: the edge keeps it until the next
    // deploy, which is the next release. It reads no database, so it answers even
    // when the analytics cannot.
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
      // Each install counts once a week and once a month, where its first batch of the period came
      // from. Whether this is that batch is asked before the batch is stored; the totals grow after,
      // in their own statement, so nothing pairs an install with a country. Two first batches at the
      // same instant (both apps of one install) can count it twice.
      const due = await quietly(async () => {
        const seen = await store.seen(rows[0].install_id);
        return PERIODS.filter(period => !seen[period]);
      }, []);
      await store.insert(rows);
      if (due.length) await quietly(() => store.tally(COUNTRY.test(country ?? '') ? country : NO_COUNTRY, due));
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
    if (path === '/v1/prune' && request.method === 'GET') {
      if (!cronSecret || request.headers.get('authorization') !== `Bearer ${cronSecret}`) return reply(401, { error: 'unauthorized' });
      return reply(200, { deleted: await store.prune(RETENTION_DAYS) });
    }
    return reply(404, { error: 'not found' });
  } catch (error) {
    if (error instanceof Invalid) return reply(400, { error: error.message });
    console.error('analytics request failed:', codeOf(error));
    return reply(500, { error: 'internal error' });
  }
}

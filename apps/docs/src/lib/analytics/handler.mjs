/**
 * api.texttocad.dev: the receiver CAD's anonymous analytics are sent to, served by this site
 * (`app/v1/[...route]/route.ts`; the domain is this project's too). A plain fetch handler over a
 * `store`, so the host it runs on and the database behind it can change without a release of
 * anything that calls it (README.md).
 *
 *   POST   /v1/events          a batch of counts (src/events.mjs) -> 204
 *   POST   /v1/forget          {install}: forget everything sent under an install id -> 204
 *   GET    /v1/prune           the daily cron: drop rows past retention (CRON_SECRET) -> 200
 *   GET    /v1/health          -> 200, or 503 naming a missing setting (DATABASE_URL, CRON_SECRET)
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

// No CORS: cadgen calls from Python, never a browser, and no web page may make its visitors' browsers
// post here.
const reply = (status, body) => new Response(body === undefined ? null : JSON.stringify(body), {
  status,
  headers: { 'cache-control': 'no-store', ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
});

// The country totals are a side count: their failure never costs a batch, and is logged by its code alone.
async function quietly(work, fallback) {
  try {
    return await work();
  } catch (error) {
    console.error('analytics country totals failed:', error?.code ?? error?.name ?? 'error');
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
 *   tally(country: string, periods: string[]): Promise<void>, forget(id: string): Promise<void>, prune(days: number): Promise<number> }} store
 * @param {{ cronSecret?: string, missing?: string[], country?: string | null }} [options] `missing`: settings the host
 *   lacks, by name (health says so). `country`: where the host places the request, from its IP address.
 */
export async function handle(request, store, { cronSecret, missing = [], country } = {}) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace(/^\/api(?=\/|$)/, '').replace(/\/+$/, '');
  try {
    // Unhealthy without its settings: a deploy's check fails rather than shipping an API that drops every batch
    // or never prunes what the privacy policy says it deletes.
    if (path === '/v1/health' && request.method === 'GET') return missing.length ? reply(503, { ok: false, missing }) : reply(200, { ok: true });
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
    // Its code and kind only: a database error's detail can quote a row's values, an install id among them,
    // and the host's logs keep each line beside the caller's IP address.
    console.error('analytics request failed:', error?.code ?? error?.name ?? 'error');
    return reply(500, { error: 'internal error' });
  }
}

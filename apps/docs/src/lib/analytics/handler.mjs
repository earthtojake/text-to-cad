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
 * It stores no IP address, no request header and nothing the batch does not name; each row's one
 * time is when it arrived (`received_at`).
 */
import { Invalid, isUuid, MAX_BYTES, rowsOf } from './events.mjs';

export const RETENTION_DAYS = 395; // thirteen months: a year compared with the one before

// No CORS: cadgen calls from Python, never a browser, and no web page may make its visitors' browsers
// post here.
const reply = (status, body) => new Response(body === undefined ? null : JSON.stringify(body), {
  status,
  headers: { 'cache-control': 'no-store', ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
});

async function json(request) {
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BYTES) throw new Invalid('the batch is too large');
  try { return JSON.parse(text); } catch { throw new Invalid('the body is not JSON'); }
}

/** @param {Request} request @param {{ insert(rows: object[]): Promise<void>, forget(id: string): Promise<void>, prune(days: number): Promise<number> }} store */
export async function handle(request, store, { cronSecret, missing = [] } = {}) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace(/^\/api(?=\/|$)/, '').replace(/\/+$/, '');
  try {
    // Unhealthy without its settings: a deploy's check fails rather than shipping an API that drops every batch
    // or never prunes what the privacy policy says it deletes.
    if (path === '/v1/health' && request.method === 'GET') return missing.length ? reply(503, { ok: false, missing }) : reply(200, { ok: true });
    if (path === '/v1/events' && request.method === 'POST') {
      await store.insert(rowsOf(await json(request)));
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

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { handle, RETENTION_DAYS } from './handler.mjs';
import { versions } from './versions.mjs';

const INSTALL = '8c347ec3-1342-4db5-a19a-491cbc8c59be';
const SESSION = '0b1e6f1a-6a52-4c39-9d43-2f5e0f0b9d11';
// What cadgen/analytics.py sends.
const BATCH = {
  schema: 2, install: INSTALL, session: SESSION, version: '0.7.6', channel: 'claude-directory', platform: 'darwin', arch: 'arm64',
  client: { name: 'codex-mcp-client', version: '0.159.0' }, presentation: 'tabs',
  events: [
    { name: 'tool', tool: 'cad_show', calls: 3, errors: 1 },
    { name: 'view', calls: 7 },
    { name: 'file', file: '3f9a1c0be47d2a55', kind: 'step' },
  ],
};

// A store in memory, all in one week: an install has been seen this week and month once it has rows.
function memory() {
  const rows = [];
  const tallies = [];
  return {
    rows,
    tallies,
    async insert(batch) { rows.push(...batch); },
    async seen(id) { const any = rows.some(row => row.install_id === id); return { week: any, month: any }; },
    async tally(country, periods) { tallies.push([country, ...periods]); },
    async forget(id) { for (let i = rows.length - 1; i >= 0; i -= 1) if (rows[i].install_id === id) rows.splice(i, 1); },
    async prune(days) { this.pruned = days; return 0; },
    async ready() {},
  };
}
const send = (store, method, path, body, headers = {}, country = 'DE') => handle(new Request(`https://api.texttocad.dev${path}`, {
  method, headers: { 'content-type': 'application/json', ...headers }, body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
}), store, { cronSecret: 'secret', country });

test('a batch becomes one row per event, carrying its context and nothing else', async () => {
  const store = memory();
  const reply = await send(store, 'POST', '/v1/events', BATCH);
  assert.equal(reply.status, 204);
  // cadgen calls from Python: no web page may make its visitors' browsers post here.
  assert.equal(reply.headers.get('access-control-allow-origin'), null);
  assert.deepEqual(store.rows.map(row => [row.event, row.tool, row.file, row.kind, row.calls, row.errors]), [
    ['tool', 'cad_show', null, null, 3, 1],
    ['view', null, null, null, 7, 0],
    ['file', null, '3f9a1c0be47d2a55', 'step', 1, 0],
  ]);
  assert.deepEqual(Object.keys(store.rows[0]).sort(), ['arch', 'calls', 'channel', 'client', 'client_version', 'errors', 'event', 'file', 'install_id', 'kind', 'platform', 'presentation', 'session_id', 'tool', 'version']);
});

test('where installs are is kept as totals: each counts once a week and a month, never beside its rows', async () => {
  const store = memory();
  await send(store, 'POST', '/v1/events', BATCH);
  await send(store, 'POST', '/v1/events', BATCH); // the same install again: already counted
  const other = { ...BATCH, install: '5d7a3d6e-91c2-4f0e-8b7a-0f6c1e2d3a4b' };
  await send(store, 'POST', '/v1/events', other, {}, 'not a country'); // the host could not tell
  assert.deepEqual(store.tallies, [['DE', 'week', 'month'], ['ZZ', 'week', 'month']]);
  assert.ok(store.rows.every(row => !('country' in row)));
  // A side count: when the totals fail, the batch is still stored.
  const broken = { ...memory(), async tally() { throw Object.assign(new Error('relation "countries" does not exist'), { code: '42P01' }); } };
  assert.equal((await send(broken, 'POST', '/v1/events', BATCH)).status, 204);
  assert.equal(broken.rows.length, BATCH.events.length);
});

test('anything outside the contract is refused and stores nothing', async () => {
  const store = memory();
  for (const bad of [
    { ...BATCH, path: '/Users/someone/secret.step' },
    { ...BATCH, install: 'someone@example.com' },
    { ...BATCH, events: [{ name: 'tool', tool: '/Users/someone/secret.step', calls: 1 }] },
    { ...BATCH, events: [{ name: 'tool', tool: 'cad_show', calls: 1, path: 'secret.step' }] },
    { ...BATCH, events: [{ name: 'file', file: '/Users/someone/secret.step', kind: 'step' }] },
    { ...BATCH, events: [{ name: 'file', file: '3f9a1c0be47d2a55', kind: 'step', name2: 'secret.step' }] },
    { ...BATCH, events: [{ name: 'file', file: '3f9a1c0be47d2a55', kind: 'docx' }] },
    { ...BATCH, events: [{ name: 'view', calls: 0 }] },
    { ...BATCH, events: [{ name: 'session_start' }] },
    { ...BATCH, client: { name: 'Café' } },
    { ...BATCH, client: { name: 'a name with spaces and a story' } },
    { ...BATCH, client: { ...BATCH.client, path: 'secret.step' } },
    { ...BATCH, events: [] },
    { ...BATCH, events: [...BATCH.events, BATCH.events[0]] }, // the same tool twice
    { ...BATCH, events: [...BATCH.events, BATCH.events[1]] }, // a second view
    { ...BATCH, events: [...BATCH.events, BATCH.events[2]] }, // the same file twice
    { ...BATCH, events: [{ name: 'tool', tool: 'cad_show', calls: 1, errors: null }] },
    { ...BATCH, channel: 'store' },
    { ...BATCH, channel: 'github' }, // a channel no plugin names any more
    { ...BATCH, schema: 1 },
  ]) assert.equal((await send(store, 'POST', '/v1/events', bad)).status, 400, JSON.stringify(bad));
  assert.equal((await send(store, 'POST', '/v1/events', '{')).status, 400);
  assert.equal((await send(store, 'POST', '/v1/events', 'x'.repeat(20_000))).status, 400);
  assert.deepEqual([store.rows, store.tallies], [[], []]);
});

test('a browser cannot post: a request with an Origin header, or a body that is not JSON, stores nothing', async () => {
  const store = memory();
  const page = await send(store, 'POST', '/v1/events', BATCH, { origin: 'https://example.com' });
  assert.deepEqual([page.status, await page.json()], [403, { error: 'not from a browser' }]);
  const text = await send(store, 'POST', '/v1/events', BATCH, { 'content-type': 'text/plain' });
  assert.deepEqual([text.status, await text.json()], [415, { error: 'the body must be application/json' }]);
  assert.deepEqual([store.rows, store.tallies], [[], []]);
});

test('an install id forgets everything sent under it; pruning is the cron\'s alone', async () => {
  const store = memory();
  await send(store, 'POST', '/v1/events', BATCH);
  assert.equal((await send(store, 'POST', '/v1/forget', { install: 'not-an-id' })).status, 400);
  assert.equal((await send(store, 'POST', '/v1/forget', { install: INSTALL })).status, 204);
  assert.equal((await send(store, 'DELETE', `/v1/installs/${INSTALL}`)).status, 404); // no id in a path
  assert.deepEqual(store.rows, []);
  assert.equal((await send(store, 'GET', '/v1/prune')).status, 401);
  assert.equal((await send(store, 'GET', '/v1/prune', undefined, { authorization: 'Bearer secret' })).status, 200);
  assert.equal(store.pruned, RETENTION_DAYS);
  assert.equal((await send(store, 'GET', '/v1/events')).status, 404);
});

test('health fails without a setting, or with tables a batch cannot be stored in, naming no more than a code', async () => {
  assert.equal((await send(memory(), 'GET', '/v1/health')).status, 200);
  const unset = await handle(new Request('https://api.texttocad.dev/v1/health'), memory(), { missing: ['CRON_SECRET'] });
  assert.deepEqual([unset.status, await unset.json()], [503, { ok: false, missing: ['CRON_SECRET'] }]);
  // A column schema.sql was not re-run for.
  const stale = { ...memory(), async ready() { throw Object.assign(new Error('column "kind" does not exist'), { code: '42703' }); } };
  const reply = await send(stale, 'GET', '/v1/health');
  assert.deepEqual([reply.status, await reply.json()], [503, { ok: false, error: '42703' }]);
});

test('the version feed is the same for everyone, kept at the edge, and answers without a database', async () => {
  const feed = { latest: '0.9.0' };
  const down = { ...memory(), async ready() { throw new Error('unreachable'); } };
  const reply = await handle(new Request('https://api.texttocad.dev/v1/versions'), down, { versions: feed, missing: ['DATABASE_URL'] });
  assert.deepEqual([reply.status, await reply.json()], [200, feed]);
  assert.equal(reply.headers.get('cache-control'), 'public, s-maxage=86400');
});

test("this release's feed names it, and nothing else", () => {
  assert.deepEqual(versions, { latest: readFileSync(new URL('../../../../../VERSION', import.meta.url), 'utf8').trim() });
});

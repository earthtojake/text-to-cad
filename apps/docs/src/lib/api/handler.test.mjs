import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { handle } from './handler.mjs';
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
// What cadgen 0.7.7 to 0.7.11 send: how the install was made in place of its channel (undefined is left
// out of the JSON a batch is sent as).
const SCHEMA_1 = { ...BATCH, schema: 1, version: '0.7.11', source: 'store', channel: undefined };

// A store in memory: the rows each batch passed on, and the country each came with.
function memory() {
  const rows = [];
  const countries = [];
  return {
    rows,
    countries,
    async insert(batch, { country }) { rows.push(...batch); countries.push(country); },
    async forget(id) { for (let i = rows.length - 1; i >= 0; i -= 1) if (rows[i].install_id === id) rows.splice(i, 1); },
    async ready() {},
  };
}
const send = (store, method, path, body, headers = {}, country = 'DE') => handle(new Request(`https://api.texttocad.dev${path}`, {
  method, headers: { 'content-type': 'application/json', ...headers }, body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
}), store, { country });

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
  assert.deepEqual(Object.keys(store.rows[0]).sort(), ['arch', 'calls', 'channel', 'client', 'client_version', 'errors', 'event', 'file', 'install_id', 'kind', 'platform', 'presentation', 'session_id', 'source', 'tool', 'version']);
});

test('every schema a released cadgen sends is stored: a copy nobody updated keeps counting', async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', SCHEMA_1)).status, 204);
  assert.equal((await send(store, 'POST', '/v1/events', BATCH)).status, 204);
  // Schema 1 names no channel: its rows keep how the install was made.
  assert.deepEqual(store.rows.map(row => [row.version, row.channel, row.source]), [
    ...SCHEMA_1.events.map(() => ['0.7.11', 'unknown', 'store']),
    ...BATCH.events.map(() => ['0.7.6', 'claude-directory', null]),
  ]);
});

test('a batch goes on with the country the host placed it in: never its address, nor anything finer', async () => {
  const store = memory();
  await send(store, 'POST', '/v1/events', BATCH);
  await send(store, 'POST', '/v1/events', BATCH, {}, 'not a country'); // the host could not tell
  assert.deepEqual(store.countries, ['DE', null]);
  assert.ok(store.rows.every(row => !('country' in row))); // a batch names no country of its own
});

test("a service that will not take the batch is the receiver's failure: the client keeps it and sends it again", async () => {
  const down = { ...memory(), async insert() { throw Object.assign(new Error('PostHog answered 503'), { code: 'posthog_503' }); } };
  const reply = await send(down, 'POST', '/v1/events', BATCH);
  assert.deepEqual([reply.status, await reply.json()], [500, { error: 'internal error' }]);
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
    { ...BATCH, schema: 3 }, // a schema no release sends
    { ...BATCH, schema: '2' },
    { ...SCHEMA_1, channel: 'claude-github' }, // each schema's own fields, and only those
    { ...SCHEMA_1, source: 'github' },
  ]) assert.equal((await send(store, 'POST', '/v1/events', bad)).status, 400, JSON.stringify(bad));
  assert.equal((await send(store, 'POST', '/v1/events', '{')).status, 400);
  assert.equal((await send(store, 'POST', '/v1/events', 'x'.repeat(20_000))).status, 400);
  assert.deepEqual([store.rows, store.countries], [[], []]);
});

test('a browser cannot post: a request with an Origin header, or a body that is not JSON, stores nothing', async () => {
  const store = memory();
  const page = await send(store, 'POST', '/v1/events', BATCH, { origin: 'https://example.com' });
  assert.deepEqual([page.status, await page.json()], [403, { error: 'not from a browser' }]);
  const text = await send(store, 'POST', '/v1/events', BATCH, { 'content-type': 'text/plain' });
  assert.deepEqual([text.status, await text.json()], [415, { error: 'the body must be application/json' }]);
  assert.deepEqual([store.rows, store.countries], [[], []]);
});

test('an install id forgets everything sent under it; retention is the service\'s', async () => {
  const store = memory();
  await send(store, 'POST', '/v1/events', BATCH);
  assert.equal((await send(store, 'POST', '/v1/forget', { install: 'not-an-id' })).status, 400);
  assert.equal((await send(store, 'POST', '/v1/forget', { install: INSTALL })).status, 204);
  assert.equal((await send(store, 'DELETE', `/v1/installs/${INSTALL}`)).status, 404); // no id in a path
  assert.deepEqual(store.rows, []);
  assert.equal((await send(store, 'GET', '/v1/prune')).status, 404);
  assert.equal((await send(store, 'GET', '/v1/events')).status, 404);
});

test('health fails without a setting, or with keys the service refuses, naming no more than a code', async () => {
  assert.equal((await send(memory(), 'GET', '/v1/health')).status, 200);
  const unset = await handle(new Request('https://api.texttocad.dev/v1/health'), memory(), { missing: ['POSTHOG_PROJECT_KEY'] });
  assert.deepEqual([unset.status, await unset.json()], [503, { ok: false, missing: ['POSTHOG_PROJECT_KEY'] }]);
  // A personal key PostHog no longer takes.
  const refused = { ...memory(), async ready() { throw Object.assign(new Error('PostHog answered 401'), { code: 'posthog_401' }); } };
  const reply = await send(refused, 'GET', '/v1/health');
  assert.deepEqual([reply.status, await reply.json()], [503, { ok: false, error: 'posthog_401' }]);
});

test('the version feed is the same for everyone, kept at the edge, and answers without the telemetry service', async () => {
  const feed = { latest: '0.9.0' };
  const down = { ...memory(), async ready() { throw new Error('unreachable'); } };
  const reply = await handle(new Request('https://api.texttocad.dev/v1/versions'), down, { versions: feed, missing: ['POSTHOG_REGION'] });
  assert.deepEqual([reply.status, await reply.json()], [200, feed]);
  assert.equal(reply.headers.get('cache-control'), 'public, s-maxage=86400');
});

test("this release's feed names it, and nothing else", () => {
  assert.deepEqual(versions, { latest: readFileSync(new URL('../../../../../VERSION', import.meta.url), 'utf8').trim() });
});

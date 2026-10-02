import assert from 'node:assert/strict';
import { test } from 'node:test';
import { handle, RETENTION_DAYS } from './handler.mjs';

const INSTALL = '8c347ec3-1342-4db5-a19a-491cbc8c59be';
const SESSION = '0b1e6f1a-6a52-4c39-9d43-2f5e0f0b9d11';
// What cadgen/analytics.py sends.
const BATCH = {
  schema: 1, install: INSTALL, session: SESSION, version: '0.7.6', source: 'store', platform: 'darwin', arch: 'arm64',
  client: { name: 'codex-mcp-client', version: '0.159.0' }, presentation: 'tabs',
  events: [
    { name: 'tool', tool: 'cad_show', calls: 3, errors: 1 },
    { name: 'view', calls: 7 },
    { name: 'file', file: '3f9a1c0be47d2a55', kind: 'step' },
  ],
};

function memory() {
  const rows = [];
  return {
    rows,
    async insert(batch) { rows.push(...batch); },
    async forget(id) { for (let i = rows.length - 1; i >= 0; i -= 1) if (rows[i].install_id === id) rows.splice(i, 1); },
    async prune(days) { this.pruned = days; return 0; },
  };
}
const send = (store, method, path, body, headers = {}) => handle(new Request(`https://api.texttocad.dev${path}`, {
  method, headers: { 'content-type': 'application/json', ...headers }, body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
}), store, { cronSecret: 'secret' });

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
  assert.deepEqual(Object.keys(store.rows[0]).sort(), ['arch', 'calls', 'client', 'client_version', 'errors', 'event', 'file', 'install_id', 'kind', 'platform', 'presentation', 'session_id', 'source', 'tool', 'version']);
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
    { ...BATCH, events: [] },
  ]) assert.equal((await send(store, 'POST', '/v1/events', bad)).status, 400, JSON.stringify(bad));
  assert.equal((await send(store, 'POST', '/v1/events', '{')).status, 400);
  assert.equal((await send(store, 'POST', '/v1/events', 'x'.repeat(20_000))).status, 400);
  assert.deepEqual(store.rows, []);
});

test('an install id forgets everything sent under it; pruning is the cron\'s alone', async () => {
  const store = memory();
  await send(store, 'POST', '/v1/events', BATCH);
  assert.equal((await send(store, 'DELETE', '/v1/installs/not-an-id')).status, 400);
  assert.equal((await send(store, 'DELETE', `/v1/installs/${INSTALL}`)).status, 204);
  assert.deepEqual(store.rows, []);
  assert.equal((await send(store, 'GET', '/v1/prune')).status, 401);
  assert.equal((await send(store, 'GET', '/v1/prune', undefined, { authorization: 'Bearer secret' })).status, 200);
  assert.equal(store.pruned, RETENTION_DAYS);
  assert.equal((await send(store, 'GET', '/api/v1/health')).status, 200);
  assert.equal((await send(store, 'GET', '/v1/events')).status, 404);
});

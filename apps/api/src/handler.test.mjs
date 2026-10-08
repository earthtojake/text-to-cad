import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { handle } from './handler.mjs';
import { versions } from './versions.mjs';

const INSTALL = '8c347ec3-1342-4db5-a19a-491cbc8c59be';
const SESSION = '0b1e6f1a-6a52-4c39-9d43-2f5e0f0b9d11';
// What cadgen/analytics.py sends from the CAD app...
const BATCH = {
  schema: 3, install: INSTALL, session: SESSION, process: 'app', version: '0.8.0', channel: 'claude-directory', platform: 'darwin',
  arch: 'arm64', client: { name: 'codex-mcp-client', version: '0.159.0' }, presentation: 'tabs',
  events: [
    { name: 'tool', tool: 'cad_show', calls: 3, errors: 1 },
    { name: 'view', calls: 7 },
    { name: 'files', kind: 'step', count: 2 },
  ],
};
// ...and from the build daemon, which names no agent app.
const DAEMON = {
  schema: 3, install: INSTALL, session: SESSION, process: 'daemon', version: '0.8.0', channel: 'claude-directory', platform: 'darwin',
  arch: 'arm64',
  events: [
    { name: 'build', kind: 'step', via: 'script', count: 9, failed: 2, crashed: 0, cancelled: 1, cached: 4, seconds: 31.5, longest: 12.2 },
    { name: 'build', kind: 'stl', via: 'command', count: 1, failed: 0, crashed: 0, cancelled: 0, cached: 0, seconds: 0.4, longest: 0.4 },
    { name: 'snapshot', kind: 'step', count: 3, failed: 0, seconds: 7.25 },
    { name: 'feature', feature: 'assembly', count: 2 },
    { name: 'health', workers: 2, crashes: 0, recycles: 0, refusals: 0 },
  ],
};
// A crash, as cadgen sends one: its type and frames in code that may be named, the person's own a bare <user>.
const CRASH = {
  name: 'exception', where: 'tool', tool: 'cad_show', type: 'KeyError', handled: true, count: 2,
  frames: [{ file: 'cadgen/mcp/server.py', function: 'Server._call', line: 421 }, { file: '<user>', function: '<user>', line: 0 },
    { file: 'json/decoder.py', function: 'JSONDecoder.decode', line: 345 }],
};
// What cadgen 0.7.12 to 0.7.15 send: no process, and with a yes a distinct file by its salted code...
const SCHEMA_2 = {
  ...BATCH, schema: 2, version: '0.7.15', process: undefined,
  events: [...BATCH.events.slice(0, 2), { name: 'file', file: '3f9a1c0be47d2a55', kind: 'step' },
    { name: 'file', file: '9b2e5c1d0a7f3e46', kind: 'step' }, { name: 'file', file: '0c4d8e2f6a1b3c5d', kind: 'stl' }],
};
// ...and 0.7.7 to 0.7.11: how the install was made in place of its channel (undefined is left out of the JSON
// a batch is sent as).
const SCHEMA_1 = { ...SCHEMA_2, schema: 1, version: '0.7.11', source: 'store', channel: undefined };

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

const CONTEXT = ['install_id', 'session_id', 'version', 'channel', 'source', 'process', 'platform', 'arch', 'client', 'client_version',
  'presentation'];
// A row's own fields, by its event.
const fieldsOf = row => Object.fromEntries(Object.entries(row).filter(([key]) => !CONTEXT.includes(key)));

test('a batch becomes one row per event, carrying its context and its own counts, and nothing else', async () => {
  const store = memory();
  const reply = await send(store, 'POST', '/v1/events', BATCH);
  assert.equal(reply.status, 204);
  // cadgen calls from Python: no web page may make its visitors' browsers post here.
  assert.equal(reply.headers.get('access-control-allow-origin'), null);
  assert.deepEqual(store.rows.map(fieldsOf), [
    { event: 'tool', tool: 'cad_show', calls: 3, errors: 1 },
    { event: 'view', calls: 7 },
    { event: 'files', kind: 'step', count: 2 },
  ]);
  assert.deepEqual(Object.keys(store.rows[0]).sort(), [...CONTEXT, 'event', 'tool', 'calls', 'errors'].sort());
  assert.deepEqual([store.rows[0].process, store.rows[0].client, store.rows[0].presentation], ['app', 'codex-mcp-client', 'tabs']);
});

test("the build daemon's counts are rows of their own, under the process that saw them", async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', DAEMON)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf), DAEMON.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  assert.ok(store.rows.every(row => row.process === 'daemon' && row.client === null && row.presentation === null));
});

test('a crash is one row, its frames checked one by one, and nothing it said', async () => {
  const store = memory();
  const worker = { name: 'exception', where: 'build', type: 'WorkerDied', handled: false, status: -11, frames: [], count: 1 };
  const page = { name: 'exception', where: 'page', type: 'TypeError', handled: false, count: 1,
    frames: [{ file: 'assets/index-Bx3k2.js', function: 'Kt', line: 1, column: 48213, chunk_id: '0de4d024-c159-4f6d-b15a-cc4ef7a6856d' }] };
  assert.equal((await send(store, 'POST', '/v1/events', { ...DAEMON, events: [CRASH, worker, page] })).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf), [CRASH, worker, page].map(({ name, ...crash }) => ({ event: name, ...crash })));
  // Only a page's frame names a chunk, and only by a debug id.
  for (const frames of [[{ ...page.frames[0], chunk_id: 'secret' }], [{ file: 'cadgen/x.py', function: 'f', chunk_id: '0de4d024-c159-4f6d-b15a-cc4ef7a6856d' }]]) {
    const event = { ...page, where: frames[0].file.endsWith('.py') ? 'build' : 'page', frames };
    assert.equal((await send(memory(), 'POST', '/v1/events', { ...DAEMON, events: [event] })).status, 400);
  }
});

test('every schema a released cadgen sends is stored: a copy nobody updated keeps counting', async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', SCHEMA_1)).status, 204);
  assert.equal((await send(store, 'POST', '/v1/events', SCHEMA_2)).status, 204);
  assert.equal((await send(store, 'POST', '/v1/events', { ...SCHEMA_2, presentation: 'browser' })).status, 204);
  // Before schema 3 only the apps sent, the browser viewer by how it shows CAD; schema 1 names no channel, and
  // its rows keep how the install was made. A file's code goes no further: a batch's files are counts by format.
  const expected = (version, channel, source, process) => [
    [version, channel, source, process, 'tool', null, null],
    [version, channel, source, process, 'view', null, null],
    [version, channel, source, process, 'files', 'step', 2],
    [version, channel, source, process, 'files', 'stl', 1],
  ];
  assert.deepEqual(store.rows.map(row => [row.version, row.channel, row.source, row.process, row.event, row.kind ?? null, row.count ?? null]), [
    ...expected('0.7.11', 'unknown', 'store', 'app'),
    ...expected('0.7.15', 'claude-directory', null, 'app'),
    ...expected('0.7.15', 'claude-directory', null, 'viewer'),
  ]);
  assert.ok(store.rows.every(row => !('file' in row)));
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
  const [build, snapshot, feature, health] = [DAEMON.events[0], DAEMON.events[2], DAEMON.events[3], DAEMON.events[4]];
  for (const bad of [
    { ...BATCH, path: '/Users/someone/secret.step' },
    { ...BATCH, install: 'someone@example.com' },
    { ...BATCH, events: [{ name: 'tool', tool: '/Users/someone/secret.step', calls: 1 }] },
    { ...BATCH, events: [{ name: 'tool', tool: 'cad_show', calls: 1, path: 'secret.step' }] },
    { ...BATCH, events: [{ name: 'files', kind: 'step', count: 1, file: '3f9a1c0be47d2a55' }] },
    { ...BATCH, events: [{ name: 'files', kind: 'docx', count: 1 }] },
    { ...BATCH, events: [{ name: 'files', kind: 'step', count: 0 }] },
    { ...BATCH, events: [{ name: 'file', file: '3f9a1c0be47d2a55', kind: 'step' }] }, // a file code, which schema 3 never sends
    { ...SCHEMA_2, events: [{ name: 'file', file: '/Users/someone/secret.step', kind: 'step' }] },
    { ...SCHEMA_2, events: [{ name: 'file', file: '3f9a1c0be47d2a55', kind: 'step', name2: 'secret.step' }] },
    { ...SCHEMA_2, events: [{ name: 'file', file: '3f9a1c0be47d2a55', kind: 'docx' }] },
    { ...SCHEMA_2, events: [...SCHEMA_2.events, SCHEMA_2.events[2]] }, // the same file twice
    { ...SCHEMA_2, events: [build] }, // the daemon's events are schema 3's
    { ...BATCH, events: [{ name: 'view', calls: 0 }] },
    { ...BATCH, events: [{ name: 'session_start' }] },
    { ...BATCH, events: [{ name: 'constructor' }] },
    { ...BATCH, client: { name: 'Café' } },
    { ...BATCH, client: { name: 'a name with spaces and a story' } },
    { ...BATCH, client: { ...BATCH.client, path: 'secret.step' } },
    { ...BATCH, events: [] },
    { ...BATCH, events: [...BATCH.events, BATCH.events[0]] }, // the same tool twice
    { ...BATCH, events: [...BATCH.events, BATCH.events[1]] }, // a second view
    { ...BATCH, events: [...BATCH.events, BATCH.events[2]] }, // one format's files twice
    { ...BATCH, events: [{ name: 'tool', tool: 'cad_show', calls: 1, errors: null }] },
    { ...BATCH, events: [{ name: 'tool', tool: 'cad_show', calls: 1, errors: 2 }] },
    { ...BATCH, process: 'cli' },
    { ...BATCH, process: undefined },
    { ...DAEMON, events: [{ ...build, kind: 'docx' }] },
    { ...DAEMON, events: [{ ...build, via: 'viewer' }] },
    { ...DAEMON, events: [{ ...build, count: 0 }] },
    { ...DAEMON, events: [{ ...build, failed: 5, cancelled: 1 }] }, // more endings than builds
    { ...DAEMON, events: [{ ...build, cached: undefined }] }, // every count, always
    { ...DAEMON, events: [{ ...build, seconds: -1 }] },
    { ...DAEMON, events: [{ ...build, seconds: '31.5' }] },
    { ...DAEMON, events: [{ ...build, model: 'secret.py' }] },
    { ...DAEMON, events: [build, build] },
    { ...DAEMON, events: [{ ...snapshot, failed: 4 }] },
    { ...DAEMON, events: [{ ...feature, feature: 'secret_sauce' }] },
    { ...DAEMON, events: [{ ...feature, count: 0 }] },
    { ...DAEMON, events: [{ ...health, workers: 0 }] }, // a health that counts nothing
    { ...DAEMON, events: [{ ...health, uptime: 3600 }] },
    { ...BATCH, events: [{ ...CRASH, message: "KeyError: 'secret bracket'" }] }, // never what it said
    { ...BATCH, events: [{ ...CRASH, frames: [{ file: '/Users/someone/secret.py', function: 'make', line: 3 }] }] },
    { ...BATCH, events: [{ ...CRASH, frames: [{ file: 'C:\\Users\\someone\\secret.py', function: 'make', line: 3 }] }] },
    { ...BATCH, events: [{ ...CRASH, frames: [{ file: '../secret.py', function: 'make', line: 3 }] }] },
    { ...BATCH, events: [{ ...CRASH, frames: [{ ...CRASH.frames[0], locals: { part: 'secret' } }] }] },
    { ...BATCH, events: [{ ...CRASH, frames: [{ ...CRASH.frames[0], function: 'make secret bracket' }] }] },
    { ...BATCH, events: [{ ...CRASH, frames: Array(31).fill(CRASH.frames[0]) }] },
    { ...BATCH, events: [{ ...CRASH, type: "KeyError('secret')" }] },
    { ...BATCH, events: [{ ...CRASH, where: 'somewhere' }] },
    { ...BATCH, events: [{ ...CRASH, handled: 'yes' }] },
    { ...BATCH, events: [{ ...CRASH, count: 0 }] },
    { ...BATCH, events: [CRASH, CRASH] }, // one crash, counted: never twice in a batch
    { ...SCHEMA_2, events: [CRASH] }, // crashes are schema 3's
    { ...BATCH, channel: 'store' },
    { ...BATCH, channel: 'github' }, // a channel no plugin names any more
    { ...BATCH, schema: 4 }, // a schema no release sends
    { ...BATCH, schema: '3' },
    { ...SCHEMA_2, process: 'app' }, // each schema's own fields, and only those
    { ...SCHEMA_1, channel: 'claude-github' },
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
  assert.deepEqual(versions, { latest: readFileSync(new URL('../../../VERSION', import.meta.url), 'utf8').trim() });
});

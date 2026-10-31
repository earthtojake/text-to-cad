import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import { handle } from './handler.mjs';
import { rateLimiter } from './limit.mjs';

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

test("a release's version and a development install's are both read, each stored as sent", async () => {
  // A development install names its own (`<version>-dev.<time>`, cadgen/analytics.py: `installation_version`): a
  // send forced from one is told apart from the release's.
  const store = memory();
  for (const version of ['0.8.0', '0.8.0-dev.20261026120000']) {
    assert.equal((await send(store, 'POST', '/v1/events', { ...BATCH, version })).status, 204, version);
  }
  assert.deepEqual([...new Set(store.rows.map(row => row.version))], ['0.8.0', '0.8.0-dev.20261026120000']);
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...BATCH, version: `0.8.0-dev.${'1'.repeat(32)}` })).status, 400,
    'never longer than a version needs');
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
  // Windows ends a faulted process with its exception code (STATUS_ACCESS_VIOLATION): an exit status too.
  const fault = { ...worker, status: 0xC0000005 };
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...DAEMON, events: [fault] })).status, 204);
  for (const status of [70000, -0xC0000005, 0x100000000, 1.5]) {
    assert.equal((await send(memory(), 'POST', '/v1/events', { ...DAEMON, events: [{ ...worker, status }] })).status, 400, status);
  }
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

test("schema 4 says why a tool's calls failed, one row per tool and reason, by a word cadgen chose", async () => {
  const store = memory();
  const failures = [{ name: 'tool_failure', tool: 'cad_show', reason: 'no_file', count: 1 }];
  assert.equal((await send(store, 'POST', '/v1/events', { ...BATCH, schema: 4, events: [...BATCH.events, ...failures] })).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).at(-1), { event: 'tool_failure', tool: 'cad_show', reason: 'no_file', count: 1 });
  // Schema 3, as cadgen 0.7.16 and 0.7.17 send it, is read as ever.
  assert.equal((await send(store, 'POST', '/v1/events', BATCH)).status, 204);
  for (const bad of [
    { ...BATCH, events: failures }, // schema 3 never sent one
    { ...BATCH, schema: 4, events: [{ ...failures[0], reason: 'No file at /Users/someone/secret.step.' }] }, // never a message
    { ...BATCH, schema: 4, events: [{ ...failures[0], reason: 'disk_full' }] }, // a word outside the vocabulary
    { ...BATCH, schema: 4, events: [{ ...failures[0], tool: '/Users/someone/secret.step' }] },
    { ...BATCH, schema: 4, events: [{ ...failures[0], count: 0 }] },
    { ...BATCH, schema: 4, events: [{ ...failures[0], count: undefined }] },
    { ...BATCH, schema: 4, events: [{ ...failures[0], path: 'secret.step' }] },
    { ...BATCH, schema: 4, events: [failures[0], failures[0]] }, // one tool and reason, counted once
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', bad)).status, 400, JSON.stringify(bad));
  // A call naming no tool of cadgen's is `cad_unknown`'s (cadgen/analytics.py: `UNKNOWN_TOOL`), a tool like any
  // other: the name the host sent is never sent, so no other needs reading.
  const unknown = [{ name: 'tool', tool: 'cad_unknown', calls: 2, errors: 2 },
    { name: 'tool_failure', tool: 'cad_unknown', reason: 'bad_request', count: 2 }];
  assert.equal((await send(store, 'POST', '/v1/events', { ...BATCH, schema: 4, events: unknown })).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).slice(-2), unknown.map(({ name, ...counts }) => ({ event: name, ...counts })));
});

// Schema 5: the daemon's batch, named, with why its builds and snapshots failed.
const NAMED = {
  ...DAEMON, schema: 5, batch: '5d0f3c2e-8b1a-4c6e-9f2d-7a3b1e4c5d6f', at: 1_791_500_000,
  events: [
    DAEMON.events[0],
    { name: 'build_failure', kind: 'step', via: 'script', reason: 'kernel_error', count: 1 },
    { name: 'build_failure', kind: 'step', via: 'script', reason: 'model_error', count: 1 },
    DAEMON.events[2],
    { name: 'snapshot_failure', kind: 'step', reason: 'browser', count: 1 },
  ],
};

test('schema 5 says why builds and snapshots failed, by a word cadgen chose, and names each row by its batch', async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', NAMED)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    NAMED.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  assert.ok(store.rows.every(row => row.at === NAMED.at && /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(row.id)));
  // The same batch sent again is the same rows, id for id; another batch's are its own.
  const ids = store.rows.map(row => row.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal((await send(store, 'POST', '/v1/events', NAMED)).status, 204);
  assert.deepEqual(store.rows.slice(ids.length).map(row => row.id), ids);
  assert.equal((await send(store, 'POST', '/v1/events', { ...NAMED, batch: 'f1e2d3c4-b5a6-4978-8a1b-2c3d4e5f6a7b' })).status, 204);
  assert.ok(store.rows.slice(2 * ids.length).every(row => !ids.includes(row.id)));
  // Schemas 1 to 4 name no batch: their rows carry no id and no time, as ever.
  const earlier = memory();
  await send(earlier, 'POST', '/v1/events', { ...BATCH, schema: 4 });
  await send(earlier, 'POST', '/v1/events', SCHEMA_1);
  assert.ok(earlier.rows.every(row => !('id' in row) && !('at' in row)));
  for (const bad of [
    { ...NAMED, batch: undefined },
    { ...NAMED, batch: 'batch-1' },
    { ...NAMED, at: undefined },
    { ...NAMED, at: 1_791_500_000.5 },
    { ...NAMED, at: -1 },
    { ...NAMED, at: '1791500000' },
    { ...BATCH, schema: 4, batch: NAMED.batch, at: NAMED.at }, // schema 4 never named a batch
    { ...DAEMON, schema: 4, events: [NAMED.events[1]] }, // nor sent why a build failed
    { ...NAMED, events: [{ ...NAMED.events[1], reason: 'ValueError: the secret part did not fit' }] }, // never a message
    { ...NAMED, events: [{ ...NAMED.events[1], reason: 'disk_full' }] }, // a word outside the vocabulary
    { ...NAMED, events: [{ ...NAMED.events[4], reason: 'kernel_error' }] }, // a build's word is no snapshot's
    { ...NAMED, events: [{ ...NAMED.events[1], via: 'viewer' }] },
    { ...NAMED, events: [{ ...NAMED.events[1], kind: 'docx' }] },
    { ...NAMED, events: [{ ...NAMED.events[1], count: 0 }] },
    { ...NAMED, events: [{ ...NAMED.events[1], model: 'secret.py' }] },
    { ...NAMED, events: [{ ...NAMED.events[4], via: 'script' }] },
    { ...NAMED, events: [NAMED.events[1], NAMED.events[1]] }, // one format, asker and reason, counted once
    { ...NAMED, events: [NAMED.events[4], NAMED.events[4]] },
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(bad)))).status, 400, JSON.stringify(bad));
});

// Schema 6: schema 5, with the engine's documents (`xbf`) and the sender a `cadgen` command starts (`cli`).
const ENGINE = {
  ...NAMED, schema: 6, process: 'cli', batch: '7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f',
  events: [
    { name: 'build', kind: 'xbf', via: 'script', count: 3, failed: 1, crashed: 0, cancelled: 0, cached: 1, seconds: 2.5, longest: 1.5 },
    { name: 'build_failure', kind: 'xbf', via: 'script', reason: 'model_error', count: 1 },
    { name: 'build', kind: 'step', via: 'command', count: 1, failed: 0, crashed: 0, cancelled: 0, cached: 0, seconds: 0.4, longest: 0.4 },
    { name: 'snapshot', kind: 'xbf', count: 1, failed: 1, seconds: 2.4 },
    { name: 'snapshot_failure', kind: 'xbf', reason: 'render_error', count: 1 },
    { name: 'health', workers: 1, crashes: 0, recycles: 0, refusals: 0 },
  ],
};

test("schema 6 counts the engine's documents, and names the sender a command starts", async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', ENGINE)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    ENGINE.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  assert.ok(store.rows.every(row => row.process === 'cli' && row.at === ENGINE.at && /^[0-9a-f-]{36}$/.test(row.id)));
  // Every process sends it: a view that showed an xbf.
  const view = { ...BATCH, schema: 6, batch: ENGINE.batch, at: ENGINE.at, events: [{ name: 'files', kind: 'xbf', count: 1 }] };
  assert.equal((await send(store, 'POST', '/v1/events', view)).status, 204);
  // Every schema before it is read as ever.
  for (const earlier of [SCHEMA_1, SCHEMA_2, BATCH, { ...BATCH, schema: 4 }, NAMED]) {
    assert.equal((await send(memory(), 'POST', '/v1/events', earlier)).status, 204, `schema ${earlier.schema}`);
  }
  for (const bad of [
    { ...NAMED, events: [ENGINE.events[0]] }, // schema 5 never counted an xbf
    { ...NAMED, process: 'cli' }, // nor came from a command's sender
    { ...BATCH, events: [{ name: 'files', kind: 'xbf', count: 1 }] },
    { ...ENGINE, process: 'engine' },
    { ...ENGINE, batch: undefined }, // named, as schema 5 is
    { ...ENGINE, events: [{ ...ENGINE.events[0], kind: 'xbf2' }] },
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(bad)))).status, 400, JSON.stringify(bad));
});

// Schema 7: schema 6, with the controls a person used in a CAD view, from the CAD app and the browser viewer alike.
const CONTROLS = {
  ...ENGINE, schema: 7, process: 'viewer', client: { name: 'cadgen-viewer', version: '0.8.0' }, presentation: 'browser',
  events: [
    { name: 'control', control: 'pencil', count: 2, seconds: 95 },
    // On all window, taken up in an earlier one: no use, its seconds alone.
    { name: 'control', control: 'preview', count: 0, seconds: 300 },
    { name: 'control', control: 'display_xray', count: 1, seconds: 0 },
    { name: 'view', calls: 4 },
  ],
};

test('schema 7 counts the controls a person used, and how long a tool that stays on was on', async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', CONTROLS)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    CONTROLS.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  assert.ok(store.rows.every(row => row.process === 'viewer' && row.at === CONTROLS.at && /^[0-9a-f-]{36}$/.test(row.id)));
  // The CAD app sends them too, and room for one event per control a window used.
  const tools = [...Array(150)].map((_, index) => ({ name: 'tool', tool: `cad_${'abcdefghij'[index % 10]}${'abcdefghijklmno'[Math.floor(index / 10)]}`,
    calls: 1, errors: 0 }));
  const app = { ...CONTROLS, process: 'app', client: BATCH.client, presentation: 'tabs', events: [...CONTROLS.events, ...tools] };
  assert.equal((await send(memory(), 'POST', '/v1/events', app)).status, 204);
  // Every schema before it is read as ever, schema 6 unchanged.
  for (const earlier of [SCHEMA_1, SCHEMA_2, BATCH, { ...BATCH, schema: 4 }, NAMED, ENGINE]) {
    const kept = memory();
    assert.equal((await send(kept, 'POST', '/v1/events', earlier)).status, 204, `schema ${earlier.schema}`);
    assert.ok(kept.rows.every(row => row.event !== 'control'));
  }
  for (const bad of [
    { ...ENGINE, events: [CONTROLS.events[0]] }, // schema 6 never counted a control
    { ...ENGINE, events: tools.slice(0, 65) }, // nor sent more than 64
    { ...CONTROLS, events: [{ name: 'control', control: 'my_model.step', count: 1, seconds: 0 }] }, // a name outside the vocabulary
    { ...CONTROLS, events: [{ name: 'control', control: 'Select', count: 1, seconds: 0 }] },
    { ...CONTROLS, events: [{ name: 'control', control: 'display_mode', value: 'xray', count: 1, seconds: 0 }] }, // no value beside it
    { ...CONTROLS, events: [{ name: 'control', control: 'pencil', count: 1 }] }, // seconds always said
    { ...CONTROLS, events: [{ name: 'control', control: 'pencil', count: 1, seconds: 1.5 }] }, // whole seconds only
    { ...CONTROLS, events: [{ name: 'control', control: 'pencil', count: 0, seconds: 0 }] }, // counting nothing
    { ...CONTROLS, events: [{ name: 'control', control: 'pencil', count: -1, seconds: 3 }] },
    { ...CONTROLS, events: [CONTROLS.events[0], CONTROLS.events[0]] }, // once per control
    { ...CONTROLS, events: [...Array(257)].map(() => CONTROLS.events[0]) },
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(bad)))).status, 400, JSON.stringify(bad).slice(0, 200));
});

test('schema 8 separates live models from XBF files without reinterpreting older batches', async () => {
  const kinds = ['model', 'xbf'];
  const events = kinds.flatMap(kind => [
    { ...ENGINE.events[0], kind },
    { ...ENGINE.events[1], kind },
    { name: 'files', kind, count: 1 },
    { ...ENGINE.events[3], kind },
    { ...ENGINE.events[4], kind },
  ]);
  const batch = { ...CONTROLS, schema: 8, events: [...events, CONTROLS.events[0]] };
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', batch)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    batch.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  assert.equal(new Set(store.rows.map(row => row.id)).size, batch.events.length);
  for (const schema of [6, 7]) {
    const old = memory();
    const file = { name: 'files', kind: 'xbf', count: 1 };
    assert.equal((await send(old, 'POST', '/v1/events', { ...ENGINE, schema, events: [file] })).status, 204);
    assert.equal(old.rows[0].kind, 'xbf');
    assert.equal((await send(memory(), 'POST', '/v1/events', { ...ENGINE, schema,
      events: [{ ...file, kind: 'model' }] })).status, 400);
  }
  // Safe deployment probe: a known kind with an invalid count reaches count validation and stores nothing.
  const refused = memory();
  const response = await send(refused, 'POST', '/v1/events', { ...batch,
    events: [{ name: 'files', kind: 'model', count: 0 }] });
  assert.equal(response.status, 400);
  assert.equal((await response.json()).error, 'events[0].count counts nothing');
  assert.deepEqual(refused.rows, []);
  for (const kind of ['models', 'model.py']) {
    assert.equal((await send(memory(), 'POST', '/v1/events', { ...batch,
      events: [{ name: 'files', kind, count: 1 }] })).status, 400);
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
    { ...BATCH, schema: 9 }, // a schema no release sends
    { ...BATCH, schema: '3' },
    { ...SCHEMA_2, process: 'app' }, // each schema's own fields, and only those
    { ...SCHEMA_1, channel: 'claude-github' },
    { ...SCHEMA_1, source: 'github' },
  ]) assert.equal((await send(store, 'POST', '/v1/events', bad)).status, 400, JSON.stringify(bad));
  assert.equal((await send(store, 'POST', '/v1/events', '{')).status, 400);
  assert.equal((await send(store, 'POST', '/v1/events', 'x'.repeat(20_000))).status, 400);
  assert.deepEqual([store.rows, store.countries], [[], []]);
});

// What a handler logs while a request runs, by level.
async function logged(run) {
  const lines = { warn: [], error: [] };
  const warn = mock.method(console, 'warn', (...args) => lines.warn.push(args.join(' ')));
  const error = mock.method(console, 'error', (...args) => lines.error.push(args.join(' ')));
  try { await run(); } finally { warn.mock.restore(); error.mock.restore(); }
  return lines;
}

test('a refused request is logged by the rule it broke and the release that sent it: never a value it carried', async () => {
  const store = memory();
  const lines = await logged(async () => {
    await send(store, 'POST', '/v1/events', { ...BATCH, events: [BATCH.events[0], { name: 'view', calls: 0 }] });
    await send(store, 'POST', '/v1/events', { ...BATCH, version: '0.9.1', next_thing: 1 }); // a newer release's field
    await send(store, 'POST', '/v1/events', '{');
    await send(store, 'POST', '/v1/forget', { install: 'someone@example.com' });
    await send(store, 'POST', '/v1/events', BATCH, { origin: 'https://example.com' });
    await send(store, 'POST', '/v1/events', BATCH); // taken: nothing to say
  });
  assert.deepEqual(lines.warn, [
    'telemetry /v1/events refused 400: events[1].calls counts nothing (schema 3, cadgen 0.8.0)',
    'telemetry /v1/events refused 400: unknown field next_thing (schema 3, cadgen 0.9.1)',
    'telemetry /v1/events refused 400: the body is not JSON',
    'telemetry /v1/forget refused 400: not an install id',
    'telemetry /v1/events refused 403: not from a browser',
  ]);
  assert.deepEqual(lines.error, []);
});

test('what a refusal logs carries nothing of the request\'s choosing: no key, value, version or path', async () => {
  const secrets = ['/Users/someone/secret.step', 'someone@example.com', '8c347ec3-1342-4db5-a19a-491cbc8c5900', 'secret bracket'];
  const store = memory();
  const lines = await logged(async () => {
    for (const secret of secrets) {
      for (const bad of [
        { ...BATCH, [secret]: 1 }, // an unknown key is the caller's to name
        { ...BATCH, version: secret },
        { ...BATCH, platform: secret },
        { ...BATCH, channel: secret },
        { ...BATCH, events: [{ name: 'tool', tool: secret, calls: 1 }] },
        { ...BATCH, events: [{ name: 'tool', tool: 'cad_show', calls: 1, [secret]: 1 }] },
        { ...BATCH, events: [{ ...CRASH, frames: [{ file: secret, function: 'make' }] }] },
        { ...BATCH, events: [{ ...CRASH, frames: [{ ...CRASH.frames[0], [secret]: 1 }] }] },
        { ...BATCH, client: { [secret]: 1 } },
        { ...BATCH, schema: secret },
        { ...BATCH, install: secret },
      ]) await send(store, 'POST', '/v1/events', bad);
      await send(store, 'POST', '/v1/events', BATCH, { origin: secret });
      await send(store, 'POST', `/v1/${secret}`, BATCH, { 'content-type': secret }); // refused on its type, at a path of its own
    }
  });
  assert.ok(lines.warn.length > 40);
  for (const line of lines.warn) for (const secret of secrets) assert.ok(!line.includes(secret), line);
  assert.ok(lines.warn.includes('telemetry request refused 415: the body must be application/json'));
});

test('a failed request is logged by its name or code, never a number or a message', async () => {
  const timeout = new DOMException('The operation was aborted due to timeout', 'TimeoutError');
  assert.equal(timeout.code, 23); // the legacy number a DOMException carries, which says nothing
  const cases = [
    [timeout, 'TimeoutError'],
    [Object.assign(new Error('PostHog answered 503 for 8c347ec3-1342-4db5-a19a-491cbc8c59be'), { code: 'posthog_503' }), 'posthog_503'],
    [new TypeError('fetch failed for someone@example.com'), 'TypeError'],
  ];
  for (const [failure, name] of cases) {
    const store = { ...memory(), async forget() { throw failure; } };
    const lines = await logged(async () => {
      assert.equal((await send(store, 'POST', '/v1/forget', { install: INSTALL })).status, 500);
    });
    assert.deepEqual(lines.error, [`telemetry request failed: ${name}`]);
  }
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

test('forgetting is limited per address and per install id: past five in ten minutes, 429 with Retry-After and no deletion', async () => {
  const warn = mock.method(console, 'warn', () => {});
  try {
    let at = 0;
    const limiter = rateLimiter({ now: () => at });
    const forgotten = [];
    const store = { ...memory(), async forget(id) { forgotten.push(id); } };
    const forget = (install, client) => handle(new Request('https://api.texttocad.dev/v1/forget', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ install }),
    }), store, { limiter, client });
    for (let i = 0; i < 5; i += 1) assert.equal((await forget(INSTALL, '203.0.113.7')).status, 204);
    const refused = await forget(INSTALL, '203.0.113.7');
    assert.deepEqual([refused.status, refused.headers.get('retry-after'), await refused.json()], [429, '600', { error: 'too many requests' }]);
    assert.equal(forgotten.length, 5);
    // The same id from anywhere else is still limited; another id from another address is not.
    assert.equal((await forget(INSTALL, '198.51.100.1')).status, 429);
    const other = '6f0c6a52-3a1e-4f43-9a7e-1d2b3c4d5e6f';
    assert.equal((await forget(other, '198.51.100.2')).status, 204);
    // One address cannot spend the key on many ids.
    for (let i = 0; i < 4; i += 1) await forget(other.replace(/.$/, String(i)), '192.0.2.9');
    assert.equal((await forget(other.replace(/.$/, '9'), '192.0.2.9')).status, 204);
    assert.equal((await forget(other.replace(/.$/, '8'), '192.0.2.9')).status, 429);
    assert.equal(warn.mock.calls.at(-1).arguments[0], 'telemetry /v1/forget refused 429: too many requests');
    at += 600_000;
    assert.equal((await forget(INSTALL, '203.0.113.7')).status, 204);
  } finally {
    warn.mock.restore();
  }
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
  const reply = await handle(new Request('https://api.texttocad.dev/v1/versions/'), down, { versions: async () => feed, missing: ['POSTHOG_REGION'] });
  assert.deepEqual([reply.status, reply.headers.get('content-type'), await reply.json()], [200, 'application/json', feed]);
  assert.equal(reply.headers.get('cache-control'), 'public, s-maxage=3600, stale-while-revalidate=86400, stale-if-error=604800');
  // No feed to give: an error the edge keeps nowhere, which a released cadgen takes as a check that failed.
  const none = await handle(new Request('https://api.texttocad.dev/v1/versions'), down, { versions: async () => null });
  assert.deepEqual([none.status, none.headers.get('cache-control')], [503, 'no-store']);
});

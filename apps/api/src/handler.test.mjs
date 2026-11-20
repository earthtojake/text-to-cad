import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import { idOf, uuidV5 } from './events.mjs';
import { handle } from './handler.mjs';
import { INSTALL_LIMIT, rateLimiter } from './limit.mjs';

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

// A store in memory: the rows each batch passed on, and the country each came with; and each report of a failed
// install, with its country.
function memory() {
  const rows = [];
  const countries = [];
  const reports = [];
  return {
    rows,
    countries,
    reports,
    async insert(batch, { country }) { rows.push(...batch); countries.push(country); },
    async report(report, { country }) { reports.push({ report, country }); },
    async forget(id) { for (let i = rows.length - 1; i >= 0; i -= 1) if (rows[i].install_id === id) rows.splice(i, 1); },
    async ready() {},
  };
}
const send = (store, method, path, body, headers = {}, country = 'DE') => handle(new Request(`https://api.texttocad.dev${path}`, {
  method, headers: { 'content-type': 'application/json', ...headers }, body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
}), store, { country });

const CONTEXT = ['install_id', 'session_id', 'version', 'channel', 'app', 'legacy_channel', 'source', 'process', 'platform', 'arch',
  'client', 'client_version', 'presentation'];
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

test("an older release's channel is stored as the delivery channel and app it was, and as it was sent", async () => {
  // [as sent, channel, app], where the batch's MCP client names no app.
  const families = [
    ['claude-install', 'default', 'claude-code'], ['codex-install', 'default', 'codex'], ['cursor-install', 'default', 'cursor'],
    ['gemini-install', 'default', 'gemini'], ['claude-github', 'default', 'claude-code'], ['codex-github', 'default', 'codex'],
    ['cursor-github', 'default', 'cursor'], ['gemini-github', 'default', 'gemini'], ['claude-desktop', 'default', 'claude-desktop'],
    ['agent-plugins', 'default', 'unknown'], ['claude-directory', 'claude', 'claude-code'], ['openai-directory', 'codex', 'codex'],
    ['cursor-marketplace', 'default', 'cursor'], ['dev', 'dev', 'unknown'], ['unknown', 'unknown', 'unknown'],
  ];
  for (const [sent, channel, app] of families) {
    for (const batch of [{ ...CONTROLS, schema: 8, channel: sent }, { ...BATCH, channel: sent, client: undefined }]) {
      const store = memory();
      assert.equal((await send(store, 'POST', '/v1/events', batch)).status, 204, sent);
      assert.ok(store.rows.length > 0, sent);
      assert.deepEqual([...new Set(store.rows.map(row => `${row.channel} ${row.app} ${row.legacy_channel}`))], [`${channel} ${app} ${sent}`]);
    }
  }
  // Schema 1 named no channel: its rows keep how the install was made, and say so of the channel.
  const first = memory();
  assert.equal((await send(first, 'POST', '/v1/events', { ...SCHEMA_1, client: undefined })).status, 204);
  assert.ok(first.rows.every(row => row.channel === 'unknown' && row.app === 'unknown' && row.legacy_channel === 'unknown'
    && row.source === 'store'));
  // The old list is checked as ever.
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', { ...BATCH, channel: 'claude-somewhere' })).status, 400);
  assert.equal((await send(store, 'POST', '/v1/events', { ...BATCH, channel: 'default' })).status, 400, "schema 11's word, not 10's");
  assert.deepEqual(store.rows, []);
});

test("an older batch's app is its MCP client's first, and the old channel's only where the client names none", async () => {
  for (const [client, sent, app] of [
    ['codex-mcp-client', 'claude-directory', 'codex'], // the directory's copy, run by Codex
    ['cursor-vscode', 'codex-install', 'cursor'], ['claude-code', 'cursor-github', 'claude-code'], ['claude-ai', 'claude-github', 'claude-desktop'],
    ['gemini-cli', 'agent-plugins', 'gemini'], ['grok-build', 'agent-plugins', 'grok'], // as Gemini CLI and Grok Build call themselves
    ['Visual-Studio-Code', 'agent-plugins', 'vscode'], // VS Code's name as an older sender carried it, its spaces made `-`
    ['Zed:Agent', 'agent-plugins', 'zed-agent'], // any other client is its own app, made a token
    ['unknown', 'gemini-install', 'gemini'], // a client that says nothing
    ['cad-viewer', 'codex-install', 'codex'], ['cadgen-viewer', 'claude-desktop', 'claude-desktop'], // the browser viewer's page names no app
  ]) {
    const store = memory();
    assert.equal((await send(store, 'POST', '/v1/events', { ...BATCH, channel: sent, client: { name: client } })).status, 204, client);
    assert.deepEqual([store.rows[0].app, store.rows[0].client], [app, client], client);
  }
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

// Schema 9: which part of a snapshot's request a refusal named, and the machine's no OpenGL context and no kernel.
const PARTS = {
  ...ENGINE, schema: 9, batch: '9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d',
  events: [
    { name: 'snapshot', kind: 'model', count: 4, failed: 4, seconds: 1.5 },
    { name: 'snapshot_failure', kind: 'model', reason: 'bad_request', part: 'display.clip', count: 1 },
    { name: 'snapshot_failure', kind: 'model', reason: 'bad_request', part: 'camera', count: 1 },
    { name: 'snapshot_failure', kind: 'model', reason: 'no_gl', part: 'none', count: 1 },
    { name: 'snapshot_failure', kind: 'model', reason: 'no_kernel', part: 'none', count: 1 },
    { name: 'build', kind: 'model', via: 'script', count: 1, failed: 1, crashed: 0, cancelled: 0, cached: 0, seconds: 0.2, longest: 0.2 },
    { name: 'build_failure', kind: 'model', via: 'script', reason: 'no_kernel', count: 1 },
  ],
};

test('schema 9 names the part of a request a snapshot refused, and why the machine could not draw or build', async () => {
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', PARTS)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    PARTS.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  // One row per part: a refusal of the clip and one of the camera are told apart.
  assert.equal(new Set(store.rows.map(row => row.id)).size, PARTS.events.length);
  // Every schema before it is read as ever: no part, and the same row ids a batch sent again had.
  for (const earlier of [SCHEMA_1, SCHEMA_2, BATCH, { ...BATCH, schema: 4 }, NAMED, ENGINE, CONTROLS, { ...CONTROLS, schema: 8 }]) {
    const kept = memory();
    assert.equal((await send(kept, 'POST', '/v1/events', earlier)).status, 204, `schema ${earlier.schema}`);
    assert.ok(kept.rows.every(row => row.part === undefined), `schema ${earlier.schema}`);
  }
  const old = memory();
  assert.equal((await send(old, 'POST', '/v1/events', ENGINE)).status, 204);
  assert.equal(old.rows.find(row => row.event === 'snapshot_failure').id, idOf(ENGINE.batch, 'snapshot_failure xbf render_error'));
  const failure = PARTS.events[1];
  for (const bad of [
    { ...ENGINE, schema: 8, events: [failure] }, // schema 8 named no part
    { ...ENGINE, schema: 8, events: [{ ...ENGINE.events[4], reason: 'no_gl' }] }, // nor these reasons
    { ...ENGINE, schema: 8, events: [{ ...ENGINE.events[1], reason: 'no_kernel' }] },
    { ...PARTS, events: [{ ...failure, part: undefined }] }, // schema 9 always does
    { ...PARTS, events: [{ ...failure, part: 'display.clip.at' }] }, // a word outside the vocabulary
    { ...PARTS, events: [{ ...failure, part: '{"axis": "w"}' }] }, // never the value
    { ...PARTS, events: [{ ...failure, part: 'none' }] }, // a refusal names its part
    { ...PARTS, events: [{ ...PARTS.events[3], part: 'camera' }] }, // and only a refusal does
    { ...PARTS, events: [{ ...PARTS.events[6], reason: 'no_gl' }] }, // no_gl is a snapshot's
    { ...PARTS, events: [failure, failure] }, // one kind, reason and part, counted once
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(bad)))).status, 400, JSON.stringify(bad));
});

test('schema 10 names a CAD tool call the engine could start no kernel process for, and no schema before it does', async () => {
  const failure = { name: 'tool_failure', tool: 'cad_show', reason: 'no_kernel', count: 2 };
  const batch = { ...PARTS, schema: 10, events: [{ name: 'tool', tool: 'cad_show', calls: 3, errors: 2 }, failure] };
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', batch)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    batch.events.map(({ name, ...counts }) => ({ event: name, ...counts })));
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...batch, schema: 9 })).status, 400);
  // Schema 9's own batch is read as ever under 10.
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...PARTS, schema: 10 })).status, 204);
});

test('schema 10 names a build the server did without an option the library asked, being older, and no schema before it does', async () => {
  const exported = [{ name: 'build', kind: 'stl', via: 'command', count: 1, failed: 1, crashed: 0, cancelled: 0, cached: 0,
    seconds: 0.5, longest: 0.5 }, { name: 'build_failure', kind: 'stl', via: 'command', reason: 'outdated', count: 1 }];
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', { ...PARTS, schema: 10, events: exported })).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields).at(-1),
    { event: 'build_failure', kind: 'stl', via: 'command', reason: 'outdated', count: 1 });
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...PARTS, schema: 9, events: exported })).status, 400);
});

test("schema 10's crash of no kernel process says which failure it was, a word of the vocabulary, and no other crash does", async () => {
  const frames = [{ file: 'cad/engine/places.py', function: 'kernel', line: 728 }];
  const unavailable = { name: 'exception', where: 'tool', tool: 'cad_show', type: 'cad.engine.serve.KernelProcessesUnavailable',
    handled: true, frames, count: 1 };
  const batch = { ...PARTS, schema: 10, events: [{ ...unavailable, cause: 'resolve' }, { ...unavailable, cause: 'pool' }, CRASH] };
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', batch)).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf).map(({ id, at, ...fields }) => fields),
    batch.events.map(({ name, ...crash }) => ({ event: name, ...crash })));
  // Two causes are two crashes; a crash without one is keyed, and so given its id, as before.
  assert.equal(new Set(store.rows.map(row => row.id)).size, 3);
  const before = memory();
  assert.equal((await send(before, 'POST', '/v1/events', { ...PARTS, schema: 9, events: [CRASH] })).status, 204);
  assert.equal(store.rows[2].id, before.rows[0].id);
  for (const bad of [
    { ...batch, schema: 9, events: [{ ...unavailable, cause: 'resolve' }] }, // schema 9 named no cause
    { ...batch, events: [{ ...unavailable, cause: 'uv could not resolve cad==0.11.9' }] }, // never its words
    { ...batch, events: [{ ...unavailable, cause: 'disk' }] }, // a word outside the vocabulary
    { ...batch, events: [{ ...CRASH, cause: 'pool' }] }, // only that crash names one
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', bad)).status, 400, JSON.stringify(bad));
});

// Schema 11: the install as one field, the agent app; no channel.
const PINNED = { ...PARTS, schema: 11, channel: undefined, app: 'claude-code', client: { name: 'claude-code', version: '2.1.0' } };

test('schema 11 names the agent app, checked by its shape, never against a list, and no channel', async () => {
  for (const app of ['codex', 'claude-code', 'unknown', 'cursor', 'visual-studio-code', 'someone.else_2']) {
    const store = memory();
    assert.equal((await send(store, 'POST', '/v1/events', { ...PINNED, app })).status, 204, app);
    assert.ok(store.rows.every(row => row.app === app && row.channel === null && row.legacy_channel === null), app);
  }
  // Named, so a batch sent again keeps its ids, made as every named schema's are.
  const store = memory();
  await send(store, 'POST', '/v1/events', PINNED);
  assert.equal(store.rows[0].id, idOf(PINNED.batch, `snapshot ${PINNED.events[0].kind}`));
  for (const bad of [
    { ...PINNED, app: undefined }, // always
    { ...PINNED, app: 'Claude Code' }, { ...PINNED, app: 'a'.repeat(41) }, { ...PINNED, app: '/Users/someone' },
    { ...PINNED, app: '' }, { ...PINNED, app: 7 },
    { ...PINNED, channel: 'claude' }, // only a development build sent one, and no release: refused as any unknown field
    { ...PINNED, legacy_channel: 'claude-directory' }, // the receiver's word, never a sender's
    { ...PINNED, source: 'store' },
    { ...PINNED, schema: 10 }, // schema 10 sends no app
  ]) assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(bad)))).status, 400, JSON.stringify(bad).slice(0, 120));
});

// Schema 11's arrival: one step of how a computer got to the sending version, from the sender a command starts.
const ARRIVING = { ...PINNED, process: 'cli', client: undefined, presentation: undefined, app: 'unknown' };
const arrival = fields => ({ name: 'arrival', route: 'updater', from: '0.11.10', count: 1, ...fields });

test('schema 11 counts how a computer got to a version: each step, its ending, and why one failed, in words of its own', async () => {
  const shapes = [
    { step: 'setup', outcome: 'ok' },
    ...['uv', 'network', 'denied', 'other'].map(reason => ({ step: 'setup', outcome: 'failed', reason })),
    { step: 'serving', outcome: 'ok', route: 'setup', from: 'none' },
    ...['done', 'gave_up', 'superseded'].map(outcome => ({ step: 'handover', outcome, attempts: 3 })),
    ...['no_report', 'setup', 'app', 'other'].map(reason => ({ step: 'handover', outcome: 'failed', reason, attempts: 1 })),
    { step: 'handover', outcome: 'done', attempts: 0, from: '0.11.11-dev.20261115120000' },
    { step: 'handover', outcome: 'done', attempts: 1000 },
  ];
  const store = memory();
  const batch = { ...ARRIVING, events: shapes.map(arrival) };
  assert.equal((await send(store, 'POST', '/v1/events', JSON.parse(JSON.stringify(batch)))).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf), shapes.map(shape => ({
    id: idOf(batch.batch, `arrival ${JSON.stringify([shape.step, shape.route ?? 'updater', shape.from ?? '0.11.10', shape.outcome,
      shape.reason ?? null, shape.attempts ?? null])}`),
    at: batch.at, event: 'arrival', step: shape.step, route: shape.route ?? 'updater', from: shape.from ?? '0.11.10',
    outcome: shape.outcome, reason: shape.reason ?? null, attempts: shape.attempts ?? null, count: 1,
  })));
  assert.ok(store.rows.every(row => row.process === 'cli' && row.version === ARRIVING.version));
  for (const bad of [
    arrival({ step: 'install', outcome: 'ok' }), // an unknown step
    arrival({ step: 'setup', outcome: 'done' }), // a hand-over's ending on a setup
    arrival({ step: 'serving', outcome: 'failed', reason: 'other' }), // a first serving only happens
    arrival({ step: 'setup', outcome: 'ok', reason: 'network' }), // a reason without `failed`
    arrival({ step: 'setup', outcome: 'failed' }), // `failed` without a reason
    arrival({ step: 'setup', outcome: 'failed', reason: 'no_report' }), // a hand-over's reason on a setup
    arrival({ step: 'setup', outcome: 'failed', reason: 'uv could not reach pypi.org' }), // never its words
    arrival({ step: 'setup', outcome: 'ok', attempts: 1 }), // attempts on a step that has none
    arrival({ step: 'handover', outcome: 'done' }), // a hand-over's attempts, always
    ...[-1, 1.5, 1001, '3', true].map(attempts => arrival({ step: 'handover', outcome: 'done', attempts })),
    ...['/Users/someone/cad', 'latest', 'v0.11.10', '0.11.10 beta', '', '1'.repeat(33), null, 11].map(from =>
      arrival({ step: 'setup', outcome: 'ok', from })), // a `from` that is no version's name
    arrival({ step: 'setup', outcome: 'ok', route: 'store' }),
    { ...arrival({ step: 'setup', outcome: 'ok' }), route: undefined },
    { ...arrival({ step: 'setup', outcome: 'ok' }), path: '/tmp' }, // nothing else
    arrival({ step: 'setup', outcome: 'ok', count: 0 }),
  ]) {
    const body = JSON.parse(JSON.stringify({ ...ARRIVING, events: [bad] }));
    assert.equal((await send(memory(), 'POST', '/v1/events', body)).status, 400, JSON.stringify(bad));
  }
  // One step once per batch; and no schema before 11 sends one.
  const twice = { ...ARRIVING, events: [arrival({ step: 'setup', outcome: 'ok' }), arrival({ step: 'setup', outcome: 'ok' })] };
  assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(twice)))).status, 400);
  const older = { ...PARTS, schema: 10, process: 'cli', events: [arrival({ step: 'setup', outcome: 'ok' })] };
  assert.equal((await send(memory(), 'POST', '/v1/events', older)).status, 400);
});

// Schema 11's update: one attempt of cad's own update of itself that ended, counted by the server after it.
const update = fields => ({ name: 'update', from: '0.11.12', outcome: 'installed', tries: 1, installer: 'uv', asked: false,
  plugin: 'none', count: 1, ...fields });

test("schema 11 counts each of cad's own updates: how it ended, which step failed, the installer, typed or not, and the install command after it", async () => {
  const shapes = [
    ...['none', 'ok', 'failed', 'underway'].map(plugin => ({ plugin })),
    { outcome: 'current', asked: true, installer: 'pipx' },
    ...['upgrade', 'older', 'put_back'].map(reason => ({ outcome: 'failed', reason, tries: 2 })),
    ...['upgrade', 'older'].map(reason => ({ outcome: 'restored', reason, asked: true })),
    { from: '0.11.12-dev.20261118120000', tries: 1000 },
  ];
  const store = memory();
  const batch = { ...ARRIVING, events: shapes.map(update) };
  assert.equal((await send(store, 'POST', '/v1/events', JSON.parse(JSON.stringify(batch)))).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf), shapes.map(update).map(({ name, ...shape }) => ({
    id: idOf(batch.batch, `update ${JSON.stringify([shape.from, shape.outcome, shape.reason ?? null, shape.tries, shape.installer,
      shape.asked, shape.plugin])}`),
    at: batch.at, event: 'update', ...shape, reason: shape.reason ?? null,
  })));
  for (const bad of [
    update({ outcome: 'updated' }), // an unknown ending
    update({ outcome: 'failed' }), // a failure names its step
    update({ outcome: 'failed', reason: 'network' }), // a word cad has not
    update({ outcome: 'failed', reason: 'uv could not reach pypi.org' }), // never its words
    update({ outcome: 'restored', reason: 'put_back' }), // put back: the put-back did not fail
    update({ reason: 'upgrade' }), // a reason without a failure
    update({ outcome: 'current', plugin: 'ok' }), // the install command after an update that installed nothing newer
    update({ outcome: 'failed', reason: 'upgrade', plugin: 'failed' }),
    update({ outcome: 'current', plugin: 'underway' }),
    ...[0, -1, 1.5, 1001, '2', true].map(tries => update({ tries })),
    update({ installer: 'pip' }), update({ installer: undefined }),
    ...['yes', 1, null].map(asked => update({ asked })), update({ asked: undefined }),
    update({ plugin: 'skipped' }), update({ plugin: undefined }),
    ...['/Users/someone/cad', 'latest', '', null].map(from => update({ from })),
    { ...update({}), path: '/tmp' }, // nothing else
    update({ count: 0 }),
  ]) {
    const body = JSON.parse(JSON.stringify({ ...ARRIVING, events: [bad] }));
    assert.equal((await send(memory(), 'POST', '/v1/events', body)).status, 400, JSON.stringify(bad));
  }
  // One attempt's shape once per batch; and no schema before 11 sends one.
  const twice = { ...ARRIVING, events: [update({}), update({})] };
  assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(twice)))).status, 400);
  const older = { ...PARTS, schema: 10, process: 'cli', events: [update({})] };
  assert.equal((await send(memory(), 'POST', '/v1/events', older)).status, 400);
});

// Schema 12: schema 11 with the plugin's install in the agent apps, which cad runs itself (`cad plugin install`).
const INSTALLING = { ...ARRIVING, schema: 12, app: 'claude-code' };
const install = fields => ({ name: 'install', by: 'person', outcome: 'ok', logo: 'played', colour: '24bit', seconds: 42, found: 3,
  failed: 1, count: 1, ...fields });

test("schema 12 counts each run of the plugin's install: who began it, how it ended, what its terminal showed, and the apps found and failed", async () => {
  const shapes = [
    {},
    ...['script', 'server'].map(by => ({ by })),
    ...['still', 'none', 'failed'].map(logo => ({ logo })),
    ...['256', 'none'].map(colour => ({ colour })),
    { outcome: 'failed', found: 2, failed: 2 },
    { outcome: 'failed', found: 1, failed: 1, seconds: 100000 },
    { outcome: 'busy', by: 'server', logo: 'none', colour: 'none', seconds: 0, found: 0, failed: 0 },
    // Its deadline stopped it: what it had found by then, whatever that was -- some done, every one failed, or none.
    { outcome: 'stopped', by: 'server', logo: 'none', colour: 'none', seconds: 900 },
    { outcome: 'stopped', by: 'server', found: 2, failed: 2 },
    { outcome: 'stopped', by: 'server', found: 4, failed: 0 },
    { outcome: 'stopped', by: 'server', found: 0, failed: 0 },
    { found: 0, failed: 0 }, // no app here: a run that ended well
    { found: 64, failed: 63 },
    { seconds: 0, count: 2 },
  ];
  const store = memory();
  const batch = { ...INSTALLING, events: shapes.map(install) };
  assert.equal((await send(store, 'POST', '/v1/events', JSON.parse(JSON.stringify(batch)))).status, 204);
  assert.deepEqual(store.rows.map(fieldsOf), shapes.map(install).map(({ name, ...shape }) => ({
    id: idOf(batch.batch, `install ${JSON.stringify([shape.by, shape.outcome, shape.logo, shape.colour, shape.seconds, shape.found,
      shape.failed])}`),
    at: batch.at, event: 'install', ...shape,
  })));
  assert.ok(store.rows.every(row => row.process === 'cli' && row.app === 'claude-code' && row.channel === null));
  for (const bad of [
    install({ by: 'cad' }), install({ by: undefined }), // who began it, in cad's three words
    install({ outcome: 'crashed' }), install({ outcome: undefined }),
    install({ logo: 'shown' }), install({ logo: undefined }),
    install({ colour: 'truecolor' }), install({ colour: 256 }), install({ colour: undefined }),
    ...[-1, 1.5, 100001, '42', null].map(seconds => install({ seconds })), install({ seconds: undefined }),
    ...[-1, 1.5, 65, '3', null].map(found => install({ found, failed: 0 })), install({ found: undefined }),
    ...[-1, 1.5, '1', null].map(failed => install({ failed })), install({ failed: undefined }),
    install({ found: 2, failed: 3 }), // more failures than apps found
    install({ outcome: 'failed' }), // a run failed where every app found failed: here one of three
    install({ outcome: 'failed', found: 0, failed: 0 }), // and at least one was found
    install({ found: 2, failed: 2 }), // every app found failed: never a run that ended well
    install({ outcome: 'busy' }), // a run that found the lock held looked for no app
    install({ outcome: 'stopped', found: 2, failed: 3 }), // a stopped run too: never more failures than apps found
    { ...install({}), reason: 'network' }, // an app's word, never a run's
    { ...install({}), path: '/Users/someone/.claude' }, // nothing else
    install({ count: 0 }), install({ count: undefined }),
  ]) {
    const body = JSON.parse(JSON.stringify({ ...INSTALLING, events: [bad] }));
    assert.equal((await send(memory(), 'POST', '/v1/events', body)).status, 400, JSON.stringify(bad));
  }
  // One run's shape once per batch; and no schema before 12 sends one.
  const twice = { ...INSTALLING, events: [install({}), install({})] };
  assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(twice)))).status, 400);
  for (const older of [{ ...ARRIVING, events: [install({})] }, { ...PARTS, schema: 10, process: 'cli', events: [install({})] }]) {
    assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(older)))).status, 400, `schema ${older.schema}`);
  }
});

const installFailure = fields => ({ name: 'install_failure', app: 'claude', reason: 'timeout', seconds: 7, count: 1, ...fields });

test("schema 12 names an app only where the plugin's install failed: which, why, its seconds, the batch's own app beside it", async () => {
  const shapes = [
    {},
    ...['command', 'network', 'exception', 'other'].map(reason => ({ reason })),
    { app: 'claude-desktop' },
    { app: 'someone.else_2', seconds: 0 }, // an open set, checked by its shape
    { app: 'codex', seconds: 100000, count: 3 },
  ];
  const store = memory();
  const batch = { ...INSTALLING, events: shapes.map(installFailure) };
  assert.equal((await send(store, 'POST', '/v1/events', JSON.parse(JSON.stringify(batch)))).status, 204);
  // A row names the app where the install failed `plugin_app`: its `app` stays the batch's, the app running cad.
  assert.deepEqual(store.rows.map(fieldsOf), shapes.map(installFailure).map(shape => ({
    id: idOf(batch.batch, `install_failure ${JSON.stringify([shape.app, shape.reason, shape.seconds])}`),
    at: batch.at, event: 'install_failure', plugin_app: shape.app, reason: shape.reason, seconds: shape.seconds,
    count: shape.count,
  })));
  assert.ok(store.rows.every(row => row.app === 'claude-code' && row.process === 'cli'));
  for (const bad of [
    ...['Claude Code', '/Users/someone/.claude', 'a'.repeat(41), '', 7, null].map(app => installFailure({ app })),
    installFailure({ app: undefined }),
    installFailure({ reason: undefined }), installFailure({ reason: null }), // a failure always names why
    installFailure({ reason: 'denied' }), // a word cad has not
    installFailure({ reason: 'claude plugin install exited 1' }), // never its words
    ...['failed', 'installed', 'updated', 'skipped'].map(status => installFailure({ status })), // no status: it failed
    ...[-1, 1.5, 100001, '7', null].map(seconds => installFailure({ seconds })), installFailure({ seconds: undefined }),
    { ...installFailure({}), plugin_app: 'claude' }, // the receiver's word, never a sender's
    { ...installFailure({}), path: '/Users/someone/.claude/plugins' }, // nothing else
    installFailure({ count: 0 }), installFailure({ count: undefined }),
  ]) {
    const body = JSON.parse(JSON.stringify({ ...INSTALLING, events: [bad] }));
    assert.equal((await send(memory(), 'POST', '/v1/events', body)).status, 400, JSON.stringify(bad));
  }
  // An app done well is never named: the kind of row that did is no kind at all.
  for (const app of [{ name: 'install_app', app: 'claude', status: 'installed', seconds: 7, count: 1 },
    { name: 'install_app', app: 'codex', status: 'failed', reason: 'timeout', seconds: 7, count: 1 }]) {
    const body = { ...INSTALLING, events: [app] };
    assert.equal((await send(memory(), 'POST', '/v1/events', body)).status, 400, JSON.stringify(app));
  }
  // One failure's shape once per batch; and no schema before 12 sends one.
  const twice = { ...INSTALLING, events: [installFailure({}), installFailure({})] };
  assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(twice)))).status, 400);
  for (const older of [{ ...ARRIVING, events: [installFailure({})] }, { ...PARTS, schema: 10, process: 'cli', events: [installFailure({})] }]) {
    assert.equal((await send(memory(), 'POST', '/v1/events', JSON.parse(JSON.stringify(older)))).status, 400, `schema ${older.schema}`);
  }
});

test('schema 12 reads everything schema 11 does, its rows keyed alike, and a schema 11 batch is read as ever', async () => {
  // A run and the app where it failed beside what a schema 11 batch counts: one batch, one row each.
  const mixed = { ...INSTALLING, events: [install({ found: 2, failed: 1 }), installFailure({ app: 'codex' }),
    arrival({ step: 'setup', outcome: 'ok' }), update({}), ...PINNED.events] };
  const store = memory();
  assert.equal((await send(store, 'POST', '/v1/events', JSON.parse(JSON.stringify(mixed)))).status, 204);
  assert.deepEqual(store.rows.map(row => row.event), mixed.events.map(event => event.name));
  const [eleven, twelve] = [memory(), memory()];
  assert.equal((await send(eleven, 'POST', '/v1/events', PINNED)).status, 204);
  assert.equal((await send(twelve, 'POST', '/v1/events', { ...PINNED, schema: 12 })).status, 204);
  assert.deepEqual(twelve.rows, eleven.rows);
  // Up to 256 events, as every schema from 7.
  const many = Array.from({ length: 257 }, (_, index) => installFailure({ seconds: index }));
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...INSTALLING, events: many.slice(0, 256) })).status, 204);
  assert.equal((await send(memory(), 'POST', '/v1/events', { ...INSTALLING, events: many })).status, 400);
});

test('a schema newer than the receiver reads is "try later", never refused: the sender keeps it for when it does', async () => {
  // A release can reach people before the receiver that reads its schema is deployed: its batches wait, not lost.
  const store = memory();
  const lines = await logged(async () => {
    for (const schema of [13, 40]) {
      const later = await send(store, 'POST', '/v1/events', { ...PINNED, schema, somethingNew: true });
      assert.deepEqual([later.status, later.headers.get('retry-after'), await later.json()],
        [503, '3600', { error: 'schema not read yet' }], `schema ${schema}`);
    }
  });
  assert.deepEqual(store.rows, []);
  assert.deepEqual(lines.warn, ['telemetry /v1/events deferred 503: a schema newer than this receiver reads (schema 13, release 0.8.0)',
    'telemetry /v1/events deferred 503: a schema newer than this receiver reads (schema 40, release 0.8.0)']);
  // Anything else unknown is refused as ever: a schema that is not a whole number, or one no release sent.
  for (const schema of [12.5, '13', 0, -1, null]) {
    assert.equal((await send(memory(), 'POST', '/v1/events', { ...PINNED, schema })).status, 400, `schema ${schema}`);
  }
  assert.equal((await send(memory(), 'POST', '/v1/events', PINNED)).status, 204);
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
  assert.deepEqual(store.rows.map(row => [row.version, row.legacy_channel, row.source, row.process, row.event, row.kind ?? null, row.count ?? null]), [
    ...expected('0.7.11', 'unknown', 'store', 'app'),
    ...expected('0.7.15', 'claude-directory', null, 'app'),
    ...expected('0.7.15', 'claude-directory', null, 'viewer'),
  ]);
  assert.ok(store.rows.every(row => !('file' in row)));
  // Translated, an older named batch keeps the row ids it had: sent twice, it is the same rows twice.
  for (const [named, key] of [[NAMED, 'build step script'], [ENGINE, 'build xbf script'], [CONTROLS, 'control pencil'],
    [PARTS, 'snapshot model'], [{ ...PARTS, schema: 10 }, 'snapshot model']]) {
    const twice = memory();
    await send(twice, 'POST', '/v1/events', named);
    await send(twice, 'POST', '/v1/events', named);
    const ids = twice.rows.map(row => row.id);
    assert.deepEqual(ids.slice(ids.length / 2), ids.slice(0, ids.length / 2), `schema ${named.schema}`);
    assert.equal(ids[0], idOf(named.batch, key), `schema ${named.schema}`);
  }
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
    'telemetry /v1/events refused 400: events[1].calls counts nothing (schema 3, release 0.8.0)',
    'telemetry /v1/events refused 400: unknown field next_thing (schema 3, release 0.9.1)',
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

// What the install command sends where a run of it failed with no working cad to count it: one report, under an id
// made for that run alone.
const RUN = '3b1f0c52-7a2e-4d0b-9c1e-5f6a7b8c9d0e';
const REPORT = { schema: 1, run: RUN, at: 1_795_000_000, stage: 'cad', outcome: 'failed', code: 2, platform: 'linux', arch: 'x86_64',
  by: 'person', uv: '0.9.7' };
// ...and where `install.py` itself crashed: the error's type, and where in the script, by function and line.
const CRASHED = { ...REPORT, stage: 'script', outcome: 'crashed', code: 1, type: 'KeyError',
  frames: [{ function: 'main', line: 2560 }, { function: 'install_cad', line: 1921 }] };
const reported = ({ schema, ...report }) => ({ id: uuidV5(`${report.run}/install_failed ${report.stage}`), ...report });

test('a failed install is one report under an id made for that run alone, with the country the host placed it in', async () => {
  const store = memory();
  const reply = await send(store, 'POST', '/v1/install', REPORT);
  assert.deepEqual([reply.status, await reply.text(), reply.headers.get('access-control-allow-origin')], [204, '', null]);
  assert.equal((await send(store, 'POST', '/v1/install/', CRASHED, {}, 'not a country')).status, 204);
  assert.deepEqual(store.reports, [{ report: reported(REPORT), country: 'DE' }, { report: reported(CRASHED), country: null }]);
  // A shell's `uuidgen` writes capitals on macOS: the same id, kept in lower case.
  const capitals = memory();
  assert.equal((await send(capitals, 'POST', '/v1/install', { ...REPORT, run: RUN.toUpperCase() })).status, 204);
  assert.deepEqual(capitals.reports[0].report, reported(REPORT));
  // Nothing of it is a batch's row, and there is nothing to read back.
  assert.deepEqual([store.rows, store.countries], [[], []]);
  assert.equal((await send(store, 'GET', '/v1/install')).status, 404);
});

test('a report of a failed install is read in every word of its vocabularies, a crash with its type and frames', async () => {
  const frame = { function: 'Live.begin', line: 2301 };
  for (const good of [
    ...['uv', 'fetch', 'python', 'cad', 'plugin', 'script'].map(stage => ({ ...REPORT, stage })),
    ...['darwin', 'linux', 'win32', 'other'].map(platform => ({ ...REPORT, platform })),
    ...['arm64', 'aarch64', 'AMD64', 'unknown'].map(arch => ({ ...REPORT, arch })),
    ...['person', 'cad'].map(by => ({ ...REPORT, by })),
    ...['none', '0.4.30', '0.10.12', '1.0.0'].map(uv => ({ ...REPORT, uv })),
    ...[0, 1, 127, 255].map(code => ({ ...REPORT, code })),
    { ...REPORT, at: 0 },
    CRASHED,
    { ...CRASHED, stage: 'cad' }, // a crash is told where the run was
    { ...CRASHED, frames: undefined }, { ...CRASHED, frames: [] }, // a crash with no frame to name
    { ...CRASHED, frames: Array(10).fill(frame) },
    { ...CRASHED, type: 'subprocess.TimeoutExpired', frames: [{ function: '<module>' }] }, // a frame with no line
  ]) {
    const store = memory();
    const body = JSON.parse(JSON.stringify(good));
    assert.equal((await send(store, 'POST', '/v1/install', body)).status, 204, JSON.stringify(good));
    assert.deepEqual(store.reports, [{ report: reported(body), country: 'DE' }]);
  }
});

test('a report of a failed install outside the contract is refused and passes nothing on', async () => {
  const store = memory();
  const frame = CRASHED.frames[0];
  for (const bad of [
    { ...REPORT, path: '/Users/someone/.local/bin/cad' }, { ...REPORT, install: INSTALL }, { ...REPORT, version: '0.11.13' },
    { ...REPORT, message: 'uv tool install cad failed' }, // nothing else, and never what it said
    ...[2, 0, '1', 1.5, null, undefined].map(schema => ({ ...REPORT, schema })),
    ...['someone@example.com', `${RUN}0`, RUN.replace(/-/g, ''), 7, undefined].map(run => ({ ...REPORT, run })),
    ...[1.5, -1, '1795000000', 1e12, undefined].map(at => ({ ...REPORT, at })),
    ...['download', 'setup', 7, undefined].map(stage => ({ ...REPORT, stage })),
    ...['ok', 'busy', undefined].map(outcome => ({ ...REPORT, outcome })),
    ...[-1, 256, 1.5, '1', undefined].map(code => ({ ...REPORT, code })),
    ...['freebsd', 'Linux', undefined].map(platform => ({ ...REPORT, platform })),
    ...['x86 64', 'a'.repeat(17), 7, undefined].map(arch => ({ ...REPORT, arch })),
    ...['script', 'server', undefined].map(by => ({ ...REPORT, by })),
    ...['0.9', 'v0.9.7', 'uv 0.9.7', '0.9.7 (abc 2026-11-01)', '0.9.7-alpha.1', '', `${'1'.repeat(16)}.${'1'.repeat(16)}.1`, 9, undefined]
      .map(uv => ({ ...REPORT, uv })),
    { ...REPORT, type: 'KeyError' }, { ...REPORT, frames: [] }, // only a crash names a type and frames
    { ...CRASHED, type: undefined }, { ...CRASHED, type: "KeyError('secret')" }, { ...CRASHED, type: 7 },
    { ...CRASHED, frames: 'main' }, { ...CRASHED, frames: Array(11).fill(frame) }, { ...CRASHED, frames: ['main'] },
    { ...CRASHED, frames: [{ ...frame, file: 'install.py' }] }, // no file names
    { ...CRASHED, frames: [{ ...frame, locals: { home: '/Users/someone' } }] },
    { ...CRASHED, frames: [{ ...frame, function: 'install cad in /Users/someone' }] }, { ...CRASHED, frames: [{ line: 3 }] },
    ...[-1, 1.5, '3', 10_000_000].map(line => ({ ...CRASHED, frames: [{ ...frame, line }] })),
  ]) assert.equal((await send(store, 'POST', '/v1/install', JSON.parse(JSON.stringify(bad)))).status, 400, JSON.stringify(bad));
  for (const body of ['{', '[]', 'null', '"cad"', '7']) assert.equal((await send(store, 'POST', '/v1/install', body)).status, 400, body);
  assert.deepEqual(store.reports, []);
});

test('a refused report of a failed install is logged by its rule alone, and one too large is not read', async () => {
  const secrets = ['/Users/someone/.local/bin/cad', 'someone@example.com', 'secret bracket'];
  const store = memory();
  const lines = await logged(async () => {
    await send(store, 'POST', '/v1/install', { ...REPORT, stage: 'download' });
    await send(store, 'POST', '/v1/install', { ...REPORT, next_thing: 1 });
    // A report is a few hundred bytes: past 4 KiB it is refused for its size, whatever it holds.
    assert.equal((await send(store, 'POST', '/v1/install', { ...CRASHED, frames: Array(200).fill(CRASHED.frames[0]) })).status, 400);
    for (const secret of secrets) {
      for (const bad of [{ ...REPORT, [secret]: 1 }, { ...REPORT, run: secret }, { ...REPORT, stage: secret }, { ...REPORT, uv: secret },
        { ...REPORT, arch: secret }, { ...CRASHED, type: secret }, { ...CRASHED, frames: [{ function: secret }] },
        { ...CRASHED, frames: [{ function: 'main', [secret]: 1 }] }]) await send(store, 'POST', '/v1/install', bad);
    }
    await send(store, 'POST', '/v1/install', REPORT); // taken: nothing to say
  });
  assert.deepEqual(lines.warn.slice(0, 3), [
    'telemetry /v1/install refused 400: stage is not one of uv, fetch, python, cad, plugin, script',
    'telemetry /v1/install refused 400: the report has an unknown field next_thing',
    'telemetry /v1/install refused 400: the report is too large',
  ]);
  assert.equal(lines.warn.length, 3 + secrets.length * 8);
  for (const line of lines.warn) for (const secret of [...secrets, RUN]) assert.ok(!line.includes(secret), line);
  assert.deepEqual([lines.error, store.reports.length], [[], 1]);
  // A batch of counts keeps its own size: 64 KiB, as ever.
  const large = { ...INSTALLING, events: Array.from({ length: 256 }, (_, index) => installFailure({ seconds: index })) };
  assert.ok(JSON.stringify(large).length > 8192);
  assert.equal((await send(memory(), 'POST', '/v1/events', large)).status, 204);
});

test('a browser cannot report a failed install, and a service that will not take one is the receiver\'s failure', async () => {
  const store = memory();
  const page = await send(store, 'POST', '/v1/install', REPORT, { origin: 'https://example.com' });
  assert.deepEqual([page.status, await page.json()], [403, { error: 'not from a browser' }]);
  const text = await send(store, 'POST', '/v1/install', REPORT, { 'content-type': 'text/plain' });
  assert.deepEqual([text.status, await text.json()], [415, { error: 'the body must be application/json' }]);
  assert.deepEqual(store.reports, []);
  const down = { ...memory(), async report() { throw Object.assign(new Error(`PostHog answered 503 for ${RUN}`), { code: 'posthog_503' }); } };
  const lines = await logged(async () => {
    const reply = await send(down, 'POST', '/v1/install', REPORT);
    assert.deepEqual([reply.status, await reply.json()], [500, { error: 'internal error' }]);
  });
  assert.deepEqual(lines.error, ['telemetry request failed: posthog_503']);
});

test('reporting a failed install is limited per address: past thirty in ten minutes, 429 with Retry-After and nothing passed on', async () => {
  const warn = mock.method(console, 'warn', () => {});
  try {
    let at = 0;
    assert.deepEqual(INSTALL_LIMIT, { limit: 30, windowMs: 600_000, size: 1000 });
    const [installLimiter, limiter] = [rateLimiter({ ...INSTALL_LIMIT, now: () => at }), rateLimiter({ now: () => at })];
    const store = memory();
    const post = (path, body, client) => handle(new Request(`https://api.texttocad.dev${path}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    }), store, { limiter, installLimiter, client });
    // A report that is refused counts too: the limit is on asking, whatever is asked.
    assert.equal((await post('/v1/install', { ...REPORT, stage: 'download' }, '203.0.113.7')).status, 400);
    for (let i = 1; i < 30; i += 1) assert.equal((await post('/v1/install', REPORT, '203.0.113.7')).status, 204);
    const refused = await post('/v1/install', REPORT, '203.0.113.7');
    assert.deepEqual([refused.status, refused.headers.get('retry-after'), await refused.json()], [429, '600', { error: 'too many requests' }]);
    assert.equal(warn.mock.calls.at(-1).arguments[0], 'telemetry /v1/install refused 429: too many requests');
    assert.equal(store.reports.length, 29);
    // Another address is not limited, nor a request the host names no address for; and forgetting keeps its own count.
    assert.equal((await post('/v1/install', REPORT, '198.51.100.1')).status, 204);
    assert.equal((await post('/v1/install', REPORT, null)).status, 204);
    assert.equal((await post('/v1/forget', { install: INSTALL }, '203.0.113.7')).status, 204);
    at += 600_000;
    assert.equal((await post('/v1/install', REPORT, '203.0.113.7')).status, 204);
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
  // Its two addresses: `/v1/releases` (cad 0.11.12 on) and the frozen `/v1/versions` (0.7.12 to 0.11.11).
  const feeds = { releases: { latest: '1.0.0', lines: { 0: '0.12.3', 1: '1.0.0' } }, versions: { latest: '0.11.14' } };
  const down = { ...memory(), async ready() { throw new Error('unreachable'); } };
  const options = { releases: async () => feeds.releases, versions: async () => feeds.versions, missing: ['POSTHOG_REGION'] };
  for (const [path, feed] of [['/v1/releases', feeds.releases], ['/v1/versions/', feeds.versions]]) {
    // Whatever the request says of itself: the same answer.
    for (const headers of [{}, { 'user-agent': 'cadgen' }, { 'user-agent': 'cad', 'x-cad-version': '0.11.3' }]) {
      const reply = await handle(new Request(`https://api.texttocad.dev${path}?release=0.11.3`, { headers }), down, options);
      assert.deepEqual([reply.status, reply.headers.get('content-type'), await reply.json()], [200, 'application/json', feed]);
      assert.equal(reply.headers.get('cache-control'), 'public, s-maxage=300, stale-while-revalidate=60, stale-if-error=604800');
      assert.equal(reply.headers.get('vary'), null);
    }
  }
  // No feed to give: an error the edge keeps nowhere, which a released cadgen takes as a check that failed.
  for (const path of ['/v1/releases', '/v1/versions']) {
    const none = await handle(new Request(`https://api.texttocad.dev${path}`), down, { releases: async () => null, versions: async () => null });
    assert.deepEqual([none.status, none.headers.get('cache-control')], [503, 'no-store']);
  }
});

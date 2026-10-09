import assert from 'node:assert/strict';
import { test } from 'node:test';
import { rowsOf } from './events.mjs';
import { EVENTS, missingSettings, posthogStore, SETTINGS, settingsOf } from './posthog.mjs';

const INSTALL = '8c347ec3-1342-4db5-a19a-491cbc8c59be';
const SESSION = '0b1e6f1a-6a52-4c39-9d43-2f5e0f0b9d11';
// What cadgen sends (cadgen/analytics.py): the CAD app's counts, and the build daemon's.
const BATCH = {
  schema: 3, install: INSTALL, session: SESSION, process: 'app', version: '0.8.0', channel: 'claude-directory', platform: 'darwin',
  arch: 'arm64', client: { name: 'codex-mcp-client', version: '0.159.0' }, presentation: 'tabs',
  events: [
    { name: 'tool', tool: 'cad_show', calls: 3, errors: 1 },
    { name: 'view', calls: 7 },
    { name: 'files', kind: 'step', count: 2 },
  ],
};
const DAEMON = {
  schema: 3, install: INSTALL, session: SESSION, process: 'daemon', version: '0.8.0', channel: 'claude-directory', platform: 'linux',
  arch: 'x86_64',
  events: [
    { name: 'build', kind: 'step', via: 'script', count: 9, failed: 2, crashed: 0, cancelled: 1, cached: 4, seconds: 31.5, longest: 12.2 },
    { name: 'snapshot', kind: 'step', count: 3, failed: 0, seconds: 7.25 },
    { name: 'feature', feature: 'assembly', count: 2 },
    { name: 'health', workers: 2, crashes: 1, recycles: 0, refusals: 0 },
  ],
};
const SETTINGS_EU = { region: 'eu', projectKey: 'phc_project', personalKey: 'phx_personal', projectId: '1234' };

// PostHog over a fetch that keeps what it was asked and answers `status`.
function posthog(status = 200) {
  const asked = [];
  const fetch = async (url, init) => {
    asked.push({ url, method: init.method ?? 'GET', headers: init.headers, body: init.body === undefined ? undefined : JSON.parse(init.body) });
    return new Response('{}', { status });
  };
  return { asked, store: posthogStore(SETTINGS_EU, { fetch }) };
}

test("each of a batch's rows is one PostHog event, under the install id, with the country and no location lookup", async () => {
  const { asked, store } = posthog();
  await store.insert(rowsOf(BATCH), { country: 'DE' });
  const [{ url, method, body }] = asked;
  assert.deepEqual([url, method, body.api_key], ['https://eu.i.posthog.com/batch/', 'POST', 'phc_project']);
  assert.deepEqual(body.batch.map(event => event.event), ['tool_used', 'view_used', 'files_shown']);
  const context = { distinct_id: INSTALL, session: SESSION, $session_id: SESSION, $geoip_disable: true, process: 'app', version: '0.8.0',
    channel: 'claude-directory', platform: 'darwin', arch: 'arm64', client: 'codex-mcp-client', client_version: '0.159.0',
    presentation: 'tabs', country: 'DE' };
  assert.deepEqual(body.batch.map(event => event.properties), [
    { ...context, tool: 'cad_show', calls: 3, errors: 1 },
    { ...context, calls: 7 },
    { ...context, kind: 'step', count: 2 },
  ]);
});

test("the build daemon's counts are PostHog events of their own, each a window's to add up", async () => {
  const { asked, store } = posthog();
  await store.insert(rowsOf(DAEMON), { country: 'NZ' });
  const { batch } = asked[0].body;
  assert.deepEqual(batch.map(event => event.event), ['models_built', 'snapshots_rendered', 'feature_used', 'daemon_health']);
  const context = { distinct_id: INSTALL, session: SESSION, $session_id: SESSION, $geoip_disable: true, process: 'daemon', version: '0.8.0',
    channel: 'claude-directory', platform: 'linux', arch: 'x86_64', country: 'NZ' };
  const countsOf = event => Object.fromEntries(Object.entries(event).filter(([key]) => key !== 'name'));
  assert.deepEqual(batch.map(event => event.properties), DAEMON.events.map(event => ({ ...context, ...countsOf(event) })));
  assert.deepEqual(Object.keys(EVENTS).sort(),
    ['build', 'exception', 'feature', 'files', 'health', 'snapshot', 'tool', 'tool_failure', 'view']);
});

test("why a tool's calls failed is PostHog's tool_failed, by tool and reason, to break down and add up", async () => {
  const { asked, store } = posthog();
  const failure = { name: 'tool_failure', tool: 'cad_screenshot', reason: 'timeout', count: 2 };
  await store.insert(rowsOf({ ...BATCH, schema: 4, events: [failure] }));
  const [event] = asked[0].body.batch;
  assert.equal(event.event, 'tool_failed');
  assert.deepEqual([event.properties.tool, event.properties.reason, event.properties.count, event.properties.process],
    ['cad_screenshot', 'timeout', 2, 'app']);
});

test("a crash is PostHog's $exception: its type and frames, only cadgen's in the app, and no message", async () => {
  const { asked, store } = posthog();
  const frames = [{ file: 'cadgen/mcp/server.py', function: 'Server._call', line: 421 }, { file: '<user>', function: '<user>', line: 0 },
    { file: 'json/decoder.py', function: 'JSONDecoder.decode', line: 345 }];
  await store.insert(rowsOf({ ...BATCH, events: [
    { name: 'exception', where: 'tool', tool: 'cad_show', type: 'KeyError', handled: true, frames, count: 2 },
    { name: 'exception', where: 'build', type: 'WorkerDied', handled: false, status: -11, frames: [], count: 1 },
    { name: 'exception', where: 'build', type: 'WorkerDied', handled: false, status: 0xC0000409, frames: [], count: 1 },
    { name: 'exception', where: 'page', type: 'TypeError', handled: false, count: 1,
      frames: [{ file: 'assets/index-Bx3k2.js', function: 'Kt', line: 1, column: 48213, chunk_id: '0de4d024-c159-4f6d-b15a-cc4ef7a6856d' }] },
  ] }), { country: 'DE' });
  const [tool, worker, fault, page] = asked[0].body.batch;
  assert.deepEqual([tool.event, worker.event, page.event], ['$exception', '$exception', '$exception']);
  assert.deepEqual([tool.properties.where, tool.properties.tool, tool.properties.count, tool.properties.process], ['tool', 'cad_show', 2, 'app']);
  assert.deepEqual(tool.properties.$exception_list, [{
    type: 'KeyError', value: '', mechanism: { type: 'generic', handled: true, synthetic: false },
    stacktrace: { type: 'raw', frames: [
      { platform: 'python', filename: 'cadgen/mcp/server.py', function: 'Server._call', lineno: 421, in_app: true },
      { platform: 'python', filename: '<user>', function: '<user>', in_app: false },
      { platform: 'python', filename: 'json/decoder.py', function: 'JSONDecoder.decode', lineno: 345, in_app: false },
    ] },
  }]);
  // A worker that died shows its exit status, and nothing else; a page's frames are JavaScript's.
  assert.deepEqual(worker.properties.$exception_list, [{ type: 'WorkerDied', value: 'exit status -11',
    mechanism: { type: 'generic', handled: false, synthetic: false } }]);
  // A Windows worker's fault, by its exception code as Windows writes it.
  assert.equal(fault.properties.$exception_list[0].value, 'exit status 0xC0000409');
  // A page's frame names its chunk, by which PostHog finds the source map the release uploaded.
  assert.deepEqual(page.properties.$exception_list[0].stacktrace.frames,
    [{ platform: 'web:javascript', filename: 'assets/index-Bx3k2.js', function: 'Kt', lineno: 1, colno: 48213,
      chunk_id: '0de4d024-c159-4f6d-b15a-cc4ef7a6856d', in_app: true }]);
});

test('where the host could not tell, an event names no country; what a schema left out, it leaves out', async () => {
  const { asked, store } = posthog();
  // As cadgen 0.7.7 to 0.7.11 send it, over JSON (which leaves out what is undefined): no process, which was
  // always an app's then, and a file by its code, which goes no further.
  const schema1 = JSON.parse(JSON.stringify({ ...BATCH, schema: 1, version: '0.7.11', process: undefined, source: 'store',
    channel: undefined, arch: undefined, client: undefined, presentation: undefined,
    events: [BATCH.events[1], { name: 'file', file: '3f9a1c0be47d2a55', kind: 'step' }] }));
  await store.insert(rowsOf(schema1), { country: null });
  const context = { distinct_id: INSTALL, session: SESSION, $session_id: SESSION, $geoip_disable: true, process: 'app', version: '0.7.11', channel: 'unknown',
    source: 'store', platform: 'darwin' };
  assert.deepEqual(asked[0].body.batch, [
    { event: 'view_used', properties: { ...context, calls: 7 } },
    { event: 'files_shown', properties: { ...context, kind: 'step', count: 1 } },
  ]);
});

test('an opt-out deletes the person and every event sent under the id, with the personal key', async () => {
  const { asked, store } = posthog();
  await store.forget(INSTALL);
  assert.deepEqual(asked, [{
    url: 'https://eu.posthog.com/api/projects/1234/persons/bulk_delete/', method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer phx_personal' },
    body: { distinct_ids: [INSTALL], delete_events: true },
  }]);
});

test("PostHog refusing or failing is the receiver's failure, named by its status alone", async () => {
  for (const status of [400, 401, 500, 503]) {
    const { store } = posthog(status);
    await assert.rejects(store.insert(rowsOf(BATCH), { country: 'DE' }), { code: `posthog_${status}` });
    await assert.rejects(store.forget(INSTALL), { code: `posthog_${status}` });
    await assert.rejects(store.ready(), { code: `posthog_${status}` });
  }
});

test('health asks for the project with the personal key, and finds the capture key its own', async () => {
  const { asked, store } = posthog();
  await store.ready();
  assert.deepEqual(asked.map(({ url, method, headers }) => [url, method, headers]),
    [['https://eu.posthog.com/api/projects/1234/', 'GET', { authorization: 'Bearer phx_personal' }]]);
  const project = token => posthogStore(SETTINGS_EU, { fetch: async () => new Response(JSON.stringify({ api_token: token })) });
  await project('phc_project').ready();
  await assert.rejects(project('phc_another').ready(), { code: 'posthog_project_key' });
});

test('the host names its settings, and health names any missing or not what PostHog takes', () => {
  const env = { POSTHOG_REGION: 'us', POSTHOG_PROJECT_KEY: 'phc_project', POSTHOG_PERSONAL_KEY: 'phx_personal', POSTHOG_PROJECT_ID: '42' };
  assert.deepEqual(missingSettings(env), []);
  assert.deepEqual(settingsOf(env), { region: 'us', projectKey: 'phc_project', personalKey: 'phx_personal', projectId: '42' });
  assert.deepEqual(missingSettings({}), SETTINGS);
  assert.deepEqual(missingSettings({ ...env, POSTHOG_REGION: 'asia', POSTHOG_PROJECT_ID: 'my-project' }), ['POSTHOG_REGION', 'POSTHOG_PROJECT_ID']);
});

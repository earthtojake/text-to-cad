import assert from 'node:assert/strict';
import { test } from 'node:test';
import { rowsOf } from './events.mjs';
import { EVENTS, missingSettings, posthogStore, SETTINGS, settingsOf } from './posthog.mjs';

const INSTALL = '8c347ec3-1342-4db5-a19a-491cbc8c59be';
const SESSION = '0b1e6f1a-6a52-4c39-9d43-2f5e0f0b9d11';
// What cadgen sends (cadgen/analytics.py).
const BATCH = {
  schema: 2, install: INSTALL, session: SESSION, version: '0.7.6', channel: 'claude-directory', platform: 'darwin', arch: 'arm64',
  client: { name: 'codex-mcp-client', version: '0.159.0' }, presentation: 'tabs',
  events: [
    { name: 'tool', tool: 'cad_show', calls: 3, errors: 1 },
    { name: 'view', calls: 7 },
    { name: 'file', file: '3f9a1c0be47d2a55', kind: 'step' },
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
  assert.deepEqual(body.batch.map(event => event.event), [EVENTS.tool, EVENTS.view, EVENTS.file]);
  const context = { distinct_id: INSTALL, session: SESSION, $geoip_disable: true, version: '0.7.6', channel: 'claude-directory',
    platform: 'darwin', arch: 'arm64', client: 'codex-mcp-client', client_version: '0.159.0', presentation: 'tabs', country: 'DE' };
  assert.deepEqual(body.batch.map(event => event.properties), [
    { ...context, tool: 'cad_show', calls: 3, errors: 1 },
    { ...context, calls: 7 },
    { ...context, file: '3f9a1c0be47d2a55', kind: 'step' },
  ]);
});

test('where the host could not tell, an event names no country; what a schema left out, it leaves out', async () => {
  const { asked, store } = posthog();
  // As cadgen 0.7.7 to 0.7.11 send it, over JSON (which leaves out what is undefined).
  const schema1 = JSON.parse(JSON.stringify({ ...BATCH, schema: 1, source: 'store', channel: undefined, arch: undefined,
    client: undefined, presentation: undefined, events: [BATCH.events[1]] }));
  await store.insert(rowsOf(schema1), { country: null });
  const [{ properties }] = asked[0].body.batch;
  assert.deepEqual(properties, { distinct_id: INSTALL, session: SESSION, $geoip_disable: true, version: '0.7.6', channel: 'unknown',
    source: 'store', platform: 'darwin', calls: 7 });
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

test('health asks for the project with the personal key', async () => {
  const { asked, store } = posthog();
  await store.ready();
  assert.deepEqual(asked.map(({ url, method, headers }) => [url, method, headers]),
    [['https://eu.posthog.com/api/projects/1234/', 'GET', { authorization: 'Bearer phx_personal' }]]);
});

test('the host names its settings, and health names any missing or not what PostHog takes', () => {
  const env = { POSTHOG_REGION: 'us', POSTHOG_PROJECT_KEY: 'phc_project', POSTHOG_PERSONAL_KEY: 'phx_personal', POSTHOG_PROJECT_ID: '42' };
  assert.deepEqual(missingSettings(env), []);
  assert.deepEqual(settingsOf(env), { region: 'us', projectKey: 'phc_project', personalKey: 'phx_personal', projectId: '42' });
  assert.deepEqual(missingSettings({}), SETTINGS);
  assert.deepEqual(missingSettings({ ...env, POSTHOG_REGION: 'asia', POSTHOG_PROJECT_ID: 'my-project' }), ['POSTHOG_REGION', 'POSTHOG_PROJECT_ID']);
});

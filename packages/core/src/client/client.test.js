import assert from 'node:assert/strict';
import test from 'node:test';
import { createCadClient } from './client.js';

function json(value) { return { ok: true, json: async () => value }; }
function deferred() { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; }

test('construction is inert; subscribers share one catalog request and explicit disposal aborts it', async () => {
  const response = deferred();
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: (url, options) => {
    calls.push({ url, options }); return response.promise;
  } });
  assert.equal(calls.length, 0);
  let notifications = 0;
  const stopOne = client.subscribe(() => notifications++);
  const stopTwo = client.subscribe(() => notifications++);
  assert.equal(calls.length, 1);
  stopOne();
  assert.equal(calls[0].options.signal.aborted, false);
  client.dispose();
  assert.equal(calls[0].options.signal.aborted, true);
  const atDispose = notifications;
  response.resolve(json({ entries: [{ file: 'late.step' }] }));
  await new Promise((r) => setImmediate(r));
  assert.equal(notifications, atDispose);
  assert.deepEqual(client.getSnapshot().entries, []);
  stopTwo();
});

test('two clients keep root identity, catalog data, cancellation and absolute assets separate', async () => {
  const calls = [];
  const fetch = async (url) => {
    calls.push(url);
    const origin = new URL(url).origin;
    return json({ rootId: `${origin}-root`, entries: [{ file: '/root/part.step', rootRelativeFile: 'part.step', url: '/__cad/asset?file=part.step' }] });
  };
  const a = createCadClient({ origin: 'http://one.test', fetch, pollIntervalMs: 0 });
  const b = createCadClient({ origin: 'http://two.test', fetch, pollIntervalMs: 0 });
  const [first, second] = await Promise.all([a.resolveEntry('part.step'), b.resolveEntry('part.step')]);
  assert.equal(first.url, 'http://one.test/__cad/asset?file=part.step');
  assert.equal(second.url, 'http://two.test/__cad/asset?file=part.step');
  assert.equal(a.workspaceId, 'http://one.test-root');
  assert.equal(b.workspaceId, 'http://two.test-root');
  a.dispose();
  await b.refresh();
  assert.equal(calls.length, 3);
  b.dispose();
});

test('file-specific requests use independent AbortSignals and late replies cannot replace a newer catalog', async () => {
  const pending = [];
  const client = createCadClient({ pollIntervalMs: 0, fetch: (url, options) => {
    const work = deferred(); pending.push({ ...work, url, options }); return work.promise;
  } });
  const firstAbort = new AbortController();
  const first = client.resolveEntry('one.step', { signal: firstAbort.signal });
  const second = client.resolveEntry('two.step');
  firstAbort.abort();
  assert.equal(pending[0].options.signal.aborted, true);
  assert.equal(pending[1].options.signal.aborted, false);
  pending[1].resolve(json({ entries: [{ file: 'two.step' }] }));
  assert.equal((await second).file, 'two.step');
  pending[0].resolve(json({ entries: [{ file: 'one.step' }] }));
  await assert.rejects(first, { name: 'AbortError' });
  assert.equal(client.getSnapshot().entries[0].file, 'two.step');
  client.dispose();
});

test('artifact compile sends the guard header and publishes only into its own client', async () => {
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url, options) => {
    calls.push({ url, options }); return json({ ok: true, state: 'rendered', catalog: { entries: [{ file: 'part.step', url: '/asset' }] } });
  } });
  await client.requestArtifact('part.step', { force: true });
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers['x-cadgen-viewer'], '1');
  assert.equal(new URL(calls[0].url).searchParams.get('force'), '1');
  assert.equal(client.getSnapshot().entries[0].url, 'http://one.test/asset');
  client.dispose();
});

test('catalog timeout retains the existing error and external cancellation stays separate', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const client = createCadClient({ pollIntervalMs: 0, fetch: (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  }) });
  const pending = client.refresh();
  const timeout = assert.rejects(pending, /Timed out loading CAD catalog after 10s/);
  t.mock.timers.tick(10_000);
  await timeout;
  assert.equal(client.getSnapshot().error, 'Timed out loading CAD catalog after 10s');
  const controller = new AbortController();
  const cancelled = client.refresh({ signal: controller.signal });
  controller.abort();
  await assert.rejects(cancelled, { name: 'AbortError' });
  client.dispose();
});

test('polling keeps its two-second cadence, obeys host visibility and stops with its last subscriber', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let visible = false, count = 0;
  const client = createCadClient({ shouldPoll: () => visible, fetch: async () => { count++; return json({ entries: [] }); } });
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  const releaseOne = client.subscribe(() => {});
  const releaseTwo = client.subscribe(() => {});
  await settle();
  assert.equal(count, 1);
  t.mock.timers.tick(2000);
  await settle();
  assert.equal(count, 1);
  visible = true;
  releaseOne();
  t.mock.timers.tick(2000);
  await settle();
  assert.equal(count, 2);
  releaseTwo();
  t.mock.timers.tick(2000);
  await settle();
  assert.equal(count, 2);
  client.dispose();
});

test('source outline requests use the client origin and cancel with the selected file', async () => {
  const pending = deferred();
  let call;
  const client = createCadClient({ origin: 'http://one.test', fetch: (url, options) => { call = {url, options}; return pending.promise; } });
  const controller = new AbortController();
  const request = client.requestDesignOutline('models/case.step', { signal: controller.signal });
  assert.equal(new URL(call.url).pathname, '/__cad/design-outline');
  assert.equal(new URL(call.url).searchParams.get('file'), 'models/case.step');
  controller.abort();
  assert.equal(call.options.signal.aborted, true);
  pending.resolve(json({status:'ready',features:[],parameters:[]}));
  await assert.rejects(request, {name:'AbortError'});
  client.dispose();
});

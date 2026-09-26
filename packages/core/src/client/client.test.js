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

test('fresh server reads observe restarts and transport errors while cached consumers remain inert', async () => {
  let calls = 0;
  let identityToken = 'before-restart';
  let unavailable = false;
  const client = createCadClient({ origin: 'http://one.test', fetch: async () => {
    calls += 1;
    if (unavailable) throw new TypeError('Backend is restarting');
    return json({ rootId: 'workspace', identityToken, autoReload: true });
  } });
  try {
    assert.equal((await client.serverInfo()).identityToken, 'before-restart');
    identityToken = 'after-restart';
    assert.equal((await client.serverInfo()).identityToken, 'before-restart');
    assert.equal(calls, 1, 'ordinary server metadata consumers retain their cache');
    assert.equal((await client.serverInfo({ fresh: true })).identityToken, 'after-restart');
    unavailable = true;
    await assert.rejects(client.serverInfo({ fresh: true }), (error) => {
      assert.equal(error.failure.kind, 'network');
      assert.equal(error.failure.operation, 'server');
      assert.equal(error.failure.url, 'http://one.test/__cad/server');
      return true;
    });
    assert.equal((await client.serverInfo()).identityToken, 'after-restart');
    assert.equal(calls, 3, 'a failed poll never replaces the last successful cached response');
  } finally {
    client.dispose();
  }
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

test('concurrent views resolving one file both receive the newest accepted catalog entry', async () => {
  const pending = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: () => {
    const response = deferred(); pending.push(response); return response.promise;
  } });
  try {
    const earlier = client.resolveEntry('part.step', { signal: new AbortController().signal });
    const later = client.resolveEntry('part.step', { signal: new AbortController().signal });
    assert.equal(pending.length, 2, 'each view owns its request cancellation');
    pending[1].resolve(json({ entries: [{ file: 'part.step', hash: 'new', url: '/new-geometry' }] }));
    const current = await later;
    assert.equal(current.hash, 'new');
    pending[0].resolve(json({ entries: [{ file: 'part.step', hash: 'old', url: '/old-geometry' }] }));
    assert.equal(await earlier, current, 'a rejected stale response cannot escape to its waiting viewer');
    assert.equal(client.getSnapshot().entries[0], current);
    assert.equal(current.url, 'http://one.test/new-geometry');
  } finally {
    client.dispose();
  }
});

test('resolving a deferred catalog entry hydrates that file instead of accepting its placeholder', async (t) => {
  const calls = [];
  const pending = { file: '/models/nested/part.step', rootRelativeFile: 'nested/part.step', catalogPending: true };
  const ready = { ...pending, catalogPending: false, hash: 'ready', tree: '/tree.json' };
  const client = createCadClient({ pollIntervalMs: 0, fetch: async (url) => {
    const file = new URL(url, 'http://test').searchParams.get('file');
    calls.push(file);
    return json({ entries: [file ? ready : pending] });
  } });
  t.after(() => client.dispose());
  await client.refresh();
  assert.equal(client.getSnapshot().entries[0].catalogPending, true);
  const entry = await client.resolveEntry('nested/part.step');
  assert.equal(entry.hash, 'ready');
  assert.deepEqual(calls, [null, 'nested/part.step']);
  assert.equal(await client.resolveEntry('/models/nested/part.step'), entry, 'a warm lookup does not fetch again');
});

test('partial catalogs retain resolved metadata, selected-file changes replace it, and removed files disappear', async (t) => {
  let entries = [{ file: 'one.step', hash: 'one-v1' }, { file: 'two.step', catalogPending: true }];
  const client = createCadClient({ pollIntervalMs: 0, fetch: async () => json({ entries }) });
  t.after(() => client.dispose());
  await client.refresh({ file: 'one.step' });
  const original = client.getSnapshot().entries[0];
  entries = [{ file: 'one.step', catalogPending: true }, { file: 'two.step', hash: 'two-v1' }];
  await client.refresh({ file: 'two.step' });
  assert.equal(client.getSnapshot().entries[0], original, 'an unrelated hydration does not invalidate the displayed file');
  assert.equal(client.getSnapshot().entries[1].hash, 'two-v1');
  entries = [{ file: 'one.step', hash: 'one-v2' }, { file: 'two.step', catalogPending: true }];
  await client.refresh({ file: 'one.step' });
  assert.deepEqual(client.getSnapshot().entries.map(({ hash }) => hash), ['one-v2', 'two-v1']);
  entries = [{ file: 'two.step', catalogPending: true }];
  await client.refresh({ file: 'two.step' });
  assert.deepEqual(client.getSnapshot().entries.map(({ file }) => file), ['two.step']);
});

test('concurrent file hydrations merge without allowing stale metadata or listings to overwrite newer replies', async (t) => {
  const pending = [];
  const client = createCadClient({ pollIntervalMs: 0, fetch: () => {
    const response = deferred(); pending.push(response); return response.promise;
  } });
  t.after(() => client.dispose());
  const one = client.resolveEntry('one.step');
  const two = client.resolveEntry('two.step');
  pending[1].resolve(json({ entries: [{ file: 'one.step', catalogPending: true }, { file: 'two.step', hash: 'two-v1' }] }));
  await two;
  pending[0].resolve(json({ entries: [{ file: 'one.step', hash: 'one-v1' }, { file: 'two.step', catalogPending: true }, { file: 'removed.step' }] }));
  await one;
  assert.deepEqual(client.getSnapshot().entries.map(({ hash }) => hash), ['one-v1', 'two-v1']);
  const old = client.refresh({ file: 'one.step', signal: new AbortController().signal });
  const fresh = client.refresh({ file: 'one.step', signal: new AbortController().signal });
  pending[3].resolve(json({ entries: [{ file: 'one.step', hash: 'one-v3' }, { file: 'two.step', catalogPending: true }] }));
  await fresh;
  pending[2].resolve(json({ entries: [{ file: 'one.step', hash: 'one-v2' }, { file: 'two.step', catalogPending: true }] }));
  await old;
  assert.equal(client.getSnapshot().entries[0].hash, 'one-v3');
  const removed = client.refresh({ file: 'one.step', signal: new AbortController().signal });
  const listing = client.refresh({ file: '' });
  pending[5].resolve(json({ entries: [{ file: 'two.step', catalogPending: true }] }));
  await listing;
  pending[4].resolve(json({ entries: [{ file: 'one.step', hash: 'one-v4' }, { file: 'two.step', catalogPending: true }] }));
  await removed;
  assert.deepEqual(client.getSnapshot().entries.map(({ file }) => file), ['two.step']);
});

test('unresolved metadata fails explicitly instead of mounting an indefinitely pending viewer', async (t) => {
  const client = createCadClient({ pollIntervalMs: 0, fetch: async () => json({ entries: [{ file: 'part.step', catalogPending: true }] }) });
  t.after(() => client.dispose());
  await assert.rejects(client.resolveEntry('part.step'), /CAD file metadata is unavailable: part.step/);
});

test('polling targets active render sessions and continues observing selected-file metadata changes', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const calls = [];
  let version = 1;
  const client = createCadClient({ fetch: async (url) => {
    const selected = new URL(url, 'http://test').searchParams.get('file');
    calls.push(selected);
    return json({ entries: ['one.step', 'two.step'].map((file) => file === selected
      ? { file, hash: `${file}-${version}` } : { file, catalogPending: true }) });
  } });
  t.after(() => client.dispose());
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  const release = client.subscribe(() => {});
  await settle();
  await client.resolveEntry('one.step');
  const one = client.createRenderSession({ file: 'one.step' });
  const two = client.createRenderSession({ file: 'two.step' });
  calls.length = 0;
  version = 2;
  t.mock.timers.tick(2000);
  await settle();
  assert.deepEqual(calls, ['one.step', 'two.step']);
  assert.deepEqual(client.getSnapshot().entries.map(({ hash }) => hash), ['one.step-2', 'two.step-2']);
  two.dispose();
  calls.length = 0;
  t.mock.timers.tick(2000);
  await settle();
  assert.deepEqual(calls, ['one.step']);
  one.dispose();
  release();
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

test('surface and preview requests are origin-bound, guarded and cancelled with their owner', async () => {
  const calls = [];
  const client = createCadClient({ origin: 'http://workspace.test', fetch: async (url, options) => {
    calls.push({ url, options });
    return json({ job: 'subscriber', feedCursor: 'next' });
  } });
  const body = { tree: 'tree', components: [{ cid: 'one', surfaceInput: 'input' }] };
  assert.equal((await client.requestSurfaces(body)).job, 'subscriber');
  await client.cancelSurfaceRequest({ job: 'subscriber' });
  await client.editingPreview('part.step', { after: 'cursor' });
  assert.equal(new URL(calls[0].url).origin, 'http://workspace.test');
  assert.deepEqual(JSON.parse(calls[0].options.body), body);
  assert.equal(calls[0].options.headers['x-cadgen-viewer'], '1');
  assert.equal(new URL(calls[1].url).pathname, '/__cad/surfaces/cancel');
  assert.equal(new URL(calls[2].url).pathname, '/__cad/preview');
  assert.equal(new URL(calls[2].url).searchParams.get('file'), 'part.step');
  assert.equal(new URL(calls[2].url).searchParams.get('after'), 'cursor');
  client.dispose();
  await assert.rejects(client.editingPreview('part.step'), { name: 'AbortError' });
});

test('a drawing is one plain GET, and a refusal arrives with the server’s own sentence', async () => {
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url, options) => {
    calls.push({ url, options });
    return json({ schemaVersion: 1, bounds: [0, 0, 10, 10], layers: [], primitives: [] });
  } });
  const payload = await client.drawing('drawings/plate.dxf');
  assert.equal(payload.schemaVersion, 1);
  assert.equal(new URL(calls[0].url).pathname, '/__cad/drawing');
  assert.equal(new URL(calls[0].url).searchParams.get('file'), 'drawings/plate.dxf');
  assert.equal(calls[0].options.method, 'GET');
  // A GET carries no cross-site POST guard: this route reads bytes and nothing else.
  assert.equal(calls[0].options.headers['x-cadgen-viewer'], undefined);
  await assert.rejects(client.drawing(''), /Missing file/);
  client.dispose();
});

test('a drawing refused by the server raises the classified failure an alert is built from', async () => {
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async () => ({
    ok: false, status: 400, statusText: 'Bad Request',
    json: async () => ({ error: 'plate.dxf is not a readable DXF document.' })
  }) });
  await assert.rejects(client.drawing('plate.dxf'), (error) => {
    assert.equal(error.name, 'ViewerRequestError');
    assert.equal(error.failure.kind, 'http');
    assert.equal(error.failure.status, 400);
    assert.equal(error.failure.operation, 'drawing');
    assert.equal(error.failure.detail, 'plate.dxf is not a readable DXF document.');
    return true;
  });
  client.dispose();
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { createCadClient, isMissingFileError } from './client.js';

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

test('two clients keep catalog data, cancellation and absolute assets separate', async () => {
  const calls = [];
  const fetch = async (url) => {
    calls.push(url);
    return json({ entries: [{ file: '/root/part.step', url: '/__cad/asset?file=/root/part.step' }] });
  };
  const a = createCadClient({ origin: 'http://one.test', fetch, pollIntervalMs: 0 });
  const b = createCadClient({ origin: 'http://two.test', fetch, pollIntervalMs: 0 });
  const [first, second] = await Promise.all([a.resolveEntry('/root/part.step'), b.resolveEntry('/root/part.step')]);
  assert.equal(first.url, 'http://one.test/__cad/asset?file=/root/part.step');
  assert.equal(second.url, 'http://two.test/__cad/asset?file=/root/part.step');
  assert.equal(new URL(calls[0]).searchParams.get('file'), '/root/part.step', 'a file is asked for by its absolute path');
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
    return json({ identityToken, autoReload: true });
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

test('a file the server does not have is a missing file, said so', async (t) => {
  const client = createCadClient({ pollIntervalMs: 0, fetch: async () => json({ entries: [] }) });
  t.after(() => client.dispose());
  await assert.rejects(client.resolveEntry('/gone/part.step'), (error) => {
    assert.equal(isMissingFileError(error), true);
    assert.match(error.message, /File does not exist: \/gone\/part.step/);
    return true;
  });
  assert.equal(isMissingFileError(new Error('offline')), false);
});

test('a folder is read one at a time, and a search under it asks the server with its query', async (t) => {
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url) => {
    calls.push(new URL(url));
    return json(url.includes('/__cad/folder') ? { path: '/m', entries: [{ name: 'arm', kind: 'directory' }], truncated: false }
      : { path: '/m', results: ['/m/arm/link.step'], truncated: true });
  } });
  t.after(() => client.dispose());
  assert.deepEqual((await client.folder('/m')).entries, [{ name: 'arm', kind: 'directory' }]);
  assert.deepEqual(await client.search('/m', 'link'), { path: '/m', results: ['/m/arm/link.step'], truncated: true });
  assert.deepEqual(calls.map((url) => [url.origin, url.pathname, Object.fromEntries(url.searchParams)]), [
    ['http://one.test', '/__cad/folder', { path: '/m' }],
    ['http://one.test', '/__cad/search', { path: '/m', q: 'link' }],
  ]);
});

test('polling reads the files on screen again, and only those', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const calls = [];
  let version = 1;
  const client = createCadClient({ fetch: async (url) => {
    const selected = new URL(url, 'http://test').searchParams.get('file');
    calls.push(selected);
    return json({ entries: selected ? [{ file: selected, hash: `${selected}-${version}` }] : [] });
  } });
  t.after(() => client.dispose());
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  const release = client.subscribe(() => {});
  await settle();
  await client.resolveEntry('/m/one.step');
  const one = client.createRenderSession({ file: '/m/one.step' });
  const two = client.createRenderSession({ file: '/m/two.step' });
  calls.length = 0;
  version = 2;
  t.mock.timers.tick(2000);
  await settle();
  assert.deepEqual(calls, ['/m/one.step', '/m/two.step']);
  assert.deepEqual(client.getSnapshot().entries.map(({ hash }) => hash), ['/m/one.step-2', '/m/two.step-2']);
  two.dispose();
  calls.length = 0;
  t.mock.timers.tick(2000);
  await settle();
  assert.deepEqual(calls, ['/m/one.step']);
  one.dispose();
  release();
});

test('artifact compile sends the guard header and answers with the server\'s start of the build', async () => {
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url, options) => {
    calls.push({ url, options }); return json({ ok: true, state: 'compiling' });
  } });
  assert.deepEqual(await client.requestArtifact('part.step', { force: true }), { ok: true, state: 'compiling' });
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers['x-cadgen-viewer'], '1');
  assert.equal(new URL(calls[0].url).searchParams.get('force'), '1');
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

test('the library, Open, Reveal and the person\'s settings are guarded requests to the viewer\'s routes, as any host reaches them', async (t) => {
  const calls = [];
  const thumbnail = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url, options = {}) => {
    const path = new URL(url).pathname;
    calls.push([path, options.method || 'GET', options.headers?.['x-cadgen-viewer'] ?? null, options.body ? JSON.parse(options.body) : null]);
    if (path === '/__cad/thumbnail') return new Response(new URL(url).searchParams.get('name') === 'a.png' ? thumbnail : null, { status: new URL(url).searchParams.get('name') === 'a.png' ? 200 : 404 });
    if (path === '/__cad/reveal') return options.body.includes('gone') ? Response.json({ error: 'That file is no longer there.' }, { status: 404 }) : new Response(null, { status: 204 });
    if (path === '/__cad/pick') return Response.json({ path: '/models/picked.step' });
    if (path === '/__cad/recents') return Response.json({ recents: [{ path: '/models/a.step' }] });
    return Response.json({ path });
  } });
  t.after(() => client.dispose());
  assert.deepEqual(await client.recents(), [{ path: '/models/a.step' }]);
  assert.deepEqual(await client.changeRecents({ action: 'open', path: '/models/a.step' }), [{ path: '/models/a.step' }]);
  await client.keepThumbnail(new Blob([thumbnail], { type: 'image/png' }), '/models/a.step');
  assert.equal(await client.thumbnail('a.png'), 'data:image/png;base64,iVBORw==');
  assert.equal(await client.thumbnail('none.png'), null);
  assert.equal(await client.pick(), '/models/picked.step');
  await client.reveal('/models/a.step');
  await assert.rejects(client.reveal('/models/gone.step'), /no longer there/);
  await client.consent();
  await client.consent(true);
  await client.consent(false);
  await client.features({ quickEdit: false });
  await client.version();
  client.reportActivity({ touched: true });
  await new Promise((resolve) => setImmediate(resolve));
  // Every change carries the header no page from another site can send; a read sends none.
  assert.deepEqual(calls, [
    ['/__cad/recents', 'GET', null, null],
    ['/__cad/recents', 'POST', '1', { action: 'open', path: '/models/a.step' }],
    ['/__cad/recents', 'POST', '1', { action: 'thumbnail', path: '/models/a.step', png: 'iVBORw==' }],
    ['/__cad/thumbnail', 'GET', null, null], ['/__cad/thumbnail', 'GET', null, null],
    ['/__cad/pick', 'POST', '1', null],
    ['/__cad/reveal', 'POST', '1', { path: '/models/a.step' }], ['/__cad/reveal', 'POST', '1', { path: '/models/gone.step' }],
    ['/__cad/analytics', 'GET', null, null],
    ['/__cad/analytics', 'POST', '1', { share: true }], ['/__cad/analytics', 'POST', '1', { share: false }],
    ['/__cad/features', 'POST', '1', { quickEdit: false }],
    ['/__cad/version', 'GET', null, null],
    ['/__cad/analytics/activity', 'POST', '1', { touched: true }],
  ]);
});

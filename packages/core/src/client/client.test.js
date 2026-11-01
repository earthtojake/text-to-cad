import assert from 'node:assert/strict';
import test from 'node:test';
import { createCadClient, isMissingFileError } from './client.js';

function json(value) { return { ok: true, json: async () => value }; }
// A file's envelope as `GET /api/v1/documents?path=` answers it (the API's), its catalog row inside.
function docs(entries) { return json({ documents: entries.map(entry => ({ id: entry.id, entry, revision: entry.hash ?? '' })) }); }
// A document the engine does not hold, as `GET /api/v1/documents/<id>` refuses it.
function missing(error, state) {
  return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ error, hint: 'run the model\'s script again', ...(state ? { state } : {}) }) };
}
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
  response.resolve(docs([{ file: 'late.step' }]));
  await new Promise((r) => setImmediate(r));
  assert.equal(notifications, atDispose);
  assert.deepEqual(client.getSnapshot().entries, []);
  stopTwo();
});

test('two clients keep catalog data, cancellation and absolute assets separate', async () => {
  const calls = [];
  const fetch = async (url) => {
    calls.push(url);
    return docs([{ file: '/root/part.step', url: '/api/v1/local/files?path=/root/part.step' }]);
  };
  const a = createCadClient({ origin: 'http://one.test', fetch, pollIntervalMs: 0 });
  const b = createCadClient({ origin: 'http://two.test', fetch, pollIntervalMs: 0 });
  const [first, second] = await Promise.all([a.resolveEntry('/root/part.step'), b.resolveEntry('/root/part.step')]);
  assert.equal(first.url, 'http://one.test/api/v1/local/files?path=/root/part.step');
  assert.equal(second.url, 'http://two.test/api/v1/local/files?path=/root/part.step');
  assert.equal(new URL(calls[0]).pathname, '/api/v1/documents');
  assert.equal(new URL(calls[0]).searchParams.get('path'), '/root/part.step', 'a file is asked for by its absolute path');
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
      assert.equal(error.failure.url, 'http://one.test/api/v1/server');
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
  pending[1].resolve(docs([{ file: 'two.step' }]));
  assert.equal((await second).file, 'two.step');
  pending[0].resolve(docs([{ file: 'one.step' }]));
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
    pending[1].resolve(docs([{ file: 'part.step', hash: 'new', url: '/new-geometry' }]));
    const current = await later;
    assert.equal(current.hash, 'new');
    pending[0].resolve(docs([{ file: 'part.step', hash: 'old', url: '/old-geometry' }]));
    assert.equal(await earlier, current, 'a rejected stale response cannot escape to its waiting viewer');
    assert.equal(client.getSnapshot().entries[0], current);
    assert.equal(current.url, 'http://one.test/new-geometry');
  } finally {
    client.dispose();
  }
});

test('a file the server does not have is a missing file, said so', async (t) => {
  const client = createCadClient({ pollIntervalMs: 0, fetch: async () => docs([]) });
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
    return json(!new URL(url).searchParams.has('q') ? { path: '/m', entries: [{ name: 'arm', kind: 'directory' }], truncated: false }
      : { path: '/m', results: ['/m/arm/link.step'], truncated: true });
  } });
  t.after(() => client.dispose());
  assert.deepEqual((await client.folder('/m')).entries, [{ name: 'arm', kind: 'directory' }]);
  assert.deepEqual(await client.search('/m', 'link'), { path: '/m', results: ['/m/arm/link.step'], truncated: true });
  assert.deepEqual(calls.map((url) => [url.origin, url.pathname, Object.fromEntries(url.searchParams)]), [
    ['http://one.test', '/api/v1/local/folder', { path: '/m' }],
    ['http://one.test', '/api/v1/local/folder', { path: '/m', q: 'link' }],
  ]);
});

test('polling reads the files on screen again, and only those', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const calls = [];
  let version = 1;
  const client = createCadClient({ fetch: async (url) => {
    const selected = new URL(url, 'http://test').searchParams.get('path');
    calls.push(selected);
    return docs(selected ? [{ file: selected, hash: `${selected}-${version}` }] : []);
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
  const client = createCadClient({ shouldPoll: () => visible, fetch: async () => { count++; return docs([]); } });
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

// `POST /api/v1/documents` opening a file, as the server answers it: its id, its kind and where its reads are.
const opened = (kind, id = 'd1') => Response.json({ id, kind, api: `/api/v1/documents/${kind}/${id}` }, { status: 201 });

test('a drawing is its document opened once, then one plain GET of its drawing', async () => {
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url, options) => {
    calls.push({ url, options });
    if (options.method === 'POST') return opened('dxf');
    return json({ schemaVersion: 1, bounds: [0, 0, 10, 10], layers: [], primitives: [] });
  } });
  const payload = await client.drawing('/drawings/plate.dxf');
  assert.equal(payload.schemaVersion, 1);
  assert.equal(new URL(calls[0].url).pathname, '/api/v1/documents');
  assert.deepEqual([calls[0].options.method, calls[0].options.headers['x-cadgen-viewer'], JSON.parse(calls[0].options.body)],
    ['POST', '1', { path: '/drawings/plate.dxf' }], 'the file opened by its path, a guarded change');
  assert.equal(new URL(calls[1].url).pathname, '/api/v1/documents/dxf/d1/drawing');
  assert.equal(calls[1].options.method, 'GET');
  // A GET carries no cross-site guard: this route reads and nothing else.
  assert.equal(calls[1].options.headers['x-cadgen-viewer'], undefined);
  // Opened once: the next read of it reads its drawing alone.
  await client.drawing('/drawings/plate.dxf');
  assert.deepEqual(calls.slice(2).map(({ url }) => new URL(url).pathname), ['/api/v1/documents/dxf/d1/drawing']);
  await assert.rejects(client.drawing(''), /Missing file/);
  client.dispose();
});

test('a drawing still rendering is asked for again after the server\'s retryMs, until its payload comes back', async () => {
  const replies = [{ state: 'drawing', retryMs: 0 }, { state: 'drawing', retryMs: 0 }, { schemaVersion: 2, primitives: [] }];
  let asked = 0;
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (_url, options) => {
    if (options.method === 'POST') return opened('dxf');
    asked += 1;
    return Response.json(replies.shift(), { status: asked < 3 ? 202 : 200 });
  } });
  assert.deepEqual(await client.drawing('/m/sheet.dxf'), { schemaVersion: 2, primitives: [] });
  assert.equal(asked, 3);
  // The wait for the next ask ends with its owner.
  const controller = new AbortController();
  const waiting = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (_url, options) => {
    if (options.method === 'POST') return opened('dxf');
    queueMicrotask(() => controller.abort());
    return Response.json({ state: 'drawing', retryMs: 60_000 }, { status: 202 });
  } });
  await assert.rejects(waiting.drawing('/m/sheet.dxf', { signal: controller.signal }), { name: 'AbortError' });
  client.dispose();
  waiting.dispose();
});

test('an engine document is read through this server, with the client\'s fetch, once the engine holds it, its import heard meanwhile', async () => {
  // The engine's progress event of the import (`cad/engine/progress.py`), handed on as it came.
  const importing = { kind: 'import', stage: 'collect', job: 'a.step', outputs: [], detail: '', done: 120, total: 628, elapsedMs: 3100 };
  const api = '/api/v1/documents/step/abc123';
  const replies = [{ id: 'abc123', kind: 'step', api, state: 'reading', retryMs: 0 },
    { id: 'abc123', kind: 'step', api, state: 'reading', retryMs: 0, building: importing }, { id: 'abc123', kind: 'step', api }];
  const asked = [];
  const fetch = async (url, options = {}) => {
    asked.push([new URL(url).pathname, options.method || 'GET', options.body ? JSON.parse(options.body) : null]);
    const path = new URL(url).searchParams.get('path');
    return path ? Response.json({ documents: [{ id: 'x', held: path === '/m/a.step' }] })
      : Response.json(replies.shift(), { status: replies.length ? 202 : 201 });
  };
  const client = createCadClient({ origin: 'http://cad.invalid', pollIntervalMs: 0, fetch });
  const heard = [];
  const served = await client.engineDocument('/m/a.step', { onProgress: frame => heard.push(frame) });
  // Read under the client's origin and with its fetch: the CAD app's travels over its tunnel.
  assert.deepEqual(served, { doc: 'abc123', kind: 'step', url: 'http://cad.invalid/api/v1/documents/step/abc123', fetch });
  assert.deepEqual(asked, Array(3).fill(['/api/v1/documents', 'POST', { path: '/m/a.step' }]), 'asked again while the engine reads it');
  // Each 202 that carries the import's frame hands it on; one with none says nothing.
  assert.deepEqual(heard, [importing]);
  assert.equal(await client.engineHolds('/m/a.step'), true);
  assert.equal(await client.engineHolds('/m/b.step'), false);
  await assert.rejects(client.engineDocument(''), /Missing file/);
  client.dispose();
});

test('an open the server stays silent on fails after its 10 s, as every read does', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  // A wedged engine: the open is sent and never answered, until the client gives up on it.
  const wedged = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: wedged });
  t.after(() => client.dispose());
  for (const open of [() => client.engineDocument('/m/a.step'), () => client.drawing('/m/sheet.dxf')]) {
    const failed = assert.rejects(open(), (error) => {
      assert.equal(error.failure.kind, 'timeout');
      assert.equal(error.failure.method, 'POST');
      assert.match(error.failure.detail, /did not respond within 10 seconds/);
      return true;
    });
    await new Promise((resolve) => setImmediate(resolve));
    t.mock.timers.tick(10_000);
    await failed;
  }
});

test('a drawing refused by the server raises the classified failure an alert is built from', async () => {
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (_url, options) => (options.method === 'POST'
    ? opened('dxf') : { ok: false, status: 400, statusText: 'Bad Request',
      json: async () => ({ error: 'plate.dxf is not a readable DXF document.', hint: 'fix the request as the error says' }) }) });
  await assert.rejects(client.drawing('/m/plate.dxf'), (error) => {
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
    if (path.endsWith('/thumbnail')) return new Response(path.includes('/d1/') ? thumbnail : null, { status: path.includes('/d1/') ? 200 : 404 });
    if (path === '/api/v1/local/reveal') return options.body.includes('gone') ? Response.json({ error: 'That file is no longer there.' }, { status: 404 }) : new Response(null, { status: 204 });
    if (path === '/api/v1/local/pick') return Response.json({ path: '/models/picked.step' });
    if (path === '/api/v1/documents') return Response.json({ documents: [{ id: 'd1', path: '/models/a.step', kind: 'step', record: 'file' }] });
    if (path === '/api/v1/settings') return Response.json({ language: { locale: null }, telemetry: { share: true } });
    return Response.json({ path });
  } });
  t.after(() => client.dispose());
  // A row as the library reads it: its record's kind is the library's, its document's beside it.
  const row = { id: 'd1', path: '/models/a.step', kind: 'file', record: 'file', documentKind: 'step' };
  assert.deepEqual(await client.recents(), [row]);
  assert.deepEqual(await client.changeRecents({ action: 'open', path: '/models/a.step' }), [row]);
  await client.keepThumbnail(new Blob([thumbnail], { type: 'image/png' }), '/models/a.step');
  // A picture, by its document's id, versioned by the picture's name.
  assert.equal(client.thumbnailUrl({ id: 'd1', thumbnail: 'a.png' }), 'http://one.test/api/v1/documents/d1/thumbnail?v=a.png');
  assert.equal(await client.thumbnail({ id: 'd1', thumbnail: 'a.png' }), 'data:image/png;base64,iVBORw==');
  assert.equal(await client.thumbnail({ id: 'd2', thumbnail: 'none.png' }), null);
  assert.equal(await client.pick(), '/models/picked.step');
  await client.reveal('/models/a.step');
  await assert.rejects(client.reveal('/models/gone.step'), /no longer there/);
  assert.deepEqual(await client.consent(), { share: true }, 'the settings\' telemetry');
  await client.consent(true);
  await client.consent(false);
  assert.equal(client.features, undefined);
  assert.deepEqual(await client.language(), { locale: null }, 'the settings\' language');
  await client.language('zh-CN');
  await client.language(null);
  await client.version();
  await client.startUpdate();
  client.reportActivity({ touched: true });
  await new Promise((resolve) => setImmediate(resolve));
  // Every change carries the header no page from another site can send; a read sends none.
  assert.deepEqual(calls, [
    ['/api/v1/documents', 'GET', null, null],
    ['/api/v1/documents', 'PATCH', '1', { action: 'open', path: '/models/a.step' }],
    ['/api/v1/documents', 'PATCH', '1', { action: 'thumbnail', path: '/models/a.step', png: 'iVBORw==' }],
    ['/api/v1/documents/d1/thumbnail', 'GET', null, null], ['/api/v1/documents/d2/thumbnail', 'GET', null, null],
    ['/api/v1/local/pick', 'POST', '1', null],
    ['/api/v1/local/reveal', 'POST', '1', { path: '/models/a.step' }], ['/api/v1/local/reveal', 'POST', '1', { path: '/models/gone.step' }],
    ['/api/v1/settings', 'GET', null, null],
    ['/api/v1/settings', 'PUT', '1', { telemetry: { share: true } }], ['/api/v1/settings', 'PUT', '1', { telemetry: { share: false } }],
    ['/api/v1/settings', 'GET', null, null],
    ['/api/v1/settings', 'PUT', '1', { language: { locale: 'zh-CN' } }], ['/api/v1/settings', 'PUT', '1', { language: { locale: null } }],
    ['/api/v1/server', 'GET', null, null],
    ['/api/v1/local/update', 'POST', '1', null],
    ['/api/v1/local/activity', 'POST', '1', { touched: true }],
  ]);
});

test('rows join by their document id: a symlinked file asked for by both its paths is one row', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const calls = [];
  // The server answers either spelling with the one document: its id, and the path it read.
  const fetch = async (url) => {
    calls.push(String(url));
    const params = new URL(String(url)).searchParams;
    const entry = { id, file: params.get('path') || '/real/a.step', hash: 'one' };
    return params.has('path') ? docs([entry]) : json({ id, entry, revision: 'one' });
  };
  const client = createCadClient({ origin: 'http://one.test', fetch, pollIntervalMs: 0 });
  const viaLink = await client.resolveEntry('/link/a.step');
  const viaTarget = await client.resolveEntry('/real/a.step');
  const viaId = await client.resolveEntry(id);
  assert.equal(client.getSnapshot().entries.length, 1, 'one document, one row');
  assert.deepEqual([viaLink.id, viaTarget.id, viaId.id], [id, id, id]);
  assert.equal(client.entryOf('/link/a.step')?.id, id);
  assert.equal(new URL(calls.at(-1)).pathname, '/api/v1/documents', 'a row the catalog has is not asked for again by its id');
  client.dispose();
});

test('an id the engine does not hold is missing, in the engine\'s words', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const calls = [];
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async (url) => {
    calls.push(String(url));
    return missing(`no document ${id} is held: run \`python /m/parts.py\` to build it again`);
  } });
  const failure = await client.resolveEntry(id).catch((error) => error);
  assert.equal(isMissingFileError(failure), true);
  assert.match(failure.message, /run `python \/m\/parts.py` to build it again/);
  assert.equal(new URL(calls[0]).pathname, `/api/v1/documents/${id}`, 'a document id is asked for by id: its envelope');
  assert.equal(failure.state, undefined, 'the engine named no state');
  client.dispose();
});

test('an id the engine does not hold carries the state the engine names for it', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async () => missing(
    `cube (${id}) is detached: /m/parts.py is gone, and nothing builds it again; delete it from the home`, 'detached') });
  const failure = await client.resolveEntry(id).catch((error) => error);
  assert.deepEqual([isMissingFileError(failure), failure.state], [true, 'detached']);
  client.dispose();
});

test('an id deleted while it is on screen leaves the catalog: asked again, it is missing', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  let held = true;
  const client = createCadClient({ origin: 'http://one.test', pollIntervalMs: 0, fetch: async () => (held
    ? json({ id, kind: 'model', entry: { id, file: id, name: 'cube', sourcePath: null }, revision: 'r1' })
    : missing(`no document ${id} is held`, 'unsaved')) });
  assert.equal((await client.resolveEntry(id)).id, id);
  held = false;  // `cad delete`
  await client.refresh({ file: id });
  assert.equal(client.entryOf(id), null, 'its row is gone');
  const failure = await client.resolveEntry(id).catch((error) => error);
  assert.deepEqual([isMissingFileError(failure), failure.state], [true, 'unsaved']);
  client.dispose();
});

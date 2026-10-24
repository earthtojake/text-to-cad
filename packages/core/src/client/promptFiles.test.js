import test from 'node:test';
import assert from 'node:assert/strict';
import { createHttpPromptFiles } from './promptFiles.js';

test("a prompt saves JSON in one request without polling; a JSON file is read by its name", async () => {
  const calls = [];
  const replies = [
    Response.json({ ok: true, snapshot: '/tmp/p/a-1.snapshot.json' }),
    new Response(new Blob(['{}'], { type: 'application/json' })),
  ];
  const files = createHttpPromptFiles({ origin: 'http://cad.invalid',
    fetch: async (url, options = {}) => { calls.push({ url, method: options.method || 'GET', headers: options.headers, body: options.body }); return replies.shift(); } });
  const request = { name: 'a.step', input: '/m/a.step', views: [{ label: 'current' }], annotation: { units: 'mm', marks: [] } };
  assert.deepEqual(await files.create(request),
    { snapshot: '/tmp/p/a-1.snapshot.json' });
  assert.deepEqual(calls.map(call => `${call.method} ${call.url}`), [
    'POST http://cad.invalid/__cad/prompt-files',
  ]);
  assert.deepEqual(JSON.parse(calls[0].body), { ...request, acceptInline: true });
  assert.ok(calls.every(call => call.headers['x-cadgen-viewer'] === '1'));
  const json = await files.read('/tmp/p/a-1.snapshot.json');
  assert.equal(json.type, 'application/json');
  assert.equal(calls.at(-1).url, 'http://cad.invalid/__cad/prompt-files/a-1.snapshot.json');
});

test("a refused packet says why", async () => {
  const files = createHttpPromptFiles({ fetch: async () => Response.json({ ok: false, error: 'annotation: marks must be an array' }, { status: 400 }) });
  await assert.rejects(files.create({ name: 'a.step', input: '/m/a.step', views: [], annotation: {} }), /marks must be an array/);
});


test('a small snapshot is returned inline without a file read', async () => {
  const inline = '{"input":"/m/a.step","jobs":[]}';
  const files = createHttpPromptFiles({ fetch: async () => Response.json({ ok: true, inline }) });
  assert.deepEqual(await files.create({}), { inline });
});

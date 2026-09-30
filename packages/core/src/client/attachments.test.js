import test from 'node:test';
import assert from 'node:assert/strict';
import { createHttpAttachmentStore } from './attachments.js';

test('a picture is posted to the viewer and named by the path the server saved it at', async () => {
  const calls = [];
  const store = createHttpAttachmentStore({ origin: 'http://cad.invalid', fetch: async (url, options) => {
    calls.push({ url, options });
    return calls.length === 1 ? Response.json({ ok: true, path: '/tmp/cadgen-sketches/a-sketch-1.png' }) : Response.json({ ok: false, error: 'A sketch is a PNG image of at most 20 MiB' }, { status: 400 });
  } });
  const png = new Blob([new Uint8Array([0x89, 0x50])], { type: 'image/png' });
  assert.equal(await store.save(png, 'parts/a.step'), '/tmp/cadgen-sketches/a-sketch-1.png');
  assert.equal(calls[0].url, 'http://cad.invalid/__cad/sketches?name=parts%2Fa.step');
  assert.deepEqual([calls[0].options.method, calls[0].options.headers['x-cadgen-viewer'], calls[0].options.body], ['POST', '1', png]);
  await assert.rejects(store.save(png, 'a.step'), /at most 20 MiB/);
  await assert.rejects(store.save(new Blob(['x'], { type: 'image/gif' }), 'a.step'), /PNG/);
});

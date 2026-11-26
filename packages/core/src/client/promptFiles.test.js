import test from 'node:test';
import assert from 'node:assert/strict';
import { createHttpPromptFiles } from './promptFiles.js';

test("a message's folders are the server's workspace and the person's home, asked of its description alone", async () => {
  const calls = [];
  const files = createHttpPromptFiles({ origin: 'http://cad.invalid', fetch: async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', headers: options.headers });
    return Response.json({ start: '/Users/a/robots', home: '/Users/a', platform: 'darwin' });
  } });
  assert.deepEqual(Object.keys(files), ['folders']);
  assert.deepEqual(await files.folders(), { start: '/Users/a/robots', home: '/Users/a' });
  assert.deepEqual(calls, [{ url: 'http://cad.invalid/api/v1/server', method: 'GET', headers: { 'x-cad-viewer': '1' } }]);
});

test('a server that says no folders, or does not answer, names none', async () => {
  const quiet = createHttpPromptFiles({ fetch: async () => Response.json({ start: '', home: 7 }) });
  assert.deepEqual(await quiet.folders(), { start: undefined, home: undefined });
  const refused = createHttpPromptFiles({ fetch: async () => new Response('no', { status: 503 }) });
  assert.deepEqual(await refused.folders(), { start: undefined, home: undefined });
});

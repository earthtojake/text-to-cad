import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const directory = await mkdtemp(join(tmpdir(), 'cad-downloads-test-'));
after(() => rm(directory, { recursive: true, force: true }));
const output = join(directory, 'downloads.mjs');
await build({ entryPoints: [fileURLToPath(new URL('./downloads.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', outfile: output });
const { createBrowserDownloads } = await import(pathToFileURL(output));
const storage = { getItem: () => null, setItem() {}, removeItem() {} };

function page() {
  const clicked = [], body = new Set();
  return { clicked, body, document: {
    body: { append: link => body.add(link) },
    createElement: () => { const link = { click() { clicked.push({ href: link.href, download: link.download, rel: link.rel, attached: body.has(link) }); }, remove() { body.delete(link); } }; return link; },
  } };
}

test('a ready file is one plain same-origin download link, clicked once and removed', () => {
  const { clicked, body, document } = page();
  const port = createBrowserDownloads({ document, storage, key: 'test' });
  port.save('http://127.0.0.1:4178/s/session/__cad/exports/job/file', 'bracket.step');
  assert.deepEqual(clicked, [{ href: 'http://127.0.0.1:4178/s/session/__cad/exports/job/file', download: 'bracket.step', rel: 'noopener', attached: true }]);
  assert.equal(body.size, 0);
  assert.doesNotMatch(clicked[0].href, /token/);
});

test('restoration keeps the exports under way, their requests and names; never a file', () => {
  let held;
  const port = createBrowserDownloads({ document: page().document, key: 'test', storage: { ...storage, getItem: () => held, setItem: (_key, value) => held = value, removeItem: () => held = undefined } });
  const value = [{ request: { requestId: 'a', epoch: 'e', source: { doc: 'd' }, format: 'stl' }, filename: 'x.stl' }];
  port.remember(value);
  assert.deepEqual(port.restore(), value);
  // A record keeps its request and name alone; a malformed one is dropped.
  held = JSON.stringify([{ filename: 'y.stl', extra: true, request: { requestId: 'b', epoch: 'e', source: { doc: 'd' }, format: 'stl' } }, { filename: 3 }]);
  assert.deepEqual(port.restore(), [{ request: { requestId: 'b', epoch: 'e', source: { doc: 'd' }, format: 'stl' }, filename: 'y.stl' }]);
  port.remember([]);
  assert.equal(held, undefined);
});

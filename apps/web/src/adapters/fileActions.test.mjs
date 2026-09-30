import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-web-actions-'));
const output = join(temporary, 'host.mjs');
await build({
  stdin: { contents: `export * from './adapters/fileActions.ts';`, resolveDir: fileURLToPath(new URL('../', import.meta.url)) },
  bundle: true, platform: 'node', conditions: ['production'], format: 'esm', outfile: output, loader: { '.css': 'empty' },
});
const { createWebFileActions } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

test('the file menu copies the served folder\'s paths, and reveals only where the server can', async () => {
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Macintosh' } });
  const clipboard = { writeText: async value => { copied.push(value); } };
  const server = { rootId: 'a', rootPath: '/models', backend: 'local-fs' };
  const actions = createWebFileActions(server, { clipboard });
  await actions.perform['copy-relative-path']({ path: 'parts/probe.step', kind: 'file' });
  await actions.perform['copy-path']({ path: 'parts/probe.step', kind: 'file' });
  await actions.perform['copy-path']({ path: 'parts', kind: 'directory' });
  assert.deepEqual(copied, ['parts/probe.step', '/models/parts/probe.step', '/models/parts']);
  assert.equal(actions.platform, 'darwin');
  // A remote backend's folder is not on this machine: no absolute path to copy.
  assert.equal(createWebFileActions({ ...server, backend: 'remote' }, { clipboard }).perform['copy-path'], undefined);
  assert.equal(actions.perform.reveal, undefined, 'older servers do not advertise reveal');
  const native = createWebFileActions({ ...server, rootPath: 'C:\\models', platform: 'win32', serverFeatures: ['reveal-path'] }, { clipboard });
  assert.equal(native.platform, 'win32', 'native effects use the server device platform');
  await native.perform['copy-path']({ path: 'parts/probe.step', kind: 'file' });
  assert.equal(copied.at(-1), 'C:\\models\\parts\\probe.step');
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, request) => {
      assert.equal(url, '/__cad/reveal');
      assert.equal(request.method, 'POST');
      assert.equal(request.headers['x-cadgen-viewer'], '1');
      assert.deepEqual(JSON.parse(request.body), { path: 'parts/probe.step' });
      return new Response(null, { status: 204 });
    };
    await native.perform.reveal({ path: 'parts/probe.step', kind: 'file' });
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'Cannot reveal file' }), { status: 400 });
    await assert.rejects(native.perform.reveal({ path: 'parts/probe.step', kind: 'file' }), /Cannot reveal file/);
  } finally { globalThis.fetch = originalFetch; }
});

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

test('the file menu copies a file\'s absolute path, and reveals only where the server can', async () => {
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Macintosh' } });
  const clipboard = { writeText: async value => { copied.push(value); } };
  const actions = createWebFileActions({ backend: 'local-fs' }, { clipboard });
  await actions.perform['copy-path']({ path: '/models/parts/probe.step', kind: 'file' });
  assert.deepEqual(copied, ['/models/parts/probe.step']);
  assert.equal(actions.platform, 'darwin');
  assert.equal(actions.perform.reveal, undefined, 'a server that does not advertise reveal has none');
  const native = createWebFileActions({ platform: 'win32', serverFeatures: ['reveal-path'] }, { clipboard });
  assert.equal(native.platform, 'win32', 'native effects use the server device platform');
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, request) => {
      assert.equal(url, '/__cad/reveal');
      assert.equal(request.method, 'POST');
      assert.equal(request.headers['x-cadgen-viewer'], '1');
      assert.deepEqual(JSON.parse(request.body), { path: 'C:/models/parts/probe.step' });
      return new Response(null, { status: 204 });
    };
    await native.perform.reveal({ path: 'C:\\models\\parts\\probe.step', kind: 'file' });
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'Cannot reveal file' }), { status: 400 });
    await assert.rejects(native.perform.reveal({ path: '/models/parts/probe.step', kind: 'file' }), /Cannot reveal file/);
  } finally { globalThis.fetch = originalFetch; }
});

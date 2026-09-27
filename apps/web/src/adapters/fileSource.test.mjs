import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const temporary = await mkdtemp(join(tmpdir(), 'hardcore-web-source-'));
const output = join(temporary, 'host.mjs');
await build({
  stdin: { contents: `export * from './adapters/fileSource.ts';`, resolveDir: fileURLToPath(new URL('../', import.meta.url)) },
  bundle: true, platform: 'node', conditions: ['production'], format: 'esm', outfile: output, loader: { '.webp': 'dataurl', '.css': 'empty' },
});
const { createWebFileSource, createWebFileActions } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));
test('web source keeps only catalog files, native path capabilities and silent clipboard actions', async () => {
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Macintosh', clipboard: { writeText: async value => copied.push(value) } } });
  let snapshot = { hydrated: true, entries: [{ file: '/models/parts/probe.step', rootRelativeFile: 'parts/probe.step', bytes: 128 }, { file: 'flat.stl', bytes: 64 }] };
  const listeners = new Set();
  const client = { getSnapshot: () => snapshot, resolveEntry: async path => snapshot.entries.find(entry => (entry.rootRelativeFile || entry.file) === path), subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); } };
  const server = { rootId: 'a', rootPath: '/models', backend: 'local-fs' };
  const delivered = [];
  const ports = { clipboard: { writeText: async value => copied.push(value) }, promptContext: { deliver: async context => { delivered.push(context); return {status: 'copied', partIds: ['reference']}; } } };
  const source = createWebFileSource(client, server);
  const actions = createWebFileActions(client, server, ports);
  const options = { signal: new AbortController().signal };
  assert.deepEqual(await source.list('', options), [{ path: 'parts', name: 'parts', kind: 'directory' }, { path: 'flat.stl', name: 'flat.stl', kind: 'file' }]);
  assert.equal((await source.stat('parts/probe.step', options)).size, 128);
  assert.equal(source.rootName, 'This directory');
  await actions.perform['copy-relative-path']({ path: 'parts/probe.step' });
  await actions.perform['copy-path']({ path: 'parts/probe.step' });
  assert.deepEqual(copied, ['parts/probe.step', '/models/parts/probe.step']);
  assert.equal(createWebFileActions(client, { rootId: 'a', rootPath: '/models', backend: 'remote' }, ports).perform['copy-path'], undefined);
  assert.equal(actions.perform['copy-reference'], undefined);
  assert.equal(actions.perform.reveal, undefined, 'older servers do not advertise reveal');
  const native = createWebFileActions(client, { ...server, platform: 'win32', serverFeatures: ['reveal-path'] }, ports);
  assert.equal(native.platform, 'win32', 'native effects use the server device platform');
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, request) => {
      assert.equal(url, '/__cad/reveal');
      assert.equal(request.method, 'POST');
      assert.equal(request.headers['x-cadgen-viewer'], '1');
      assert.deepEqual(JSON.parse(request.body), { path: 'parts/probe.step' });
      return new Response(null, {status: 204});
    };
    await native.perform.reveal({ path: 'parts/probe.step' });
    globalThis.fetch = async () => new Response(JSON.stringify({error: 'Cannot reveal file'}), {status: 400});
    await assert.rejects(native.perform.reveal({ path: 'parts/probe.step' }), /Cannot reveal file/);
  } finally { globalThis.fetch = originalFetch; }
  for (const unsupported of ['readText', 'readAsset', 'writeText', 'rename', 'create', 'duplicate', 'trash', 'actions']) assert.equal(source[unsupported], undefined);
  const changes = [];
  const unsubscribe = source.subscribe(change => changes.push(change));
  snapshot = { ...snapshot, entries: [snapshot.entries[1]] };
  for (const listener of listeners) listener();
  assert.deepEqual(changes, [{ sourceId: 'a', changes: [{ kind: 'deleted', path: 'parts/probe.step', entryKind: 'file' }] }]);
  snapshot = { ...snapshot, entries: [{ ...snapshot.entries[0], compileProgress: 0.5 }] };
  for (const listener of listeners) listener();
  assert.equal(changes.at(-1).changes[0].kind, 'metadata');
  snapshot = { ...snapshot, entries: [{ ...snapshot.entries[0], hash: 'new-content' }] };
  for (const listener of listeners) listener();
  assert.equal(changes.at(-1).changes[0].kind, 'content');
  unsubscribe();
  assert.equal(listeners.size, 0);
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(source.paths({ signal: aborted.signal }), { name: 'AbortError' });
});

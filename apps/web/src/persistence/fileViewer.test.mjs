import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const temporary = await mkdtemp(join(tmpdir(), 'hardcore-web-host-'));
const output = join(temporary, 'host.mjs');
await build({
  stdin: { contents: `export * from './persistence/fileViewer.ts'; export * from './adapters/fileSource.ts';`, resolveDir: new URL('../', import.meta.url).pathname },
  bundle: true, platform: 'node', format: 'esm', outfile: output,
});
const { readViewState, writeViewState, createWebFileSource } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));
function storage() {
  const entries = new Map();
  return { getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value), removeItem: key => entries.delete(key) };
}
function viewport(width) { globalThis.window = { innerWidth: width, sessionStorage: storage() }; }

test('fresh narrow views open the tree at the original width; wider views use the renderer default', () => {
  viewport(480);
  const narrow = readViewState('narrow', storage());
  assert.equal(narrow.panel, 'tree');
  assert.equal(narrow.panelWidth, 365);
  viewport(800);
  assert.equal(readViewState('compact', storage()).panelWidth, 280);
  viewport(1280);
  assert.equal(readViewState('wide', storage()).panel, null);
  assert.equal(readViewState('wide', storage()).panelWidth, 365);
});

test('restoration uses the supplied storage and keeps explicit closed/default panels', () => {
  viewport(1280);
  const session = storage();
  session.setItem('cad-viewer:directory-session:v1', JSON.stringify({ version: 1, fileSheetOpen: false, fileViewerOpen: false, fileSheetWidthPx: 401, fileViewerExpandedDirectoryIds: ['nested'] }));
  assert.deepEqual(readViewState('old', session), { panel: '', panelWidth: 401, expandedDirectories: ['nested'] });
  writeViewState('a', { panel: null, panelWidth: 300, expandedDirectories: ['a'] }, session);
  assert.equal(readViewState('a', session).panel, null);
  writeViewState('a', { panel: '', panelWidth: 900 }, session);
  assert.equal(readViewState('a', session).panel, '');
  assert.equal(readViewState('a', session).panelWidth, 480);
  assert.equal(readViewState('b', session).panelWidth, 401);
});

test('closing the legacy inspector without an explicit tree decision restores the tree', () => {
  viewport(1280);
  const session = storage();
  session.setItem('cad-viewer:directory-session:v1', JSON.stringify({ version: 1, fileSheetOpen: false }));
  assert.equal(readViewState('root', session).panel, 'tree');
});

test('web source keeps only catalog files, native path capabilities and original copy feedback', async () => {
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Macintosh', clipboard: { writeText: async value => copied.push(value) } } });
  let snapshot = { hydrated: true, entries: [{ file: '/models/parts/probe.step', rootRelativeFile: 'parts/probe.step', bytes: 128 }, { file: 'flat.stl', bytes: 64 }] };
  const listeners = new Set();
  const client = { getSnapshot: () => snapshot, resolveEntry: async path => snapshot.entries.find(entry => (entry.rootRelativeFile || entry.file) === path), subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); } };
  const statuses = [];
  const source = createWebFileSource(client, { rootId: 'a', rootPath: '/models', backend: 'local-fs' }, { onCopyStatus: value => statuses.push(value) });
  const options = { signal: new AbortController().signal };
  assert.deepEqual(await source.list('', options), [{ path: 'parts', name: 'parts', kind: 'directory' }, { path: 'flat.stl', name: 'flat.stl', kind: 'file' }]);
  assert.equal((await source.stat('parts/probe.step', options)).size, 128);
  assert.equal(source.rootName, 'This directory');
  await source.actions.perform['copy-relative-path']({ path: 'parts/probe.step' });
  await source.actions.perform['copy-path']({ path: 'parts/probe.step' });
  assert.deepEqual(copied, ['parts/probe.step', '/models/parts/probe.step']);
  assert.equal(statuses.at(-1), 'Copied path for probe.step');
  assert.equal(createWebFileSource(client, { rootId: 'a', rootPath: '/models', backend: 'remote' }).actions.perform['copy-path'], undefined);
  const changes = [];
  const unsubscribe = source.subscribe(change => changes.push(change));
  snapshot = { ...snapshot, entries: [snapshot.entries[1]] };
  for (const listener of listeners) listener();
  assert.deepEqual(changes, [{ sourceId: 'a', paths: ['parts/probe.step'] }]);
  unsubscribe();
  assert.equal(listeners.size, 0);
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(source.paths({ signal: aborted.signal }), { name: 'AbortError' });
});

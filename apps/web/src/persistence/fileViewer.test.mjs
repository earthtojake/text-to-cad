import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const temporary = await mkdtemp(join(tmpdir(), 'hardcore-web-host-'));
const output = join(temporary, 'host.mjs');
await build({
  stdin: { contents: `export * from './persistence/fileViewer.ts'; export * from './persistence/cadPreferences.ts'; export * from './adapters/fileSource.ts';`, resolveDir: fileURLToPath(new URL('../', import.meta.url)) },
  bundle: true, platform: 'node', conditions: ['production'], format: 'esm', outfile: output, loader: { '.webp': 'dataurl', '.css': 'empty' },
});
const { readViewState, writeViewState, createWebCadPreferences, createWebFileSource, createWebFileActions } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));
function storage() {
  const entries = new Map();
  return { getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value), removeItem: key => entries.delete(key) };
}
function viewport(width) { globalThis.window = { innerWidth: width, sessionStorage: storage() }; }

// A page load is a file opened directly, so it opens with the file's own default panel
// (`panel: null`) at any width, whatever the last page had open.
test('a page load opens with the file’s default panel; its width is the renderer default for the viewport', () => {
  viewport(480);
  assert.equal(readViewState('narrow', storage()).panel, null);
  assert.equal(readViewState('narrow', storage()).panelWidth, 365);
  viewport(800);
  assert.equal(readViewState('compact', storage()).panelWidth, 280);
  viewport(1280);
  assert.equal(readViewState('wide', storage()).panel, null);
  assert.equal(readViewState('wide', storage()).panelWidth, 365);
});

test('restoration keeps the width and the expanded folders, never the open panel', () => {
  viewport(1280);
  const session = storage();
  session.setItem('cad-viewer:directory-session:v1', JSON.stringify({ version: 1, fileSheetWidthPx: 401, fileViewerExpandedDirectoryIds: ['nested'] }));
  assert.deepEqual(readViewState('old', session), { panel: null, panelWidth: 401, expandedDirectories: ['nested'] });
  writeViewState('a', { panel: 'tree', panelWidth: 900, expandedDirectories: ['a'] }, session);
  assert.equal(readViewState('a', session).panel, null);
  assert.equal(readViewState('a', session).panelWidth, 480);
  assert.equal(readViewState('b', session).panelWidth, 401);
});

test('a stale web view merges its renderer changes without reverting another view', () => {
  viewport(1280);
  const session = storage();
  const baseline = { panel: null, panelWidth: 300, expandedDirectories: [], renderers: { a: { camera: 'old-a' }, b: { camera: 'old-b' } } };
  writeViewState('root', baseline, session);
  writeViewState('root', { ...baseline, panel: 'tree', panelWidth: 420, expandedDirectories: ['parts'], renderers: { ...baseline.renderers, b: { camera: 'new-b' } } }, session, baseline);
  writeViewState('root', { ...baseline, renderers: { ...baseline.renderers, a: { camera: 'new-a' } } }, session, baseline);
  assert.deepEqual(readViewState('root', session), { panel: null, panelWidth: 420, expandedDirectories: ['parts'], renderers: { a: { camera: 'new-a' }, b: { camera: 'new-b' } } });
});

test('whatever panel was stored, a load restores the file state and opens the renderer default', () => {
  viewport(1280);
  const session = storage();
  const renderers = { '["part.step","cad"]': { version: 1, fileSession: { render: { enabled: true } } } };
  writeViewState('root', { panel: 'cad-theme', panelWidth: 340, expandedDirectories: ['parts'], renderers }, session);
  assert.deepEqual(readViewState('root', session), { panel: null, panelWidth: 340, expandedDirectories: ['parts'], renderers });
});

test('web CAD preferences ignore legacy custom themes and retired tutorial state', () => {
  const previousWindow = globalThis.window;
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const local = storage();
  const legacy = JSON.stringify({ version: 13, themeId: 'custom', custom: { projection: 'perspective' } });
  local.setItem('cad-viewer:theme', legacy);
  const listeners = new Map();
  globalThis.window = { localStorage: local, addEventListener: (type, listener) => listeners.set(type, listener), removeEventListener: type => listeners.delete(type) };
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: local });
  try {
    const preferences = createWebCadPreferences();
    const disconnect = preferences.connect();
    const snapshot = preferences.getSnapshot();
    assert.equal('theme' in snapshot, false);
    listeners.get('storage')({ key: 'cad-viewer:theme' });
    assert.equal(preferences.getSnapshot(), snapshot);
    assert.equal('seenTips' in snapshot, false);
    assert.equal(local.getItem('cad-viewer:theme'), legacy);
    disconnect();
    assert.equal(listeners.size, 0);
  } finally {
    globalThis.window = previousWindow;
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage);
    else delete globalThis.localStorage;
  }
});

test('global orbit preference survives host recreation and synchronizes other windows', () => {
  const previousWindow = globalThis.window;
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const local = storage();
  const listeners = new Map();
  globalThis.window = { addEventListener: (type, listener) => listeners.set(type, listener), removeEventListener: type => listeners.delete(type) };
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: local });
  try {
    const source = createWebCadPreferences();
    const disconnect = source.connect();
    source.update({ orbit: { speed: 1.37 } });
    assert.deepEqual(createWebCadPreferences().getSnapshot().orbit, { speed: 1.37 });
    local.setItem('cad-viewer:orbit:v1', JSON.stringify({ speed: 0 }));
    listeners.get('storage')({ key: 'cad-viewer:orbit:v1' });
    assert.deepEqual(source.getSnapshot().orbit, { speed: 0 });
    local.removeItem('cad-viewer:orbit:v1');
    listeners.get('storage')({ key: null });
    assert.deepEqual(source.getSnapshot().orbit, { speed: 1 });
    disconnect();
  } finally {
    globalThis.window = previousWindow;
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage);
    else delete globalThis.localStorage;
  }
});

test('web preferences ignore retired tab arrangements without rewriting them', () => {
  const previousWindow = globalThis.window;
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const local = storage();
  const listeners = new Map();
  globalThis.window = { addEventListener: (type, listener) => listeners.set(type, listener), removeEventListener: type => listeners.delete(type) };
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: local });
  try {
    const layoutKey = 'cad-viewer:file-sheet-tab-layout:v7';
    const legacy = JSON.stringify({ step: { split: true, top: ['render'], bottom: ['tree', 'pose'], ratio: 0.2 } });
    local.setItem(layoutKey, legacy);
    const source = createWebCadPreferences();
    const disconnect = source.connect();
    const initial = source.getSnapshot();
    assert.equal('fileSheetTabs' in initial, false);
    listeners.get('storage')({ key: layoutKey });
    assert.equal(source.getSnapshot(), initial);
    source.update({ orbit: { speed: 2 } });
    assert.equal(local.getItem(layoutKey), legacy);
    assert.deepEqual(JSON.parse(local.getItem('cad-viewer:orbit:v1')), { speed: 2 });
    local.setItem('cad-viewer:orbit:v1', JSON.stringify({ speed: 4 }));
    listeners.get('storage')({ key: 'cad-viewer:orbit:v1' });
    assert.deepEqual(source.getSnapshot().orbit, { speed: 4 });
    // Pose transitions are retired: a stored preference is ignored, never read back or rewritten.
    const retired = JSON.stringify({ animate: false, speed: 2 });
    local.setItem('cad-viewer:pose-transition:v1', retired);
    const before = source.getSnapshot();
    listeners.get('storage')({ key: 'cad-viewer:pose-transition:v1' });
    assert.equal(source.getSnapshot(), before);
    assert.equal('poseTransition' in source.getSnapshot(), false);
    assert.equal(local.getItem('cad-viewer:pose-transition:v1'), retired);
    disconnect();
  } finally {
    globalThis.window = previousWindow;
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage); else delete globalThis.localStorage;
  }
});

test('web source keeps only catalog files, native path capabilities and original copy feedback', async () => {
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Macintosh', clipboard: { writeText: async value => copied.push(value) } } });
  let snapshot = { hydrated: true, entries: [{ file: '/models/parts/probe.step', rootRelativeFile: 'parts/probe.step', bytes: 128 }, { file: 'flat.stl', bytes: 64 }] };
  const listeners = new Set();
  const client = { getSnapshot: () => snapshot, resolveEntry: async path => snapshot.entries.find(entry => (entry.rootRelativeFile || entry.file) === path), subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); } };
  const statuses = [];
  const server = { rootId: 'a', rootPath: '/models', backend: 'local-fs' };
  const delivered = [];
  const ports = { clipboard: { writeText: async value => copied.push(value) }, promptContext: { deliver: async context => { delivered.push(context); return {status: 'copied', partIds: ['reference']}; } }, onCopyStatus: value => statuses.push(value) };
  const source = createWebFileSource(client, server);
  const actions = createWebFileActions(client, server, ports);
  const options = { signal: new AbortController().signal };
  assert.deepEqual(await source.list('', options), [{ path: 'parts', name: 'parts', kind: 'directory' }, { path: 'flat.stl', name: 'flat.stl', kind: 'file' }]);
  assert.equal((await source.stat('parts/probe.step', options)).size, 128);
  assert.equal(source.rootName, 'This directory');
  await actions.perform['copy-relative-path']({ path: 'parts/probe.step' });
  await actions.perform['copy-path']({ path: 'parts/probe.step' });
  assert.deepEqual(copied, ['parts/probe.step', '/models/parts/probe.step']);
  assert.equal(statuses.at(-1), 'Copied path for probe.step');
  assert.equal(createWebFileActions(client, { rootId: 'a', rootPath: '/models', backend: 'remote' }, ports).perform['copy-path'], undefined);
  await actions.perform['copy-reference']({ path: 'parts/probe.step' });
  assert.deepEqual(delivered[0].parts[0].reference, { resource: { kind: 'workspace-file', workspaceId: 'a', path: 'parts/probe.step' }, target: { kind: 'whole-resource' } });
  assert.equal(copied.length, 2, 'reference delivery does not also do an ordinary clipboard write');
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

import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-web-tab-'));
const output = join(temporary, 'tab.mjs');
await build({
  stdin: { contents: `export * from './persistence/tabRecord.ts'; export { createTabStore, TAB_RECORD_VERSION } from '@text-to-cad/ui/tab-store';`, resolveDir: fileURLToPath(new URL('../', import.meta.url)) },
  bundle: true, platform: 'node', conditions: ['production'], format: 'esm', outfile: output, loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.css': 'empty' },
  // The tab store reaches the shared column's width bounds through a React module; nothing of it renders here.
  external: ['react', 'react-dom', 'lucide-react', 'radix-ui'],
});
const { TAB_RECORD_KEY, sessionTabRecord, createTabStore, TAB_RECORD_VERSION } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

function fakeSessionStorage() {
  const entries = new Map();
  return { entries, getItem: key => entries.get(key) ?? null, setItem: (key, value) => { entries.set(key, String(value)); } };
}

test('the web adapter keeps the whole tab record under one sessionStorage key, and a fresh storage is a fresh tab', () => {
  const storage = fakeSessionStorage();
  const store = createTabStore(sessionTabRecord(storage));
  assert.equal(storage.entries.size, 0, 'construction reads and writes nothing');
  assert.deepEqual(store.settings.getSnapshot().appearance, 'system');
  store.settings.update({ appearance: 'dark', toolStack: { panels: { tree: { width: 240 } }, collapsed: {}, closed: { tree: true } } });
  store.files.write('/m/a.step', 'step', { version: 2, camera: null, display: null, renderer: {} });
  const stored = JSON.parse(storage.getItem(TAB_RECORD_KEY));
  assert.equal(stored.version, TAB_RECORD_VERSION);
  assert.deepEqual([stored.settings.appearance, stored.settings.toolStack], ['dark', { panels: { tree: { width: 240 } }, collapsed: {}, closed: { tree: true } }]);
  assert.deepEqual(Object.keys(stored.files), [JSON.stringify(['/m/a.step', 'step'])]);
  assert.deepEqual([...storage.entries.keys()], [TAB_RECORD_KEY], 'one key, nothing else');
  // The same storage again is the same tab reloaded; another storage is another tab.
  const reloaded = createTabStore(sessionTabRecord(storage));
  assert.deepEqual(reloaded.getSnapshot(), store.getSnapshot());
  const fresh = createTabStore(sessionTabRecord(fakeSessionStorage()));
  assert.equal(fresh.settings.getSnapshot().appearance, 'system');
  assert.deepEqual(fresh.getSnapshot().files, {});
});

test('a storage that is blocked or holds junk is a tab at its defaults, and a blocked write never throws', () => {
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  const store = createTabStore(sessionTabRecord(blocked));
  assert.equal(store.settings.getSnapshot().appearance, 'system');
  assert.doesNotThrow(() => store.settings.update({ appearance: 'light' }));
  assert.equal(store.settings.getSnapshot().appearance, 'light', 'the tab keeps going in memory');
  const junk = fakeSessionStorage();
  junk.setItem(TAB_RECORD_KEY, '{not json');
  assert.equal(createTabStore(sessionTabRecord(junk)).settings.getSnapshot().appearance, 'system');
  junk.setItem(TAB_RECORD_KEY, JSON.stringify({ version: 0, settings: { appearance: 'dark' } }));
  assert.equal(createTabStore(sessionTabRecord(junk)).settings.getSnapshot().appearance, 'system', 'another version is the defaults');
});

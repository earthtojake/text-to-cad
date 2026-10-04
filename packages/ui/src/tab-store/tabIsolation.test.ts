import { expect, test } from 'vitest';
import { createTabStore } from './tabStore.js';
import type { TabRecordStorage } from './tabStore.js';
import { defaultTabRecord } from './tabRecord.js';
import { readFileView, writeFileView } from '../renderers/kit/shell/fileView.js';
import { DEFAULT_PLAYBACK } from '../renderers/kit/tools/playbar/playbackPreferences.js';

// Each browser tab has a sessionStorage of its own, and a reload of the tab keeps it: a web host
// hands the tab store exactly that, under one key (`renderers/harness/index.tsx`). A tab here is
// one such storage; a reload is a new store over the same one.
const KEY = 'text-to-cad:tab:test';
function browserTab(): { storage: Storage; record: () => TabRecordStorage } {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, String(value)); },
    removeItem: (key: string) => { values.delete(key); }, clear: () => values.clear(), key: () => null, get length() { return values.size; },
  } as Storage;
  return { storage, record: () => ({ read: () => JSON.parse(storage.getItem(KEY) || 'null'), write: record => storage.setItem(KEY, JSON.stringify(record)) }) };
}

test('a new tab starts at the defaults and two tabs never meet: each reload brings back its own tab\'s settings and file views alone', () => {
  const one = browserTab(), two = browserTab();
  const first = createTabStore(one.record());
  // Tab one: the tree panel widened, the panel column widened, the appearance chosen, and the file in wireframe.
  first.settings.update({ appearance: 'dark', toolStack: { panels: { tree: { width: 240 } }, collapsed: {}, closed: {} }, panelWidth: 300 });
  first.files.write('/models/part.step', 'step', writeFileView({ display: { mode: 'wireframe' }, playback: { orbitSpeed: 3, autoplay: true } }) as never);

  // Tab two, in the same browser: none of it.
  const second = createTabStore(two.record());
  expect(second.getSnapshot()).toEqual(defaultTabRecord());
  expect(second.settings.getSnapshot()).toEqual({ panelWidth: 220, toolStack: { panels: {}, collapsed: {}, closed: {} }, appearance: 'system', library: { layout: 'grid' } });
  const fresh = readFileView(second.files.read('/models/part.step', 'step'));
  expect([fresh.display.mode, fresh.playback]).toEqual(['solid', DEFAULT_PLAYBACK]);
  second.settings.update({ appearance: 'light' });

  // Tab one reloaded: its own settings and view, untouched by tab two.
  const reloaded = createTabStore(one.record());
  const settings = reloaded.settings.getSnapshot();
  expect([settings.appearance, settings.toolStack.panels, settings.panelWidth]).toEqual(['dark', { tree: { width: 240 } }, 300]);
  const view = readFileView(reloaded.files.read('/models/part.step', 'step'));
  expect([view.display.mode, view.playback.orbitSpeed, view.playback.autoplay]).toEqual(['wireframe', 3, true]);

  // Tab two reloaded: its own.
  const secondReloaded = createTabStore(two.record());
  expect(secondReloaded.settings.getSnapshot().appearance).toBe('light');
  expect(secondReloaded.settings.getSnapshot().toolStack).toEqual({ panels: {}, collapsed: {}, closed: {} });
  expect(secondReloaded.files.read('/models/part.step', 'step')).toBeUndefined();
});

test("preview's Playback settings are the file's: kept across a reload of the tab, and another file has its own defaults", () => {
  const tab = browserTab();
  const store = createTabStore(tab.record());
  // A fresh file: orbit on at 1×, the routine's own loop, Autoplay off.
  expect(readFileView(store.files.read('/models/part.step', 'step')).playback).toEqual({ orbit: true, orbitSpeed: 1, autoplay: false });
  // Orbit off, its speed 2×, Loop off, Autoplay on — the file's view as the shell writes it.
  const chosen = { orbit: false, orbitSpeed: 2, autoplay: true, loop: false };
  store.files.write('/models/part.step', 'step', writeFileView({ playback: chosen }) as never);
  expect(readFileView(store.files.read('/models/part.step', 'step')).playback).toEqual(chosen);

  // A reload of the tab keeps every choice; the routine's speed stays its own until chosen.
  const reloaded = createTabStore(tab.record());
  const kept = readFileView(reloaded.files.read('/models/part.step', 'step')).playback;
  expect(kept).toEqual(chosen);
  expect('speed' in kept).toBe(false);

  // Another file starts at the defaults.
  expect(readFileView(reloaded.files.read('/models/other.step', 'step')).playback).toEqual(DEFAULT_PLAYBACK);
});

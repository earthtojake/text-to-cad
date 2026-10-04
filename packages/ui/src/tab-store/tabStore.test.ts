import { act, renderHook } from '@testing-library/react';
import { expect, test } from 'vitest';
import { createTabStore, memoryTabRecord } from './tabStore.js';
import { TAB_FILE_LIMIT, TAB_RECORD_VERSION, defaultTabRecord, readTabRecord, tabFileKey, writeTabFile } from './tabRecord.js';
import { useTabViewerState } from './useTabViewerState.js';
import { readFileView, writeFileView } from '../renderers/kit/shell/fileView.js';

const view = (camera: unknown) => ({ version: 2, camera, display: null, renderer: {} });

test('the record normalizes: every setting to its bounds, the files to well-keyed plain objects, and another version to the defaults', () => {
  expect(TAB_RECORD_VERSION).toBe(2);
  expect(readTabRecord(undefined)).toEqual(defaultTabRecord());
  expect(defaultTabRecord()).toEqual({ version: 2, settings: {
    panelWidth: 220, toolStack: { panels: {}, collapsed: {}, closed: {} }, appearance: 'system', library: { layout: 'grid' },
  }, files: {} });
  // A record of the version before (a file tree's width, views under a root) is the defaults.
  for (const raw of [null, 'x', [], { version: 1, settings: { appearance: 'dark', fileTree: { width: 300 } } }, { version: 3, settings: { appearance: 'dark' } }]) {
    expect(readTabRecord(raw), JSON.stringify(raw)).toEqual(defaultTabRecord());
  }
  const record = readTabRecord({ version: 2, settings: {
    panelWidth: 9999, fileTree: { width: 300 },
    toolStack: { panels: { tree: { width: 12 } }, collapsed: { tree: true, 'Not an id': true }, closed: { tree: true, sdf: 'no' } },
    orbit: { speed: 99 }, playback: { autoplay: true }, appearance: 'cinematic', library: { layout: 'shelf' },
  }, files: { [tabFileKey('/models/a.step', 'step')]: view(1), '["root","b.step","step"]': view(2), 'junk': view(3), [tabFileKey('/models/c.step', 'step')]: 'not a view' } });
  expect(record.settings).toEqual({
    panelWidth: 480, toolStack: { panels: { tree: { width: 164 } }, collapsed: { tree: true }, closed: { tree: true } }, appearance: 'system', library: { layout: 'grid' },
  });
  const settings = (patch: object) => readTabRecord({ version: 2, settings: patch, files: {} }).settings;
  expect([settings({ panelWidth: 12 }).panelWidth, settings({ panelWidth: 'wide' }).panelWidth, settings({ library: { layout: 'list' } }).library]).toEqual([140, 220, { layout: 'list' }]);
  expect(Object.keys(record.files)).toEqual([tabFileKey('/models/a.step', 'step')]);
});

test('the files are the file on screen\'s, by absolute path: a write keeps the newest alone, and a record stored with more is read back as its newest', () => {
  expect(TAB_FILE_LIMIT).toBe(1);
  // The same key a FileViewer's `renderers` map uses.
  expect(tabFileKey('/models/a.step', 'step')).toBe(JSON.stringify(['/models/a.step', 'step']));
  const [a, b] = [tabFileKey('/models/a.step', 'step'), tabFileKey('/models/b.step', 'step')];
  let files: Record<string, unknown> = writeTabFile({}, a, view('a') as never);
  files = writeTabFile(files as never, b, view('b') as never);
  expect(files).toEqual({ [b]: view('b') });
  files = writeTabFile(files as never, b, view('again') as never);
  expect(files).toEqual({ [b]: view('again') });
  const over: Record<string, unknown> = {};
  for (let index = 0; index < 50; index += 1) over[tabFileKey(`/models/${index}.step`, 'step')] = view(index);
  expect(readTabRecord({ version: 2, settings: {}, files: over }).files).toEqual({ [tabFileKey('/models/49.step', 'step')]: view(49) });
});

test('leaving a file drops its view: retain keeps the file on screen\'s, whichever renderer wrote it, none for no file, and never a setting', () => {
  const writes: unknown[] = [];
  const store = createTabStore({ read: () => undefined, write: record => { writes.push(record); } });
  store.settings.update({ appearance: 'dark', library: { layout: 'list' } });
  const settings = store.settings.getSnapshot();
  store.files.write('/models/a.step', 'mesh', view('a'));
  // The file on screen keeps its view, whatever renderer wrote it; nothing changes, so nothing is written.
  const written = writes.length;
  store.files.retain('/models/a.step');
  expect([store.files.read('/models/a.step', 'mesh'), writes.length]).toEqual([view('a'), written]);
  // Another file, and no file at all, each drop it.
  for (const path of ['/models/b.step', null]) {
    store.files.write('/models/a.step', 'step', view('a'));
    store.files.retain(path);
    expect(store.getSnapshot().files, String(path)).toEqual({});
  }
  store.files.write('/models/a.step', 'step', view('a'));
  store.files.remove('/models/a.step', 'step');
  expect(store.getSnapshot().files).toEqual({});
  expect(store.settings.getSnapshot()).toBe(settings);
});

test('the store reads its storage once, writes every change through whole, and publishes a new snapshot per change', () => {
  const writes: unknown[] = [];
  const storage = { reads: 0, read() { this.reads += 1; return { version: TAB_RECORD_VERSION, settings: { panelWidth: 300 }, files: {} }; }, write(record: unknown) { writes.push(JSON.parse(JSON.stringify(record))); } };
  const store = createTabStore(storage);
  expect(storage.reads).toBe(1);
  const first = store.getSnapshot();
  expect(first.settings.panelWidth).toBe(300);
  const heard: unknown[] = [];
  store.subscribe(() => heard.push(store.getSnapshot()));
  store.settings.update({ panelWidth: 300 });
  expect([writes.length, heard.length]).toEqual([0, 0]);
  expect(store.getSnapshot()).toBe(first);
  store.settings.update({ appearance: 'dark' });
  expect(store.getSnapshot()).not.toBe(first);
  expect(store.getSnapshot().settings).toEqual({ ...first.settings, appearance: 'dark' });
  expect([writes.length, heard.length, storage.reads]).toEqual([1, 1, 1]);
  store.files.write('/models/a.step', 'step', view('a'));
  expect((writes[1] as { files: object }).files).toEqual({ [tabFileKey('/models/a.step', 'step')]: view('a') });
  expect(store.files.read('/models/a.step', 'step')).toEqual(view('a'));
  // A blocked write is not the viewer's problem.
  const blocked = createTabStore({ read: () => undefined, write() { throw new Error('quota'); } });
  expect(() => blocked.settings.update({ appearance: 'light' })).not.toThrow();
  expect(blocked.settings.getSnapshot().appearance).toBe('light');
  expect(createTabStore({ read() { throw new Error('blocked'); }, write() {} }).getSnapshot()).toEqual(defaultTabRecord());
});

test('the preferences a renderer reads are the settings: patched by key, normalized, and shared by every file of the tab', () => {
  const store = createTabStore(memoryTabRecord());
  const preferences = store.settings;
  preferences.update({ appearance: 'dark' });
  preferences.update({ toolStack: { panels: { tree: { width: 240, height: 12 } }, collapsed: { sdf: false } } as never });
  expect(preferences.getSnapshot().appearance).toBe('dark');
  expect(preferences.getSnapshot().toolStack).toEqual({ panels: { tree: { width: 240, height: 64 } }, collapsed: { sdf: false }, closed: {} });
  preferences.update({ toolStack: { panels: {}, collapsed: {}, closed: {} } });
  expect(preferences.getSnapshot().toolStack).toEqual({ panels: {}, collapsed: {}, closed: {} });
  expect(preferences.getSnapshot()).toBe(store.getSnapshot().settings);
});

test('the file views come as FileViewer\'s records, stable per snapshot, and a view\'s changes merge without reverting a newer write', () => {
  const store = createTabStore(memoryTabRecord());
  const a = tabFileKey('/models/a.step', 'step');
  store.files.write('/models/a.step', 'step', view('a'));
  const views = store.files.all();
  expect(views).toEqual({ [a]: view('a') });
  expect(store.files.all()).toBe(views);
  // A stale view that changed nothing does not put back what it last saw.
  store.files.write('/models/a.step', 'step', view('a2'));
  store.files.merge(views, views);
  expect(store.files.all()).toEqual({ [a]: view('a2') });
  // What it changed lands, and what it dropped goes.
  store.files.merge(views, { [a]: view('a3') });
  expect(store.files.all()).toEqual({ [a]: view('a3') });
  store.files.merge(store.files.all(), {});
  expect(store.files.all()).toEqual({});
});

test('FileViewer\'s state comes from the tab: its column width and file views are kept, and the open panel never is', () => {
  const storage = memoryTabRecord();
  const first = renderHook(() => useTabViewerState(createTabStore(storage)));
  expect(first.result.current.state).toEqual({ panel: null, panelWidth: 220, renderers: {} });
  const a = tabFileKey('/models/a.step', 'step');
  act(() => first.result.current.onStateChange({ panel: 'details', panelWidth: 300, renderers: { [a]: view('a') } }));
  expect(first.result.current.state).toEqual({ panel: 'details', panelWidth: 300, renderers: { [a]: view('a') } });
  first.unmount();
  // A reload of the tab: the width and the view come back, and the file opens on its own default panel.
  const reloaded = renderHook(() => useTabViewerState(createTabStore(storage)));
  expect(reloaded.result.current.state).toEqual({ panel: null, panelWidth: 300, renderers: { [a]: view('a') } });
});

test("a file view's slices drop by signature while its camera and display are kept, whatever store it came through", () => {
  const store = createTabStore(memoryTabRecord());
  const camera = { position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1] };
  store.files.write('/models/a.step', 'step', writeFileView({ camera, display: { mode: 'render' }, renderer: { tree: { open: ['o1'] } }, signatures: { tree: 'geo:1' } }) as never);
  const reopened = createTabStore(memoryTabRecord(JSON.parse(JSON.stringify(store.getSnapshot()))));
  const same = readFileView(reopened.files.read('/models/a.step', 'step'), { tree: 'geo:1' });
  expect([same.camera, same.display.mode, same.renderer]).toEqual([camera, 'render', { tree: { open: ['o1'] } }]);
  const rebuilt = readFileView(reopened.files.read('/models/a.step', 'step'), { tree: 'geo:2' });
  expect([rebuilt.camera, rebuilt.display.mode, rebuilt.renderer]).toEqual([camera, 'render', {}]);
});

import { expect, test } from 'vitest';
import { createTabStore, memoryTabRecord } from './tabStore.js';
import { TAB_FILE_LIMIT, TAB_RECORD_VERSION, defaultTabRecord, readTabRecord, tabFileKey, writeTabFile } from './tabRecord.js';
import { readFileView, writeFileView } from '../renderers/kit/shell/fileView.js';

const view = (camera: unknown) => ({ version: 2, camera, display: null, renderer: {} });

test('the record normalizes: every setting to its bounds, the files to well-keyed plain objects, and another version to the defaults', () => {
  expect(readTabRecord(undefined)).toEqual(defaultTabRecord());
  expect(defaultTabRecord()).toEqual({ version: TAB_RECORD_VERSION, settings: {
    fileTree: { width: 220, expanded: {} }, toolStack: { panels: {}, collapsed: {}, closed: {} }, appearance: 'system', library: { layout: 'grid' },
  }, files: {} });
  for (const raw of [null, 'x', [], { version: 0, settings: { appearance: 'dark' } }, { version: 2, settings: { appearance: 'dark' } }]) {
    expect(readTabRecord(raw), JSON.stringify(raw)).toEqual(defaultTabRecord());
  }
  const record = readTabRecord({ version: TAB_RECORD_VERSION, settings: {
    fileTree: { width: 9999, expanded: { root: ['a', 'a', 7, 'b'], other: 'x' } },
    toolStack: { panels: { tree: { width: 12 } }, collapsed: { tree: true, 'Not an id': true }, closed: { tree: true, sdf: 'no' } },
    orbit: { speed: 99 }, playback: { autoplay: true }, appearance: 'cinematic', library: { layout: 'shelf' },
  }, files: { [tabFileKey('root', 'a.step', 'step')]: view(1), '["root","b.step"]': view(2), 'junk': view(3), [tabFileKey('root', 'c.step', 'step')]: 'not a view' } });
  expect(record.settings).toEqual({
    fileTree: { width: 480, expanded: { root: ['a', 'b'] } }, toolStack: { panels: { tree: { width: 164 } }, collapsed: { tree: true }, closed: { tree: true } },
    appearance: 'system', library: { layout: 'grid' },
  });
  expect(readTabRecord({ version: TAB_RECORD_VERSION, settings: { library: { layout: 'list' } }, files: {} }).settings.library).toEqual({ layout: 'list' });
  expect('orbit' in record.settings || 'playback' in record.settings).toBe(false, 'playback is a file view\'s, never a setting');
  expect(Object.keys(record.files)).toEqual([tabFileKey('root', 'a.step', 'step')]);
});

test('the files are the file on screen\'s: a write keeps the newest alone, and a record stored with more is read back as its newest', () => {
  expect(TAB_FILE_LIMIT).toBe(1);
  const [a, b] = [tabFileKey('root', 'a.step', 'step'), tabFileKey('root', 'b.step', 'step')];
  let files: Record<string, unknown> = writeTabFile({}, a, view('a') as never);
  files = writeTabFile(files as never, b, view('b') as never);
  expect(files).toEqual({ [b]: view('b') });
  // The file on screen written again stays.
  files = writeTabFile(files as never, b, view('again') as never);
  expect(files).toEqual({ [b]: view('again') });
  // A record an earlier build left with fifty files is read back as its newest.
  const over: Record<string, unknown> = {};
  for (let index = 0; index < 50; index += 1) over[tabFileKey('root', `${index}.step`, 'step')] = view(index);
  expect(readTabRecord({ version: TAB_RECORD_VERSION, settings: {}, files: over }).files).toEqual({ [tabFileKey('root', '49.step', 'step')]: view(49) });
});

test('leaving a file drops its view: retain keeps the file on screen\'s, under its root and whichever renderer wrote it, none for no file, and never a setting', () => {
  const writes: unknown[] = [];
  const store = createTabStore({ read: () => undefined, write: record => { writes.push(record); } });
  store.settings.update({ appearance: 'dark', library: { layout: 'list' } });
  const settings = store.settings.getSnapshot();
  store.files.write('one', 'a.step', 'mesh', view('a'));
  // The file on screen keeps its view, whatever renderer wrote it; nothing changes, so nothing is written.
  const written = writes.length;
  store.files.retain('one', 'a.step');
  expect([store.files.read('one', 'a.step', 'mesh'), writes.length]).toEqual([view('a'), written]);
  // Another file, the same path under another root, and no file at all each drop it.
  for (const [root, path] of [['one', 'b.step'], ['two', 'a.step'], ['one', null]] as const) {
    store.files.write('one', 'a.step', 'step', view('a'));
    store.files.retain(root, path);
    expect(store.getSnapshot().files, `${root}:${path}`).toEqual({});
  }
  expect(store.settings.getSnapshot()).toBe(settings);
});

test('the store reads its storage once, writes every change through whole, and publishes a new snapshot per change', () => {
  const writes: unknown[] = [];
  const storage = { reads: 0, read() { this.reads += 1; return { version: TAB_RECORD_VERSION, settings: { fileTree: { width: 300 } }, files: {} }; }, write(record: unknown) { writes.push(JSON.parse(JSON.stringify(record))); } };
  const store = createTabStore(storage);
  expect(storage.reads).toBe(1);
  const first = store.getSnapshot();
  expect(first.settings.fileTree).toEqual({ width: 300, expanded: {} });
  const heard: unknown[] = [];
  store.subscribe(() => heard.push(store.getSnapshot()));
  store.settings.update({ fileTree: { width: 300, expanded: {} } });
  expect(writes).toHaveLength(0);
  expect(heard).toHaveLength(0);
  expect(store.getSnapshot()).toBe(first);
  store.settings.update({ appearance: 'dark' });
  expect(store.getSnapshot()).not.toBe(first);
  expect(store.getSnapshot().settings).toEqual({ ...first.settings, appearance: 'dark' });
  expect(writes).toHaveLength(1);
  expect(heard).toHaveLength(1);
  expect(storage.reads).toBe(1);
  store.files.write('root', 'a.step', 'step', view('a'));
  expect((writes[1] as { files: object }).files).toEqual({ [tabFileKey('root', 'a.step', 'step')]: view('a') });
  expect(store.files.read('root', 'a.step', 'step')).toEqual(view('a'));
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
  preferences.update({ toolStack: { panels: { tree: { width: 240, height: 12 } }, collapsed: { sdf: false } } });
  expect(preferences.getSnapshot().appearance).toBe('dark');
  expect(preferences.getSnapshot().toolStack).toEqual({ panels: { tree: { width: 240, height: 64 } }, collapsed: { sdf: false }, closed: {} });
  preferences.update({ toolStack: { panels: {}, collapsed: {}, closed: {} } });
  expect(preferences.getSnapshot().toolStack).toEqual({ panels: {}, collapsed: {}, closed: {} });
  expect(preferences.getSnapshot()).toBe(store.getSnapshot().settings);
});

test("a root's view comes as FileViewer's records, stable per snapshot, and a view's changes merge without reverting a newer write", () => {
  const store = createTabStore(memoryTabRecord());
  const a = JSON.stringify(['a.step', 'step']);
  store.files.write('one', 'a.step', 'step', view('a'));
  const views = store.files.forRoot('one');
  expect(views).toEqual({ [a]: view('a') });
  expect(store.files.forRoot('one')).toBe(views);
  expect(store.files.forRoot('two')).toEqual({});
  // A stale view of the root that changed nothing does not put back what it last saw.
  store.files.write('one', 'a.step', 'step', view('a2'));
  store.files.merge('one', views, views);
  expect(store.files.forRoot('one')).toEqual({ [a]: view('a2') });
  // What it changed lands, and what it dropped goes.
  store.files.merge('one', views, { [a]: view('a3') });
  expect(store.files.forRoot('one')).toEqual({ [a]: view('a3') });
  store.files.merge('one', store.files.forRoot('one'), {});
  expect(store.files.forRoot('one')).toEqual({});
});

test("a file view's slices drop by signature while its camera and display are kept, whatever store it came through", () => {
  const store = createTabStore(memoryTabRecord());
  const camera = { position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1] };
  store.files.write('root', 'a.step', 'step', writeFileView({ camera, display: { mode: 'render' }, renderer: { tree: { open: ['o1'] } }, signatures: { tree: 'geo:1' } }) as never);
  const reopened = createTabStore(memoryTabRecord(JSON.parse(JSON.stringify(store.getSnapshot()))));
  const same = readFileView(reopened.files.read('root', 'a.step', 'step'), { tree: 'geo:1' });
  expect([same.camera, same.display.mode, same.renderer]).toEqual([camera, 'render', { tree: { open: ['o1'] } }]);
  const rebuilt = readFileView(reopened.files.read('root', 'a.step', 'step'), { tree: 'geo:2' });
  expect([rebuilt.camera, rebuilt.display.mode, rebuilt.renderer]).toEqual([camera, 'render', {}]);
});

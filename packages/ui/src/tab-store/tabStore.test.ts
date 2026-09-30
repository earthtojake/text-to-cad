import { expect, test } from 'vitest';
import { createTabStore, memoryTabRecord } from './tabStore.js';
import { TAB_FILE_LIMIT, TAB_RECORD_VERSION, defaultTabRecord, readTabRecord, tabFileKey, writeTabFile } from './tabRecord.js';
import { readFileView, writeFileView } from '../renderers/kit/shell/fileView.js';

const view = (camera: unknown) => ({ version: 2, camera, display: null, renderer: {} });

test('the record normalizes: every setting to its bounds, the files to well-keyed plain objects, and another version to the defaults', () => {
  expect(readTabRecord(undefined)).toEqual(defaultTabRecord());
  expect(defaultTabRecord()).toEqual({ version: TAB_RECORD_VERSION, settings: {
    fileTree: { width: 220, expanded: {} }, toolStack: { panels: {}, collapsed: {} }, appearance: 'system', library: { layout: 'grid' },
  }, files: {} });
  for (const raw of [null, 'x', [], { version: 0, settings: { appearance: 'dark' } }, { version: 2, settings: { appearance: 'dark' } }]) {
    expect(readTabRecord(raw), JSON.stringify(raw)).toEqual(defaultTabRecord());
  }
  const record = readTabRecord({ version: TAB_RECORD_VERSION, settings: {
    fileTree: { width: 9999, expanded: { root: ['a', 'a', 7, 'b'], other: 'x' } },
    toolStack: { panels: { tree: { width: 12 } }, collapsed: { tree: true, 'Not an id': true } },
    orbit: { speed: 99 }, playback: { autoplay: true }, appearance: 'cinematic', library: { layout: 'shelf' },
  }, files: { [tabFileKey('root', 'a.step', 'step')]: view(1), '["root","b.step"]': view(2), 'junk': view(3), [tabFileKey('root', 'c.step', 'step')]: 'not a view' } });
  expect(record.settings).toEqual({
    fileTree: { width: 480, expanded: { root: ['a', 'b'] } }, toolStack: { panels: { tree: { width: 164 } }, collapsed: { tree: true } },
    appearance: 'system', library: { layout: 'grid' },
  });
  expect(readTabRecord({ version: TAB_RECORD_VERSION, settings: { library: { layout: 'list' } }, files: {} }).settings.library).toEqual({ layout: 'list' });
  expect('orbit' in record.settings || 'playback' in record.settings).toBe(false, 'playback is a file view\'s, never a setting');
  expect(Object.keys(record.files)).toEqual([tabFileKey('root', 'a.step', 'step')]);
});

test('the files are the fifty most recently written: a write puts a file last, and the fifty-first evicts the oldest', () => {
  let files: Record<string, unknown> = {};
  for (let index = 0; index < TAB_FILE_LIMIT; index += 1) files = writeTabFile(files as never, tabFileKey('root', `${index}.step`, 'step'), view(index) as never);
  expect(Object.keys(files)).toHaveLength(TAB_FILE_LIMIT);
  // Writing the first again makes it the newest.
  files = writeTabFile(files as never, tabFileKey('root', '0.step', 'step'), view('again') as never);
  expect(Object.keys(files).at(-1)).toBe(tabFileKey('root', '0.step', 'step'));
  expect(Object.keys(files)).toHaveLength(TAB_FILE_LIMIT);
  // The fifty-first: the oldest, now `1.step`, goes.
  files = writeTabFile(files as never, tabFileKey('root', 'new.step', 'step'), view('new') as never);
  expect(Object.keys(files)).toHaveLength(TAB_FILE_LIMIT);
  expect(files[tabFileKey('root', '1.step', 'step')]).toBeUndefined();
  expect(files[tabFileKey('root', '0.step', 'step')]).toEqual(view('again'));
  // A stored record over the limit is read back as its last fifty.
  const over: Record<string, unknown> = {};
  for (let index = 0; index < TAB_FILE_LIMIT + 5; index += 1) over[tabFileKey('root', `${index}.step`, 'step')] = view(index);
  const read = readTabRecord({ version: TAB_RECORD_VERSION, settings: {}, files: over });
  expect(Object.keys(read.files)).toHaveLength(TAB_FILE_LIMIT);
  expect(read.files[tabFileKey('root', '4.step', 'step')]).toBeUndefined();
  expect(read.files[tabFileKey('root', '5.step', 'step')]).toEqual(view(5));
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
  expect(preferences.getSnapshot().toolStack).toEqual({ panels: { tree: { width: 240, height: 64 } }, collapsed: { sdf: false } });
  preferences.update({ toolStack: { panels: {}, collapsed: {} } });
  expect(preferences.getSnapshot().toolStack).toEqual({ panels: {}, collapsed: {} });
  expect(preferences.getSnapshot()).toBe(store.getSnapshot().settings);
});

test("a root's views come as FileViewer's records, stable per snapshot, and a view's changes merge without reverting another's", () => {
  const store = createTabStore(memoryTabRecord());
  store.files.write('one', 'a.step', 'step', view('a'));
  store.files.write('two', 'a.step', 'step', view('other root'));
  const views = store.files.forRoot('one');
  expect(views).toEqual({ [JSON.stringify(['a.step', 'step'])]: view('a') });
  expect(store.files.forRoot('one')).toBe(views);
  // A stale view of root one changes `b` while `a` moved on: only `b` lands.
  const baseline = { ...views, [JSON.stringify(['b.step', 'step'])]: view('b0') };
  store.files.write('one', 'a.step', 'step', view('a2'));
  store.files.merge('one', baseline, { ...baseline, [JSON.stringify(['b.step', 'step'])]: view('b1') });
  expect(store.files.forRoot('one')).toEqual({ [JSON.stringify(['a.step', 'step'])]: view('a2'), [JSON.stringify(['b.step', 'step'])]: view('b1') });
  // A key the view dropped is removed; the other root is untouched.
  store.files.merge('one', store.files.forRoot('one'), { [JSON.stringify(['a.step', 'step'])]: view('a2') });
  expect(Object.keys(store.files.forRoot('one'))).toEqual([JSON.stringify(['a.step', 'step'])]);
  expect(store.files.forRoot('two')).toEqual({ [JSON.stringify(['a.step', 'step'])]: view('other root') });
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

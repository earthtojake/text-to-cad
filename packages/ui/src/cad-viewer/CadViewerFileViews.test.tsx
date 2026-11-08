import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { unavailablePromptContext } from '@cad/core/prompt';
import type { FileViewerProps } from '../file-viewer/types.js';
// The built package: its renderers' modules are JSX in `.js`, which only the build compiles.
import { CadViewer, createCadFileSource } from '../../dist/cad-viewer/index.js';
import { createLiveRegistry } from '../../dist/host/liveRegistry.js';
import { createTabStore, memoryTabRecord } from '../../dist/tab-store/tabStore.js';
import { tabFileKey } from '../../dist/tab-store/tabRecord.js';

// The shared FileViewer, reduced to the file on screen's view as its renderer keeps it: the view it
// opens with (the host's record for it), and its last write as it unmounts. That write is the flush
// every renderer makes when its file is left (`useRendererShell`), a cleanup of the very commit that
// left it. A file opens once its document has loaded, as `useFileDocument`'s does (its stat and its
// preparation are awaited): its renderer mounts after the commit that showed the file, and so after
// that commit's effects, `CadViewer`'s among them.
const key = (path: string) => JSON.stringify([path, 'step']);
// `paths`: a document's id, as a host addresses a file, to the file it names (the renderer keys its view
// by the file's path, whichever way it was addressed).
const viewer = vi.hoisted(() => ({ props: null as FileViewerProps | null, opened: [] as [string, unknown][], paths: {} as Record<string, string> }));
vi.mock('../../dist/file-viewer/FileViewer.js', async () => {
  const { createElement, useEffect, useRef, useState } = await import('react');
  function Renderer({ props }: { props: FileViewerProps }) {
    const latest = useRef(props);
    latest.current = props;
    useEffect(() => {
      const path = viewer.paths[String(latest.current.file)] ?? String(latest.current.file);
      viewer.opened.push([path, latest.current.state.renderers?.[key(path)] ?? null]);
      return () => {
        const { state, onStateChange } = latest.current;
        onStateChange({ ...state, renderers: { ...state.renderers, [key(path)]: { left: path } } });
      };
    }, []);
    return null;
  }
  function FileViewer(props: FileViewerProps) {
    viewer.props = props;
    const [loaded, setLoaded] = useState<string | null>(null);
    useEffect(() => {
      let live = true;
      void Promise.resolve().then(() => { if (live) setLoaded(props.file); });
      return () => { live = false; };
    }, [props.file]);
    return props.file && loaded === props.file ? createElement(Renderer, { key: String(props.file), props }) : null;
  }
  return { FileViewer };
});
afterEach(() => { cleanup(); viewer.props = null; viewer.opened.length = 0; viewer.paths = {}; });
// What a file's load awaits, done.
const settle = () => act(async () => {});

function catalogClient(known = true) {
  const entries = ['a', 'b'].map(name => ({ id: `id-${name}`, file: `/models/${name}.step`, sourcePath: `/models/${name}.step`, name: `${name}.step` }));
  const snapshot = { hydrated: true, entries: known ? entries : [], error: '', revision: 1, refreshing: false, catalogRevision: '' };
  return { getSnapshot: () => snapshot as never, subscribe: () => () => {}, refresh: vi.fn(async () => ({ entries: [] })),
    entryOf: (file: string) => snapshot.entries.find(entry => entry.id === file || entry.file === file) ?? null,
    resolveEntry: vi.fn(async () => { throw new Error('unused'); }) };
}

test('the tab keeps the file on screen\'s view alone, which a reload brings back, and a file left for another or for the home opens as it was left when the page shows it again', async () => {
  const client = catalogClient();
  const tabStore = createTabStore(memoryTabRecord());
  tabStore.settings.update({ appearance: 'dark', library: { layout: 'list' } });
  const settings = tabStore.settings.getSnapshot();
  const host = { files: createCadFileSource(client as never), clipboard: { writeText: async () => {}, writeImage: async () => {} },
    promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const } };
  const view = (file: string) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={createLiveRegistry()} file={file} onShow={() => {}} />;
  const opened = () => viewer.opened.at(-1);
  const stored = () => tabStore.getSnapshot().files;
  const [a, b] = ['/models/a.step', '/models/b.step'];

  // A reload: the page goes, the renderer's last write with it, and comes back on the same file,
  // which opens as it was left.
  const page = render(view(a));
  await settle();
  page.unmount();
  expect(stored()).toEqual({ [tabFileKey(a, 'step')]: { left: a } });
  const { rerender } = render(view(a));
  await settle();
  expect(opened()).toEqual([a, { left: a }]);

  // Another file and back, in the same page: the tab holds the view of the file on screen alone, and the
  // page gives the file left its view back as it shows it again.
  await act(async () => { rerender(view(b)); });
  expect(opened()).toEqual([b, null]);
  expect(stored()).toEqual({});
  await act(async () => { rerender(view(a)); });
  expect(opened()).toEqual([a, { left: a }]);
  expect(stored()).toEqual({ [tabFileKey(a, 'step')]: { left: a } });
  await act(async () => { rerender(view(b)); });
  expect(opened()).toEqual([b, { left: b }]);

  // The home and back: the same.
  await act(async () => { rerender(view('')); });
  expect(stored()).toEqual({});
  await act(async () => { rerender(view(a)); });
  expect(opened()).toEqual([a, { left: a }]);

  // A page of its own (a new tab) has nothing set aside: only what the tab's record holds.
  const record = memoryTabRecord();
  const other = createTabStore(record);
  other.files.write(b, 'step', { left: b });
  other.files.retain(a);
  expect(createTabStore(record).getSnapshot().files).toEqual({});

  // None of it is a setting: the tab's are as they were.
  expect(tabStore.settings.getSnapshot()).toBe(settings);
});

test('a file addressed by its id, as the web host does, opens as it was left after a reload, before and after the catalog knows it', async () => {
  viewer.paths = { 'id-a': '/models/a.step', 'id-b': '/models/b.step' };
  for (const known of [true, false]) {
    const client = catalogClient(known);
    const tabStore = createTabStore(memoryTabRecord());
    const host = { files: createCadFileSource(client as never), clipboard: { writeText: async () => {}, writeImage: async () => {} },
      promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const } };
    const view = (file: string) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={createLiveRegistry()} file={file} onShow={() => {}} />;
    const page = render(view('id-a'));
    await settle();
    page.unmount();
    expect(tabStore.getSnapshot().files).toEqual({ [tabFileKey('/models/a.step', 'step')]: { left: '/models/a.step' } });
    const { rerender, unmount } = render(view('id-a'));
    await settle();
    // A renderer reads its view as its file loads, after the page has settled what it keeps: the
    // record must still hold it then.
    expect(viewer.opened.at(-1)).toEqual(['/models/a.step', { left: '/models/a.step' }]);
    expect(tabStore.getSnapshot().files).toEqual({ [tabFileKey('/models/a.step', 'step')]: { left: '/models/a.step' } });
    if (known) {
      // Another file by its id, and back: the one left opens as it was left.
      await act(async () => { rerender(view('id-b')); });
      await act(async () => { rerender(view('id-a')); });
      expect(viewer.opened.at(-1)).toEqual(['/models/a.step', { left: '/models/a.step' }]);
    }
    unmount();
  }
});

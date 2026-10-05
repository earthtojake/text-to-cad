import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import type { FileViewerProps } from '../file-viewer/types.js';
// The built package: its renderers' modules are JSX in `.js`, which only the build compiles.
import { CadViewer, createCadFileSource } from '../../dist/cad-viewer/index.js';
import { createLiveRegistry } from '../../dist/host/liveRegistry.js';
import { createTabStore, memoryTabRecord } from '../../dist/tab-store/tabStore.js';
import { tabFileKey } from '../../dist/tab-store/tabRecord.js';

// The shared FileViewer, reduced to the file on screen's view as its renderer keeps it: the view it
// opens with (the host's record for it), and its last write as it unmounts. That write is the flush
// every renderer makes when its file is left (`useRendererShell`), a cleanup of the very commit that
// left it.
const key = (path: string) => JSON.stringify([path, 'step']);
const viewer = vi.hoisted(() => ({ props: null as FileViewerProps | null, opened: [] as [string, unknown][] }));
vi.mock('../../dist/file-viewer/FileViewer.js', async () => {
  const { createElement, useEffect, useRef } = await import('react');
  function Renderer({ props }: { props: FileViewerProps }) {
    const latest = useRef(props);
    latest.current = props;
    useEffect(() => {
      const path = String(latest.current.file);
      viewer.opened.push([path, latest.current.state.renderers?.[key(path)] ?? null]);
      return () => {
        const { state, onStateChange } = latest.current;
        onStateChange({ ...state, renderers: { ...state.renderers, [key(path)]: { left: path } } });
      };
    }, []);
    return null;
  }
  return { FileViewer: (props: FileViewerProps) => {
    viewer.props = props;
    return props.file ? createElement(Renderer, { key: String(props.file), props }) : null;
  } };
});
afterEach(() => { cleanup(); viewer.props = null; viewer.opened.length = 0; });

function catalogClient() {
  const snapshot = { hydrated: true, entries: [], error: '', revision: 1, refreshing: false, catalogRevision: '' };
  return { getSnapshot: () => snapshot as never, subscribe: () => () => {}, refresh: vi.fn(async () => ({ entries: [] })),
    resolveEntry: vi.fn(async () => { throw new Error('unused'); }) };
}

test('only the file on screen keeps its view: a reload brings it back, and a file left for another or for the home starts over', () => {
  const client = catalogClient();
  const tabStore = createTabStore(memoryTabRecord());
  tabStore.settings.update({ appearance: 'dark', library: { layout: 'list' } });
  const settings = tabStore.settings.getSnapshot();
  const host = { files: createCadFileSource(client as never), clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const } };
  const view = (file: string) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={createLiveRegistry()} file={file} onShow={() => {}} />;
  const opened = () => viewer.opened.at(-1);
  const stored = () => tabStore.getSnapshot().files;

  // A reload: the page goes, the renderer's last write with it, and comes back on the same file,
  // which opens as it was left.
  render(view('/models/a.step')).unmount();
  expect(stored()).toEqual({ [tabFileKey('/models/a.step', 'step')]: { left: '/models/a.step' } });
  const { rerender } = render(view('/models/a.step'));
  expect(opened()).toEqual(['/models/a.step', { left: '/models/a.step' }]);

  // Another file and back: the file left keeps nothing.
  rerender(view('/models/b.step'));
  expect(opened()).toEqual(['/models/b.step', null]);
  rerender(view('/models/a.step'));
  expect(opened()).toEqual(['/models/a.step', null]);

  // The home and back: nothing is on screen, so nothing is kept.
  act(() => { viewer.props!.onStateChange({ ...viewer.props!.state, renderers: { [key('/models/a.step')]: { camera: 'moved' } } }); });
  rerender(view(''));
  expect(stored()).toEqual({});
  rerender(view('/models/a.step'));
  expect(opened()).toEqual(['/models/a.step', null]);

  // None of it is a setting: the tab's are as they were.
  expect(tabStore.settings.getSnapshot()).toBe(settings);
});

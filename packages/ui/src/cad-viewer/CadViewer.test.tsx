import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import type { FileViewerProps } from '../file-viewer/types.js';
// The built package: its renderers' modules are JSX in `.js`, which only the build compiles.
import { CadViewer, createCatalogFileSource } from '../../dist/cad-viewer/index.js';
import { createLiveRegistry } from '../../dist/host/liveRegistry.js';
import { createTabStore, memoryTabRecord } from '../../dist/tab-store/tabStore.js';

// The shared FileViewer, reduced to what this composition hands it: the view on screen, and the
// one a card's picture is drawn in out of sight (a compact one), while it is mounted.
const viewer = vi.hoisted(() => ({ props: null as FileViewerProps | null, hidden: null as FileViewerProps | null }));
vi.mock('../../dist/file-viewer/FileViewer.js', async () => {
  const { useEffect } = await import('react');
  return { FileViewer: (props: FileViewerProps) => {
    const hidden = Boolean(props.host.environment.compact);
    if (hidden) viewer.hidden = props; else viewer.props = props;
    useEffect(() => () => { if (hidden) viewer.hidden = null; }, [hidden]);
    return null;
  } };
});
afterEach(() => { cleanup(); viewer.props = null; viewer.hidden = null; });

function catalogClient() {
  let snapshot = { hydrated: false, entries: [] as Record<string, unknown>[], error: '', revision: 0, refreshing: true, rootId: 'a' };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot as never,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    refresh: vi.fn(async () => ({ entries: [] })),
    resolveEntry: vi.fn(async () => { throw new Error('unused'); }),
    publish(entries: Record<string, unknown>[]) { snapshot = { ...snapshot, hydrated: true, refreshing: false, entries, revision: snapshot.revision + 1 }; for (const listener of [...listeners]) listener(); },
  };
}
const library = { list: async () => [], change: async () => [], thumbnail: async () => null, open: async () => {} };

test('the CAD viewer follows its catalog, and shows what the viewer asks for through the host', async () => {
  const client = catalogClient();
  const tabStore = createTabStore(memoryTabRecord());
  const live = createLiveRegistry();
  const shows: string[] = [], shown: (string | null)[] = [];
  const host = { files: createCatalogFileSource(client as never, { id: 'a', rootName: 'root' }), clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const } };
  const view = (file: string) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={live} file={file} rootPath="/models"
    library={library} onShow={next => shows.push(next)} onShown={next => shown.push(next)} />;
  const { rerender } = render(view('parts/a.step'));
  const props = () => viewer.props!;
  // One renderer per file family, every one reading the tab's settings.
  expect(props().renderers.map(renderer => renderer.id)).toEqual(['step', 'dxf', 'glb', 'mesh', 'robot']);
  // While the catalog resolves the requested file, the navbar names nothing...
  expect(props().navigationPath).toBeNull();
  await act(async () => client.publish([{ file: '/models/parts/a.step', rootRelativeFile: 'parts/a.step' }, { file: 'b.step' }]));
  // ...then the file, as the catalog names it, which the host hears of once.
  expect(props().navigationPath).toBe('parts/a.step');
  expect(shown).toEqual([null, 'parts/a.step']);
  rerender(view('gone.step'));
  // A missing file is named by its own path once the catalog has answered.
  expect(props().navigationPath).toBe('gone.step');
  rerender(view('parts/a.step'));

  // A file the catalog does not list is not shown; one it lists is, with the panel it asked for.
  act(() => props().host.navigation.openFile('nowhere.step', { target: 'new', panel: 'tree' }));
  expect(shows).toEqual([]);
  act(() => props().host.navigation.openFile('b.step', { target: 'new', panel: 'tree' }));
  expect([shows, props().state.panel]).toEqual([['b.step'], 'tree']);
  // The file on screen keeps its panel unless one is asked for.
  act(() => props().host.navigation.openFile('parts/a.step', { target: 'current' }));
  expect([shows.length, props().state.panel]).toEqual([1, 'tree']);
  act(() => props().host.navigation.openFile('parts/a.step', { target: 'new', panel: '' }));
  expect(props().state.panel).toBe('');
  // The mark leads home: the host shows no file.
  act(() => props().host.navigation.home!());
  expect(shows.at(-1)).toBe('');

  // The home is the library, laid out as the tab keeps it.
  const home = props().presentation!.home as { props: { layout: string; onLayoutChange(layout: string): void } };
  expect(home.props.layout).toBe('grid');
  act(() => home.props.onLayoutChange('list'));
  expect(tabStore.settings.getSnapshot().library.layout).toBe('list');
  expect((props().presentation!.home as { props: { layout: string } }).props.layout).toBe('list');

  // The catalog is read again when the person comes back to the page.
  client.refresh.mockClear();
  act(() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); });
  expect(client.refresh).toHaveBeenCalledTimes(2);
  expect(client.refresh.mock.calls[0][0]).toMatchObject({ markRefreshing: false });
});

test('a root read a folder at a time shows what its explorer lists, which its catalog does not hold', () => {
  const client = catalogClient();
  const shows: string[] = [];
  const host = { files: createCatalogFileSource(client as never, { id: 'fs', rootName: '/' }), clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: unavailablePromptContext, environment: { colorScheme: 'dark' as const } };
  render(<CadViewer client={client as never} host={host} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()} file="" rootPath="/"
    library={library} onShow={next => shows.push(next)} accept={path => path} />);
  act(() => viewer.props!.host.navigation.openFile('Users/me/part.stl', { target: 'new', panel: 'tree' }));
  expect(shows).toEqual(['Users/me/part.stl']);
});

test('the home pictures a card out of sight, in a viewer of its own, from what is already built, and never builds one', async () => {
  const client = catalogClient();
  const pictureClient = { ...catalogClient(), requestArtifactStatus: vi.fn(async (file: string) => ({ state: file === 'a.stl' ? 'compiled' : 'not-compiled' })) };
  const pictured = { ...library, pictureFrom: (model: { path: string }) => ({ client: pictureClient as never, file: model.path.slice(1), keep: async () => {} }) };
  const host = { files: createCatalogFileSource(client as never, { id: 'a', rootName: 'root' }), clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const } };
  const view = (file: string) => <CadViewer client={client as never} host={host} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()} file={file}
    rootPath="/models" library={pictured} onShow={() => {}} />;
  const { rerender } = render(view(''));
  const picture = (viewer.props!.presentation!.home as { props: { picture(model: { path: string }): Promise<boolean> } }).props.picture;
  // A model whose display is not built keeps its placeholder: its status is read, and that is all.
  await expect(picture({ path: '/b.step' })).resolves.toBe(false);
  expect(viewer.hidden).toBeNull();
  // One that is built is drawn in a view of its own: compact, with renderers of its own, reaching no prompt.
  let drawn!: Promise<boolean>;
  await act(async () => { drawn = picture({ path: '/a.stl' }); });
  const hidden = viewer.hidden!;
  expect([hidden.file, hidden.host.promptContext.getSnapshot().kind]).toEqual(['a.stl', 'unavailable']);
  expect(hidden.renderers).not.toBe(viewer.props!.renderers);
  // A view that fails gives the card up, and goes.
  act(() => hidden.onError!(new Error('unreadable')));
  await expect(drawn).resolves.toBe(false);
  expect(viewer.hidden).toBeNull();
  // A file opened while one is drawn has the screen to itself.
  let again!: Promise<boolean>;
  await act(async () => { again = picture({ path: '/a.stl' }); });
  expect(viewer.hidden).not.toBeNull();
  rerender(view('parts/a.step'));
  await expect(again).resolves.toBe(false);
  expect(viewer.hidden).toBeNull();
});

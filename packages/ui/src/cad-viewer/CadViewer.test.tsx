import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import type { FileViewerProps } from '../file-viewer/types.js';
// The built package: its renderers' modules are JSX in `.js`, which only the build compiles.
import { CadViewer, createCadFileSource } from '../../dist/cad-viewer/index.js';
import { createLiveRegistry } from '../../dist/host/liveRegistry.js';
import { createTabStore, memoryTabRecord } from '../../dist/tab-store/tabStore.js';
import { viewerLinks } from '../../dist/file-viewer/navigation/links.js';

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
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewer.props = null; viewer.hidden = null; });

function cadClient() {
  let snapshot = { hydrated: false, entries: [] as Record<string, unknown>[], error: '', revision: 0, refreshing: true, catalogRevision: '' };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot as never,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    refresh: vi.fn(async () => ({ entries: [] })),
    resolveEntry: vi.fn(async () => { throw new Error('unused'); }),
    folder: vi.fn(), search: vi.fn(),
    publish(entries: Record<string, unknown>[]) { snapshot = { ...snapshot, hydrated: true, refreshing: false, entries, revision: snapshot.revision + 1 }; for (const listener of [...listeners]) listener(); },
  };
}
const ports = (client: ReturnType<typeof cadClient>, extra: object = {}) => ({ files: createCadFileSource(client as never),
  clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, ...extra });
const library = { list: async () => [], change: async () => [], thumbnail: async () => null, open: async () => {} };
const props = () => viewer.props!;

test('the CAD viewer shows one file by its absolute path, the home with none, and what the viewer asks for through the host', async () => {
  const client = cadClient();
  const tabStore = createTabStore(memoryTabRecord());
  const shows: string[] = [], shown: (string | null)[] = [];
  const host = ports(client);
  const view = (file: string, homed = true) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={createLiveRegistry()} file={file}
    library={homed ? library : undefined} onShow={next => shows.push(next)} onShown={next => shown.push(next)} />;
  const { rerender } = render(view('C:\\models\\a.step'));
  // One renderer per file family, every one reading the tab's settings.
  expect(props().renderers.map(renderer => renderer.id)).toEqual(['step', 'dxf', 'glb', 'mesh', 'robot']);
  // The file in the viewer's one spelling, which the host hears of once the catalog has it.
  expect([props().file, shown]).toEqual(['C:/models/a.step', [null]]);
  await act(async () => client.publish([{ file: 'C:/models/a.step' }]));
  expect(shown).toEqual([null, 'C:/models/a.step']);

  // A file the viewer asks for (a pick in the explorer, a renderer's link) is the host's to show;
  // the file on screen is shown already.
  act(() => props().host.navigation.openFile('C:\\models\\b.step'));
  act(() => props().host.navigation.openFile('C:/models/a.step'));
  expect(shows).toEqual(['C:/models/b.step']);
  // The navbar's logo leads home, which is no file; a host with no library has no home to lead to.
  act(() => props().host.navigation.home!());
  expect(shows.at(-1)).toBe('');
  rerender(view('C:/models/a.step', false));
  expect(props().host.navigation.home).toBeUndefined();

  // No file is the home: the library, laid out as the tab keeps it.
  rerender(view(''));
  expect(props().file).toBeNull();
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

test('a file that does not exist says so by its path, and any other failure says why, each with the way home where the host has one', () => {
  const client = cadClient();
  const shows: string[] = [];
  const view = (homed: boolean) => <CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()}
    file="/models/gone.step" library={homed ? library : undefined} onShow={next => shows.push(next)} />;
  const { rerender } = render(view(true));
  const failure = (missing: boolean) => render(<>{props().presentation!.error!({ message: 'The viewer stopped', missing })}</>);
  const missing = failure(true);
  expect([missing.getByText('File does not exist'), missing.getByText('/models/gone.step')]).toHaveLength(2);
  fireEvent.click(missing.getByRole('button', { name: 'Go home' }));
  expect(shows).toEqual(['']);
  missing.unmount();
  const broken = failure(false);
  expect([broken.getByText('Could not open that file'), broken.getByText('The viewer stopped'), broken.getByRole('button', { name: 'Go home' })]).toHaveLength(3);
  broken.unmount();
  rerender(view(false));
  expect(failure(true).queryByRole('button', { name: 'Go home' })).toBeNull();
});

test('the home pictures a card out of sight, in a viewer of its own, from what is already built, and never builds one', async () => {
  const client = { ...cadClient(), requestArtifactStatus: vi.fn(async (file: string) => ({ state: file === '/models/a.stl' ? 'compiled' : 'not-compiled' })) };
  const host = ports(client);
  const view = (file: string) => <CadViewer client={client as never} host={host} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()} file={file}
    library={library} onThumbnail={async () => {}} onShow={() => {}} />;
  const { rerender } = render(view(''));
  const picture = (props().presentation!.home as { props: { picture(model: { path: string }): Promise<boolean> } }).props.picture;
  // A model whose display is not built keeps its placeholder: its status is read, and that is all.
  await expect(picture({ path: '/models/b.step' })).resolves.toBe(false);
  expect(viewer.hidden).toBeNull();
  // One that is built is drawn in a view of its own: compact, with renderers of its own, reaching no prompt.
  let drawn!: Promise<boolean>;
  await act(async () => { drawn = picture({ path: '/models/a.stl' }); });
  const hidden = viewer.hidden!;
  expect([hidden.file, hidden.host.promptContext.getSnapshot().kind]).toEqual(['/models/a.stl', 'unavailable']);
  expect(hidden.renderers).not.toBe(props().renderers);
  // A view that fails gives the card up, and goes.
  act(() => hidden.onError!(new Error('unreadable')));
  await expect(drawn).resolves.toBe(false);
  expect(viewer.hidden).toBeNull();
  // A file opened while one is drawn has the screen to itself.
  let again!: Promise<boolean>;
  await act(async () => { again = picture({ path: '/models/a.stl' }); });
  expect(viewer.hidden).not.toBeNull();
  rerender(view('/models/parts/a.step'));
  await expect(again).resolves.toBe(false);
  expect(viewer.hidden).toBeNull();
});

test("the person's settings go to the app menu over every file; the home shows the host's links", async () => {
  const client = cadClient();
  const appSettings = [{ id: 'analytics', label: 'Share anonymous usage data', checked: false, onCheckedChange: () => {} }];
  render(<CadViewer client={client as never} host={ports(client, { links: viewerLinks({ version: '0.7.4' }) })} tabStore={createTabStore(memoryTabRecord())}
    live={createLiveRegistry()} file="/models/parts/a.step" library={library} appSettings={appSettings} onShow={() => {}} />);
  // FileViewer's navbar logo opens them (its own suite).
  expect(props().appSettings).toBe(appSettings);
  const home = render(props().presentation!.home as ReactElement);
  const row = await home.findByRole('navigation', { name: 'CAD links' });
  expect([...row.querySelectorAll('a, button')].map(node => node.getAttribute('aria-label'))).toEqual(['GitHub', 'Discord', 'X']);
});

test('the features the person left on reach every file the viewer shows', () => {
  const client = cadClient();
  render(<CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()}
    file="/models/parts/a.step" features={{ quickEdit: false }} onShow={() => {}} />);
  expect(props().features).toEqual({ quickEdit: false });
});

import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { unavailablePromptContext } from '@cad/core/prompt';
import type { FileViewerProps } from '../file-viewer/types.js';
// The built package: its renderers' modules are JSX in `.js`, which only the build compiles.
import { CadViewer, createCadFileSource } from '../../dist/cad-viewer/index.js';
import { createLiveRegistry } from '../../dist/host/liveRegistry.js';
import { createTabStore, memoryTabRecord } from '../../dist/tab-store/tabStore.js';
import { viewerLinks } from '../../dist/file-viewer/navigation/links.js';

// The shared FileViewer, reduced to what this composition hands it: the one view, on screen.
const viewer = vi.hoisted(() => ({ props: null as FileViewerProps | null }));
vi.mock('../../dist/file-viewer/FileViewer.js', () => ({ FileViewer: (props: FileViewerProps) => { viewer.props = props; return null; } }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewer.props = null; });

function cadClient() {
  let snapshot = { hydrated: false, entries: [] as Record<string, unknown>[], error: '', revision: 0, refreshing: true, catalogRevision: '' };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot as never,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    refresh: vi.fn(async () => ({ entries: [] })),
    resolveEntry: vi.fn(async () => { throw new Error('unused'); }),
    publish(entries: Record<string, unknown>[]) { snapshot = { ...snapshot, hydrated: true, refreshing: false, entries, revision: snapshot.revision + 1 }; for (const listener of [...listeners]) listener(); },
  };
}
const ports = (client: ReturnType<typeof cadClient>, extra: object = {}) => ({ files: createCadFileSource(client as never),
  clipboard: { writeText: async () => {}, writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, ...extra });
const library = { list: async () => [], change: async () => [], thumbnail: async () => null, open: async () => {} };
const props = () => viewer.props!;

test('the viewer shows one file by its absolute path, the home with none, and what the viewer asks for through the host', async () => {
  const client = cadClient();
  const tabStore = createTabStore(memoryTabRecord());
  const shows: string[] = [], shown: (string | null)[] = [];
  const host = ports(client);
  const view = (file: string, homed = true) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={createLiveRegistry()} file={file}
    library={homed ? library : undefined} onShow={next => shows.push(next)} onShown={next => shown.push(next)} />;
  const { rerender } = render(view('C:\\models\\a.step'));
  // One renderer per file family, every one reading the tab's settings.
  // A STEP opens as an .xbf does, in the engine document's renderer: the STEP renderer is not registered.
  expect(props().renderers.map(renderer => renderer.id)).toEqual(['dxf', 'board', 'schematic', 'glb', 'mesh', 'robot', 'model']);
  // The file in the viewer's one spelling, which the host hears of once the catalog has it.
  expect([props().file, shown]).toEqual(['C:/models/a.step', [null]]);
  await act(async () => client.publish([{ file: 'C:/models/a.step' }]));
  expect(shown).toEqual([null, 'C:/models/a.step']);

  // A file the viewer asks for (the project's previous or next, a renderer's link) is the host's to show;
  // the file on screen is shown already.
  act(() => props().host.navigation.openFile!('C:\\models\\b.step'));
  act(() => props().host.navigation.openFile!('C:/models/a.step'));
  expect(shows).toEqual(['C:/models/b.step']);
  // The navbar's logo leads home, which is no file. A host with no library (a file handler's) shows
  // its file and nothing else: no home to lead to, and no other file to open.
  act(() => props().host.navigation.home!());
  expect(shows.at(-1)).toBe('');
  rerender(view('C:/models/a.step', false));
  expect([props().host.navigation.home, props().host.navigation.openFile]).toEqual([undefined, undefined]);

  // No file is the home: the library, laid out and ordered as the tab keeps it, each choice kept beside the other.
  rerender(view(''));
  expect(props().file).toBeNull();
  const home = () => props().presentation!.home as { props: { layout: string; sort: string; onLayoutChange(layout: string): void; onSortChange(sort: string): void } };
  expect([home().props.layout, home().props.sort]).toEqual(['grid', 'activity']);
  act(() => home().props.onLayoutChange('list'));
  act(() => home().props.onSortChange('kind'));
  expect(tabStore.settings.getSnapshot().library).toEqual({ layout: 'list', sort: 'kind' });
  expect([home().props.layout, home().props.sort]).toEqual(['list', 'kind']);
  // Neither is reset by leaving the home for a file and coming back.
  rerender(view('C:/models/a.step'));
  rerender(view(''));
  expect([home().props.layout, home().props.sort]).toEqual(['list', 'kind']);
  act(() => home().props.onLayoutChange('grid'));
  expect(tabStore.settings.getSnapshot().library).toEqual({ layout: 'grid', sort: 'kind' });

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

test('the failure states read in the language the host names, and follow it when it changes', () => {
  const client = cadClient();
  const tabStore = createTabStore(memoryTabRecord());
  const live = createLiveRegistry();
  const view = (locale?: string) => <CadViewer client={client as never} host={ports(client, { environment: { colorScheme: 'light', locale } })} tabStore={tabStore} live={live}
    file="/models/gone.step" library={library} onShow={() => {}} />;
  const { rerender } = render(view());
  // The host's `environment.locale` is the language: a change re-draws "Go home" and both failure titles.
  const failure = (missing: boolean) => render(<>{props().presentation!.error!({ message: 'The viewer stopped', missing })}</>);
  expect(failure(true).getByText('File does not exist')).toBeTruthy();
  failure(true).unmount();
  rerender(view('zh-CN'));
  const zh = failure(true);
  expect(zh.getByText('文件不存在')).toBeTruthy();
  expect(zh.getByRole('button', { name: '返回主页' })).toBeTruthy();
  zh.unmount();
  rerender(view('fr'));
  const back = failure(false);
  expect(back.getByText('Could not open that file')).toBeTruthy();
  back.unmount();
});

test('a model document on screen is pictured by its id once it settles, once per build the engine holds', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const client = cadClient();
  const live = createLiveRegistry();
  const kept: [string, string][] = [];
  render(<CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())} live={live} file={id}
    library={library} onThumbnail={async (png, file) => { kept.push([await png.text(), file]); }} onShow={() => {}} />);
  await act(async () => client.publish([{ id, file: id, sourcePath: null, hash: 'model:1' }]));
  let pictures = 0;
  const shot = vi.fn(async () => new Blob([`build ${++pictures}`]));
  await act(async () => { live.binding.bind({ readState: () => ({ active: true, loading: false, resource: { kind: 'cad-model', path: id } }),
    capture: async () => new Blob(), thumbnail: shot }); });
  await vi.waitFor(() => expect(kept).toEqual([['build 1', id]]));
  // The catalog read again with the same build changes nothing; a rebuild is pictured again.
  await act(async () => client.publish([{ id, file: id, sourcePath: null, hash: 'model:1', name: 'cube' }]));
  expect(shot).toHaveBeenCalledTimes(1);
  await act(async () => client.publish([{ id, file: id, sourcePath: null, hash: 'model:2' }]));
  await vi.waitFor(() => expect(kept).toEqual([['build 1', id], ['build 2', id]]));
});

test("the person's settings and the host's links go to the file viewer for the app menu (the home's Settings); the home has no links of its own", async () => {
  const client = cadClient();
  const appSettings = [{ id: 'analytics', label: 'Share anonymous usage data', checked: false, onCheckedChange: () => {} }];
  render(<CadViewer client={client as never} host={ports(client, { links: viewerLinks({ version: '0.7.4' }) })} tabStore={createTabStore(memoryTabRecord())}
    live={createLiveRegistry()} file="/models/parts/a.step" library={library} appSettings={appSettings} onShow={() => {}} />);
  // FileViewer hands them to the home's sidebar for its Settings row (their own suites).
  expect(props().appSettings).toBe(appSettings);
  expect(props().host.links).toEqual(expect.objectContaining({ version: '0.7.4' }));
  const home = render(props().presentation!.home as ReactElement);
  await home.findByRole('heading', { level: 1, name: 'Recents' });
  expect(home.queryByRole('link')).toBeNull();
});

test("the home's sidebar is kept in the tab's settings as a file's panel is in its view: the person's choice and its width, handed back to the home each time it is shown and after a reload", () => {
  const client = cadClient();
  const storage = memoryTabRecord();
  const page = (tabStore: ReturnType<typeof createTabStore>, file = '') => <CadViewer client={client as never} host={ports(client)} tabStore={tabStore} live={createLiveRegistry()}
    file={file} library={library} onShow={() => {}} />;
  const home = () => props().presentation!.home as { props: { panel: object | null; onPanelChange(panel: object): void } };
  const tabStore = createTabStore(storage);
  const { rerender, unmount } = render(page(tabStore));
  // Nothing chosen yet: nothing kept, and the home's width decides.
  expect([home().props.panel, tabStore.settings.getSnapshot().library]).toEqual([null, { layout: 'grid', sort: 'activity' }]);
  act(() => home().props.onPanelChange({ open: false }));
  act(() => home().props.onPanelChange({ open: false, width: 304 }));
  expect(tabStore.settings.getSnapshot().library).toEqual({ layout: 'grid', sort: 'activity', panel: { open: false, width: 304 } });
  // It is the home's, beside its layout and its order: neither write drops the other, and a file shown meanwhile keeps none of it.
  act(() => (home().props as unknown as { onLayoutChange(layout: string): void }).onLayoutChange('list'));
  rerender(page(tabStore, '/models/a.step'));
  rerender(page(tabStore));
  expect([home().props.panel, tabStore.settings.getSnapshot().library.layout, tabStore.getSnapshot().files]).toEqual([{ open: false, width: 304 }, 'list', {}]);
  // A reload of the tab (its storage read again) brings it back; what the person undid is gone from it.
  unmount();
  const reloaded = createTabStore(storage);
  render(page(reloaded));
  expect(home().props.panel).toEqual({ open: false, width: 304 });
  act(() => home().props.onPanelChange({}));
  expect(reloaded.settings.getSnapshot().library).toEqual({ layout: 'list', sort: 'activity' });
});

test('a document named by its id is its row, joined by id: the host hears its file and its id, and one the engine does not hold says why', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const base = cadClient();
  const client = { ...base, entryOf: (path: string) => (base.getSnapshot() as unknown as { entries: Record<string, unknown>[] }).entries
    .find(entry => entry.id === path || entry.file === path) ?? null };
  const shown: [string | null, string | null][] = [];
  render(<CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()}
    file={id} library={library} onShow={() => {}} onShown={(file, ident) => shown.push([file, ident])} />);
  // A symlink's target and its link are one document, one row: the file is heard by the row's own path.
  await act(async () => client.publish([{ id, file: '/models/real/a.step' }]));
  expect(shown.at(-1)).toEqual(['/models/real/a.step', id]);
  // One the engine does not hold: one title, over the engine's own words.
  const missing = render(<>{props().presentation!.error!({ message: `no document ${id} is held`, missing: true })}</>);
  expect([missing.getByText('This model is no longer held'), missing.getByText(`no document ${id} is held`)].every(Boolean)).toBe(true);
});

test("the host's Full size is the navbar's one host action: Export is the file menu's, never the navbar's", () => {
  const client = cadClient();
  const view = (extra: object) => <CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())} live={createLiveRegistry()} file=""
    library={library} onShow={() => {}} {...extra} />;
  const { rerender } = render(view({ fullSize: <b data-full="" /> }));
  const { container } = render(<>{props().navbarActions}</>);
  expect([...container.querySelectorAll('[data-full]')].map(node => node.tagName)).toEqual(['B']);
  expect(container.querySelector('[data-export-menu]')).toBeNull();
  // A host that hands none: the navbar has no host action, and the file menu no Export without downloads.
  rerender(view({}));
  expect([props().navbarActions ?? null, props().fileMenuItems ?? null]).toEqual([null, null]);
});

test("What's new is said over the home, and over a file once its view is up: never over its loading page", () => {
  const client = cadClient();
  const live = createLiveRegistry();
  const whatsNew = { entry: '0.11', onDismiss: vi.fn() };
  const view = (file: string) => <CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())} live={live} file={file}
    library={library} onShow={() => {}} whatsNew={whatsNew} />;
  const { rerender } = render(view(''));
  expect(screen.getByRole('dialog').getAttribute('data-whats-new')).toBe('0.11');
  rerender(view('/m/a.step'));
  expect(screen.queryByRole('dialog')).toBeNull();  // the file's loading page: its renderer is not up
  let release = () => {};
  act(() => { release = live.binding.bind({ readState: () => ({}), capture: async () => new Blob(), thumbnail: async () => new Blob() }); });
  expect(screen.getByRole('dialog')).toBeTruthy();
  act(() => release());
});

type HomeProps = { place: unknown; from: { path: string; id: string | null; name: string } | null; onBack(): void; onPlaceChange(place: unknown): void;
  onPlaceShown(name: string): void; navigation: { hrefOf?: unknown; openBeside?: unknown } };
const homeProps = () => (props().presentation!.home as { props: HomeProps }).props;

test("a document in a project has its project's name before its own and its folder's files, read again while it is shown; the name shows that folder with the document just left remembered", async () => {
  const listed = { project: { id: 'p1', name: 'parts', root: '/models/parts', created: 1, opened: 1, missing: false }, path: 'v3', folders: [], truncated: false,
    documents: [{ path: '/models/parts/v3/a.step', name: 'a.step', folder: '/models/parts/v3' }] };
  const base = cadClient();
  const client = Object.assign(base, { projectFolder: vi.fn(async () => listed),
    entryOf: (path: string) => (base.getSnapshot() as unknown as { entries: Record<string, unknown>[] }).entries.find(entry => entry.file === path) ?? null });
  // A host that keeps the file and the place itself, as an app does: what it is asked to show is what it shows next.
  const shows: [string, unknown][] = [];
  const tabStore = createTabStore(memoryTabRecord());
  const host = ports(client);
  const view = (file: string, extra: object = {}) => <CadViewer client={client as never} host={host} tabStore={tabStore}
    live={createLiveRegistry()} file={file} name="a.step" library={library} onShow={(next, place) => shows.push([next, place])} {...extra} />;
  const { rerender } = render(view('/models/parts/v3/a.step'));
  expect(props().project).toBeNull();
  await act(async () => client.publish([{ id: 'f1', file: '/models/parts/v3/a.step', name: 'a.step', project: { id: 'p1', name: 'parts', root: '/models/parts', folder: 'v3' } }]));
  // Its name from its row; the files of its folder as the client reads them, which [ and ] step through.
  expect(props().project?.name).toBe('parts');
  await vi.waitFor(() => expect(props().project?.documents).toEqual(listed.documents));
  expect(client.projectFolder).toHaveBeenCalledWith('p1', expect.objectContaining({ path: 'v3', signal: expect.any(AbortSignal) }));
  // A host with no addresses: the name is no link.
  expect(props().project?.href).toBeNull();
  // Its name shows the home at that project's page, at the folder the document is in.
  act(() => props().project!.onShow());
  expect(shows.at(-1)).toEqual(['', { view: 'project', project: 'p1', path: 'v3' }]);
  rerender(view('', { place: { view: 'project', project: 'p1', path: 'v3' } }));
  await vi.waitFor(() => expect(homeProps()).toMatchObject({ place: { view: 'project', project: 'p1', path: 'v3' } }));
  // The document just left is the home's to ring, by its path and its id, with the way back to it.
  expect(homeProps().from).toMatchObject({ path: '/models/parts/v3/a.step', id: 'f1', name: 'a.step' });
  act(() => homeProps().onBack());
  expect(shows.at(-1)).toEqual(['/models/parts/v3/a.step', undefined]);
  // Back on it and at its project's page again (the browser's Back): still the one just left.
  rerender(view('/models/parts/v3/a.step'));
  rerender(view('', { place: { view: 'project', project: 'p1' } }));
  expect(homeProps().from).toMatchObject({ path: '/models/parts/v3/a.step' });
  // Another place forgets it, for good: its project's page again has no ring.
  rerender(view('', { place: { view: 'recents' } }));
  expect(homeProps().from).toBeNull();
  rerender(view('', { place: { view: 'project', project: 'p1' } }));
  expect(homeProps().from).toBeNull();
  // So does another document opened from the project's page.
  rerender(view('/models/parts/v3/a.step'));
  act(() => props().project!.onShow());
  rerender(view('', { place: { view: 'project', project: 'p1' } }));
  expect(homeProps().from).not.toBeNull();
  rerender(view('/models/parts/v3/b.step', { place: { view: 'project', project: 'p1' } }));
  rerender(view('', { place: { view: 'project', project: 'p1' } }));
  expect(homeProps().from).toBeNull();
  // A host with no home has no project to show.
  rerender(view('/models/parts/v3/a.step', { library: undefined }));
  expect(props().project).toBeNull();
});

test("the home's place is the host's where it keeps one, the view's own otherwise, and the host hears each place's name", async () => {
  const client = cadClient();
  const shows: [string, unknown][] = [], named: [unknown, string][] = [];
  const host = ports(client);
  const tabStore = createTabStore(memoryTabRecord());
  const view = (extra: object = {}) => <CadViewer client={client as never} host={host} tabStore={tabStore} live={createLiveRegistry()} file=""
    library={library} onShow={(next, place) => shows.push([next, place])} onHomeShown={(place, name) => named.push([place, name])} {...extra} />;
  const { rerender } = render(view());
  // A host that keeps no place: the view starts at Recents and keeps where the person goes, telling the host too.
  expect(homeProps().place).toEqual({ view: 'recents' });
  act(() => homeProps().onPlaceChange({ view: 'pinned' }));
  expect([homeProps().place, shows.at(-1)]).toEqual([{ view: 'pinned' }, ['', { view: 'pinned' }]]);
  // The navbar's logo leads to the home's first place; a press's event is no place.
  act(() => (props().host.navigation.home as (event?: unknown) => void)({ view: window, type: 'click' }));
  expect([homeProps().place, shows.at(-1)]).toEqual([{ view: 'recents' }, ['', { view: 'recents' }]]);
  act(() => props().host.navigation.home!({ view: 'project', project: 'p1' }));
  expect(homeProps().place).toEqual({ view: 'project', project: 'p1' });
  // A host that keeps the place (its address, its history) is the one that says it.
  rerender(view({ place: { view: 'pinned' } }));
  expect(homeProps().place).toEqual({ view: 'pinned' });
  // The home says its place's name, as the person reads it, for the host's page title.
  act(() => homeProps().onPlaceShown('Starred'));
  expect(named).toEqual([[{ view: 'pinned' }, 'Starred']]);
  // A place the home no longer has (Standalone, whose documents are Recents'), asked for, is Recents.
  act(() => props().host.navigation.home!({ view: 'standalone' } as never));
  expect(shows.at(-1)).toEqual(['', { view: 'recents' }]);
});

test("the host's addresses and its Open in new tab reach the home, the navbar's project name and the viewer's navigation; a view with no home has neither", async () => {
  const base = cadClient();
  const client = Object.assign(base, { projectFolder: vi.fn(async () => ({ project: { id: 'p1', name: 'parts', root: '/models/parts', created: 1, opened: 1, missing: false }, path: '', folders: [], documents: [], truncated: false })),
    entryOf: (path: string) => (base.getSnapshot() as unknown as { entries: Record<string, unknown>[] }).entries.find(entry => entry.file === path) ?? null });
  const hrefOf = (target: { document?: string; home?: { view: string; project?: string } }) => target.home ? `/?project=${target.home.project}` : `/${target.document}`;
  const openBeside = { kind: 'tab' as const, open() {} };
  const host = ports(client, { navigation: { hrefOf, openBeside } });
  const tabStore = createTabStore(memoryTabRecord());
  const view = (file: string, homed = true) => <CadViewer client={client as never} host={host as never} tabStore={tabStore} live={createLiveRegistry()} file={file}
    library={homed ? library : undefined} onShow={() => {}} />;
  const { rerender } = render(view('/models/parts/a.step'));
  await act(async () => client.publish([{ id: 'f1', file: '/models/parts/a.step', project: { id: 'p1', name: 'parts', root: '/models/parts' } }]));
  // The viewer's own navigation carries them beside its own openFile and home.
  expect([props().host.navigation.hrefOf, props().host.navigation.openBeside, typeof props().host.navigation.home]).toEqual([hrefOf, openBeside, 'function']);
  // The project's name is a link to its page.
  expect(props().project?.href).toBe('/?project=p1');
  rerender(view(''));
  expect(homeProps().navigation).toEqual({ hrefOf, openBeside });
  // A view that shows one file alone links nowhere.
  rerender(view('/models/parts/a.step', false));
  expect(props().host.navigation).toEqual({});
});

test("a document in no project offers to import its folder as a project, the chooser starting at its folder (a model's: its script's), and is read again once it is one", async () => {
  const base = cadClient();
  const client = Object.assign(base, { entryOf: (path: string) => (base.getSnapshot() as unknown as { entries: Record<string, unknown>[] }).entries
    .find(entry => entry.file === path || entry.id === path) ?? null });
  const importFolder = vi.fn(async () => ({ project: { id: 'p1', name: 'parts', root: '/models/parts' }, made: true, folder: '/models/parts' }));
  const view = (file: string) => <CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())}
    live={createLiveRegistry()} file={file} library={{ ...library, importFolder }} onShow={() => {}} />;
  const { rerender } = render(view('/models/parts/a.step'));
  await act(async () => client.publish([{ id: 'f1', file: '/models/parts/a.step', project: null }]));
  client.refresh.mockClear();
  await act(async () => { props().onImportFolder!(); });
  expect(importFolder).toHaveBeenLastCalledWith('/models/parts');
  expect(client.refresh).toHaveBeenCalledTimes(1);
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  rerender(view(id));
  await act(async () => client.publish([{ id, file: id, sourcePath: null, script: '/models/gear/src/gear.py', project: null }]));
  await act(async () => { props().onImportFolder!(); });
  expect(importFolder).toHaveBeenLastCalledWith('/models/gear/src');
  // In a project already, it has none.
  await act(async () => client.publish([{ id, file: id, sourcePath: null, script: '/models/gear/src/gear.py', project: { id: 'p2', name: 'gear', root: '/models/gear' } }]));
  expect(props().project?.name).toBe('gear');
});

test("mounts the search of every document once, over a document and the home, with the document on screen and its project; a host with no library has none", async () => {
  const base = cadClient();
  const client = Object.assign(base, { projectFolder: vi.fn(async () => ({ project: { id: 'p1', name: 'parts', root: '/models/parts', created: 1, opened: 1, missing: false }, path: '', folders: [], documents: [], truncated: false })),
    entryOf: (path: string) => (base.getSnapshot() as unknown as { entries: Record<string, unknown>[] }).entries.find(entry => entry.file === path) ?? null });
  const view = (file: string, extra: object = {}) => <CadViewer client={client as never} host={ports(client)} tabStore={createTabStore(memoryTabRecord())}
    live={createLiveRegistry()} file={file} library={library} onShow={() => {}} {...extra} />;
  const { rerender } = render(view('/models/parts/a.step'));
  await act(async () => client.publish([{ id: 'f1', file: '/models/parts/a.step', project: { id: 'p1', name: 'parts', root: '/models/parts' } }]));
  // The overlay FileViewer draws holds it: the search, handed what is on screen and the host's navigation.
  const search = () => [props().overlay].flat().flatMap(node => ((node as ReactElement)?.props as { children?: unknown })?.children ?? [])
    .flat().find(node => (node as ReactElement | null)?.props && 'search' in ((node as ReactElement).props as object)) as ReactElement<any> | undefined;
  expect(search()!.props).toMatchObject({ library, current: { id: 'f1', path: '/models/parts/a.step', project: { id: 'p1', name: 'parts' } } });
  expect(search()!.props.navigation).toBe(props().host.navigation);
  // ⌘K and the app menu's Search documents open it.
  expect(search()!.props.search.open).toBe(false);
  act(() => props().onSearch!());
  expect(search()!.props.search.open).toBe(true);
  // Over the home: the same search, nothing on screen.
  rerender(view(''));
  expect(search()!.props.current).toMatchObject({ id: null, path: null, project: null });
  // A host with no library: no search.
  rerender(view('/models/parts/a.step', { library: undefined }));
  expect([props().onSearch, search()]).toEqual([null, undefined]);
});

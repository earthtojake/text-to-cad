import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
// The built module: its Settings is the renderer kit's, whose JSX lives in .js files this runner does not compile.
import { ModelLibrary } from '../../dist/library/ModelLibrary.js';
import { activityLabel, ageLabel, lastActivity } from '../../dist/lib/age.js';
import { ControlUsageProvider } from '../../dist/usage/controls.js';
import { ViewerHostContext } from '../../dist/host/context.js';
import { FileViewer } from '../../dist/file-viewer/index.js';
import { viewerLinks } from '../../dist/file-viewer/navigation/links.js';
import { PANEL_PEEK_DELAY_MS, PANEL_PEEK_EXIT_FALLBACK_MS, PANEL_PEEK_LEAVE_MS } from '../../dist/file-viewer/panelPeek.js';
import { testHost } from '../../dist/host/testing/host.js';
import { ViewerMobileContext } from '../../dist/file-viewer/responsive.js';
import { below, filterModels, formatLabel, sortDocuments } from '../../dist/library/ModelLibrary.js';
import { libraryRow } from '@cad/core/client';
import type { LibraryFolder, LibraryModel, LibraryNavigation, LibraryProject, ModelLibrarySource } from './ModelLibrary.js';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const NOW = Date.UTC(2026, 8, 30, 12);
const model = (name: string, extra: Partial<LibraryModel> = {}): LibraryModel =>
  ({ path: `/work/parts/${name}`, name, folder: '/work/parts', opened: 1, updated: Date.now() / 1000 - 16 * 3600, created: null, pinned: false, missing: false, thumbnail: null, pictured: null, ...extra });

function library(models: LibraryModel[], extra: Partial<ModelLibrarySource> = {}): ModelLibrarySource {
  return {
    list: async () => models,
    change: vi.fn(async (action, item) => models.map(entry => entry.path === item.path ? { ...entry, pinned: action === 'pin' } : entry)
      .sort((a, b) => Number(b.pinned) - Number(a.pinned))),
    thumbnail: async () => null,
    open: vi.fn(async () => {}),
    ...extra,
  };
}

// A card's ⋯ menu, opened as a press opens it: once a render, as a second menu opened after the first in one jsdom render stays shut.
async function menu(name: string) {
  const trigger = screen.getByRole('button', { name: `Actions for ${name}` });
  await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  return screen.findByRole('menu');
}
const items = (open: HTMLElement) => within(open).getAllByRole('menuitem').map(item => item.textContent);

it('starts with its bar (the search at the right, no name of its own), its places at the left, and the place on screen under its title, with no wordmark or links (the app menu\'s)', async () => {
  render(<ModelLibrary library={library([])} onLayoutChange={() => {}} onSortChange={() => {}} />);
  await screen.findByText('Nothing here yet');
  // With no navbar over it, the page's own bar: the search, and no heading: the place's title says where the person is.
  const bar = document.querySelector('[data-library-bar]')!;
  expect(bar.querySelector('h1, h2')).toBeNull();
  expect([...bar.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label'))).toEqual(['Search models']);
  // The search keeps its placeholder; every control is the scale's control (28px), its icons 16px.
  expect(screen.getByRole('searchbox', { name: 'Search models' }).getAttribute('placeholder')).toBe('Search');
  expect(screen.getByRole('searchbox', { name: 'Search models' }).className).toContain('h-control');
  // The place on screen: its title, the page's one heading of the first level, in a row of its own. With nothing to
  // list there is no Sort or layout in it: nothing to order or lay out.
  const main = screen.getByRole('main', { name: 'CAD models' });
  const head = main.firstElementChild!;
  expect([head.hasAttribute('data-library-head'), head.querySelector('h1')?.textContent, screen.getAllByRole('heading', { level: 1 }).length]).toEqual([true, 'Recents', 1]);
  expect([main.querySelector('[data-library-toolbar]'), screen.queryByRole('group', { name: 'Layout' })]).toEqual([null, null]);
  // No count; the one picture is the welcome's C mark.
  expect(main.querySelector('[data-pill-count]')).toBeNull();
  expect([...main.querySelectorAll('img')].map(image => Boolean(image.closest('[data-library-empty]')))).toEqual([true]);
  // Its one navigation is its places; a host with no addresses has no link anywhere.
  expect(screen.getAllByRole('navigation').map(node => node.getAttribute('aria-label'))).toEqual(['Places']);
  expect(screen.queryByRole('link')).toBeNull();
  cleanup();
  // A place that lists something: in the title's own row, Sort and the grid/list segmented control at its right.
  render(<ModelLibrary library={library([model('a.step')])} onLayoutChange={() => {}} onSortChange={() => {}} />);
  await screen.findByRole('button', { name: 'Open a.step' });
  const toolbar = screen.getByRole('main').querySelector('[data-library-toolbar]')!;
  expect([toolbar.parentElement?.hasAttribute('data-library-head'), [...toolbar.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label'))])
    .toEqual([true, ['Sort by Last activity', 'Grid', 'List']]);
  // One row: the head holds the title and the toolbar, and nothing else but the title's own controls; no kind tabs.
  expect([toolbar.parentElement?.querySelector('h1')?.textContent, screen.queryByRole('group', { name: 'Show' }), document.querySelector('[data-library-kinds]')]).toEqual(['Recents', null, null]);
  // Grid and List are one segmented control: two control-tall toggles on one track.
  expect(screen.getByRole('group', { name: 'Layout' }).hasAttribute('data-segmented-control')).toBe(true);
  expect(['Grid', 'List'].map(name => screen.getByRole('button', { name }).className.includes('h-control'))).toEqual([true, true]);
});

it('ends its bar in Import where the host has a chooser -- a file, or a folder opened as a project -- counted, and none where it has not', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const pick = vi.fn(async () => {});
  const importFolder = vi.fn(async () => null);
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={library([], { pick, importFolder })} onLayoutChange={() => {}} /></ControlUsageProvider>);
  await screen.findByText('Nothing here yet');
  const row = document.querySelector('[data-library-bar]')!;
  // Last of the bar, after the search: the folder icon, "Import", 28px as its neighbours, neutral (never a filled primary).
  expect([...row.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label') ?? node.textContent)).toEqual(['Search models', 'Import']);
  const trigger = screen.getByRole('button', { name: 'Import', exact: true });
  expect([trigger.getAttribute('data-variant'), trigger.className.includes('h-control'), Boolean(trigger.querySelector('svg.lucide-folder-open'))]).toEqual(['outline', true, true]);
  await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  expect(items(await screen.findByRole('menu'))).toEqual(['File…', 'Folder…']);
  await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: 'File…' })); });
  expect(pick).toHaveBeenCalledTimes(1);
  // With nothing yet, the welcome's Import file and Import folder are the same choosers.
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Import file' })); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Import folder' })); });
  expect([pick.mock.calls.length, importFolder.mock.calls.length]).toEqual([2, 1]);
  view.unmount();
  expect(reports.flat()).toEqual([{ control: 'home_pick', count: 2, seconds: 0 }, { control: 'home_import_folder', count: 1, seconds: 0 }]);
});

// Where the system's chooser takes a file or a folder in one (a Mac's open panel), Import is one button that opens it, as
// VS Code's "Open…" is there; elsewhere it stays the menu of File… and Folder… (above).
it("is one Import button where one chooser takes either: a folder chosen is opened as a project, a file shown, each counted as File's and Folder's are", async () => {
  const press = async (button: HTMLElement) => { await act(async () => { fireEvent.click(button); }); };
  const reports: { control: string; count: number; seconds: number }[][] = [];
  let listed: LibraryProject[] = [];
  const gear = project('p2', 'gear', { root: '/w/gear' });
  const folders = hosted([gear], [file(gear, 'part_0.stl'), file(gear, 'STEP/gear.step')]);
  // What the one chooser answers in turn, as a host hands it on: a file (which the host has shown), a cancel, a folder
  // made a project, and a folder inside it.
  const answers = [{ file: '/w/loose.step' }, null, { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: true, folder: '/w/gear' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear/STEP' }];
  const importAny = vi.fn(async () => { const answer = answers.shift()!; if (answer && 'project' in answer) listed = [gear]; return answer; });
  const pick = vi.fn(async () => {}), importFolder = vi.fn(async () => null);
  const places: unknown[] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library([], { folder: folders.folder, projects: async () => listed, pick, importFolder, importAny })} onPlaceChange={next => places.push(next)} />
  </ControlUsageProvider>);
  await screen.findByText('Nothing here yet');
  // The bar's Import: the outline button, its folder icon and its word, with no chevron and no menu (its size, as drawn,
  // is the browser spec's).
  const bar = document.querySelector('[data-library-bar]')!;
  const button = within(bar as HTMLElement).getByRole('button', { name: 'Import', exact: true });
  expect([button.getAttribute('data-variant'), button.textContent, button.getAttribute('aria-haspopup'),
    [...button.querySelectorAll('svg')].map(svg => svg.getAttribute('class')?.match(/lucide-[\w-]+/)?.[0])]).toEqual(['outline', 'Import', null, ['lucide-folder-open']]);
  // The welcome's two ways in are that one button too.
  const welcome = document.querySelector<HTMLElement>('[data-library-empty]')!;
  expect([within(welcome).getAllByRole('button').map(node => node.textContent), screen.queryByRole('button', { name: 'Import file' }), screen.queryByRole('button', { name: 'Import folder' })])
    .toEqual([['Import'], null, null]);
  // A file chosen: the host shows it; the home goes nowhere and says nothing.
  await press(button);
  expect([importAny.mock.calls.length, screen.queryByRole('menu'), places, document.querySelector('[data-library-note]')]).toEqual([1, null, [], null]);
  // Cancelled: nothing.
  await press(within(welcome).getByRole('button', { name: 'Import' }));
  expect([importAny.mock.calls.length, places]).toEqual([2, []]);
  // A folder chosen: opened as a project, its page shown with a line saying what came of it, as Folder's is.
  await press(button);
  expect(await screen.findByText('gear is now a project. Nothing was written to the folder.')).toBeTruthy();
  expect(places).toEqual([{ view: 'project', project: 'p2' }]);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  // A folder inside a project: the project's page, at that folder.
  await press(within(document.querySelector('[data-library-bar]') as HTMLElement).getByRole('button', { name: 'Import', exact: true }));
  expect(await screen.findByText('STEP is inside gear, which is already a project.')).toBeTruthy();
  expect(places.at(-1)).toEqual({ view: 'project', project: 'p2', path: 'STEP' });
  // The sidebar's +, by Projects, stays the folder chooser; File… alone is never asked for.
  await press(screen.getByRole('button', { name: 'Open a folder as a project' }));
  expect([importAny.mock.calls.length, importFolder.mock.calls.length, pick.mock.calls.length]).toEqual([4, 1, 0]);
  view.unmount();
  // Counted by what was chosen, by File's and Folder's names (and the +, Folder's); a cancel counts nothing.
  expect(reported(reports)).toEqual({ home_pick: 1, home_import_folder: 3 });
});

it('opens and stars through the host, and with nothing yet says how a file gets here', async () => {
  render(<ModelLibrary library={library([])} onLayoutChange={() => {}} />);
  // The bar keeps its search with nothing to list yet, and the place no layout switch; the page welcomes: the
  // title, one line, and no Import where the host has no chooser.
  expect(await screen.findByRole('heading', { name: 'Nothing here yet' })).toBeTruthy();
  expect(screen.getByText('Import a file or a folder, or ask your agent to build a model.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Import file' })).toBeNull();
  expect(screen.getByRole('searchbox', { name: 'Search models' })).toBeTruthy();
  expect(screen.queryByRole('group', { name: 'Layout' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Import', exact: true })).toBeNull();
  cleanup();

  const inPlace = library([model('a.step'), model('b.stl', { missing: true })]);
  render(<ModelLibrary library={inPlace} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  expect((screen.getByRole('button', { name: 'Open b.stl' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Open b.stl' }).textContent).toContain('File unavailable');
  await act(async () => { fireEvent.click(open); });
  expect(inPlace.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'a.step' }));
  // Star is the card's menu's too, the host's `pin` (the word the wire shipped with). The list is by last activity, and
  // the host's own order (its starred first) where two tie.
  await act(async () => { fireEvent.click(within(await menu('b.stl')).getByRole('menuitem', { name: 'Star' })); });
  expect(inPlace.change).toHaveBeenLastCalledWith('pin', expect.objectContaining({ name: 'b.stl' }));
  const files = within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem');
  expect(files.map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'))).toEqual(['Open b.stl', 'Open a.step']);
  // Each card has its star by its ⋯ (Figma's), pressed and filled while it is starred; its menu offers Unstar.
  expect(within(files[0]).getByRole('button', { name: 'Unstar' }).getAttribute('aria-pressed')).toBe('true');
  expect(within(files[0]).getByRole('button', { name: 'Unstar' }).querySelector('svg.lucide-star')?.getAttribute('fill')).toBe('currentColor');
  expect(within(files[1]).getByRole('button', { name: 'Star' }).getAttribute('aria-pressed')).toBe('false');
  expect(within(files[1]).getByRole('button', { name: 'Star' }).querySelector('svg.lucide-star')?.getAttribute('fill')).toBe('none');
  await act(async () => { fireEvent.click(within(files[1]).getByRole('button', { name: 'Star' })); });
  expect(inPlace.change).toHaveBeenLastCalledWith('pin', expect.objectContaining({ name: 'a.step' }));
  cleanup();
  render(<ModelLibrary library={library([model('b.stl', { pinned: true })])} />);
  await screen.findByRole('button', { name: 'Open b.stl' });
  expect(items(await menu('b.stl'))).toEqual(['Open', 'Unstar']);
});

it('stands placeholders where the models will be while the list is read, and opens one at a time with a spinner over it', async () => {
  let listed!: (models: LibraryModel[]) => void;
  let opened!: () => void;
  const source = library([], {
    list: () => new Promise<readonly LibraryModel[]>(resolve => { listed = resolve; }),
    open: vi.fn(() => new Promise<void>(resolve => { opened = resolve; })),
  });
  render(<ModelLibrary library={source} layout="list" />);
  // Read, the list is a few placeholder rows, busy, with its status said aloud.
  let loading = screen.getByRole('list', { name: 'Files' });
  expect([loading.getAttribute('aria-busy'), loading.querySelectorAll('.cad-library-row').length]).toEqual(['true', 3]);
  expect(within(loading).getByRole('status').textContent).toBe('Loading files');
  // And placeholder rows where the projects will be.
  expect(within(screen.getByRole('navigation', { name: 'Places' })).getByRole('status').textContent).toBe('Loading projects');
  cleanup();
  render(<ModelLibrary library={source} />);
  loading = screen.getByRole('list', { name: 'Files' });
  expect([loading.getAttribute('aria-busy'), loading.querySelectorAll('.cad-library-card').length]).toEqual(['true', 4]);
  await act(async () => { listed([model('a.step'), model('b.step')]); });
  expect(screen.getByRole('list', { name: 'Files' }).getAttribute('aria-busy')).toBeNull();
  // The model being opened says so over its picture; a second press, on it or another, opens nothing.
  const a = screen.getByRole('button', { name: 'Open a.step' });
  await act(async () => { fireEvent.click(a); });
  expect(a.getAttribute('aria-busy')).toBe('true');
  expect(within(a).getByRole('status', { name: 'Opening a.step' })).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open b.step' })); fireEvent.click(a); });
  expect(source.open).toHaveBeenCalledTimes(1);
  await act(async () => { opened(); });
  expect(a.getAttribute('aria-busy')).toBeNull();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open b.step' })); });
  expect(source.open).toHaveBeenCalledTimes(2);
});

it('names a card by its file and how long ago it was last active, and switches between a grid and a list', async () => {
  const layouts: string[] = [];
  const { rerender } = render(<ModelLibrary library={library([model('bracket.step')])} layout="grid" onLayoutChange={layout => layouts.push(layout)} />);
  const card = await screen.findByRole('button', { name: 'Open bracket.step' });
  // Its format's badge on its picture, then its name over its age.
  expect(card.textContent).toMatch(/^STEPbracket\.stepEdited 16h ago$/);
  expect(card.textContent).not.toContain('/work');
  expect(screen.getByRole('button', { name: 'Grid' }).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  expect(layouts).toEqual(['list']);
  rerender(<ModelLibrary library={library([model('bracket.step')])} layout="list" onLayoutChange={layout => layouts.push(layout)} />);
  expect(screen.getByRole('button', { name: 'List' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('list', { name: 'Files' }).closest('.cad-library-table')).not.toBeNull();
  // A row has the card's one menu.
  expect(screen.getByRole('button', { name: 'Actions for bracket.step' })).toBeTruthy();
});

it('lists rows under a Name, Type, Last viewed and Last edited header: each its picture and name, its type, then both ages with no verb, its pin and ⋯ at its end', async () => {
  const hour = 3600, now = Date.now() / 1000;
  render(<ModelLibrary library={library([
    model('plate.step', { opened: now - 5 * hour, updated: now - 30 * hour }),
    model('arm.xbf', { opened: null, updated: now - 2 * hour }),
    model('ghost.step', { opened: null, updated: null }),
  ])} layout="list" onLayoutChange={() => {}} />);
  await screen.findByRole('button', { name: 'Open plate.step' });
  const list = screen.getByRole('list', { name: 'Files' });
  // The header row is the columns' labels, for the eye: each row names itself.
  const header = list.previousElementSibling!;
  expect([header.getAttribute('aria-hidden'), [...header.children].map(cell => cell.textContent)]).toEqual(['true', ['Name', 'Type', 'Last viewed', 'Last edited']]);
  const cells = (name: string) => {
    const row = screen.getByRole('button', { name: `Open ${name}` });
    return [Boolean(row.querySelector('[data-library-name] > [data-library-picture]')), row.querySelector('[data-library-label]')?.textContent,
      ...[...row.querySelectorAll('[data-column]')].map(cell => [cell.getAttribute('data-column'), cell.textContent])];
  };
  expect(cells('plate.step')).toEqual([true, 'plate.step', ['type', 'STEP'], ['viewed', '5h ago'], ['edited', '1d ago']]);
  // An xbf is the engine's own document saved as a file: a model, XBF where its parts are not known. A file no page has
  // opened has a dash for Last viewed, and a time that is not known is a dash too.
  expect(cells('arm.xbf')).toEqual([true, 'arm.xbf', ['type', 'XBF'], ['viewed', '—'], ['edited', '2h ago']]);
  expect(cells('ghost.step')).toEqual([true, 'ghost.step', ['type', 'STEP'], ['viewed', '—'], ['edited', '—']]);
  // No Where, Size, Updated or Created column anywhere.
  expect([...document.querySelectorAll('[data-column]')].map(cell => cell.getAttribute('data-column'))).not.toEqual(expect.arrayContaining(['where', 'size', 'created', 'kind']));
  // A row's picture has no badge: its Type says it. Its pin and ⋯ follow its button, at its end.
  expect(list.querySelector('[data-library-format]')).toBeNull();
  const row = screen.getByRole('button', { name: 'Open plate.step' }).closest('li')!;
  expect(within(row).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Open plate.step', 'Star', 'Actions for plate.step']);
});

it('gives each card one menu: Open, Copy path, Copy link and Reveal where the host can, then Star, and nothing that forgets a file', async () => {
  const copied: string[] = [], revealed: string[] = [], linked: unknown[] = [];
  const fileActions = { platform: 'darwin' as const, perform: { 'copy-path': ({ path }: { path: string }) => { copied.push(path); },
    'copy-link': (entry: unknown) => { linked.push(entry); }, reveal: ({ path }: { path: string }) => { revealed.push(path); } } };
  const source = library([model('bracket.step', { id: 'id-bracket' })]);
  const shown = async () => {
    cleanup();
    render(<ModelLibrary library={source} fileActions={fileActions} />);
    await screen.findByRole('button', { name: 'Open bracket.step' });
    return menu('bracket.step');
  };
  let open = await shown();
  // No Remove from Recents, as Figma's and Drive's file browsers have none: no rule, nothing that forgets the file.
  expect([items(open), open.querySelector('[role=separator]'), document.body.textContent]).toEqual([['Open', 'Copy path', 'Copy link', 'Reveal in Finder', 'Star'], null, expect.not.stringMatching(/remove|delete/i)]);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Copy path' })); });
  expect(copied).toEqual(['/work/parts/bracket.step']);
  open = await shown();
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Copy link' })); });
  expect(linked).toEqual([expect.objectContaining({ path: '/work/parts/bracket.step', id: 'id-bracket', kind: 'file' })]);
  open = await shown();
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Reveal in Finder' })); });
  expect(revealed).toEqual(['/work/parts/bracket.step']);
  open = await shown();
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open' })); });
  expect(source.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'bracket.step' }));
  cleanup();
  // A host that can do nothing with a file on disk offers neither.
  render(<ModelLibrary library={library([model('bracket.step')])} />);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  expect(items(await menu('bracket.step'))).toEqual(['Open', 'Star']);
});

it('gives a card no glyph, and has no kind tabs: every document of a place is listed, whatever its kind', async () => {
  const source = library([model('bracket.step'), model('arm.xbf'), model('plate.dxf'),
    model('blinky.kicad_pcb'), model('arm.stl')]);
  const names = () => within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem').map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'));
  render(<ModelLibrary library={source} onSortChange={() => {}} />);
  const arm = await screen.findByRole('button', { name: 'Open arm.xbf' });
  // The picture and its badge say what a card is: no glyph beside its name.
  const caption = (card: HTMLElement) => card.querySelector('[data-library-label]')!.parentElement!;
  expect([caption(arm).querySelector('svg'), caption(screen.getByRole('button', { name: 'Open bracket.step' })).querySelector('svg')]).toEqual([null, null]);
  // Nothing narrows the place by kind: no group of tabs, no "3D models" or "All" button, five cards of five kinds.
  expect([screen.queryByRole('group', { name: 'Show' }), document.querySelector('[data-library-kinds]'), ...['All', '3D models', 'Drawings', 'Boards', 'Robots'].map(name => screen.queryByRole('button', { name }))])
    .toEqual([null, null, null, null, null, null, null]);
  expect(names().sort()).toEqual(['Open arm.stl', 'Open arm.xbf', 'Open blinky.kicad_pcb', 'Open bracket.step', 'Open plate.dxf']);
});

it('has no kind tabs in Recents, Starred, a project\'s page or a search, nor any kind in the address', async () => {
  const p1 = project('p1', 'tag');
  const mixed = [model('a.step', { pinned: true }), model('b.dxf', { pinned: true }), model('c.urdf', { pinned: true })];
  const source = library(mixed, hosted([p1], [file(p1, 'tag.step'), file(p1, 'tag.dxf'), file(p1, 'tag.urdf')]));
  const none = () => [document.querySelector('[data-library-kinds]'), screen.queryByRole('group', { name: 'Show' }), screen.queryByRole('button', { name: 'Robots' })];
  const view = render(<ModelLibrary library={source} place={{ view: 'recents' }} />);
  await screen.findByRole('button', { name: 'Open a.step' });
  expect(none()).toEqual([null, null, null]);
  view.rerender(<ModelLibrary library={source} place={{ view: 'pinned' }} />);
  await screen.findByRole('button', { name: 'Open c.urdf' });
  expect(none()).toEqual([null, null, null]);
  view.rerender(<ModelLibrary library={source} place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open tag.urdf' });
  expect(none()).toEqual([null, null, null]);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'tag' } });
  await screen.findByRole('button', { name: 'Open tag.dxf' });
  expect(none()).toEqual([null, null, null]);
});

it('takes an .xbf the server lists (kind model, record file) as a model: a Part or an Assembly, by its parts', async () => {
  // As the server lists them: a document's kind, and its record's (`libraryRow` hands the library the record's as `kind`).
  const listed = (name: string, extra: Record<string, unknown>) => libraryRow({ ...model(name), ...extra }) as LibraryModel;
  const saved = listed('rig.xbf', { id: 'id-rig', kind: 'model', record: 'file', parts: 3 });
  const single = listed('pin.xbf', { id: 'id-pin', kind: 'model', record: 'file', parts: 1 });
  const step = listed('rig.step', { kind: 'step', record: 'file', parts: 3 });
  expect([saved, step].map(item => item.documentKind)).toEqual(['model', 'step']);
  const labels = { xbf: 'XBF', part: 'Part', assembly: 'Assembly' };
  expect([saved, single, step].map(item => formatLabel(item, labels))).toEqual(['Assembly', 'Part', 'STEP']);
});


it('says how long ago with no verb, in the largest unit that is at least one, then the short date', () => {
  const ago = (seconds: number) => ageLabel(NOW / 1000 - seconds, NOW);
  expect([ago(20), ago(5 * 60), ago(2 * 3600), ago(3 * 86400)]).toEqual(['now', '5m ago', '2h ago', '3d ago']);
  expect(ago(40 * 86400)).toBe(new Date(NOW - 40 * 86400_000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }));
  expect(ageLabel(null, NOW)).toBe('');
});

it('dates a row by its last activity, the later of when it was opened and updated', () => {
  expect(lastActivity({ opened: 10, updated: 20 })).toBe(20);
  expect(lastActivity({ opened: 30, updated: 20 })).toBe(30);
  expect(lastActivity({ opened: null, updated: 20 })).toBe(20);
  expect(lastActivity({ opened: null, updated: null })).toBeNull();
});

it("says a tile's last activity with its verb: Edited for a change after the last opening, Viewed for an opening after the last change", () => {
  const at = (seconds: number) => NOW / 1000 - seconds;
  expect(activityLabel({ opened: at(16 * 60), updated: at(2 * 60) }, NOW)).toBe('Edited 2m ago');
  expect(activityLabel({ opened: at(16 * 60), updated: at(3 * 86400) }, NOW)).toBe('Viewed 16m ago');
  expect(activityLabel({ opened: null, updated: at(20) }, NOW)).toBe('Edited now');
  expect(activityLabel({ opened: at(20), updated: null }, NOW)).toBe('Viewed now');
  // The page opened what was just built: one time, an edit.
  expect(activityLabel({ opened: at(60), updated: at(60) }, NOW)).toBe('Edited 1m ago');
  expect(activityLabel({ opened: null, updated: null }, NOW)).toBe('');
});

it('shows a card by its last change or its last opening, whichever came last, each with its verb', async () => {
  const hour = 3600, now = Date.now() / 1000;
  render(<ModelLibrary library={library([
    model('arm.xbf', { opened: null, updated: now - 2 * hour }),
    model('plate.step', { opened: now - 5 * hour, updated: now - 30 * hour }),
  ])} />);
  expect((await screen.findByRole('button', { name: 'Open arm.xbf' })).textContent).toBe('XBFarm.xbfEdited 2h ago');
  expect(screen.getByRole('button', { name: 'Open plate.step' }).textContent).toBe('STEPplate.stepViewed 5h ago');
});

it('shows why an open failed where the library shows it', async () => {
  const failing = library([model('a.step')], { open: async () => { throw new Error('That model is gone.'); } });
  render(<ModelLibrary library={failing} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  await act(async () => { fireEvent.click(open); });
  expect((await screen.findByRole('alert')).textContent).toBe('That model is gone.');
});



it('reads its list again every couple of seconds while the home is up, keeping the cards when nothing changed', async () => {
  vi.useFakeTimers();
  try {
    const list = vi.fn(async () => [model('plate.step')]);
    render(<ModelLibrary library={library([], { list })} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(list).toHaveBeenCalledTimes(1);
    const card = screen.getByRole('button', { name: 'Open plate.step' });
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect(list).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Open plate.step' })).toBe(card);
  } finally { vi.useRealTimers(); }
});

it("counts what a person does on the home by name: a search begun, a card opened", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const source = library([model('juno.xbf', { updated: 10 }), model('wheel.xbf', { updated: 5 }), model('bracket.dxf')]);
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open juno.xbf' });
  const search = screen.getByRole('searchbox', { name: 'Search models' });
  for (const value of ['b', 'br', '']) fireEvent.change(search, { target: { value } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open bracket.dxf' })); });
  view.unmount();
  expect(reported(reports)).toEqual({ home_search: 1, home_open: 1 });
});

it('counts the star, from its button or the menu, by the names it shipped with, the grid/list switch, and Copy path, Copy link and Reveal', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const fileActions = { platform: 'darwin' as const, perform: { 'copy-path': () => {}, 'copy-link': () => {}, reveal: () => {} } };
  const source = library([model('bracket.step'), model('plate.step', { pinned: true })]);
  // A host that keeps the layout chosen, as the tab does.
  function Kept() {
    const [layout, setLayout] = useState<'grid' | 'list'>('grid');
    return <ModelLibrary library={source} fileActions={fileActions} layout={layout} onLayoutChange={setLayout} />;
  }
  const home = () => render(<ControlUsageProvider report={counts => reports.push(counts)}><Kept /></ControlUsageProvider>);
  let view = home();
  await screen.findByRole('button', { name: 'Open bracket.step' });
  const bracket = screen.getByRole('button', { name: 'Open bracket.step' }).closest('li')!;
  await act(async () => { fireEvent.click(within(bracket).getByRole('button', { name: 'Star' })); });
  // The layout chosen, then the one already on (no use), then the other.
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  fireEvent.click(screen.getByRole('button', { name: 'Grid' }));
  await act(async () => { fireEvent.click(within(await menu('bracket.step')).getByRole('menuitem', { name: 'Copy path' })); });
  view.unmount();
  cleanup();
  // A menu each render (jsdom): Reveal, then Unstar from the menu.
  for (const item of ['Copy link', 'Reveal in Finder', 'Unstar']) {
    view = home();
    await screen.findByRole('button', { name: 'Open plate.step' });
    await act(async () => { fireEvent.click(within(await menu('plate.step')).getByRole('menuitem', { name: item })); });
    view.unmount();
    cleanup();
  }
  const said = Object.fromEntries(reports.flat().map(({ control, count }) => [control, count]));
  expect(said).toEqual({ home_pin: 1, home_layout_list: 1, home_layout_grid: 1, home_copy_path: 1, home_copy_link: 1, home_reveal: 1, home_unpin: 1 });
});

// Every picture is the light viewport's, on the model area's light gradient in both themes: none (a board's
// or a drawing's included) is turned for the dark theme.
it("shows every card's light picture in both themes, never turned, and badges it with its format", async () => {
  const thumbnail = vi.fn(async (item: LibraryModel) => `data:${item.name}:${item.thumbnail}`);
  const source = library([model('video.kicad_pcb', { thumbnail: 'light.png', pictured: Date.now() / 1000 }),
    model('plate.dxf', { thumbnail: 'plate.png', pictured: Date.now() / 1000 }), model('arm.xbf')], { thumbnail });
  const home = (colorScheme: 'light' | 'dark') => <ViewerHostContext.Provider value={{ environment: { colorScheme } } as any}><ModelLibrary library={source} /></ViewerHostContext.Provider>;
  const view = render(home('dark'));
  const picture = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).closest('.cad-library-card')!.querySelector('[data-library-picture]')!;
  await waitFor(() => expect(picture('video.kicad_pcb').querySelector('img')?.getAttribute('src')).toBe('data:video.kicad_pcb:light.png'));
  await waitFor(() => expect(picture('plate.dxf').querySelector('img')?.getAttribute('src')).toBe('data:plate.dxf:plate.png'));
  view.rerender(home('light'));
  expect(picture('video.kicad_pcb').querySelector('img')?.getAttribute('src')).toBe('data:video.kicad_pcb:light.png');
  expect(thumbnail.mock.calls.every(call => call.length === 1)).toBe(true);
  // A card whose row names no picture is its format's tile: nothing is asked for it, and nothing draws one.
  expect([...new Set(thumbnail.mock.calls.map(([item]) => item.name))].sort()).toEqual(['plate.dxf', 'video.kicad_pcb']);
  expect(picture('arm.xbf').querySelector('img')).toBeNull();
  expect(['video.kicad_pcb', 'plate.dxf'].map(name => [picture(name).hasAttribute('data-drawing'), picture(name).hasAttribute('data-thumbnail-variant')])).toEqual([[false, false], [false, false]]);
  expect(['video.kicad_pcb', 'plate.dxf', 'arm.xbf'].map(name => picture(name).querySelector('[data-library-format]')?.textContent)).toEqual(['KiCad PCB', 'DXF', 'XBF']);
});

it('calls a model a Part or an Assembly by its parts, XBF where they are not known, and every other file by its format', async () => {
  const documents = [model('hinge.xbf', { parts: 1 }), model('rig.xbf', { parts: 3 }), model('unread.xbf', { parts: null }), model('empty.xbf', { parts: 0 }),
    model('pair.step', { parts: 2 }), model('plate.stl', { parts: 1 })];
  const names = documents.map(item => item.name);
  const said = ['Part', 'Assembly', 'XBF', 'XBF', 'STEP', 'STL'];
  // On a card, its badge.
  render(<ModelLibrary library={library(documents)} />);
  await screen.findByRole('button', { name: 'Open hinge.xbf' });
  const badge = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).closest('.cad-library-card')!.querySelector('[data-library-format]')?.textContent;
  expect(names.map(badge)).toEqual(said);
  cleanup();
  // In the list, its Type.
  render(<ModelLibrary library={library(documents)} layout="list" onLayoutChange={() => {}} />);
  await screen.findByRole('button', { name: 'Open hinge.xbf' });
  expect(names.map(name => screen.getByRole('button', { name: `Open ${name}` }).querySelector('[data-column="type"]')?.textContent)).toEqual(said);
  expect(documents.map(item => formatLabel(item, { xbf: 'XBF', part: 'Part', assembly: 'Assembly' }))).toEqual(said);
});

// A card's line is the age alone, a file's as a model's: both times are the list's columns.
it("says a card's age alone, the list saying both times", async () => {
  const now = Date.now() / 1000;
  render(<ModelLibrary library={library([model('plate.step', { opened: now - 5 * 3600, updated: now - 30 * 3600 }),
    model('tiny.stl', { opened: now - 5 * 3600, updated: now - 30 * 3600 }), model('arm.xbf', { opened: null, updated: now - 2 * 3600 })])} />);
  const status = async (name: string) => (await screen.findByRole('button', { name: `Open ${name}` })).querySelector('[data-library-status]')!.textContent;
  expect([await status('plate.step'), await status('tiny.stl'), await status('arm.xbf')]).toEqual(['Viewed 5h ago', 'Viewed 5h ago', 'Edited 2h ago']);
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Recents');
});

// A project as the host lists it.
const project = (id: string, name: string, extra: Partial<LibraryProject> = {}): LibraryProject =>
  ({ id, name, root: `/Users/sam/cad/${name}`, opened: 1, missing: false, ...extra });
// A file of a project, by its path below the project's root, as its folder lists it: one no page has opened.
const file = (of: LibraryProject, below: string, extra: Partial<LibraryModel> = {}) => model(below.split('/').pop()!, {
  path: `${of.root}/${below}`, id: `file-${of.id}-${below}`, folder: `${of.root}/${below}`.replace(/\/[^/]*$/, ''), project: of.id,
  opened: null, created: null, ...extra });
// A host's projects, and each one's folder answered from the files below it as a CAD host answers it
// (`GET /api/v1/projects/<id>`): its subfolders that hold a file, then its files; with words, every file below that
// holds them all, and no folders. A folder that holds nothing is not there.
function hosted(projects: LibraryProject[], files: LibraryModel[] = [], extra: Partial<LibraryFolder> = {}) {
  const folder = vi.fn(async (id: string, { path = '', q = '' }: { path?: string; q?: string }): Promise<LibraryFolder> => {
    const found = projects.find(entry => entry.id === id);
    if (!found) throw new Error(`no project ${id}`);
    const base = path ? `${found.root}/${path}` : found.root;
    const below = files.filter(item => item.project === id && item.path.startsWith(`${base}/`)).map(item => ({ item, rest: item.path.slice(base.length + 1) }));
    if (path && !below.length) throw new Error(`no folder ${path} in ${found.name}`);
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length) return { project: found, path, folders: [], truncated: false, ...extra,
      documents: below.filter(({ rest }) => words.every(word => rest.toLowerCase().includes(word))).map(({ item }) => item) };
    const names = [...new Set(below.filter(({ rest }) => rest.includes('/')).map(({ rest }) => rest.split('/')[0]))];
    return { project: found, path, folders: names.map(name => ({ name, path: path ? `${path}/${name}` : name })), truncated: false, ...extra,
      documents: below.filter(({ rest }) => !rest.includes('/')).map(({ item }) => item) };
  });
  return { projects: async () => projects, folder };
}
// The place's documents, by their press targets' names (a button's or a link's), in order.
const opens = () => [...document.querySelectorAll('.cad-library-open[aria-label]')].map(node => node.getAttribute('aria-label'));
const place = (key: string) => document.querySelector<HTMLElement>(`[data-place="${key}"]`)!;
const reported = (reports: { control: string; count: number }[][]) => reports.flat().reduce<Record<string, number>>((sums, { control, count }) =>
  ({ ...sums, [control]: (sums[control] ?? 0) + count }), {});

it('lists its places in a sidebar with no counts: Recents, Starred, then each project, the one on screen marked', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const tag = project('p1', 'heart-tag'), lamp = project('p2', 'lamp', { missing: true });
  const recents = [model('opened.stl', { path: '/Users/sam/cad/heart-tag/STL/part_0.stl', project: 'p1', pinned: true }), model('loose.step'), model('other.stl', { pinned: true })];
  const places: unknown[] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library(recents, hosted([tag, lamp], [file(tag, 'top.step'), file(tag, 'STL/part_0.stl'), file(tag, 'STL/part_1.stl')]))}
      onPlaceChange={next => places.push(next)} />
  </ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open loose.step' });
  const sidebar = screen.getByRole('navigation', { name: 'Places' });
  // The panel's surface (the viewer's own, docked) and its rows: a glyph and the name, and no count, as Figma's and
  // Drive's sidebars have none; no place of the documents in no project (they are Recents' and the search's).
  expect([sidebar.closest('aside')!.getAttribute('data-panel-surface'), sidebar.closest('aside')!.getAttribute('aria-label')]).toEqual(['docked', 'Sidebar']);
  const rows = [...sidebar.querySelectorAll<HTMLElement>('[data-place]')];
  expect(rows.map(row => [row.getAttribute('data-place'), row.textContent, row.hasAttribute('data-tree-row'), row.querySelectorAll('svg').length]))
    .toEqual([['recents', 'Recents', true, 1], ['pinned', 'Starred', true, 1], ['project:p1', 'heart-tag', true, 1], ['project:p2', 'lamp', true, 1]]);
  // Starred's glyph is lucide's star, drawn as an outline as every place's is.
  expect([place('pinned').querySelector('svg.lucide-star')?.getAttribute('fill'), Boolean(place('pinned').querySelector('svg.lucide-pin'))]).toEqual(['none', false]);
  expect(within(sidebar).getByRole('heading', { level: 2 }).textContent).toBe('Projects');
  // A host with no addresses: every row a button. The one on screen is marked and said; a project whose folder is gone is muted.
  expect(rows.map(row => [row.tagName, row.getAttribute('aria-current')])).toEqual([['BUTTON', 'page'], ['BUTTON', null], ['BUTTON', null], ['BUTTON', null]]);
  expect([place('project:p2').hasAttribute('data-missing'), place('project:p2').className.includes('text-muted-foreground')]).toEqual([true, true]);
  // Recents: every document opened lately, across projects.
  expect(opens()).toEqual(['Open opened.stl', 'Open loose.step', 'Open other.stl']);
  // A press shows the place: its name is the heading, its row the marked one, and the host hears of it.
  await act(async () => { fireEvent.click(place('pinned')); });
  expect([screen.getByRole('main').querySelector('h1')?.textContent, place('pinned').getAttribute('aria-current'), place('recents').getAttribute('aria-current')])
    .toEqual(['Starred', 'page', null]);
  expect(opens()).toEqual(['Open opened.stl', 'Open other.stl']);
  await act(async () => { fireEvent.click(place('project:p1')); });
  await waitFor(() => expect(opens()).toEqual(['Open STL', 'Open top.step']));
  await act(async () => { fireEvent.click(place('project:p1')); });  // the place on screen: no move
  await act(async () => { fireEvent.click(place('recents')); });
  expect(places).toEqual([{ view: 'pinned' }, { view: 'project', project: 'p1' }, { view: 'recents' }]);
  // Up and Down move between the rows, Home and End to the first and the last.
  place('recents').focus();
  fireEvent.keyDown(place('recents'), { key: 'ArrowDown' });
  expect(document.activeElement).toBe(place('pinned'));
  fireEvent.keyDown(place('pinned'), { key: 'End' });
  expect(document.activeElement).toBe(place('project:p2'));
  fireEvent.keyDown(place('project:p2'), { key: 'ArrowUp' });
  expect(document.activeElement).toBe(place('project:p1'));
  view.unmount();
  expect(reported(reports)).toEqual({ home_place_pinned: 1, home_place_project: 1, home_place_recents: 1 });
});

it("shows the place the host names, and tells the host its name as the person reads it", async () => {
  const names: string[] = [];
  const tag = project('p1', 'heart-tag');
  const source = library([model('loose.step')], hosted([tag], [file(tag, 'part_0.stl'), file(tag, 'housing/v3/lid.step')]));
  const home = (at: Parameters<typeof ModelLibrary>[0]['place']) => <ModelLibrary library={source} place={at} onPlaceShown={name => names.push(name)} />;
  const view = render(home({ view: 'project', project: 'p1' }));
  // Until the projects are read, the project's page waits where its documents will be.
  expect(screen.getByRole('list', { name: 'Files' }).getAttribute('aria-busy')).toBe('true');
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([place('project:p1').getAttribute('aria-current'), screen.getByRole('main').querySelector('h1')?.textContent]).toEqual(['page', 'heart-tag']);
  view.rerender(home({ view: 'pinned' }));
  // Nothing starred: its page says how a file gets there.
  expect(place('pinned').textContent).toBe('Starred');
  expect(screen.getByText('Nothing starred yet. Star a file to keep it here.')).toBeTruthy();
  // A folder of a project is named by its own name.
  view.rerender(home({ view: 'project', project: 'p1', path: 'housing/v3' }));
  await screen.findByRole('button', { name: 'Open lid.step' });
  expect(names).toEqual(['Project', 'heart-tag', 'Starred', 'v3']);
});

it("a project's page lists its folders first, then its files, and its heading leads back up", async () => {
  const tag = project('p1', 'heart-tag');
  const files = [file(tag, 'top.step'), file(tag, 'housing/v3/housing.xbf', { opened: 5, parts: 3 }), file(tag, 'housing/v3/lid.step'),
    file(tag, 'housing/v3/drawings/plan.dxf'), file(tag, 'dxf/plate.dxf')];
  const places: unknown[] = [];
  const page = (path?: string, layout: 'grid' | 'list' = 'grid') => <ModelLibrary library={library([], hosted([tag], files))} layout={layout}
    place={{ view: 'project', project: 'p1', ...(path ? { path } : {}) }} onPlaceChange={next => places.push(next)} />;
  const view = render(page());
  await screen.findByRole('button', { name: 'Open top.step' });
  const heading = () => screen.getByRole('main').firstElementChild!;
  // Its name and its folder glyph, and no folder path beside it (its ⋯'s Copy path says where it is).
  expect([heading().querySelector('h1')?.textContent, heading().textContent, Boolean(heading().querySelector('svg.lucide-folder'))])
    .toEqual(['heart-tag', 'heart-tag', true]);
  // Its folders first, in the host's order, then the files directly in it: nothing below is flattened here.
  expect(opens()).toEqual(['Open housing', 'Open dxf', 'Open top.step']);
  // A folder is its glyph and its name in a list of its own, with no picture, count, pin or menu: a way into it.
  const folders = screen.getByRole('list', { name: 'Folders' });
  const housing = within(folders).getByRole('button', { name: 'Open housing' });
  expect([housing.textContent, Boolean(housing.querySelector('svg.lucide-folder')), housing.querySelector('[data-library-picture]'),
    within(housing.closest('li')!).getAllByRole('button').length]).toEqual(['housing', true, null, 1]);
  await act(async () => { fireEvent.click(housing); });
  expect(places).toEqual([{ view: 'project', project: 'p1', path: 'housing' }]);
  // Two levels down: the path in the heading, each part but the last a way back up.
  view.rerender(page('housing/v3'));
  await screen.findByRole('button', { name: 'Open lid.step' });
  expect(opens()).toEqual(['Open drawings', 'Open housing.xbf', 'Open lid.step']);
  const crumbs = [...heading().querySelectorAll('[data-library-crumb]')].map(crumb => crumb.textContent);
  expect([crumbs, heading().querySelector('h1')?.textContent]).toEqual([['heart-tag', 'housing'], 'v3']);
  places.length = 0;
  for (const crumb of ['heart-tag', 'housing']) await act(async () => { fireEvent.click(within(heading() as HTMLElement).getByRole('button', { name: crumb })); });
  expect(places).toEqual([{ view: 'project', project: 'p1' }, { view: 'project', project: 'p1', path: 'housing' }]);
  // A file of the folder has its star and its menu.
  expect(within(screen.getByRole('button', { name: 'Open lid.step' }).closest('li')!).getByRole('button', { name: 'Star' })).toBeTruthy();
  expect(items(await menu('lid.step'))).toEqual(['Open', 'Star']);
  // In a list a folder is a row, its glyph where a picture is and its Type "Folder" and a dash in each time, first.
  view.rerender(page('housing/v3', 'list'));
  const row = within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem')[0];
  expect([row.textContent, [...row.querySelectorAll('[data-column]')].map(cell => cell.textContent)]).toEqual(['drawingsFolder——', ['Folder', '—', '—']]);
});

// A project's top page leads with Recent: the library's rows of the project below its top folder, newest first, as
// Drive's Home leads with Suggested files and Box's All Files with its Recents; then the listing under All files.
it("a project's top page leads with its files opened or built below the top, newest first, then the listing under All files; never below the top, never in a search", async () => {
  const tag = project('p1', 'heart-tag'), gear = project('p2', 'gear');
  const now = Date.now() / 1000;
  // Opened lately and never changed since, so the order is by the opening alone and not by when the fixtures were built.
  const opened = (of: LibraryProject, below: string, hours: number) => ({ ...file(of, below), opened: now - hours * 3600, updated: null });
  const rows = [opened(tag, 'housing/v3/housing.xbf', 3), opened(tag, 'top.step', 1), opened(tag, 'exports/housing.step', 7), opened(tag, 'dxf/plate.dxf', 2),
    ...['a', 'b', 'c'].map((name, index) => opened(tag, `dxf/old/${name}.dxf`, 20 + index)), opened(gear, 'sub/gear.step', 0.5), model('loose.step', { opened: now })];
  const host = hosted([tag, gear], [file(tag, 'top.step'), file(tag, 'top.dxf'), file(tag, 'housing/v3/housing.xbf'), file(tag, 'exports/housing.step'), file(tag, 'dxf/plate.dxf')]);
  const page = (path = '', layout: 'grid' | 'list' = 'list') => <ModelLibrary library={library(rows, host)} layout={layout} place={{ view: 'project', project: 'p1', ...(path ? { path } : {}) }} />;
  const view = render(page());
  const recent = await screen.findByRole('list', { name: 'Recent' });
  // Two labels, Recent over its rows and All files over the listing, the page's headings under its title.
  const main = screen.getByRole('main');
  expect([...main.querySelectorAll('h1, h2')].map(heading => [heading.tagName, heading.textContent])).toEqual([['H1', 'heart-tag'], ['H2', 'Recent'], ['H2', 'All files']]);
  // The project's files below its top, by last activity, newest first; at most five rows in the list; none of its top
  // folder (they are the listing's), none of another project and none of no project.
  const named = (list: HTMLElement) => within(list).getAllByRole('listitem').map(item => [item.querySelector('[data-library-label]')?.textContent]);
  expect(named(recent)).toEqual([['plate.dxf'], ['housing.xbf'], ['housing.step'], ['a.dxf'], ['b.dxf']]);
  // Under a header of its own, the listing's columns: no Where.
  expect([...recent.previousElementSibling!.querySelectorAll(':scope > span')].map(cell => cell.textContent)).toEqual(['Name', 'Type', 'Last viewed', 'Last edited']);
  expect(within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem').map(item => item.querySelector('[data-library-label]')?.textContent))
    .toEqual(['housing', 'exports', 'dxf', 'top.step', 'top.dxf']);
  // Read from the library alone: the host was asked for the folder on screen and nothing else.
  expect(host.folder.mock.calls.map(([, options]) => options)).toEqual(host.folder.mock.calls.map(() => ({ path: '' })));
  // A search replaces it: the search's results, with no Recent and no labels.
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'hous' } });
  await waitFor(() => expect(host.folder).toHaveBeenLastCalledWith('p1', { path: '', q: 'hous' }));
  await waitFor(() => expect(opens()).toEqual(['Open housing.xbf', 'Open housing.step']));
  expect([screen.queryByRole('list', { name: 'Recent' }), main.querySelectorAll('h2').length]).toEqual([null, 0]);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: '' } });
  await screen.findByRole('list', { name: 'Recent' });
  // In the grid it is one row of the cards' grid, its cards the listing's.
  view.rerender(page('', 'grid'));
  expect(screen.getByRole('list', { name: 'Recent' }).querySelector('.cad-library-card [data-library-status]')?.textContent).toBe('Viewed 2h ago');
  // Below the top, the folder's page as it is: no Recent, no labels.
  view.rerender(page('housing'));
  await screen.findByRole('button', { name: 'Open v3' });
  expect([screen.queryByRole('list', { name: 'Recent' }), screen.getByRole('main').querySelectorAll('h2').length]).toEqual([null, 0]);
  cleanup();
  // A project with nothing opened below its top: its page as it is.
  render(<ModelLibrary library={library([opened(tag, 'top.step', 1)], hosted([tag], [file(tag, 'top.step'), file(tag, 'dxf/plate.dxf')]))} layout="list" place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open top.step' });
  expect([screen.queryByRole('list', { name: 'Recent' }), screen.getByRole('main').querySelectorAll('h2').length]).toEqual([null, 0]);
});

// A folder's page lists every file in it. A file the viewer does not open (`documentKind: null`, as a CAD host's row of it
// says) comes after the documents: in the grid a tile of the folders' family, in the list a row; and a press on it opens
// it, as a press on a document does: in an app of the computer's, there being no page for it.
it("lists every file of a folder, the documents first; a press on one that is no document opens it with the default handler, else the host's first app, and says so where nothing opens it", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  // A submenu's list scrolls in the chrome's scroll region, which measures itself.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  const tag = project('p1', 'heart-tag');
  const other = (below: string) => file(tag, below, { documentKind: null, thumbnail: null });
  const files = [file(tag, 'arm.xbf', { documentKind: 'model' }), other('datasheet.pdf'), other('build.py'), other('Makefile'), other('run.sh'), other('locked.pdf'), file(tag, 'lid.step', { documentKind: 'step' })];
  const asked: string[] = [], opened: unknown[] = [], done: string[] = [];
  // Open in's answer for each, as a CAD host gives it: one target, the file; `default` there only as false.
  const answers: Record<string, object> = {
    'datasheet.pdf': { target: 'source', kind: 'pdf', name: 'datasheet.pdf', present: true, apps: [{ id: 'preview', name: 'Preview' }] },
    'build.py': { target: 'source', kind: 'code', name: 'build.py', present: true, apps: [{ id: 'vscode', name: 'Visual Studio Code' }, { id: 'cursor', name: 'Cursor' }], default: false },
    Makefile: { target: 'source', kind: 'file', name: 'Makefile', present: true, apps: [] },
    'run.sh': { target: 'source', kind: 'file', name: 'run.sh', present: true, apps: [], default: false },
    'locked.pdf': { target: 'source', kind: 'pdf', name: 'locked.pdf', present: true, apps: [] },
  };
  const fileActions = { platform: 'darwin' as const,
    perform: { 'copy-path': ({ path }: { path: string }) => { done.push(`copy ${path}`); }, reveal: ({ path }: { path: string }) => { done.push(`reveal ${path}`); }, 'copy-link': () => {} },
    apps: async (entry: { path: string; id?: string }) => { asked.push(entry.id ?? ''); return { targets: [answers[entry.path.split('/').pop()!]], fileManager: 'finder' } as never; },
    openApp: async (entry: { path: string; id?: string }, target: string, app: string) => {
      if (entry.path.endsWith('locked.pdf')) throw new Error('This file cannot be opened. Check its permissions.');
      opened.push([entry.id, target, app]);
    } };
  const navigation: LibraryNavigation = { hrefOf: target => 'document' in target ? `/${target.document}` : null, openBeside: { kind: 'tab', open() {} } };
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const page = (layout: 'grid' | 'list') => <ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library([], hosted([tag], files))} fileActions={fileActions} navigation={navigation} layout={layout} place={{ view: 'project', project: 'p1' }} /></ControlUsageProvider>;
  const entryOf = (name: string) => document.querySelector<HTMLElement>(`[aria-label="Open ${name}"]`)!.closest('li')!;
  const press = async (name: string) => { await act(async () => { fireEvent.click(screen.getByRole('button', { name: `Open ${name}` })); }); };
  for (const layout of ['grid', 'list'] as const) {
    asked.length = 0;
    const view = render(page(layout));
    await screen.findByRole('link', { name: 'Open arm.xbf' });
    // Every file: the documents, then the files no page opens, each in the Sort's order (here the host's: they tie).
    expect(opens()).toEqual(['Open arm.xbf', 'Open lid.step', 'Open datasheet.pdf', 'Open build.py', 'Open Makefile', 'Open run.sh', 'Open locked.pdf']);
    // A document is a link with its star and ⋯. A file that is none has no page, so it is a button, with its ⋯ and no
    // star; it is neither dimmed nor disabled, and never the ringed one.
    expect([entryOf('arm.xbf').querySelector('a')?.getAttribute('href'), within(entryOf('arm.xbf')).getAllByRole('button').map(button => button.getAttribute('aria-label'))])
      .toEqual(['/file-p1-arm.xbf', ['Star', 'Actions for arm.xbf']]);
    for (const name of ['datasheet.pdf', 'build.py', 'Makefile', 'run.sh']) {
      const entry = entryOf(name), button = within(entry).getByRole('button', { name: `Open ${name}` });
      expect([entry.querySelector('a'), within(entry).getAllByRole('button').map(each => each.getAttribute('aria-label')), button.hasAttribute('disabled'), button.getAttribute('aria-haspopup'),
        entry.hasAttribute('data-missing'), entry.hasAttribute('data-from')]).toEqual([null, [`Open ${name}`, `Actions for ${name}`], false, null, false, false]);
    }
    if (layout === 'grid') {
      // In the grid, the documents' cards, then those files' tiles, in a list of their own: each its kind's glyph and its
      // name, with no picture, badge or line (it has no picture to show).
      const named = (list: string) => within(screen.getByRole('list', { name: list })).getAllByRole('listitem').map(item => item.querySelector('[data-library-label]')?.textContent);
      expect([named('Files'), named('Other files')]).toEqual([['arm.xbf', 'lid.step'], ['datasheet.pdf', 'build.py', 'Makefile', 'run.sh', 'locked.pdf']]);
      expect([entryOf('build.py').querySelector('[data-library-picture], [data-library-format], [data-library-status]'), Boolean(entryOf('build.py').querySelector('[data-glyph="file"] svg'))])
        .toEqual([null, true]);
    } else {
      // In the list, rows after the documents', each Type its extension as its name writes it, upper case; a dash with none.
      expect(['datasheet.pdf', 'build.py', 'Makefile'].map(name => entryOf(name).querySelector('[data-column="type"]')?.textContent)).toEqual(['PDF', 'PY', '—']);
    }
    // Nothing is asked of the host until a press. Then the file is opened: by the OS's own handler where it is offered...
    expect(asked).toEqual([]);
    await press('datasheet.pdf');
    await waitFor(() => expect(opened).toEqual([['file-p1-datasheet.pdf', 'source', 'default']]));
    expect([asked, screen.queryByRole('menu'), screen.queryByRole('alert')]).toEqual([['file-p1-datasheet.pdf'], null, null]);
    // ...a file with no app listed too...
    await press('Makefile');
    await waitFor(() => expect(opened.at(-1)).toEqual(['file-p1-Makefile', 'source', 'default']));
    // ...else by the first app the host lists (code, with an editor installed)...
    await press('build.py');
    await waitFor(() => expect(opened.at(-1)).toEqual(['file-p1-build.py', 'source', 'vscode']));
    expect(opened.length).toBe(3);
    // ...and where it lists neither, nothing opens it here: said in the place's line, by the file's name.
    await press('run.sh');
    expect((await screen.findByRole('alert')).textContent).toBe('No app on this computer opens run.sh.');
    expect(opened.length).toBe(3);
    // An open the host refuses is said in its own words; the next press clears the line.
    await press('locked.pdf');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('This file cannot be opened. Check its permissions.'));
    await press('datasheet.pdf');
    await waitFor(() => expect(opened.length).toBe(4));
    expect(screen.queryByRole('alert')).toBeNull();
    opened.length = 0;
    view.unmount();
  }
  // Its ⋯: Open in, a submenu of the host's apps and Default app (the rows the navbar's Open in draws), looked up as the
  // menu opens; then Copy path and the file manager. No Open, Open in new tab, Copy link or Star.
  const menuOf = async (name: string) => {
    const open = await menu(name);
    await waitFor(() => expect(asked.at(-1)).toBe(`file-p1-${name}`));
    return open;
  };
  let view = render(page('grid'));
  await screen.findByRole('link', { name: 'Open arm.xbf' });
  let open = await menuOf('build.py');
  await within(open).findByRole('menuitem', { name: 'Open in' });
  expect(items(open)).toEqual(['Open in', 'Copy path', 'Reveal in Finder']);
  await user.click(within(open).getByRole('menuitem', { name: 'Open in' }));
  const openIn = await screen.findByRole('menu', { name: 'Open in' });
  // No Default app where the host says the OS's handler is not offered.
  expect(items(openIn)).toEqual(['Visual Studio Code', 'Cursor']);
  await act(async () => { fireEvent.click(within(openIn).getByRole('menuitem', { name: 'Cursor' })); });
  expect(opened).toEqual([['file-p1-build.py', 'source', 'cursor']]);
  view.unmount();
  // No app and no handler: Copy path and the file manager alone, both working.
  view = render(page('list'));
  await screen.findByRole('link', { name: 'Open arm.xbf' });
  open = await menuOf('run.sh');
  expect(items(open)).toEqual(['Copy path', 'Reveal in Finder']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Reveal in Finder' })); });
  expect(done).toEqual(['reveal /Users/sam/cad/heart-tag/run.sh']);
  view.unmount();
  // A document's ⋯ has Open in too, after its Open and Open in new tab.
  view = render(page('grid'));
  await screen.findByRole('link', { name: 'Open arm.xbf' });
  answers['arm.xbf'] = { target: 'source', kind: 'model', name: 'arm.py', present: true, apps: [{ id: 'vscode', name: 'Visual Studio Code' }], default: false };
  open = await menuOf('arm.xbf');
  await within(open).findByRole('menuitem', { name: 'Open in' });
  expect(items(open)).toEqual(['Open', 'Open in new tab', 'Open in', 'Copy path', 'Copy link', 'Reveal in Finder', 'Star']);
  view.unmount();
  // Each open handed to an app is counted, a refused one too; never which app.
  expect(reported(reports)).toMatchObject({ file_open_app: 11, home_reveal: 1 });
});

it("orders a folder's page in groups, each in the Sort's order: its folders, its documents, then the files no page opens", async () => {
  const tag = project('p1', 'heart-tag');
  const files = [file(tag, 'zeta.step', { documentKind: 'step', updated: 50 }), file(tag, 'beta.pdf', { documentKind: null, updated: 90 }),
    file(tag, 'alpha.xbf', { documentKind: 'model', updated: 10 }), file(tag, 'gamma.py', { documentKind: null, updated: 20 }), file(tag, 'sub/inner.step')];
  // A host that shows a file in its file manager: each file is a press.
  const fileActions = { platform: 'linux' as const, perform: { 'copy-path': () => {}, reveal: () => {} } };
  const page = (sort: 'activity' | 'name', layout: 'grid' | 'list') => <ModelLibrary library={library([], hosted([tag], files))} fileActions={fileActions} layout={layout}
    sort={sort} onSortChange={() => {}} place={{ view: 'project', project: 'p1' }} />;
  const view = render(page('activity', 'list'));
  await screen.findByRole('button', { name: 'Open zeta.step' });
  // Newest first within each group: beta.pdf, the newest of all, still after the documents.
  expect(opens()).toEqual(['Open sub', 'Open zeta.step', 'Open alpha.xbf', 'Open beta.pdf', 'Open gamma.py']);
  view.rerender(page('name', 'list'));
  expect(opens()).toEqual(['Open sub', 'Open alpha.xbf', 'Open zeta.step', 'Open beta.pdf', 'Open gamma.py']);
  // The grid in the same order: the folders' tiles, the documents' cards, then the other files' tiles.
  view.rerender(page('name', 'grid'));
  expect([opens(), ['Folders', 'Files', 'Other files'].map(list => within(screen.getByRole('list', { name: list })).getAllByRole('listitem').length)])
    .toEqual([['Open sub', 'Open alpha.xbf', 'Open zeta.step', 'Open beta.pdf', 'Open gamma.py'], [1, 2, 2]]);
});

it("groups a search's results as a folder's page is, the documents' cards then the other files' tiles; and while a file's tile is being opened, a spinner stands where its glyph is", async () => {
  const tag = project('p1', 'heart-tag');
  const host = hosted([tag], [file(tag, 'arm.xbf', { documentKind: 'model' }), file(tag, 'build.py', { documentKind: null }), file(tag, 'build.step', { documentKind: 'step' })]);
  let answer!: (files: unknown) => void;
  const openApp = vi.fn(async () => {});
  const fileActions = { platform: 'linux' as const, perform: { 'copy-path': () => {} }, apps: () => new Promise(resolve => { answer = resolve; }) as never, openApp };
  render(<ModelLibrary library={library([], host)} fileActions={fileActions} place={{ view: 'project', project: 'p1' }} />);
  const press = await screen.findByRole('button', { name: 'Open build.py' });
  const tile = press.closest('li')!;
  expect(tile.closest('ul')?.getAttribute('aria-label')).toBe('Other files');
  // Pressed, its apps are asked for: a spinner where its glyph was, until the host answers and the app is opened.
  await act(async () => { fireEvent.click(press); });
  expect([tile.hasAttribute('data-opening'), press.getAttribute('aria-busy'), Boolean(within(tile).queryByLabelText('Opening build.py')), tile.querySelector('[data-glyph]')])
    .toEqual([true, 'true', true, null]);
  await act(async () => { answer({ targets: [{ target: 'source', kind: 'code', name: 'build.py', present: true, apps: [{ id: 'vscode', name: 'VS Code' }], default: false }] }); });
  await waitFor(() => expect(openApp).toHaveBeenCalledWith(expect.objectContaining({ id: 'file-p1-build.py' }), 'source', 'vscode'));
  await waitFor(() => expect([tile.hasAttribute('data-opening'), Boolean(tile.querySelector('[data-glyph="file"]'))]).toEqual([false, true]));
  // A search: the documents' cards first, then the file no page opens as the same tile, never a card with an empty picture.
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'build' } });
  await waitFor(() => expect(host.folder).toHaveBeenLastCalledWith('p1', { path: '', q: 'build' }));
  await waitFor(() => expect(opens()).toEqual(['Open build.step', 'Open build.py']));
  const lists = ['Files', 'Other files'].map(list => within(screen.getByRole('list', { name: list })).getAllByRole('listitem').map(item => item.textContent));
  expect([lists[0].length, lists[1].length, screen.getByRole('button', { name: 'Open build.py' }).closest('li')?.querySelector('[data-library-format]')]).toEqual([1, 1, null]);
});

it("groups a search's rows in the list the documents' first, then the other files', each in the Sort's order, and no cell is blank or says Standalone", async () => {
  const tag = project('p1', 'heart-tag');
  const loose = (below: string) => file(tag, below, { documentKind: null, thumbnail: null, updated: null });
  const host = hosted([tag], [loose('a-build.py'), file(tag, 'z-build.step', { documentKind: 'step', updated: null }), file(tag, 'b-build.step', { documentKind: 'step' }), loose('c-build.pdf')]);
  const fileActions = { platform: 'linux' as const, perform: { 'copy-path': () => {} }, apps: async () => ({ targets: [] }) as never, openApp: async () => {} };
  render(<ModelLibrary library={library([], host)} fileActions={fileActions} layout="list" sort="name" onSortChange={() => {}} place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open a-build.py' });
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'build' } });
  await waitFor(() => expect(host.folder).toHaveBeenLastCalledWith('p1', { path: '', q: 'build' }));
  await waitFor(() => expect(opens()).toEqual(['Open b-build.step', 'Open z-build.step', 'Open a-build.py', 'Open c-build.pdf']));
  const rows = [...screen.getByRole('list', { name: 'Files' }).querySelectorAll('li')];
  const blank = rows.flatMap(row => [...row.querySelectorAll('[data-column]')].filter(cell => !(cell.textContent ?? '').trim()));
  expect(blank).toEqual([]);
  expect(screen.queryByText('Standalone')).toBeNull();
  const edited = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).querySelector('[data-column=edited]')?.textContent;
  expect([edited('z-build.step'), edited('a-build.py')]).toEqual(['—', '—']);
});

it('a file that is no document does what its host can: shown in the file manager where the host opens no apps, and no control at all where it can do neither', async () => {
  const tag = project('p1', 'heart-tag');
  const files = [file(tag, 'arm.xbf', { documentKind: 'model' }), file(tag, 'notes.md', { documentKind: null })];
  const done: string[] = [];
  const page = (fileActions?: object) => <ModelLibrary library={library([], hosted([tag], files))} fileActions={fileActions as never} place={{ view: 'project', project: 'p1' }} />;
  // A host that opens no apps: a press shows the file in its file manager, and the ⋯ has what the host can do.
  let view = render(page({ platform: 'linux', perform: { 'copy-path': () => {}, reveal: ({ path }: { path: string }) => { done.push(path); } } }));
  const notes = await screen.findByRole('button', { name: 'Open notes.md' });
  await act(async () => { fireEvent.click(notes); });
  expect(done).toEqual(['/Users/sam/cad/heart-tag/notes.md']);
  expect(items(await menu('notes.md'))).toEqual(['Copy path', 'Show in file manager']);
  view.unmount();
  // A host that can only copy a path: the tile is there, named, and is no control; its ⋯ offers Copy path.
  view = render(page({ platform: 'linux', perform: { 'copy-path': () => {} } }));
  await screen.findByRole('button', { name: 'Open arm.xbf' });
  let card = screen.getByText('notes.md').closest('li')!;
  expect([within(card).queryByRole('link'), within(card).getAllByRole('button').map(button => button.getAttribute('aria-label')), card.querySelector('[data-library-label]')?.textContent])
    .toEqual([null, ['Actions for notes.md'], 'notes.md']);
  expect(items(await menu('notes.md'))).toEqual(['Copy path']);
  view.unmount();
  // A host that can do nothing with a file: no control at all.
  view = render(page());
  await screen.findByRole('button', { name: 'Open arm.xbf' });
  card = screen.getByText('notes.md').closest('li')!;
  expect([within(card).queryByRole('button'), within(card).queryByRole('link')]).toEqual([null, null]);
  view.unmount();
});

it("a search on a project's page asks the host and lists what is below, flat; every list has the same four columns", async () => {
  const tag = project('p1', 'heart-tag');
  const host = hosted([tag], [file(tag, 'housing/v3/housing.xbf'), file(tag, 'housing/v3/drawings/housing-plan.dxf'), file(tag, 'housing/lid.step'), file(tag, 'top.step')]);
  const source = library([model('loose.step'), { ...file(tag, 'top.step'), opened: 5 }], host);
  const home = (at: Parameters<typeof ModelLibrary>[0]['place']) => <ModelLibrary library={source} layout="list" place={at} />;
  const view = render(home({ view: 'project', project: 'p1', path: 'housing' }));
  await screen.findByRole('button', { name: 'Open lid.step' });
  const header = () => [...screen.getByRole('list', { name: 'Files' }).previousElementSibling!.children].map(cell => cell.textContent);
  const columns = ['Name', 'Type', 'Last viewed', 'Last edited'];
  // A folder's listing, a search and Recents: one header, with no Where or Project.
  expect([header(), opens()]).toEqual([columns, ['Open v3', 'Open lid.step']]);
  // Words typed: once typing rests, the host is asked for everything below the folder on screen that holds them.
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'hous' } });
  await waitFor(() => expect(host.folder).toHaveBeenLastCalledWith('p1', { path: 'housing', q: 'hous' }));
  await waitFor(() => expect(opens()).toEqual(['Open housing.xbf', 'Open housing-plan.dxf']));
  expect(header()).toEqual(columns);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'nothing' } });
  expect(await screen.findByText('No matches.')).toBeTruthy();
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: '' } });
  view.rerender(home({ view: 'recents' }));
  expect(header()).toEqual(columns);
  expect(below('/a/b/c.py', '/a/b/')).toBe('c.py');
  expect([below('/a/b', '/a/b'), below('C:\\work\\x\\y.py', 'C:/work'), below('/elsewhere/y.py', '/a/b')]).toEqual(['', 'x/y.py', '/elsewhere/y.py']);
});

it("narrows a project's page by the path below the project's folder: its own name matches nothing", () => {
  const rows = [model('a.step', { path: '/w/gearbox/a.step' }), model('gearbox.xbf', { path: '/w/gearbox/sub/gearbox.xbf' })];
  expect(filterModels(rows, 'gearbox').length).toBe(2);
  expect(filterModels(rows, 'gearbox', '/w/gearbox').map(item => item.name)).toEqual(['gearbox.xbf']);
});

it("says a card's last activity alone, as Figma's cards do: no project before it in Recents or Starred", async () => {
  const tag = project('p1', 'heart-tag');
  const source = library([{ ...file(tag, 'src/arm.xbf'), opened: 5, pinned: true }, model('loose.step', { pinned: true })], hosted([tag]));
  const home = (at: Parameters<typeof ModelLibrary>[0]['place']) => <ModelLibrary library={source} place={at} />;
  const view = render(home({ view: 'recents' }));
  await waitFor(() => expect(place('project:p1')).toBeTruthy());
  const second = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).querySelector('[data-library-status]')?.textContent;
  expect([second('arm.xbf'), second('loose.step')]).toEqual(['Edited 16h ago', 'Edited 16h ago']);
  view.rerender(home({ view: 'pinned' }));
  expect([second('arm.xbf'), second('loose.step')]).toEqual(['Edited 16h ago', 'Edited 16h ago']);
});

it("sorts the place on screen by last activity, by name, by last viewed or by last edited, the host keeping the choice", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const documents = [model('b10.step', { opened: 100, updated: 30 }), model('b9.step', { updated: 40, opened: null }), model('arm.xbf', { opened: 50, updated: 10 }),
    model('Axle.dxf', { opened: 70, updated: 20, pinned: true })];
  const sorts: string[] = [];
  const home = (sort?: 'activity' | 'name' | 'viewed' | 'edited') => <ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library(documents)} sort={sort} onSortChange={next => sorts.push(next)} /></ControlUsageProvider>;
  const view = render(home());
  await screen.findByRole('button', { name: 'Open arm.xbf' });
  // Last activity, the later of viewed and edited, newest first: a starred document is not first (Starred is a place of its own).
  expect(opens()).toEqual(['Open b10.step', 'Open Axle.dxf', 'Open arm.xbf', 'Open b9.step']);
  // One control: its glyph, the sort's name and a chevron, with no label beside it; named whole for assistive technology.
  const trigger = screen.getByRole('button', { name: 'Sort by Last activity' });
  expect([trigger.textContent, trigger.previousElementSibling, [...trigger.querySelectorAll('svg')].map(svg => svg.getAttribute('class')?.match(/lucide-[\w-]+/)?.[0]),
    trigger.getAttribute('data-variant')]).toEqual(['Last activity', null, ['lucide-arrow-down-up', 'lucide-chevron-down'], 'ghost']);
  await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  const open = await screen.findByRole('menu');
  // Only orders of what the list shows.
  expect(within(open).getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Last activity', 'true'], ['Name', 'false'], ['Last viewed', 'false'], ['Last edited', 'false']]);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitemradio', { name: 'Name' })); });
  expect(sorts).toEqual(['name']);
  // By name, as a person counts: 9 before 10, whatever the case.
  view.rerender(home('name'));
  expect(opens()).toEqual(['Open arm.xbf', 'Open Axle.dxf', 'Open b9.step', 'Open b10.step']);
  expect(screen.getByRole('button', { name: 'Sort by Name' }).textContent).toBe('Name');
  // By when a page last opened it, newest first, a file none opened last; by when it last changed.
  view.rerender(home('viewed'));
  expect(opens()).toEqual(['Open b10.step', 'Open Axle.dxf', 'Open arm.xbf', 'Open b9.step']);
  view.rerender(home('edited'));
  expect(opens()).toEqual(['Open b9.step', 'Open b10.step', 'Open Axle.dxf', 'Open arm.xbf']);
  expect(screen.getByRole('button', { name: 'Sort by Last edited' }).textContent).toBe('Last edited');
  // Where a time is not known the file comes last, the host's order where two tie.
  expect(sortDocuments([model('n.step', { opened: null }), model('o.step', { opened: 5 }), model('m.step', { opened: null })], 'viewed').map(item => item.name)).toEqual(['o.step', 'n.step', 'm.step']);
  view.unmount();
  expect(reported(reports)).toEqual({ home_sort_name: 1 });
  cleanup();
  // A host that keeps no order has no Sort.
  render(<ModelLibrary library={library(documents)} />);
  await screen.findByRole('button', { name: 'Open arm.xbf' });
  expect(screen.queryByRole('button', { name: /^Sort/ })).toBeNull();
});

it('narrows Recents and Starred with a search of the rows in hand, and says when nothing matches', async () => {
  const source = library([model('part_1.stl', { pinned: true }), model('part_2.stl', { pinned: true })]);
  render(<ModelLibrary library={source} place={{ view: 'pinned' }} />);
  await screen.findByRole('button', { name: 'Open part_2.stl' });
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'part_2' } });
  expect(opens()).toEqual(['Open part_2.stl']);
  // The sidebar's row is the place's name alone, whatever the search.
  expect(place('pinned').textContent).toBe('Starred');
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'nothing' } });
  expect(screen.getByRole('main').querySelector('[data-library-state]')?.textContent).toBe('No matches.');
});

it("gives a project's page a menu: the folder on screen's Copy path and Reveal, and Remove from CAD, which forgets the project alone, goes to Recents and says so", async () => {
  const perform = { 'copy-path': vi.fn(async () => {}), reveal: vi.fn(async () => {}) };
  let listed = [project('p1', 'heart-tag')];
  const removeProject = vi.fn(async () => { listed = []; return listed; });
  const places: unknown[] = [];
  const source = library([model('loose.step')], { ...hosted(listed, [file(listed[0], 'part_0.stl')]), projects: async () => listed, removeProject });
  const page = () => <ModelLibrary library={source} fileActions={{ platform: 'darwin', perform }} onPlaceChange={next => places.push(next)} />;
  let view = render(page());
  await waitFor(() => expect(place('project:p1')).toBeTruthy());
  await act(async () => { fireEvent.click(place('project:p1')); });
  const trigger = () => screen.getByRole('button', { name: 'Actions for the project heart-tag' });
  await act(async () => { fireEvent.pointerDown(trigger(), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  expect(items(await screen.findByRole('menu'))).toEqual(['Copy path', 'Reveal in Finder', 'Remove from CAD']);
  await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: 'Copy path' })); });
  expect(perform['copy-path']).toHaveBeenCalledWith({ path: '/Users/sam/cad/heart-tag', kind: 'directory' });
  // A menu each render (jsdom): Remove from CAD, in a home of its own.
  view.unmount();
  cleanup();
  places.length = 0;
  view = render(page());
  await waitFor(() => expect(place('project:p1')).toBeTruthy());
  await act(async () => { fireEvent.click(place('project:p1')); });
  await act(async () => { fireEvent.pointerDown(trigger(), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  await act(async () => { fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from CAD' })); });
  expect(removeProject).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1' }));
  expect(await screen.findByText('heart-tag removed. Nothing on disk changed.')).toBeTruthy();
  expect([place('project:p1'), place('recents').getAttribute('aria-current'), opens()]).toEqual([null, 'page', ['Open loose.step']]);
  expect(places).toEqual([{ view: 'project', project: 'p1' }, { view: 'recents' }]);
  // The line is that move's: it goes with the next place.
  await act(async () => { fireEvent.click(place('pinned')); });
  expect(screen.queryByText(/heart-tag removed/)).toBeNull();
});

it("goes to the page of the project Import's Folder opened, from the sidebar's + too, and says what came of it", async () => {
  let listed: LibraryProject[] = [];
  const gear = project('p2', 'gear', { root: '/w/gear' });
  const folders = hosted([gear], [file(gear, 'part_0.stl'), file(gear, 'STEP/gear.step')]);
  const answers = [{ project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: true, folder: '/w/gear' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear/STEP' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear' }];
  // The projects list it a read later than its answer: its page waits for it meanwhile.
  let arrive!: () => void;
  const importFolder = vi.fn(async () => { arrive = () => { listed = [gear]; }; return answers.shift()!; });
  const places: unknown[] = [];
  render(<ModelLibrary library={library([], { folder: folders.folder, projects: async () => listed, importFolder, pick: async () => {} })} onPlaceChange={next => places.push(next)} />);
  await screen.findByText('Nothing here yet');
  // No projects yet: said where they would be.
  expect(within(screen.getByRole('navigation', { name: 'Places' })).getByText('No projects yet.')).toBeTruthy();
  const choose = async () => {
    await act(async () => { fireEvent.pointerDown(screen.getByRole('button', { name: 'Import', exact: true }), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    await act(async () => { fireEvent.click(await screen.findByRole('menuitem', { name: 'Folder…' })); });
  };
  await choose();
  expect(await screen.findByText('gear is now a project. Nothing was written to the folder.')).toBeTruthy();
  expect(places).toEqual([{ view: 'project', project: 'p2' }]);
  expect(screen.getByRole('list', { name: 'Files' }).getAttribute('aria-busy')).toBe('true');
  await act(async () => { arrive(); document.dispatchEvent(new Event('visibilitychange')); });
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([screen.getByRole('main').querySelector('h1')?.textContent, place('project:p2').getAttribute('aria-current')]).toEqual(['gear', 'page']);
  await choose();
  // A folder inside a project: the project's page, at that folder.
  expect(await screen.findByText('STEP is inside gear, which is already a project.')).toBeTruthy();
  expect(places.at(-1)).toEqual({ view: 'project', project: 'p2', path: 'STEP' });
  await screen.findByRole('button', { name: 'Open gear.step' });
  // The sidebar's +, by Projects: the same chooser.
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open a folder as a project' })); });
  expect(await screen.findByText('gear is already a project.')).toBeTruthy();
  expect(importFolder).toHaveBeenCalledTimes(3);
  cleanup();
  // A host with no chooser has no +.
  render(<ModelLibrary library={library([], { projects: async () => [] })} />);
  await screen.findByText('Nothing here yet');
  expect(screen.queryByRole('button', { name: 'Open a folder as a project' })).toBeNull();
});

it('says what each place lacks: an empty project, one whose folder is gone, one no longer listed, a folder that cannot be read, and projects that cannot be read', async () => {
  const tag = project('p1', 'heart-tag'), lamp = project('p2', 'lamp', { missing: true });
  const source = library([model('loose.step', { project: 'p1' })], hosted([tag, lamp], [file(lamp, 'part_0.stl')]));
  const home = (at: Parameters<typeof ModelLibrary>[0]['place'], from = source) => <ModelLibrary library={from} place={at} />;
  const view = render(home({ view: 'project', project: 'p1' }));
  expect(await screen.findByText('This folder is empty.')).toBeTruthy();
  view.rerender(home({ view: 'project', project: 'p1', path: 'renamed' }));
  expect(await screen.findByText("Couldn't read this folder. It may have been moved or renamed.")).toBeTruthy();
  expect([...document.querySelectorAll('[data-library-crumb]')].map(crumb => crumb.textContent)).toEqual(['heart-tag']);
  view.rerender(home({ view: 'project', project: 'p2' }));
  expect(screen.getByText("This project's folder is gone. Remove it, or put the folder back.")).toBeTruthy();
  expect(opens()).toEqual([]);
  view.rerender(home({ view: 'project', project: 'removed' }));
  expect(screen.getByText('This project is no longer in CAD. Open its folder again to bring it back.')).toBeTruthy();
  expect(screen.getByRole('main').querySelector('h1')?.textContent).toBe('Project');
  cleanup();
  // The projects cannot be read: said where they would be, and on a project's page; the documents are still listed.
  const failing = library([model('loose.step')], { projects: async () => { throw new Error('offline'); } });
  const again = render(home({ view: 'recents' }, failing));
  await screen.findByRole('button', { name: 'Open loose.step' });
  expect(within(screen.getByRole('navigation', { name: 'Places' })).getByText("Couldn't read the projects.")).toBeTruthy();
  again.rerender(home({ view: 'project', project: 'p1' }, failing));
  expect(within(screen.getByRole('main')).getByText("Couldn't read the projects.")).toBeTruthy();
});

// The host's addresses (`navigation.hrefOf`): a document's page by its id, a place's on the home; a document named by
// its path (its row carries no id) has none.
const addresses: LibraryNavigation = { hrefOf: target => 'document' in target ? (target.document.startsWith('/') ? null : `/${target.document}?token=t`)
  : `/?${target.home.view === 'project' ? `project=${target.home.project}${target.home.path ? `&path=${target.home.path}` : ''}` : `view=${target.home.view}`}` };

it("makes a card's and a row's main press a real link where the host gives the document an address, and a button where it gives none", async () => {
  const tag = project('p1', 'heart-tag');
  const source = library([model('bracket.step', { id: 'id-bracket' }), model('gone.step', { id: 'id-gone', missing: true }), model('unnamed.step')],
    hosted([tag], [file(tag, 'part_0.stl'), file(tag, 'STL/part_1.stl')]));
  for (const layout of ['grid', 'list'] as const) {
    const view = render(<ModelLibrary library={source} layout={layout} navigation={addresses} />);
    const card = await screen.findByRole('link', { name: 'Open bracket.step' });
    expect([card.tagName, card.getAttribute('href'), card.classList.contains('cad-library-open')]).toEqual(['A', '/id-bracket?token=t', true]);
    // A plain click opens it in this view, and the browser follows nothing.
    const click = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    await act(async () => { card.dispatchEvent(click); });
    expect([click.defaultPrevented, (source.open as ReturnType<typeof vi.fn>).mock.calls.length]).toEqual([true, 1]);
    // ⌘ or Ctrl and a click, Shift and a click, and a middle click are the browser's: a new tab, and nothing opens here.
    for (const init of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { button: 1 }]) {
      const press = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init });
      await act(async () => { card.dispatchEvent(press); });
      expect(press.defaultPrevented).toBe(false);
    }
    expect(source.open).toHaveBeenCalledTimes(1);
    // A document that is gone opens nowhere: a disabled button.
    expect([(screen.getByRole('button', { name: 'Open gone.step' }) as HTMLButtonElement).disabled, screen.queryByRole('link', { name: 'Open gone.step' })]).toEqual([true, null]);
    // A document the host has no address for (its row carries no id): a button, opened here.
    expect(screen.getByRole('button', { name: 'Open unnamed.step' }).tagName).toBe('BUTTON');
    // A project's file no page has opened yet has its page (the host knows each file it lists by its id), and its
    // folder has its own address: a plain click goes there in this view.
    await act(async () => { fireEvent.click(place('project:p1')); });
    expect((await screen.findByRole('link', { name: 'Open part_0.stl' })).getAttribute('href')).toBe('/file-p1-part_0.stl?token=t');
    const folder = screen.getByRole('link', { name: 'Open STL' });
    expect(folder.getAttribute('href')).toBe('/?project=p1&path=STL');
    await act(async () => { fireEvent.click(folder); });
    expect((await screen.findByRole('link', { name: 'Open part_1.stl' })).getAttribute('href')).toBe('/file-p1-STL/part_1.stl?token=t');
    // And so has each part of the path back up.
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'heart-tag' }).getAttribute('href')).toBe('/?project=p1');
    view.unmount();
    cleanup();
    (source.open as ReturnType<typeof vi.fn>).mockClear();
  }
});

it("makes each place's row a link where the host gives places an address: a plain click shows it here", async () => {
  const places: unknown[] = [];
  render(<ModelLibrary library={library([model('a.step')], hosted([project('p1', 'heart-tag')]))} navigation={addresses} onPlaceChange={next => places.push(next)} />);
  await waitFor(() => expect(place('project:p1')).toBeTruthy());
  expect([...document.querySelectorAll('[data-place]')].map(row => [row.tagName, row.getAttribute('href')]))
    .toEqual([['A', '/?view=recents'], ['A', '/?view=pinned'], ['A', '/?project=p1']]);
  const meta = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, metaKey: true });
  await act(async () => { place('project:p1').dispatchEvent(meta); });
  expect([meta.defaultPrevented, places]).toEqual([false, []]);
  const plain = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
  await act(async () => { place('project:p1').dispatchEvent(plain); });
  expect([plain.defaultPrevented, places, place('project:p1').getAttribute('aria-current')]).toEqual([true, [{ view: 'project', project: 'p1' }], 'page']);
});

it("offers Open in new tab in every document's menu, directly after Open, and first in a project's, where the host can open a target beside the view", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const opened: unknown[] = [];
  const tag = project('p1', 'heart-tag');
  const source = library([model('bracket.step', { id: 'id-bracket' })], { ...hosted([tag], [file(tag, 'part_0.stl'), file(tag, 'STL/part_1.stl')]), removeProject: async () => [] });
  const home = (navigation: LibraryNavigation, at: Parameters<typeof ModelLibrary>[0]['place'] = { view: 'project', project: 'p1' }) =>
    render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} navigation={navigation} place={at} /></ControlUsageProvider>);
  const tab: LibraryNavigation = { openBeside: { kind: 'tab', open: target => { opened.push(target); } } };
  // A document the host has a page for is named by its id.
  let view = home(tab, { view: 'recents' });
  await screen.findByRole('button', { name: 'Open bracket.step' });
  let open = await menu('bracket.step');
  expect(items(open)).toEqual(['Open', 'Open in new tab', 'Star']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open in new tab' })); });
  view.unmount();
  cleanup();
  // A project's file no page has opened, by its id.
  view = home(tab);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  open = await menu('part_0.stl');
  expect(items(open)).toEqual(['Open', 'Open in new tab', 'Star']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open in new tab' })); });
  view.unmount();
  cleanup();
  // A project's ⋯, on one of its folders: Open in new tab first, which opens that folder.
  view = home(tab, { view: 'project', project: 'p1', path: 'STL' });
  await screen.findByRole('button', { name: 'Open part_1.stl' });
  await act(async () => { fireEvent.pointerDown(screen.getByRole('button', { name: 'Actions for the project heart-tag' }), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  open = await screen.findByRole('menu');
  expect(items(open)).toEqual(['Open in new tab', 'Remove from CAD']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open in new tab' })); });
  await waitFor(() => expect(opened).toHaveLength(3));
  expect(opened).toEqual([{ document: 'id-bracket' }, { document: 'file-p1-part_0.stl' }, { home: { view: 'project', project: 'p1', path: 'STL' } }]);
  view.unmount();
  expect(reported(reports)).toEqual({ home_open_new_tab: 2, home_project_open_new_tab: 1 });
  cleanup();
  // A page in an app's frame: Open in browser, a document's alone where the host opens no place beside the view.
  const browser: LibraryNavigation = { openBeside: { kind: 'browser', places: false, open: () => {} } };
  view = home(browser);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect(items(await menu('part_0.stl')).slice(0, 2)).toEqual(['Open', 'Open in browser']);
  view.unmount();
  cleanup();
  home(browser);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  await act(async () => { fireEvent.pointerDown(screen.getByRole('button', { name: 'Actions for the project heart-tag' }), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  expect(items(await screen.findByRole('menu'))).toEqual(['Remove from CAD']);
  cleanup();
  // A host that cannot: no such item (the first tests' menus).
  render(<ModelLibrary library={source} />);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  expect(items(await menu('bracket.step'))).toEqual(['Open', 'Star']);
});

it('names a document whose row carries no id by its path, and says why Open in new tab failed where the library shows it', async () => {
  const asked: unknown[] = [];
  render(<ModelLibrary library={library([model('a.step')])} navigation={{ openBeside: { kind: 'tab', open: target => { asked.push(target); } } }} />);
  await screen.findByRole('button', { name: 'Open a.step' });
  await act(async () => { fireEvent.click(within(await menu('a.step')).getByRole('menuitem', { name: 'Open in new tab' })); });
  await waitFor(() => expect(asked).toEqual([{ document: '/work/parts/a.step' }]));
  cleanup();
  const navigation: LibraryNavigation = { openBeside: { kind: 'tab', open: async () => { throw new Error('File does not exist: /work/parts/a.step'); } } };
  render(<ModelLibrary library={library([model('a.step')])} navigation={navigation} />);
  await screen.findByRole('button', { name: 'Open a.step' });
  await act(async () => { fireEvent.click(within(await menu('a.step')).getByRole('menuitem', { name: 'Open in new tab' })); });
  expect((await screen.findByRole('alert')).textContent).toBe('File does not exist: /work/parts/a.step');
});

it("rings the document just left, brings it into view, and goes back to it from its button or with Escape while nothing else has the key", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const scrolled = vi.fn();
  Element.prototype.scrollIntoView = scrolled;
  const tag = project('p1', 'heart-tag');
  const back = vi.fn();
  const files = ['part_0.stl', 'part_1.stl', 'part_2.stl'].map(name => file(tag, name));
  const left = { ...files[1], path: '/elsewhere/part_1.stl' };
  const source = library([model('loose.step')], hosted([tag], files));
  const home = (from: Parameters<typeof ModelLibrary>[0]['from'], layout: 'grid' | 'list' = 'grid') => <ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={source} layout={layout} place={{ view: 'project', project: 'p1' }} from={from} onBack={back} /></ControlUsageProvider>;
  const view = render(home({ path: left.path, id: left.id, name: left.name }));
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  // Its card, and no other, is the one marked (by its id: it was reached by another path); brought into view once drawn.
  const ringed = () => [...document.querySelectorAll('[data-from]')].map(item => within(item as HTMLElement).getAllByRole('button')[0].getAttribute('aria-label'));
  expect(ringed()).toEqual(['Open part_1.stl']);
  await waitFor(() => expect(scrolled).toHaveBeenCalledTimes(1));
  expect([scrolled.mock.contexts[0], scrolled.mock.calls[0]]).toEqual([document.querySelector('[data-from]'), [{ block: 'nearest' }]]);
  // The way back stands at the title row's right end, before Sort and the layout, with its key.
  const button = screen.getByRole('button', { name: 'Back to part_1.stl' });
  expect([button.closest('[data-library-head]') !== null, button.nextElementSibling?.hasAttribute('data-library-toolbar'), button.querySelector('kbd')?.textContent, button.getAttribute('aria-keyshortcuts')])
    .toEqual([true, true, 'Esc', 'Escape']);
  fireEvent.click(button);
  expect(back).toHaveBeenCalledTimes(1);
  // Escape goes back too...
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(back).toHaveBeenCalledTimes(2);
  // ...but not from a field being typed in, nor while a menu is up (its Escape closes it), nor with a modifier held.
  fireEvent.keyDown(screen.getByRole('searchbox', { name: 'Search models' }), { key: 'Escape' });
  fireEvent.keyDown(document.body, { key: 'Escape', metaKey: true });
  await menu('part_0.stl');
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(back).toHaveBeenCalledTimes(2);
  // A row is ringed as a card is.
  view.rerender(home({ path: left.path, id: left.id, name: left.name }, 'list'));
  expect(ringed()).toEqual(['Open part_1.stl']);
  // The host forgets it (another document opened, another place): no ring, no way back, and Escape is nobody's.
  cleanup();
  render(home(null));
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([ringed(), screen.queryByRole('button', { name: /^Back to/ })]).toEqual([[], null]);
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(back).toHaveBeenCalledTimes(2);
  expect(reported(reports)).toEqual({ home_back: 2 });
});


// The home under the viewer's navbar, as a host shows it (`FileViewer`): the sidebar is the viewer's panel over this
// page (`LibrarySidebar.jsx`, on `file-viewer/panelFrame.jsx`), so its toggle is the navbar's, after the logo. The page
// is `width` wide: the home's frame, the home and the viewer all measure it.
function page({ width = 1200, panel, onPanelChange, onPlaceChange, links = true, projects = [] as LibraryProject[], platform = 'darwin', home: homeProps = {}, report }:
  { width?: number; panel?: object | null; onPanelChange?: (panel: object) => void; onPlaceChange?: (place: unknown) => void; links?: boolean | object; projects?: LibraryProject[];
    platform?: string; home?: object; report?: (counts: { control: string; count: number; seconds: number }[]) => void } = {}) {
  let wide = width;
  const observers: { callback: (entries: unknown[]) => void; targets: Element[] }[] = [];
  vi.stubGlobal('ResizeObserver', class {
    entry: { callback: (entries: unknown[]) => void; targets: Element[] };
    constructor(callback: (entries: unknown[]) => void) { this.entry = { callback, targets: [] }; observers.push(this.entry); }
    observe(target: Element) { this.entry.targets.push(target); }
    unobserve() {}
    disconnect() { this.entry.targets = []; }
  });
  const MEASURED = '[data-library-frame], .cad-library, .text-to-cad-file-viewer';
  const boxes = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const own = this.matches(MEASURED) ? wide : 0;
    return { x: 0, y: 0, left: 0, top: 0, right: own, bottom: 0, width: own, height: 0, toJSON() {} } as DOMRect;
  });
  const home = vi.fn();
  const host = testHost({ navigation: { openFile() {}, home }, environment: { colorScheme: 'light', platform },
    ...(links ? { links: links === true ? viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x' }) : links as any } : null) });
  const source = library([model('loose.step')], hosted(projects));
  const share = vi.fn(), theme = vi.fn();
  const view = render(<ControlUsageProvider report={report}><FileViewer file={null} host={host} renderers={[]} state={{}} onStateChange={() => {}}
    appSettings={links ? [{ id: 'analytics', label: 'Telemetry', checked: true, onCheckedChange: share }] : undefined}
    colorScheme={links ? { preference: 'system', onPreferenceChange: theme } : undefined}
    presentation={{ home: <ModelLibrary library={source} panel={panel as any} onPanelChange={onPanelChange} onPlaceChange={onPlaceChange as any} {...homeProps} /> }} /></ControlUsageProvider>);
  return {
    view, home, share, theme,
    /** The page resized: what measures itself is told, as a ResizeObserver tells it. */
    resize: (next: number) => act(() => { wide = next; for (const { callback, targets } of observers) if (targets.some(target => target.matches(MEASURED))) callback([]); }),
    restore: () => boxes.mockRestore(),
    toggle: () => document.querySelector<HTMLElement>('[data-viewer-navbar] [data-navbar-panel="left"]')!,
    sidebar: () => document.querySelector<HTMLElement>('aside[data-library-sidebar]'),
    frame: () => document.querySelector<HTMLElement>('[data-library-frame]')!,
  };
}
// Where the sidebar is: pinned beside the place, peeking over it, or gone; and what its toggle says.
const where = (home: ReturnType<typeof page>) => {
  const side = home.sidebar();
  const state = !side || side.hidden ? 'gone' : side.hasAttribute('data-panel-peek') ? 'peek' : side.getAttribute('data-library-sidebar') === 'page' ? 'sheet' : 'pinned';
  return [state, home.toggle().getAttribute('aria-expanded'), home.toggle().getAttribute('aria-label')];
};
const mouse = { pointerType: 'mouse' };

it("its sidebar is the viewer's panel: pinned it pushes the place, its toggle in the navbar after the logo; collapsed it leaves nothing; the person's choice is kept and stands at any width", async () => {
  const kept: object[] = [];
  const home = page({ width: 1200, onPanelChange: next => kept.push(next) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    // Wide enough, with no choice: pinned, beside the place (in the frame's row, before it, taking its own width).
    expect(where(home)).toEqual(['pinned', 'true', 'Hide panel']);
    const side = home.sidebar()!;
    expect([side.parentElement === home.frame(), side.nextElementSibling === screen.getByRole('main'), side.style.width, side.className.split(' ').includes('shrink-0'),
      side.className.split(' ').includes('absolute'), home.frame().getAttribute('data-sidebar')]).toEqual([true, true, '232px', true, false, 'push']);
    // The same toggle as over a document: in the row after the logo, the sidebar's glyph, its key in its hint.
    const row = [...document.querySelectorAll('[data-viewer-navbar] nav > *')].map(node => node.querySelector('[data-navbar-panel]') ? 'toggle' : node.getAttribute('data-navbar-logo') ? 'logo' : '?');
    expect(row).toEqual(['logo', 'toggle']);
    expect([Boolean(home.toggle().querySelector('svg[data-sidebar-icon]')), home.toggle().getAttribute('aria-keyshortcuts')]).toEqual([true, '⌘\\']);
    // Collapsed: nothing of it left, and that is their choice, written once.
    fireEvent.click(home.toggle());
    expect([where(home), home.frame().getAttribute('data-sidebar'), kept]).toEqual([['gone', 'false', 'Show panel'], 'closed', [{ open: false }]]);
    // The choice stands however wide the home is; and open, however narrow.
    await home.resize(1800);
    expect(where(home)).toEqual(['gone', 'false', 'Show panel']);
    fireEvent.click(home.toggle());
    await home.resize(640);
    expect([where(home), kept]).toEqual([['pinned', 'true', 'Hide panel'], [{ open: false }, { open: true }]]);
  } finally { home.restore(); }
});

it("until the person chooses, the home's width opens or collapses its sidebar, again at every resize, and nothing is written", async () => {
  const kept: object[] = [];
  // 871px: one short of the 640px the place keeps beside the default 232px.
  const home = page({ width: 871, onPanelChange: next => kept.push(next) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    expect(where(home)).toEqual(['gone', 'false', 'Show panel']);
    await home.resize(872);
    expect(where(home)).toEqual(['pinned', 'true', 'Hide panel']);
    await home.resize(700);
    expect([where(home), kept]).toEqual([['gone', 'false', 'Show panel'], []]);
  } finally { home.restore(); }
});

it('peeks the collapsed sidebar as a card over the place while a mouse rests on its toggle; never kept, put away by Escape or a press on the place, pinned only by the toggle', async () => {
  const kept: object[] = [];
  const home = page({ width: 1200, panel: { open: false }, onPanelChange: next => kept.push(next) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    expect(where(home)).toEqual(['gone', 'false', 'Show panel']);
    vi.useFakeTimers();
    const wait = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });
    const rest = () => { fireEvent.pointerEnter(home.toggle(), mouse); wait(PANEL_PEEK_DELAY_MS); };
    // The panel's delay, then the same sidebar over the page: a card, taking no room, the page still its full width.
    fireEvent.pointerEnter(home.toggle(), mouse);
    wait(PANEL_PEEK_DELAY_MS - 1);
    expect(where(home)[0]).toBe('gone');
    wait(1);
    expect([where(home), home.sidebar()!.className.split(' ').includes('absolute'), Boolean(home.sidebar()!.querySelector('[data-panel-peek-card]')),
      home.frame().getAttribute('data-sidebar'), within(home.sidebar()!).getByRole('navigation', { name: 'Places' }) !== null])
      .toEqual([['peek', 'false', 'Show panel'], true, true, 'closed', true]);
    // No grip on a peek: its width is not set there.
    expect(within(home.sidebar()!).queryByRole('separator')).toBeNull();
    // It goes once the pointer has left both for the panel's delay, sliding out (jsdom plays none: its fallback ends it).
    fireEvent.pointerLeave(home.toggle(), mouse);
    wait(PANEL_PEEK_LEAVE_MS);
    expect(home.sidebar()!.hasAttribute('data-panel-peek-leaving')).toBe(true);
    wait(PANEL_PEEK_EXIT_FALLBACK_MS);
    expect(where(home)[0]).toBe('gone');
    // Escape puts it away; so does a press on the place. A place chosen in it does not: nothing done inside pins or closes it.
    rest();
    fireEvent.keyDown(document.body, { key: 'Escape' });
    wait(PANEL_PEEK_EXIT_FALLBACK_MS);
    expect(where(home)[0]).toBe('gone');
    fireEvent.pointerLeave(home.toggle(), mouse);
    rest();
    fireEvent.pointerEnter(home.sidebar()!, mouse);
    fireEvent.click(home.sidebar()!.querySelector<HTMLElement>('[data-place="pinned"]')!);
    expect([where(home)[0], screen.getByRole('main').querySelector('h1')?.textContent]).toEqual(['peek', 'Starred']);
    fireEvent.pointerDown(screen.getByRole('main'));
    wait(PANEL_PEEK_EXIT_FALLBACK_MS);
    expect([where(home)[0], kept]).toEqual(['gone', []]);
    // A click on the toggle while it peeks pins it where it stands, and that is a choice.
    fireEvent.pointerLeave(home.toggle(), mouse);
    rest();
    fireEvent.click(home.toggle());
    expect([where(home), kept]).toEqual([['pinned', 'true', 'Hide panel'], [{ open: true }]]);
    // No peek for a finger, nor with a button held.
    fireEvent.click(home.toggle());
    fireEvent.pointerLeave(home.toggle(), mouse);
    fireEvent.pointerEnter(home.toggle(), { pointerType: 'touch' });
    wait(PANEL_PEEK_DELAY_MS * 2);
    fireEvent.pointerLeave(home.toggle(), { pointerType: 'touch' });
    fireEvent.pointerEnter(home.toggle(), { pointerType: 'mouse', buttons: 1 });
    wait(PANEL_PEEK_DELAY_MS * 2);
    expect(where(home)[0]).toBe('gone');
  } finally { vi.useRealTimers(); home.restore(); }
});

it('⌘\\ and Ctrl+\\ show and hide the sidebar and pin a peek, as the toggle does; never from a field being typed in, nor \\ alone', async () => {
  const kept: object[] = [];
  const home = page({ width: 1200, onPanelChange: next => kept.push(next) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    const key = (target: Element, held: object) => fireEvent.keyDown(target, { key: '\\', code: 'Backslash', ...held });
    key(document.body, {});
    key(screen.getByRole('searchbox', { name: 'Search models' }), { metaKey: true });
    key(document.body, { metaKey: true, shiftKey: true });
    expect([where(home)[0], kept]).toEqual(['pinned', []]);
    // The key is the viewer's while it is: the page's own does not follow.
    expect(key(document.body, { metaKey: true })).toBe(false);
    expect([where(home), kept]).toEqual([['gone', 'false', 'Show panel'], [{ open: false }]]);
    key(document.body, { ctrlKey: true });
    expect(where(home)[0]).toBe('pinned');
    // A peek, pinned by the key.
    key(document.body, { ctrlKey: true });
    vi.useFakeTimers();
    fireEvent.pointerEnter(home.toggle(), mouse);
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_DELAY_MS); });
    expect(where(home)[0]).toBe('peek');
    key(document.body, { metaKey: true });
    expect([where(home)[0], kept.at(-1)]).toEqual(['pinned', { open: true }]);
  } finally { vi.useRealTimers(); home.restore(); }
});

it("its width is the panel's: 232px at first, 200 to 480 by its grip, and what the person set is kept with their choice and drawn again", async () => {
  const kept: object[] = [];
  const home = page({ width: 1400, onPanelChange: next => kept.push(next) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    const grip = () => within(home.sidebar()!).getByRole('separator', { name: 'Resize panel' });
    expect([home.sidebar()!.style.width, grip().getAttribute('aria-valuenow'), grip().getAttribute('aria-valuemin'), grip().getAttribute('aria-valuemax')])
      .toEqual(['232px', '232', '200', '480']);
    // The arrows nudge it; Home and End take it to its bounds. Each is written whole, the choice with it.
    fireEvent.keyDown(grip(), { key: 'ArrowRight' });
    expect([home.sidebar()!.style.width, kept]).toEqual(['248px', [{ width: 248 }]]);
    fireEvent.keyDown(grip(), { key: 'End' });
    fireEvent.keyDown(grip(), { key: 'Home' });
    fireEvent.click(home.toggle());
    expect([kept.slice(1), where(home)[0]]).toEqual([[{ width: 480 }, { width: 200 }, { open: false, width: 200 }], 'gone']);
    // A drag writes once, as it lets go, within the bounds.
    fireEvent.click(home.toggle());
    fireEvent.pointerDown(grip(), { button: 0, pointerId: 1, clientX: 200 });
    fireEvent.pointerMove(grip(), { pointerId: 1, clientX: 320 });
    expect([home.sidebar()!.style.width, kept.length]).toEqual(['320px', 5]);
    fireEvent.pointerMove(grip(), { pointerId: 1, clientX: 900 });
    fireEvent.pointerUp(grip(), { pointerId: 1, clientX: 900 });
    expect([home.sidebar()!.style.width, kept.at(-1)]).toEqual(['480px', { open: true, width: 480 }]);
  } finally { home.restore(); cleanup(); }
  // What the host kept is what the home comes up with: its width within the bounds whatever was stored, its choice at any width.
  for (const [panel, drawn] of [[{ open: true, width: 300 }, '300px'], [{ width: 9999 }, '480px'], [{ width: 12 }, '200px']] as const) {
    const again = page({ width: 1400, panel });
    try { expect([where(again)[0], again.sidebar()!.style.width]).toEqual(['pinned', drawn]); } finally { again.restore(); cleanup(); }
  }
});

it('with no host to keep it, the home keeps its sidebar for as long as it is up; a host that kept it closed has it closed from the first frame', async () => {
  const own = page({ width: 1400 });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    fireEvent.click(own.toggle());
    await own.resize(1900);
    expect(where(own)[0]).toBe('gone');
  } finally { own.restore(); cleanup(); }
  const kept = page({ width: 1400, panel: { open: false, width: 320 } });
  try {
    // Before anything is read: the toggle is in the navbar and says the sidebar is shut.
    expect(where(kept)).toEqual(['gone', 'false', 'Show panel']);
    await screen.findByRole('button', { name: 'Open loose.step' });
    fireEvent.click(kept.toggle());
    expect([where(kept)[0], kept.sidebar()!.style.width]).toEqual(['pinned', '320px']);
  } finally { kept.restore(); }
});

it("on a phone the sidebar is the panel's sheet under the navbar: closed until its toggle opens it, a place chosen in it closes it, and nothing of it is kept", async () => {
  const kept: object[] = [], places: unknown[] = [];
  const home = page({ width: 390, onPanelChange: next => kept.push(next), onPlaceChange: next => places.push(next), projects: [project('p1', 'heart-tag')] });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    await waitFor(() => expect(document.querySelector('[data-viewer-layout]')?.getAttribute('data-viewer-layout')).toBe('mobile'));
    const sheet = () => document.querySelector<HTMLElement>('[data-panel-sheet]');
    expect([sheet(), home.sidebar(), home.toggle().getAttribute('aria-expanded'), screen.queryByRole('navigation', { name: 'Places' })]).toEqual([null, null, 'false', null]);
    fireEvent.click(home.toggle());
    await waitFor(() => expect(sheet()).not.toBeNull());
    // The panel's sheet: from the left, in the viewer's element, no scrim, no grip; the same places and Settings.
    expect([sheet()!.getAttribute('role'), sheet()!.closest('.text-to-cad-file-viewer') !== null, sheet()!.className.includes('max-w-[20rem]'),
      document.querySelector('[data-slot="sheet-overlay"]')!.hasAttribute('data-scrim'), where(home), within(sheet()!).queryByRole('separator')])
      .toEqual(['dialog', true, true, false, ['sheet', 'true', 'Hide panel'], null]);
    expect([...sheet()!.querySelectorAll('[data-place]')].map(row => row.getAttribute('data-place'))).toEqual(['recents', 'pinned', 'project:p1']);
    // A place chosen is shown, and the sheet gives the page back.
    fireEvent.click(sheet()!.querySelector<HTMLElement>('[data-place="project:p1"]')!);
    await waitFor(() => expect(sheet()).toBeNull());
    expect([places, screen.getByRole('main').querySelector('h1')?.textContent, home.toggle().getAttribute('aria-expanded')]).toEqual([[{ view: 'project', project: 'p1' }], 'heart-tag', 'false']);
    // Its key opens and shuts it; Escape shuts it. Never kept.
    fireEvent.keyDown(document.body, { key: '\\', code: 'Backslash', ctrlKey: true });
    await waitFor(() => expect(sheet()).not.toBeNull());
    fireEvent.keyDown(sheet()!, { key: 'Escape' });
    await waitFor(() => expect(sheet()).toBeNull());
    expect(kept).toEqual([]);
    // Wide again: the sheet's state is gone, and the width decides as it did.
    fireEvent.click(home.toggle());
    await waitFor(() => expect(sheet()).not.toBeNull());
    await home.resize(1200);
    await waitFor(() => expect(sheet()).toBeNull());
    expect([where(home), kept]).toEqual([['pinned', 'true', 'Hide panel'], []]);
  } finally { home.restore(); }
});

it('Escape puts a peek of the sidebar away before it goes back to the document just left; a pinned sidebar never takes the key', async () => {
  const onBack = vi.fn();
  const home = page({ width: 1200, panel: { open: false }, projects: [project('p1', 'heart-tag')],
    home: { place: { view: 'project', project: 'p1' }, from: { path: '/Users/sam/cad/heart-tag/STL/part_0.stl', name: 'part_0.stl' }, onBack } });
  try {
    await screen.findByRole('button', { name: 'Back to part_0.stl' });
    vi.useFakeTimers();
    fireEvent.pointerEnter(home.toggle(), mouse);
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_DELAY_MS); });
    expect(where(home)[0]).toBe('peek');
    // The first Escape is the peek's; the next goes back.
    fireEvent.keyDown(document.body, { key: 'Escape' });
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_EXIT_FALLBACK_MS); });
    expect([where(home)[0], onBack.mock.calls.length]).toEqual(['gone', 0]);
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(onBack).toHaveBeenCalledTimes(1);
    // Pinned, it is no layer of its own: Escape goes straight back, and it stays.
    fireEvent.click(home.toggle());
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect([onBack.mock.calls.length, where(home)[0]]).toEqual([2, 'pinned']);
  } finally { vi.useRealTimers(); home.restore(); }
});

// The sidebar's foot: the host's links as icons at its left and Settings' cog at its right corner, which opens what is
// left of the app's menu (`AppMenu`); the file viewer hands the home both where the host has a home.
const foot = (surface: HTMLElement) => surface.querySelector<HTMLElement>('[data-app-foot]')!;
const cog = (surface: HTMLElement) => within(foot(surface)).getByRole('button', { name: 'Settings' });
const footLinks = (surface: HTMLElement) => [...foot(surface).querySelectorAll<HTMLAnchorElement>('[data-app-foot-links] a')];
async function settings(surface: HTMLElement) {
  await act(async () => { fireEvent.pointerDown(cog(surface), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  return screen.findByRole('menu', { name: 'Settings' });
}
const menuRows = (menu: HTMLElement) => [...menu.querySelectorAll('[role^="menuitem"]')].map(item => item.textContent || item.getAttribute('aria-label'));

it("ends its sidebar in a row of icons, pinned: the host's links at the left (GitHub, Discord, then Send feedback), each followed the host's way, and Settings' cog at the right, whose menu holds the settings alone", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const opened: string[] = [];
  const home = page({ width: 1200, report: counts => reports.push(counts),
    links: viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x', open: async (url: string) => { opened.push(url); } }) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    // Pinned: the surface's last block, after its one scroller, so it stays while the places scroll.
    const side = home.sidebar()!;
    expect([foot(side).parentElement === side, foot(side).previousElementSibling?.getAttribute('data-slot'), foot(side).closest('nav')]).toEqual([true, 'scroll-area', null]);
    // The links, in order, each an icon named for assistive technology and in a hint; then, apart, the cog.
    expect(footLinks(side).map(link => [link.getAttribute('aria-label'), link.getAttribute('data-link'), link.getAttribute('target'), link.querySelectorAll('svg').length, link.textContent]))
      .toEqual([['GitHub', 'github', '_blank', 1, ''], ['Discord', 'discord', '_blank', 1, ''], ['Send feedback', 'feedback', '_blank', 1, '']]);
    expect(footLinks(side).map(link => link.getAttribute('href')!.replace(/\?.*/, '')))
      .toEqual(['https://github.com/earthtojake/text-to-cad', 'https://discord.gg/x', 'https://github.com/earthtojake/text-to-cad/issues/new']);
    expect([foot(side).lastElementChild === cog(side), cog(side).closest('[data-app-foot-links]'), cog(side).getAttribute('aria-haspopup'), cog(side).querySelectorAll('svg').length,
      [...footLinks(side), cog(side)].every(tile => tile.className.split(' ').includes('size-control'))]).toEqual([true, null, 'menu', 1, true]);
    await userEvent.setup().hover(footLinks(side)[1]);
    expect((await screen.findByRole('tooltip')).textContent).toBe('Discord');
    // A press follows the link as the app menu's item did: through the host where it opens links itself; Send feedback is counted.
    expect(fireEvent.click(footLinks(side)[0])).toBe(false);
    expect(fireEvent.click(footLinks(side)[2])).toBe(false);
    await waitFor(() => expect(opened.map(url => url.replace(/\?.*/, ''))).toEqual(['https://github.com/earthtojake/text-to-cad', 'https://github.com/earthtojake/text-to-cad/issues/new']));
    expect(new URL(opened[1]).searchParams.get('title')).toBe('Feedback: ');
    // The cog opens the app's menu with what is left: the person's settings and the version; no links, no way home, no search.
    const menu = await settings(side);
    expect([menu.hasAttribute('data-app-menu'), menuRows(menu), menu.querySelector('[data-link="github"], [data-link="discord"], [data-link="feedback"]'),
      menu.querySelector('[data-menu-footer]')?.textContent, cog(side).getAttribute('data-state')])
      .toEqual([true, ['Telemetry', 'System', 'Light', 'Dark'], null, 'v0.7.4', 'open']);
    // A setting turns without closing it.
    await act(async () => { fireEvent.click(within(menu).getByRole('menuitemcheckbox', { name: 'Telemetry' })); });
    await act(async () => { fireEvent.click(within(menu).getByRole('menuitemradio', { name: 'Dark' })); });
    expect([home.share.mock.calls, home.theme.mock.calls, Boolean(document.querySelector('[data-app-menu]'))]).toEqual([[[false]], [['dark']], true]);
    home.view.unmount();
    expect(reported(reports)).toEqual({ feedback: 1, theme_dark: 1 });
  } finally { home.restore(); cleanup(); }
  // Only the links the host gives; with none of them, the cog alone.
  const some = page({ width: 1200, links: { version: '0.7.4', release: '', github: 'https://github.com/a/b', discord: '', issues: '' } });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    expect([footLinks(some.sidebar()!).map(link => link.getAttribute('aria-label')), cog(some.sidebar()!) !== null]).toEqual([['GitHub'], true]);
  } finally { some.restore(); cleanup(); }
});

it("has the same foot in the peek and in a phone's sheet; a peek stays up while Settings' menu is, and through a press in it", async () => {
  const home = page({ width: 1200, panel: { open: false } });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    vi.useFakeTimers();
    fireEvent.pointerEnter(home.toggle(), mouse);
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_DELAY_MS); });
    expect([where(home)[0], footLinks(home.sidebar()!).map(link => link.getAttribute('aria-label')), cog(home.sidebar()!).getAttribute('aria-label')])
      .toEqual(['peek', ['GitHub', 'Discord', 'Send feedback'], 'Settings']);
    act(() => { fireEvent.pointerDown(cog(home.sidebar()!), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    fireEvent.pointerLeave(home.toggle(), mouse);
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_LEAVE_MS * 4); });
    expect([where(home)[0], Boolean(document.querySelector('[data-app-menu]'))]).toEqual(['peek', true]);
    // A press in that menu (it stands outside the sidebar, over the page) is no press on the page: the peek stays.
    act(() => { fireEvent.pointerDown(document.querySelector('[data-app-menu] [role="menuitemcheckbox"]')!, { button: 0, pointerType: 'mouse' }); });
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_EXIT_FALLBACK_MS); });
    expect(where(home)[0]).toBe('peek');
  } finally { vi.useRealTimers(); home.restore(); cleanup(); }
  const phone = page({ width: 390 });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    await waitFor(() => expect(document.querySelector('[data-viewer-layout]')?.getAttribute('data-viewer-layout')).toBe('mobile'));
    fireEvent.click(phone.toggle());
    const sheet = await waitFor(() => { const found = document.querySelector<HTMLElement>('[data-panel-sheet]'); expect(found).not.toBeNull(); return found!; });
    expect([foot(sheet).previousElementSibling?.getAttribute('data-slot'), footLinks(sheet).map(link => link.getAttribute('aria-label'))])
      .toEqual(['scroll-area', ['GitHub', 'Discord', 'Send feedback']]);
    expect(menuRows(await settings(sheet))).toEqual(['Telemetry', 'System', 'Light', 'Dark']);
  } finally { phone.restore(); cleanup(); }
});

it('has no foot where the host hands nothing for it, nor under no file viewer', async () => {
  const bare = page({ width: 1200, links: false });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    expect([document.querySelector('[data-app-foot]'), screen.queryByRole('button', { name: 'Settings' })]).toEqual([null, null]);
  } finally { bare.restore(); cleanup(); }
  render(<ModelLibrary library={library([model('a.step')])} />);
  await screen.findByRole('button', { name: 'Open a.step' });
  expect([document.querySelector('[data-app-foot]'), screen.getByRole('navigation', { name: 'Places' }) !== null]).toEqual([null, true]);
});

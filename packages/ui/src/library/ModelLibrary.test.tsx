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
import { DOCUMENT_KINDS, PLACE_ROWS, below, documentKind, kindChips, sortDocuments } from '../../dist/library/ModelLibrary.js';
import { DOCUMENT_TYPE_REGISTRY } from '@cad/core/lib/documentTypes.generated.js';
import type { LibraryModel, LibraryNavigation, LibraryProject, ModelLibrarySource } from './ModelLibrary.js';

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

it('starts with its bar (Home at the left, the search at the right), its places at the left, and the place on screen under its heading row, with no wordmark or links (the app menu\'s)', async () => {
  render(<ModelLibrary library={library([])} onLayoutChange={() => {}} onSortChange={() => {}} />);
  await screen.findByText('Nothing here yet');
  // With no navbar over it, the page's own bar: Home, the page's heading, and the search.
  const bar = document.querySelector('.cad-library-bar')!;
  expect(bar.querySelector('h1')?.textContent).toBe('Home');
  expect([...bar.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label'))).toEqual(['Search models']);
  // The search keeps its placeholder; every control is the scale's control (28px), its icons 16px.
  expect(screen.getByRole('searchbox', { name: 'Search models' }).getAttribute('placeholder')).toBe('Search');
  expect(screen.getByRole('searchbox', { name: 'Search models' }).className).toContain('h-control');
  // The place on screen: its name, the page's one larger text, then Sort and the grid/list segmented control at the row's right.
  const main = screen.getByRole('main', { name: 'CAD models' });
  const row = main.firstElementChild!;
  expect(row.querySelector('h2')?.textContent).toBe('Recents');
  expect([...row.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label'))).toEqual(['Sort by Last activity', 'Grid', 'List']);
  // Grid and List are one segmented control: two control-tall toggles on one track.
  expect(screen.getByRole('group', { name: 'Layout' }).hasAttribute('data-segmented-control')).toBe(true);
  expect(['Grid', 'List'].map(name => screen.getByRole('button', { name }).className.includes('h-control'))).toEqual([true, true]);
  // No count; the one picture is the welcome's C mark.
  expect(row.querySelector('.cad-library-count')).toBeNull();
  expect([...main.querySelectorAll('img')].map(image => Boolean(image.closest('[data-library-empty]')))).toEqual([true]);
  // Its one navigation is its places; a host with no addresses has no link anywhere.
  expect(screen.getAllByRole('navigation').map(node => node.getAttribute('aria-label'))).toEqual(['Places']);
  expect(screen.queryByRole('link')).toBeNull();
});

it('ends its bar in Import where the host has a chooser -- a file, or a folder opened as a project -- counted, and none where it has not', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const pick = vi.fn(async () => {});
  const importFolder = vi.fn(async () => null);
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={library([], { pick, importFolder })} onLayoutChange={() => {}} /></ControlUsageProvider>);
  await screen.findByText('Nothing here yet');
  const row = document.querySelector('.cad-library-bar')!;
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

it('opens and pins through the host, and with nothing yet says how a file gets here', async () => {
  render(<ModelLibrary library={library([])} onLayoutChange={() => {}} />);
  // The toolbar keeps its search and layout switch with nothing to list yet; the page welcomes: the
  // title, one line, and no Import where the host has no chooser.
  expect(await screen.findByRole('heading', { name: 'Nothing here yet' })).toBeTruthy();
  expect(screen.getByText('Import a file or a folder, or ask your agent to build a model.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Import file' })).toBeNull();
  expect(screen.getByRole('searchbox', { name: 'Search models' })).toBeTruthy();
  expect(screen.getByRole('group', { name: 'Layout' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Import', exact: true })).toBeNull();
  cleanup();

  const inPlace = library([model('a.step'), model('b.stl', { missing: true })]);
  render(<ModelLibrary library={inPlace} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  expect((screen.getByRole('button', { name: 'Open b.stl' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Open b.stl' }).textContent).toContain('File unavailable');
  await act(async () => { fireEvent.click(open); });
  expect(inPlace.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'a.step' }));
  // Pin is the card's menu's. The list is by last activity, and the host's own order (its pinned first) where two tie.
  await act(async () => { fireEvent.click(within(await menu('b.stl')).getByRole('menuitem', { name: 'Pin' })); });
  expect(inPlace.change).toHaveBeenLastCalledWith('pin', expect.objectContaining({ name: 'b.stl' }));
  const files = within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem');
  expect(files.map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'))).toEqual(['Open b.stl', 'Open a.step']);
  // Each card has its pin by its ⋯ (Figma's star), pressed while it is pinned; its menu offers Unpin.
  expect(within(files[0]).getByRole('button', { name: 'Unpin' }).getAttribute('aria-pressed')).toBe('true');
  expect(within(files[1]).getByRole('button', { name: 'Pin' }).getAttribute('aria-pressed')).toBe('false');
  await act(async () => { fireEvent.click(within(files[1]).getByRole('button', { name: 'Pin' })); });
  expect(inPlace.change).toHaveBeenLastCalledWith('pin', expect.objectContaining({ name: 'a.step' }));
  cleanup();
  render(<ModelLibrary library={library([model('b.stl', { pinned: true })])} />);
  await screen.findByRole('button', { name: 'Open b.stl' });
  expect(items(await menu('b.stl'))).toEqual(['Open', 'Unpin', 'Delete']);
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
  expect(screen.getByRole('list', { name: 'Files' }).className).toContain('cad-library-list');
  // A row has the card's one menu.
  expect(screen.getByRole('button', { name: 'Actions for bracket.step' })).toBeTruthy();
});

it('lists rows under a Name, Kind, Size, Updated and Created header: each its picture and name, its kind and size, then both ages with no verb, its pin and ⋯ at its end', async () => {
  const hour = 3600, now = Date.now() / 1000;
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  render(<ModelLibrary library={library([
    model('plate.step', { opened: now - 5 * hour, updated: now - 30 * hour, created: now - 3 * 86400, size: 89_000 }),
    model('arm', { path: id, kind: 'model', script: '/work/parts/arm.py', opened: null, updated: now - 2 * hour, created: now - 2 * hour }),
    model('gone.step', { missing: true, updated: null, opened: now - 3 * 86400, created: null }),
  ])} layout="list" onLayoutChange={() => {}} />);
  await screen.findByRole('button', { name: 'Open plate.step' });
  const list = screen.getByRole('list', { name: 'Files' });
  // The header row is the columns' labels, for the eye: each row names itself.
  const header = list.previousElementSibling!;
  expect([header.getAttribute('aria-hidden'), [...header.children].map(cell => cell.textContent)]).toEqual(['true', ['Name', 'Kind', 'Size', 'Updated', 'Created']]);
  const cells = (name: string) => {
    const row = screen.getByRole('button', { name: `Open ${name}` });
    return [Boolean(row.querySelector('.cad-library-name > .cad-library-thumbnail')), row.querySelector('.cad-library-label')?.textContent,
      ...[...row.querySelectorAll('[data-column]')].map(cell => [cell.getAttribute('data-column'), cell.textContent])];
  };
  expect(cells('plate.step')).toEqual([true, 'plate.step', ['kind', 'STEP'], ['size', '87 KB'], ['updated', '1d ago'], ['created', '3d ago']]);
  // A model built from code is Code with no size; its Created is its first run's; a record from before the time was kept
  // has an empty Created, and a file that is gone says so where its time on disk was.
  expect(cells('arm')).toEqual([true, 'arm', ['kind', 'Code'], ['size', '—'], ['updated', '2h ago'], ['created', '2h ago']]);
  expect(cells('gone.step')).toEqual([true, 'gone.step', ['kind', 'STEP'], ['size', '—'], ['updated', 'File unavailable'], ['created', '']]);
  // A row's picture has no badge: its Kind says it. Its pin and ⋯ follow its button, at its end.
  expect(list.querySelector('.cad-library-format')).toBeNull();
  const row = screen.getByRole('button', { name: 'Open plate.step' }).closest('li')!;
  expect(within(row).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Open plate.step', 'Pin', 'Actions for plate.step']);
});

it('gives each card one menu: Open, a file\'s Copy path and Reveal where the host can, Pin, then Delete; a model has no path to offer', async () => {
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const copied: string[] = [], revealed: string[] = [], linked: unknown[] = [];
  const fileActions = { platform: 'darwin' as const, perform: { 'copy-path': ({ path }: { path: string }) => { copied.push(path); },
    'copy-link': (entry: unknown) => { linked.push(entry); }, reveal: ({ path }: { path: string }) => { revealed.push(path); } } };
  const source = library([model('bracket.step'), model('arm', { path: id, kind: 'model', script: '/work/parts/arm.py' })]);
  const shown = async (name: string) => {
    cleanup();
    render(<ModelLibrary library={source} fileActions={fileActions} />);
    await screen.findByRole('button', { name: `Open ${name}` });
    return menu(name);
  };
  let open = await shown('bracket.step');
  expect(items(open)).toEqual(['Open', 'Copy path', 'Copy link', 'Reveal in Finder', 'Pin', 'Delete']);
  // Delete is the last, after a rule, and destructive.
  expect(open.querySelector('[role=separator]')?.nextElementSibling?.textContent).toBe('Delete');
  expect(within(open).getByRole('menuitem', { name: 'Delete' }).getAttribute('data-variant')).toBe('destructive');
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Copy path' })); });
  expect(copied).toEqual(['/work/parts/bracket.step']);
  // A model is no file: it is not tied to the script it was built from. Its page is: Copy link,
  // by its document's id.
  open = await shown('arm');
  expect(items(open)).toEqual(['Open', 'Copy link', 'Pin', 'Delete']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Copy link' })); });
  expect(linked).toEqual([expect.objectContaining({ path: id, kind: 'file' })]);
  open = await shown('bracket.step');
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Reveal in Finder' })); });
  expect(revealed).toEqual(['/work/parts/bracket.step']);
  open = await shown('bracket.step');
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open' })); });
  expect(source.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'bracket.step' }));
  cleanup();
  // A host that can do nothing with a file on disk offers neither.
  render(<ModelLibrary library={library([model('bracket.step')])} />);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  expect(items(await menu('bracket.step'))).toEqual(['Open', 'Pin', 'Delete']);
});

it('marks each card with its kind\'s glyph, and narrows the place to one kind with a chip: All first, then each kind it holds, with its count', async () => {
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const source = library([model('bracket.step'), model('arm', { path: id, kind: 'model', script: '/work/parts/arm.py' }), model('plate.dxf'),
    model('blinky.kicad_pcb'), model('arm.stl')]);
  const names = () => within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem').map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'));
  const chips = () => within(screen.getByRole('group', { name: 'Show' })).getAllByRole('button')
    .map(chip => [chip.getAttribute('aria-label'), chip.getAttribute('aria-pressed')]);
  render(<ModelLibrary library={source} onSortChange={() => {}} />);
  const arm = await screen.findByRole('button', { name: 'Open arm' });
  expect(arm.querySelector('[data-glyph]')?.getAttribute('data-glyph')).toBe('model');
  expect(screen.getByRole('button', { name: 'Open bracket.step' }).querySelector('[data-glyph]')?.getAttribute('data-glyph')).toBe('file');
  // A row of pills of its own, under the heading row: a model and the files exported from it are 3D models alike.
  const row = screen.getByRole('group', { name: 'Show' });
  expect([row.previousElementSibling?.classList.contains('cad-library-toolbar'), row.closest('.cad-library-toolbar')]).toEqual([true, null]);
  expect(chips()).toEqual([['All, 5', 'true'], ['3D models, 3', 'false'], ['Drawings, 1', 'false'], ['Boards, 1', 'false']]);
  expect(within(row).getAllByRole('button').map(chip => [chip.textContent, chip.className.includes('h-control')]))
    .toEqual([['AllAll5', true], ['3D models3D models3', true], ['DrawingsDrawings1', true], ['BoardsBoards1', true]]);
  fireEvent.click(screen.getByRole('button', { name: '3D models, 3' }));
  expect(names()).toEqual(['Open bracket.step', 'Open arm', 'Open arm.stl']);
  expect(chips().map(([, pressed]) => pressed)).toEqual(['false', 'true', 'false', 'false']);
  fireEvent.click(screen.getByRole('button', { name: 'Boards, 1' }));
  expect(names()).toEqual(['Open blinky.kicad_pcb']);
  // A search and the chip narrow together, and the counts follow the search: of the place before the chip.
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'arm' } });
  expect(chips()).toEqual([['All, 2', 'false'], ['3D models, 2', 'false'], ['Drawings, 0', 'false'], ['Boards, 0', 'true']]);
  expect(screen.getByRole('main').querySelector('.cad-library-empty')?.textContent).toBe('No matching models.');
  fireEvent.click(screen.getByRole('button', { name: '3D models, 2' }));
  expect(names()).toEqual(['Open arm', 'Open arm.stl']);
  fireEvent.click(screen.getByRole('button', { name: 'All, 2' }));
  expect(names()).toEqual(['Open arm', 'Open arm.stl']);
  cleanup();
  // With one kind alone there is nothing to tell apart: no chips. A model and its STEP are one kind.
  render(<ModelLibrary library={library([model('bracket.step'), model('arm', { path: id, kind: 'model' })])} />);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  expect(screen.queryByRole('group', { name: 'Show' })).toBeNull();
});

it('offers a place\'s own kinds, and shows all of a place that lacks the kind chosen in another', async () => {
  const projects = [
    { ...project('p1', 'tag', 0), documents: [model('tag.step', { project: 'p1' }), model('tag.dxf', { project: 'p1' }), model('tag.urdf', { project: 'p1' })] },
    { ...project('p2', 'gear', 0), documents: [model('gear.step', { project: 'p2' }), model('gear.kicad_sch', { project: 'p2' })] },
    { ...project('p3', 'lone', 2) },
  ];
  const source = library([], { projects: async () => projects });
  const chips = () => [...document.querySelectorAll('[data-library-kinds] button')].map(chip => chip.getAttribute('aria-label'));
  const view = render(<ModelLibrary library={source} place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open tag.step' });
  expect(chips()).toEqual(['All, 3', '3D models, 1', 'Drawings, 1', 'Robots, 1']);
  fireEvent.click(screen.getByRole('button', { name: 'Robots, 1' }));
  expect(opens()).toEqual(['Open tag.urdf']);
  // The choice is the page's own, as the place is: a place without robots shows all of its own.
  view.rerender(<ModelLibrary library={source} place={{ view: 'project', project: 'p2' }} />);
  await screen.findByRole('button', { name: 'Open gear.step' });
  expect(chips()).toEqual(['All, 2', '3D models, 1', 'Schematics, 1']);
  expect(screen.getByRole('button', { name: 'All, 2' }).getAttribute('aria-pressed')).toBe('true');
  expect(opens()).toEqual(['Open gear.step', 'Open gear.kicad_sch']);
  // One of one kind: no chips.
  view.rerender(<ModelLibrary library={source} place={{ view: 'project', project: 'p3' }} />);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect(chips()).toEqual([]);
  // Back where robots are, the choice holds.
  view.rerender(<ModelLibrary library={source} place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open tag.urdf' });
  expect(opens()).toEqual(['Open tag.urdf']);
});

it('knows every document type and every extension the viewer opens as a kind, by the row\'s type first and its file\'s extension else', () => {
  // Every type the registry has, as a row names it, and each of its files' extensions; and a glTF, which opens as a GLB.
  const types = DOCUMENT_TYPE_REGISTRY.documentTypes;
  const missing = [
    ...types.filter((type: { wire: string }) => !documentKind(model('x', { kind: 'file', documentKind: type.wire, path: '/w/x' }))).map((type: { wire: string }) => type.wire),
    ...[...types.flatMap((type: { extensions: string[] }) => type.extensions), '.gltf'].filter(extension => !documentKind(model(`x${extension}`))),
  ];
  expect(missing).toEqual([]);
  expect(DOCUMENT_KINDS).toEqual(['models', 'drawings', 'boards', 'schematics', 'robots']);
  expect(['a.STEP', 'a.stp', 'a.3mf', 'a.xbf', 'a.glb', 'a.dxf', 'a.kicad_pcb', 'a.kicad_sch', 'a.urdf', 'a.srdf'].map(name => documentKind(model(name))))
    .toEqual(['models', 'models', 'models', 'models', 'models', 'drawings', 'boards', 'schematics', 'robots', 'robots']);
  // A document built from code is a 3D model, whatever it is named; a row's type wins over its name; a file the viewer
  // does not open is no kind (All alone lists it).
  expect(documentKind(model('plate.dxf', { kind: 'model' }))).toBe('models');
  expect(documentKind(model('board', { documentKind: 'kicad_pcb' }))).toBe('boards');
  expect(documentKind(model('notes.txt'))).toBeNull();
  expect(kindChips([model('a.step'), model('notes.txt')], '')).toEqual([]);
  expect(kindChips([model('a.step'), model('b.dxf'), model('notes.txt')], '')).toEqual([{ kind: 'all', count: 3 }, { kind: 'models', count: 1 }, { kind: 'drawings', count: 1 }]);
});

it('gives every model of a script its own card and row, each opening itself, with nothing folded', async () => {
  const ids = ['0', '1', '2'].map(digit => `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f1${digit}`);
  const script = '/work/juno/juno.py';
  const models = [
    model('wheel', { path: ids[0], kind: 'model', script, updated: 30 }),
    model('juno', { path: ids[1], kind: 'model', script, updated: 10 }),
    model('axle', { path: ids[2], kind: 'model', script, updated: 20 }),
    model('bracket.step'),
  ];
  const names = () => within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem').map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'));
  for (const layout of ['grid', 'list'] as const) {
    const source = library(models);
    render(<ModelLibrary library={source} layout={layout} />);
    await screen.findByRole('button', { name: 'Open juno' });
    expect(names()).toEqual(['Open bracket.step', 'Open wheel', 'Open axle', 'Open juno']);
    expect(screen.queryByRole('button', { name: /more$/ })).toBeNull();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open axle' })); });
    expect(source.open).toHaveBeenLastCalledWith(expect.objectContaining({ name: 'axle' }));
    // A search finds the model it names, alone.
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'axle' } });
    expect(names()).toEqual(['Open axle']);
    cleanup();
  }
});

it('asks before Delete, in words that say what stays on disk, and the card leaves at once', async () => {
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const bracket = model('bracket', { path: id, kind: 'model', script: '/work/parts/bracket.py' });
  let settle!: () => void;
  const source = library([bracket, model('bracket.step')], {
    change: vi.fn(() => new Promise<readonly LibraryModel[]>(resolve => { settle = () => resolve([model('bracket.step')]); })),
  });
  render(<ModelLibrary library={source} />);
  await screen.findByRole('button', { name: 'Open bracket' });
  await act(async () => { fireEvent.click(within(await menu('bracket')).getByRole('menuitem', { name: 'Delete' })); });
  const dialog = await screen.findByRole('alertdialog');
  expect(within(dialog).getByRole('heading').textContent).toBe('Delete bracket?');
  expect(within(dialog).getByText("Removes the engine's record and its saved build. The script and any exported files stay on disk. Run the script to build it again.")).toBeTruthy();
  expect(within(dialog).getAllByRole('button').map(button => button.textContent)).toEqual(['Cancel', 'Delete']);
  // Cancel deletes nothing.
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' })); });
  expect(screen.queryByRole('alertdialog')).toBeNull();
  expect(source.change).not.toHaveBeenCalled();
  cleanup();
  render(<ModelLibrary library={source} />);
  await screen.findByRole('button', { name: 'Open bracket' });
  await act(async () => { fireEvent.click(within(await menu('bracket')).getByRole('menuitem', { name: 'Delete' })); });
  await act(async () => { fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' })); });
  // Deleted through the client, and gone from the list before it answers.
  expect(source.change).toHaveBeenCalledWith('delete', expect.objectContaining({ path: id }));
  expect(screen.queryByRole('button', { name: 'Open bracket' })).toBeNull();
  await act(async () => { settle(); });
  expect(screen.queryByRole('button', { name: 'Open bracket' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Open bracket.step' })).toBeTruthy();
});

it('asks to delete a file from the viewer alone, and one model of a script alone', async () => {
  const file = library([model('bracket.step')]);
  render(<ModelLibrary library={file} />);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  await act(async () => { fireEvent.click(within(await menu('bracket.step')).getByRole('menuitem', { name: 'Delete' })); });
  let dialog = await screen.findByRole('alertdialog');
  expect(within(dialog).getByRole('heading').textContent).toBe('Delete bracket.step from the viewer?');
  expect(within(dialog).getByText("Removes the engine's record of this file. The file itself stays on disk.")).toBeTruthy();
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' })); });
  expect(file.change).toHaveBeenCalledWith('remove', expect.objectContaining({ name: 'bracket.step' }));
  cleanup();
  const script = '/work/juno/juno.py';
  const ids = ['0', '1', '2'].map(digit => `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f1${digit}`);
  const models = [model('juno', { path: ids[0], kind: 'model', script }), model('wheel', { path: ids[1], kind: 'model', script }),
    model('axle', { path: ids[2], kind: 'model', script })];
  const juno = library(models, { change: vi.fn(async (_action, item) => models.filter(entry => entry.path !== item.path)) });
  render(<ModelLibrary library={juno} />);
  await screen.findByRole('button', { name: 'Open wheel' });
  await act(async () => { fireEvent.click(within(await menu('wheel')).getByRole('menuitem', { name: 'Delete' })); });
  dialog = await screen.findByRole('alertdialog');
  expect(within(dialog).getByRole('heading').textContent).toBe('Delete wheel?');
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' })); });
  await waitFor(() => expect(juno.change).toHaveBeenCalledTimes(1));
  expect((juno.change as ReturnType<typeof vi.fn>).mock.calls.map(([action, item]) => [action, item.name])).toEqual([['delete', 'wheel']]);
  // The script's other models stay.
  expect(screen.getByRole('button', { name: 'Open juno' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Open wheel' })).toBeNull();
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

it('shows a model by its run and a file by its opening, whichever came last, each with its verb', async () => {
  const hour = 3600, now = Date.now() / 1000;
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  render(<ModelLibrary library={library([
    model('arm', { path: id, kind: 'model', opened: null, updated: now - 2 * hour }),
    model('plate.step', { opened: now - 5 * hour, updated: now - 30 * hour }),
  ])} />);
  expect((await screen.findByRole('button', { name: 'Open arm' })).textContent).toBe('CodearmEdited 2h ago');
  expect(screen.getByRole('button', { name: 'Open plate.step' }).textContent).toBe('STEPplate.stepViewed 5h ago');
});

it('shows why an open failed where the library shows it', async () => {
  const failing = library([model('a.step')], { open: async () => { throw new Error('That model is gone.'); } });
  render(<ModelLibrary library={failing} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  await act(async () => { fireEvent.click(open); });
  expect((await screen.findByRole('alert')).textContent).toBe('That model is gone.');
});

it('asks for a picture of each card on screen that has none or an old one, one at a time, and reads the list again once one is kept', async () => {
  const edited = Date.now() / 1000 - 60;
  let models = [
    model('new.step', { updated: edited + 10 }),
    model('current.step', { thumbnail: 'current.png', pictured: edited + 30, updated: edited }),
    model('old.step', { thumbnail: 'old.png', pictured: edited - 3600, updated: edited - 10 }),
    model('gone.step', { missing: true }),
  ];
  const list = vi.fn(async () => models);
  let finish!: (kept: boolean) => void;
  const picture = vi.fn(() => new Promise<boolean>(resolve => { finish = resolve; }));
  render(<ModelLibrary library={library(models, { list })} picture={picture} />);
  await screen.findByRole('button', { name: 'Open new.step' });
  // The first, alone: the next waits for it.
  await waitFor(() => expect(picture.mock.calls.map(([item]) => item.name)).toEqual(['new.step']));
  models = models.map(item => item.name === 'new.step' ? { ...item, thumbnail: 'new.png', pictured: Date.now() / 1000 } : item);
  await act(async () => finish(true));
  expect(list).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(picture.mock.calls.map(([item]) => item.name)).toEqual(['new.step', 'old.step']));
  // One not drawn is not asked for again while the page is up; the current and the missing never are.
  await act(async () => finish(false));
  expect(picture).toHaveBeenCalledTimes(2);
  expect(list).toHaveBeenCalledTimes(2);
});

// The home stays up while an agent rebuilds a model it lists: the card is pictured again.
it('pictures a card again when it is updated while the home is up', async () => {
  const edited = Date.now() / 1000 - 60;
  let models = [model('plate.step', { thumbnail: 'plate.png', pictured: edited + 30, updated: edited })];
  const list = vi.fn(async () => models);
  const picture = vi.fn(async () => true);
  render(<ModelLibrary library={library(models, { list })} picture={picture} />);
  await screen.findByRole('button', { name: 'Open plate.step' });
  expect(picture).not.toHaveBeenCalled();
  models = [{ ...models[0], updated: edited + 60 }];
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
  await waitFor(() => expect(picture.mock.calls.map(([item]) => item.updated)).toEqual([edited + 60]));
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

it("counts what a person does on the home by name: a kind chosen, a search begun, a card opened, a delete cancelled and one confirmed", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const script = '/work/juno/juno.py';
  const ids = ['0', '1'].map(digit => `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f1${digit}`);
  const source = library([model('juno', { path: ids[0], kind: 'model', script, updated: 10 }),
    model('wheel', { path: ids[1], kind: 'model', script, updated: 5 }), model('bracket.dxf')]);
  // A kind chosen by its chip, each by its name; the one already on is no use.
  const choose = async (...chips: string[]) => {
    const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
    await screen.findByRole('button', { name: 'Open juno' });
    for (const chip of chips) fireEvent.click(screen.getByRole('button', { name: chip }));
    view.unmount();
    cleanup();
  };
  await choose('Drawings, 1', 'Drawings, 1', '3D models, 2', 'All, 3', 'All, 3');
  expect(reported(reports)).toEqual({ home_kind_drawings: 1, home_kind_models: 1, home_kind_all: 1 });
  reports.length = 0;
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open juno' });
  const search = screen.getByRole('searchbox', { name: 'Search models' });
  for (const value of ['b', 'br', '']) fireEvent.change(search, { target: { value } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open bracket.dxf' })); });
  await act(async () => { fireEvent.click(within(await menu('bracket.dxf')).getByRole('menuitem', { name: 'Delete' })); });
  await act(async () => { fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' })); });
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, count }) => [control, count]));
  expect(said).toEqual({ home_search: 1, home_open: 1, home_delete_cancel: 1 });
  // A delete the person confirms is counted as one.
  cleanup();
  reports.length = 0;
  const again = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open bracket.dxf' });
  await act(async () => { fireEvent.click(within(await menu('bracket.dxf')).getByRole('menuitem', { name: 'Delete' })); });
  await act(async () => { fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' })); });
  again.unmount();
  expect(reports.flat()).toEqual([{ control: 'home_delete', count: 1, seconds: 0 }]);
});

it('counts the pin, from its button or the menu, the grid/list switch, and Copy path, Copy link and Reveal', async () => {
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
  await act(async () => { fireEvent.click(within(bracket).getByRole('button', { name: 'Pin' })); });
  // The layout chosen, then the one already on (no use), then the other.
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  fireEvent.click(screen.getByRole('button', { name: 'Grid' }));
  await act(async () => { fireEvent.click(within(await menu('bracket.step')).getByRole('menuitem', { name: 'Copy path' })); });
  view.unmount();
  cleanup();
  // A menu each render (jsdom): Reveal, then Unpin from the menu.
  for (const item of ['Copy link', 'Reveal in Finder', 'Unpin']) {
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
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const source = library([model('video.kicad_pcb', { thumbnail: 'light.png', pictured: Date.now() / 1000 }),
    model('plate.dxf', { thumbnail: 'plate.png', pictured: Date.now() / 1000 }), model('arm', { path: id, kind: 'model' })], { thumbnail });
  const home = (colorScheme: 'light' | 'dark') => <ViewerHostContext.Provider value={{ environment: { colorScheme } } as any}><ModelLibrary library={source} /></ViewerHostContext.Provider>;
  const view = render(home('dark'));
  const picture = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).closest('.cad-library-card')!.querySelector('.cad-library-thumbnail')!;
  await waitFor(() => expect(picture('video.kicad_pcb').querySelector('img')?.getAttribute('src')).toBe('data:video.kicad_pcb:light.png'));
  await waitFor(() => expect(picture('plate.dxf').querySelector('img')?.getAttribute('src')).toBe('data:plate.dxf:plate.png'));
  view.rerender(home('light'));
  expect(picture('video.kicad_pcb').querySelector('img')?.getAttribute('src')).toBe('data:video.kicad_pcb:light.png');
  expect(thumbnail.mock.calls.every(call => call.length === 1)).toBe(true);
  expect(['video.kicad_pcb', 'plate.dxf'].map(name => [picture(name).hasAttribute('data-drawing'), picture(name).hasAttribute('data-thumbnail-variant')])).toEqual([[false, false], [false, false]]);
  expect(['video.kicad_pcb', 'plate.dxf', 'arm'].map(name => picture(name).querySelector('.cad-library-format')?.textContent)).toEqual(['KiCad PCB', 'DXF', 'Code']);
});

// A file's size, the server's, goes before its age; a model has none.
it("says a file's size before its age, and a model's age alone", async () => {
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const now = Date.now() / 1000;
  render(<ModelLibrary library={library([model('plate.step', { opened: now - 5 * 3600, updated: now - 30 * 3600, size: 1_700_000 }),
    model('tiny.stl', { opened: now - 5 * 3600, updated: now - 30 * 3600, size: 900 }), model('arm', { path: id, kind: 'model', opened: null, updated: now - 2 * 3600 })])} />);
  const status = async (name: string) => (await screen.findByRole('button', { name: `Open ${name}` })).querySelector('.cad-library-status')!.textContent;
  expect([await status('plate.step'), await status('tiny.stl'), await status('arm')]).toEqual(['1.6 MB · Viewed 5h ago', '900 B · Viewed 5h ago', 'Edited 2h ago']);
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Home');
});

// A project as the host lists it: `models` models, then `files` files in its folder that no page has opened.
const project = (id: string, name: string, files: number, models = 0, extra: Partial<LibraryProject> = {}): LibraryProject => ({
  id, name, root: `/Users/sam/cad/${name}`, opened: 1, missing: false,
  documents: [
    ...Array.from({ length: models }, (_, index) => model(`${name}_model_${index}`, { path: `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f${String(index).padStart(2, '0')}`,
      id: `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f${String(index).padStart(2, '0')}`, kind: 'model', project: id, opened: null,
      script: `/Users/sam/cad/${name}/src/${name}.py`, folder: `/Users/sam/cad/${name}/src` })),
    ...Array.from({ length: files }, (_, index) => model(`part_${index}.stl`, { path: `/Users/sam/cad/${name}/STL/part_${index}.stl`, id: `file-${id}-${index}`,
      folder: `/Users/sam/cad/${name}/STL`, project: id, opened: null, created: null })),
  ],
  ...extra,
});
// The place's documents, by their press targets' names (a button's or a link's), in order.
const opens = () => [...document.querySelectorAll('.cad-library-open[aria-label]')].map(node => node.getAttribute('aria-label'));
const place = (key: string) => document.querySelector<HTMLElement>(`[data-place="${key}"]`)!;
const reported = (reports: { control: string; count: number }[][]) => reports.flat().reduce<Record<string, number>>((sums, { control, count }) =>
  ({ ...sums, [control]: (sums[control] ?? 0) + count }), {});

it('lists its places in a sidebar: Recents, Pinned with its count, each project with its count, then Standalone, the one on screen marked', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const tag = project('p1', 'heart-tag', 9, 2), lamp = project('p2', 'lamp', 0, 0, { missing: true });
  const recents = [model('opened.stl', { path: '/Users/sam/cad/heart-tag/STL/part_0.stl', project: 'p1', pinned: true }), model('loose.step'), model('other.stl', { pinned: true })];
  const places: unknown[] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library(recents, { projects: async () => [tag, lamp] })} home="/Users/sam" onPlaceChange={next => places.push(next)} />
  </ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open loose.step' });
  const sidebar = screen.getByRole('navigation', { name: 'Places' });
  // The panel's surface (the viewer's own, docked) and its rows: a glyph, the name, its count on the right; none where there is nothing to count.
  expect([sidebar.closest('aside')!.getAttribute('data-panel-surface'), sidebar.closest('aside')!.getAttribute('aria-label')]).toEqual(['docked', 'Sidebar']);
  const rows = [...sidebar.querySelectorAll<HTMLElement>('[data-place]')];
  expect(rows.map(row => [row.getAttribute('data-place'), row.textContent, row.hasAttribute('data-tree-row'), row.querySelectorAll('svg').length]))
    .toEqual([['recents', 'Recents', true, 1], ['pinned', 'Pinned2', true, 1], ['project:p1', 'heart-tag11', true, 1], ['project:p2', 'lamp', true, 1], ['standalone', 'Standalone2', true, 1]]);
  expect(within(sidebar).getByRole('heading', { level: 2 }).textContent).toBe('Projects');
  // A host with no addresses: every row a button. The one on screen is marked and said; a project whose folder is gone is muted.
  expect(rows.map(row => [row.tagName, row.getAttribute('aria-current')])).toEqual([['BUTTON', 'page'], ['BUTTON', null], ['BUTTON', null], ['BUTTON', null], ['BUTTON', null]]);
  expect([place('project:p2').hasAttribute('data-missing'), place('project:p2').className.includes('text-muted-foreground')]).toEqual([true, true]);
  // Recents: every document opened lately, across projects.
  expect(opens()).toEqual(['Open opened.stl', 'Open loose.step', 'Open other.stl']);
  // A press shows the place: its name is the heading, its row the marked one, and the host hears of it.
  await act(async () => { fireEvent.click(place('pinned')); });
  expect([screen.getByRole('main').querySelector('h2')?.textContent, place('pinned').getAttribute('aria-current'), place('recents').getAttribute('aria-current')])
    .toEqual(['Pinned', 'page', null]);
  expect(opens()).toEqual(['Open opened.stl', 'Open other.stl']);
  await act(async () => { fireEvent.click(place('standalone')); });
  expect(opens()).toEqual(['Open loose.step', 'Open other.stl']);
  await act(async () => { fireEvent.click(place('project:p1')); });
  expect(opens()).toHaveLength(11);
  await act(async () => { fireEvent.click(place('project:p1')); });  // the place on screen: no move
  await act(async () => { fireEvent.click(place('recents')); });
  expect(places).toEqual([{ view: 'pinned' }, { view: 'standalone' }, { view: 'project', project: 'p1' }, { view: 'recents' }]);
  // Up and Down move between the rows, Home and End to the first and the last.
  place('recents').focus();
  fireEvent.keyDown(place('recents'), { key: 'ArrowDown' });
  expect(document.activeElement).toBe(place('pinned'));
  fireEvent.keyDown(place('pinned'), { key: 'End' });
  expect(document.activeElement).toBe(place('standalone'));
  fireEvent.keyDown(place('standalone'), { key: 'ArrowUp' });
  expect(document.activeElement).toBe(place('project:p2'));
  view.unmount();
  expect(reported(reports)).toEqual({ home_place_pinned: 1, home_place_standalone: 1, home_place_project: 1, home_place_recents: 1 });
});

it("shows the place the host names, and tells the host its name as the person reads it", async () => {
  const names: string[] = [];
  const source = library([model('loose.step')], { projects: async () => [project('p1', 'heart-tag', 2, 1)] });
  const home = (at: Parameters<typeof ModelLibrary>[0]['place']) => <ModelLibrary library={source} place={at} onPlaceShown={name => names.push(name)} home="/Users/sam" />;
  const view = render(home({ view: 'project', project: 'p1' }));
  // Until the projects are read, the project's page waits where its documents will be.
  expect(screen.getByRole('list', { name: 'Files' }).getAttribute('aria-busy')).toBe('true');
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([place('project:p1').getAttribute('aria-current'), screen.getByRole('main').querySelector('h2')?.textContent]).toEqual(['page', 'heart-tag']);
  view.rerender(home({ view: 'standalone' }));
  expect(opens()).toEqual(['Open loose.step']);
  view.rerender(home({ view: 'pinned' }));
  // Nothing pinned: its row has no count, and its page says how a document gets there.
  expect(place('pinned').textContent).toBe('Pinned');
  expect(screen.getByText('Nothing pinned yet. Pin a document to keep it here.')).toBeTruthy();
  expect(names).toEqual(['Project', 'heart-tag', 'Standalone', 'Pinned']);
});

it("gives a project a page of its own: its name, its folder from the home folder and its menu, then every one of its documents, each saying where it is", async () => {
  const tag = project('p1', 'heart-tag', 9, 2, { truncated: true });
  render(<ModelLibrary library={library([], { projects: async () => [tag] })} home="/Users/sam" place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  const heading = screen.getByRole('main').firstElementChild!;
  expect([heading.querySelector('h2')?.textContent, heading.querySelector('.cad-library-path')?.textContent, Boolean(heading.querySelector('svg.lucide-folder'))])
    .toEqual(['heart-tag', '~/cad/heart-tag', true]);
  // All eleven, with no Show all: its models by last activity among its files.
  expect(opens()).toHaveLength(11);
  expect(screen.queryByRole('button', { name: /^Show \d/ })).toBeNull();
  // A card's second line: a model's script under the project's folder; a file's size and age (its folder is the list's).
  const second = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).querySelector('.cad-library-status')?.textContent;
  expect([second('heart-tag_model_0'), second('part_0.stl')]).toEqual(['src/heart-tag.py · Edited 16h ago', 'Edited 16h ago']);
  // A file of the project's that no page opened: no pin, and no Delete (its folder lists it).
  expect(within(screen.getByRole('button', { name: 'Open part_0.stl' }).closest('li')!).queryByRole('button', { name: 'Pin' })).toBeNull();
  expect(items(await menu('part_0.stl'))).toEqual(['Open']);
  // The host's walk of its folder stopped early: said under the last of them.
  expect(screen.getByText('Not every file is listed: this folder holds more than CAD lists at once.')).toBeTruthy();
});

it("adds a Where column to a project's list, a model's script and a file's folder under the project's, and a Project column to Recents and Pinned", async () => {
  const tag = project('p1', 'heart-tag', 1, 1);
  tag.documents = [...tag.documents, model('top.step', { path: '/Users/sam/cad/heart-tag/top.step', folder: '/Users/sam/cad/heart-tag', project: 'p1', opened: null })];
  const source = library([model('loose.step'), { ...tag.documents[0], opened: 5 }], { projects: async () => [tag] });
  const home = (at: Parameters<typeof ModelLibrary>[0]['place']) => <ModelLibrary library={source} layout="list" place={at} />;
  const view = render(home({ view: 'project', project: 'p1' }));
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  const header = () => [...screen.getByRole('list', { name: 'Files' }).previousElementSibling!.children].map(cell => cell.textContent);
  const where = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).querySelector('[data-column=where]')?.textContent;
  expect(header()).toEqual(['Name', 'Where', 'Kind', 'Size', 'Updated', 'Created']);
  // A file in the project's own folder is nowhere under it.
  expect([where('heart-tag_model_0'), where('part_0.stl'), where('top.step')]).toEqual(['src/heart-tag.py', 'STL', '']);
  view.rerender(home({ view: 'recents' }));
  expect(header()).toEqual(['Name', 'Project', 'Kind', 'Size', 'Updated', 'Created']);
  expect([where('heart-tag_model_0'), where('loose.step')]).toEqual(['heart-tag', 'Standalone']);
  // Standalone's documents are in no project: nothing to say.
  view.rerender(home({ view: 'standalone' }));
  expect(header()).toEqual(['Name', 'Kind', 'Size', 'Updated', 'Created']);
  expect(below('/a/b/c.py', '/a/b/')).toBe('c.py');
  expect([below('/a/b', '/a/b'), below('C:\\work\\x\\y.py', 'C:/work'), below('/elsewhere/y.py', '/a/b')]).toEqual(['', 'x/y.py', '/elsewhere/y.py']);
});

it("leads a card's second line with its project's name in Recents and Pinned, where projects are listed", async () => {
  const tag = project('p1', 'heart-tag', 0, 1);
  const source = library([{ ...tag.documents[0], pinned: true }, model('loose.step', { size: 2048, pinned: true })], { projects: async () => [tag] });
  const home = (at: Parameters<typeof ModelLibrary>[0]['place']) => <ModelLibrary library={source} place={at} />;
  const view = render(home({ view: 'recents' }));
  await waitFor(() => expect(place('project:p1')).toBeTruthy());
  const second = (name: string) => screen.getByRole('button', { name: `Open ${name}` }).querySelector('.cad-library-status')?.textContent;
  expect([second('heart-tag_model_0'), second('loose.step')]).toEqual(['heart-tag · Edited 16h ago', 'Standalone · 2 KB · Edited 16h ago']);
  view.rerender(home({ view: 'pinned' }));
  expect([second('heart-tag_model_0'), second('loose.step')]).toEqual(['heart-tag · Edited 16h ago', 'Standalone · 2 KB · Edited 16h ago']);
  view.rerender(home({ view: 'standalone' }));
  expect(second('loose.step')).toBe('2 KB · Edited 16h ago');
});

it('shows the first of a long place, and the rest once its Show more is pressed', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const big = project('p1', 'bolts', PLACE_ROWS + 7);
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library([], { projects: async () => [big] })} place={{ view: 'project', project: 'p1' }} />
  </ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([PLACE_ROWS, opens().length, place('project:p1').textContent]).toEqual([120, 120, 'bolts127']);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Show 7 more' })); });
  expect(opens()).toHaveLength(127);
  expect(screen.queryByRole('button', { name: /^Show \d/ })).toBeNull();
  view.unmount();
  expect(reported(reports)).toEqual({ home_project_more: 1 });
});

it("sorts the place on screen by last activity, by name or by kind, the host keeping the choice", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const documents = [model('b10.step', { updated: 30 }), model('b9.step', { updated: 40, opened: null }), model('arm', { path: id, kind: 'model', updated: 10 }),
    model('Axle.dxf', { updated: 20, pinned: true })];
  const sorts: string[] = [];
  const home = (sort?: 'activity' | 'name' | 'kind') => <ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library(documents)} sort={sort} onSortChange={next => sorts.push(next)} /></ControlUsageProvider>;
  const view = render(home());
  await screen.findByRole('button', { name: 'Open arm' });
  // Last activity, newest first: a pinned document is not first (Pinned is a place of its own).
  expect(opens()).toEqual(['Open b9.step', 'Open b10.step', 'Open Axle.dxf', 'Open arm']);
  const trigger = screen.getByRole('button', { name: 'Sort by Last activity' });
  expect([trigger.textContent, trigger.previousElementSibling?.textContent]).toEqual(['Last activity', 'Sort']);
  await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  const open = await screen.findByRole('menu');
  expect(within(open).getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Last activity', 'true'], ['Name', 'false'], ['Kind', 'false']]);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitemradio', { name: 'Name' })); });
  expect(sorts).toEqual(['name']);
  // By name, as a person counts: 9 before 10, whatever the case.
  view.rerender(home('name'));
  expect(opens()).toEqual(['Open arm', 'Open Axle.dxf', 'Open b9.step', 'Open b10.step']);
  expect(screen.getByRole('button', { name: 'Sort by Name' }).textContent).toBe('Name');
  // By kind: the 3D models (the one built from code first), then the drawings, each kind by format, then by name.
  view.rerender(home('kind'));
  expect(opens()).toEqual(['Open arm', 'Open b9.step', 'Open b10.step', 'Open Axle.dxf']);
  expect(sortDocuments([model('z.step'), model('a.stl'), model('m.dxf'), model('n.urdf'), model('q.kicad_sch'), model('p.kicad_pcb'), model('a.3mf'),
    model('notes.txt'), model('k', { kind: 'model' })], 'kind').map(item => item.name))
    .toEqual(['k', 'a.3mf', 'z.step', 'a.stl', 'm.dxf', 'p.kicad_pcb', 'q.kicad_sch', 'n.urdf', 'notes.txt']);
  view.unmount();
  expect(reported(reports)).toEqual({ home_sort_name: 1 });
  cleanup();
  // A host that keeps no order has no Sort.
  render(<ModelLibrary library={library(documents)} />);
  await screen.findByRole('button', { name: 'Open arm' });
  expect(screen.queryByRole('button', { name: /^Sort/ })).toBeNull();
});

it('narrows the place on screen with a search, and says when nothing matches', async () => {
  const source = library([model('loose.step')], { projects: async () => [project('p1', 'heart-tag', 3), project('p2', 'gear', 2)] });
  render(<ModelLibrary library={source} place={{ view: 'project', project: 'p1' }} />);
  await screen.findByRole('button', { name: 'Open part_2.stl' });
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'part_2' } });
  expect(opens()).toEqual(['Open part_2.stl']);
  // The sidebar's counts are the places', not the search's.
  expect([place('project:p1').textContent, place('project:p2').textContent]).toEqual(['heart-tag3', 'gear2']);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'nothing' } });
  expect(screen.getByRole('main').querySelector('.cad-library-empty')?.textContent).toBe('No matching models.');
});

it("gives a project's page a menu: its folder's Copy path and Reveal, and Remove from CAD, which forgets the project alone, goes to Recents and says so", async () => {
  const perform = { 'copy-path': vi.fn(async () => {}), reveal: vi.fn(async () => {}) };
  let listed = [project('p1', 'heart-tag', 1)];
  const removeProject = vi.fn(async () => { listed = []; return listed; });
  const places: unknown[] = [];
  const source = library([model('loose.step')], { projects: async () => listed, removeProject });
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
  expect(await screen.findByText('heart-tag removed. Nothing on disk changed, and its documents are standalone again.')).toBeTruthy();
  expect([place('project:p1'), place('recents').getAttribute('aria-current'), opens()]).toEqual([null, 'page', ['Open loose.step']]);
  expect(places).toEqual([{ view: 'project', project: 'p1' }, { view: 'recents' }]);
  // The line is that move's: it goes with the next place.
  await act(async () => { fireEvent.click(place('standalone')); });
  expect(screen.queryByText(/heart-tag removed/)).toBeNull();
});

it("goes to the page of the project Import's Folder opened, from the sidebar's + too, and says what came of it", async () => {
  let listed: LibraryProject[] = [];
  const answers = [{ project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: true, folder: '/w/gear' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear/STEP' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear' }];
  // The projects list it a read later than its answer: its page waits for it meanwhile.
  let arrive!: () => void;
  const importFolder = vi.fn(async () => { arrive = () => { listed = [project('p2', 'gear', 1, 0, { root: '/w/gear' })]; }; return answers.shift()!; });
  const places: unknown[] = [];
  render(<ModelLibrary library={library([], { projects: async () => listed, importFolder, pick: async () => {} })} onPlaceChange={next => places.push(next)} />);
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
  expect([screen.getByRole('main').querySelector('h2')?.textContent, place('project:p2').getAttribute('aria-current')]).toEqual(['gear', 'page']);
  await choose();
  expect(await screen.findByText('STEP is inside gear, which is already a project.')).toBeTruthy();
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

it('says what each place lacks: an empty project, one whose folder is gone, one no longer listed, and projects that cannot be read', async () => {
  const source = library([model('loose.step', { project: 'p1' })], { projects: async () => [project('p1', 'heart-tag', 0), project('p2', 'lamp', 2, 0, { missing: true })] });
  const home = (at: Parameters<typeof ModelLibrary>[0]['place'], from = source) => <ModelLibrary library={from} place={at} />;
  const view = render(home({ view: 'project', project: 'p1' }));
  expect(await screen.findByText('No models or CAD files here yet.')).toBeTruthy();
  view.rerender(home({ view: 'project', project: 'p2' }));
  expect(screen.getByText("This project's folder is gone. Remove it, or put the folder back.")).toBeTruthy();
  expect(opens()).toEqual([]);
  view.rerender(home({ view: 'project', project: 'removed' }));
  expect(screen.getByText('This project is no longer in CAD. Open its folder again to bring it back.')).toBeTruthy();
  expect(screen.getByRole('main').querySelector('h2')?.textContent).toBe('Project');
  view.rerender(home({ view: 'standalone' }));
  expect(screen.getByText('No standalone documents. Every document here is in a project.')).toBeTruthy();
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
  : `/?${target.home.view === 'project' ? `project=${target.home.project}` : `view=${target.home.view}`}` };

it("makes a card's and a row's main press a real link where the host gives the document an address, and a button where it gives none", async () => {
  const tag = project('p1', 'heart-tag', 1, 1);
  const source = library([model('bracket.step', { id: 'id-bracket' }), model('gone.step', { id: 'id-gone', missing: true }), model('unnamed.step')], { projects: async () => [tag] });
  for (const layout of ['grid', 'list'] as const) {
    const view = render(<ModelLibrary library={source} layout={layout} navigation={addresses} />);
    const card = await screen.findByRole('link', { name: 'Open bracket.step' });
    expect([card.tagName, card.getAttribute('href'), card.className]).toEqual(['A', '/id-bracket?token=t', 'cad-library-open']);
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
    // A project's model has its page, and so has its file no page has opened yet: the host knows each by its id.
    await act(async () => { fireEvent.click(place('project:p1')); });
    expect(screen.getByRole('link', { name: 'Open heart-tag_model_0' }).getAttribute('href')).toBe('/8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f00?token=t');
    expect(screen.getByRole('link', { name: 'Open part_0.stl' }).getAttribute('href')).toBe('/file-p1-0?token=t');
    view.unmount();
    cleanup();
    (source.open as ReturnType<typeof vi.fn>).mockClear();
  }
});

it("makes each place's row a link where the host gives places an address: a plain click shows it here", async () => {
  const places: unknown[] = [];
  render(<ModelLibrary library={library([model('a.step')], { projects: async () => [project('p1', 'heart-tag', 1)] })} navigation={addresses} onPlaceChange={next => places.push(next)} />);
  await waitFor(() => expect(place('project:p1')).toBeTruthy());
  expect([...document.querySelectorAll('[data-place]')].map(row => [row.tagName, row.getAttribute('href')]))
    .toEqual([['A', '/?view=recents'], ['A', '/?view=pinned'], ['A', '/?project=p1'], ['A', '/?view=standalone']]);
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
  const tag = project('p1', 'heart-tag', 1, 1);
  const source = library([model('bracket.step', { id: 'id-bracket' })], { projects: async () => [tag], removeProject: async () => [] });
  const home = (navigation: LibraryNavigation, at: Parameters<typeof ModelLibrary>[0]['place'] = { view: 'project', project: 'p1' }) =>
    render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} navigation={navigation} place={at} /></ControlUsageProvider>);
  const tab: LibraryNavigation = { openBeside: { kind: 'tab', open: target => { opened.push(target); } } };
  // A document the host has a page for is named by its id.
  let view = home(tab, { view: 'recents' });
  await screen.findByRole('button', { name: 'Open bracket.step' });
  let open = await menu('bracket.step');
  expect(items(open)).toEqual(['Open', 'Open in new tab', 'Pin', 'Delete']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open in new tab' })); });
  view.unmount();
  cleanup();
  // A project's file no page has opened, and a model, each by its id.
  for (const name of ['part_0.stl', 'heart-tag_model_0']) {
    view = home(tab);
    await screen.findByRole('button', { name: `Open ${name}` });
    open = await menu(name);
    expect(items(open).slice(0, 2)).toEqual(['Open', 'Open in new tab']);
    await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open in new tab' })); });
    view.unmount();
    cleanup();
  }
  // A project's ⋯: Open in new tab first.
  view = home(tab);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  await act(async () => { fireEvent.pointerDown(screen.getByRole('button', { name: 'Actions for the project heart-tag' }), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  open = await screen.findByRole('menu');
  expect(items(open)).toEqual(['Open in new tab', 'Remove from CAD']);
  await act(async () => { fireEvent.click(within(open).getByRole('menuitem', { name: 'Open in new tab' })); });
  await waitFor(() => expect(opened).toHaveLength(4));
  expect(opened).toEqual([{ document: 'id-bracket' }, { document: 'file-p1-0' }, { document: '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f00' },
    { home: { view: 'project', project: 'p1' } }]);
  view.unmount();
  expect(reported(reports)).toEqual({ home_open_new_tab: 3, home_project_open_new_tab: 1 });
  cleanup();
  // A page in an app's frame: Open in browser, a document's alone where the host opens no place beside the view.
  const browser: LibraryNavigation = { openBeside: { kind: 'browser', places: false, open: () => {} } };
  view = home(browser);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect(items(await menu('heart-tag_model_0')).slice(0, 2)).toEqual(['Open', 'Open in browser']);
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
  expect(items(await menu('bracket.step'))).toEqual(['Open', 'Pin', 'Delete']);
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
  const tag = project('p1', 'heart-tag', 3, 2);
  const back = vi.fn();
  const left = tag.documents[1];
  const source = library([model('loose.step')], { projects: async () => [tag] });
  const home = (from: Parameters<typeof ModelLibrary>[0]['from'], layout: 'grid' | 'list' = 'grid') => <ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={source} layout={layout} place={{ view: 'project', project: 'p1' }} from={from} onBack={back} /></ControlUsageProvider>;
  const view = render(home({ path: left.path, id: left.id, name: left.name }));
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  // Its card, and no other, is the one marked; it is brought into view once it is drawn.
  const ringed = () => [...document.querySelectorAll('[data-from]')].map(item => within(item as HTMLElement).getAllByRole('button')[0].getAttribute('aria-label'));
  expect(ringed()).toEqual(['Open heart-tag_model_1']);
  await waitFor(() => expect(scrolled).toHaveBeenCalledTimes(1));
  expect([scrolled.mock.contexts[0], scrolled.mock.calls[0]]).toEqual([document.querySelector('[data-from]'), [{ block: 'nearest' }]]);
  // The way back stands in the heading row, with its key.
  const button = screen.getByRole('button', { name: 'Back to heart-tag_model_1' });
  expect([button.closest('.cad-library-toolbar') !== null, button.querySelector('kbd')?.textContent, button.getAttribute('aria-keyshortcuts')]).toEqual([true, 'Esc', 'Escape']);
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
  expect(ringed()).toEqual(['Open heart-tag_model_1']);
  // The host forgets it (another document opened, another place): no ring, no way back, and Escape is nobody's.
  cleanup();
  render(home(null));
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([ringed(), screen.queryByRole('button', { name: /^Back to/ })]).toEqual([[], null]);
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(back).toHaveBeenCalledTimes(2);
  expect(reported(reports)).toEqual({ home_back: 2 });
});

it('shows the document just left even where it is past the first of a long place', async () => {
  const big = project('p1', 'bolts', PLACE_ROWS + 5);
  const last = big.documents.at(-1)!;
  // Oldest of all: last by last activity.
  big.documents = big.documents.map(item => item === last ? { ...item, updated: 1 } : item);
  render(<ModelLibrary library={library([], { projects: async () => [big] })} place={{ view: 'project', project: 'p1' }} from={{ path: last.path, name: last.name }} onBack={() => {}} />);
  await screen.findByRole('button', { name: 'Open part_0.stl' });
  expect([opens().length, opens().at(-1), document.querySelectorAll('[data-from]').length]).toEqual([PLACE_ROWS + 5, `Open ${last.name}`, 1]);
});

// A narrow home keeps its sidebar's ways (`LibrarySidebar.jsx`): what narrows is the place's own gutters.
it('puts the place on the narrow gutters in a home narrower than 720px, measured on the home and never the window; its heading stays Home and the place keeps its name', async () => {
  let width = 719;
  const boxes = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const wide = this.classList.contains('cad-library') ? width : 0;
    return { x: 0, y: 0, left: 0, top: 0, right: wide, bottom: 0, width: wide, height: 0, toJSON() {} } as DOMRect;
  });
  const resized: (() => void)[] = [];
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { resized.push(callback); } observe() {} disconnect() {} });
  try {
    render(<ModelLibrary library={library([model('a.step')])} />);
    await screen.findByRole('button', { name: 'Open a.step' });
    const narrow = () => document.querySelector('[data-library-narrow]') !== null;
    // No menu of places on the heading: Home, and the place's name in its own row, at any width.
    expect([narrow(), screen.getByRole('heading', { level: 1 }).textContent, screen.getByRole('main').querySelector('h2')?.textContent, screen.queryByRole('button', { name: /^Places/ })])
      .toEqual([true, 'Home', 'Recents', null]);
    width = 720;
    await act(async () => { resized.forEach(callback => callback()); });
    expect([narrow(), screen.getByRole('heading', { level: 1 }).textContent]).toEqual([false, 'Home']);
  } finally { boxes.mockRestore(); }
});

// The home under the viewer's navbar, as a host shows it (`FileViewer`): the sidebar is the viewer's panel over this
// page (`LibrarySidebar.jsx`, on `file-viewer/panelFrame.jsx`), so its toggle is the navbar's first control. The page
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
  const MEASURED = '.cad-library-frame, .cad-library, .text-to-cad-file-viewer';
  const boxes = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const own = this.matches(MEASURED) ? wide : 0;
    return { x: 0, y: 0, left: 0, top: 0, right: own, bottom: 0, width: own, height: 0, toJSON() {} } as DOMRect;
  });
  const home = vi.fn();
  const host = testHost({ navigation: { openFile() {}, home }, environment: { colorScheme: 'light', platform },
    ...(links ? { links: links === true ? viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x' }) : links as any } : null) });
  const source = library([model('loose.step')], { projects: async () => projects });
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
    frame: () => document.querySelector<HTMLElement>('.cad-library-frame')!,
  };
}
// Where the sidebar is: pinned beside the place, peeking over it, or gone; and what its toggle says.
const where = (home: ReturnType<typeof page>) => {
  const side = home.sidebar();
  const state = !side || side.hidden ? 'gone' : side.hasAttribute('data-panel-peek') ? 'peek' : side.getAttribute('data-library-sidebar') === 'page' ? 'sheet' : 'pinned';
  return [state, home.toggle().getAttribute('aria-expanded'), home.toggle().getAttribute('aria-label')];
};
const mouse = { pointerType: 'mouse' };

it("its sidebar is the viewer's panel: pinned it pushes the place, its toggle the navbar's first control; collapsed it leaves nothing; the person's choice is kept and stands at any width", async () => {
  const kept: object[] = [];
  const home = page({ width: 1200, onPanelChange: next => kept.push(next) });
  try {
    await screen.findByRole('button', { name: 'Open loose.step' });
    // Wide enough, with no choice: pinned, beside the place (in the frame's row, before it, taking its own width).
    expect(where(home)).toEqual(['pinned', 'true', 'Hide panel']);
    const side = home.sidebar()!;
    expect([side.parentElement === home.frame(), side.nextElementSibling === screen.getByRole('main'), side.style.width, side.className.split(' ').includes('shrink-0'),
      side.className.split(' ').includes('absolute'), home.frame().getAttribute('data-sidebar')]).toEqual([true, true, '232px', true, false, 'push']);
    // The same toggle as over a document: first in the row, before the logo, the sidebar's glyph, its key in its hint.
    const row = [...document.querySelectorAll('[data-viewer-navbar] nav > *')].map(node => node.querySelector('[data-navbar-panel]') ? 'toggle' : node.getAttribute('data-navbar-logo') ? 'logo' : '?');
    expect(row).toEqual(['toggle', 'logo']);
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
    expect([where(home)[0], screen.getByRole('main').querySelector('h2')?.textContent]).toEqual(['peek', 'Pinned']);
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
  const home = page({ width: 390, onPanelChange: next => kept.push(next), onPlaceChange: next => places.push(next), projects: [project('p1', 'heart-tag', 2)] });
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
    expect([...sheet()!.querySelectorAll('[data-place]')].map(row => row.getAttribute('data-place'))).toEqual(['recents', 'pinned', 'project:p1', 'standalone']);
    // A place chosen is shown, and the sheet gives the page back.
    fireEvent.click(sheet()!.querySelector<HTMLElement>('[data-place="project:p1"]')!);
    await waitFor(() => expect(sheet()).toBeNull());
    expect([places, screen.getByRole('main').querySelector('h2')?.textContent, home.toggle().getAttribute('aria-expanded')]).toEqual([[{ view: 'project', project: 'p1' }], 'heart-tag', 'false']);
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
  const home = page({ width: 1200, panel: { open: false }, projects: [project('p1', 'heart-tag', 2)],
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

it("ends its sidebar in a row of icons, pinned: the host's links at the left (GitHub, Discord, X, then Send feedback), each followed the host's way, and Settings' cog at the right, whose menu holds the settings alone", async () => {
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
      .toEqual([['GitHub', 'github', '_blank', 1, ''], ['Discord', 'discord', '_blank', 1, ''], ['X', 'x', '_blank', 1, ''], ['Send feedback', 'feedback', '_blank', 1, '']]);
    expect(footLinks(side).map(link => link.getAttribute('href')!.replace(/\?.*/, '')))
      .toEqual(['https://github.com/earthtojake/text-to-cad', 'https://discord.gg/x', 'https://x.com/earthtojake', 'https://github.com/earthtojake/text-to-cad/issues/new']);
    expect([foot(side).lastElementChild === cog(side), cog(side).closest('[data-app-foot-links]'), cog(side).getAttribute('aria-haspopup'), cog(side).querySelectorAll('svg').length,
      [...footLinks(side), cog(side)].every(tile => tile.className.split(' ').includes('size-control'))]).toEqual([true, null, 'menu', 1, true]);
    await userEvent.setup().hover(footLinks(side)[1]);
    expect((await screen.findByRole('tooltip')).textContent).toBe('Discord');
    // A press follows the link as the app menu's item did: through the host where it opens links itself; Send feedback is counted.
    expect(fireEvent.click(footLinks(side)[0])).toBe(false);
    expect(fireEvent.click(footLinks(side)[3])).toBe(false);
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
  const some = page({ width: 1200, links: { version: '0.7.4', release: '', x: '', github: 'https://github.com/a/b', discord: '', issues: '' } });
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
      .toEqual(['peek', ['GitHub', 'Discord', 'X', 'Send feedback'], 'Settings']);
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
      .toEqual(['scroll-area', ['GitHub', 'Discord', 'X', 'Send feedback']]);
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

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
// The built module: its Settings is the renderer kit's, whose JSX lives in .js files this runner does not compile.
import { ModelLibrary } from '../../dist/library/ModelLibrary.js';
import { activityLabel, ageLabel, lastActivity } from '../../dist/lib/age.js';
import { ControlUsageProvider } from '../../dist/usage/controls.js';
import { ViewerHostContext } from '../../dist/host/context.js';
import type { LibraryModel, LibraryProject, ModelLibrarySource } from './ModelLibrary.js';

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

it('starts with its control row: Home at the left, the search and the grid/list switch at the right, and no wordmark or links (the app menu\'s)', async () => {
  render(<ModelLibrary library={library([])} onLayoutChange={() => {}} />);
  await screen.findByText('Nothing here yet');
  const main = screen.getByRole('main', { name: 'CAD models' });
  const row = main.firstElementChild!;
  expect(row.querySelector('h1')?.textContent).toBe('Home');
  expect([...row.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label'))).toEqual(['Search models', 'Grid', 'List']);
  // The search keeps its placeholder; every control is the scale's control (28px), its icons 16px.
  expect(screen.getByRole('searchbox', { name: 'Search models' }).getAttribute('placeholder')).toBe('Search');
  expect(screen.getByRole('searchbox', { name: 'Search models' }).className).toContain('h-control');
  expect(['Grid', 'List'].map(name => [screen.getByRole('button', { name }).className.includes('size-control'),
    screen.getByRole('button', { name }).querySelector('svg')?.getAttribute('class')?.includes('size-4')])).toEqual([[true, true], [true, true]]);
  // No count; the one picture is the welcome's C mark.
  expect(row.querySelector('.cad-library-count')).toBeNull();
  expect([...main.querySelectorAll('img')].map(image => Boolean(image.closest('[data-library-empty]')))).toEqual([true]);
  expect(screen.queryByRole('navigation')).toBeNull();
  expect(screen.queryByRole('link')).toBeNull();
});

it('ends its control row in Import where the host has a chooser -- a file, or a folder opened as a project -- counted, and none where it has not', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const pick = vi.fn(async () => {});
  const importFolder = vi.fn(async () => null);
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={library([], { pick, importFolder })} onLayoutChange={() => {}} /></ControlUsageProvider>);
  await screen.findByText('Nothing here yet');
  const row = screen.getByRole('main', { name: 'CAD models' }).firstElementChild!;
  // Last of the row, after the grid/list switch: the folder icon, "Import", 28px as its neighbours, neutral (never a filled primary).
  expect([...row.querySelectorAll('input, button')].map(node => node.getAttribute('aria-label') ?? node.textContent)).toEqual(['Search models', 'Grid', 'List', 'Import']);
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
  // Pinned files come first, in the one list of Files: Pin is the card's menu's.
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
  expect(screen.getByRole('status').textContent).toBe('Loading files');
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
  // A model is a Model with no size; its Created is its first run's; a record from before the time was kept
  // has an empty Created, and a file that is gone says so where its time on disk was.
  expect(cells('arm')).toEqual([true, 'arm', ['kind', 'Model'], ['size', '—'], ['updated', '2h ago'], ['created', '2h ago']]);
  expect(cells('gone.step')).toEqual([true, 'gone.step', ['kind', 'STEP'], ['size', '—'], ['updated', 'File unavailable'], ['created', '']]);
  // A row's picture has no badge: its Kind says it. Its pin and ⋯ follow its button, at its end.
  expect(list.querySelector('.cad-library-format')).toBeNull();
  const row = within(list).getAllByRole('listitem')[0];
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

it('marks each card with its kind\'s glyph, and the type filter ("All ▾") shows models or files', async () => {
  const id = '8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12';
  const source = library([model('bracket.step'), model('arm', { path: id, kind: 'model', script: '/work/parts/arm.py' })]);
  const names = () => within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem').map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'));
  // A fresh home each time: a second menu opened in one jsdom render stays shut.
  const choose = async (value: string) => {
    cleanup();
    render(<ModelLibrary library={source} />);
    await screen.findByRole('button', { name: 'Open arm' });
    const trigger = screen.getByRole('button', { name: 'Show All' });
    await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    const open = await screen.findByRole('menu');
    expect(within(open).getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
      .toEqual([['All', 'true'], ['Models', 'false'], ['Files', 'false']]);
    await act(async () => { fireEvent.click(within(open).getByRole('menuitemradio', { name: value })); });
    expect(screen.getByRole('button', { name: `Show ${value}` }).textContent).toBe(value);
  };
  render(<ModelLibrary library={source} />);
  const arm = await screen.findByRole('button', { name: 'Open arm' });
  expect(arm.querySelector('[data-glyph]')?.getAttribute('data-glyph')).toBe('model');
  expect(screen.getByRole('button', { name: 'Open bracket.step' }).querySelector('[data-glyph]')?.getAttribute('data-glyph')).toBe('file');
  // A stock dropdown at the right of the control row, before the search, in the row's 28px.
  const trigger = screen.getByRole('button', { name: 'Show All' });
  expect([trigger.textContent, trigger.className.includes('h-control'), trigger.nextElementSibling?.querySelector('input')?.getAttribute('aria-label')]).toEqual(['All', true, 'Search models']);
  expect(names()).toEqual(['Open bracket.step', 'Open arm']);
  await choose('Models');
  expect(names()).toEqual(['Open arm']);
  await choose('Files');
  expect(names()).toEqual(['Open bracket.step']);
  cleanup();
  // With one kind alone there is nothing to tell apart: no filter.
  render(<ModelLibrary library={library([model('bracket.step')])} />);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  expect(screen.queryByRole('button', { name: /^Show / })).toBeNull();
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
    expect(names()).toEqual(['Open wheel', 'Open juno', 'Open axle', 'Open bracket.step']);
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
  expect((await screen.findByRole('button', { name: 'Open arm' })).textContent).toBe('ModelarmEdited 2h ago');
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
    model('new.step'),
    model('current.step', { thumbnail: 'current.png', pictured: edited + 30, updated: edited }),
    model('old.step', { thumbnail: 'old.png', pictured: edited - 3600, updated: edited }),
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

it("counts what a person does on the home by name: a type chosen, a search begun, a card opened, a delete cancelled and one confirmed", async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const script = '/work/juno/juno.py';
  const ids = ['0', '1'].map(digit => `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f1${digit}`);
  const source = library([model('juno', { path: ids[0], kind: 'model', script, updated: 10 }),
    model('wheel', { path: ids[1], kind: 'model', script, updated: 5 }), model('bracket.step')]);
  // The type filter's choice, in a home of its own: a second menu opened in one jsdom render stays shut.
  const choose = async (value: string) => {
    const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
    await screen.findByRole('button', { name: 'Open juno' });
    await act(async () => { fireEvent.pointerDown(screen.getByRole('button', { name: 'Show All' }), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    await act(async () => { fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitemradio', { name: value })); });
    view.unmount();
    cleanup();
  };
  await choose('Models');
  await choose('All'); // already shown: no use
  expect(reports.flat()).toEqual([{ control: 'home_filter_models', count: 1, seconds: 0 }]);
  reports.length = 0;
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open juno' });
  const search = screen.getByRole('searchbox', { name: 'Search models' });
  for (const value of ['b', 'br', '']) fireEvent.change(search, { target: { value } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open bracket.step' })); });
  await act(async () => { fireEvent.click(within(await menu('bracket.step')).getByRole('menuitem', { name: 'Delete' })); });
  await act(async () => { fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' })); });
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, count }) => [control, count]));
  expect(said).toEqual({ home_search: 1, home_open: 1, home_delete_cancel: 1 });
  // A delete the person confirms is counted as one.
  cleanup();
  reports.length = 0;
  const again = render(<ControlUsageProvider report={counts => reports.push(counts)}><ModelLibrary library={source} /></ControlUsageProvider>);
  await screen.findByRole('button', { name: 'Open bracket.step' });
  await act(async () => { fireEvent.click(within(await menu('bracket.step')).getByRole('menuitem', { name: 'Delete' })); });
  await act(async () => { fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' })); });
  again.unmount();
  expect(reports.flat()).toEqual([{ control: 'home_delete', count: 1, seconds: 0 }]);
});

it('counts the pin, from its button or the menu, the grid/list switch, and Copy path, Copy link and Reveal', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const fileActions = { platform: 'darwin' as const, perform: { 'copy-path': () => {}, 'copy-link': () => {}, reveal: () => {} } };
  const source = library([model('bracket.step'), model('plate.step', { pinned: true })]);
  const home = () => render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={source} fileActions={fileActions} onLayoutChange={() => {}} /></ControlUsageProvider>);
  let view = home();
  await screen.findByRole('button', { name: 'Open bracket.step' });
  const bracket = screen.getByRole('button', { name: 'Open bracket.step' }).closest('li')!;
  await act(async () => { fireEvent.click(within(bracket).getByRole('button', { name: 'Pin' })); });
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
  expect(['video.kicad_pcb', 'plate.dxf', 'arm'].map(name => picture(name).querySelector('.cad-library-format')?.textContent)).toEqual(['KiCad PCB', 'DXF', 'Model']);
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

// A project as the host lists it: `count` files in its folder, each of the project, and `models` models.
const project = (id: string, name: string, files: number, models = 0, extra: Partial<LibraryProject> = {}): LibraryProject => ({
  id, name, root: `/Users/sam/cad/${name}`, opened: 1, missing: false,
  documents: [
    ...Array.from({ length: models }, (_, index) => model(`${name}_model_${index}`, { path: `8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f${String(index).padStart(2, '0')}`,
      kind: 'model', project: id, opened: null })),
    ...Array.from({ length: files }, (_, index) => model(`part_${index}.stl`, { path: `/Users/sam/cad/${name}/STL/part_${index}.stl`, project: id,
      opened: null, created: null })),
  ],
  ...extra,
});

it('lists each project as a section of its documents, models first, eight until its Show all, then the documents of no project under Standalone', async () => {
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const tag = project('p1', 'heart-tag', 9, 2);
  const recents = [model('opened.stl', { path: '/Users/sam/cad/heart-tag/STL/part_0.stl', project: 'p1' }), model('loose.step'), model('other.stl')];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ModelLibrary library={library(recents, { projects: async () => [tag] })} home="/Users/sam" />
  </ControlUsageProvider>);
  const section = await screen.findByRole('region', { name: 'heart-tag' });
  expect(within(section).getByRole('heading', { level: 2 }).textContent).toBe('heart-tag');
  // Its folder, from `~`.
  expect(section.querySelector('.cad-library-section-path')?.textContent).toBe('~/cad/heart-tag');
  const cards = () => within(section).getAllByRole('listitem').map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'));
  expect(cards()).toEqual(['Open heart-tag_model_0', 'Open heart-tag_model_1', ...Array.from({ length: 6 }, (_, index) => `Open part_${index}.stl`)]);
  await act(async () => { fireEvent.click(within(section).getByRole('button', { name: 'Show all 11' })); });
  expect(cards()).toHaveLength(11);
  expect(within(section).getByRole('button', { name: 'Show fewer' }).getAttribute('aria-expanded')).toBe('true');
  // A file of the project's that no page opened: no pin, and no Delete (its folder lists it).
  expect(within(section.querySelectorAll('li')[2] as HTMLElement).queryByRole('button', { name: 'Pin' })).toBeNull();
  expect(items(await menu('part_0.stl'))).toEqual(['Open']);
  // The documents of no project, under Standalone; the project's own opened file is its section's alone.
  const standalone = screen.getByRole('region', { name: 'Standalone' });
  expect(within(standalone).getByRole('heading', { level: 2 }).textContent).toBe('Standalone');
  expect(within(standalone).getAllByRole('listitem').map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label')))
    .toEqual(['Open loose.step', 'Open other.stl']);
  view.unmount();
  expect(reports.flat()).toEqual([{ control: 'home_project_more', count: 1, seconds: 0 }]);
});

it('narrows every section with a search, leaving out a section with nothing that matches', async () => {
  render(<ModelLibrary library={library([model('loose.step')], { projects: async () => [project('p1', 'heart-tag', 3), project('p2', 'gear', 2)] })} />);
  await screen.findByRole('region', { name: 'gear' });
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'part_2' } });
  expect(screen.getAllByRole('region').map(region => region.getAttribute('aria-label'))).toEqual(['heart-tag']);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search models' }), { target: { value: 'nothing' } });
  expect(screen.getByRole('status').textContent).toBe('No matching models.');
});

it("gives each project a menu: its folder's Copy path and Reveal, and Remove from CAD, which forgets the project alone and says so", async () => {
  const perform = { 'copy-path': vi.fn(async () => {}), reveal: vi.fn(async () => {}) };
  let listed = [project('p1', 'heart-tag', 1)];
  const removeProject = vi.fn(async () => { listed = []; return listed; });
  render(<ModelLibrary library={library([], { projects: async () => listed, removeProject })} fileActions={{ platform: 'darwin', perform }} />);
  await screen.findByRole('region', { name: 'heart-tag' });
  const trigger = screen.getByRole('button', { name: 'Actions for the project heart-tag' });
  await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  expect(items(await screen.findByRole('menu'))).toEqual(['Copy path', 'Reveal in Finder', 'Remove from CAD']);
  await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: 'Copy path' })); });
  expect(perform['copy-path']).toHaveBeenCalledWith({ path: '/Users/sam/cad/heart-tag', kind: 'directory' });
  await act(async () => { fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  await act(async () => { fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from CAD' })); });
  expect(removeProject).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1' }));
  expect(await screen.findByText('heart-tag removed. Nothing on disk changed, and its documents are standalone again.')).toBeTruthy();
  expect(screen.queryByRole('region', { name: 'heart-tag' })).toBeNull();
});

it("brings the project Import's Folder opened into view, marked, and says what came of it", async () => {
  const scrolled = vi.fn();
  Element.prototype.scrollIntoView = scrolled;
  let listed: LibraryProject[] = [];
  const answers = [{ project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: true, folder: '/w/gear' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear/STEP' },
    { project: { id: 'p2', name: 'gear', root: '/w/gear' }, made: false, folder: '/w/gear' }];
  const importFolder = vi.fn(async () => { listed = [project('p2', 'gear', 1, 0, { root: '/w/gear' })]; return answers.shift()!; });
  render(<ModelLibrary library={library([], { projects: async () => listed, importFolder, pick: async () => {} })} />);
  await screen.findByText('Nothing here yet');
  const choose = async () => {
    await act(async () => { fireEvent.pointerDown(screen.getByRole('button', { name: 'Import', exact: true }), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    await act(async () => { fireEvent.click(await screen.findByRole('menuitem', { name: 'Folder…' })); });
  };
  await choose();
  expect(await screen.findByText('gear is now a project. Nothing was written to the folder.')).toBeTruthy();
  const section = screen.getByRole('region', { name: 'gear' });
  expect(section.hasAttribute('data-focus')).toBe(true);
  expect(scrolled).toHaveBeenCalled();
  await choose();
  expect(await screen.findByText('STEP is inside gear, which is already a project.')).toBeTruthy();
  await choose();
  expect(await screen.findByText('gear is already a project.')).toBeTruthy();
});

it("brings the project the host names into view: the navbar's project name, pressed", async () => {
  const scrolled = vi.fn();
  Element.prototype.scrollIntoView = scrolled;
  render(<ModelLibrary library={library([], { projects: async () => [project('p1', 'heart-tag', 1), project('p2', 'gear', 1)] })} focus="p2" />);
  const gear = await screen.findByRole('region', { name: 'gear' });
  expect([gear.hasAttribute('data-focus'), screen.getByRole('region', { name: 'heart-tag' }).hasAttribute('data-focus')]).toEqual([true, false]);
  await waitFor(() => expect(scrolled).toHaveBeenCalledTimes(1));
  expect(scrolled.mock.contexts[0]).toBe(gear);
});

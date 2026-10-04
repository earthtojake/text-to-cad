import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
// The built module: its Settings is the renderer kit's, whose JSX lives in .js files this runner does not compile.
import { ModelLibrary, editedLabel } from '../../dist/library/ModelLibrary.js';
import type { LibraryModel, ModelLibrarySource } from './ModelLibrary.js';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const NOW = Date.UTC(2026, 8, 30, 12);
const model = (name: string, extra: Partial<LibraryModel> = {}): LibraryModel =>
  ({ path: `/work/parts/${name}`, name, folder: '/work/parts', opened: 1, modified: Date.now() / 1000 - 16 * 3600, pinned: false, missing: false, thumbnail: null, pictured: null, ...extra });

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

it('heads the home with the TEXTTOCAD wordmark over GitHub and the cog that opens the app menu, the host\'s update button first when there is one; no tagline', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  const user = userEvent.setup();
  const links = { version: '0.7.4', release: 'r', x: 'https://x.com/earthtojake', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x',
    issues: 'https://github.com/earthtojake/text-to-cad/issues/new' };
  const changes: boolean[] = [];
  render(<ModelLibrary library={library([])} links={links} platform="win32"
    appSettings={[{ id: 'analytics', label: 'Share anonymous usage data', checked: false, onCheckedChange: value => { changes.push(value); } }]} />);
  const nav = await screen.findByRole('navigation', { name: 'CAD links' });
  expect(screen.getByRole('img', { name: 'text-to-cad' }).getAttribute('src')).toMatch(/texttocad/);
  expect([...nav.querySelectorAll('a, button')].map(node => node.getAttribute('aria-label'))).toEqual(['GitHub', 'Settings']);
  expect(screen.queryByText('Build things')).toBeNull();
  // The app menu, as the navbar's logo opens it but for Back to files (the home is not a file): the
  // host's own settings, Send feedback, GitHub and Discord, then the version and "Made by @…".
  await user.click(within(nav).getByRole('button', { name: 'Settings' }));
  const menu = await screen.findByRole('menu', { name: 'Settings' });
  expect([...menu.querySelectorAll('[role^="menuitem"]')].map(item => item.textContent)).toEqual(['Share anonymous usage data', 'Send feedback', 'GitHub', 'Discord']);
  // Send feedback: a new issue on the project's tracker, begun "Feedback: ", for the person to finish,
  // naming the version and the platform; no label: the project has none for feedback.
  const feedback = new URL(within(menu).getByRole('menuitem', { name: 'Send feedback' }).getAttribute('href')!);
  expect([`${feedback.origin}${feedback.pathname}`, feedback.searchParams.get('title'), feedback.searchParams.get('labels')])
    .toEqual(['https://github.com/earthtojake/text-to-cad/issues/new', 'Feedback: ', null]);
  expect(feedback.searchParams.get('body')).toMatch(/^\*\*What happened, or what would you like\?\*\*\n[\s\S]*- CAD: 0\.7\.4\n- Platform: win32$/);
  const footer = menu.querySelector('[data-menu-footer]')!;
  expect([...footer.querySelectorAll('a')].map(link => [link.textContent, link.getAttribute('href')]))
    .toEqual([['v0.7.4', 'r'], ['Made by @earthtojake', 'https://x.com/earthtojake']]);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Share anonymous usage data' }));
  expect(changes).toEqual([true]);
  cleanup();
  // A host with no tracker has no Send feedback.
  render(<ModelLibrary library={library([])} links={{ ...links, issues: '' }} />);
  await user.click(within(await screen.findByRole('navigation', { name: 'CAD links' })).getByRole('button', { name: 'Settings' }));
  expect(within(await screen.findByRole('menu')).queryByRole('menuitem', { name: 'Send feedback' })).toBeNull();
  cleanup();
  // The host's update button, first in the row, while its install is behind; its Full size, last, where it shows the view small.
  render(<ModelLibrary library={library([])} links={links} update={<button type="button" aria-label="Update to 0.7.5" />}
    fullSize={<button type="button" aria-label="Full size" />} />);
  const row = await screen.findByRole('navigation', { name: 'CAD links' });
  expect([...row.querySelectorAll('a, button')].map(node => node.getAttribute('aria-label'))).toEqual(['Update to 0.7.5', 'GitHub', 'Settings', 'Full size']);
});

it('offers Open only where the host has a chooser, and opens and pins through the host', async () => {
  const pick = vi.fn(async () => {});
  render(<ModelLibrary library={library([], { pick })} onLayoutChange={() => {}} />);
  await act(async () => { fireEvent.click(await screen.findByRole('button', { name: 'Open', exact: true })); });
  // The toolbar keeps its search and layout switch with nothing to list yet.
  expect(screen.getByRole('searchbox', { name: 'Search models' })).toBeTruthy();
  expect(screen.getByRole('group', { name: 'Layout' })).toBeTruthy();
  expect(pick).toHaveBeenCalledTimes(1);
  // Empty, the library is one card that opens the chooser.
  const card = await screen.findByRole('button', { name: 'Open File' });
  await act(async () => { fireEvent.click(card); });
  expect(pick).toHaveBeenCalledTimes(2);
  cleanup();
  // With no chooser, it says how a file gets here.
  render(<ModelLibrary library={library([])} />);
  expect(await screen.findByText('Open a CAD file to see it here.')).toBeTruthy();
  cleanup();

  const inPlace = library([model('a.step'), model('b.stl', { missing: true })]);
  render(<ModelLibrary library={inPlace} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  expect(screen.queryByRole('button', { name: 'Open', exact: true })).toBeNull();
  expect((screen.getByRole('button', { name: 'Open b.stl' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Open b.stl' }).textContent).toContain('File unavailable');
  await act(async () => { fireEvent.click(open); });
  expect(inPlace.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'a.step' }));
  // Pinned files come first, in the one list of Files.
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pin b.stl' })); });
  const files = within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem');
  expect(files.map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'))).toEqual(['Open b.stl', 'Open a.step']);
  expect(screen.getByRole('button', { name: 'Unpin b.stl' }).getAttribute('aria-pressed')).toBe('true');
  // A pinned card's pin is filled; a card has no Remove of its own.
  expect(screen.getByRole('button', { name: 'Unpin b.stl' }).querySelector('svg')?.getAttribute('fill')).toBe('currentColor');
  expect(screen.getByRole('button', { name: 'Pin a.step' }).querySelector('svg')?.getAttribute('fill')).toBe('none');
  expect(screen.queryByRole('button', { name: 'Remove a.step' })).toBeNull();
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

it('names a card by its file and when it was edited, and switches between a grid and a list', async () => {
  const layouts: string[] = [];
  const { rerender } = render(<ModelLibrary library={library([model('bracket.step')])} layout="grid" onLayoutChange={layout => layouts.push(layout)} />);
  const card = await screen.findByRole('button', { name: 'Open bracket.step' });
  expect(card.textContent).toMatch(/^bracket\.stepEdited \d+h ago$/);
  expect(card.textContent).not.toContain('/work');
  expect(screen.getByRole('button', { name: 'Grid' }).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  expect(layouts).toEqual(['list']);
  rerender(<ModelLibrary library={library([model('bracket.step')])} layout="list" onLayoutChange={layout => layouts.push(layout)} />);
  expect(screen.getByRole('button', { name: 'List' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('list', { name: 'Files' }).className).toContain('cad-library-list');
  // A row can be removed.
  expect(screen.getByRole('button', { name: 'Remove bracket.step' })).toBeTruthy();
});

it('says how long ago a file changed in the largest unit that is at least one', () => {
  const ago = (seconds: number) => editedLabel(NOW / 1000 - seconds, NOW);
  expect([ago(20), ago(5 * 60), ago(16 * 3600), ago(3 * 86400)]).toEqual(['Edited just now', 'Edited 5m ago', 'Edited 16h ago', 'Edited 3d ago']);
  expect(ago(40 * 86400)).toMatch(/^Edited \S/);
  expect(editedLabel(null, NOW)).toBe('');
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
    model('current.step', { thumbnail: 'current.png', pictured: edited + 30, modified: edited }),
    model('old.step', { thumbnail: 'old.png', pictured: edited - 3600, modified: edited }),
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
it('pictures a card again when its file is edited while the home is up', async () => {
  const edited = Date.now() / 1000 - 60;
  let models = [model('plate.step', { thumbnail: 'plate.png', pictured: edited + 30, modified: edited })];
  const list = vi.fn(async () => models);
  const picture = vi.fn(async () => true);
  render(<ModelLibrary library={library(models, { list })} picture={picture} />);
  await screen.findByRole('button', { name: 'Open plate.step' });
  expect(picture).not.toHaveBeenCalled();
  models = [{ ...models[0], modified: edited + 60 }];
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
  await waitFor(() => expect(picture.mock.calls.map(([item]) => item.modified)).toEqual([edited + 60]));
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

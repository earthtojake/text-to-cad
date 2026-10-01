import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ModelLibrary, editedLabel, type LibraryModel, type ModelLibrarySource } from './ModelLibrary.js';

afterEach(cleanup);

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

it('heads the home with the CAD wordmark over the host\'s version, as the navbar has it, and no tagline', async () => {
  const links = { version: '0.7.4', release: 'r', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x', install: { command: 'c', prompt: 'p' } };
  const clipboard = { writeText: async () => {}, readText: async () => '', writeImage: async () => {} };
  render(<ModelLibrary library={library([])} links={links} clipboard={clipboard} />);
  const nav = await screen.findByRole('navigation', { name: 'CAD links' });
  expect(within(nav).getByRole('button', { name: 'Version 0.7.4' }).textContent).toBe('v0.7.4');
  expect(screen.queryByText('Build things')).toBeNull();
});

it('offers Open only where the host has a chooser, and opens and pins through the host', async () => {
  const pick = vi.fn(async () => {});
  render(<ModelLibrary library={library([], { pick })} />);
  await act(async () => { fireEvent.click(await screen.findByRole('button', { name: 'Open', exact: true })); });
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

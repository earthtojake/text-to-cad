import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ModelLibrary, editedLabel, type LibraryModel, type ModelLibrarySource } from './ModelLibrary.js';

afterEach(cleanup);

const NOW = Date.UTC(2026, 8, 30, 12);
const model = (name: string, extra: Partial<LibraryModel> = {}): LibraryModel =>
  ({ path: `/work/parts/${name}`, name, folder: '/work/parts', opened: 1, modified: Date.now() / 1000 - 16 * 3600, pinned: false, missing: false, thumbnail: null, ...extra });

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

it('offers Open Model only where the host has a chooser, and opens and pins through the host', async () => {
  const pick = vi.fn(async () => {});
  render(<ModelLibrary library={library([], { pick })} />);
  await act(async () => { fireEvent.click(await screen.findByRole('button', { name: 'Open Model' })); });
  expect(pick).toHaveBeenCalled();
  expect(screen.getByText('Open a CAD file to see it here.')).toBeTruthy();
  cleanup();

  const inPlace = library([model('a.step'), model('b.stl', { missing: true })]);
  render(<ModelLibrary library={inPlace} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  expect(screen.queryByRole('button', { name: 'Open Model' })).toBeNull();
  expect((screen.getByRole('button', { name: 'Open b.stl' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Open b.stl' }).textContent).toContain('File unavailable');
  await act(async () => { fireEvent.click(open); });
  expect(inPlace.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'a.step' }));
  // Pinned files come first, in the one list of Files.
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pin b.stl' })); });
  const files = within(screen.getByRole('list', { name: 'Files' })).getAllByRole('listitem');
  expect(files.map(item => within(item).getAllByRole('button')[0].getAttribute('aria-label'))).toEqual(['Open b.stl', 'Open a.step']);
  expect(screen.getByRole('button', { name: 'Unpin b.stl' }).getAttribute('aria-pressed')).toBe('true');
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

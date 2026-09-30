import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ModelLibrary, type LibraryModel, type ModelLibrarySource } from './ModelLibrary.js';

afterEach(cleanup);

const model = (name: string, extra: Partial<LibraryModel> = {}): LibraryModel =>
  ({ path: `/work/${name}`, name, folder: '/work', opened: 1, pinned: false, missing: false, thumbnail: null, ...extra });

function library(models: LibraryModel[], extra: Partial<ModelLibrarySource> = {}): ModelLibrarySource {
  return {
    list: async () => models,
    change: vi.fn(async (action, item) => models.map(entry => entry.path === item.path ? { ...entry, pinned: action === 'pin' } : entry)),
    thumbnail: async () => null,
    open: vi.fn(async () => {}),
    ...extra,
  };
}

it('offers Open Model only where the host has a chooser, and opens and pins through the host', async () => {
  const pick = vi.fn(async () => {});
  const withChooser = library([], { pick });
  render(<ModelLibrary library={withChooser} />);
  const chooser = await screen.findByRole('button', { name: 'Open Model' });
  await act(async () => { fireEvent.click(chooser); });
  expect(pick).toHaveBeenCalled();
  cleanup();

  const inPlace = library([model('a.step'), model('b.stl', { missing: true })]);
  render(<ModelLibrary library={inPlace} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  expect(screen.queryByRole('button', { name: 'Open Model' })).toBeNull();
  expect((screen.getByRole('button', { name: 'Open b.stl' }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => { fireEvent.click(open); });
  expect(inPlace.open).toHaveBeenCalledWith(expect.objectContaining({ name: 'a.step' }));
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pin a.step' })); });
  expect(await screen.findByRole('region', { name: 'Pinned' })).toBeTruthy();
});

it('shows why an open failed where the library shows it', async () => {
  const failing = library([model('a.step')], { open: async () => { throw new Error('That model is gone.'); } });
  render(<ModelLibrary library={failing} />);
  const open = await screen.findByRole('button', { name: 'Open a.step' });
  await act(async () => { fireEvent.click(open); });
  expect((await screen.findByRole('alert')).textContent).toBe('That model is gone.');
});

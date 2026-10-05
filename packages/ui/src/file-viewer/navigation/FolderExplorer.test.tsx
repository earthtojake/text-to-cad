import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FolderExplorer, folderTrail, parentFolder } from '../../../dist/file-viewer/navigation/FolderExplorer.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

const FILE = '/home/me/models/parts/a.step';
const entry = (kind: 'file' | 'directory') => (path: string) => ({ path, name: path.split('/').pop()!, kind });
const [dir, file] = [entry('directory'), entry('file')];
// A disk, one folder at a time, as `FileSource.list` reads it.
const FOLDERS: Record<string, ReturnType<typeof dir>[]> = {
  '/home': [dir('/home/me')],
  '/home/me/models/parts': [dir('/home/me/models/parts/brackets'), file(FILE)],
  '/home/me/models/parts/brackets': [file('/home/me/models/parts/brackets/b.step')],
};
const list = async (directory: string) => FOLDERS[directory] ?? [];
// Each row as `kind:path`, the open file starred.
const rows = () => [...document.querySelectorAll('[data-explorer-row]')]
  .map(row => `${row.getAttribute('data-kind')}:${row.getAttribute('data-path')}${row.getAttribute('aria-current') === 'true' ? '*' : ''}`);
const row = (path: string) => document.querySelector<HTMLElement>(`[data-explorer-row][data-path="${path}"]`)!;
// The breadcrumb's buttons, the folder it is in starred.
const crumbs = () => within(screen.getByRole('navigation', { name: 'Folders' })).getAllByRole('button')
  .map(button => button.getAttribute('aria-label') ?? `${button.textContent}${button.getAttribute('aria-current') === 'location' ? '*' : ''}`);

it('names the folders down to a path, and the one holding it, on every filesystem', () => {
  expect(folderTrail('C:\\models\\a.step')).toEqual([{ name: 'C:', path: 'C:/' }, { name: 'models', path: 'C:/models' }, { name: 'a.step', path: 'C:/models/a.step' }]);
  expect([parentFolder(FILE), parentFolder('/a.step'), parentFolder('/'), parentFolder('C:/a.step')]).toEqual(['/home/me/models/parts', '/', '/', 'C:/']);
});

it('starts in the open file\'s folder and climbs by its last three folders, the ones above in the ellipsis\'s menu: a folder opens in place, a file is the pick', async () => {
  const user = userEvent.setup();
  const onOpen = vi.fn();
  const source = { list: vi.fn(list), search: vi.fn() };
  render(<FolderExplorer source={source} file={FILE} onOpen={onOpen} />);
  await screen.findByText('brackets');
  expect(source.list).toHaveBeenCalledWith('/home/me/models/parts', { signal: expect.any(AbortSignal) });
  // Its subfolders, then its files, the open file marked.
  expect(rows()).toEqual(['directory:/home/me/models/parts/brackets', `file:${FILE}*`]);
  expect(crumbs()).toEqual(['Folders above', 'me', 'models', 'parts*']);
  // A folder opens where the explorer is, and a file in it is the pick, by its absolute path.
  await user.click(row('/home/me/models/parts/brackets'));
  await screen.findByText('b.step');
  expect([rows(), crumbs()]).toEqual([['file:/home/me/models/parts/brackets/b.step'], ['Folders above', 'models', 'parts', 'brackets*']]);
  await user.click(row('/home/me/models/parts/brackets/b.step'));
  expect(onOpen.mock.calls).toEqual([['/home/me/models/parts/brackets/b.step']]);
  // A crumb climbs back to its folder.
  await user.click(screen.getByRole('button', { name: 'parts' }));
  await screen.findByText('brackets');
  expect(crumbs()).toEqual(['Folders above', 'me', 'models', 'parts*']);
  // The ellipsis holds the folders above the breadcrumb's three.
  await user.click(screen.getByRole('button', { name: 'Folders above' }));
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['/', 'home']);
  await user.click(screen.getByRole('menuitem', { name: 'home' }));
  await screen.findByText('me');
  expect([rows(), crumbs()]).toEqual([['directory:/home/me'], ['/', 'home*']]);
});

it('filters by searching under its folder once typing pauses, each keystroke cancelling the search before, and says when the search stopped early', async () => {
  vi.useFakeTimers();
  const onOpen = vi.fn();
  const searches: { query: string; signal: AbortSignal; answer(result: { paths: string[]; truncated: boolean }): void }[] = [];
  const source = { list, search: vi.fn((_directory: string, query: string, { signal }: { signal: AbortSignal }) =>
    new Promise<{ paths: string[]; truncated: boolean }>(answer => { searches.push({ query, signal, answer }); })) };
  render(<FolderExplorer source={source} file={FILE} onOpen={onOpen} />);
  await act(async () => {});
  const filter = screen.getByRole('textbox', { name: 'Filter files' });
  fireEvent.change(filter, { target: { value: 'b' } });
  act(() => { vi.advanceTimersByTime(100); });
  fireEvent.change(filter, { target: { value: 'br' } });
  act(() => { vi.advanceTimersByTime(149); });
  // Nothing is searched while the person types: each keystroke waits 150 ms again.
  expect([source.search.mock.calls.length, screen.getByRole('status').textContent]).toEqual([0, 'Searching…']);
  act(() => { vi.advanceTimersByTime(1); });
  expect(source.search.mock.calls).toEqual([['/home/me/models/parts', 'br', { signal: searches[0].signal }]]);
  // The next keystroke cancels the search still out; one that answers anyway lands nowhere.
  fireEvent.change(filter, { target: { value: 'bra' } });
  expect(searches[0].signal.aborted).toBe(true);
  act(() => { vi.advanceTimersByTime(150); });
  await act(async () => { searches[1].answer({ paths: ['/home/me/models/parts/brackets/bracket.step', FILE], truncated: true }); });
  await act(async () => { searches[0].answer({ paths: [], truncated: false }); });
  // Every match under the folder, its subfolder muted before its name, and a note that it stopped early.
  expect(rows()).toEqual(['file:/home/me/models/parts/brackets/bracket.step', `file:${FILE}*`]);
  const match = row('/home/me/models/parts/brackets/bracket.step');
  expect([match.textContent, match.querySelector('span.text-muted-foreground')?.textContent]).toEqual(['brackets/bracket.step', 'brackets/']);
  expect(screen.getByText('Stopped early. Keep typing to narrow the search.')).toBeTruthy();
  fireEvent.click(match);
  expect(onOpen).toHaveBeenCalledWith('/home/me/models/parts/brackets/bracket.step');
});

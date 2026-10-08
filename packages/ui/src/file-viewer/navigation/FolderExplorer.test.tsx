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

it('starts in the open file\'s folder: a press opens a subfolder inline, a double-click opens it in the explorer\'s place, a crumb climbs back, the folders above are the ellipsis\'s', async () => {
  const user = userEvent.setup();
  const onOpen = vi.fn();
  const source = { list: vi.fn(list), search: vi.fn() };
  render(<FolderExplorer source={source} file={FILE} onOpen={onOpen} />);
  await screen.findByText('brackets');
  expect(source.list).toHaveBeenCalledWith('/home/me/models/parts', { signal: expect.any(AbortSignal) });
  // Its subfolders, then its files, the open file marked.
  expect(rows()).toEqual(['directory:/home/me/models/parts/brackets', `file:${FILE}*`]);
  expect(crumbs()).toEqual(['Folders above', 'me', 'models', 'parts*']);
  // A press opens the subfolder inline, under itself and a little further in; the explorer stays where it is.
  const brackets = row('/home/me/models/parts/brackets');
  await user.click(brackets);
  await screen.findByText('b.step');
  expect(rows()).toEqual(['directory:/home/me/models/parts/brackets', 'file:/home/me/models/parts/brackets/b.step', `file:${FILE}*`]);
  expect([brackets.getAttribute('aria-expanded'), brackets.style.paddingLeft, row('/home/me/models/parts/brackets/b.step').style.paddingLeft])
    .toEqual(['true', '8px', '18px']);
  // Its rows hang from a faint line under its chevron, as every tree's do.
  expect([brackets.querySelectorAll('[data-tree-guide]').length,
    row('/home/me/models/parts/brackets/b.step').querySelectorAll('[data-tree-guide]').length]).toEqual([0, 1]);
  expect(crumbs()).toEqual(['Folders above', 'me', 'models', 'parts*']);
  // A file in it is the pick, by its absolute path; pressed again, the folder closes.
  await user.click(row('/home/me/models/parts/brackets/b.step'));
  expect(onOpen.mock.calls).toEqual([['/home/me/models/parts/brackets/b.step']]);
  await user.click(brackets);
  expect([rows(), brackets.getAttribute('aria-expanded')]).toEqual([['directory:/home/me/models/parts/brackets', `file:${FILE}*`], 'false']);
  // A double-click opens it in the explorer's place.
  await user.dblClick(row('/home/me/models/parts/brackets'));
  await screen.findByRole('button', { name: 'brackets' });
  expect([rows(), crumbs()]).toEqual([['file:/home/me/models/parts/brackets/b.step'], ['Folders above', 'models', 'parts', 'brackets*']]);
  // A crumb climbs back to its folder, where the folder double-clicked is not left open inline.
  await user.click(screen.getByRole('button', { name: 'parts' }));
  await screen.findByText('brackets');
  expect([rows(), crumbs()]).toEqual([['directory:/home/me/models/parts/brackets', `file:${FILE}*`], ['Folders above', 'me', 'models', 'parts*']]);
  // The ellipsis holds the folders above the breadcrumb's three.
  await user.click(screen.getByRole('button', { name: 'Folders above' }));
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['/', 'home']);
  await user.click(screen.getByRole('menuitem', { name: 'home' }));
  await screen.findByText('me');
  expect([rows(), crumbs()]).toEqual([['directory:/home/me'], ['/', 'home*']]);
});

it('walks the rows on screen by keyboard: Right opens a folder inline and Left closes it, Up and Down step through what it holds', async () => {
  render(<FolderExplorer source={{ list: vi.fn(list), search: vi.fn() }} file={FILE} onOpen={vi.fn()} />);
  await screen.findByText('brackets');
  const brackets = row('/home/me/models/parts/brackets');
  brackets.focus();
  fireEvent.keyDown(brackets, { key: 'ArrowRight' });
  await screen.findByText('b.step');
  fireEvent.keyDown(brackets, { key: 'ArrowDown' });
  expect(document.activeElement).toBe(row('/home/me/models/parts/brackets/b.step'));
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
  expect(document.activeElement).toBe(row(FILE));
  fireEvent.keyDown(brackets, { key: 'ArrowLeft' });
  expect(rows()).toEqual(['directory:/home/me/models/parts/brackets', `file:${FILE}*`]);
});

it('keeps every crumb whole: the folders that do not fit beside the one it is in go into the ellipsis, the farthest first', async () => {
  const user = userEvent.setup();
  // jsdom lays nothing out: here the folder the explorer is in is cut while any folder above it
  // shares the row with it, and fits once it is alone beside the ellipsis.
  const restores: (() => void)[] = [];
  const stub = (key: 'scrollWidth' | 'clientWidth', width: (crumb: HTMLElement) => number) => {
    const inherited = Object.getOwnPropertyDescriptor(Element.prototype, key)!;
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get(this: HTMLElement) {
      return this.getAttribute('aria-current') === 'location' ? width(this) : inherited.get!.call(this);
    } });
    restores.push(() => { delete (HTMLElement.prototype as any)[key]; });
  };
  const beside = (crumb: HTMLElement) => crumb.closest('nav')!.querySelectorAll('button:not([aria-current]):not([aria-label])').length;
  stub('scrollWidth', () => 200);
  stub('clientWidth', crumb => beside(crumb) ? 120 : 200);
  try {
    render(<FolderExplorer source={{ list: vi.fn(list), search: vi.fn() }} file={FILE} onOpen={vi.fn()} />);
    await screen.findByText('brackets');
    expect(crumbs()).toEqual(['Folders above', 'parts*']);
    // The ellipsis holds every folder above it, down to the nearest.
    await user.click(screen.getByRole('button', { name: 'Folders above' }));
    expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['/', 'home', 'me', 'models']);
  } finally { while (restores.length) restores.pop()!(); }
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

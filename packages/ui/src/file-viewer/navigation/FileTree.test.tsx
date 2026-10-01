import React, { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FileTree } from '../../../dist/file-viewer/navigation/FileTree.js';

const scrollIntoView = Element.prototype.scrollIntoView;
const scrolled: (string | undefined)[] = [];
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = function (this: Element) { scrolled.push((this as HTMLElement).dataset.path); };
  scrolled.length = 0;
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Element.prototype.scrollIntoView = scrollIntoView; });

const LISTINGS = {
  '': [
    { path: '.git', name: '.git', kind: 'directory' },
    { path: '.github', name: '.github', kind: 'directory' },
    { path: 'STEP', name: 'STEP', kind: 'directory' },
    { path: '.gitignore', name: '.gitignore', kind: 'file' },
    { path: 'notes.txt', name: 'notes.txt', kind: 'file' },
    { path: 'part.step', name: 'part.step', kind: 'file' },
  ],
  '.git': [{ path: '.git/config', name: 'config', kind: 'file' }],
  STEP: [{ path: 'STEP/bracket.step', name: 'bracket.step', kind: 'file' }],
};

// Stable, as a host's is: the tree re-reads the reveal whenever `load` changes.
const noLoad = () => {};
function Tree({ activePath = null as string | null, onOpen = (_: string) => {}, listings = LISTINGS as Record<string, any[]>, fails = false }) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [active, setActive] = useState(activePath);
  const source = { rootName: 'project', expanded, setExpanded, listings, load: noLoad, revision: 0,
    paths: async () => ['.git/config', '.github/ci.yml', 'STEP/bracket.step', 'notes.txt', 'part.step'], platform: 'darwin', onAction() {} };
  return <FileTree source={source as any} activePath={active} onOpen={(path: string) => { if (!fails) setActive(path); onOpen(path); }} />;
}
const rows = () => [...document.querySelectorAll<HTMLElement>('[data-path]')].map(row => row.dataset.path);

it('leaves .git out of the tree and the filter, and keeps every other dotfile', async () => {
  render(<Tree />);
  expect(rows()).toEqual(['.github', 'STEP', '.gitignore', 'notes.txt', 'part.step']);
  fireEvent.change(screen.getByRole('combobox', { name: 'Filter files' }), { target: { value: 'c' } });
  await waitFor(() => expect(rows()).toContain('.github/ci.yml'));
  expect(rows()).not.toContain('.git/config');
});

it('shows .git while the open file is inside it', () => {
  render(<Tree activePath=".git/config" />);
  expect(rows()).toContain('.git');
});

it('a file picked from the filter opens and brings the whole tree back', async () => {
  const onOpen = vi.fn();
  render(<Tree onOpen={onOpen} />);
  const filter = screen.getByRole('combobox', { name: 'Filter files' }) as HTMLInputElement;
  fireEvent.change(filter, { target: { value: 'part' } });
  await waitFor(() => expect(rows()).toEqual(['part.step']));
  fireEvent.click(document.querySelector('[data-path="part.step"]')!);
  expect(onOpen).toHaveBeenCalledWith('part.step');
  expect(filter.value).toBe('');
  expect(rows()).toEqual(['.github', 'STEP', '.gitignore', 'notes.txt', 'part.step']);

  // From the keyboard too: Enter on the ranked list opens its first match and ends the search.
  fireEvent.change(filter, { target: { value: 'notes' } });
  await waitFor(() => expect(rows()).toEqual(['notes.txt']));
  fireEvent.keyDown(filter, { key: 'Enter' });
  expect(onOpen).toHaveBeenLastCalledWith('notes.txt');
  expect(filter.value).toBe('');
});

it('leaves out the .git file at the root of a worktree too', () => {
  render(<Tree listings={{ '': [{ path: '.git', name: '.git', kind: 'file' }, { path: 'part.step', name: 'part.step', kind: 'file' }] }} />);
  expect(rows()).toEqual(['part.step']);
});

it('picking the file already open, from a folder shut by hand, opens the folder and scrolls to it', async () => {
  render(<Tree activePath="STEP/bracket.step" />);
  expect(rows()).toContain('STEP/bracket.step');
  fireEvent.click(document.querySelector('[data-path="STEP"]')!);
  expect(rows()).not.toContain('STEP/bracket.step');
  scrolled.length = 0;
  const filter = screen.getByRole('combobox', { name: 'Filter files' }) as HTMLInputElement;
  fireEvent.change(filter, { target: { value: 'bracket' } });
  await waitFor(() => expect(rows()).toEqual(['STEP/bracket.step']));
  fireEvent.click(document.querySelector('[data-path="STEP/bracket.step"]')!);
  expect(filter.value).toBe('');
  expect(rows()).toContain('STEP/bracket.step');
  expect(scrolled).toContain('STEP/bracket.step');
});

it('a pick that did not open never pulls the tree to it later, when its folder is opened by hand', async () => {
  const onOpen = vi.fn();
  render(<Tree fails onOpen={onOpen} />);
  const filter = screen.getByRole('combobox', { name: 'Filter files' }) as HTMLInputElement;
  fireEvent.change(filter, { target: { value: 'bracket' } });
  await waitFor(() => expect(rows()).toEqual(['STEP/bracket.step']));
  fireEvent.click(document.querySelector('[data-path="STEP/bracket.step"]')!);
  expect(onOpen).toHaveBeenCalledWith('STEP/bracket.step');
  expect(rows()).not.toContain('STEP/bracket.step');
  scrolled.length = 0;
  fireEvent.click(document.querySelector('[data-path="STEP"]')!);
  expect(rows()).toContain('STEP/bracket.step');
  expect(scrolled).not.toContain('STEP/bracket.step');
});

it('highlights one row: the open file, not also the row the cursor last sat on or the first row', () => {
  const highlighted = () => [...document.querySelectorAll<HTMLElement>('[data-path]')]
    .filter(row => /(^|\s)bg-accent(\/30)?(\s|$)/.test(row.className)).map(row => row.dataset.path);
  const source = { rootName: 'project', expanded: new Set(), setExpanded() {}, listings: LISTINGS, load: noLoad, revision: 0,
    paths: async () => [], platform: 'darwin', onAction() {} };
  const view = render(<FileTree source={source as any} activePath={null} onOpen={() => {}} />);
  // Nothing open, nobody has moved: nothing tinted.
  expect(highlighted()).toEqual([]);
  // notes.txt picked from the tree, then part.step opened from elsewhere (a tab, a link).
  fireEvent.click(document.querySelector('[data-path="notes.txt"]')!);
  view.rerender(<FileTree source={source as any} activePath="notes.txt" onOpen={() => {}} />);
  view.rerender(<FileTree source={source as any} activePath="part.step" onOpen={() => {}} />);
  expect(highlighted()).toEqual(['part.step']);
  // The keys start from the open file: it is the tree's Tab stop, and the arrow moves focus.
  const open = document.querySelector<HTMLElement>('[data-path="part.step"]')!;
  expect(open.tabIndex).toBe(0);
  act(() => open.focus());
  fireEvent.keyDown(open, { key: 'ArrowUp' });
  expect(document.activeElement).toBe(document.querySelector('[data-path="notes.txt"]'));
  expect(highlighted()).toEqual(['notes.txt', 'part.step']);
});

const treeSource = (extra: Record<string, unknown> = {}) => ({ rootName: 'project', expanded: new Set(), setExpanded() {}, listings: LISTINGS,
  load: noLoad, revision: 0, paths: async () => [], platform: 'darwin', onAction() {}, ...extra });
const row = (path: string) => document.querySelector<HTMLElement>(`[role=treeitem][data-path="${path}"]`)!;

it('keys act only on the focused row: nothing is renamed, trashed or opened from the list itself', () => {
  const trash = vi.fn(async () => true);
  const onOpen = vi.fn();
  render(<FileTree source={treeSource({ trash, rename: async () => null }) as any} activePath={null} onOpen={onOpen} />);
  const tree = screen.getByRole('tree');
  // The list is not a Tab stop, and a key that reaches it acts on no row.
  expect(tree.tabIndex).toBe(-1);
  fireEvent.keyDown(tree, { key: 'Backspace', metaKey: true });
  fireEvent.keyDown(tree, { key: 'Enter' });
  fireEvent.keyDown(tree, { key: 'F2' });
  expect(trash).not.toHaveBeenCalled();
  expect(onOpen).not.toHaveBeenCalled();
  expect(document.querySelectorAll('input')).toHaveLength(1); // the filter; no rename field
  // Nor does ⌘⌫ in the filter box: there it deletes text.
  fireEvent.keyDown(screen.getByRole('combobox', { name: 'Filter files' }), { key: 'Backspace', metaKey: true });
  expect(trash).not.toHaveBeenCalled();
});

it('is one Tab stop, and F2 renames the row with focus after the arrows moved it', () => {
  render(<FileTree source={treeSource({ rename: async () => null }) as any} activePath={null} onOpen={() => {}} />);
  const stops = () => [...document.querySelectorAll<HTMLElement>('[role=tree] [data-path]')].filter((element) => element.tabIndex === 0);
  expect(stops()).toHaveLength(1);
  act(() => row('notes.txt').focus());
  expect(stops()).toEqual([row('notes.txt')]);
  fireEvent.keyDown(row('notes.txt'), { key: 'ArrowDown' });
  expect(document.activeElement).toBe(row('part.step'));
  expect(stops()).toEqual([row('part.step')]);
  fireEvent.keyDown(document.activeElement!, { key: 'F2' });
  const field = screen.getByLabelText('Rename part.step');
  expect(document.activeElement).toBe(field);
  // The field's row is a row of the tree (aria-required-children).
  expect(field.closest('[role=tree] > * [role=treeitem], [role=tree] > [role=treeitem]')).not.toBeNull();
});

it('⌘⌫ trashes the row with focus, says so, and hands focus to the next row', async () => {
  const trash = vi.fn(async () => true);
  render(<FileTree source={treeSource({ trash }) as any} activePath={null} onOpen={() => {}} />);
  act(() => row('notes.txt').focus());
  fireEvent.keyDown(row('notes.txt'), { key: 'Backspace', metaKey: true });
  expect(trash).toHaveBeenCalledWith({ path: 'notes.txt', kind: 'file' });
  await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Moved notes.txt to the Trash'));
  expect(document.activeElement).toBe(row('part.step'));
});

it('the filter is a combobox over a listbox of matches, naming the one Enter opens', async () => {
  const onOpen = vi.fn();
  render(<Tree onOpen={onOpen} />);
  const filter = screen.getByRole('combobox', { name: 'Filter files' });
  filter.focus();
  expect(filter.getAttribute('aria-expanded')).toBe('false');
  fireEvent.change(filter, { target: { value: 'step' } });
  await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(2));
  const listbox = screen.getByRole('listbox');
  expect(filter.getAttribute('aria-expanded')).toBe('true');
  expect(filter.getAttribute('aria-controls')).toBe(listbox.id);
  expect(screen.queryByRole('tree')).toBeNull();
  const [first, second] = screen.getAllByRole('option');
  expect(filter.getAttribute('aria-activedescendant')).toBe(first!.id);
  expect(first.getAttribute('aria-selected')).toBe('true');
  fireEvent.keyDown(filter, { key: 'ArrowDown' });
  expect(filter.getAttribute('aria-activedescendant')).toBe(second!.id);
  expect(second.getAttribute('aria-selected')).toBe('true');
  expect(document.activeElement).toBe(filter);
  fireEvent.keyDown(filter, { key: 'Enter' });
  expect(onOpen).toHaveBeenCalledWith(second!.dataset.path);
});

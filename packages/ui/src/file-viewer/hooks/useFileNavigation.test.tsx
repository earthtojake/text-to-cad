import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { useFileNavigation } from './useFileNavigation.js';
import type { FileChanges, FileEntry, FileSource, FileViewerState } from '../types.js';
afterEach(cleanup);
const entry = (path: string): FileEntry => ({ path, name: path.split('/').pop()!, kind: 'file' });
function source(id: string): FileSource { return { id, rootName: id, stat: async path => ({ ...entry(path), size: 0, extension: '' }) }; }
const initialState: FileViewerState = { panel: 'tree', panelWidth: 300, expandedDirectories: [''] };

test('late directory and search replies cannot populate another source', async () => {
  let finishList!: (files: FileEntry[]) => void, finishSearch!: (paths: string[]) => void;
  const a = { ...source('a'), list: vi.fn(() => new Promise<FileEntry[]>(resolve => { finishList = resolve; })), paths: vi.fn(() => new Promise<string[]>(resolve => { finishSearch = resolve; })) };
  const b = { ...source('b'), list: vi.fn(async () => [entry('b.txt')]) };
  const onStateChange = vi.fn(), onOpenFile = vi.fn();
  const { result, rerender } = renderHook(({ files }) => useFileNavigation({ source: files, state: initialState, onStateChange, onOpenFile, path: null }), { initialProps: { files: a as FileSource } });
  let search!: Promise<readonly string[]>;
  act(() => { search = result.current.tree.paths!(); });
  rerender({ files: b });
  await waitFor(() => expect(result.current.tree.listings['']).toEqual([entry('b.txt')]));
  await act(async () => { finishList([entry('a.txt')]); finishSearch(['a.txt']); expect(await search).toEqual([]); });
  expect(result.current.tree.listings['']).toEqual([entry('b.txt')]);
});

test('typed directory moves preserve expansion and navigate the current file; deletion prunes all descendants', async () => {
  let notify!: (changes: FileChanges) => void;
  const files = { ...source('root'), list: vi.fn(async (directory: string) => [entry(`${directory}/note.txt`)]), subscribe(listener: (changes: FileChanges) => void) { notify = listener; return () => {}; } };
  const open = vi.fn();
  const { result } = renderHook(() => {
    const [state, onStateChange] = useState<FileViewerState>({ ...initialState, expandedDirectories: ['', 'old', 'old/deep'] });
    return useFileNavigation({ source: files, state, onStateChange, onOpenFile: open, path: 'old/deep/note.txt' });
  });
  await waitFor(() => expect(result.current.tree.listings['old/deep']).toBeDefined());
  act(() => notify({ sourceId: files.id, changes: [{ kind: 'moved', from: 'old', to: 'new', entryKind: 'directory' }] }));
  expect(open).toHaveBeenCalledWith('new/deep/note.txt', { target: 'current' });
  expect([...result.current.tree.expanded]).toEqual(['', 'new', 'new/deep']);
  await waitFor(() => expect(result.current.tree.listings['new/deep']).toEqual([entry('new/deep/note.txt')]));
  act(() => notify({ sourceId: files.id, changes: [{ kind: 'deleted', path: 'new', entryKind: 'directory' }] }));
  expect([...result.current.tree.expanded]).toEqual(['']);
  expect(result.current.tree.listings['new/deep']).toBeUndefined();
});

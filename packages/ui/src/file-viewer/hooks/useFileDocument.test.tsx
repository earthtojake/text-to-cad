import { StrictMode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { useFileDocument } from './useFileDocument.js';
import type { DocumentSaveResult, FileChanges, FileSource, PrepareContext, RendererRegistration, WriteResult } from '../types.js';

afterEach(cleanup);

test('source changes and explicit reloads refresh renderer metadata; navigating between files keeps warm preparation', async () => {
  const preparations: PrepareContext[] = [];
  const listeners = new Set<Parameters<NonNullable<FileSource['subscribe']>>[0]>();
  const source: FileSource = {
    id: 'workspace', rootName: 'models',
    stat: async (path) => ({ path, name: path, kind: 'file', size: 0, extension: 'step' }),
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
  const renderers: RendererRegistration[] = [{
    id: 'cad', priority: 1, matches: () => true,
    async prepare(context) { preparations.push(context); return { Component: () => null }; },
  }];
  const { result, rerender } = renderHook(({ path }) => useFileDocument(path, source, renderers), {
    initialProps: { path: 'one.step' }, wrapper: StrictMode,
  });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(false);
  act(() => { for (const listener of listeners) listener({ sourceId: source.id, changes: [{ kind: 'content', path: 'one.step' }] }); });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(true);
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(true);
  rerender({ path: 'two.step' });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.file.path).toBe('two.step');
  expect(preparations.at(-1)?.refresh).toBe(false);
  rerender({ path: 'one.step' });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(false);
});

function editable() {
  const listeners = new Set<(change: FileChanges) => void>();
  const contents = new Map([['one.txt', { content: 'one', revision: 'r1' }], ['two.txt', { content: 'two', revision: 'r2' }]]);
  const write = vi.fn<NonNullable<FileSource['writeText']>>();
  const source: FileSource = { id: 'workspace', rootName: 'root', writeText: write,
    stat: vi.fn(async path => ({ path, name: path, kind: 'file' as const, size: 3, extension: 'txt' })),
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; } };
  const renderers: RendererRegistration[] = [{ id: 'text', priority: 0, matches: () => true,
    prepare: vi.fn(async ({ file }) => ({ Component: () => null, text: contents.get(file.path)! })) }];
  const emit = (changes: FileChanges['changes']) => { for (const listener of listeners) listener({ sourceId: source.id, changes }); };
  const hook = renderHook(({ path }) => useFileDocument(path, source, renderers), { initialProps: { path: 'one.txt' } });
  return { ...hook, source, write, contents, renderers, emit };
}

test('typing during a save survives; a structured conflict preserves the draft', async () => {
  const { result, write } = editable();
  await waitFor(() => expect(result.current.document?.value).toBe('one'));
  let complete!: (result: WriteResult) => void;
  write.mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  act(() => result.current.document!.setValue('submitted'));
  let saving!: Promise<DocumentSaveResult>;
  act(() => { saving = result.current.document!.save(); });
  act(() => result.current.document!.setValue('typed while saving'));
  await act(async () => { complete({ status: 'saved', document: { content: 'submitted', revision: 'r3' } }); await saving; });
  expect(result.current.document).toMatchObject({ value: 'typed while saving', dirty: true, revision: 'r3', saving: false });
  write.mockResolvedValue({ status: 'conflict', actualRevision: 'external', message: 'any host wording' });
  await act(() => result.current.document!.save());
  expect(result.current.document).toMatchObject({ value: 'typed while saving', dirty: true, stale: true });
});

test('a cancelled but committed save cannot overwrite a different document', async () => {
  const { result, rerender, write } = editable();
  await waitFor(() => expect(result.current.document?.value).toBe('one'));
  let complete!: (result: WriteResult) => void;
  write.mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  act(() => result.current.document!.setValue('submitted'));
  let saving!: Promise<DocumentSaveResult>;
  act(() => { saving = result.current.document!.save(); });
  rerender({ path: 'two.txt' });
  await waitFor(() => expect(result.current.document?.value).toBe('two'));
  expect(write.mock.calls[0][1].signal.aborted).toBe(true);
  await act(async () => { complete({ status: 'saved', document: { content: 'submitted', revision: 'r3' } }); await saving; });
  expect(result.current.document).toMatchObject({ value: 'two', dirty: false, revision: 'r2' });
});

test('external metadata leaves a draft alone; rename carries it and deletion marks it stale', async () => {
  const { result, rerender, contents, source, emit } = editable();
  await waitFor(() => expect(result.current.document?.value).toBe('one'));
  act(() => result.current.document!.setValue('unsaved'));
  const reads = vi.mocked(source.stat).mock.calls.length;
  act(() => emit([{ kind: 'metadata', path: 'one.txt' }]));
  expect(vi.mocked(source.stat).mock.calls).toHaveLength(reads);
  contents.set('renamed.txt', contents.get('one.txt')!);
  act(() => emit([{ kind: 'moved', from: 'one.txt', to: 'renamed.txt', entryKind: 'file' }]));
  rerender({ path: 'renamed.txt' });
  await waitFor(() => expect(result.current.document?.value).toBe('unsaved'));
  expect(result.current.document).toMatchObject({ dirty: true, stale: false, revision: 'r1' });
  act(() => emit([{ kind: 'deleted', path: 'renamed.txt', entryKind: 'file' }]));
  expect(result.current.document).toMatchObject({ value: 'unsaved', dirty: true, stale: true });
});

test('external content refreshes clean documents and retains dirty drafts', async () => {
  const { result, contents, emit } = editable();
  await waitFor(() => expect(result.current.document?.value).toBe('one'));
  contents.set('one.txt', { content: 'external', revision: 'r3' });
  act(() => emit([{ kind: 'content', path: 'one.txt', revision: 'r3' }]));
  await waitFor(() => expect(result.current.document?.value).toBe('external'));
  act(() => result.current.document!.setValue('my draft'));
  contents.set('one.txt', { content: 'new external', revision: 'r4' });
  act(() => emit([{ kind: 'content', path: 'one.txt', revision: 'r4' }]));
  expect(result.current.document).toMatchObject({ value: 'my draft', stale: true });
});

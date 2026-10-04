import { StrictMode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { useFileDocument } from './useFileDocument.js';
import type { FileChanges, FileSource, PrepareContext, RendererRegistration } from '../types.js';

afterEach(cleanup);

// A source whose changes a test announces, and a renderer that records each preparation.
function watched(live: boolean) {
  const preparations: PrepareContext[] = [];
  const listeners = new Set<(change: FileChanges) => void>();
  const source: FileSource = {
    id: 'local',
    stat: async (path) => ({ path, name: path.split('/').pop()!, kind: 'file', size: 0, extension: 'step' }),
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
  const renderers: RendererRegistration[] = [{
    id: 'cad', priority: 1, matches: () => true,
    async prepare(context) { preparations.push(context); return { Component: () => null, live }; },
  }];
  const emit = (changes: FileChanges['changes']) => act(() => { for (const listener of listeners) listener({ sourceId: source.id, changes }); });
  return { source, renderers, preparations, emit };
}

test('source changes and explicit reloads refresh renderer metadata; navigating between files keeps warm preparation', async () => {
  const { source, renderers, preparations, emit } = watched(false);
  const { result, rerender } = renderHook(({ path }) => useFileDocument(path, source, renderers), {
    initialProps: { path: '/models/one.step' }, wrapper: StrictMode,
  });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(false);
  // Compiler progress is metadata, and another file's revision is not this one's: neither reopens it.
  const key = result.current.key;
  emit([{ kind: 'metadata', path: '/models/one.step' }, { kind: 'content', path: '/models/other.step' }]);
  expect(result.current.key).toBe(key);
  emit([{ kind: 'content', path: '/models/one.step' }]);
  expect(result.current.key).not.toBe(key);
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(true);
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(true);
  rerender({ path: '/models/two.step' });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.file.path).toBe('/models/two.step');
  expect(preparations.at(-1)?.refresh).toBe(false);
  rerender({ path: '/models/one.step' });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(false);
});

test('a live document stays open when its file changes, for its renderer follows the file; a reload still opens it again', async () => {
  const { source, renderers, preparations, emit } = watched(true);
  const { result } = renderHook(() => useFileDocument('/models/one.step', source, renderers), { wrapper: StrictMode });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  const opened = { key: result.current.key, preparations: preparations.length };
  emit([{ kind: 'content', path: '/models/one.step', revision: 'r2' }]);
  expect([result.current.key, result.current.loaded.status, preparations.length]).toEqual([opened.key, 'ready', opened.preparations]);
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.key).not.toBe(opened.key));
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(true);
});

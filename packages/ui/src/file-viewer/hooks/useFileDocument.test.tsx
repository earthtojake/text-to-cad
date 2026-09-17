import { StrictMode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { useFileDocument } from './useFileDocument.js';
import type { FileSource, PrepareContext, RendererRegistration } from '../types.js';

afterEach(cleanup);

test('source changes and explicit reloads refresh renderer metadata; navigating between files keeps warm preparation', async () => {
  const preparations: PrepareContext[] = [];
  const listeners = new Set<Parameters<NonNullable<FileSource['subscribe']>>[0]>();
  const source: FileSource = {
    id: 'workspace', rootName: 'models',
    stat: async (path) => ({ path, name: path, kind: 'file' }),
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
  act(() => { for (const listener of listeners) listener({ sourceId: source.id, paths: ['one.step'] }); });
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

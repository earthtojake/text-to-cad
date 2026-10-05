import { StrictMode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { useFileDocument } from './useFileDocument.js';
import type { FileSource, PrepareContext, RendererRegistration } from '../types.js';

afterEach(cleanup);

test('an explicit reload refreshes the file it opens again; navigating between files keeps warm preparation', async () => {
  // A renderer that records each preparation.
  const preparations: PrepareContext[] = [];
  const source: FileSource = {
    id: 'local',
    stat: async (path) => ({ path, name: path.split('/').pop()!, kind: 'file', size: 0, extension: 'step' }),
  };
  const renderers: RendererRegistration[] = [{
    id: 'cad', priority: 1, matches: () => true,
    async prepare(context) { preparations.push(context); return { Component: () => null }; },
  }];
  const { result, rerender } = renderHook(({ path }) => useFileDocument(path, source, renderers), {
    initialProps: { path: '/models/one.step' }, wrapper: StrictMode,
  });
  await waitFor(() => expect(result.current.loaded.status).toBe('ready'));
  expect(preparations.at(-1)?.refresh).toBe(false);
  const key = result.current.key;
  act(() => result.current.reload());
  expect(result.current.key).not.toBe(key);
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

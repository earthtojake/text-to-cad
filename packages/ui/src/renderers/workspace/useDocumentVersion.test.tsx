import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useDocumentVersion } from '../../../dist/renderers/workspace/useDocumentVersion.js';

afterEach(cleanup);

const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';

it('a document held by its id reads its row again at each new version, and stops waiting when the view goes', async () => {
  const versions = ['1', '2'];
  const asked: string[] = [];
  let ended: AbortSignal | null = null;
  const client = {
    documentVersion: vi.fn(async (_file: string, after: string, { signal }: { signal: AbortSignal }) => {
      asked.push(after);
      ended = signal;
      // The engine answers at once with a version past `after`, then holds the ask until the view goes.
      const next = versions.shift();
      if (next) return { version: next };
      return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
    }),
    refresh: vi.fn(async () => ({ entries: [] })),
  };
  const view = renderHook(() => useDocumentVersion({ client, file: id }));
  await waitFor(() => expect(asked).toEqual(['', '1', '2']), { timeout: 5000 });
  expect(client.refresh.mock.calls.map(([options]) => (options as { file: string }).file)).toEqual([id, id]);
  view.unmount();
  expect(ended!.aborted).toBe(true);
});

it('a file is followed by the catalog: nothing waits on its version', () => {
  const client = { documentVersion: vi.fn(), refresh: vi.fn() };
  renderHook(() => useDocumentVersion({ client, file: '/models/scene.glb' }));
  expect(client.documentVersion).not.toHaveBeenCalled();
});

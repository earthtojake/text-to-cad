import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { loadXbfDocument } from '@text-to-cad/core/lib/xbf/xbfDocument.js';
import { useXbfScene } from './useXbfScene.js';

// Keep geometry out of this connection test. Version polling still uses the real
// waitForXbfVersion -> getJson -> fetch path whose rejection the hook must own.
vi.mock('@text-to-cad/core/lib/xbf/xbfDocument.js', async importOriginal => ({
  ...await importOriginal(), loadXbfDocument: vi.fn(),
}));
vi.mock('@text-to-cad/core/lib/xbf/xbfScene.js', () => ({
  createXbfScene: () => ({ dispose: vi.fn() }),
}));

afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });

for (const reconnects of [true, false]) {
  it(`catches a version fetch TypeError and ${reconnects ? 'resumes polling the replacement document' : 'presents a failed reconnection'}`, async () => {
    vi.useFakeTimers();
    const versionFailure = new TypeError('Failed to fetch');
    const reconnectFailure = new Error('The engine refused the document');
    const fetch = vi.fn((_url: string, { signal }: { signal: AbortSignal }) => {
      if (fetch.mock.calls.length === 1) return Promise.reject(versionFailure);
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      });
    });
    const served = { url: 'https://cad.test/api/doc/one', fetch };
    const client = { engineDocument: vi.fn().mockResolvedValueOnce(served) };
    if (reconnects) client.engineDocument.mockResolvedValueOnce(served);
    else client.engineDocument.mockRejectedValueOnce(reconnectFailure);
    const document = (version: string) => ({
      version, source: { url: served.url, origin: 'https://cad.test', base: 'https://cad.test', doc: 'one' },
      structure: { instances: [{}] }, parts: new Map(), look: {}, fetch: globalThis.fetch,
      load: { fetched: [], kept: [], structureMs: 0, partsMs: 0, bytes: 0 }, release: vi.fn(),
    });
    vi.mocked(loadXbfDocument).mockResolvedValueOnce(document('v1')).mockResolvedValueOnce(document('v2'));
    const hook = renderHook(() => useXbfScene({ client, file: 'one' }));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const previous = hook.result.current.scene;
    expect(previous).not.toBeNull();
    expect(hook.result.current).toMatchObject({ revision: 'v1', busy: false, error: null });

    // Advance only the retry timer; a rejected version read must retain the
    // previous scene and either recover or surface the host's reconnection error.
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(client.engineDocument).toHaveBeenCalledTimes(2);
    if (reconnects) {
      expect(hook.result.current).toMatchObject({ revision: 'v2', busy: false, error: null });
      expect(hook.result.current.scene).not.toBe(previous);
      expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('after=v2'), expect.anything());
    } else {
      expect(hook.result.current.scene).toBe(previous);
      expect(hook.result.current).toMatchObject({ revision: 'v1', busy: false, error: reconnectFailure });
    }
    hook.unmount();
  });
}

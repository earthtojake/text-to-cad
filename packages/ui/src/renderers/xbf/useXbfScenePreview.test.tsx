import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { loadXbfDocument } from '@cad/core/lib/xbf/xbfDocument.js';
import { useXbfScene } from './useXbfScene.js';

// A model's preview of other values of its parameters, drawn in the document's place: read with the
// document's parts as `previous`, never the document itself, and the document's own scene back when
// it is let go. No geometry: the reads and the scenes are stand-ins.
vi.mock('@cad/core/lib/xbf/xbfDocument.js', async importOriginal => ({
  ...await importOriginal(), loadXbfDocument: vi.fn(),
}));
vi.mock('@cad/core/lib/xbf/xbfScene.js', () => ({
  createXbfScene: (_three: unknown, document: { version: string }) => ({ of: document.version, dispose: vi.fn() }),
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('a preview is drawn in the document\'s place, read beside its parts, and the document is drawn again when it is let go', async () => {
  // The version wait never answers: the document stays v1 throughout.
  const fetch = vi.fn((_url: string, { signal }: { signal: AbortSignal }) => new Promise<Response>((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  const served = { url: 'https://cad.test/api/v1/documents/model/one', fetch };
  const client = { engineDocument: vi.fn().mockResolvedValue(served) };
  const part = (key: string) => ({ key, retain: vi.fn(), release: vi.fn() });
  const read = (version: string, keys: string[]) => ({
    version, source: { url: served.url, origin: 'https://cad.test', base: 'https://cad.test', doc: 'one', kind: 'model' },
    structure: { instances: [{}] }, parts: new Map(keys.map(key => [key, part(key)])), look: { looked: true }, fetch,
    load: { fetched: [], kept: [], structureMs: 0, partsMs: 0, bytes: 0 }, release: vi.fn(),
  });
  const base = read('v1', ['plate', 'rib']);
  const first = read('p1', ['plate', 'rib-2']);
  const second = read('p2', ['plate', 'rib-3']);
  vi.mocked(loadXbfDocument).mockResolvedValueOnce(base as never).mockResolvedValueOnce(first as never).mockResolvedValueOnce(second as never);
  const hook = renderHook(({ preview }: { preview: string | null }) => useXbfScene({ client, file: 'one', preview }), { initialProps: { preview: null } });
  await vi.waitFor(() => expect(hook.result.current.scene).toMatchObject({ of: 'v1' }));
  const own = hook.result.current.scene;

  hook.rerender({ preview: '/preview/1' });
  await vi.waitFor(() => expect(hook.result.current.scene).toMatchObject({ of: 'p1' }));
  // Read as a version is: the document's parts and look to keep, the document's fetch.
  const [url, options] = vi.mocked(loadXbfDocument).mock.calls[1] as [string, any];
  expect([url, [...options.previous.parts.keys()], options.previous.look, options.fetch]).toEqual(['/preview/1', ['plate', 'rib'], { looked: true }, fetch]);
  // Never the document: its document, revision and readiness are as they were; what is drawn is the preview.
  expect(hook.result.current).toMatchObject({ document: base, revision: 'v1', busy: false, previewing: '/preview/1', sceneRevision: 'p1' });

  // The next preview keeps the parts of the document and of the preview before it, and lets that one go.
  hook.rerender({ preview: '/preview/2' });
  await vi.waitFor(() => expect(hook.result.current.scene).toMatchObject({ of: 'p2' }));
  expect([...(vi.mocked(loadXbfDocument).mock.calls[2][1] as any).previous.parts.keys()]).toEqual(['plate', 'rib', 'rib-2']);
  expect([first.release.mock.calls.length, base.release.mock.calls.length]).toEqual([1, 0]);

  // Let go (Reset, a Save that landed): the document's own scene again, the preview released.
  const shownScene = hook.result.current.scene as { dispose: ReturnType<typeof vi.fn> };
  hook.rerender({ preview: null });
  expect(hook.result.current.scene).toBe(own);
  expect(hook.result.current).toMatchObject({ previewing: null, sceneRevision: 'v1', revision: 'v1' });
  expect([shownScene.dispose.mock.calls.length, second.release.mock.calls.length, base.release.mock.calls.length]).toEqual([1, 1, 0]);
  hook.unmount();
});

it('a preview that cannot be read leaves the scene on screen as it is', async () => {
  const fetch = vi.fn((_url: string, { signal }: { signal: AbortSignal }) => new Promise<Response>((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  const served = { url: 'https://cad.test/api/v1/documents/model/one', fetch };
  const client = { engineDocument: vi.fn().mockResolvedValue(served) };
  const base = { version: 'v1', source: { url: served.url, origin: 'https://cad.test', base: 'https://cad.test', doc: 'one', kind: 'model' },
    structure: { instances: [{}] }, parts: new Map(), look: {}, fetch, load: { fetched: [], kept: [], structureMs: 0, partsMs: 0, bytes: 0 }, release: vi.fn() };
  const gone = Object.assign(new Error('no such preview'), { status: 404 });
  vi.mocked(loadXbfDocument).mockResolvedValueOnce(base as never).mockRejectedValueOnce(gone);
  const hook = renderHook(({ preview }: { preview: string | null }) => useXbfScene({ client, file: 'one', preview }), { initialProps: { preview: null } });
  await vi.waitFor(() => expect(hook.result.current.scene).toMatchObject({ of: 'v1' }));
  const own = hook.result.current.scene;
  hook.rerender({ preview: '/preview/gone' });
  await vi.waitFor(() => expect(hook.result.current.previewError).toBe(gone));
  expect(hook.result.current).toMatchObject({ scene: own, previewing: null, error: null });
  hook.unmount();
});

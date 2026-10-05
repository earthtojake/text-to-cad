import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { createLiveRegistry } from '../host/liveRegistry.js';
import { THUMBNAIL_SIZE, useModelThumbnail } from './thumbnails.js';

afterEach(cleanup);

/** A mounted view showing `path`, whose picture comes when the test settles it. */
function view(path: string) {
  let settle!: (png: Blob) => void;
  return {
    readState: () => ({ active: true, loading: false, resource: { kind: 'workspace-file', path } }),
    capture: async () => new Blob(['screen']),
    thumbnail: vi.fn(() => new Promise<Blob>(resolve => { settle = resolve; })),
    settle: (png: Blob) => settle(png),
  };
}

test('the file on screen is pictured once its view settles, at the card\'s size, and a stale view never is', async () => {
  const live = createLiveRegistry();
  const save = vi.fn(async () => {});
  const { rerender } = renderHook(({ file }) => useModelThumbnail(live, file, 'r1', save), { initialProps: { file: '/models/a.step' as string | null } });
  const a = view('/models/a.step');
  act(() => { live.binding.bind(a); });
  expect(a.thumbnail).toHaveBeenCalledWith(THUMBNAIL_SIZE);
  await act(async () => a.settle(new Blob(['a'])));
  expect(save).toHaveBeenCalledWith(expect.any(Blob), '/models/a.step');
  // The host moved on to another file while the view still shows the old one: its picture is not the new file's.
  const b = view('/models/a.step');
  act(() => { live.binding.bind(b); });
  rerender({ file: '/models/b.step' });
  await act(async () => b.settle(new Blob(['still a'])));
  expect(save).toHaveBeenCalledTimes(1);
});

test('a model rebuilt while it is open is pictured again once its new revision settles, and only then', async () => {
  const live = createLiveRegistry();
  const save = vi.fn(async () => {});
  const { rerender } = renderHook(({ revision }) => useModelThumbnail(live, '/models/a.step', revision, save), { initialProps: { revision: 'r1' } });
  const a = view('/models/a.step');
  act(() => { live.binding.bind(a); });
  await act(async () => a.settle(new Blob(['r1'])));
  expect(save).toHaveBeenCalledTimes(1);
  rerender({ revision: 'r1' });
  expect(a.thumbnail).toHaveBeenCalledTimes(1);
  rerender({ revision: 'r2' });
  expect(a.thumbnail).toHaveBeenCalledTimes(2);
  await act(async () => a.settle(new Blob(['r2'])));
  expect(save).toHaveBeenCalledTimes(2);
});

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
  const { rerender } = renderHook(({ file }) => useModelThumbnail(live, file, save), { initialProps: { file: 'a.step' as string | null } });
  const a = view('a.step');
  act(() => { live.binding.bind(a); });
  expect(a.thumbnail).toHaveBeenCalledWith(THUMBNAIL_SIZE);
  await act(async () => a.settle(new Blob(['a'])));
  expect(save).toHaveBeenCalledWith(expect.any(Blob), 'a.step');
  // The host moved on to another file while the view still shows the old one: its picture is not the new file's.
  const b = view('a.step');
  act(() => { live.binding.bind(b); });
  rerender({ file: 'b.step' });
  await act(async () => b.settle(new Blob(['still a'])));
  expect(save).toHaveBeenCalledTimes(1);
});

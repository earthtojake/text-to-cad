import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ViewerFeatures } from '../file-viewer/types.js';
import { DEFAULT_FEATURES, useFeatures } from './useFeatures.js';

afterEach(cleanup);

/** A host's server: what it keeps, every call it is asked, and a way to hold or fail the next answer. */
function server(kept: ViewerFeatures = {}) {
  const calls: (Partial<ViewerFeatures> | undefined)[] = [];
  let next: ((change?: Partial<ViewerFeatures>) => Promise<ViewerFeatures>) | null = null;
  const features = vi.fn((change?: Partial<ViewerFeatures>) => {
    calls.push(change);
    const answer = next;
    next = null;
    if (answer) return answer(change);
    if (change) kept = { ...kept, ...change };
    return Promise.resolve({ quickEdit: true, ...kept });
  });
  return { features, calls, once(answer: (change?: Partial<ViewerFeatures>) => Promise<ViewerFeatures>) { next = answer; }, kept: () => kept };
}

it('Quick edit is on until the person turns it off: Settings shows it once the server has answered, and a click keeps the choice there', async () => {
  const host = server();
  const { result } = renderHook(() => useFeatures(host.features));
  // Before the server answers, Quick Edit is as it starts, and Settings offers no choice it could not keep.
  expect(result.current.features).toEqual({ quickEdit: true });
  expect(result.current.appSettings).toBeUndefined();
  await act(async () => {});
  expect(result.current.appSettings).toEqual([expect.objectContaining({ id: 'quickEdit', label: 'Quick edit', checked: true })]);
  await act(async () => result.current.appSettings![0].onCheckedChange(false));
  expect(host.calls).toEqual([undefined, { quickEdit: false }]);
  expect(result.current.features).toEqual({ quickEdit: false });
  expect(result.current.appSettings![0].checked).toBe(false);
  expect(host.kept()).toEqual({ quickEdit: false });
  expect(DEFAULT_FEATURES).toEqual({ quickEdit: true });
});

it('a choice another view made is read when the person comes back, a change never lost to a read sent before it, and one that failed read back', async () => {
  const host = server({ quickEdit: false });
  const { result } = renderHook(() => useFeatures(host.features));
  await act(async () => {});
  expect(result.current.features.quickEdit).toBe(false);
  // Another tab turned it back on: this one hears of it when the page is focused again.
  host.kept().quickEdit = true;
  await act(async () => { window.dispatchEvent(new Event('focus')); });
  expect(result.current.features.quickEdit).toBe(true);
  // The click's own focus sends a read that answers late, with the old value: the click stands.
  let releaseStaleRead: (value: ViewerFeatures) => void = () => {};
  host.once(() => new Promise(resolve => { releaseStaleRead = resolve; }));
  act(() => { window.dispatchEvent(new Event('focus')); });
  await act(async () => result.current.appSettings![0].onCheckedChange(false));
  await act(async () => releaseStaleRead({ quickEdit: true }));
  expect(result.current.features.quickEdit).toBe(false);
  // A change the server did not keep is read back rather than shown as kept.
  host.once(() => Promise.reject(new Error('unwritable')));
  await act(async () => result.current.appSettings![0].onCheckedChange(true));
  expect(result.current.features.quickEdit).toBe(false);
  // Only what this page knows, on or off, is taken from a reply.
  host.once(() => Promise.resolve({ quickEdit: 'yes', later: false } as unknown as ViewerFeatures));
  await act(async () => { window.dispatchEvent(new Event('focus')); });
  expect(result.current.features).toEqual({ quickEdit: true });
});

it('a view that cannot ask its server keeps every feature on and offers no choice', async () => {
  const { result } = renderHook(() => useFeatures(() => Promise.reject(new Error('no route'))));
  await act(async () => {});
  expect([result.current.features, result.current.appSettings]).toEqual([{ quickEdit: true }, undefined]);
});

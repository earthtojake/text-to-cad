import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ACTIVITY_DETAIL_INTERVAL_MS, useFileActivityReport } from '../../../../dist/renderers/cad/workbench/useFileActivityReport.js';

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const loading = (done: number, extra = {}) => ({ loading: true, label: 'Opening', tone: 'neutral', title: `${done} of 256 items complete in this stage.`, ...extra });
const report = (onActivityChange = vi.fn()) => ({ onActivityChange, ...renderHook(({ activity, publish }) => useFileActivityReport(activity, publish), {
  initialProps: { activity: loading(0) as any, publish: onActivityChange } }) });

it('a large assembly\'s per-component progress reaches the host a few times a second, never once per commit', () => {
  const { onActivityChange, rerender } = report();
  expect(onActivityChange.mock.calls).toEqual([[loading(0)]]);
  for (let done = 1; done <= 120; done += 1) rerender({ activity: loading(done), publish: onActivityChange });
  // The regression: each of these commits published from its passive effects,
  // and the host update it scheduled tripped React's nested-update limit.
  expect(onActivityChange).toHaveBeenCalledTimes(1);
  act(() => { vi.advanceTimersByTime(ACTIVITY_DETAIL_INTERVAL_MS); });
  expect(onActivityChange.mock.calls).toEqual([[loading(0)], [loading(120)]]);
  rerender({ activity: loading(121), publish: onActivityChange });
  act(() => { vi.advanceTimersByTime(ACTIVITY_DETAIL_INTERVAL_MS); });
  expect(onActivityChange).toHaveBeenLastCalledWith(loading(121));
});

it('a status change is published in its own commit and supersedes pending detail', () => {
  const { onActivityChange, rerender } = report();
  rerender({ activity: loading(5), publish: onActivityChange });
  const failed = { loading: false, label: 'Open failed', tone: 'error', title: 'The viewer couldn’t prepare this file for display.', onActivate() {} };
  for (const next of [loading(5, { label: 'Updating' }), loading(5, { label: 'Updating', tone: 'info' }), failed, null]) {
    rerender({ activity: next, publish: onActivityChange });
    expect(onActivityChange).toHaveBeenLastCalledWith(next);
  }
  const published = onActivityChange.mock.calls.length;
  act(() => { vi.advanceTimersByTime(ACTIVITY_DETAIL_INTERVAL_MS * 2); });
  expect(onActivityChange).toHaveBeenCalledTimes(published);
});

it('clears the host on unmount and republishes to a new host callback, dropping pending detail', () => {
  const { onActivityChange, rerender, unmount } = report();
  rerender({ activity: loading(9), publish: onActivityChange });
  const next = vi.fn();
  rerender({ activity: loading(9), publish: next });
  expect(onActivityChange).toHaveBeenLastCalledWith(null);
  expect(next.mock.calls).toEqual([[loading(9)]]);
  rerender({ activity: loading(10), publish: next });
  unmount();
  expect(next).toHaveBeenLastCalledWith(null);
  act(() => { vi.advanceTimersByTime(ACTIVITY_DETAIL_INTERVAL_MS * 2); });
  expect(next).toHaveBeenCalledTimes(2);
  expect(onActivityChange).toHaveBeenCalledTimes(2);
});

import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useEditingPreview } from '../../../../../../dist/renderers/step/components/workbench/hooks/useEditingPreview.js';

afterEach(() => cleanup());

// The feed is polled; while it is down every poll fails the same way. Each failure used to
// publish a new state, re-rendering the whole STEP surface (and its tree) once per poll.
it('keeps its state across repeated identical failures and identical updates', () => {
  let update: (next: unknown) => void = () => {}, fail: (error: Error) => void = () => {};
  const client = { observeEditingPreview: (_file: string, onUpdate: any, onError: any) => { update = onUpdate; fail = onError; return () => {}; } };
  const { result } = renderHook(() => useEditingPreview('part.step', { enabled: true, client }));
  act(() => fail(new Error('offline')));
  const failed = result.current.state;
  expect(failed.error).toBe('offline');
  act(() => fail(new Error('offline')));
  act(() => fail(new Error('offline')));
  expect(result.current.state).toBe(failed);
  // A different failure is news.
  act(() => fail(new Error('refused')));
  expect(result.current.state).not.toBe(failed);
  expect(result.current.state.error).toBe('refused');
  // As is recovery; the same update twice is not.
  act(() => update({ epoch: 'e1', revision: 1, state: 'ready' }));
  const ready = result.current.state;
  act(() => update({ epoch: 'e1', revision: 1, state: 'ready' }));
  expect(result.current.state).toBe(ready);
});

// The view shows the saved file: when a build finishes, or the file moves past one, the catalog is
// read at once, so the saved file replaces the one on screen without waiting for its next poll.
it('reads the catalog again at once when a build finishes or the file moves past it', () => {
  let update: (next: unknown) => void = () => {};
  const refreshes: unknown[] = [];
  const client = {
    observeEditingPreview: (_file: string, onUpdate: any) => { update = onUpdate; return () => {}; },
    refresh: (options: unknown) => { refreshes.push(options); return Promise.resolve(); },
  };
  const { result } = renderHook(() => useEditingPreview('part.step', { enabled: true, client }));
  act(() => update({ epoch: 'e1', revision: 1, state: 'building' }));
  expect(refreshes).toEqual([]);
  act(() => update({ epoch: 'e1', revision: 1, state: 'done' }));
  expect(refreshes).toEqual([{ file: 'part.step', markRefreshing: false }]);
  act(() => update({ epoch: 'e1', revision: 1, state: 'done', superseded: true }));
  expect(refreshes).toHaveLength(1);
  // The next build is followed again, and its finish read again.
  act(() => update({ epoch: 'e1', revision: 2, state: 'building' }));
  act(() => update({ epoch: 'e1', revision: 2, state: 'failed', error: 'boom' }));
  expect(refreshes).toHaveLength(1);
  expect(result.current.state.error).toBe('boom');
  act(() => update({ epoch: 'e1', revision: 2, state: 'failed', superseded: true }));
  expect(refreshes).toHaveLength(2);
  expect(result.current.state.error).toBe('');
});

// A build records its result and writes the file after: the feed names the save the moment it
// lands, and the catalog is read then, before the build's done.
it('reads the catalog again the moment the feed names the saved file', () => {
  let update: (next: unknown) => void = () => {};
  const refreshes: unknown[] = [];
  const client = {
    observeEditingPreview: (_file: string, onUpdate: any) => { update = onUpdate; return () => {}; },
    refresh: (options: unknown) => { refreshes.push(options); return Promise.resolve(); },
  };
  renderHook(() => useEditingPreview('part.step', { enabled: true, client }));
  act(() => update({ epoch: 'e1', revision: 3, state: 'building', saved: null }));
  expect(refreshes).toEqual([]);
  act(() => update({ epoch: 'e1', revision: 3, state: 'building', saved: { tree: 't'.repeat(64), documentHash: 'd'.repeat(64) } }));
  expect(refreshes).toEqual([{ file: 'part.step', markRefreshing: false }]);
  act(() => update({ epoch: 'e1', revision: 3, state: 'building', saved: { tree: 't'.repeat(64), documentHash: 'd'.repeat(64) } }));
  expect(refreshes).toHaveLength(1);
  act(() => update({ epoch: 'e1', revision: 3, state: 'done', saved: { tree: 't'.repeat(64), documentHash: 'd'.repeat(64) } }));
  expect(refreshes).toHaveLength(2);
});

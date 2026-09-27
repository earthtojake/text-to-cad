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

import React from 'react';
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEmbeddedGlbAnimationClock, EmbeddedGlbAnimationClockProvider } from '../../../../dist/renderers/cad/workbench/embeddedGlbAnimationClockStore.js';
import { useEmbeddedGlbAnimation } from '../../../../dist/renderers/cad/workbench/useEmbeddedGlbAnimation.js';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('GLB playback, document replacement and unmount stay within their renderer', () => {
  const frames = new Map<number, FrameRequestCallback>();
  let nextFrame = 0;
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { frames.set(++nextFrame, callback); return nextFrame; });
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => { frames.delete(id); });
  const firstClock = createEmbeddedGlbAnimationClock(), secondClock = createEmbeddedGlbAnimationClock();
  const document = { clips: [{ name: 'Open', duration: 5 }] };
  const first = renderHook(({ model }) => useEmbeddedGlbAnimation(model), {
    initialProps: { model: document }, wrapper: ({ children }) => <EmbeddedGlbAnimationClockProvider value={firstClock}>{children}</EmbeddedGlbAnimationClockProvider>,
  });
  const second = renderHook(() => useEmbeddedGlbAnimation(document), {
    wrapper: ({ children }) => <EmbeddedGlbAnimationClockProvider value={secondClock}>{children}</EmbeddedGlbAnimationClockProvider>,
  });
  act(() => { first.result.current!.onScrub(1); second.result.current!.onScrub(2); second.result.current!.onPlayToggle(); });
  expect(frames.size).toBe(1);
  act(() => {
    const scheduled = [...frames.values()]; frames.clear();
    scheduled.forEach(frame => frame(performance.now() + 100));
  });
  expect(secondClock.getAnimationClock()).toBeGreaterThan(2);
  const secondTime = secondClock.getAnimationClock();
  act(() => first.result.current!.onRestart());
  expect(firstClock.getAnimationClock()).toBe(0);
  expect(secondClock.getAnimationClock()).toBe(secondTime);
  first.rerender({ model: { clips: [{ name: 'Close', duration: 3 }] } });
  expect(secondClock.getAnimationClock()).toBe(secondTime);
  first.unmount();
  expect(frames.size).toBe(1);
  second.unmount();
  expect(frames.size).toBe(0);
});

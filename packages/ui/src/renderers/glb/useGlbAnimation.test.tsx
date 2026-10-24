import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useGlbAnimation } from '../../../dist/renderers/glb/useGlbAnimation.js';

afterEach(cleanup);

const clip = (name: string) => ({ name, duration: 2, tracks: [], userData: { cadgen: { duration: 2 } } });

it('every clip opens looping, a motion once that the player repeats, and the viewer\'s own Loop wins until put at rest', () => {
  const document = { scene: null, clips: [clip('nod'), clip('steer')] };
  const view = renderHook(() => useGlbAnimation(document, () => {}));
  expect(view.result.current!.clips.map((row: any) => row.label)).toEqual(['nod', 'steer']);
  expect(view.result.current!.loopEnabled).toBe(true);
  act(() => view.result.current!.onLoopToggle(false));
  expect(view.result.current!.loopEnabled).toBe(false);
  act(() => view.result.current!.resetPlayback());
  expect(view.result.current!.loopEnabled).toBe(true);
  act(() => view.result.current!.onLoopToggle(false));
  act(() => view.result.current!.onClipSelect('glb:1'));
  expect(view.result.current!.loopEnabled).toBe(true);
});

import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
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

// A renderer's own clip (a result's own routine) on the playbar's runtime: listed after the
// file's, posed by its own `apply` while it owns the model, and let go of with `release`.
it('plays a renderer\'s own clip through its apply, and lets go of it on release', () => {
  const apply = vi.fn();
  const release = vi.fn();
  const own = [{ id: 'own:routine', label: 'Routine', duration: 2, play: { apply, release } }];
  const requestRender = vi.fn();
  const { result } = renderHook(() => useGlbAnimation(null, requestRender, own));
  expect(result.current!.clips.map((clip: any) => clip.label)).toEqual(['Routine']);
  expect(apply).not.toHaveBeenCalled();
  act(() => { result.current!.onScrub(1.5); });
  expect(apply).toHaveBeenLastCalledWith(1.5);
  expect(requestRender).toHaveBeenCalled();
  act(() => { result.current!.onRelease(); });
  expect(release).toHaveBeenCalledTimes(1);
  expect(result.current!.enabled).toBe(false);
});

it('has no playbar for a file with no clips and none of the renderer\'s own', () => {
  const { result } = renderHook(() => useGlbAnimation(null, () => {}));
  expect(result.current).toBeNull();
});

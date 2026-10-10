import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useGlbAnimation } from '../../../dist/renderers/glb/useGlbAnimation.js';

// A renderer's own clip (an FEA result's Load ramp) on the playbar's runtime: listed after the
// file's, posed by its own `apply` while it owns the model, and let go of with `release`.
it('plays a renderer\'s own clip through its apply, and lets go of it on release', () => {
  const apply = vi.fn();
  const release = vi.fn();
  const own = [{ id: 'fea:load-ramp', label: 'Load ramp', duration: 2, play: { apply, release } }];
  const requestRender = vi.fn();
  const { result } = renderHook(() => useGlbAnimation(null, requestRender, own));
  expect(result.current!.clips.map((clip: any) => clip.label)).toEqual(['Load ramp']);
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

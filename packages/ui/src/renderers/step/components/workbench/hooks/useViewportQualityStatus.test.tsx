import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useViewportQualityStatus } from './useViewportQualityStatus.js';

afterEach(cleanup);

const snapshot = (overrides = {}) => ({
  modelKey: 'model.step:rev', file: 'model.step', componentCount: 3, standardSettled: false, quality: 'standard',
  qualitySettled: false, busy: false, pendingEvaluation: true, belowMinimum: 0, unmetTargets: [], ...overrides
});
const publish = (detail: object) => act(() => { window.dispatchEvent(new CustomEvent('cad:lod-status', { detail })); });

it('a camera sample that changes nothing the status reads does not re-render its host', () => {
  // The STEP surface hosts this hook. A preview orbit resamples the LOD camera on every frame and
  // the scheduler publishes a snapshot each time; while a model streams in, a re-render of the
  // surface per frame is what made preview sluggish.
  let renders = 0;
  const view = renderHook(() => {
    renders += 1;
    return useViewportQualityStatus({ modelKey: 'model.step:rev', file: 'model.step', hasGeometry: true,
      modelComplete: false, lodExpectedComponentCount: 3, quality: 'standard' });
  });
  publish(snapshot({ camera: { position: [0, 0, 0] } }));
  const settled = renders;
  expect(view.result.current.state).toBe('preview');

  // Sixty orbit frames: a new camera, new distances and visibility, the same status inputs.
  for (let frame = 1; frame <= 60; frame += 1) {
    publish(snapshot({ camera: { position: [frame, 0, 0] }, visibility: { visibleOccurrences: frame }, occupied: [] }));
  }
  expect(renders).toBe(settled);

  // A snapshot that changes what the status says is accepted at once.
  publish(snapshot({ busy: true }));
  expect(renders).toBe(settled + 1);
  publish(snapshot({ busy: true, unmetTargets: [{ cid: 'c1', reason: 'memory-denied' }] }));
  expect(view.result.current.state).toBe('limited');

  // Another model's snapshot never lands on this one.
  const before = renders;
  publish(snapshot({ modelKey: 'other.step:rev', busy: false }));
  expect(renders).toBe(before);
});

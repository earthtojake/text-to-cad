import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useViewportLoadStatus } from './useViewportLoadStatus.js';

afterEach(cleanup);

it('records first geometry, then the whole model, once per model', () => {
  const view = renderHook((props) => useViewportLoadStatus(props), {
    initialProps: { modelKey: 'model.step:one', hasGeometry: false, modelComplete: false },
  });
  expect(view.result.current).toMatchObject({ firstGeometry: false, complete: false, firstGeometryAt: null, completeAt: null });

  view.rerender({ modelKey: 'model.step:one', hasGeometry: true, modelComplete: false });
  const first = view.result.current.firstGeometryAt;
  expect(first).toEqual(expect.any(Number));
  expect(view.result.current.completeAt).toBeNull();

  view.rerender({ modelKey: 'model.step:one', hasGeometry: true, modelComplete: true });
  expect(view.result.current).toMatchObject({ complete: true, firstGeometryAt: first });
  expect(view.result.current.completeAt).toBeGreaterThanOrEqual(first);
  expect((window as any).__cadViewerLoad).toEqual(view.result.current);

  // Another revision starts its own timeline.
  view.rerender({ modelKey: 'model.step:two', hasGeometry: false, modelComplete: false });
  expect(view.result.current).toMatchObject({ modelKey: 'model.step:two', firstGeometryAt: null, completeAt: null });
});

import { act, renderHook } from '@testing-library/react';
import { expect, it } from 'vitest';
import { useMeasureSession } from '../../../../../dist/renderers/kit/tools/measure/useMeasureSession.js';
import { useViewerHistory } from '../../../../../dist/renderers/kit/shell/useViewerHistory.js';

it('each measurement taken, deleted or cleared is a step of the view\'s history, walked back and forth with the ink\'s', () => {
  const view = renderHook(() => {
    const history = useViewerHistory();
    const measure = useMeasureSession({ fileKey: 'a.step', revision: '1', picking: true });
    measure.history.current = history;
    return { history, measure };
  });
  const now = () => view.result.current;
  const count = () => now().measure.measurements.length;
  const measureBetween = (a: number[], b: number[]) => act(() => { now().measure.onPick({ point: a }); now().measure.onPick({ point: b }); });
  measureBetween([0, 0, 0], [3, 4, 0]);
  measureBetween([0, 0, 0], [6, 8, 0]);
  expect([count(), now().history.canUndo]).toEqual([2, true]);
  act(() => { now().history.undo(); });
  expect(count()).toBe(1);
  act(() => { now().history.redo(); });
  expect(count()).toBe(2);
  act(() => now().measure.onDelete(now().measure.measurements[0].id));
  expect(count()).toBe(1);
  act(() => now().measure.clear());
  expect(count()).toBe(0);
  act(() => { now().history.undo(); });
  expect(count()).toBe(1);
  act(() => { now().history.undo(); });
  expect(count()).toBe(2);
  // A pick that only starts or hovers a measurement is no step.
  act(() => { now().measure.onPick({ point: [9, 9, 9] }); now().measure.onHoverPoint({ point: [1, 1, 1] }); });
  act(() => { now().history.undo(); });
  expect(count()).toBe(1);
});

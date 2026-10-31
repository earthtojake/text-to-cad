import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import MeasurementCard from '../../../../../dist/renderers/kit/tools/measure/MeasurementCard.js';

afterEach(cleanup);

it("a measurement chip's card is its full reading: the distance, the delta, and what each end bound to", () => {
  const item = { measurement: { euclidean: 21.38, delta: [21.38, 0, 0], unit: 'mm' }, pickA: { snapKind: 'vertex' }, pickB: { snapKind: 'edge' } };
  const view = render(<MeasurementCard item={item} />);
  const rows = [...view.container.querySelectorAll('[data-info-row]')].map(row => row.textContent);
  expect(rows[0]).toBe('Distance21.38 mm');
  expect(rows[rows.length - 1]).toBe('BetweenVertex → Edge');
  expect(rows.some(row => row.startsWith('Delta'))).toBe(true);
});

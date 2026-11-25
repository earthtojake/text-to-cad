import { english } from '../../../../../dist/i18n/core.js';
import { expect, it } from 'vitest';
import { measurementFacts } from '../../../../../dist/renderers/kit/tools/measure/MeasurementCard.js';

it("a measurement chip's card is its full reading: the distance, the delta, and what each end bound to", () => {
  const item = { measurement: { euclidean: 21.38, delta: [21.38, 0, 0], unit: 'mm' }, pickA: { snapKind: 'vertex' }, pickB: { snapKind: 'edge' } };
  const facts = measurementFacts(item, english);
  expect([facts[0].label, facts[0].value]).toEqual(['Distance', '21.38 mm']);
  expect(facts.at(-1)!.label).toBe('Between');
  expect(facts.at(-1)!.copy).toBe(false);
  expect(facts.some(fact => fact.label === 'Delta')).toBe(true);
});

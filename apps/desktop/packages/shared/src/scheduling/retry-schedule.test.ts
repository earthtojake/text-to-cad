import { describe, expect, it } from 'vitest';
import { retrySchedule } from './retry-schedule';

describe('retrySchedule', () => {
  it('walks the delay sequence and exhausts past the end', () => {
    const schedule = retrySchedule({ delaysMs: [100, 250, 500] });

    expect(schedule.delayFor(0)).toBe(100);
    expect(schedule.delayFor(1)).toBe(250);
    expect(schedule.delayFor(2)).toBe(500);
    expect(schedule.delayFor(3)).toBeUndefined();
  });

  it('repeats the final delay when repeatLast is set', () => {
    const schedule = retrySchedule({ delaysMs: [100, 250], repeatLast: true });

    expect(schedule.delayFor(1)).toBe(250);
    expect(schedule.delayFor(50)).toBe(250);
  });

  it('caps retries at maxRetries even with repeatLast', () => {
    const schedule = retrySchedule({ delaysMs: [250, 1_000], repeatLast: true, maxRetries: 3 });

    expect(schedule.delayFor(2)).toBe(1_000);
    expect(schedule.delayFor(3)).toBeUndefined();
  });

  it('applies deterministic jitter around each delay', () => {
    const schedule = retrySchedule({
      delaysMs: [1_000],
      jitter: { ratio: 0.5, random: () => 1 },
    });

    expect(schedule.delayFor(0)).toBe(1_500);
  });
});

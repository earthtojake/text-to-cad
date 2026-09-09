import { describe, expect, it, vi } from 'vitest';
import { ManualClock } from './manual-clock';

describe('ManualClock', () => {
  it('fires timers in deadline and registration order', async () => {
    const clock = new ManualClock(100);
    const events: string[] = [];

    clock.schedule(20, () => events.push('third'));
    clock.schedule(10, () => events.push('first'));
    clock.schedule(10, () => events.push('second'));

    await clock.advanceBy(10);
    expect(clock.now()).toBe(110);
    expect(events).toEqual(['first', 'second']);

    await clock.advanceTo(120);
    expect(events).toEqual(['first', 'second', 'third']);
  });

  it('cancels timers before they fire', async () => {
    const clock = new ManualClock();
    const callback = vi.fn();
    const handle = clock.schedule(10, callback);

    handle.dispose();
    await clock.advanceBy(10);

    expect(callback).not.toHaveBeenCalled();
    expect(handle.active).toBe(false);
  });

  it('resolves sleeps when advanced', async () => {
    const clock = new ManualClock();
    const resolved = vi.fn();

    void clock.sleep(10).then(resolved);
    await clock.advanceBy(9);
    expect(resolved).not.toHaveBeenCalled();

    await clock.advanceBy(1);
    expect(resolved).toHaveBeenCalledTimes(1);
  });
});

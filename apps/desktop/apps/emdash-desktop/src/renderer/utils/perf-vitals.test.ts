import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import {
  startRendererPerfVitals,
  type RendererPerfEntry,
  type RendererPerfVitalsReport,
} from './perf-vitals';

type ObserverHandlers = Map<string, (entries: readonly RendererPerfEntry[]) => void>;

function fakeObserve(handlers: ObserverHandlers) {
  const disconnects: string[] = [];
  const observe = vi.fn(
    (
      options: { type: 'longtask' | 'event'; durationThreshold?: number },
      callback: (entries: readonly RendererPerfEntry[]) => void
    ) => {
      handlers.set(options.type, callback);
      return () => disconnects.push(options.type);
    }
  );
  return { observe, disconnects };
}

describe('startRendererPerfVitals', () => {
  it('registers no observers and no timers when the session is not sampled', async () => {
    const handlers: ObserverHandlers = new Map();
    const { observe } = fakeObserve(handlers);
    const clock = createManualClock(0);
    const schedule = vi.spyOn(clock, 'schedule');
    const capture = vi.fn();

    const vitals = await startRendererPerfVitals({
      isSampled: async () => false,
      observe,
      capture,
      clock,
    });

    expect(vitals.active).toBe(false);
    expect(observe).not.toHaveBeenCalled();
    expect(schedule).not.toHaveBeenCalled();
    await clock.advanceBy(3_600_000);
    expect(capture).not.toHaveBeenCalled();
  });

  it('treats a failing sampling probe as unsampled', async () => {
    const handlers: ObserverHandlers = new Map();
    const { observe } = fakeObserve(handlers);

    const vitals = await startRendererPerfVitals({
      isSampled: async () => {
        throw new Error('rpc unavailable');
      },
      observe,
      capture: vi.fn(),
      clock: createManualClock(0),
    });

    expect(vitals.active).toBe(false);
    expect(observe).not.toHaveBeenCalled();
  });

  it('aggregates long tasks and worst interaction latency per interval', async () => {
    const handlers: ObserverHandlers = new Map();
    const { observe } = fakeObserve(handlers);
    const clock = createManualClock(0);
    const reports: RendererPerfVitalsReport[] = [];

    const vitals = await startRendererPerfVitals({
      isSampled: async () => true,
      observe,
      capture: (report) => reports.push(report),
      clock,
      intervalMs: 300_000,
    });
    expect(vitals.active).toBe(true);

    handlers.get('longtask')!([
      { entryType: 'longtask', duration: 80 },
      { entryType: 'longtask', duration: 120.4 },
    ]);
    handlers.get('event')!([
      { entryType: 'event', duration: 90, interactionId: 7 },
      { entryType: 'event', duration: 400, interactionId: 9 },
      { entryType: 'event', duration: 900, interactionId: 0 },
    ]);

    await clock.advanceBy(300_000);
    expect(reports).toEqual([
      { long_tasks: 2, long_task_total_ms: 200, inp_ms: 400, interval_ms: 300_000 },
    ]);

    // Accumulators reset between intervals.
    await clock.advanceBy(300_000);
    expect(reports[1]).toEqual({
      long_tasks: 0,
      long_task_total_ms: 0,
      inp_ms: 0,
      interval_ms: 300_000,
    });

    vitals.dispose();
  });

  it('stops reporting and disconnects observers on dispose', async () => {
    const handlers: ObserverHandlers = new Map();
    const { observe, disconnects } = fakeObserve(handlers);
    const clock = createManualClock(0);
    const capture = vi.fn();

    const vitals = await startRendererPerfVitals({
      isSampled: async () => true,
      observe,
      capture,
      clock,
      intervalMs: 300_000,
    });

    vitals.dispose();
    await clock.advanceBy(900_000);
    expect(capture).not.toHaveBeenCalled();
    expect(disconnects.sort()).toEqual(['event', 'longtask']);
  });
});

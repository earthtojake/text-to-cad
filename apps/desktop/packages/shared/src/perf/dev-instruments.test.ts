import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Logger } from '../logger/types';
import { createManualClock } from '../testing';
import { startDevPerfInstruments } from './dev-instruments';
import { recordSpawn, resetSpawnCounts } from './spawn-metrics';

function stubLogger(level: Logger['level']): Logger & { debugCalls: unknown[][] } {
  const debugCalls: unknown[][] = [];
  const logger = {
    level,
    debugCalls,
    debug: (...args: unknown[]) => {
      debugCalls.push(args);
    },
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    child: () => logger,
  };
  return logger as unknown as Logger & { debugCalls: unknown[][] };
}

beforeEach(() => {
  resetSpawnCounts();
});

describe('startDevPerfInstruments', () => {
  it('creates no timer when the logger is not at debug level', async () => {
    const clock = createManualClock(0);
    const schedule = vi.spyOn(clock, 'schedule');

    const instruments = startDevPerfInstruments({ logger: stubLogger('info'), clock });

    expect(instruments.active).toBe(false);
    expect(schedule).not.toHaveBeenCalled();
    await clock.advanceBy(120_000);
    instruments.dispose();
  });

  it('logs spawn counts and rss per tick and drains counters between ticks', async () => {
    const clock = createManualClock(0);
    const logger = stubLogger('debug');
    const instruments = startDevPerfInstruments({ logger, clock, intervalMs: 60_000 });

    recordSpawn('git');
    recordSpawn('git');
    recordSpawn('fetch');
    await clock.advanceBy(60_000);

    expect(logger.debugCalls).toHaveLength(1);
    const [message, fields] = logger.debugCalls[0]! as [string, Record<string, unknown>];
    expect(message).toBe('perf.instruments');
    expect(fields.spawns).toEqual({ git: 2, fetch: 1 });
    expect(typeof fields.rssBytes).toBe('number');

    recordSpawn('tmux');
    await clock.advanceBy(60_000);
    const [, second] = logger.debugCalls[1]! as [string, Record<string, unknown>];
    expect(second.spawns).toEqual({ tmux: 1 });

    instruments.dispose();
    await clock.advanceBy(120_000);
    expect(logger.debugCalls).toHaveLength(2);
  });

  it('merges extra fields from the host process', async () => {
    const clock = createManualClock(0);
    const logger = stubLogger('debug');
    const instruments = startDevPerfInstruments({
      logger,
      clock,
      intervalMs: 1_000,
      extraFields: () => ({ appMetrics: [{ type: 'Browser', memoryKb: 42 }] }),
    });

    await clock.advanceBy(1_000);

    const [, fields] = logger.debugCalls[0]! as [string, Record<string, unknown>];
    expect(fields.appMetrics).toEqual([{ type: 'Browser', memoryKb: 42 }]);
    instruments.dispose();
  });
});

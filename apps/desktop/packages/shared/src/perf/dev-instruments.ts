import type { LogFields, Logger } from '../logger/types';
import { systemClock, type Clock } from '../scheduling';
import type { TimerHandle } from '../scheduling/timer-handle';
import { snapshotSpawnCounts } from './spawn-metrics';

export type DevPerfInstruments = {
  readonly active: boolean;
  dispose(): void;
};

export type StartDevPerfInstrumentsOptions = {
  logger: Logger;
  clock?: Clock;
  intervalMs?: number;
  /** Extra per-tick fields, e.g. Electron app metrics from the main process. */
  extraFields?: () => LogFields | undefined;
};

const DEFAULT_INTERVAL_MS = 60_000;

const inactive: DevPerfInstruments = { active: false, dispose() {} };

/**
 * Dev-only per-process performance instruments: once a minute, log the spawn
 * counts accumulated since the previous tick (spawns per minute by purpose)
 * and this process's RSS. Strictly gated on debug logging — when the logger is
 * not at debug level, no timer is created and nothing is sampled.
 */
export function startDevPerfInstruments(
  options: StartDevPerfInstrumentsOptions
): DevPerfInstruments {
  if (options.logger.level !== 'debug') return inactive;

  const clock = options.clock ?? systemClock;
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS;
  let timer: TimerHandle | null = null;
  let disposed = false;

  const tick = (): void => {
    if (disposed) return;
    options.logger.debug('perf.instruments', {
      intervalMs,
      spawns: snapshotSpawnCounts({ reset: true }),
      rssBytes: readOwnRss(),
      ...(options.extraFields?.() ?? {}),
    });
    schedule();
  };
  const schedule = (): void => {
    timer = clock.schedule(intervalMs, tick, { unref: true });
  };
  schedule();

  return {
    active: true,
    dispose() {
      disposed = true;
      timer?.dispose();
    },
  };
}

function readOwnRss(): number | null {
  const proc = (globalThis as { process?: { memoryUsage?: { rss?: () => number } } }).process;
  try {
    return proc?.memoryUsage?.rss?.() ?? null;
  } catch {
    return null;
  }
}

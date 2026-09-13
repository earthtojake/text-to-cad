import { monitorEventLoopDelay, performance, type IntervalHistogram } from 'node:perf_hooks';
import v8 from 'node:v8';
import { systemClock, type Clock } from '../../scheduling';
import type { TimerHandle } from '../../scheduling/timer-handle';
import { snapshotSpawnCounts, SPAWN_PURPOSES } from '../spawn-metrics';

/**
 * Numbers-only per-process performance vitals. Every value is a finite number
 * and every key comes from {@link PERF_VITALS_ALLOWED_KEYS}, so payloads pass
 * the telemetry property allowlist by construction — no paths, no command
 * lines, no free-form strings.
 */
export type ProcessVitals = Readonly<Record<string, number>>;

export const PERF_VITALS_ALLOWED_KEYS: readonly string[] = [
  'rss_mb',
  'heap_used_mb',
  'heap_total_mb',
  'detached_contexts',
  'cpu_percent',
  'elu_percent',
  'loop_delay_p95_ms',
  'loop_delay_max_ms',
  'interval_ms',
  ...SPAWN_PURPOSES.map((purpose) => `spawns_${purpose}`),
];

export type VitalsSampler = {
  /** Sample vitals accumulated since the previous call (or since creation). */
  sample(): ProcessVitals;
  dispose(): void;
};

/**
 * Continuous-sampling-safe process vitals: RSS, CPU since last sample,
 * event-loop delay/utilization, V8 heap statistics with the detached-context
 * count as a leak canary, and spawn-seam counters. All APIs used here are
 * documented safe for always-on sampling; the event-loop-delay histogram is
 * the only standing instrument and it is disposed with the sampler.
 */
export function createVitalsSampler(): VitalsSampler {
  const loopDelay: IntervalHistogram = monitorEventLoopDelay({ resolution: 20 });
  loopDelay.enable();
  let prevCpu = process.cpuUsage();
  let prevElu = performance.eventLoopUtilization();
  let prevHrtime = process.hrtime.bigint();

  return {
    sample(): ProcessVitals {
      const now = process.hrtime.bigint();
      const wallMicros = Number(now - prevHrtime) / 1_000;
      prevHrtime = now;

      const cpu = process.cpuUsage(prevCpu);
      prevCpu = process.cpuUsage();

      const elu = performance.eventLoopUtilization();
      const eluDelta = performance.eventLoopUtilization(elu, prevElu);
      prevElu = elu;

      const heap = v8.getHeapStatistics();
      const vitals: Record<string, number> = {
        rss_mb: bytesToMb(process.memoryUsage.rss()),
        heap_used_mb: bytesToMb(heap.used_heap_size),
        heap_total_mb: bytesToMb(heap.total_heap_size),
        detached_contexts: heap.number_of_detached_contexts,
        cpu_percent: wallMicros > 0 ? round1(((cpu.user + cpu.system) / wallMicros) * 100) : 0,
        elu_percent: round1(clamp01(eluDelta.utilization) * 100),
        loop_delay_p95_ms: nanosToMs(loopDelay.percentile(95)),
        loop_delay_max_ms: nanosToMs(loopDelay.max),
      };
      loopDelay.reset();

      const spawns = snapshotSpawnCounts({ reset: true });
      for (const purpose of SPAWN_PURPOSES) {
        const count = spawns[purpose];
        if (count !== undefined && count > 0) vitals[`spawns_${purpose}`] = count;
      }
      return vitals;
    },
    dispose() {
      loopDelay.disable();
    },
  };
}

export type VitalsReporting = {
  dispose(): void;
};

export type StartVitalsReportingOptions = {
  intervalMs: number;
  report(vitals: ProcessVitals): void;
  clock?: Clock;
};

/**
 * Sample and report process vitals on a fixed cadence. The timer is unref'd so
 * it never keeps a process alive. Callers own the decision to start this at
 * all — an unsampled or telemetry-disabled session must simply not call it.
 */
export function startVitalsReporting(options: StartVitalsReportingOptions): VitalsReporting {
  const clock = options.clock ?? systemClock;
  const sampler = createVitalsSampler();
  let timer: TimerHandle | null = null;
  let disposed = false;

  const tick = (): void => {
    if (disposed) return;
    options.report({ ...sampler.sample(), interval_ms: options.intervalMs });
    schedule();
  };
  const schedule = (): void => {
    timer = clock.schedule(options.intervalMs, tick, { unref: true });
  };
  schedule();

  return {
    dispose() {
      disposed = true;
      timer?.dispose();
      sampler.dispose();
    },
  };
}

function bytesToMb(bytes: number): number {
  return Math.round(bytes / (1024 * 1024));
}

function nanosToMs(nanos: number): number {
  return round1(nanos / 1_000_000);
}

function round1(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 10) / 10 : 0;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

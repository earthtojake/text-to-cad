import { startDevPerfInstruments, type DevPerfInstruments } from '@emdash/shared/perf';
import { app } from 'electron';
import { log } from '@main/lib/logger';

/**
 * Main-process dev performance instruments: per-minute spawn counts plus the
 * RSS of every Chromium-managed process (main, renderers, GPU) via
 * app.getAppMetrics(). Workers self-report through their own process logging
 * bootstrap. No-op unless debug logging is enabled.
 */
export function startMainDevPerfInstruments(): DevPerfInstruments {
  return startDevPerfInstruments({
    logger: log,
    extraFields: () => ({
      appMetrics: app.getAppMetrics().map((metric) => ({
        pid: metric.pid,
        type: metric.type,
        cpuPercent: Number(metric.cpu.percentCPUUsage.toFixed(1)),
        memoryWorkingSetKb: metric.memory.workingSetSize,
      })),
    }),
  });
}

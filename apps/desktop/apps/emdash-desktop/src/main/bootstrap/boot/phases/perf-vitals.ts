import { startVitalsReporting, type ProcessVitals } from '@emdash/shared/perf/node';
import { app } from 'electron';
import type { DesktopRuntimes } from '@main/gateway/desktop-runtimes';
import { telemetryService } from '@main/lib/telemetry';

/** Slow steady cadence: 12 reports/hour per process in sampled sessions. */
export const PERF_VITALS_INTERVAL_MS = 5 * 60_000;

/**
 * Production performance-vitals telemetry (the regression signal of record
 * for the footprint effort). Strictly behind the telemetry opt-in and the
 * per-session sampling roll: when `isPerfSampledSession()` is false — the
 * default, and always the case when telemetry is disabled — this function
 * returns without creating any timer, observer, or worker activation.
 */
export function startPerfVitalsTelemetry(runtimes: DesktopRuntimes): void {
  if (!telemetryService.isPerfSampledSession()) return;

  runtimes.startWorkerVitalsSampling(PERF_VITALS_INTERVAL_MS);
  startVitalsReporting({
    intervalMs: PERF_VITALS_INTERVAL_MS,
    report(vitals) {
      telemetryService.capture('perf_vitals', {
        process_name: 'main',
        ...vitals,
        ...appMetricsSummary(),
      });
    },
  });
}

/**
 * Cross-process summary from Electron's own bookkeeping: covers the renderer
 * and GPU processes that cannot self-sample over worker IPC.
 */
function appMetricsSummary(): Partial<ProcessVitals> {
  try {
    const metrics = app.getAppMetrics();
    let totalKb = 0;
    let rendererKb = 0;
    let gpuKb = 0;
    for (const metric of metrics) {
      const workingSetKb = metric.memory?.workingSetSize ?? 0;
      totalKb += workingSetKb;
      if (metric.type === 'Tab') rendererKb = Math.max(rendererKb, workingSetKb);
      if (metric.type === 'GPU') gpuKb = Math.max(gpuKb, workingSetKb);
    }
    return {
      app_process_count: metrics.length,
      app_total_rss_mb: Math.round(totalKb / 1024),
      renderer_rss_mb: Math.round(rendererKb / 1024),
      gpu_rss_mb: Math.round(gpuKb / 1024),
    };
  } catch {
    return {};
  }
}

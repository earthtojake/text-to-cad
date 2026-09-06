import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import { getDesktopWireClient } from '../lib/runtime/desktop-wire-client';

/** Matches the main-process vitals cadence: 12 reports/hour. */
export const RENDERER_PERF_VITALS_INTERVAL_MS = 5 * 60_000;

/** Event-timing entries shorter than this are not interaction-latency signal. */
const INTERACTION_DURATION_THRESHOLD_MS = 40;

export type RendererPerfEntry = {
  readonly entryType: string;
  readonly duration: number;
  readonly interactionId?: number;
};

export type RendererPerfObserve = (
  options: { type: 'longtask' | 'event'; durationThreshold?: number },
  callback: (entries: readonly RendererPerfEntry[]) => void
) => () => void;

export type RendererPerfVitalsReport = {
  long_tasks: number;
  long_task_total_ms: number;
  inp_ms: number;
  interval_ms: number;
};

export type StartRendererPerfVitalsDeps = {
  isSampled(): Promise<boolean>;
  observe: RendererPerfObserve;
  capture(report: RendererPerfVitalsReport): void;
  clock?: Clock;
  intervalMs?: number;
};

export type RendererPerfVitals = {
  readonly active: boolean;
  dispose(): void;
};

const inactive: RendererPerfVitals = { active: false, dispose() {} };

/**
 * Renderer responsiveness vitals for telemetry-sampled sessions: a `longtask`
 * observer (main-thread stalls) and an event-timing observer (INP-style worst
 * interaction latency), aggregated and reported on a slow cadence. When the
 * session is not sampled — always the case when telemetry is disabled — this
 * resolves without registering any observer or timer.
 */
export async function startRendererPerfVitals(
  deps: StartRendererPerfVitalsDeps
): Promise<RendererPerfVitals> {
  const sampled = await deps.isSampled().catch(() => false);
  if (!sampled) return inactive;

  const clock = deps.clock ?? systemClock;
  const intervalMs = deps.intervalMs ?? RENDERER_PERF_VITALS_INTERVAL_MS;

  let longTasks = 0;
  let longTaskTotalMs = 0;
  let maxInteractionMs = 0;

  const disposeLongTask = deps.observe({ type: 'longtask' }, (entries) => {
    for (const entry of entries) {
      longTasks += 1;
      longTaskTotalMs += entry.duration;
    }
  });
  const disposeEvent = deps.observe(
    { type: 'event', durationThreshold: INTERACTION_DURATION_THRESHOLD_MS },
    (entries) => {
      for (const entry of entries) {
        // interactionId === 0 marks non-interaction events; count only real
        // interactions when the field is present.
        if (entry.interactionId === 0) continue;
        maxInteractionMs = Math.max(maxInteractionMs, entry.duration);
      }
    }
  );

  let timer: TimerHandle | null = null;
  let disposed = false;
  const tick = (): void => {
    if (disposed) return;
    deps.capture({
      long_tasks: longTasks,
      long_task_total_ms: Math.round(longTaskTotalMs),
      inp_ms: Math.round(maxInteractionMs),
      interval_ms: intervalMs,
    });
    longTasks = 0;
    longTaskTotalMs = 0;
    maxInteractionMs = 0;
    schedule();
  };
  const schedule = (): void => {
    timer = clock.schedule(intervalMs, tick);
  };
  schedule();

  return {
    active: true,
    dispose() {
      disposed = true;
      void timer?.dispose();
      disposeLongTask();
      disposeEvent();
    },
  };
}

/** Production wiring: sampling status over RPC, real PerformanceObservers. */
export function initRendererPerfVitals(): void {
  void startRendererPerfVitals({
    isSampled: async () => {
      const client = await getDesktopWireClient();
      const result = await client.telemetry.getStatus();
      return result.status.perf_sampled;
    },
    observe: performanceObserve,
    capture: (report) => captureTelemetry('perf_renderer_vitals', report),
  }).catch(() => {
    // Vitals are best-effort; never break renderer bootstrap.
  });
}

function performanceObserve(
  options: { type: 'longtask' | 'event'; durationThreshold?: number },
  callback: (entries: readonly RendererPerfEntry[]) => void
): () => void {
  if (typeof PerformanceObserver === 'undefined') return () => {};
  try {
    const observer = new PerformanceObserver((list) => {
      callback(list.getEntries() as unknown as readonly RendererPerfEntry[]);
    });
    observer.observe({
      type: options.type,
      buffered: true,
      ...(options.durationThreshold !== undefined
        ? { durationThreshold: options.durationThreshold }
        : {}),
    } as PerformanceObserverInit);
    return () => observer.disconnect();
  } catch {
    // Entry type unsupported in this environment.
    return () => {};
  }
}

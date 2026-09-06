import type { Scope } from '@emdash/shared/concurrency';
import type { WorkerProcess, WorkerProcessSpawner, WorkerProcessSpec } from './types';
import { WORKER_NAME_ENV_VAR } from './types';

const WORKER_VITALS_KIND = 'wire-worker-vitals';

/**
 * Host → worker: begin self-sampling vitals on the given cadence. Sent only
 * for telemetry-sampled sessions; a worker that never receives this message
 * creates no sampling timers.
 */
export type WorkerVitalsStart = {
  kind: typeof WORKER_VITALS_KIND;
  event: 'start';
  intervalMs: number;
};

/** Worker → host: one numbers-only vitals sample. */
export type WorkerVitalsReport = {
  kind: typeof WORKER_VITALS_KIND;
  event: 'report';
  vitals: Readonly<Record<string, number>>;
};

export function workerVitalsStart(intervalMs: number): WorkerVitalsStart {
  return { kind: WORKER_VITALS_KIND, event: 'start', intervalMs };
}

export function workerVitalsReport(vitals: Readonly<Record<string, number>>): WorkerVitalsReport {
  return { kind: WORKER_VITALS_KIND, event: 'report', vitals };
}

export function isWorkerVitalsStart(message: unknown): message is WorkerVitalsStart {
  return isVitalsMessage(message) && message.event === 'start';
}

export function isWorkerVitalsReport(message: unknown): message is WorkerVitalsReport {
  return isVitalsMessage(message) && message.event === 'report';
}

function isVitalsMessage(message: unknown): message is { kind: string; event: string } {
  if (typeof message !== 'object' || message === null) return false;
  return (message as Record<string, unknown>).kind === WORKER_VITALS_KIND;
}

export type VitalsCollectingSpawner = WorkerProcessSpawner & {
  /**
   * Activate vitals sampling: sends a start message to every live worker
   * process and to any process spawned afterwards (covering restarts).
   * Idempotent; the last interval wins for future spawns.
   */
  startSampling(intervalMs: number): void;
};

export type CreateVitalsCollectingSpawnerOptions = {
  onReport(workerName: string, vitals: Readonly<Record<string, number>>): void;
};

/**
 * Decorate a {@link WorkerProcessSpawner} so the host can collect self-sampled
 * vitals from every worker over the existing IPC channel. Until
 * `startSampling` is called, workers are never asked to sample — the only
 * overhead is a message listener that sees no vitals traffic.
 */
export function createVitalsCollectingSpawner(
  inner: WorkerProcessSpawner,
  options: CreateVitalsCollectingSpawnerOptions
): VitalsCollectingSpawner {
  let samplingIntervalMs: number | null = null;
  const live = new Set<WorkerProcess>();

  return {
    async spawn(spec: WorkerProcessSpec, scope: Scope): Promise<WorkerProcess> {
      const process = await inner.spawn(spec, scope);
      const workerName = spec.env?.[WORKER_NAME_ENV_VAR] ?? 'unknown';

      live.add(process);
      process.onMessage((message) => {
        if (isWorkerVitalsReport(message)) options.onReport(workerName, message.vitals);
      });
      process.onExit(() => {
        live.delete(process);
      });

      if (samplingIntervalMs !== null) {
        trySend(process, workerVitalsStart(samplingIntervalMs));
      }
      return process;
    },
    startSampling(intervalMs: number): void {
      samplingIntervalMs = intervalMs;
      for (const process of live) {
        trySend(process, workerVitalsStart(intervalMs));
      }
    },
  };
}

function trySend(process: WorkerProcess, message: unknown): void {
  try {
    process.send(message);
  } catch {
    // Process may have exited between bookkeeping and send; vitals are best-effort.
  }
}

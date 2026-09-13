const WORKER_SIGNAL_KIND = 'wire-runtime-signal';

export type WorkerSignal = {
  kind: typeof WORKER_SIGNAL_KIND;
  event: 'ready' | 'shutdown';
};

export const WORKER_READY_SIGNAL: WorkerSignal = {
  kind: WORKER_SIGNAL_KIND,
  event: 'ready',
};

export const WORKER_SHUTDOWN_SIGNAL: WorkerSignal = {
  kind: WORKER_SIGNAL_KIND,
  event: 'shutdown',
};

export function isWorkerSignal(
  message: unknown,
  event?: WorkerSignal['event']
): message is WorkerSignal {
  if (typeof message !== 'object' || message === null) return false;
  const record = message as Record<string, unknown>;
  if (record.kind !== WORKER_SIGNAL_KIND) return false;
  return event === undefined || record.event === event;
}

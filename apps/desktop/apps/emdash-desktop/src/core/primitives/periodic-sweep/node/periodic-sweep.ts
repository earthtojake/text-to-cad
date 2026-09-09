import type { Scope } from '@emdash/shared/concurrency';

export type PeriodicSweep = {
  runNow(): Promise<void>;
  dispose(): void;
};

export function startPeriodicSweep(options: {
  scope: Scope;
  intervalMs: number;
  run(): Promise<void>;
  onError(error: unknown): void;
}): PeriodicSweep {
  let running = false;
  let disposed = false;
  const runNow = async () => {
    if (running || disposed) return;
    running = true;
    try {
      await options.run();
    } finally {
      running = false;
    }
  };
  const timer = setInterval(() => {
    void runNow().catch(options.onError);
  }, options.intervalMs);
  timer.unref?.();
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    clearInterval(timer);
  };
  options.scope.add(dispose);
  return { runNow, dispose };
}

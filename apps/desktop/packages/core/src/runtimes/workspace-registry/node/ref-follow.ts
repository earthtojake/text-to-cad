import { noopLogger, type Logger } from '@emdash/shared/logger';

/**
 * Production cadence for the autonomous ref-follow pass (pr-workspace-model spec,
 * Staleness): slow and jittered, decoupled from the scan — this loop does network
 * fetches, so it runs on tens of minutes, never seconds. Each delay is
 * `intervalMs + random() * jitterMs`, so repeated passes (and hosts restarting near
 * each other) never align into a thundering herd against the forge.
 */
export const DEFAULT_REF_FOLLOW_INTERVAL_MS = 20 * 60_000;
export const DEFAULT_REF_FOLLOW_JITTER_MS = 10 * 60_000;

export type RefFollowSchedulerOptions = {
  /** One follow pass over the registry; failures are logged, never rethrown. */
  runPass: () => Promise<unknown>;
  intervalMs?: number;
  jitterMs?: number;
  /** Injectable randomness (0..1) for deterministic jitter in tests. */
  random?: () => number;
  logger?: Logger;
};

/**
 * The follow loop's clockwork: fires one pass at a time on a jittered cadence, with
 * the next delay armed only after the previous pass settles — passes never overlap.
 * The first pass waits a full jittered interval (boot already scans; freshness in the
 * first minutes is the drift indicator's job). Starts with the registry component and
 * stops cleanly on dispose: the timer is cleared and an in-flight pass is awaited, so
 * tests never leak timers or half-finished git work.
 */
export class RefFollowScheduler {
  private readonly runPass: () => Promise<unknown>;
  private readonly intervalMs: number;
  private readonly jitterMs: number;
  private readonly random: () => number;
  private readonly logger: Logger;

  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight: Promise<void> | null = null;
  private disposed = false;

  constructor(options: RefFollowSchedulerOptions) {
    this.runPass = options.runPass;
    this.intervalMs = options.intervalMs ?? DEFAULT_REF_FOLLOW_INTERVAL_MS;
    this.jitterMs = options.jitterMs ?? DEFAULT_REF_FOLLOW_JITTER_MS;
    this.random = options.random ?? Math.random;
    this.logger = options.logger ?? noopLogger;
  }

  start(): void {
    this.schedule();
  }

  async dispose(): Promise<void> {
    this.disposed = true;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    await this.inFlight;
  }

  private schedule(): void {
    if (this.disposed) return;
    const delay = this.intervalMs + this.random() * this.jitterMs;
    this.timer = setTimeout(() => this.fire(), delay);
    this.timer.unref?.();
  }

  private fire(): void {
    if (this.disposed) return;
    this.inFlight = this.runPass()
      .then(() => undefined)
      .catch((error) => {
        // A failed pass is as silent as a skipped worktree: log and retry next pass.
        this.logger.warn?.(`ref-follow pass failed: ${String(error)}`);
      })
      .finally(() => {
        this.inFlight = null;
        this.schedule();
      });
  }
}

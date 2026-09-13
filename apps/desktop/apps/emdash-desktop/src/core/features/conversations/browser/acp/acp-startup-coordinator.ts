import { systemClock, type Clock } from '@emdash/shared/scheduling';

export type AcpStartupPhase = 'queued' | 'starting' | 'retrying' | 'connecting';

type StartupOutcome<T> = { kind: 'value'; value: T } | { kind: 'error'; error: unknown };

export interface AcpStartupCoordinatorOptions {
  maxConcurrent?: number;
  retryDelaysMs?: readonly number[];
  clock?: Clock;
}

export interface AcpStartupRunOptions<T> {
  onPhase?: (phase: AcpStartupPhase) => void;
  shouldRetry?: (outcome: StartupOutcome<T>, attempt: number) => boolean;
  compatibilityKey?: string;
}

type QueuedStart = () => void;

type StartupFlight = {
  promise: Promise<unknown>;
  phase: AcpStartupPhase;
  listeners: Set<(phase: AcpStartupPhase) => void>;
  compatibilityKey: string;
};

export class AcpStartupConflictError extends Error {
  constructor(conversationId: string) {
    super(`A different agent startup is already in progress for '${conversationId}'`);
    this.name = 'AcpStartupConflictError';
  }
}

/**
 * Bounds expensive provider startup without constraining prompt turns after a
 * session is ready. Starts for one conversation are single-flight so a client
 * timeout/retry cannot create two provider sessions for the same chat.
 */
export class AcpStartupCoordinator {
  private readonly maxConcurrent: number;
  private readonly retryDelaysMs: readonly number[];
  private readonly clock: Clock;
  private readonly queue: QueuedStart[] = [];
  private readonly flights = new Map<string, StartupFlight>();
  private active = 0;

  constructor(options: AcpStartupCoordinatorOptions = {}) {
    this.maxConcurrent = Math.max(1, Math.floor(options.maxConcurrent ?? 2));
    this.retryDelaysMs = options.retryDelaysMs ?? [300, 900];
    this.clock = options.clock ?? systemClock;
  }

  run<T>(
    conversationId: string,
    operation: (attempt: number) => Promise<T>,
    options: AcpStartupRunOptions<T> = {}
  ): Promise<T> {
    const existing = this.flights.get(conversationId);
    if (existing) {
      if (existing.compatibilityKey !== (options.compatibilityKey ?? '')) {
        return Promise.reject(new AcpStartupConflictError(conversationId));
      }
      if (options.onPhase) {
        existing.listeners.add(options.onPhase);
        options.onPhase(existing.phase);
      }
      return existing.promise as Promise<T>;
    }

    const queued = this.active >= this.maxConcurrent;
    const initialPhase: AcpStartupPhase = queued ? 'queued' : 'starting';
    const flight: StartupFlight = {
      promise: Promise.resolve(undefined),
      phase: initialPhase,
      listeners: new Set(options.onPhase ? [options.onPhase] : []),
      compatibilityKey: options.compatibilityKey ?? '',
    };
    this.publishPhase(flight, initialPhase);
    flight.promise = this.admit(() => this.runAttempts(operation, options, flight));
    this.flights.set(conversationId, flight);
    void flight.promise
      .finally(() => {
        if (this.flights.get(conversationId) === flight) {
          this.flights.delete(conversationId);
        }
        flight.listeners.clear();
      })
      .catch(() => {});
    return flight.promise as Promise<T>;
  }

  private admit<T>(operation: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.queue.push(() => {
        this.active += 1;
        void operation()
          .then(resolve, reject)
          .finally(() => {
            this.active -= 1;
            this.drain();
          });
      });
      this.drain();
    });
  }

  private drain(): void {
    while (this.active < this.maxConcurrent) {
      const next = this.queue.shift();
      if (!next) return;
      next();
    }
  }

  private async runAttempts<T>(
    operation: (attempt: number) => Promise<T>,
    options: AcpStartupRunOptions<T>,
    flight: StartupFlight
  ): Promise<T> {
    let attempt = 0;
    for (;;) {
      this.publishPhase(flight, attempt === 0 ? 'starting' : 'retrying');
      try {
        const value = await operation(attempt);
        const outcome: StartupOutcome<T> = { kind: 'value', value };
        if (!options.shouldRetry?.(outcome, attempt)) return value;
        const delayMs = this.retryDelaysMs[attempt];
        if (delayMs === undefined) return value;
        this.publishPhase(flight, 'retrying');
        await this.clock.sleep(delayMs);
      } catch (error) {
        const outcome: StartupOutcome<T> = { kind: 'error', error };
        if (!options.shouldRetry?.(outcome, attempt)) throw error;
        const delayMs = this.retryDelaysMs[attempt];
        if (delayMs === undefined) throw error;
        this.publishPhase(flight, 'retrying');
        await this.clock.sleep(delayMs);
      }
      attempt += 1;
    }
  }

  private publishPhase(flight: StartupFlight, phase: AcpStartupPhase): void {
    flight.phase = phase;
    for (const listener of flight.listeners) listener(phase);
  }
}

import { abortableWait, abortReason } from '../scheduling';

/** FIFO limiter that bounds concurrent work without rejecting excess callers. */
export interface ConcurrencyLimiter {
  run<T>(signal: AbortSignal, operation: () => Promise<T>): Promise<T>;
}

class ConcurrencyLimiterImpl implements ConcurrencyLimiter {
  private active = 0;
  private readonly waiting: Array<{
    resolve: (release: () => void) => void;
  }> = [];

  constructor(private readonly limit: number) {
    if (!Number.isInteger(limit) || limit < 1) {
      throw new Error('Concurrency limit must be a positive integer');
    }
  }

  async run<T>(signal: AbortSignal, operation: () => Promise<T>): Promise<T> {
    const release = await this.acquire(signal);
    try {
      return await operation();
    } finally {
      release();
    }
  }

  private acquire(signal: AbortSignal): Promise<() => void> {
    if (signal.aborted) return Promise.reject(abortReason(signal, 'Operation cancelled'));
    if (this.active < this.limit) {
      this.active += 1;
      return Promise.resolve(this.releaseOnce());
    }

    return abortableWait<() => void>({ signal, fallback: 'Operation cancelled' }, (settle) => {
      const waiter = { resolve: settle.resolve };
      this.waiting.push(waiter);
      return () => {
        const index = this.waiting.indexOf(waiter);
        if (index >= 0) this.waiting.splice(index, 1);
      };
    });
  }

  private releaseOnce(): () => void {
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.active -= 1;
      this.drain();
    };
  }

  private drain(): void {
    // Aborted waiters are removed synchronously by their wait's cleanup, so
    // every queued waiter here is still live.
    while (this.active < this.limit && this.waiting.length > 0) {
      const waiter = this.waiting.shift()!;
      this.active += 1;
      waiter.resolve(this.releaseOnce());
    }
  }
}

export function createConcurrencyLimiter(limit: number): ConcurrencyLimiter {
  return new ConcurrencyLimiterImpl(limit);
}

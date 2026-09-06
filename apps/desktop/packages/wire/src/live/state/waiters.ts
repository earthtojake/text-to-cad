import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import type { LiveCursor } from '../../api/channel';

type CursorWaiter = {
  target: LiveCursor;
  resolve: () => void;
  reject: (error: Error) => void;
  timer: TimerHandle | undefined;
};

type MutationWaiter = {
  mutationId: string;
  resolve: () => void;
  reject: (error: Error) => void;
  timer: TimerHandle | undefined;
};

export class LiveStateWaiters {
  private cursorWaiters: CursorWaiter[] = [];
  private mutationWaiters: MutationWaiter[] = [];
  private readonly clock: Clock;

  constructor(
    private readonly cursor: () => LiveCursor | undefined,
    options: { clock?: Clock } = {}
  ) {
    this.clock = options.clock ?? systemClock;
  }

  waitForCursor(target: LiveCursor, timeoutMs = 15_000): Promise<void> {
    if (this.cursorSatisfies(target)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const waiter: CursorWaiter = {
        target,
        resolve,
        reject,
        timer:
          timeoutMs > 0
            ? this.clock.schedule(
                timeoutMs,
                () => {
                  waiter.timer = undefined;
                  this.cursorWaiters = this.cursorWaiters.filter(
                    (candidate) => candidate !== waiter
                  );
                  reject(new Error(`Timed out waiting for live cursor ${formatCursor(target)}`));
                },
                { unref: true }
              )
            : undefined,
      };
      this.cursorWaiters.push(waiter);
    });
  }

  waitForMutation(mutationId: string, timeoutMs = 15_000): Promise<void> {
    return new Promise((resolve, reject) => {
      const waiter: MutationWaiter = {
        mutationId,
        resolve,
        reject,
        timer:
          timeoutMs > 0
            ? this.clock.schedule(
                timeoutMs,
                () => {
                  waiter.timer = undefined;
                  this.mutationWaiters = this.mutationWaiters.filter(
                    (candidate) => candidate !== waiter
                  );
                  reject(new Error(`Timed out waiting for live mutation ${mutationId}`));
                },
                { unref: true }
              )
            : undefined,
      };
      this.mutationWaiters.push(waiter);
    });
  }

  flushCursorWaiters(): void {
    const ready = this.cursorWaiters.filter((waiter) => this.cursorSatisfies(waiter.target));
    if (ready.length === 0) return;
    this.cursorWaiters = this.cursorWaiters.filter(
      (waiter) => !this.cursorSatisfies(waiter.target)
    );
    for (const waiter of ready) {
      waiter.timer?.dispose();
      waiter.resolve();
    }
  }

  flushMutationWaiters(mutationIds: string[]): void {
    if (mutationIds.length === 0) return;
    const ids = new Set(mutationIds);
    const ready = this.mutationWaiters.filter((waiter) => ids.has(waiter.mutationId));
    if (ready.length === 0) return;
    this.mutationWaiters = this.mutationWaiters.filter((waiter) => !ids.has(waiter.mutationId));
    for (const waiter of ready) {
      waiter.timer?.dispose();
      waiter.resolve();
    }
  }

  flushAllMutationWaiters(): void {
    const ready = this.mutationWaiters;
    if (ready.length === 0) return;
    this.mutationWaiters = [];
    for (const waiter of ready) {
      waiter.timer?.dispose();
      waiter.resolve();
    }
  }

  rejectAll(error: Error): void {
    const cursorWaiters = this.cursorWaiters;
    const mutationWaiters = this.mutationWaiters;
    this.cursorWaiters = [];
    this.mutationWaiters = [];
    for (const waiter of cursorWaiters) {
      waiter.timer?.dispose();
      waiter.reject(error);
    }
    for (const waiter of mutationWaiters) {
      waiter.timer?.dispose();
      waiter.reject(error);
    }
  }

  private cursorSatisfies(target: LiveCursor): boolean {
    const cursor = this.cursor();
    if (!cursor) return false;
    if (cursor.generation > target.generation) return true;
    return cursor.generation === target.generation && cursor.sequence >= target.sequence;
  }
}

function formatCursor(cursor: LiveCursor): string {
  return `${cursor.generation}:${cursor.sequence}`;
}

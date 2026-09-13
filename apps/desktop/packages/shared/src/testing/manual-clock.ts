import type { Clock, ScheduleOptions, SleepOptions, TimerHandle } from '../scheduling';
import { normalizeDelay, sleepWithClock } from '../scheduling/clock';

type ManualTimer = {
  id: number;
  deadline: number;
  callback: () => void;
  active: boolean;
};

export class ManualClock implements Clock {
  private currentTime: number;
  private nextId = 1;
  private readonly timers = new Map<number, ManualTimer>();

  constructor(startAt = 0) {
    this.currentTime = startAt;
  }

  now(): number {
    return this.currentTime;
  }

  schedule(delayMs: number, callback: () => void, _options: ScheduleOptions = {}): TimerHandle {
    const timer: ManualTimer = {
      id: this.nextId++,
      deadline: this.currentTime + normalizeDelay(delayMs),
      callback,
      active: true,
    };
    this.timers.set(timer.id, timer);
    return {
      get active() {
        return timer.active;
      },
      dispose: () => {
        if (!timer.active) return;
        timer.active = false;
        this.timers.delete(timer.id);
      },
    };
  }

  sleep(delayMs: number, options?: SleepOptions): Promise<void> {
    return sleepWithClock(this, delayMs, options);
  }

  async advanceBy(ms: number): Promise<void> {
    await this.advanceTo(this.currentTime + normalizeDelay(ms));
  }

  async advanceTo(targetTime: number): Promise<void> {
    if (targetTime < this.currentTime) {
      throw new Error('ManualClock cannot move backwards');
    }

    for (;;) {
      const next = this.nextDueTimer(targetTime);
      if (!next) break;
      this.currentTime = next.deadline;
      this.timers.delete(next.id);
      if (!next.active) continue;
      next.active = false;
      next.callback();
      await flushMicrotasks();
    }

    this.currentTime = targetTime;
    await flushMicrotasks();
  }

  async runAll(options: { maxTimers?: number } = {}): Promise<void> {
    const maxTimers = options.maxTimers ?? 10_000;
    let fired = 0;
    for (;;) {
      const next = this.nextTimer();
      if (!next) break;
      fired += 1;
      if (fired > maxTimers) {
        throw new Error(`ManualClock exceeded ${maxTimers} timers`);
      }
      await this.advanceTo(next.deadline);
    }
  }

  clear(): void {
    for (const timer of this.timers.values()) timer.active = false;
    this.timers.clear();
  }

  private nextDueTimer(targetTime: number): ManualTimer | undefined {
    const timer = this.nextTimer();
    return timer && timer.deadline <= targetTime ? timer : undefined;
  }

  private nextTimer(): ManualTimer | undefined {
    let next: ManualTimer | undefined;
    for (const timer of this.timers.values()) {
      if (!timer.active) continue;
      if (
        !next ||
        timer.deadline < next.deadline ||
        (timer.deadline === next.deadline && timer.id < next.id)
      ) {
        next = timer;
      }
    }
    return next;
  }
}

export function createManualClock(startAt = 0): ManualClock {
  return new ManualClock(startAt);
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

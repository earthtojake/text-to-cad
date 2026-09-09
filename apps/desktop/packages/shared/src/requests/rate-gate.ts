import { systemClock, throwIfAborted, type Clock } from '../scheduling';

export type RateFeedback = {
  cost?: number;
  remaining?: number;
  resetAtMs?: number;
  retryAfterMs?: number;
};

export interface RateGate {
  acquire(cost: number, signal: AbortSignal): Promise<void>;
  observe(feedback: RateFeedback): void;
}

export type TokenBucketRateGateOptions = {
  capacity: number;
  refillPerSec: number;
  reserve?: number;
  clock?: Clock;
};

export function createTokenBucketGate(options: TokenBucketRateGateOptions): RateGate {
  return new TokenBucketRateGate(options);
}

class TokenBucketRateGate implements RateGate {
  private readonly capacity: number;
  private readonly refillPerSec: number;
  private readonly reserve: number;
  private readonly clock: Clock;
  private tokens: number;
  private lastRefillAt: number;
  private blockedUntil = 0;
  private serverRemaining: number | undefined;
  private serverResetAt: number | undefined;

  constructor(options: TokenBucketRateGateOptions) {
    if (!Number.isFinite(options.capacity) || options.capacity <= 0) {
      throw new Error('Rate gate capacity must be a positive finite number');
    }
    if (!Number.isFinite(options.refillPerSec) || options.refillPerSec <= 0) {
      throw new Error('Rate gate refill rate must be a positive finite number');
    }
    if (
      options.reserve !== undefined &&
      (!Number.isFinite(options.reserve) || options.reserve < 0)
    ) {
      throw new Error('Rate gate reserve must be a non-negative finite number');
    }
    this.capacity = options.capacity;
    this.refillPerSec = options.refillPerSec;
    this.reserve = options.reserve ?? 0;
    this.clock = options.clock ?? systemClock;
    this.tokens = this.capacity;
    this.lastRefillAt = this.clock.now();
  }

  async acquire(cost: number, signal: AbortSignal): Promise<void> {
    if (!Number.isFinite(cost) || cost < 0) {
      throw new Error('Rate gate cost must be a non-negative finite number');
    }

    const tokenCost = Math.min(cost, this.capacity);
    for (;;) {
      throwIfAborted(signal);
      const now = this.clock.now();
      this.refill(now);
      this.expireServerBudget(now);

      const pauseMs = Math.max(0, this.blockedUntil - now);
      const budgetMs = this.serverBudgetWait(cost, now);
      const tokenMs =
        this.tokens >= tokenCost
          ? 0
          : Math.ceil(((tokenCost - this.tokens) / this.refillPerSec) * 1_000);
      const waitMs = Math.max(pauseMs, budgetMs, tokenMs);
      if (waitMs > 0) {
        await this.clock.sleep(waitMs, { signal });
        continue;
      }

      this.tokens = Math.max(0, this.tokens - tokenCost);
      if (this.serverRemaining !== undefined) {
        this.serverRemaining = Math.max(0, this.serverRemaining - cost);
      }
      return;
    }
  }

  observe(feedback: RateFeedback): void {
    const now = this.clock.now();
    this.refill(now);
    this.expireServerBudget(now);
    if (isNonNegativeFinite(feedback.cost)) {
      this.tokens = Math.max(0, this.tokens - Math.min(feedback.cost, this.capacity));
    }
    if (isNonNegativeFinite(feedback.retryAfterMs)) {
      this.blockedUntil = Math.max(this.blockedUntil, now + feedback.retryAfterMs);
    }
    this.reconcileServerBudget(feedback);
    if (
      this.serverRemaining !== undefined &&
      this.serverRemaining <= this.reserve &&
      this.serverResetAt !== undefined &&
      this.serverResetAt > now
    ) {
      this.blockedUntil = Math.max(this.blockedUntil, this.serverResetAt);
    }
    this.expireServerBudget(now);
  }

  private reconcileServerBudget(feedback: RateFeedback): void {
    const resetAt = isNonNegativeFinite(feedback.resetAtMs) ? feedback.resetAtMs : undefined;
    const remaining = isNonNegativeFinite(feedback.remaining) ? feedback.remaining : undefined;
    if (resetAt === undefined) {
      if (remaining !== undefined) {
        this.serverRemaining =
          this.serverRemaining === undefined
            ? remaining
            : Math.min(this.serverRemaining, remaining);
      }
      return;
    }
    if (this.serverResetAt === undefined || resetAt > this.serverResetAt) {
      this.serverResetAt = resetAt;
      this.serverRemaining = remaining;
      return;
    }
    if (resetAt === this.serverResetAt && remaining !== undefined) {
      this.serverRemaining =
        this.serverRemaining === undefined ? remaining : Math.min(this.serverRemaining, remaining);
    }
  }

  private refill(now: number): void {
    const elapsedMs = Math.max(0, now - this.lastRefillAt);
    this.tokens = Math.min(this.capacity, this.tokens + (elapsedMs / 1_000) * this.refillPerSec);
    this.lastRefillAt = now;
  }

  private serverBudgetWait(cost: number, now: number): number {
    if (
      this.serverRemaining === undefined ||
      this.serverResetAt === undefined ||
      this.serverRemaining - this.reserve >= cost
    ) {
      return 0;
    }
    return Math.max(0, this.serverResetAt - now);
  }

  private expireServerBudget(now: number): void {
    if (this.serverResetAt === undefined || this.serverResetAt > now) return;
    this.serverRemaining = undefined;
    this.serverResetAt = undefined;
    if (this.blockedUntil <= now) this.blockedUntil = 0;
  }
}

function isNonNegativeFinite(value: number | undefined): value is number {
  return value !== undefined && Number.isFinite(value) && value >= 0;
}

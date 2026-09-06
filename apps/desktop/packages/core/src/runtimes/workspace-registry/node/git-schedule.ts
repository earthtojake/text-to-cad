import os from 'node:os';

/**
 * Priority classes for registry-spawned subprocesses (spec: workspace-lifecycle-v2,
 * git concurrency model). Order matters: lower index dispatches first.
 */
export const GIT_WORK_TIERS = ['creation', 'activation', 'background', 'probe'] as const;
export type GitWorkTier = (typeof GIT_WORK_TIERS)[number];

const TIER_INDEX: Record<GitWorkTier, number> = {
  creation: 0,
  activation: 1,
  background: 2,
  probe: 3,
};

/** Tiers that receive headroom and hold their repository's idle gate. */
const LAST_HIGH_TIER = TIER_INDEX.background;

export type GitScheduleOptions = {
  /** Concurrent subprocess budget; defaults to min(cores, 8). */
  capacity?: number;
  /** Extra slots only creation/activation may overflow into; defaults to 2. */
  headroom?: number;
};

export type GitWork = {
  tier: GitWorkTier;
  /** Repository key for idle gating; omit for work not tied to one repository. */
  repository?: string;
};

type Waiter = { start: () => void };

/**
 * The registry's git budget: one per-runtime semaphore over every registry-spawned git
 * subprocess and artifact-copy process, with priority dispatch and +headroom slots
 * reserved for creation/activation so interactive verbs always start immediately —
 * even when probes saturate the budget. Never a mutual-exclusion device: git's own
 * locking (plus the per-worktree writer lock) owns correctness; this owns load.
 *
 * Idle gating: work in the top three tiers counts toward its repository's gate from
 * enqueue to completion; `whenIdle` lets the scan path defer probing a repository
 * that has interactive work in flight, with a deadline (the poll floor) as the
 * anti-starvation bound.
 */
export class GitSchedule {
  private readonly capacity: number;
  private readonly headroom: number;
  private running = 0;
  private readonly queues: Waiter[][] = GIT_WORK_TIERS.map(() => []);
  private readonly repoWork = new Map<string, number>();
  private readonly idleWaiters = new Map<string, Array<() => void>>();

  constructor(options: GitScheduleOptions = {}) {
    this.capacity = options.capacity ?? Math.min(os.availableParallelism?.() ?? 8, 8);
    this.headroom = options.headroom ?? 2;
  }

  async run<T>(work: GitWork, task: () => Promise<T> | T): Promise<T> {
    const tier = TIER_INDEX[work.tier];
    const gated = tier <= LAST_HIGH_TIER && work.repository !== undefined;
    if (gated) this.enterRepo(work.repository!);
    try {
      await this.acquire(tier);
      try {
        return await task();
      } finally {
        this.release();
      }
    } finally {
      if (gated) this.leaveRepo(work.repository!);
    }
  }

  /**
   * Holds the repository's idle gate for the duration of a composite operation (a
   * whole creation pipeline, a background-step chain) without consuming a budget
   * slot — the individual subprocesses inside still take their own slots. Keeps
   * idle-gated scans out of the gaps between an operation's subprocesses.
   */
  async withRepoHold<T>(repository: string, task: () => Promise<T> | T): Promise<T> {
    this.enterRepo(repository);
    try {
      return await task();
    } finally {
      this.leaveRepo(repository);
    }
  }

  /**
   * Resolves when the repository has no queued or in-flight creation/activation/
   * background work — or after `deadlineMs`, so constant churn can never starve the
   * caller past the poll floor.
   */
  whenIdle(repository: string, deadlineMs: number): Promise<void> {
    if ((this.repoWork.get(repository) ?? 0) === 0) return Promise.resolve();
    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve();
      };
      const timer = setTimeout(finish, deadlineMs);
      timer.unref?.();
      const waiters = this.idleWaiters.get(repository) ?? [];
      waiters.push(finish);
      this.idleWaiters.set(repository, waiters);
    });
  }

  private limitFor(tier: number): number {
    return tier <= TIER_INDEX.activation ? this.capacity + this.headroom : this.capacity;
  }

  private acquire(tier: number): Promise<void> {
    if (this.running < this.limitFor(tier)) {
      this.running += 1;
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      this.queues[tier]!.push({ start: resolve });
    });
  }

  private release(): void {
    this.running -= 1;
    for (let tier = 0; tier < this.queues.length; tier += 1) {
      const queue = this.queues[tier]!;
      while (queue.length > 0 && this.running < this.limitFor(tier)) {
        this.running += 1;
        queue.shift()!.start();
      }
    }
  }

  private enterRepo(repository: string): void {
    this.repoWork.set(repository, (this.repoWork.get(repository) ?? 0) + 1);
  }

  private leaveRepo(repository: string): void {
    const next = (this.repoWork.get(repository) ?? 1) - 1;
    if (next > 0) {
      this.repoWork.set(repository, next);
      return;
    }
    this.repoWork.delete(repository);
    const waiters = this.idleWaiters.get(repository);
    if (!waiters) return;
    this.idleWaiters.delete(repository);
    for (const waiter of waiters) waiter();
  }
}

/**
 * The per-worktree writer lock (spec: exclusivity shrinks to workspaceClaims plus
 * this): mutators of one worktree's checkout (plumbing, removal) hold it exclusively;
 * probes of that worktree wait for release via `whenUnlocked` so they never observe a
 * torn checkout. Probes of other worktrees are untouched, and probes never block
 * writers — this is one-directional exclusion, not a read-write lock.
 */
export class WorktreeWriteLocks {
  private readonly writers = new Map<string, Promise<void>>();

  async withWriter<T>(key: string, task: () => Promise<T> | T): Promise<T> {
    const previous = this.writers.get(key) ?? Promise.resolve();
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const chained = previous.then(() => held);
    this.writers.set(key, chained);
    await previous;
    try {
      return await task();
    } finally {
      release();
      if (this.writers.get(key) === chained) this.writers.delete(key);
    }
  }

  /** Resolves once no writer holds the worktree; immediate when unlocked. */
  whenUnlocked(key: string): Promise<void> {
    return this.writers.get(key) ?? Promise.resolve();
  }
}

const TRANSIENT_LOCK_PATTERNS = [
  /unable to create .*\.lock.*file exists/i,
  /could not lock (ref|config)/i,
  /\.lock.*file exists/i,
];

/** True for git's "another process holds the lock" failures — retryable by design. */
export function isTransientLockError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return TRANSIENT_LOCK_PATTERNS.some((pattern) => pattern.test(message));
}

export type RetryTransientLockOptions = {
  /** Backoff before each retry; length bounds the retry count. */
  delaysMs?: number[];
};

const DEFAULT_LOCK_RETRY_DELAYS_MS = [50, 150, 400];

/**
 * Caller-side retry for transient index/ref-lock collisions (spec: handled by retry
 * with short backoff, not by up-front serialization). Non-transient failures surface
 * on the first attempt.
 */
export async function retryTransientLock<T>(
  task: () => Promise<T>,
  options: RetryTransientLockOptions = {}
): Promise<T> {
  const delays = options.delaysMs ?? DEFAULT_LOCK_RETRY_DELAYS_MS;
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await task();
    } catch (error) {
      if (attempt >= delays.length || !isTransientLockError(error)) throw error;
      await new Promise((resolve) => setTimeout(resolve, delays[attempt]));
    }
  }
}

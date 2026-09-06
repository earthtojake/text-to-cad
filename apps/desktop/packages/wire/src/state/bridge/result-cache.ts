import type { LiveMutationResult } from '../../api/channel';

export const DEFAULT_MUTATION_RESULT_CACHE_TTL_MS = 5 * 60 * 1000;
export const DEFAULT_MUTATION_RESULT_CACHE_MAX_ENTRIES = 1000;

export type MutationResultCacheOptions = {
  ttlMs?: number;
  maxEntries?: number;
  now?: () => number;
};

type CacheEntry<D, E> = {
  value: LiveMutationResult<D, E>;
  expiresAt: number;
};

export type MutationResultCacheDedupeSource = 'settled' | 'inFlight';

export type MutationResultCacheRunOptions = {
  onDedupe?: (source: MutationResultCacheDedupeSource) => void;
};

export class MutationResultCache {
  private readonly ttlMs: number;
  private readonly maxEntries: number;
  private readonly now: () => number;
  private readonly settled = new Map<string, CacheEntry<unknown, unknown>>();
  private readonly inFlight = new Map<string, Promise<LiveMutationResult<unknown, unknown>>>();

  constructor(options: MutationResultCacheOptions = {}) {
    this.ttlMs = Math.max(0, options.ttlMs ?? DEFAULT_MUTATION_RESULT_CACHE_TTL_MS);
    this.maxEntries = Math.max(1, options.maxEntries ?? DEFAULT_MUTATION_RESULT_CACHE_MAX_ENTRIES);
    this.now = options.now ?? Date.now;
  }

  run<D, E>(
    mutationId: string,
    execute: () => Promise<LiveMutationResult<D, E>>,
    options: MutationResultCacheRunOptions = {}
  ): Promise<LiveMutationResult<D, E>> {
    const cached = this.get<D, E>(mutationId);
    if (cached) {
      options.onDedupe?.('settled');
      return Promise.resolve(cached);
    }

    const inFlight = this.inFlight.get(mutationId) as Promise<LiveMutationResult<D, E>> | undefined;
    if (inFlight) {
      options.onDedupe?.('inFlight');
      return inFlight;
    }

    const pending = execute()
      .then((result) => {
        this.set(mutationId, result);
        return result;
      })
      .finally(() => {
        this.inFlight.delete(mutationId);
      });
    this.inFlight.set(mutationId, pending as Promise<LiveMutationResult<unknown, unknown>>);
    return pending;
  }

  get<D, E>(mutationId: string): LiveMutationResult<D, E> | undefined {
    const entry = this.settled.get(mutationId);
    if (!entry) return undefined;
    if (entry.expiresAt <= this.now()) {
      this.settled.delete(mutationId);
      return undefined;
    }
    this.settled.delete(mutationId);
    this.settled.set(mutationId, entry);
    return entry.value as LiveMutationResult<D, E>;
  }

  clear(): void {
    this.settled.clear();
    this.inFlight.clear();
  }

  private set<D, E>(mutationId: string, value: LiveMutationResult<D, E>): void {
    this.settled.set(mutationId, {
      value: value as LiveMutationResult<unknown, unknown>,
      expiresAt: this.now() + this.ttlMs,
    });
    this.evictExpired();
    while (this.settled.size > this.maxEntries) {
      const oldest = this.settled.keys().next().value;
      if (oldest === undefined) break;
      this.settled.delete(oldest);
    }
  }

  private evictExpired(): void {
    const now = this.now();
    for (const [mutationId, entry] of this.settled) {
      if (entry.expiresAt <= now) this.settled.delete(mutationId);
    }
  }
}

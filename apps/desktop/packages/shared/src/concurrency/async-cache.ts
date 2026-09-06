import { systemClock, type Clock } from '../scheduling';
import { createScope, type Run, type Scope } from './scope';

export interface AsyncCache<K, T> {
  get(key: K): Promise<T>;
  refresh(key: K): Promise<T>;
  peek(key: K): T | undefined;
  set(key: K, value: T): void;
  invalidate(key: K): void;
  clear(): void;
  dispose(): Promise<void>;
}

export type CreateAsyncCacheOptions<K, T> = {
  key: (key: K) => string;
  scope?: Scope;
  label?: string;
  ttlMs?: number;
  maxEntries?: number;
  clock?: Clock;
  load: (key: K, signal: AbortSignal) => Promise<T> | T;
  onError?: (error: unknown, key: string) => void;
};

type Entry<K, T> = {
  key: K;
  generation: number;
  value: T | undefined;
  hasValue: boolean;
  expiresAt: number;
  run: Run<T> | undefined;
  promise: Promise<T> | undefined;
};

export function createAsyncCache<K, T>(options: CreateAsyncCacheOptions<K, T>): AsyncCache<K, T> {
  const clock = options.clock ?? systemClock;
  const cacheScope = options.scope
    ? options.scope.child(options.label ?? 'async-cache')
    : createScope({ label: options.label, clock });
  const ttlMs = Math.max(0, options.ttlMs ?? 0);
  const maxEntries = Math.max(1, options.maxEntries ?? Number.POSITIVE_INFINITY);
  const now = (): number => clock.now();
  const entries = new Map<string, Entry<K, T>>();
  let disposed = false;
  let disposePromise: Promise<void> | undefined;

  cacheScope.add(() => {
    disposed = true;
    for (const entry of entries.values()) entry.run?.cancel(new Error('AsyncCache disposed'));
    entries.clear();
  });

  return {
    get(key): Promise<T> {
      assertOpen();
      const keyId = options.key(key);
      const entry = entries.get(keyId);
      if (entry?.promise) return entry.promise;
      if (entry?.hasValue && entry.expiresAt > now()) return Promise.resolve(entry.value as T);
      return load(keyId, key, entry);
    },
    refresh(key): Promise<T> {
      assertOpen();
      const keyId = options.key(key);
      const existing = entries.get(keyId);
      if (existing?.promise) return existing.promise;
      return load(keyId, key, existing);
    },
    peek(key): T | undefined {
      // A genuinely side-effect-free read: no expired-entry delete, no LRU
      // bump. Cleanup stays lazy on get/set.
      const entry = entries.get(options.key(key));
      if (!entry?.hasValue) return undefined;
      if (entry.expiresAt <= now()) return undefined;
      return entry.value as T;
    },
    set(key, value): void {
      assertOpen();
      const keyId = options.key(key);
      const existing = entries.get(keyId);
      const entry: Entry<K, T> = {
        key,
        generation: (existing?.generation ?? 0) + 1,
        value,
        hasValue: true,
        expiresAt: expiresAt(),
        run: undefined,
        promise: undefined,
      };
      entries.set(keyId, entry);
      evictOverflow();
    },
    invalidate(key): void {
      const keyId = options.key(key);
      const entry = entries.get(keyId);
      entry?.run?.cancel(new Error(`AsyncCache invalidated '${keyId}'`));
      entries.delete(keyId);
    },
    clear(): void {
      for (const entry of entries.values()) entry.run?.cancel(new Error('AsyncCache cleared'));
      entries.clear();
    },
    dispose(): Promise<void> {
      if (disposePromise) return disposePromise;
      disposed = true;
      disposePromise = cacheScope.dispose();
      return disposePromise;
    },
  };

  function load(keyId: string, key: K, existing: Entry<K, T> | undefined): Promise<T> {
    const generation = (existing?.generation ?? 0) + 1;
    const entry: Entry<K, T> = {
      key,
      generation,
      value: existing?.value,
      hasValue: false,
      expiresAt: 0,
      run: undefined,
      promise: undefined,
    };
    entries.set(keyId, entry);

    const run = cacheScope.run(`load:${keyId}`, (signal) => options.load(key, signal));
    entry.run = run;
    entry.promise = run
      .value()
      .then((value) => {
        if (disposed) throw new Error('AsyncCache is disposed');
        if (entries.get(keyId) !== entry || entry.generation !== generation) return value;
        entry.value = value;
        entry.hasValue = true;
        entry.expiresAt = expiresAt();
        entry.run = undefined;
        entry.promise = undefined;
        touch(keyId, entry);
        evictOverflow();
        return value;
      })
      .catch((error: unknown) => {
        if (entries.get(keyId) === entry) entries.delete(keyId);
        options.onError?.(error, keyId);
        throw error;
      });
    return entry.promise;
  }

  function expiresAt(): number {
    if (ttlMs === 0) return Number.POSITIVE_INFINITY;
    return now() + ttlMs;
  }

  function touch(keyId: string, entry: Entry<K, T>): void {
    entries.delete(keyId);
    entries.set(keyId, entry);
  }

  function evictOverflow(): void {
    while (entries.size > maxEntries) {
      const oldest = entries.keys().next().value;
      if (oldest === undefined) return;
      const entry = entries.get(oldest);
      if (entry?.promise) {
        touch(oldest, entry);
        return;
      }
      entries.delete(oldest);
    }
  }

  function assertOpen(): void {
    if (disposed || cacheScope.disposed) throw new Error('AsyncCache is disposed');
  }
}

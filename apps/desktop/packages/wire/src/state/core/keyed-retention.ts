import { createScope, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import { stableStringify } from '@emdash/shared/util';

/**
 * Internal keyed-retention primitive: key → child scope + refcount + linger
 * timer + dispose-on-idle. `family` is built on it and the live-model replica
 * cache adopts it. Not part of the public state surface.
 */
export type KeyedRetentionOptions<K, V> = {
  /**
   * Builds the entry value. `entry.value` is not assigned yet while `create`
   * runs; the entry is passed so listeners created here can later retain the
   * exact entry via `retainEntry`.
   */
  create: (key: K, scope: Scope, entry: RetainedEntry<K, V>) => V;
  key?: (key: K) => string;
  /** Idle window before an unretained entry is disposed. `<= 0` disposes immediately. */
  lingerMs?: number;
  name?: string;
  scope?: Scope;
  clock?: Clock;
};

export type RetainedEntry<K, V> = {
  readonly key: K;
  readonly keyId: string;
  readonly scope: Scope;
  value: V;
};

export type KeyedRetention<K, V> = {
  /** Returns the entry for `key`, creating it (idle, linger armed) if missing. */
  ensure(key: K): RetainedEntry<K, V>;
  peek(key: K): RetainedEntry<K, V> | undefined;
  /** Creates the entry if missing and holds a refcount; never arms a birth linger. */
  retain(key: K): () => void;
  /** Retains `entry` if it is still current; a stale entry yields a no-op release. */
  retainEntry(entry: RetainedEntry<K, V>): () => void;
  /** Disposes the current entry for `key` now, regardless of refcount. */
  evict(key: K, error?: unknown): Promise<void>;
  /** In-flight disposal for `key`, if any — lets async adopters serialize re-creation. */
  pendingDisposal(key: K): Promise<void> | undefined;
  dispose(): Promise<void>;
  readonly disposed: boolean;
};

type Entry<K, V> = RetainedEntry<K, V> & {
  value: V;
  refCount: number;
  timer: TimerHandle | undefined;
};

export function keyedRetention<K, V>(options: KeyedRetentionOptions<K, V>): KeyedRetention<K, V> {
  const keyFor = options.key ?? stableStringify;
  const clock = options.clock ?? systemClock;
  const rootScope =
    options.scope ?? createScope({ label: options.name ?? 'keyed-retention', clock });
  const entries = new Map<string, Entry<K, V>>();
  const pendingDisposals = new Map<string, Promise<void>>();
  const lingerMs = options.lingerMs ?? 0;
  let disposed = false;

  rootScope.add(async () => {
    disposed = true;
    const current = [...entries.values()];
    entries.clear();
    await Promise.all(
      current.map((entry) => {
        clearTimer(entry);
        return entry.scope.dispose();
      })
    );
  });

  return {
    ensure(key) {
      const entry = entryFor(key);
      if (entry.refCount > 0) clearTimer(entry);
      else scheduleDispose(entry);
      return entry;
    },
    peek(key) {
      return entries.get(keyFor(key));
    },
    retain(key) {
      return retainEntry(entryFor(key));
    },
    retainEntry(entry) {
      const current = entries.get(entry.keyId);
      if (current !== entry) return () => {};
      return retainEntry(current);
    },
    evict(key, error) {
      const entry = entries.get(keyFor(key));
      if (!entry) return pendingDisposals.get(keyFor(key)) ?? Promise.resolve();
      return disposeEntry(entry, error);
    },
    pendingDisposal(key) {
      return pendingDisposals.get(keyFor(key));
    },
    async dispose() {
      if (disposed) return;
      disposed = true;
      await rootScope.dispose();
      entries.clear();
    },
    get disposed() {
      return disposed || rootScope.disposed;
    },
  };

  function entryFor(key: K): Entry<K, V> {
    if (disposed || rootScope.disposed)
      throw new Error(`${options.name ?? 'Keyed retention'} is disposed`);
    const keyId = keyFor(key);
    const existing = entries.get(keyId);
    if (existing) return existing;
    const scope = rootScope.child(keyId);
    const entry: Entry<K, V> = {
      key,
      keyId,
      scope,
      value: undefined as V,
      refCount: 0,
      timer: undefined,
    };
    try {
      entry.value = options.create(key, scope, entry);
    } catch (error) {
      void scope.dispose(error);
      throw error;
    }
    entries.set(keyId, entry);
    return entry;
  }

  function retainEntry(entry: Entry<K, V>): () => void {
    clearTimer(entry);
    entry.refCount += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      entry.refCount = Math.max(0, entry.refCount - 1);
      if (entry.refCount === 0) scheduleDispose(entry);
    };
  }

  function scheduleDispose(entry: Entry<K, V>): void {
    if (entries.get(entry.keyId) !== entry || entry.refCount > 0) return;
    clearTimer(entry);
    if (lingerMs <= 0) {
      void disposeEntry(entry);
      return;
    }
    entry.timer = clock.schedule(
      lingerMs,
      () => {
        entry.timer = undefined;
        void disposeEntry(entry);
      },
      { unref: true }
    );
  }

  function disposeEntry(entry: Entry<K, V>, error?: unknown): Promise<void> {
    if (entries.get(entry.keyId) !== entry) {
      return pendingDisposals.get(entry.keyId) ?? Promise.resolve();
    }
    clearTimer(entry);
    entries.delete(entry.keyId);
    const disposal = entry.scope.dispose(error).finally(() => {
      if (pendingDisposals.get(entry.keyId) === disposal) pendingDisposals.delete(entry.keyId);
    });
    pendingDisposals.set(entry.keyId, disposal);
    return disposal;
  }

  function clearTimer(entry: Entry<K, V>): void {
    entry.timer?.dispose();
    entry.timer = undefined;
  }
}

import { once, type Lease, type PendingLease } from '../lifecycle';
import { err, ok, type Result } from '../result';
import { systemClock, type Clock, type TimerHandle } from '../scheduling';
import { createScope, type Scope } from './scope';

export interface ResourceCache<K, T> {
  acquire(key: K): PendingLease<T>;
  peek(key: K): T | undefined;
  invalidate(key: K): Promise<void>;
  dispose(): Promise<void>;
}

export type CreateResourceCacheOptions<K, T> = {
  key: (key: K) => string;
  scope?: Scope;
  label?: string;
  idleTtlMs?: number;
  clock?: Clock;
  create: (key: K, scope: Scope) => Promise<T> | T;
  onError?: (error: unknown, key: string) => void;
};

type Entry<K, T> = {
  key: K;
  keyId: string;
  scope: Scope;
  refCount: number;
  hasValue: boolean;
  value: T | undefined;
  createPromise: Promise<T> | undefined;
  disposePromise: Promise<void> | undefined;
  idleTimer: TimerHandle | undefined;
};

export function createResourceCache<K, T>(
  options: CreateResourceCacheOptions<K, T>
): ResourceCache<K, T> {
  const clock = options.clock ?? systemClock;
  const cacheScope = options.scope
    ? options.scope.child(options.label ?? 'resource-cache')
    : createScope({ label: options.label, clock });
  const entries = new Map<string, Entry<K, T>>();
  const idleTtlMs = options.idleTtlMs ?? 0;
  let disposed = false;
  let disposePromise: Promise<void> | undefined;
  let disposeEntriesPromise: Promise<void> | undefined;

  cacheScope.add(() => disposeEntries());

  return {
    acquire(key): PendingLease<T> {
      return acquirePendingLease(key);
    },
    peek(key): T | undefined {
      const entry = entries.get(options.key(key));
      return entry?.hasValue === true ? entry.value : undefined;
    },
    async invalidate(key): Promise<void> {
      const entry = entries.get(options.key(key));
      if (!entry) return;
      await disposeEntry(entry);
    },
    async dispose(): Promise<void> {
      if (disposePromise) return disposePromise;
      disposed = true;
      disposePromise = cacheScope.dispose();
      return disposePromise;
    },
  };

  function acquirePendingLease(key: K): PendingLease<T> {
    let entry: Entry<K, T> | undefined;
    let released = false;

    const ready = (async (): Promise<T> => {
      if (disposed || cacheScope.disposed) throw new Error('ResourceCache is disposed');

      const keyId = options.key(key);
      let current = entries.get(keyId);
      if (current?.disposePromise) {
        await current.disposePromise;
        if (disposed || cacheScope.disposed) throw new Error('ResourceCache is disposed');
        current = entries.get(keyId);
      }

      if (released) throw new Error('ResourceCache lease was released before ready');

      if (!current) {
        current = createEntry(key, keyId);
        entries.set(keyId, current);
      }

      entry = current;
      clearIdleTimer(current);
      current.refCount += 1;

      try {
        return await ensureCreated(current);
      } catch (error) {
        if (!released) await releaseEntry(current);
        throw error;
      }
    })();
    ready.catch(() => {});

    return {
      ready: () => ready,
      release: once(async () => {
        released = true;
        if (entry) await releaseEntry(entry);
      }),
    };
  }

  function createEntry(key: K, keyId: string): Entry<K, T> {
    const entry: Entry<K, T> = {
      key,
      keyId,
      scope: cacheScope.child(entryScopeLabel(keyId)),
      refCount: 0,
      hasValue: false,
      value: undefined,
      createPromise: undefined,
      disposePromise: undefined,
      idleTimer: undefined,
    };
    // Registered once per entry; release cycles only reschedule the timer.
    entry.scope.add(() => clearIdleTimer(entry));
    return entry;
  }

  function entryScopeLabel(keyId: string): string {
    return options.scope || options.label ? keyId : `resource-cache:${keyId}`;
  }

  async function disposeEntries(): Promise<void> {
    if (disposeEntriesPromise) return disposeEntriesPromise;
    disposed = true;
    disposeEntriesPromise = (async () => {
      const current = [...entries.values()];
      await Promise.all(current.map((entry) => disposeEntry(entry)));
      entries.clear();
    })();
    return disposeEntriesPromise;
  }

  function ensureCreated(entry: Entry<K, T>): Promise<T> {
    if (entry.hasValue) return Promise.resolve(entry.value as T);
    if (entry.createPromise) return entry.createPromise;

    const createRun = entry.scope.run('create', () => options.create(entry.key, entry.scope));
    entry.createPromise = createRun
      .value()
      .then((value) => {
        entry.createPromise = undefined;
        if (disposed || entries.get(entry.keyId) !== entry || entry.scope.disposed) {
          throw new Error('ResourceCache entry was disposed during creation');
        }
        entry.hasValue = true;
        entry.value = value;
        if (entry.refCount === 0) scheduleDispose(entry);
        return value;
      })
      .catch(async (error: unknown) => {
        entry.createPromise = undefined;
        if (entries.get(entry.keyId) === entry) entries.delete(entry.keyId);
        options.onError?.(error, entry.keyId);
        await entry.scope.dispose(error);
        throw error;
      });

    return entry.createPromise;
  }

  function releaseEntry(entry: Entry<K, T>): Promise<void> {
    if (entries.get(entry.keyId) !== entry) return Promise.resolve();
    if (entry.refCount > 0) entry.refCount -= 1;
    if (entry.refCount > 0) return Promise.resolve();
    if (entry.createPromise && !entry.hasValue) return Promise.resolve();
    return scheduleDispose(entry);
  }

  function scheduleDispose(entry: Entry<K, T>): Promise<void> {
    if (entry.disposePromise || entries.get(entry.keyId) !== entry) return Promise.resolve();
    clearIdleTimer(entry);
    if (idleTtlMs <= 0) {
      return disposeEntry(entry);
    }
    entry.idleTimer = clock.schedule(
      idleTtlMs,
      () => {
        entry.idleTimer = undefined;
        void disposeEntry(entry);
      },
      { unref: true }
    );
    return Promise.resolve();
  }

  async function disposeEntry(entry: Entry<K, T>): Promise<void> {
    if (entry.disposePromise) return entry.disposePromise;
    clearIdleTimer(entry);
    entry.disposePromise = entry.scope.dispose().finally(() => {
      if (entries.get(entry.keyId) === entry) entries.delete(entry.keyId);
    });
    return entry.disposePromise;
  }

  function clearIdleTimer(entry: Entry<K, T>): void {
    if (!entry.idleTimer) return;
    entry.idleTimer.dispose();
    entry.idleTimer = undefined;
  }
}

export async function acquireResourceAsResult<K, T, E>(
  cache: ResourceCache<K, T>,
  key: K,
  isExpectedError: (error: unknown) => error is E
): Promise<Result<Lease<T>, E>> {
  const pending = cache.acquire(key);

  try {
    const value = await pending.ready();
    return ok({ value, release: pending.release });
  } catch (error) {
    if (isExpectedError(error)) return err(error);
    throw error;
  }
}

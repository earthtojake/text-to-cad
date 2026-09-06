import { once, type PendingLease } from '@emdash/shared';
import type { ResourceCache, Scope } from '@emdash/shared/concurrency';
import type { Clock } from '@emdash/shared/scheduling';
import { keyedRetention, type RetainedEntry } from '../../state/core/keyed-retention';

/**
 * Replica resource retention built on the state kernel's internal
 * keyed-retention primitive (key → child scope + refcount + linger timer +
 * dispose-on-idle), adapted to async creation with pending leases.
 */
export type ReplicaResourceCacheOptions<K, T> = {
  key: (key: K) => string;
  lingerMs?: number;
  label?: string;
  scope?: Scope;
  clock?: Clock;
  create: (key: K, scope: Scope) => Promise<T> | T;
  onError?: (error: unknown, key: string) => void;
};

type AsyncSlot<T> = {
  hasValue: boolean;
  value: T | undefined;
  createPromise: Promise<T> | undefined;
};

export function createReplicaResourceCache<K, T>(
  options: ReplicaResourceCacheOptions<K, T>
): ResourceCache<K, T> {
  const retention = keyedRetention<K, AsyncSlot<T>>({
    key: options.key,
    lingerMs: options.lingerMs ?? 0,
    name: options.label ?? 'replica-resource-cache',
    scope: options.scope,
    clock: options.clock,
    create: () => ({ hasValue: false, value: undefined, createPromise: undefined }),
  });

  return {
    acquire(key): PendingLease<T> {
      let releaseEntry: (() => void) | undefined;
      let released = false;

      const ready = (async (): Promise<T> => {
        assertActive();
        const pending = retention.pendingDisposal(key);
        if (pending) {
          await pending;
          assertActive();
        }
        if (released) throw new Error('ResourceCache lease was released before ready');

        releaseEntry = retention.retain(key);
        const entry = retention.ensure(key);
        try {
          return await ensureCreated(entry);
        } catch (error) {
          if (!released) {
            released = true;
            releaseEntry();
          }
          throw error;
        }
      })();
      ready.catch(() => {});

      return {
        ready: () => ready,
        release: once(async () => {
          released = true;
          releaseEntry?.();
        }),
      };
    },
    peek(key): T | undefined {
      const entry = retention.peek(key);
      return entry?.value.hasValue === true ? entry.value.value : undefined;
    },
    async invalidate(key): Promise<void> {
      await retention.evict(key);
    },
    dispose(): Promise<void> {
      return retention.dispose();
    },
  };

  function ensureCreated(entry: RetainedEntry<K, AsyncSlot<T>>): Promise<T> {
    const slot = entry.value;
    if (slot.hasValue) return Promise.resolve(slot.value as T);
    if (slot.createPromise) return slot.createPromise;

    // Hold the entry while creation is in flight so a lease released
    // mid-create does not dispose the scope out from under the factory.
    const releaseCreateHold = retention.retainEntry(entry);
    const createRun = entry.scope.run('create', () => options.create(entry.key, entry.scope));
    slot.createPromise = createRun
      .value()
      .then((value) => {
        slot.createPromise = undefined;
        if (retention.disposed || retention.peek(entry.key) !== entry || entry.scope.disposed) {
          throw new Error('ResourceCache entry was disposed during creation');
        }
        slot.hasValue = true;
        slot.value = value;
        releaseCreateHold();
        return value;
      })
      .catch(async (error: unknown) => {
        slot.createPromise = undefined;
        options.onError?.(error, entry.keyId);
        if (retention.peek(entry.key) === entry) await retention.evict(entry.key, error);
        releaseCreateHold();
        throw error;
      });

    return slot.createPromise;
  }

  function assertActive(): void {
    if (retention.disposed) throw new Error('ResourceCache is disposed');
  }
}

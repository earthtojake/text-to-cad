import { createEmitter, err, ok, type Emitter } from '@emdash/shared';
import { createResourceCache, createScope, type Scope } from '@emdash/shared/concurrency';
import { runWithTimeout } from '@emdash/shared/scheduling';
import type { IWatchService, WatchEvent } from '#services/fs-watch/api';
import type { WatchBackend, WatchKey, WatchOnError } from './backend';
import { realpathOrResolve } from './paths';

export type CreateWatchServiceOptions = {
  backend: WatchBackend;
  scope?: Scope;
  graceMs?: number;
  startupTimeoutMs?: number;
  onError?: WatchOnError;
};

const DEFAULT_STARTUP_TIMEOUT_MS = 10_000;

type WatchChannel = {
  events: Emitter<WatchEvent[]>;
  resync: Emitter<void>;
};

export function createWatchService(options: CreateWatchServiceOptions): IWatchService {
  const serviceScope = options.scope
    ? options.scope.child('fs-watch-service')
    : createScope({ label: 'fs-watch-service' });
  const consumers = new Set<Scope>();
  let disposed = false;

  const channels = createResourceCache<WatchKey, WatchChannel>({
    key: watchKey,
    scope: serviceScope,
    label: 'channels',
    idleTtlMs: options.graceMs ?? 0,
    onError: (error, key) => options.onError?.(`watch ${key}`, error),
    create: async (key, scope) => {
      const events = createEmitter<WatchEvent[]>();
      const resync = createEmitter<void>();
      scope.add(() => {
        events.clear();
        resync.clear();
      });
      await runWithTimeout(
        () =>
          options.backend.subscribe(
            key,
            {
              events: (batch) => events.emit(batch),
              resync: () => resync.emit(),
            },
            scope
          ),
        {
          timeoutMs: options.startupTimeoutMs ?? DEFAULT_STARTUP_TIMEOUT_MS,
          signal: scope.signal,
        }
      );
      return { events, resync };
    },
  });

  return {
    watch(root, onEvents, watchOptions = {}) {
      if (disposed || serviceScope.disposed) throw new Error('FsWatchService disposed');

      const key = normalizeWatchKey(root, watchOptions.ignore);
      const lease = channels.acquire(key);
      const consumerScope = serviceScope.child('consumer');
      consumers.add(consumerScope);
      consumerScope.add(() => {
        consumers.delete(consumerScope);
      });

      let released = false;
      const ready = lease.ready().then(
        (channel) => {
          if (released || consumerScope.disposed) return ok(undefined);
          consumerScope.add(
            channel.events.subscribe(
              withDebounce(onEvents, watchOptions.debounceMs ?? 0, consumerScope)
            )
          );
          if (watchOptions.onResync)
            consumerScope.add(channel.resync.subscribe(watchOptions.onResync));
          return ok(undefined);
        },
        (error: unknown) => {
          if (!released && !consumerScope.disposed) {
            try {
              watchOptions.onError?.(error);
            } catch {
              // Failure observers are best-effort and must not break the ready Result channel.
            }
          }
          return err(error);
        }
      );

      return {
        ready: () => ready,
        release: async () => {
          if (released) return;
          released = true;
          await consumerScope.dispose();
          await lease.release();
        },
      };
    },
    async dispose() {
      if (disposed) return;
      disposed = true;
      const activeConsumers = [...consumers];
      consumers.clear();
      await Promise.allSettled(activeConsumers.map((consumer) => consumer.dispose()));
      await channels.dispose();
      await options.backend.dispose?.();
      await serviceScope.dispose();
    },
  };
}

function normalizeWatchKey(root: string, ignore: string[] | undefined): WatchKey {
  return {
    root: realpathOrResolve(root),
    ignore: [...(ignore ?? [])].sort(),
  };
}

function watchKey(key: WatchKey): string {
  return JSON.stringify(key);
}

function withDebounce(
  onEvents: (events: WatchEvent[]) => void,
  debounceMs: number,
  scope: Scope
): (events: WatchEvent[]) => void {
  if (debounceMs <= 0) return onEvents;

  let pending: WatchEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;

  const clear = (): void => {
    if (timer) clearTimeout(timer);
    timer = null;
    pending = [];
  };
  scope.add(clear);

  return (events) => {
    pending.push(...events);
    if (timer) return;

    timer = setTimeout(() => {
      timer = null;
      const batch = pending;
      pending = [];
      if (batch.length > 0) onEvents(batch);
    }, debounceMs);
  };
}

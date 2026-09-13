import type { PendingLease } from '../lifecycle';
import { createResourceCache, type ResourceCache } from './resource-cache';
import type { Scope } from './scope';

const sharedKey = Symbol('shared-resource');

export interface SharedResource<T> {
  acquire(): PendingLease<T>;
  peek(): T | undefined;
  invalidate(): Promise<void>;
  dispose(): Promise<void>;
}

export type CreateSharedResourceOptions<T> = {
  scope?: Scope;
  label?: string;
  idleTtlMs?: number;
  create: (scope: Scope) => Promise<T> | T;
  onError?: (error: unknown) => void;
};

export function createSharedResource<T>(
  options: CreateSharedResourceOptions<T>
): SharedResource<T> {
  const cache: ResourceCache<typeof sharedKey, T> = createResourceCache({
    key: () => 'shared',
    scope: options.scope,
    label: options.label,
    idleTtlMs: options.idleTtlMs,
    create: (_key, scope) => options.create(scope),
    onError: (error) => options.onError?.(error),
  });

  return {
    acquire() {
      return cache.acquire(sharedKey);
    },
    peek() {
      return cache.peek(sharedKey);
    },
    invalidate() {
      return cache.invalidate(sharedKey);
    },
    dispose() {
      return cache.dispose();
    },
  };
}

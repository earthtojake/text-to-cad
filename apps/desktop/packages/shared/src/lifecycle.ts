import { log } from '@emdash/shared/logger';

export type Unsubscribe = () => void;

export interface Lease<T> {
  readonly value: T;
  release(): Promise<void>;
}

export interface PendingLease<T> {
  ready(): Promise<T>;
  release(): Promise<void>;
}

export function once<T>(fn: () => Promise<T>): () => Promise<T> {
  let promise: Promise<T> | undefined;
  return () => (promise ??= fn());
}

export function toPendingLease<T>(leasePromise: Promise<Lease<T>>): PendingLease<T> {
  leasePromise.catch(() => {});
  return {
    ready: async () => (await leasePromise).value,
    release: once(async () => {
      try {
        await (await leasePromise).release();
      } catch (error) {
        log.warn('pending lease release failed', { error });
      }
    }),
  };
}

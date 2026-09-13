/**
 * Canonical abort-reason mapping: an Error reason passes through; otherwise the
 * fallback message becomes an Error; otherwise the raw reason or a DOMException.
 * Rejections stay Errors whenever possible. Note that DOMException is an Error
 * in modern Node, so a default abort reason passes through and the fallback
 * only beats genuinely non-Error reasons.
 */
export function abortReason(signal: AbortSignal, fallback?: string): unknown {
  if (signal.reason instanceof Error) return signal.reason;
  if (fallback !== undefined) return new Error(fallback);
  return signal.reason ?? new DOMException('Aborted', 'AbortError');
}

export function throwIfAborted(signal: AbortSignal | undefined, fallback?: string): void {
  if (signal?.aborted) throw abortReason(signal, fallback);
}

export type AbortableWaitOptions = {
  signal?: AbortSignal;
  fallback?: string;
};

export type AbortableWaitSettle<T> = {
  resolve(value: T | PromiseLike<T>): void;
  reject(error: unknown): void;
};

export type AbortableWaitExecutor<T> = (settle: AbortableWaitSettle<T>) => (() => void) | void;

/**
 * Awaits a settlement racing an optional AbortSignal, owning the whole
 * choreography: the single-settlement guard, abort-listener add/remove, the
 * initial-aborted check, canonical abort-reason mapping, and
 * cleanup-on-any-settlement.
 *
 * The executor registers the wait (start a timer, enqueue a waiter, chain a
 * promise) and returns its undo action, which runs exactly once on the first
 * settlement — resolution, rejection, or abort.
 */
export function abortableWait<T>(
  options: AbortableWaitOptions,
  executor: AbortableWaitExecutor<T>
): Promise<T> {
  const signal = options.signal;
  if (signal?.aborted) return Promise.reject(abortReason(signal, options.fallback));

  return new Promise<T>((resolve, reject) => {
    let settled = false;
    let cleanup: (() => void) | void;
    let cleanupRan = false;

    const runCleanup = (): void => {
      if (cleanupRan || !cleanup) return;
      cleanupRan = true;
      cleanup();
    };

    const finish = (complete: () => void): void => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', onAbort);
      runCleanup();
      complete();
    };

    const onAbort = (): void => {
      finish(() => reject(abortReason(signal as AbortSignal, options.fallback)));
    };

    const settle: AbortableWaitSettle<T> = {
      resolve: (value) => finish(() => resolve(value)),
      reject: (error) => finish(() => reject(error)),
    };

    signal?.addEventListener('abort', onAbort, { once: true });

    try {
      cleanup = executor(settle);
    } catch (error) {
      settle.reject(error);
      return;
    }
    // The executor may settle synchronously, before its cleanup is returned.
    if (settled) runCleanup();
  });
}

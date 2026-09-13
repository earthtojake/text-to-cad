import { abortableWait } from '../scheduling';
import { stableStringify } from '../util';
import type { SignalContext, SignalHandler } from './handler';

export type DeduplicateOptions<I> = {
  key?: (input: I) => string;
  cancelWhenUnused?: boolean;
};

type Entry<O> = {
  controller: AbortController;
  promise: Promise<O>;
  settled: boolean;
  waiters: number;
};

export function deduplicate(): <I, O, C extends SignalContext>(
  next: SignalHandler<I, O, C>
) => SignalHandler<I, O, C>;
export function deduplicate<I>(
  options: DeduplicateOptions<I>
): <O, C extends SignalContext>(next: SignalHandler<I, O, C>) => SignalHandler<I, O, C>;
export function deduplicate<I>(options: DeduplicateOptions<I> = {}) {
  return function <O, C extends SignalContext>(
    next: SignalHandler<I, O, C>
  ): SignalHandler<I, O, C> {
    const keyOf = options.key ?? stableStringify;
    const inFlight = new Map<string, Entry<O>>();

    return (input, context) => {
      const key = keyOf(input);
      let entry = inFlight.get(key);
      if (!entry) {
        entry = createEntry(key, input, context);
        inFlight.set(key, entry);
      }
      return waitForEntry(key, entry, context.signal);
    };

    function createEntry(key: string, input: I, context: C): Entry<O> {
      const controller = new AbortController();
      const entry = {
        controller,
        settled: false,
        waiters: 0,
      } as Entry<O>;
      let promise: Promise<O>;
      try {
        promise = next(input, { ...context, signal: controller.signal } as C);
      } catch (error) {
        promise = Promise.reject(error);
      }
      promise = promise.finally(() => {
        entry.settled = true;
        if (inFlight.get(key)?.promise === promise) inFlight.delete(key);
      });
      promise.catch(() => {});
      entry.promise = promise;
      return entry;
    }

    function waitForEntry(
      key: string,
      entry: Entry<O>,
      signal: AbortSignal | undefined
    ): Promise<O> {
      return abortableWait<O>({ signal }, (settle) => {
        entry.waiters += 1;
        entry.promise.then(settle.resolve, settle.reject);
        return () => {
          entry.waiters -= 1;
          if (
            options.cancelWhenUnused &&
            entry.waiters === 0 &&
            !entry.settled &&
            !entry.controller.signal.aborted
          ) {
            if (inFlight.get(key) === entry) inFlight.delete(key);
            entry.controller.abort(new Error('Deduplicated request has no waiters'));
          }
        };
      });
    }
  };
}

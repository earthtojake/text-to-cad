/**
 * @vitest-environment jsdom
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAsyncAction } from './use-async-action';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

describe('useAsyncAction', () => {
  it('tracks pending state and stores successful data', async () => {
    const deferred = createDeferred<void>();
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useAsyncAction(
        async (_signal, value: string) => {
          await deferred.promise;
          return value;
        },
        { onSuccess }
      )
    );

    let triggerPromise: Promise<void> | undefined;
    act(() => {
      triggerPromise = result.current[0]('resolved');
    });

    expect(result.current[1]).toBeUndefined();
    expect(result.current[2]).toBe(true);

    await act(async () => {
      deferred.resolve();
      await triggerPromise;
    });

    expect(result.current[1]).toBe('resolved');
    expect(result.current[2]).toBe(false);
    expect(onSuccess).toHaveBeenCalledWith('resolved');
  });

  it('clears existing data when a new action starts', async () => {
    const firstDeferred = createDeferred<string>();
    const secondDeferred = createDeferred<string>();
    const deferreds = [firstDeferred, secondDeferred];
    let callIndex = 0;
    const { result } = renderHook(() => useAsyncAction(async () => deferreds[callIndex++].promise));

    let firstTriggerPromise: Promise<void> | undefined;
    act(() => {
      firstTriggerPromise = result.current[0]();
    });

    await act(async () => {
      firstDeferred.resolve('first');
      await firstTriggerPromise;
    });

    expect(result.current[1]).toBe('first');

    act(() => {
      void result.current[0]();
    });

    expect(result.current[1]).toBeUndefined();
    expect(result.current[2]).toBe(true);

    await act(async () => {
      secondDeferred.resolve('second');
    });

    await waitFor(() => {
      expect(result.current[1]).toBe('second');
    });
  });

  it('normalizes errors and calls onError', async () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useAsyncAction(
        async () => {
          throw 'boom';
        },
        { onError }
      )
    );

    await act(async () => {
      await result.current[0]();
    });

    expect(result.current[1]).toBeUndefined();
    expect(result.current[2]).toBe(false);
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'boom' }));
  });

  it('cancels the current action and suppresses abort errors', async () => {
    const onError = vi.fn();
    const signals: AbortSignal[] = [];
    const { result } = renderHook(() =>
      useAsyncAction(
        async (signal) => {
          signals.push(signal);
          return await new Promise<string>((_resolve, reject) => {
            signal.addEventListener('abort', () => {
              reject(new DOMException('Aborted', 'AbortError'));
            });
          });
        },
        { onError }
      )
    );

    act(() => {
      void result.current[0]();
    });

    expect(result.current[2]).toBe(true);

    act(() => {
      result.current[0].cancel();
    });

    expect(signals[0].aborted).toBe(true);
    expect(result.current[2]).toBe(false);

    await waitFor(() => {
      expect(onError).not.toHaveBeenCalled();
    });
  });

  it('cancels stale runs and keeps the latest result', async () => {
    const firstDeferred = createDeferred<string>();
    const secondDeferred = createDeferred<string>();
    const deferreds = [firstDeferred, secondDeferred];
    const signals: AbortSignal[] = [];
    let callIndex = 0;
    const { result } = renderHook(() =>
      useAsyncAction(async (signal) => {
        signals.push(signal);
        return await deferreds[callIndex++].promise;
      })
    );

    act(() => {
      void result.current[0]();
    });
    act(() => {
      void result.current[0]();
    });

    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);

    await act(async () => {
      firstDeferred.resolve('first');
      await firstDeferred.promise;
    });

    expect(result.current[1]).toBeUndefined();
    expect(result.current[2]).toBe(true);

    await act(async () => {
      secondDeferred.resolve('second');
      await secondDeferred.promise;
    });

    expect(result.current[1]).toBe('second');
    expect(result.current[2]).toBe(false);
  });

  it('aborts in-flight actions on unmount and ignores late results', async () => {
    const deferred = createDeferred<string>();
    const onSuccess = vi.fn();
    const signals: AbortSignal[] = [];
    const { result, unmount } = renderHook(() =>
      useAsyncAction(
        async (signal) => {
          signals.push(signal);
          return await deferred.promise;
        },
        { onSuccess }
      )
    );

    act(() => {
      void result.current[0]();
    });

    unmount();
    expect(signals[0].aborted).toBe(true);

    await act(async () => {
      deferred.resolve('late');
      await deferred.promise;
    });

    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('keeps the trigger stable while using the latest action', async () => {
    const firstAction = vi.fn(async () => 'first');
    const secondAction = vi.fn(async () => 'second');
    const { result, rerender } = renderHook(({ action }) => useAsyncAction(action), {
      initialProps: { action: firstAction },
    });
    const trigger = result.current[0];

    rerender({ action: secondAction });

    expect(result.current[0]).toBe(trigger);

    await act(async () => {
      await result.current[0]();
    });

    expect(firstAction).not.toHaveBeenCalled();
    expect(secondAction).toHaveBeenCalled();
    expect(result.current[1]).toBe('second');
  });
});

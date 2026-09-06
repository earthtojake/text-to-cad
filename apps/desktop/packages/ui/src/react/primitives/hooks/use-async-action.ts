import * as React from 'react';

export type AsyncActionTrigger<TArgs extends unknown[]> = ((...args: TArgs) => Promise<void>) & {
  cancel: () => void;
};

export interface UseAsyncActionOptions<TResult> {
  onSuccess?: (data: TResult) => void;
  onError?: (error: Error) => void;
}

export function useAsyncAction<TArgs extends unknown[], TResult>(
  action: (signal: AbortSignal, ...args: TArgs) => Promise<TResult>,
  options?: UseAsyncActionOptions<TResult>
): [AsyncActionTrigger<TArgs>, TResult | undefined, boolean] {
  const [data, setData] = React.useState<TResult | undefined>(undefined);
  const [inProgress, setInProgress] = React.useState(false);

  const actionRef = React.useRef(action);
  const optionsRef = React.useRef(options);
  const abortControllerRef = React.useRef<AbortController | null>(null);
  const requestIdRef = React.useRef(0);
  const isMountedRef = React.useRef(true);

  actionRef.current = action;
  optionsRef.current = options;

  React.useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

  const trigger = React.useCallback(async (...args: TArgs) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      ++requestIdRef.current;
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const requestId = ++requestIdRef.current;

    setInProgress(true);
    setData(undefined);

    try {
      const result = await actionRef.current(abortController.signal, ...args);
      if (requestId !== requestIdRef.current || !isMountedRef.current) return;
      setData(result);
      optionsRef.current?.onSuccess?.(result);
    } catch (error) {
      if (requestId !== requestIdRef.current || !isMountedRef.current) return;
      if (abortController.signal.aborted) return;
      const normalizedError = error instanceof Error ? error : new Error(String(error));
      optionsRef.current?.onError?.(normalizedError);
    } finally {
      if (requestId === requestIdRef.current && isMountedRef.current) {
        setInProgress(false);
        abortControllerRef.current = null;
      }
    }
  }, []);

  const cancel = React.useCallback(() => {
    if (!abortControllerRef.current) return;
    abortControllerRef.current.abort();
    ++requestIdRef.current;
    setInProgress(false);
    abortControllerRef.current = null;
  }, []);

  const triggerWithCancel = React.useMemo(
    () => Object.assign(trigger, { cancel }),
    [trigger, cancel]
  );

  return [triggerWithCancel, data, inProgress];
}

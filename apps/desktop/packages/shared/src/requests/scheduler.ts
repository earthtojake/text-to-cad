import {
  createConcurrencyLimiter,
  createMailbox,
  type Disposable,
  type Scope,
} from '../concurrency';
import { abortableWait, abortReason, throwIfAborted } from '../scheduling';
import type { RateGate } from './rate-gate';

export const requestPriorities = {
  background: 0,
  task: 1,
  interactive: 2,
} as const;

export type RequestPriority = (typeof requestPriorities)[keyof typeof requestPriorities];

export type ScheduledRequest<T> = {
  priority: number;
  key?: string;
  cost?: number;
  run(signal: AbortSignal): Promise<T>;
};

export type RequestSchedulerStats = {
  pending: number;
  inFlight: number;
};

export interface RequestScheduler extends Disposable {
  readonly stats: RequestSchedulerStats;
  submit<T>(request: ScheduledRequest<T>, options?: { signal?: AbortSignal }): Promise<T>;
}

export type CreateRequestSchedulerOptions = {
  scope: Scope;
  maxConcurrency: number;
  gate?: RateGate;
  label?: string;
};

type EntryState = 'queued' | 'gating' | 'running' | 'settled';

type RequestEntry = {
  sequence: number;
  heapVersion: number;
  priority: number;
  key: string | undefined;
  cost: number;
  run(signal: AbortSignal): Promise<unknown>;
  controller: AbortController;
  state: EntryState;
  waiters: number;
  promise: Promise<unknown>;
  resolve(value: unknown): void;
  reject(error: unknown): void;
};

type HeapItem = {
  entry: RequestEntry;
  version: number;
  priority: number;
  sequence: number;
};

export function createRequestScheduler(options: CreateRequestSchedulerOptions): RequestScheduler {
  if (!Number.isInteger(options.maxConcurrency) || options.maxConcurrency < 1) {
    throw new Error('Request scheduler concurrency must be a positive integer');
  }

  const scope = options.scope.child(options.label ?? 'request-scheduler');
  const limiter = createConcurrencyLimiter(options.maxConcurrency);
  const gate = options.gate ?? unlimitedRateGate;
  const wake = scope.use(createMailbox<number>({ capacity: 1, overflow: 'drop-newest' }));
  const heap: HeapItem[] = [];
  const keyed = new Map<string, RequestEntry>();
  const entries = new Set<RequestEntry>();
  const activePromises = new Set<Promise<void>>();
  let sequence = 0;
  let pending = 0;
  let inFlight = 0;
  let disposePromise: Promise<void> | undefined;

  scope.add(async () => {
    const reason = abortReason(scope.signal, 'Request scheduler disposed');
    for (const entry of entries) {
      if (!entry.controller.signal.aborted) entry.controller.abort(reason);
      if (entry.state === 'queued') settle(entry, false, reason);
    }
    heap.length = 0;
    pending = 0;
    await Promise.allSettled([...activePromises]);
  });

  void scope.run('pump', async (signal) => {
    for (;;) {
      await wake.take({ signal });
      await dispatch(signal);
    }
  }).exit;

  return {
    get stats(): RequestSchedulerStats {
      return { pending, inFlight };
    },
    submit<T>(
      request: ScheduledRequest<T>,
      submitOptions: { signal?: AbortSignal } = {}
    ): Promise<T> {
      if (scope.disposed) return Promise.reject(new Error('Request scheduler is disposed'));
      if (submitOptions.signal?.aborted) {
        return Promise.reject(abortReason(submitOptions.signal));
      }
      validateRequest(request);

      let entry = request.key !== undefined ? keyed.get(request.key) : undefined;
      if (!entry) {
        entry = createEntry(request);
        entries.add(entry);
        if (entry.key !== undefined) keyed.set(entry.key, entry);
        enqueue(entry);
      } else if (entry.state === 'queued' && request.priority > entry.priority) {
        entry.priority = request.priority;
        enqueue(entry, true);
      }
      return waitForEntry<T>(entry, submitOptions.signal);
    },
    dispose(): Promise<void> {
      if (!disposePromise) disposePromise = scope.dispose(new Error('Request scheduler disposed'));
      return disposePromise;
    },
  };

  function createEntry<T>(request: ScheduledRequest<T>): RequestEntry {
    let resolve!: (value: unknown) => void;
    let reject!: (error: unknown) => void;
    const promise = new Promise<unknown>((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
    });
    promise.catch(() => {});
    return {
      sequence: sequence++,
      heapVersion: 0,
      priority: request.priority,
      key: request.key,
      cost: request.cost ?? 1,
      run: request.run,
      controller: new AbortController(),
      state: 'queued',
      waiters: 0,
      promise,
      resolve,
      reject,
    };
  }

  function enqueue(entry: RequestEntry, promotion = false): void {
    entry.heapVersion += 1;
    pushHeap(heap, {
      entry,
      version: entry.heapVersion,
      priority: entry.priority,
      sequence: entry.sequence,
    });
    if (!promotion) pending += 1;
    wake.tryOffer(1);
  }

  async function dispatch(signal: AbortSignal): Promise<void> {
    while (inFlight < options.maxConcurrency) {
      const entry = takeNext();
      if (!entry) return;
      pending -= 1;
      entry.state = 'gating';
      const requestSignal = AbortSignal.any([signal, entry.controller.signal]);
      try {
        await gate.acquire(entry.cost, requestSignal);
        throwIfAborted(requestSignal);
      } catch (error) {
        settle(entry, false, error);
        if (signal.aborted) throw abortReason(signal);
        continue;
      }

      entry.state = 'running';
      inFlight += 1;
      const execution = execute(entry).finally(() => {
        activePromises.delete(execution);
        inFlight -= 1;
        wake.tryOffer(1);
      });
      activePromises.add(execution);
    }
  }

  function takeNext(): RequestEntry | undefined {
    for (;;) {
      const item = popHeap(heap);
      if (!item) return undefined;
      if (
        item.entry.state !== 'queued' ||
        item.version !== item.entry.heapVersion ||
        item.entry.controller.signal.aborted
      ) {
        continue;
      }
      return item.entry;
    }
  }

  async function execute(entry: RequestEntry): Promise<void> {
    const signal = AbortSignal.any([scope.signal, entry.controller.signal]);
    try {
      const value = await limiter.run(signal, async () => await entry.run(signal));
      settle(entry, true, value);
    } catch (error) {
      settle(entry, false, error);
    }
  }

  function settle(entry: RequestEntry, success: boolean, value: unknown): void {
    if (entry.state === 'settled') return;
    if (entry.state === 'queued') pending = Math.max(0, pending - 1);
    entry.state = 'settled';
    entries.delete(entry);
    if (entry.key !== undefined && keyed.get(entry.key) === entry) keyed.delete(entry.key);
    if (success) entry.resolve(value);
    else entry.reject(value);
  }

  function waitForEntry<T>(entry: RequestEntry, signal: AbortSignal | undefined): Promise<T> {
    return abortableWait<T>({ signal, fallback: 'Scheduled request cancelled' }, (settlement) => {
      entry.waiters += 1;
      entry.promise.then((value) => settlement.resolve(value as T), settlement.reject);
      return () => {
        entry.waiters -= 1;
        if (entry.waiters === 0 && entry.state !== 'settled' && !entry.controller.signal.aborted) {
          const reason = signal?.aborted
            ? abortReason(signal)
            : new Error('Scheduled request has no waiters');
          if (entry.key !== undefined && keyed.get(entry.key) === entry) {
            keyed.delete(entry.key);
          }
          entry.controller.abort(reason);
          if (entry.state === 'queued') settle(entry, false, reason);
        }
      };
    });
  }
}

const unlimitedRateGate: RateGate = {
  async acquire(_cost, signal) {
    throwIfAborted(signal);
  },
  observe() {},
};

function validateRequest(request: ScheduledRequest<unknown>): void {
  if (!Number.isFinite(request.priority)) {
    throw new Error('Scheduled request priority must be finite');
  }
  if (request.cost !== undefined && (!Number.isFinite(request.cost) || request.cost < 0)) {
    throw new Error('Scheduled request cost must be a non-negative finite number');
  }
}

function pushHeap(heap: HeapItem[], item: HeapItem): void {
  heap.push(item);
  let index = heap.length - 1;
  while (index > 0) {
    const parent = Math.floor((index - 1) / 2);
    if (!comesBefore(heap[index]!, heap[parent]!)) break;
    [heap[index], heap[parent]] = [heap[parent]!, heap[index]!];
    index = parent;
  }
}

function popHeap(heap: HeapItem[]): HeapItem | undefined {
  const first = heap[0];
  const last = heap.pop();
  if (!first || !last || heap.length === 0) return first;
  heap[0] = last;
  let index = 0;
  for (;;) {
    const left = index * 2 + 1;
    const right = left + 1;
    let best = index;
    if (left < heap.length && comesBefore(heap[left]!, heap[best]!)) best = left;
    if (right < heap.length && comesBefore(heap[right]!, heap[best]!)) best = right;
    if (best === index) break;
    [heap[index], heap[best]] = [heap[best]!, heap[index]!];
    index = best;
  }
  return first;
}

function comesBefore(left: HeapItem, right: HeapItem): boolean {
  return (
    left.priority > right.priority ||
    (left.priority === right.priority && left.sequence < right.sequence)
  );
}

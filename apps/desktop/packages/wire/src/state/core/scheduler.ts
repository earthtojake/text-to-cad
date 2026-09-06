export type BatchMeta = {
  mutationIds?: readonly string[];
};

type Flushable = {
  __stateInstrumentation?: TurnInstrumentation;
  __flush(): void;
};

type TurnInstrumentation = {
  turnFlushed?: () => void;
};

let scheduled = false;
let flushing = false;
let batchDepth = 0;
let currentBatchMeta: BatchMeta | undefined;
const dirty = new Set<Flushable>();
const notifications = new Set<Flushable>();

export function batch<T>(work: () => T, meta: BatchMeta = {}): T {
  const previous = currentBatchMeta;
  batchDepth += 1;
  currentBatchMeta = mergeMeta(previous, meta);
  try {
    return work();
  } finally {
    batchDepth -= 1;
    currentBatchMeta = previous;
    if (batchDepth === 0) scheduleFlush();
  }
}

export function activeBatchMeta(): BatchMeta | undefined {
  return currentBatchMeta;
}

export function enqueueDirty(node: Flushable): void {
  dirty.add(node);
  scheduleFlush();
}

export function enqueueNotification(node: Flushable): void {
  notifications.add(node);
  scheduleFlush();
}

export function flushStateTurn(): void {
  if (flushing) return;
  scheduled = false;
  flushing = true;
  const instrumentation = new Set<TurnInstrumentation>();
  try {
    while (dirty.size > 0) {
      const current = [...dirty];
      dirty.clear();
      for (const node of current) {
        collectInstrumentation(instrumentation, node);
        node.__flush();
      }
    }

    const pending = [...notifications];
    notifications.clear();
    for (const node of pending) {
      collectInstrumentation(instrumentation, node);
      node.__flush();
    }
  } finally {
    for (const hooks of instrumentation) hooks.turnFlushed?.();
    flushing = false;
    if (dirty.size > 0 || notifications.size > 0) scheduleFlush();
  }
}

function scheduleFlush(): void {
  if (batchDepth > 0 || scheduled) return;
  scheduled = true;
  queueMicrotask(flushStateTurn);
}

function mergeMeta(left: BatchMeta | undefined, right: BatchMeta): BatchMeta | undefined {
  const ids = new Set<string>();
  for (const id of left?.mutationIds ?? []) ids.add(id);
  for (const id of right.mutationIds ?? []) ids.add(id);
  return ids.size > 0 ? { mutationIds: [...ids] } : left;
}

function collectInstrumentation(set: Set<TurnInstrumentation>, node: Flushable): void {
  if (node.__stateInstrumentation) set.add(node.__stateInstrumentation);
}

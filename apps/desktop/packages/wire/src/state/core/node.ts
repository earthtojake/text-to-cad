import type { Unsubscribe } from '@emdash/shared';
import { nodeConstructed, notifyObservedChange } from './observed-registry';
import { activeBatchMeta, enqueueNotification } from './scheduler';

export type StateStatus = 'live' | 'stale' | 'loading' | 'error';

export type Snapshot<T> = {
  value: T;
  status: StateStatus;
  revision: number;
  observedAt?: number;
  error?: unknown;
  mutationIds?: readonly string[];
  generation?: number;
};

export type Revision = {
  nodeId: string;
  revision: number;
  generation?: number;
  mutationIds?: readonly string[];
};

export type Readable<T> = {
  readonly __stateNode: StateNode<unknown>;
  readonly __stateValue?: T;
};

export type StateInstrumentation = {
  turnFlushed?: () => void;
  nodePublished?: (name: string | undefined) => void;
  nodeRecomputed?: (name: string | undefined) => void;
  observerError?: (error: unknown, name: string | undefined) => void;
};

export type CommitOptions = {
  mutationIds?: readonly string[];
  status?: StateStatus;
  observedAt?: number;
  error?: unknown;
  generation?: number;
  notify?: boolean;
};

export type Observer<T> = (snapshot: Snapshot<T>) => void;

export type Collector = {
  dependencies: Map<StateNode<unknown>, Snapshot<unknown>>;
  status: StateStatus;
  error: unknown;
};

let nextNodeId = 1;
let currentCollector: Collector | undefined;

export abstract class StateNode<T> {
  readonly id = `state:${nextNodeId++}`;
  readonly __stateNode: StateNode<unknown> = this as unknown as StateNode<unknown>;
  readonly __stateValue?: T;

  protected snapshotValue: Snapshot<T>;
  protected observers = new Set<Observer<T>>();
  protected dependents = new Set<{ markDirty(): void }>();
  private retainCount = 0;
  private notificationQueued = false;

  protected constructor(
    initialValue: T,
    protected readonly options: {
      name?: string;
      equals?: (left: T, right: T) => boolean;
      instrumentation?: StateInstrumentation;
      onObservedChange?: (observed: boolean) => void;
    } = {}
  ) {
    this.snapshotValue = {
      value: initialValue,
      status: 'live',
      revision: 0,
    };
    nodeConstructed(this as unknown as StateNode<unknown>);
  }

  get __stateInstrumentation(): StateInstrumentation | undefined {
    return this.options.instrumentation;
  }

  peek(): T {
    return this.currentSnapshot().value;
  }

  currentSnapshot(): Snapshot<T> {
    return this.snapshotValue;
  }

  observe(observer: Observer<T>, options: { immediate?: boolean } = {}): Unsubscribe {
    this.retain();
    this.observers.add(observer);
    if (options.immediate !== false) this.notifyObserver(observer, this.currentSnapshot());
    let disposed = false;
    return () => {
      if (disposed) return;
      disposed = true;
      this.observers.delete(observer);
      this.release();
    };
  }

  addDependent(dependent: { markDirty(): void }): void {
    this.dependents.add(dependent);
  }

  removeDependent(dependent: { markDirty(): void }): void {
    this.dependents.delete(dependent);
  }

  retain(): void {
    this.retainCount += 1;
    if (this.retainCount === 1) {
      this.onObserved();
      this.options.onObservedChange?.(true);
      notifyObservedChange(this as unknown as StateNode<unknown>, true);
    }
  }

  release(): void {
    if (this.retainCount === 0) return;
    this.retainCount -= 1;
    if (this.retainCount === 0) {
      this.onUnobserved();
      this.options.onObservedChange?.(false);
      notifyObservedChange(this as unknown as StateNode<unknown>, false);
    }
  }

  get observed(): boolean {
    return this.retainCount > 0;
  }

  protected commit(nextValue: T, options: CommitOptions = {}): Revision {
    const mutationIds = mergeMutationIds(activeBatchMeta()?.mutationIds, options.mutationIds);
    const nextStatus = options.status ?? this.snapshotValue.status;
    const nextError = options.error;
    const nextGeneration = options.generation ?? this.snapshotValue.generation;
    const equal =
      this.snapshotValue.status === nextStatus &&
      this.snapshotValue.error === nextError &&
      this.snapshotValue.generation === nextGeneration &&
      this.equals(this.snapshotValue.value, nextValue) &&
      sameIds(this.snapshotValue.mutationIds, mutationIds);

    if (!equal) {
      this.snapshotValue = {
        value: nextValue,
        status: nextStatus,
        revision: this.snapshotValue.revision + 1,
        observedAt: options.observedAt ?? this.snapshotValue.observedAt,
        error: nextError,
        mutationIds,
        generation: nextGeneration,
      };
      this.options.instrumentation?.nodePublished?.(this.options.name);
      for (const dependent of [...this.dependents]) dependent.markDirty();
      if (options.notify !== false) this.queueNotification();
    }

    return this.revision();
  }

  protected replaceSnapshot(snapshot: Snapshot<T>, options: { notify?: boolean } = {}): Revision {
    this.snapshotValue = {
      ...snapshot,
      revision: this.snapshotValue.revision + 1,
    };
    this.options.instrumentation?.nodePublished?.(this.options.name);
    for (const dependent of [...this.dependents]) dependent.markDirty();
    if (options.notify !== false) this.queueNotification();
    return this.revision();
  }

  protected revision(): Revision {
    return {
      nodeId: this.id,
      revision: this.snapshotValue.revision,
      generation: this.snapshotValue.generation,
      mutationIds: this.snapshotValue.mutationIds,
    };
  }

  protected equals(left: T, right: T): boolean {
    return (this.options.equals ?? Object.is)(left, right);
  }

  protected onObserved(): void {}
  protected onUnobserved(): void {}

  private queueNotification(): void {
    if (this.notificationQueued) return;
    this.notificationQueued = true;
    enqueueNotification({
      __stateInstrumentation: this.options.instrumentation,
      __flush: () => {
        this.notificationQueued = false;
        const snapshot = this.currentSnapshot();
        for (const observer of [...this.observers]) this.notifyObserver(observer, snapshot);
      },
    });
  }

  private notifyObserver(observer: Observer<T>, snapshot: Snapshot<T>): void {
    try {
      observer(snapshot);
    } catch (error) {
      this.options.instrumentation?.observerError?.(error, this.options.name);
    }
  }
}

export function peek<T>(node: Readable<T>): T {
  return node.__stateNode.peek() as T;
}

/**
 * Full snapshot read — value + status + revision + metadata. Tracked when
 * read inside a `derived` computation; `peek` is the untracked read.
 */
export function snapshot<T>(node: Readable<T>): Snapshot<T> {
  trackDependency(node.__stateNode);
  return node.__stateNode.currentSnapshot() as Snapshot<T>;
}

export function revisionOf(node: Readable<unknown>): Revision {
  const state = node.__stateNode;
  const current = state.currentSnapshot();
  return {
    nodeId: state.id,
    revision: current.revision,
    generation: current.generation,
    mutationIds: current.mutationIds,
  };
}

export function withCollector<T>(work: () => T): { value: T; collector: Collector } {
  const previous = currentCollector;
  const collector: Collector = {
    dependencies: new Map(),
    status: 'live',
    error: undefined,
  };
  currentCollector = collector;
  try {
    const value = work();
    return { value, collector };
  } catch (error) {
    throw new CollectedComputationError(error, collector);
  } finally {
    currentCollector = previous;
  }
}

export class CollectedComputationError {
  constructor(
    readonly error: unknown,
    readonly collector: Collector
  ) {}
}

function trackDependency(node: StateNode<unknown>): void {
  if (!currentCollector) return;
  const snap = node.currentSnapshot();
  currentCollector.dependencies.set(node, snap);
  currentCollector.status = weakerStatus(currentCollector.status, snap.status);
  if (snap.error !== undefined && currentCollector.error === undefined)
    currentCollector.error = snap.error;
}

export function weakerStatus(left: StateStatus, right: StateStatus): StateStatus {
  return statusRank(left) <= statusRank(right) ? left : right;
}

function statusRank(status: StateStatus): number {
  switch (status) {
    case 'error':
      return 0;
    case 'loading':
      return 1;
    case 'stale':
      return 2;
    case 'live':
      return 3;
  }
}

export function mergeMutationIds(
  ...sources: Array<readonly string[] | undefined>
): readonly string[] | undefined {
  const ids = new Set<string>();
  for (const source of sources) {
    for (const id of source ?? []) ids.add(id);
  }
  return ids.size > 0 ? [...ids] : undefined;
}

function sameIds(
  left: readonly string[] | undefined,
  right: readonly string[] | undefined
): boolean {
  if (!left?.length && !right?.length) return true;
  if ((left?.length ?? 0) !== (right?.length ?? 0)) return false;
  const expected = new Set(left);
  return (right ?? []).every((id) => expected.has(id));
}

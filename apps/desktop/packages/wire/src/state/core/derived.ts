import {
  CollectedComputationError,
  StateNode,
  type Collector,
  type Readable,
  type StateInstrumentation,
  withCollector,
} from './node';
import { enqueueDirty } from './scheduler';

export type DerivedOptions<T> = {
  equals?: (left: T, right: T) => boolean;
  name?: string;
  instrumentation?: StateInstrumentation;
};

class DerivedNode<T> extends StateNode<T | undefined> implements Readable<T | undefined> {
  private dependencies = new Set<StateNode<unknown>>();
  private dependencyRevisions = new Map<StateNode<unknown>, number>();
  private dirty = true;
  private computing = false;
  private retainingAfterObservation = false;

  constructor(
    private readonly compute: () => T,
    options: DerivedOptions<T> = {}
  ) {
    super(undefined, options as DerivedOptions<T | undefined>);
  }

  override currentSnapshot() {
    this.ensureComputed();
    return super.currentSnapshot();
  }

  markDirty(): void {
    if (this.dirty) return;
    this.dirty = true;
    for (const dependent of [...this.dependents]) dependent.markDirty();
    if (this.observed) enqueueDirty(this);
  }

  override removeDependent(dependent: { markDirty(): void }): void {
    super.removeDependent(dependent);
    this.detachIfUnused();
  }

  __flush(): void {
    if (!this.observed || !this.dirty) return;
    this.recompute();
  }

  protected override onObserved(): void {
    this.retainingAfterObservation = true;
    try {
      this.ensureComputed();
    } finally {
      this.retainingAfterObservation = false;
    }
    for (const dependency of this.dependencies) dependency.retain();
  }

  protected override onUnobserved(): void {
    for (const dependency of this.dependencies) dependency.release();
    this.detachIfUnused();
  }

  /**
   * With no observers and no dependents nothing can consume a dirty
   * notification, so leave the dependencies' dependent sets and become
   * collectable. The next read or observe recomputes and re-attaches lazily.
   */
  private detachIfUnused(): void {
    if (this.observed || this.dependents.size > 0 || this.dependencies.size === 0) return;
    for (const dependency of this.dependencies) dependency.removeDependent(this);
    this.dependencies = new Set();
    this.dirty = true;
  }

  private ensureComputed(): void {
    if (!this.dirty) return;
    this.recompute();
  }

  private recompute(): void {
    if (this.computing) throw new Error('Reactive derived cycle detected');
    this.computing = true;
    try {
      const { value, collector } = withCollector(this.compute);
      this.options.instrumentation?.nodeRecomputed?.(this.options.name);
      const mutationIds = this.changedMutationIds(collector);
      this.replaceDependencies(collector);
      this.dirty = false;
      this.commit(value, {
        status: collector.status,
        error: collector.error,
        mutationIds,
      });
    } catch (error) {
      const collector = error instanceof CollectedComputationError ? error.collector : undefined;
      const mutationIds = collector ? this.changedMutationIds(collector) : undefined;
      if (collector) this.replaceDependencies(collector);
      this.dirty = false;
      this.commit(this.peek(), {
        status: 'error',
        error: error instanceof CollectedComputationError ? error.error : error,
        mutationIds,
      });
    } finally {
      this.computing = false;
    }
  }

  private replaceDependencies(collector: Collector): void {
    for (const dependency of this.dependencies) {
      if (collector.dependencies.has(dependency)) continue;
      dependency.removeDependent(this);
      if (this.observed) dependency.release();
      this.dependencyRevisions.delete(dependency);
    }
    for (const dependency of collector.dependencies.keys()) {
      if (this.dependencies.has(dependency)) continue;
      dependency.addDependent(this);
      if (this.observed && !this.retainingAfterObservation) dependency.retain();
    }
    this.dependencies = new Set(collector.dependencies.keys());
    for (const [dependency, dependencySnapshot] of collector.dependencies) {
      this.dependencyRevisions.set(dependency, dependencySnapshot.revision);
    }
  }

  private changedMutationIds(collector: Collector): readonly string[] | undefined {
    const ids = new Set<string>();
    for (const [dependency, dependencySnapshot] of collector.dependencies) {
      const previousRevision = this.dependencyRevisions.get(dependency);
      if (previousRevision !== undefined && previousRevision >= dependencySnapshot.revision)
        continue;
      for (const id of dependencySnapshot.mutationIds ?? []) ids.add(id);
    }
    return ids.size > 0 ? [...ids] : undefined;
  }
}

export function derived<T>(
  compute: () => T,
  options: DerivedOptions<T> = {}
): Readable<T | undefined> {
  return new DerivedNode(compute, options);
}

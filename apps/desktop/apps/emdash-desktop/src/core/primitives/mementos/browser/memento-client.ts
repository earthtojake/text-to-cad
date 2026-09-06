import { createScope, type Scope } from '@emdash/shared/concurrency';
import type { ContractClient } from '@emdash/wire/rpc';
import {
  observe,
  optimistic,
  remote,
  snapshot,
  whenReady,
  type OptimisticView,
  type RemoteModel,
  type RemoteMember,
} from '@emdash/wire/state';
import {
  comparer,
  computed,
  makeObservable,
  observable,
  reaction,
  runInAction,
  type IReactionDisposer,
} from 'mobx';
import type { z } from 'zod';
import {
  DEFAULT_TRANSIENT_MAX_ENTRIES,
  mementoKeyId,
  mementosWireContract,
  persistedMementosForSubjectKind,
  type MementoCatalogEntry,
  type MementoDef,
  type MementoModelKey,
  type MementoRow,
} from '@core/primitives/mementos/api';
import type { Subject, SubjectDef } from '@core/primitives/subjects/api';

// The mementos node integration test pulls this file into the node program
// (no DOM lib), so `window` is declared structurally here; the runtime guards
// below already made the beforeunload registration environment-neutral.
declare const window:
  | {
      addEventListener?: (type: 'beforeunload', listener: () => void) => void;
      removeEventListener?: (type: 'beforeunload', listener: () => void) => void;
    }
  | undefined;

type MementosClientContract = ContractClient<typeof mementosWireContract>;
type PersistentRemote = RemoteModel<typeof mementosWireContract.memento>;
type PersistentMember = RemoteMember<typeof mementosWireContract.memento>;
type BoundMementoDef<TValue, TKind extends string> = MementoDef<
  TValue,
  SubjectDef<TKind, z.ZodType>
>;
type MementoUpdater<TValue> = TValue | ((current: TValue) => TValue);

interface ModelLease {
  readonly model: PersistentMementoModel;
  readonly ready: Promise<void>;
  release(): Promise<void>;
}

export interface MementoHandle<TValue> {
  readonly value: TValue;
  readonly ready: Promise<void>;
  readonly isPending: boolean;
  readonly hasStoredValue: boolean;
  read(): TValue;
  update(next: MementoUpdater<TValue>): void;
  reset(): Promise<void>;
  flush(): Promise<void>;
  autoPersist(read: () => TValue, scope?: Scope): IReactionDisposer;
  dispose(): Promise<void>;
}

export interface MementoClientOptions {
  readonly debounceMs?: number;
  readonly now?: () => number;
  readonly onError?: (error: unknown) => void;
  readonly registerBeforeUnload?: boolean;
  readonly catalog?: readonly MementoCatalogEntry[];
}

export class MementoClient {
  private readonly scope = createScope({ label: 'memento-client' });
  private readonly remoteModel: PersistentRemote;
  private readonly spaces = new Set<SubjectSpace<string>>();
  private readonly persistentHandles = new Set<PersistentMementoHandle<unknown>>();
  private readonly transient = new TransientMementoStore();
  private readonly catalog: readonly MementoCatalogEntry[];
  private readonly debounceMs: number;
  private readonly now: () => number;
  private readonly onError: (error: unknown) => void;
  private readonly beforeUnload = () => {
    void this.flush().catch(this.onError);
  };
  private disposed = false;

  constructor(
    readonly wire: MementosClientContract,
    options: MementoClientOptions = {}
  ) {
    this.remoteModel = remote(mementosWireContract.memento, wire.memento, {
      scope: this.scope,
      lingerMs: 30_000,
    });
    this.debounceMs = options.debounceMs ?? 1_000;
    this.now = options.now ?? Date.now;
    this.onError = options.onError ?? (() => {});
    this.catalog = options.catalog ?? [];
    if (
      options.registerBeforeUnload !== false &&
      typeof window !== 'undefined' &&
      typeof window.addEventListener === 'function'
    ) {
      window.addEventListener('beforeunload', this.beforeUnload);
    }
  }

  subject<TKind extends string>(subject: Subject<TKind>): SubjectSpace<TKind> {
    this.assertActive();
    const space = new SubjectSpace(this, subject);
    this.spaces.add(space as SubjectSpace<string>);
    return space;
  }

  async deleteBySubject(subject: Subject): Promise<number> {
    this.assertActive();
    await this.discardPendingWhere(
      (handle) => handle.subject.kind === subject.kind && handle.subject.key === subject.key
    );
    const result = await this.wire.deleteBySubject(subject);
    if (!result.success) throw new Error(result.error.message);
    this.transient.deleteBySubject(subject);
    return result.data.deleted;
  }

  async deleteAll(): Promise<number> {
    this.assertActive();
    await this.discardPendingWhere(() => true);
    const result = await this.wire.deleteAll(undefined);
    if (!result.success) throw new Error(result.error.message);
    this.transient.clear();
    return result.data.deleted;
  }

  async deleteOrphans(kind: string, validKeys: readonly string[]): Promise<number> {
    this.assertActive();
    const valid = new Set(validKeys);
    await this.discardPendingWhere(
      (handle) => handle.subject.kind === kind && !valid.has(handle.subject.key)
    );
    const result = await this.wire.deleteOrphans({ kind, validKeys: [...validKeys] });
    if (!result.success) throw new Error(result.error.message);
    this.transient.deleteOrphans(kind, valid);
    return result.data.deleted;
  }

  async flush(): Promise<void> {
    const results = await Promise.allSettled(
      [...this.persistentHandles].map(async (handle) => await handle.flush())
    );
    const errors = results.flatMap((result) =>
      result.status === 'rejected' ? [result.reason] : []
    );
    if (errors.length > 0) throw new AggregateError(errors, 'Failed to flush mementos');
  }

  reportError(error: unknown): void {
    this.onError(error);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    if (typeof window !== 'undefined' && typeof window.removeEventListener === 'function') {
      window.removeEventListener('beforeunload', this.beforeUnload);
    }
    let flushError: unknown;
    try {
      await this.flush();
    } catch (error) {
      flushError = error;
    }
    await Promise.allSettled([...this.spaces].map(async (space) => await space.release()));
    this.spaces.clear();
    await this.scope.dispose();
    if (flushError) throw flushError;
  }

  acquirePersistentModel(key: MementoModelKey): ModelLease {
    const model = new PersistentMementoModel(this.scope, this.remoteModel, key);
    let released = false;
    return {
      model,
      ready: model.ready,
      release: async () => {
        if (released) return;
        released = true;
        await model.dispose();
      },
    };
  }

  createPersistentHandle<TValue>(
    subject: Subject,
    definition: MementoDef<TValue, SubjectDef<string, z.ZodType>>
  ): MementoHandle<TValue> {
    const handle = new PersistentMementoHandle(this, subject, definition, {
      debounceMs: this.debounceMs,
      now: this.now,
      onError: this.onError,
    });
    this.persistentHandles.add(handle as PersistentMementoHandle<unknown>);
    return handle;
  }

  createTransientHandle<TValue>(
    subject: Subject,
    definition: MementoDef<TValue, SubjectDef<string, z.ZodType>>
  ): MementoHandle<TValue> {
    return this.transient.acquire(subject, definition);
  }

  unregisterSpace(space: SubjectSpace<string>): void {
    this.spaces.delete(space);
  }

  unregisterPersistentHandle(handle: PersistentMementoHandle<unknown>): void {
    this.persistentHandles.delete(handle);
  }

  persistedDefinitionsForSubjectKind(kind: string): readonly MementoCatalogEntry[] {
    return persistedMementosForSubjectKind(this.catalog, kind);
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('MementoClient is disposed');
  }

  private async discardPendingWhere(
    predicate: (handle: PersistentMementoHandle<unknown>) => boolean
  ): Promise<void> {
    const results = await Promise.allSettled(
      [...this.persistentHandles]
        .filter(predicate)
        .map(async (handle) => await handle.discardPending())
    );
    for (const result of results) {
      if (result.status === 'rejected') this.reportError(result.reason);
    }
  }
}

export class SubjectSpace<TKind extends string> {
  /** Observable mirror of `ready`; true once the initial hydration resolved. */
  isHydrated = false;

  private readonly handles = new Map<string, MementoHandle<unknown>>();
  private readonly prefetch: ModelLease[];
  private released = false;

  constructor(
    private readonly client: MementoClient,
    readonly subject: Subject<TKind>
  ) {
    this.prefetch = client
      .persistedDefinitionsForSubjectKind(subject.kind)
      .map((definition) => client.acquirePersistentModel(toModelKey(subject, definition.id)));
    makeObservable(this, { isHydrated: observable });
    void this.ready.then(
      () => {
        runInAction(() => {
          this.isHydrated = true;
        });
      },
      (error: unknown) => client.reportError(error)
    );
  }

  get ready(): Promise<void> {
    return Promise.all([
      ...this.prefetch.map(({ ready }) => ready),
      ...[...this.handles.values()].map(({ ready }) => ready),
    ]).then(() => undefined);
  }

  handle<TValue>(definition: BoundMementoDef<TValue, TKind>): MementoHandle<TValue> {
    if (this.released) throw new Error('SubjectSpace is released');
    if (definition.subject.kind !== this.subject.kind) {
      throw new Error(
        `Memento '${definition.id}' requires subject '${definition.subject.kind}', received '${this.subject.kind}'`
      );
    }

    const existing = this.handles.get(definition.id);
    if (existing) return existing as MementoHandle<TValue>;

    const unboundDefinition = definition as MementoDef<TValue, SubjectDef<string, z.ZodType>>;
    const handle =
      definition.retention.tier === 'persisted'
        ? this.client.createPersistentHandle(this.subject, unboundDefinition)
        : this.client.createTransientHandle(this.subject, unboundDefinition);
    this.handles.set(definition.id, handle as MementoHandle<unknown>);
    return handle;
  }

  async release(): Promise<void> {
    if (this.released) return;
    this.released = true;
    this.client.unregisterSpace(this as SubjectSpace<string>);
    const handles = [...this.handles.values()];
    this.handles.clear();
    await Promise.all([
      ...handles.map(async (handle) => await handle.dispose()),
      ...this.prefetch.map(async (lease) => await lease.release()),
    ]);
  }
}

interface DirtyValue<TValue> {
  readonly revision: number;
  readonly value: TValue;
  readonly row: MementoRow;
}

class PersistentMementoModel {
  readonly member: PersistentMember;
  readonly view: OptimisticView<MementoRow | null>;
  readonly ready: Promise<void>;
  value: MementoRow | null | undefined;
  private readonly scope: Scope;
  private loading = true;

  constructor(parentScope: Scope, remoteModel: PersistentRemote, key: MementoModelKey) {
    this.scope = parentScope.child(`memento:${mementoKeyId(key)}`);
    this.member = remoteModel(key);
    this.view = optimistic(this.member.states.value);
    makeObservable<this, 'loading'>(this, {
      value: observable.ref,
      loading: observable,
      isPending: computed,
    });
    observe(
      this.view,
      (snapshot) => {
        runInAction(() => {
          this.value = snapshot.value;
          this.loading = snapshot.status === 'loading';
        });
      },
      { scope: this.scope }
    );
    this.ready = whenReady(this.view, { scope: this.scope }).then(() => undefined);
  }

  get isPending(): boolean {
    return this.loading;
  }

  /**
   * Pulls the view's current snapshot into the MobX mirror synchronously. The
   * state kernel delivers observer notifications a microtask later, so callers
   * that just changed the view (e.g. applied an optimistic patch) use this to
   * keep dependent observables from reading a stale value in between.
   */
  syncFromView(): void {
    const current = snapshot(this.view);
    runInAction(() => {
      this.value = current.value;
      this.loading = current.status === 'loading';
    });
  }

  async dispose(): Promise<void> {
    await this.scope.dispose();
  }
}

class PersistentMementoHandle<TValue> implements MementoHandle<TValue> {
  readonly ready: Promise<void>;
  private readonly lease: ModelLease;
  private readonly parser: ParsedMementoValue<TValue>;
  private readonly debounceMs: number;
  private readonly now: () => number;
  private readonly onError: (error: unknown) => void;
  private dirty: DirtyValue<TValue> | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private activeWrite: Promise<void> | undefined;
  private revision = 0;
  private disposed = false;

  constructor(
    private readonly client: MementoClient,
    readonly subject: Subject,
    private readonly definition: MementoDef<TValue, SubjectDef<string, z.ZodType>>,
    options: { debounceMs: number; now: () => number; onError: (error: unknown) => void }
  ) {
    this.lease = client.acquirePersistentModel(toModelKey(subject, definition.id));
    this.ready = this.lease.ready;
    this.parser = new ParsedMementoValue(definition);
    this.debounceMs = options.debounceMs;
    this.now = options.now;
    this.onError = options.onError;
    makeObservable<this, 'dirty'>(this, {
      dirty: observable.ref,
      value: computed,
      isPending: computed,
      hasStoredValue: computed,
    });
  }

  get value(): TValue {
    return this.dirty?.value ?? this.parser.parse(this.lease.model.value);
  }

  get isPending(): boolean {
    return this.dirty !== undefined || this.lease.model.isPending;
  }

  get hasStoredValue(): boolean {
    return this.dirty !== undefined || this.lease.model.value != null;
  }

  read(): TValue {
    return this.value;
  }

  update(next: MementoUpdater<TValue>): void {
    this.assertActive();
    const value =
      typeof next === 'function' ? (next as (current: TValue) => TValue)(this.value) : next;
    const data = this.definition.schema.serialize(value);
    this.parser.remember(data, value);
    runInAction(() => {
      this.dirty = {
        revision: ++this.revision,
        value,
        row: {
          version: this.definition.schema.currentVersion,
          data,
          updatedAt: this.now(),
        },
      };
    });
    this.scheduleFlush();
  }

  async reset(): Promise<void> {
    this.assertActive();
    this.cancelTimer();
    runInAction(() => {
      this.dirty = undefined;
      this.revision += 1;
    });
    await this.activeWrite;
    const invocation = await this.lease.model.member.mutations.reset(undefined);
    if (!invocation.result.success) throw new Error(invocation.result.error.message);
    await invocation.settled;
  }

  async flush(): Promise<void> {
    this.cancelTimer();
    if (this.activeWrite) await this.activeWrite;
    if (!this.dirty) return;
    this.activeWrite = this.flushDirty(this.dirty).finally(() => {
      this.activeWrite = undefined;
    });
    await this.activeWrite;
    if (this.dirty) await this.flush();
  }

  autoPersist(read: () => TValue, scope?: Scope): IReactionDisposer {
    const dispose = reaction(read, (value) => this.update(value), {
      equals: comparer.structural,
    });
    scope?.add(dispose);
    return dispose;
  }

  async discardPending(): Promise<void> {
    this.cancelTimer();
    runInAction(() => {
      this.dirty = undefined;
      this.revision += 1;
    });
    await this.activeWrite;
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    try {
      await this.flush();
    } finally {
      this.disposed = true;
      this.cancelTimer();
      this.client.unregisterPersistentHandle(this as PersistentMementoHandle<unknown>);
      await this.lease.release();
    }
  }

  private async flushDirty(dirty: DirtyValue<TValue>): Promise<void> {
    try {
      // view.run applies the row as a synchronous optimistic patch; syncing
      // the mirror before dropping the local draft keeps the observable value
      // from flapping back to the stale row while the write is in flight.
      const pendingResult = this.lease.model.view.run(
        this.lease.model.member.mutations.save,
        dirty.row,
        (_current, row) => row
      );
      this.lease.model.syncFromView();
      runInAction(() => {
        const patchVisible = this.lease.model.value?.data === dirty.row.data;
        if (this.dirty?.revision === dirty.revision && patchVisible) this.dirty = undefined;
      });
      const result = await pendingResult;
      if (!result.success) throw new Error(result.error.message);
      runInAction(() => {
        if (this.dirty?.revision === dirty.revision) this.dirty = undefined;
      });
    } catch (error) {
      runInAction(() => {
        if (!this.dirty && this.revision === dirty.revision) this.dirty = dirty;
      });
      throw error;
    }
  }

  private scheduleFlush(): void {
    this.cancelTimer();
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.flush().catch(this.onError);
    }, this.debounceMs);
  }

  private cancelTimer(): void {
    if (this.timer === undefined) return;
    clearTimeout(this.timer);
    this.timer = undefined;
  }

  private assertActive(): void {
    if (this.disposed) throw new Error(`Memento handle '${this.definition.id}' is disposed`);
  }
}

class ParsedMementoValue<TValue> {
  private data: string | undefined;
  private value: TValue;

  constructor(private readonly definition: MementoDef<TValue, SubjectDef<string, z.ZodType>>) {
    this.value = definition.default;
  }

  parse(row: MementoRow | null | undefined): TValue {
    if (!row) return this.definition.default;
    if (row.data === this.data) return this.value;
    const parsed = this.definition.schema.parseJson(row.data);
    this.data = row.data;
    this.value = parsed ?? this.definition.default;
    return this.value;
  }

  remember(data: string, value: TValue): void {
    this.data = data;
    this.value = value;
  }
}

interface TransientEntry {
  readonly mementoId: string;
  readonly subject: Subject;
  readonly cell: TransientCell;
  readonly defaultValue: unknown;
  maxEntries: number;
  pins: number;
  accessedAt: number;
}

class TransientCell {
  value: unknown;
  hasStoredValue = false;

  constructor(initial: unknown) {
    this.value = initial;
    makeObservable(this, { value: observable.ref, hasStoredValue: observable });
  }
}

class TransientMementoStore {
  private readonly entries = new Map<string, TransientEntry>();
  private clock = 0;

  acquire<TValue>(
    subject: Subject,
    definition: MementoDef<TValue, SubjectDef<string, z.ZodType>>
  ): MementoHandle<TValue> {
    const key = mementoKeyId(toModelKey(subject, definition.id));
    let entry = this.entries.get(key);
    if (!entry) {
      entry = {
        mementoId: definition.id,
        subject,
        cell: new TransientCell(definition.default),
        defaultValue: definition.default,
        maxEntries:
          definition.retention.tier === 'transient'
            ? definition.retention.maxEntries
            : DEFAULT_TRANSIENT_MAX_ENTRIES,
        pins: 0,
        accessedAt: ++this.clock,
      };
      this.entries.set(key, entry);
    }
    entry.pins += 1;
    entry.accessedAt = ++this.clock;
    return new TransientMementoHandle(this, entry, definition);
  }

  release(entry: TransientEntry): void {
    entry.pins = Math.max(0, entry.pins - 1);
    entry.accessedAt = ++this.clock;
    this.prune(entry.mementoId, entry.maxEntries);
  }

  touch(entry: TransientEntry): void {
    entry.accessedAt = ++this.clock;
  }

  deleteBySubject(subject: Subject): void {
    this.deleteWhere(
      (entry) => entry.subject.kind === subject.kind && entry.subject.key === subject.key
    );
  }

  deleteOrphans(kind: string, validKeys: ReadonlySet<string>): void {
    this.deleteWhere((entry) => entry.subject.kind === kind && !validKeys.has(entry.subject.key));
  }

  clear(): void {
    this.deleteWhere(() => true);
  }

  private deleteWhere(predicate: (entry: TransientEntry) => boolean): void {
    for (const [key, entry] of this.entries) {
      if (predicate(entry)) {
        runInAction(() => {
          entry.cell.value = entry.defaultValue;
          entry.cell.hasStoredValue = false;
        });
        if (entry.pins === 0) this.entries.delete(key);
      }
    }
  }

  private prune(mementoId: string, maxEntries: number): void {
    const candidates = [...this.entries.entries()]
      .filter(([, entry]) => entry.mementoId === mementoId)
      .sort((left, right) => left[1].accessedAt - right[1].accessedAt);
    let overflow = candidates.length - maxEntries;
    for (const [key, entry] of candidates) {
      if (overflow <= 0) break;
      if (entry.pins > 0) continue;
      this.entries.delete(key);
      overflow -= 1;
    }
  }
}

class TransientMementoHandle<TValue> implements MementoHandle<TValue> {
  readonly ready = Promise.resolve();
  readonly isPending = false;
  private disposed = false;

  constructor(
    private readonly store: TransientMementoStore,
    private readonly entry: TransientEntry,
    private readonly definition: MementoDef<TValue, SubjectDef<string, z.ZodType>>
  ) {}

  get value(): TValue {
    return this.entry.cell.value as TValue;
  }

  get hasStoredValue(): boolean {
    return this.entry.cell.hasStoredValue;
  }

  read(): TValue {
    return this.value;
  }

  update(next: MementoUpdater<TValue>): void {
    this.assertActive();
    const value =
      typeof next === 'function' ? (next as (current: TValue) => TValue)(this.value) : next;
    runInAction(() => {
      this.entry.cell.value = value;
      this.entry.cell.hasStoredValue = true;
    });
    this.store.touch(this.entry);
  }

  async reset(): Promise<void> {
    this.assertActive();
    runInAction(() => {
      this.entry.cell.value = this.definition.default;
      this.entry.cell.hasStoredValue = false;
    });
    this.store.touch(this.entry);
  }

  async flush(): Promise<void> {}

  autoPersist(read: () => TValue, scope?: Scope): IReactionDisposer {
    const dispose = reaction(read, (value) => this.update(value), {
      equals: comparer.structural,
    });
    scope?.add(dispose);
    return dispose;
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.store.release(this.entry);
  }

  private assertActive(): void {
    if (this.disposed) throw new Error(`Memento handle '${this.definition.id}' is disposed`);
  }
}

function toModelKey(subject: Subject, mementoId: string): MementoModelKey {
  return {
    mementoId,
    kind: subject.kind,
    key: subject.key,
  };
}

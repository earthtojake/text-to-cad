import { ok, toPendingLease, type Lease, type PendingLease, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { stableStringify } from '@emdash/shared/util';
import type {
  LiveCursor,
  LiveCursorEntry,
  LiveMutationResult,
  LiveSource,
} from '../../api/channel';
import type {
  LiveModelDef,
  LiveModelKey,
  LiveModelMutations,
  LiveModelStates,
  LiveStateData,
  MutationData,
  MutationError,
  MutationInput,
} from '../../api/define';
import type { WireInstrumentation } from '../../api/instrumentation';
import type { LeasedLiveModelProvider } from '../../live/replica/leased-provider';
import { LiveStateSource } from '../../live/state/source';
import {
  StateNode,
  observe,
  snapshot,
  type Readable,
  type Revision,
  type StateInstrumentation,
  type Snapshot,
} from '../core';
import { keyedRetention } from '../core/keyed-retention';
import { assignDraft } from './assign-draft';
import { MutationResultCache, type MutationResultCacheOptions } from './result-cache';

type StateName<Group extends LiveModelDef> = Extract<keyof LiveModelStates<Group>, string>;
type MutationName<Group extends LiveModelDef> = Extract<keyof LiveModelMutations<Group>, string>;

export type ExposedStateResolver<Group extends LiveModelDef, Name extends StateName<Group>> = (
  key: LiveModelKey<Group>,
  scope: Scope
) =>
  | Readable<LiveStateData<LiveModelStates<Group>[Name]> | undefined>
  | Promise<Readable<LiveStateData<LiveModelStates<Group>[Name]> | undefined>>;

export type ExposedStates<Group extends LiveModelDef> = {
  [Name in StateName<Group>]:
    | Readable<LiveStateData<LiveModelStates<Group>[Name]> | undefined>
    | Promise<Readable<LiveStateData<LiveModelStates<Group>[Name]> | undefined>>
    | ExposedStateResolver<Group, Name>;
};

export type ExposedPublishMode = 'replace' | 'diff';

export type ExposedPublishOptions<Group extends LiveModelDef> =
  | ExposedPublishMode
  | Partial<Record<StateName<Group>, ExposedPublishMode>>;

export type ExposedMutationContext<
  Group extends LiveModelDef,
  Name extends MutationName<Group>,
> = Readonly<{
  key: LiveModelKey<Group>;
  input: MutationInput<LiveModelMutations<Group>[Name]>;
  mutationId: string;
  observed<State extends StateName<Group>>(
    name: State,
    revision: Revision | Promise<Revision>
  ): Promise<void>;
}>;

export type ExposedMutationHandlers<Group extends LiveModelDef> = {
  [Name in MutationName<Group>]: (
    context: ExposedMutationContext<Group, Name>
  ) =>
    | Promise<
        Result<
          MutationData<LiveModelMutations<Group>[Name]>,
          MutationError<LiveModelMutations<Group>[Name]>
        >
      >
    | Result<
        MutationData<LiveModelMutations<Group>[Name]>,
        MutationError<LiveModelMutations<Group>[Name]>
      >;
};

export type ExposeOptions<Group extends LiveModelDef> = {
  scope?: Scope;
  mutations?: Partial<ExposedMutationHandlers<Group>>;
  idempotency?: MutationResultCacheOptions | false;
  lingerMs?: number;
  clock?: Clock;
  instrumentation?: WireInstrumentation;
  publish?: ExposedPublishOptions<Group>;
};

type StateRecord = {
  key: unknown;
  name: string;
  node: Readable<unknown>;
  liveState: LiveStateSource<unknown> | undefined;
  readyWaiters: ReadyWaiter[];
  waiters: RevisionWaiter[];
};

type ReadyWaiter = {
  resolve(liveState: LiveStateSource<unknown>): void;
  reject(error: unknown): void;
};

type RevisionWaiter = {
  revision: Revision;
  mutationId: string;
  resolve(cursor: LiveCursor): void;
  reject(error: unknown): void;
};

export function expose<Group extends LiveModelDef>(
  contract: Group,
  states: ExposedStates<NoInfer<Group>>,
  options: ExposeOptions<NoInfer<Group>> = {}
): LeasedLiveModelProvider<Group> {
  const scope = options.scope ?? createScope({ label: `state-expose:${contract.id}` });
  const clock = options.clock ?? systemClock;
  const lingerMs = options.lingerMs ?? 15_000;
  const mutationCache =
    options.idempotency === false ? undefined : new MutationResultCache(options.idempotency);
  let disposed = false;

  type RecordKey = { key: LiveModelKey<Group>; name: StateName<Group> };
  const records = keyedRetention<RecordKey, StateRecord>({
    key: ({ key, name }) => `${contract.states[name].id}:${stableStringify(key)}`,
    lingerMs,
    name: `state-expose:${contract.id}`,
    scope,
    clock,
    create: ({ key, name }, stateScope) => {
      const resolver = states[name];
      const resolved = (typeof resolver === 'function'
        ? resolver(key, stateScope)
        : resolver) as unknown as Readable<unknown> | Promise<Readable<unknown>>;
      const node = isPromiseLike(resolved)
        ? asyncReadable(resolved, stateScope, undefined)
        : resolved;
      const record: StateRecord = {
        key,
        name,
        node,
        liveState: undefined,
        readyWaiters: [],
        waiters: [],
      };
      stateScope.add(() => rejectRecord(record, new Error('Exposed state disposed')));
      observe(
        node,
        (current) => {
          publishSnapshot(record, current);
        },
        { scope: stateScope, immediate: false }
      );
      publishSnapshot(record, snapshot(node));
      return record;
    },
  });

  return {
    kind: 'leasedLiveModelProvider',
    contract,
    acquireState(key, name) {
      assertActive();
      return acquireStateRecord(key, name);
    },
    runMutation(name, envelope) {
      assertActive();
      const execute = () => runMutation(name, envelope);
      if (!mutationCache) return execute();
      return mutationCache.run(envelope.mutationId, execute, {
        onDedupe: () =>
          options.instrumentation?.mutationDeduped?.({
            mutationId: envelope.mutationId,
            path: `${contract.id}.${String(name)}`,
          }),
      });
    },
    async dispose() {
      if (disposed) return;
      disposed = true;
      mutationCache?.clear();
      await records.dispose();
      await scope.dispose();
    },
  };

  function acquireStateRecord<Name extends StateName<Group>>(
    key: LiveModelKey<Group>,
    name: Name
  ): PendingLease<LiveSource> {
    const recordKey: RecordKey = { key, name };
    const releaseEntry = records.retain(recordKey);
    const record = records.ensure(recordKey).value;
    const release = () => {
      releaseEntry();
      // An errored record that never produced a source is not worth lingering.
      if (
        !record.liveState &&
        snapshot(record.node).status === 'error' &&
        records.peek(recordKey)?.value === record
      ) {
        void records.evict(recordKey);
      }
    };
    return toPendingLease(
      readyRecord(record).then(
        (liveState) =>
          ({
            value: liveState,
            release: async () => release(),
          }) satisfies Lease<LiveSource>,
        (error) => {
          release();
          throw error;
        }
      )
    );
  }

  async function runMutation<Name extends MutationName<Group>>(
    name: Name,
    envelope: {
      key: LiveModelKey<Group>;
      input: MutationInput<LiveModelMutations<Group>[Name]>;
      mutationId: string;
    }
  ): Promise<
    LiveMutationResult<
      MutationData<LiveModelMutations<Group>[Name]>,
      MutationError<LiveModelMutations<Group>[Name]>
    >
  > {
    const handler = options.mutations?.[name];
    if (!handler) throw new Error(`Mutation '${contract.id}.${String(name)}' requires a handler`);
    const cursors = new Map<string, LiveCursorEntry>();
    const context: ExposedMutationContext<Group, Name> = {
      key: envelope.key,
      input: envelope.input,
      mutationId: envelope.mutationId,
      observed(stateName, revision) {
        return Promise.resolve(revision).then((resolved) =>
          waitForRevision(envelope.key, stateName, resolved, envelope.mutationId).then((cursor) => {
            const state = contract.states[stateName];
            cursors.set(state.id, {
              model: state.id,
              key: envelope.key,
              cursor,
            });
          })
        );
      },
    };
    const result = await handler(context as never);
    if (!result.success) return result;
    return ok({
      data: result.data as MutationData<LiveModelMutations<Group>[Name]>,
      cursors: [...cursors.values()],
    });
  }

  function waitForRevision<Name extends StateName<Group>>(
    key: LiveModelKey<Group>,
    name: Name,
    revision: Revision,
    mutationId: string
  ): Promise<LiveCursor> {
    const record = records.ensure({ key, name }).value;
    const current = snapshot(record.node);
    if (record.liveState && matchesWaiter(record, current, revision, mutationId))
      return Promise.resolve(record.liveState.cursor);
    return new Promise((resolve, reject) => {
      record.waiters.push({ revision, mutationId, resolve, reject });
    });
  }

  function readyRecord(record: StateRecord): Promise<LiveStateSource<unknown>> {
    const current = snapshot(record.node);
    if (record.liveState && current.status === 'live') return Promise.resolve(record.liveState);
    if (current.status === 'error') return Promise.reject(current.error);
    return new Promise((resolve, reject) => {
      record.readyWaiters.push({ resolve, reject });
    });
  }

  function publishSnapshot(record: StateRecord, current: Snapshot<unknown>): void {
    if (current.status === 'loading' || current.status === 'stale') return;
    if (current.status === 'error') {
      rejectRecord(record, current.error ?? new Error('Exposed state failed'));
      return;
    }

    const liveState = record.liveState;
    const cursor = liveState
      ? publishLiveState(record, liveState, current)
      : (record.liveState = new LiveStateSource(current.value)).cursor;
    if (!record.liveState) throw new Error('Exposed state failed to initialize');
    const readyLiveState = record.liveState;

    const readyWaiters = record.readyWaiters;
    record.readyWaiters = [];
    for (const waiter of readyWaiters) waiter.resolve(readyLiveState);

    const ready = record.waiters.filter((waiter) =>
      matchesWaiter(record, current, waiter.revision, waiter.mutationId)
    );
    record.waiters = record.waiters.filter(
      (waiter) => !matchesWaiter(record, current, waiter.revision, waiter.mutationId)
    );
    for (const waiter of ready) waiter.resolve(cursor);
  }

  function publishLiveState(
    record: StateRecord,
    liveState: LiveStateSource<unknown>,
    current: Snapshot<unknown>
  ): LiveCursor {
    const mutationIds = current.mutationIds ? [...current.mutationIds] : undefined;
    if (publishMode(record) === 'diff') {
      return liveState.produce(
        (draft) => {
          return assignDraft(draft, current.value) as never;
        },
        { mutationIds }
      );
    }
    return liveState.replace(current.value, { mutationIds });
  }

  function publishMode(record: StateRecord): ExposedPublishMode {
    const publish = options.publish;
    if (!publish) return 'replace';
    if (typeof publish === 'string') return publish;
    return publish[record.name as StateName<Group>] ?? 'replace';
  }

  function rejectRecord(record: StateRecord, error: unknown): void {
    const readyWaiters = record.readyWaiters;
    const waiters = record.waiters;
    record.readyWaiters = [];
    record.waiters = [];
    for (const waiter of readyWaiters) waiter.reject(error);
    for (const waiter of waiters) waiter.reject(error);
  }

  function matchesWaiter(
    record: StateRecord,
    current: Snapshot<unknown>,
    revision: Revision,
    mutationId: string
  ): boolean {
    if (current.mutationIds?.includes(mutationId)) return true;
    return record.node.__stateNode.id === revision.nodeId && current.revision >= revision.revision;
  }

  function assertActive(): void {
    if (disposed) throw new Error(`Exposed state provider '${contract.id}' is disposed`);
  }
}

class AsyncReadableNode<T> extends StateNode<T | undefined> implements Readable<T | undefined> {
  private disposed = false;

  constructor(
    source: Promise<Readable<T | undefined>>,
    scope: Scope,
    instrumentation: StateInstrumentation | undefined
  ) {
    super(undefined, { instrumentation });
    this.commit(undefined, { status: 'loading' });
    scope.add(() => {
      this.disposed = true;
    });
    void source.then(
      (node) => {
        if (this.disposed) return;
        const unsubscribe = node.__stateNode.observe((current) => {
          this.replaceSnapshot(current as Snapshot<T | undefined>);
        });
        scope.add(unsubscribe);
      },
      (error) => {
        if (this.disposed) return;
        this.commit(undefined, { status: 'error', error });
      }
    );
  }
}

function asyncReadable<T>(
  source: Promise<Readable<T | undefined>>,
  scope: Scope,
  instrumentation: StateInstrumentation | undefined
): Readable<T | undefined> {
  return new AsyncReadableNode(source, scope, instrumentation);
}

function isPromiseLike<T>(value: T | Promise<T>): value is Promise<T> {
  return typeof (value as Promise<T>).then === 'function';
}

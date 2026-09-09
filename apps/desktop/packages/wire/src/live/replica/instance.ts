import type { Result } from '@emdash/shared';
import {
  createMutationId,
  type LiveCursorEntry,
  type LiveMutationSuccess,
} from '../../api/channel';
import type { MutationCallOptions } from '../../api/client';
import type {
  LiveStateData,
  LiveModelKey,
  LiveModelStates,
  LiveModelMutations,
  LiveModelDef,
  LiveStateDef,
  MutationData,
  MutationError,
  MutationInput,
} from '../../api/define';
import type { WireInstrumentation } from '../../api/instrumentation';
import type { LiveChangeMeta } from '../state';
import type { ReplicaState, ReplicaStateOptions } from './state';
import type { StateStore } from './store';

/**
 * Replica-side mutation success. `settled: false` is client-side metadata added
 * when the mutation committed upstream but cursor translation timed out before
 * the local replica caught up; the field is absent otherwise, so the wire shape
 * of `LiveMutationResult` is unchanged.
 */
export type ReplicaMutationSuccess<D> = LiveMutationSuccess<D> & {
  settled?: boolean;
};

export type ReplicaMutationResult<D, E> = Result<ReplicaMutationSuccess<D>, E>;

export type ContractMutationInvocation<D, E> = {
  result: ReplicaMutationResult<D, E>;
  settled: Promise<void>;
};

export type ReplicaStates<Group extends LiveModelDef> = {
  [Name in keyof LiveModelStates<Group>]: ReplicaState<LiveStateData<LiveModelStates<Group>[Name]>>;
};

export type ReplicaMutations<Group extends LiveModelDef> = {
  [Name in keyof LiveModelMutations<Group>]: (
    input: MutationInput<LiveModelMutations<Group>[Name]>,
    options?: MutationCallOptions
  ) => Promise<
    ContractMutationInvocation<
      MutationData<LiveModelMutations<Group>[Name]>,
      MutationError<LiveModelMutations<Group>[Name]>
    >
  >;
};

export type ReplicaInstance<Group extends LiveModelDef = LiveModelDef> = {
  readonly key: LiveModelKey<Group>;
  readonly states: ReplicaStates<Group>;
  readonly mutations: ReplicaMutations<Group>;
  readonly ready: Promise<void>;
};

export type ReplicaStateStores<Group extends LiveModelDef> = {
  [Name in keyof LiveModelStates<Group>]?: () => StateStore<
    LiveStateData<LiveModelStates<Group>[Name]>
  >;
};

export type ReplicaStateChangeHandlers<Group extends LiveModelDef> = {
  [Name in keyof LiveModelStates<Group>]?: (
    value: LiveStateData<LiveModelStates<Group>[Name]>,
    meta: LiveChangeMeta
  ) => void;
};

export type ReplicaInstanceOptions<Group extends LiveModelDef = LiveModelDef> = Omit<
  ReplicaStateOptions<unknown>,
  'store' | 'onChange'
> & {
  stores?: ReplicaStateStores<Group>;
  onChange?: ReplicaStateChangeHandlers<Group>;
};

export function buildReplicaInstance<Group extends LiveModelDef>(
  contract: Group,
  key: LiveModelKey<Group>,
  opts: {
    createState(name: string, stateDef: LiveStateDef): ReplicaState<unknown>;
    mutate<Name extends Extract<keyof LiveModelMutations<Group>, string>>(
      name: Name,
      envelope: {
        key: LiveModelKey<Group>;
        input: unknown;
        mutationId: string;
      },
      options?: MutationCallOptions
    ): Promise<
      ReplicaMutationResult<
        MutationData<LiveModelMutations<Group>[Name]>,
        MutationError<LiveModelMutations<Group>[Name]>
      >
    >;
  }
): ReplicaInstance<Group> {
  const states: Record<string, ReplicaState<unknown>> = {};

  for (const [name, state] of Object.entries(contract.states)) {
    states[name] = opts.createState(name, state);
  }

  const mutations: Record<string, unknown> = {};
  for (const name of Object.keys(contract.mutations)) {
    mutations[name] = async (
      input: unknown,
      callOptions: MutationCallOptions = {}
    ): Promise<ContractMutationInvocation<unknown, unknown>> => {
      const mutationId = callOptions.mutationId ?? createMutationId();
      const result = await opts.mutate(name as never, { key, input, mutationId }, callOptions);
      return {
        result,
        settled: result.success
          ? settleCursors(states, contract, mutationId, result.data.cursors)
          : Promise.resolve(),
      };
    };
  }

  return {
    key,
    states: states as ReplicaStates<Group>,
    mutations: mutations as ReplicaMutations<Group>,
    ready: Promise.all(Object.values(states).map((state) => state.ready)).then(() => undefined),
  };
}

export type TranslateCursorsOptions = {
  instrumentation?: WireInstrumentation;
  mutationId?: string;
};

/**
 * Translates upstream cursors to the replica's local numbering. A translation
 * timeout never throws: the entry is translated best-effort and the result is
 * marked `settled: false` so callers can react without failure semantics.
 */
export async function translateCursors(
  instance: ReplicaInstance,
  contract: LiveModelDef,
  cursors: LiveCursorEntry[],
  options: TranslateCursorsOptions = {}
): Promise<{ cursors: LiveCursorEntry[]; settled: boolean }> {
  const translated: LiveCursorEntry[] = [];
  let settled = true;
  for (const entry of cursors) {
    const stateName = stateNameForCursor(contract, entry);
    const state = stateName ? instance.states[stateName] : undefined;
    if (!state) {
      translated.push(entry);
      continue;
    }
    try {
      await state.waitForCursor(entry.cursor);
    } catch (error) {
      settled = false;
      options.instrumentation?.cursorTranslationTimeout?.({
        model: entry.model,
        mutationId: options.mutationId,
        error,
      });
    }
    translated.push({
      ...entry,
      cursor: state.localCursorFor(entry.cursor),
    });
  }
  return { cursors: translated, settled };
}

async function settleCursors(
  states: Record<string, ReplicaState<unknown>>,
  group: LiveModelDef,
  mutationId: string,
  cursors: LiveCursorEntry[]
): Promise<void> {
  await Promise.all(
    cursors.map((entry) => {
      const stateName = stateNameForCursor(group, entry);
      if (!stateName) return Promise.resolve();
      const state = states[stateName];
      if (!state) return Promise.resolve();
      return Promise.any([
        state.waitForMutation(mutationId),
        state.waitForLocalCursor(entry.cursor),
      ])
        .then(() => undefined)
        .catch(() => undefined);
    })
  );
}

export function stateNameForCursor(
  group: LiveModelDef,
  entry: LiveCursorEntry
): string | undefined {
  for (const [name, state] of Object.entries(group.states)) {
    if (state.id === entry.model) return name;
  }
  return undefined;
}

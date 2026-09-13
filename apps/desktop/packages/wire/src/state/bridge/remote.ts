import { createScope, type Scope } from '@emdash/shared/concurrency';
import type { Clock } from '@emdash/shared/scheduling';
import type { LiveModelClientHandle, MutationCallOptions } from '../../api/client';
import type { LiveModelDef, LiveModelKey, LiveModelStates, LiveStateData } from '../../api/define';
import {
  createLiveModelReplicaCache,
  type LiveModelReplicaCacheOptions,
  type ReplicaInstance,
  type ReplicaMutations,
} from '../../live/replica';
import { cell, family, peek, type Cell, type Family, type Readable } from '../core';

type StateName<Group extends LiveModelDef> = Extract<keyof LiveModelStates<Group>, string>;

export type RemoteState<T> = Readable<T | undefined> & {
  refresh(): Promise<void>;
};

type RemoteStates<Group extends LiveModelDef> = {
  [Name in StateName<Group>]: RemoteState<LiveStateData<LiveModelStates<Group>[Name]>>;
};

export type RemoteMember<Group extends LiveModelDef> = {
  states: RemoteStates<Group>;
  mutations: ReplicaMutations<Group>;
};

export type RemoteModel<Group extends LiveModelDef> = Family<
  LiveModelKey<Group>,
  RemoteMember<Group>
>;

export type RemoteOptions<Group extends LiveModelDef> = LiveModelReplicaCacheOptions<Group> & {
  scope?: Scope;
  clock?: Clock;
};

export function remote<Group extends LiveModelDef>(
  contract: Group,
  client: LiveModelClientHandle<Group>,
  options: RemoteOptions<Group> = {}
): RemoteModel<Group> {
  const scope = options.scope
    ? options.scope.child(`remote:${contract.id}`)
    : createScope({ label: `remote:${contract.id}` });
  const replica = createLiveModelReplicaCache(contract, client, options);
  scope.add(() => replica.dispose());

  const members: RemoteModel<Group> = family(
    (key: LiveModelKey<Group>, scope) => {
      const stateCells: Record<string, Cell<unknown>> = {};
      const remoteStates: Record<string, RemoteState<unknown>> = {};
      const mutations: Record<string, unknown> = {};
      const lease = replica.acquire(key);
      const readyInstance = lease.ready();
      for (const name of Object.keys(contract.states)) {
        // Member retention while any state cell is observed is provided by the
        // family's observation-based retention; no hand-wiring needed here.
        const state = cell<unknown>(undefined, {
          name: `${contract.id}.${name}`,
        });
        state.set(undefined, { status: 'loading', notify: false });
        stateCells[name] = state;
        remoteStates[name] = withRefresh(state, async () => {
          const instance = (await readyInstance) as ReplicaInstance<Group>;
          await (
            instance.states[name as keyof typeof instance.states] as {
              refresh(): Promise<void>;
            }
          ).refresh();
        });
      }
      scope.add(() => lease.release());
      for (const name of Object.keys(contract.mutations)) {
        mutations[name] = async (input: unknown, options: MutationCallOptions = {}) => {
          const instance = (await readyInstance) as ReplicaInstance<Group>;
          return await instance.mutations[name as keyof ReplicaMutations<Group>](
            input as never,
            options
          );
        };
      }

      void lease
        .ready()
        .then((instance) => {
          for (const [name, state] of Object.entries(instance.states)) {
            const target = stateCells[name];
            if (!target) continue;
            const replicaState = state as {
              current(): unknown;
              cursor?: { generation: number };
              onChange(
                listener: (
                  value: unknown,
                  meta: { kind: 'seed' | 'update'; mutationIds?: readonly string[] }
                ) => void
              ): () => void;
            };
            target.set(replicaState.current(), {
              status: 'live',
              generation: replicaState.cursor?.generation,
            });
            scope.add(
              replicaState.onChange((value, meta) => {
                target.set(value, {
                  status: 'live',
                  generation: replicaState.cursor?.generation,
                  mutationIds: meta.kind === 'update' ? meta.mutationIds : undefined,
                });
              })
            );
          }
        })
        .catch((error: unknown) => {
          for (const target of Object.values(stateCells)) {
            target.set(peek(target), {
              status: 'error',
              error,
            });
          }
        });

      return {
        states: remoteStates as unknown as RemoteStates<Group>,
        mutations: mutations as ReplicaMutations<Group>,
      };
    },
    {
      lingerMs: options.lingerMs,
      clock: options.clock,
      scope,
      name: `remote:${contract.id}`,
    }
  );

  const disposeMembers = members.dispose;
  members.dispose = async () => {
    await disposeMembers();
    await replica.dispose();
  };
  return members;
}

function withRefresh<T>(state: Cell<T | undefined>, refresh: () => Promise<void>): RemoteState<T> {
  return Object.assign(state, { refresh }) as RemoteState<T>;
}

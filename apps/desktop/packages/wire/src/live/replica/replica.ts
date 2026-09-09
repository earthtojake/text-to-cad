import type { PendingLease } from '@emdash/shared';
import { stableStringify } from '@emdash/shared/util';
import type { LiveMutationResult, LiveSource } from '../../api/channel';
import type {
  MutationCallOptions,
  LiveModelClientHandle,
  LiveClientHandle,
} from '../../api/client';
import type { LiveModelKey, LiveModelDef, MutationData, MutationError } from '../../api/define';
import type { LiveChangeMeta } from '../state';
import {
  buildReplicaInstance,
  translateCursors,
  type ReplicaInstance,
  type ReplicaInstanceOptions,
  type ReplicaMutationResult,
} from './instance';
import type { LiveModelProvider } from './provider';
import { createReplicaResourceCache } from './retention';
import { resourceCachedLiveSource } from './source';
import { ReplicaState } from './state';
import type { StateStore } from './store';

export type LiveModelReplicaCacheOptions<Group extends LiveModelDef = LiveModelDef> =
  ReplicaInstanceOptions<Group> & {
    lingerMs?: number;
  };

export type LiveModelReplicaCache<Group extends LiveModelDef = LiveModelDef> = Omit<
  LiveModelProvider<Group>,
  'kind'
> & {
  readonly kind: 'liveModelReplicaCache';
  acquire(key: LiveModelKey<Group>): PendingLease<ReplicaInstance<Group>>;
  peek(key: LiveModelKey<Group>): ReplicaInstance<Group> | undefined;
  dispose(): Promise<void>;
};

export function createLiveModelReplicaCache<Group extends LiveModelDef>(
  contract: Group,
  group: LiveModelClientHandle<Group>,
  options: LiveModelReplicaCacheOptions<Group> = {}
): LiveModelReplicaCache<Group> {
  const source = createReplicaResourceCache<LiveModelKey<Group>, ReplicaInstance<Group>>({
    key: stableStringify,
    lingerMs: options.lingerMs,
    async create(key, scope) {
      const instance = buildReplicaInstance(contract, key, {
        createState(name, model) {
          const stateName = name as keyof Group['states'];
          const replica = new ReplicaState(
            group.state(key, name as never) as LiveClientHandle<unknown>,
            {
              instrumentation: options.instrumentation,
              logger: options.logger,
              clock: options.clock,
              onResyncFailed: options.onResyncFailed,
              onChange: options.onChange?.[stateName] as
                | ((value: unknown, meta: LiveChangeMeta) => void)
                | undefined,
              schema: model.dataSchema,
              store: options.stores?.[stateName]?.() as StateStore<unknown> | undefined,
            }
          );
          scope.add(() => replica.dispose());
          return replica;
        },
        mutate(name, envelope, callOptions) {
          return runReplicaMutation(name, envelope, callOptions);
        },
      });
      await instance.ready;
      return instance;
    },
  });

  return {
    kind: 'liveModelReplicaCache',
    contract,
    acquire(key) {
      return source.acquire(key);
    },
    peek(key) {
      return source.peek(key);
    },
    resolveState(key, name) {
      return resourceCachedLiveSource(source, key, (instance) => stateFor(instance, name));
    },
    async runMutation(name, envelope) {
      return runReplicaMutation(name, envelope);
    },
    dispose() {
      return source.dispose();
    },
  };

  async function runReplicaMutation<Name extends Extract<keyof Group['mutations'], string>>(
    name: Name,
    envelope: {
      key: LiveModelKey<Group>;
      input: unknown;
      mutationId: string;
    },
    callOptions?: MutationCallOptions
  ): Promise<
    ReplicaMutationResult<
      MutationData<Group['mutations'][Name]>,
      MutationError<Group['mutations'][Name]>
    >
  > {
    const lease = source.acquire(envelope.key);
    try {
      const instance = await lease.ready();
      const result = (await group.mutate(
        name as never,
        {
          key: envelope.key,
          input: envelope.input as never,
          mutationId: envelope.mutationId,
        },
        { ...callOptions, mutationId: envelope.mutationId } satisfies MutationCallOptions
      )) as LiveMutationResult<
        MutationData<Group['mutations'][Name]>,
        MutationError<Group['mutations'][Name]>
      >;
      if (!result.success) return result;
      const translation = await translateCursors(instance, contract, result.data.cursors, {
        instrumentation: options.instrumentation,
        mutationId: envelope.mutationId,
      });
      return {
        success: true,
        data: {
          ...result.data,
          cursors: translation.cursors,
          // Only added on timeout so the settled wire shape stays byte-identical.
          ...(translation.settled ? {} : { settled: false }),
        },
      };
    } finally {
      await lease.release();
    }
  }
}

function stateFor(instance: ReplicaInstance, name: string): LiveSource {
  const model = instance.states[name];
  if (!model) throw new Error(`Unknown replica model '${name}'`);
  return model;
}

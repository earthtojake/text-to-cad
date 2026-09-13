import { ok, type Result } from '@emdash/shared';
import { retry as retryOperation } from '@emdash/shared/scheduling';
import { z } from 'zod';
import { createMutationId, type LiveCursorEntry, type LiveMutationResult } from '../api/channel';
import {
  createLiveClientHandle,
  isEventStreamClientHandle,
  isLiveJobClientHandle,
  isLiveLogClientHandle,
  isLiveModelClientHandle,
  type EventStreamClientHandle,
  type EventStreamSubscribeOptions,
  type LiveJobClientHandle,
  type LiveLogClientHandle,
  type LiveModelClientHandle,
  type MutationCallOptions,
} from '../api/client';
import type { Connection } from '../api/connect';
import type {
  EventStreamEndpointDef,
  EventStreamEvent,
  EventStreamKey,
  JobError,
  JobInput,
  JobProgress,
  JobResult,
  LiveJobEndpointDef,
  LiveLogEndpointDef,
  LiveLogKey,
  LiveModelDef,
} from '../api/define';
import type {
  LiveEndpointBinding,
  LiveEndpointDef,
  LiveEndpointKinds,
  MaybeAsyncLiveSource,
} from '../api/endpoint-kinds';
import { WireError } from '../api/protocol';
import { encodeTopic } from '../api/topics';
import { isEventStreamHost, eventFromUpdate, type EventStreamHost } from './event-stream';
import { LiveJobSource, type LiveJobContext } from './job';
import {
  isLeasedLiveModelProvider,
  isLiveJobReplicaCache,
  isLiveLogReplicaCache,
  isLiveModelProvider,
  type LeasedLiveModelProvider,
  type LiveJobReplicaCache,
  type LiveLogReplicaCache,
  type LiveModelProvider,
} from './replica';

/**
 * The single internal dispatch module for the five live endpoint kinds
 * (liveState via liveModel, liveModel, liveJob, liveLog, eventStream). It
 * concentrates, per kind, the controller-side implementation resolution
 * (including provider duck-typing) and the client-side handle construction,
 * behind the `LiveEndpointKinds` interface the RPC core consumes. The core
 * never imports the live layer; this module imports both.
 */

export type LiveLogImpl<Def extends LiveLogEndpointDef> = (
  key: LiveLogKey<Def>
) => MaybeAsyncLiveSource;

export type LiveLogEntryImpl<Def extends LiveLogEndpointDef> =
  | LiveLogImpl<Def>
  | LiveLogClientHandle
  | LiveLogReplicaCache;

export type EventStreamImpl<Def extends EventStreamEndpointDef> = (
  key: EventStreamKey<Def>
) => MaybeAsyncLiveSource;

export type EventStreamEntryImpl<Def extends EventStreamEndpointDef> =
  | EventStreamImpl<Def>
  | EventStreamHost<Def>
  | EventStreamClientHandle<Def>;

export type LiveModelEntryImpl<Def extends LiveModelDef> =
  | LiveModelClientHandle<Def>
  | LiveModelProvider<Def>
  | LeasedLiveModelProvider<Def>;

export type JobImpl<Def extends LiveJobEndpointDef> = {
  run(
    input: JobInput<Def>,
    ctx: LiveJobContext<JobProgress<Def>>
  ): Promise<Result<JobResult<Def>, JobError<Def>>> | Result<JobResult<Def>, JobError<Def>>;
  toError?(error: unknown): JobError<Def>;
};

export type LiveJobEntryImpl<Def extends LiveJobEndpointDef> =
  | JobImpl<Def>
  | LiveJobClientHandle<Def>
  | LiveJobReplicaCache<Def>;

const jobKeySchema = z.object({ jobId: z.string() });

export const liveEndpointKinds: LiveEndpointKinds = {
  bindEndpoint(def, impl, path) {
    switch (def.kind) {
      case 'liveLog':
        return bindLiveLog(def, impl, path);
      case 'eventStream':
        return bindEventStream(def, impl, path);
      case 'liveJob':
        return bindLiveJob(def, impl, path);
      case 'liveModel':
        return bindLiveModel(def, impl, path);
    }
  },
  createEndpointClient(def, path, connection) {
    switch (def.kind) {
      case 'liveLog':
        return createLiveLogClientHandle(connection, def);
      case 'eventStream':
        return createEventStreamClientHandle(connection, def);
      case 'liveJob':
        return createLiveJobClientHandle(connection, def, path);
      case 'liveModel':
        return createLiveModelClientHandle(connection, path, def);
    }
  },
};

function bindLiveLog(
  def: LiveLogEndpointDef,
  entryImpl: unknown,
  fullPath: string
): LiveEndpointBinding {
  const impl = entryImpl as LiveLogEntryImpl<LiveLogEndpointDef> | undefined;
  if (!impl) {
    throw new WireError('MISSING_HANDLER', `Live log '${fullPath}' requires a resolver`);
  }
  if (isLiveLogReplicaCache(impl) && impl.def.id !== def.id) {
    throw new WireError(
      'CONTRACT_MISMATCH',
      `Live log replica for '${fullPath}' was created for '${impl.def.id}'`
    );
  }
  return {
    topics: [{ id: def.id, resolve: createLiveLogResolver(impl) }],
  };
}

function bindEventStream(
  def: EventStreamEndpointDef,
  entryImpl: unknown,
  fullPath: string
): LiveEndpointBinding {
  const impl = entryImpl as EventStreamEntryImpl<EventStreamEndpointDef> | undefined;
  if (!impl) {
    throw new WireError('MISSING_HANDLER', `Event stream '${fullPath}' requires a resolver`);
  }
  if (def.resourced && !isEventStreamHost(impl) && !isEventStreamClientHandle(impl)) {
    throw new WireError(
      'CONTRACT_MISMATCH',
      `Resourced event stream '${fullPath}' requires a host or forwarded client handle`
    );
  }
  return {
    topics: [{ id: def.id, resolve: createEventStreamResolver(def, impl) }],
  };
}

function bindLiveJob(
  def: LiveJobEndpointDef,
  entryImpl: unknown,
  fullPath: string
): LiveEndpointBinding {
  const impl = entryImpl as LiveJobEntryImpl<LiveJobEndpointDef> | undefined;
  if (!impl) {
    throw new WireError('MISSING_HANDLER', `Job '${fullPath}' requires a handler`);
  }
  if (isLiveJobClientHandle(impl)) {
    return {
      topics: [
        {
          id: def.id,
          resolve: (key) => impl.handle((key as { jobId: string }).jobId).asLiveSource(),
        },
      ],
      procedures: [
        { path: `${fullPath}.start`, handler: (input) => impl.start(input as never) },
        {
          path: `${fullPath}.cancel`,
          handler: async (input) => {
            const parsed = jobKeySchema.parse(input);
            await impl.cancel(parsed.jobId);
            return undefined;
          },
        },
      ],
    };
  }
  if (isLiveJobReplicaCache(impl)) {
    if (impl.def.id !== def.id) {
      throw new WireError(
        'CONTRACT_MISMATCH',
        `Live job replica for '${fullPath}' was created for '${impl.def.id}'`
      );
    }
    return {
      topics: [{ id: def.id, resolve: (key) => impl.resolve((key as { jobId: string }).jobId) }],
      procedures: [
        {
          path: `${fullPath}.start`,
          handler: async (input) => {
            const lease = await impl.start(input as never);
            try {
              const job = await lease.ready();
              return { jobId: job.jobId };
            } finally {
              await lease.release();
            }
          },
        },
        {
          path: `${fullPath}.cancel`,
          handler: async (input) => {
            const parsed = jobKeySchema.parse(input);
            await impl.cancel(parsed.jobId);
            return undefined;
          },
        },
      ],
    };
  }
  const server = createLiveJob(impl);
  return {
    topics: [{ id: def.id, resolve: (key) => server.source((key as { jobId: string }).jobId) }],
    procedures: [
      { path: `${fullPath}.start`, handler: async (input) => server.start(input) },
      {
        path: `${fullPath}.cancel`,
        handler: async (input) => {
          const parsed = jobKeySchema.parse(input);
          server.cancel(parsed.jobId);
          return undefined;
        },
      },
    ],
    dispose: () => server.dispose(),
  };
}

function bindLiveModel(
  def: LiveModelDef,
  entryImpl: unknown,
  fullPath: string
): LiveEndpointBinding {
  const provider = resolveLiveModelProvider(def, entryImpl, fullPath);
  return {
    topics: Object.entries(def.states).map(([stateName, state]) =>
      provider.kind === 'leasedLiveModelProvider'
        ? {
            id: state.id,
            acquire: (key: unknown) => provider.acquireState(key as never, stateName),
          }
        : {
            id: state.id,
            resolve: (key: unknown) => provider.resolveState(key as never, stateName),
          }
    ),
    procedures: Object.keys(def.mutations).map((mutationName) => ({
      path: `${fullPath}.${mutationName}`,
      handler: async (input: unknown) => {
        const envelope = parseLiveModelMutationInput(input);
        return await provider.runMutation(mutationName, envelope as never);
      },
    })),
  };
}

function resolveLiveModelProvider(
  def: LiveModelDef,
  entryImpl: unknown,
  fullPath: string
): LiveModelProvider | LeasedLiveModelProvider {
  if (isLeasedLiveModelProvider(entryImpl)) {
    if (entryImpl.contract.id !== def.id) {
      throw new WireError(
        'CONTRACT_MISMATCH',
        `Leased live model provider for '${fullPath}' was created for '${entryImpl.contract.id}'`
      );
    }
    return entryImpl;
  }

  if (isLiveModelProvider(entryImpl)) {
    if (entryImpl.contract.id !== def.id) {
      throw new WireError(
        'CONTRACT_MISMATCH',
        `Live model provider for '${fullPath}' was created for '${entryImpl.contract.id}'`
      );
    }
    return entryImpl;
  }

  if (isLiveModelClientHandle(entryImpl)) {
    if (entryImpl.def.id !== def.id) {
      throw new WireError(
        'CONTRACT_MISMATCH',
        `Live model client handle for '${fullPath}' was created for '${entryImpl.def.id}'`
      );
    }
    return {
      kind: 'liveModelProvider',
      contract: def,
      resolveState: (key, name) => entryImpl.state(key, name).asLiveSource(),
      runMutation: (name, envelope) => entryImpl.mutate(name, envelope),
    };
  }

  throw new WireError(
    'MISSING_HANDLER',
    `Live model '${fullPath}' requires a provider or client handle`
  );
}

function createLiveLogResolver(
  impl: LiveLogEntryImpl<LiveLogEndpointDef>
): (key: unknown) => MaybeAsyncLiveSource {
  if (isLiveLogReplicaCache(impl)) return (key) => impl.resolve(key as never);
  if (isLiveLogClientHandle(impl)) return (key) => impl.handle(key as never).asLiveSource();
  return impl as (key: unknown) => MaybeAsyncLiveSource;
}

function createEventStreamResolver(
  def: EventStreamEndpointDef,
  impl: EventStreamEntryImpl<EventStreamEndpointDef>
): (key: unknown) => MaybeAsyncLiveSource {
  if (isEventStreamHost(impl)) {
    if (impl.def.id !== def.id) {
      throw new WireError(
        'CONTRACT_MISMATCH',
        `Event stream host for '${def.id}' was created for '${impl.def.id}'`
      );
    }
    return (key) => impl.resolve(key as never);
  }
  if (isEventStreamClientHandle(impl)) {
    if (impl.def.id !== def.id) {
      throw new WireError(
        'CONTRACT_MISMATCH',
        `Event stream client handle for '${def.id}' was created for '${impl.def.id}'`
      );
    }
    return (key) => impl.handle(key as never).asLiveSource();
  }
  return impl as (key: unknown) => MaybeAsyncLiveSource;
}

function createLiveJob(
  impl: JobImpl<LiveJobEndpointDef>
): LiveJobSource<unknown, unknown, unknown, unknown> {
  return new LiveJobSource<unknown, unknown, unknown, unknown>(
    async (input, ctx) => {
      return await impl.run(input, {
        jobId: ctx.jobId,
        signal: ctx.signal,
        progress: (progress) => ctx.progress(progress),
      });
    },
    {
      toError: impl.toError,
    }
  );
}

function parseLiveModelMutationInput(input: unknown): {
  key: unknown;
  input: Record<string, unknown>;
  mutationId: string;
} {
  const envelope = input as { key?: unknown; input?: unknown; mutationId?: unknown };
  return {
    key: envelope.key,
    input: (envelope.input ?? {}) as Record<string, unknown>,
    mutationId: typeof envelope.mutationId === 'string' ? envelope.mutationId : createMutationId(),
  };
}

function createLiveLogClientHandle<Def extends LiveLogEndpointDef>(
  connection: Connection,
  def: Def
): LiveLogClientHandle<Def> {
  return {
    kind: 'liveLogClientHandle',
    def,
    handle: (key) => createLiveClientHandle(connection, encodeTopic(def.id, key)),
  };
}

function createEventStreamClientHandle<Def extends EventStreamEndpointDef>(
  connection: Connection,
  def: Def
): EventStreamClientHandle<Def> {
  return {
    kind: 'eventStreamClientHandle',
    def,
    handle: (key) => createLiveClientHandle(connection, encodeTopic(def.id, key)),
    subscribe(key, options: EventStreamSubscribeOptions<Def>) {
      return connection.attach(
        encodeTopic(def.id, key),
        (update) => options.onEvent(eventFromUpdate<EventStreamEvent<Def>>(update)),
        {
          onReattach: options.onGap,
          onReattachError: options.onError,
        }
      );
    },
  };
}

function createLiveJobClientHandle<Def extends LiveJobEndpointDef>(
  connection: Connection,
  def: Def,
  path: string
): LiveJobClientHandle<Def> {
  return {
    kind: 'liveJobClientHandle',
    def,
    async start(input) {
      return (await connection.call(`${path}.start`, input)) as { jobId: string };
    },
    async cancel(jobId) {
      await connection.call(`${path}.cancel`, { jobId });
    },
    handle(jobId) {
      return createLiveClientHandle(connection, encodeTopic(def.id, { jobId }));
    },
  };
}

function createLiveModelClientHandle<Def extends LiveModelDef>(
  connection: Connection,
  path: string,
  def: Def
): LiveModelClientHandle<Def> {
  return {
    kind: 'liveModelClientHandle',
    def,
    state(key: unknown, name: string) {
      const state = def.states[name];
      return createLiveClientHandle(connection, encodeTopic(state.id, key));
    },
    mutate(
      name: string,
      envelope: { key: unknown; input: unknown; mutationId?: string },
      options?: MutationCallOptions
    ) {
      const mutationId = envelope.mutationId ?? options?.mutationId ?? createMutationId();
      return callMutationWithRetry(
        connection,
        `${path}.${name}`,
        envelope,
        mutationId,
        options ?? {}
      ) as Promise<LiveMutationResult<never, never>>;
    },
  } as unknown as LiveModelClientHandle<Def>;
}

async function callMutationWithRetry(
  connection: Connection,
  path: string,
  input: unknown,
  mutationId: string,
  options: MutationCallOptions
): Promise<unknown> {
  const call = (): Promise<unknown> =>
    connection.call(path, addMutationId(input, mutationId), {
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  const retry = options.retry;
  if (!retry) return call();
  return await retryOperation(call, {
    signal: options.signal,
    schedule: retry.schedule,
    shouldRetry: shouldRetryMutation,
  });
}

function shouldRetryMutation(error: unknown): boolean {
  return error instanceof WireError && (error.code === 'DISCONNECTED' || error.code === 'TIMEOUT');
}

function addMutationId(input: unknown, mutationId: string): unknown {
  return { ...(input as { key: unknown; input: unknown }), mutationId };
}

type ForwardedMutationResult = Result<{ data: unknown; cursors: LiveCursorEntry[] }, unknown>;

/**
 * Rebinds a live endpoint client handle to a mounted contract definition for
 * `forwardContractImpl`, remapping live-model mutation cursors onto the
 * mounted state ids.
 */
export function rebindLiveClientHandle(def: LiveEndpointDef, clientEntry: unknown): unknown {
  if (typeof clientEntry !== 'object' || clientEntry === null || Array.isArray(clientEntry)) {
    return clientEntry;
  }
  if (def.kind !== 'liveModel') return { ...clientEntry, def };

  const source = clientEntry as {
    def?: LiveModelDef;
    mutate?: (...args: unknown[]) => Promise<ForwardedMutationResult>;
  };
  if (!source.def || typeof source.mutate !== 'function') return { ...clientEntry, def };

  const targetStateIds = new Map(
    Object.entries(source.def.states).flatMap(([name, state]) => {
      const target = def.states[name];
      return target ? [[state.id, target.id] as const] : [];
    })
  );
  return {
    ...clientEntry,
    def,
    async mutate(...args: unknown[]) {
      const result = await source.mutate!(...args);
      if (!result.success) return result;
      return ok({
        ...result.data,
        cursors: result.data.cursors.map((cursor) => ({
          ...cursor,
          model: targetStateIds.get(cursor.model) ?? cursor.model,
        })),
      });
    },
  };
}

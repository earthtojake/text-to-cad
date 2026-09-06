import { ok, type Result, type SerializedError, type Unsubscribe } from '@emdash/shared';
import type { RetrySchedule } from '@emdash/shared/scheduling';
import {
  createSingleUseDownloadHandle,
  normalizeUploadFile,
  type BlobDownloadHandle,
  type UploadFileValue,
} from './blob-channel';
import type {
  EventStreamSnapshotData,
  LiveLogSnapshotData,
  LiveMutationResult,
  LiveSnapshot,
  LiveSource,
  LiveUpdate,
} from './channel';
import type { AttachOptions, CallOptions, Connection } from './connect';
import type {
  Contract,
  ContractDefinitions,
  DownloadFileEndpointDef,
  DownloadFileError,
  DownloadFileInput,
  DownloadFileMeta,
  EndpointDef,
  EventStreamEndpointDef,
  EventStreamEvent,
  EventStreamKey,
  EndpointInput,
  LiveStateData,
  EndpointOutput,
  LiveModelKey,
  LiveModelStates,
  LiveModelMutations,
  LiveJobEndpointDef,
  JobError,
  JobInput,
  JobProgress,
  JobResult,
  LiveLogEndpointDef,
  LiveLogKey,
  LiveModelDef,
  MutationData,
  MutationError,
  MutationInput,
  UploadFileEndpointDef,
  UploadFileError,
  UploadFileInput,
  UploadFileResult,
} from './define';
import { isEndpointDef } from './define';
import type { LiveEndpointKinds } from './endpoint-kinds';
import type { WireError } from './protocol';

export type MutationCallOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
  mutationId?: string;
  /**
   * Explicit opt-in retry on `DISCONNECTED`/`TIMEOUT` rejections. There is no
   * automatic retry; mutation ids keep opted-in retries idempotent.
   */
  retry?: {
    schedule: RetrySchedule;
  };
};

export type ProcedureCallOptions = Pick<CallOptions, 'signal' | 'timeoutMs'>;
export type FileUploadCallOptions = ProcedureCallOptions & {
  onProgress?: (progress: { sent: number; total?: number }) => void;
};

export type ClientOptions = {
  pathPrefix?: string;
};

export type LiveClientHandle<T = unknown> = {
  readonly topic: string;
  snapshot(): Promise<LiveSnapshot<T>>;
  attach(push: (update: LiveUpdate) => void, options?: AttachOptions): Promise<Unsubscribe>;
  asLiveSource(): LiveSource;
};

export type LiveLogClientHandle<Def extends LiveLogEndpointDef = LiveLogEndpointDef> = {
  readonly kind: 'liveLogClientHandle';
  readonly def: Def;
  handle(key: LiveLogKey<Def>): LiveClientHandle<LiveLogSnapshotData>;
};

export type EventStreamSubscribeOptions<
  Def extends EventStreamEndpointDef = EventStreamEndpointDef,
> = {
  onEvent(event: EventStreamEvent<Def>): void;
  onGap?(): void;
  onError?: (error: WireError, context: { retrying: boolean }) => void;
};

export type EventStreamClientHandle<Def extends EventStreamEndpointDef = EventStreamEndpointDef> = {
  readonly kind: 'eventStreamClientHandle';
  readonly def: Def;
  handle(key: EventStreamKey<Def>): LiveClientHandle<EventStreamSnapshotData>;
  subscribe(
    key: EventStreamKey<Def>,
    options: EventStreamSubscribeOptions<Def>
  ): Promise<Unsubscribe>;
};

export type LiveModelClientHandle<Def extends LiveModelDef = LiveModelDef> =
  Def extends LiveModelDef
    ? {
        readonly kind: 'liveModelClientHandle';
        readonly def: Def;
        state<Name extends Extract<keyof LiveModelStates<Def>, string>>(
          key: LiveModelKey<Def>,
          name: Name
        ): LiveClientHandle<LiveStateData<LiveModelStates<Def>[Name]>>;
        mutate<Name extends Extract<keyof LiveModelMutations<Def>, string>>(
          name: Name,
          envelope: {
            key: LiveModelKey<Def>;
            input: MutationInput<LiveModelMutations<Def>[Name]>;
            mutationId?: string;
          },
          options?: MutationCallOptions
        ): Promise<
          LiveMutationResult<
            MutationData<LiveModelMutations<Def>[Name]>,
            MutationError<LiveModelMutations<Def>[Name]>
          >
        >;
      }
    : never;

export type LiveJobClientHandle<Def extends LiveJobEndpointDef = LiveJobEndpointDef> = {
  readonly kind: 'liveJobClientHandle';
  readonly def: Def;
  start(input: JobInput<Def>): Promise<{ jobId: string }>;
  cancel(jobId: string): Promise<void>;
  handle(jobId: string): LiveClientHandle<LiveJobStateFor<Def>>;
};

export type LiveJobStateFor<Def extends LiveJobEndpointDef> =
  | {
      status: 'running';
      startedAt: number;
      progress: JobProgress<Def>[];
      progressCount: number;
    }
  | {
      status: 'succeeded';
      startedAt: number;
      finishedAt: number;
      progress: JobProgress<Def>[];
      result: JobResult<Def>;
    }
  | {
      status: 'failed';
      startedAt: number;
      finishedAt: number;
      progress: JobProgress<Def>[];
      error?: JobError<Def>;
      cause?: SerializedError;
    }
  | {
      status: 'cancelled';
      startedAt: number;
      finishedAt: number;
      progress: JobProgress<Def>[];
    };

type EndpointClient<Def> = Def extends { kind: 'procedure' }
  ? (input: EndpointInput<Def>, options?: ProcedureCallOptions) => Promise<EndpointOutput<Def>>
  : Def extends LiveJobEndpointDef
    ? LiveJobClientHandle<Def>
    : Def extends EventStreamEndpointDef
      ? EventStreamClientHandle<Def>
      : Def extends LiveLogEndpointDef
        ? LiveLogClientHandle<Def>
        : Def extends LiveModelDef
          ? LiveModelClientHandle<Def>
          : Def extends DownloadFileEndpointDef
            ? (
                input: DownloadFileInput<Def>,
                options?: ProcedureCallOptions
              ) => Promise<
                Result<BlobDownloadHandle<DownloadFileMeta<Def>>, DownloadFileError<Def>>
              >
            : Def extends UploadFileEndpointDef
              ? (
                  input: UploadFileInput<Def>,
                  file: UploadFileValue,
                  options?: FileUploadCallOptions
                ) => Promise<Result<UploadFileResult<Def>, UploadFileError<Def>>>
              : never;

type ContractEntryClient<Def> = Def extends EndpointDef
  ? EndpointClient<Def>
  : Def extends Contract<infer Nested>
    ? ContractClient<Nested>
    : never;

export type ContractClient<Defs extends ContractDefinitions> = {
  [Name in Extract<keyof Defs, string>]: ContractEntryClient<Defs[Name]>;
};

export type BuildClientOptions = ClientOptions & {
  /** The single internal live endpoint-kind dispatch table. */
  liveEndpoints: LiveEndpointKinds;
};

/**
 * Core client engine. Builds procedure and blob endpoint callers itself and
 * delegates live endpoint handles to the supplied dispatch table. The public
 * `client` wrapper injects the table.
 */
export function buildClient<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  connection: Connection,
  options: BuildClientOptions
): ContractClient<Defs> {
  const pathPrefix = options.pathPrefix ? [options.pathPrefix] : [];
  return buildContractClient(
    contract,
    pathPrefix,
    connection,
    options.liveEndpoints
  ) as ContractClient<Defs>;
}

function buildContractClient(
  contract: ContractDefinitions,
  pathPrefix: string[],
  connection: Connection,
  liveEndpoints: LiveEndpointKinds
): Record<string, unknown> {
  const client: Record<string, unknown> = {};

  for (const [name, def] of Object.entries(contract)) {
    const fullPath = [...pathPrefix, name].join('.');
    if (!isEndpointDef(def)) {
      client[name] = buildContractClient(def, [...pathPrefix, name], connection, liveEndpoints);
      continue;
    }

    switch (def.kind) {
      case 'procedure':
        client[name] = (input: unknown, options?: ProcedureCallOptions) =>
          connection.call(fullPath, input, options);
        break;
      case 'downloadFile':
        client[name] = async (input: unknown, options?: ProcedureCallOptions) => {
          const result = (await connection.call(fullPath, input, options)) as Result<
            { meta: DownloadFileMeta<typeof def>; channel: string },
            unknown
          >;
          if (!result.success) return result;
          const handle = createSingleUseDownloadHandle(
            result.data.meta,
            connection.openBlobConsumer(result.data.channel)
          );
          options?.signal?.addEventListener('abort', () => handle.cancel(), { once: true });
          return ok(handle);
        };
        break;
      case 'uploadFile':
        client[name] = async (
          input: unknown,
          file: UploadFileValue,
          options?: FileUploadCallOptions
        ) => {
          const { meta, source } = normalizeUploadFile(file);
          const channel = createRequestId();
          const producer = connection.openBlobProducer(channel, source);
          const onAbort = (): void => producer.close();
          options?.signal?.addEventListener('abort', onAbort, { once: true });
          try {
            return (await connection.call(fullPath, input, {
              signal: options?.signal,
              upload: { channel, meta },
            })) as Result<unknown, unknown>;
          } finally {
            options?.signal?.removeEventListener('abort', onAbort);
            producer.close();
          }
        };
        break;
      case 'liveJob':
      case 'liveLog':
      case 'eventStream':
      case 'liveModel':
        client[name] = liveEndpoints.createEndpointClient(def, fullPath, connection);
        break;
    }
  }

  return client;
}

/** Builds the generic per-topic handle every live endpoint kind hands out. */
export function createLiveClientHandle<T>(
  connection: Connection,
  topic: string
): LiveClientHandle<T> {
  return {
    topic,
    snapshot: () => connection.snapshot(topic) as Promise<LiveSnapshot<T>>,
    attach: (push, options) => connection.attach(topic, push, options),
    asLiveSource() {
      return {
        snapshot: () => connection.snapshot(topic),
        subscribe: (cb, options) =>
          connection.attach(topic, cb, {
            onReattach: options?.onGap,
            onReattachError: options?.onError,
          }),
      };
    },
  };
}

function createRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `wire_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

export function isLiveLogClientHandle(value: unknown): value is LiveLogClientHandle {
  return isTagged(value, 'liveLogClientHandle');
}

export function isEventStreamClientHandle(value: unknown): value is EventStreamClientHandle {
  return isTagged(value, 'eventStreamClientHandle');
}

export function isLiveModelClientHandle(value: unknown): value is LiveModelClientHandle {
  return isTagged(value, 'liveModelClientHandle');
}

export function isLiveJobClientHandle(value: unknown): value is LiveJobClientHandle {
  return isTagged(value, 'liveJobClientHandle');
}

function isTagged(value: unknown, kind: string): boolean {
  return typeof value === 'object' && value !== null && (value as { kind?: unknown }).kind === kind;
}

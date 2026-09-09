import type {
  ContractClient,
  EventStreamClientHandle,
  EventStreamSubscribeOptions,
  FileUploadCallOptions,
  LiveClientHandle,
  LiveJobClientHandle,
  LiveLogClientHandle,
  LiveModelClientHandle,
  MutationCallOptions,
  ProcedureCallOptions,
} from '../api/client';
import type { Contract, ContractDefinitions } from '../api/define';
import { isEndpointDef } from '../api/define';
import { encodeTopic } from '../api/topics';

/**
 * A queueing (VS Code barrier style) view over a client that is not available
 * yet. Every endpoint waits for the readiness promise internally, so callers
 * can issue calls before the backing worker or connection exists: early calls
 * queue on the readiness promise and complete once it resolves, and a
 * readiness failure (for example a worker spawn error) rejects every queued
 * and future call with that failure. No artificial timeout is introduced —
 * the readiness promise's own lifecycle decides when queued calls settle.
 *
 * Live endpoint handles are constructed synchronously with their canonical
 * topics (the same `encodeTopic` scheme the real client uses); only their
 * traffic (snapshot/attach/subscribe/mutate) awaits readiness.
 */
export function queuedClient<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  ready: () => Promise<ContractClient<Defs>>
): ContractClient<Defs> {
  let memo: Promise<ContractClient<Defs>> | undefined;
  const readyOnce = (): Promise<ContractClient<Defs>> => (memo ??= ready());
  return buildQueuedContractClient(
    contract,
    [],
    readyOnce as () => Promise<unknown>
  ) as ContractClient<Defs>;
}

type AnyClientEntry = Record<string, unknown>;

function buildQueuedContractClient(
  contract: ContractDefinitions,
  path: string[],
  ready: () => Promise<unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [name, def] of Object.entries(contract)) {
    const entryPath = [...path, name];
    if (!isEndpointDef(def)) {
      result[name] = buildQueuedContractClient(def, entryPath, ready);
      continue;
    }

    const leaf = (): Promise<unknown> => ready().then((client) => resolvePath(client, entryPath));

    switch (def.kind) {
      case 'procedure':
      case 'downloadFile':
        result[name] = (input: unknown, options?: ProcedureCallOptions) =>
          leaf().then((fn) =>
            (fn as (i: unknown, o?: ProcedureCallOptions) => unknown)(input, options)
          );
        break;
      case 'uploadFile':
        result[name] = (input: unknown, file: unknown, options?: FileUploadCallOptions) =>
          leaf().then((fn) =>
            (fn as (i: unknown, f: unknown, o?: FileUploadCallOptions) => unknown)(
              input,
              file,
              options
            )
          );
        break;
      case 'liveLog': {
        const handle: LiveLogClientHandle = {
          kind: 'liveLogClientHandle',
          def,
          handle: (key) =>
            queuedLiveHandle(encodeTopic(def.id, key), async () =>
              ((await leaf()) as LiveLogClientHandle).handle(key)
            ),
        };
        result[name] = handle;
        break;
      }
      case 'eventStream': {
        const handle: EventStreamClientHandle = {
          kind: 'eventStreamClientHandle',
          def,
          handle: (key) =>
            queuedLiveHandle(encodeTopic(def.id, key), async () =>
              ((await leaf()) as EventStreamClientHandle).handle(key)
            ),
          subscribe: async (key, options: EventStreamSubscribeOptions) =>
            await ((await leaf()) as EventStreamClientHandle).subscribe(key, options),
        };
        result[name] = handle;
        break;
      }
      case 'liveJob': {
        const handle: LiveJobClientHandle = {
          kind: 'liveJobClientHandle',
          def,
          start: async (input) => await ((await leaf()) as LiveJobClientHandle).start(input),
          cancel: async (jobId) => {
            await ((await leaf()) as LiveJobClientHandle).cancel(jobId);
          },
          handle: (jobId) =>
            queuedLiveHandle(encodeTopic(def.id, { jobId }), async () =>
              ((await leaf()) as LiveJobClientHandle).handle(jobId)
            ),
        };
        result[name] = handle;
        break;
      }
      case 'liveModel': {
        const handle = {
          kind: 'liveModelClientHandle',
          def,
          state: (key: unknown, stateName: string) =>
            queuedLiveHandle(encodeTopic(def.states[stateName].id, key), async () =>
              (
                (await leaf()) as {
                  state(key: unknown, name: string): LiveClientHandle;
                }
              ).state(key, stateName)
            ),
          mutate: async (
            mutationName: string,
            envelope: { key: unknown; input: unknown; mutationId?: string },
            options?: MutationCallOptions
          ) =>
            await (
              (await leaf()) as {
                mutate(
                  name: string,
                  envelope: { key: unknown; input: unknown; mutationId?: string },
                  options?: MutationCallOptions
                ): Promise<unknown>;
              }
            ).mutate(mutationName, envelope, options),
        };
        result[name] = handle as unknown as LiveModelClientHandle;
        break;
      }
    }
  }
  return result;
}

function queuedLiveHandle<T>(
  topic: string,
  getHandle: () => Promise<LiveClientHandle<T>>
): LiveClientHandle<T> {
  return {
    topic,
    snapshot: async () => await (await getHandle()).snapshot(),
    attach: async (push, options) => await (await getHandle()).attach(push, options),
    asLiveSource() {
      return {
        snapshot: async () => await (await getHandle()).snapshot(),
        subscribe: async (cb, options) =>
          await (await getHandle()).asLiveSource().subscribe(cb, options),
      };
    },
  };
}

function resolvePath(client: unknown, path: string[]): unknown {
  let current: unknown = client;
  for (const segment of path) {
    current = (current as AnyClientEntry)[segment];
  }
  return current;
}

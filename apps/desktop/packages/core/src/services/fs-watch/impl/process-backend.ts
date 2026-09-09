import { stableStringify } from '@emdash/shared/util';
import { eventFromUpdate } from '@emdash/wire/live';
import type { ContractClient } from '@emdash/wire/rpc';
import type { fsWatchContract, FsWatchStreamEvent } from '#services/fs-watch/api';
import type { WatchBackend, WatchKey, WatchOnError } from './backend';

export type ProcessWatchBackendOptions = {
  client:
    | ContractClient<typeof fsWatchContract>
    | (() => Promise<ContractClient<typeof fsWatchContract>>);
  ready?: () => Promise<void>;
  onError?: WatchOnError;
};

export function processWatchBackend(options: ProcessWatchBackendOptions): WatchBackend {
  const onError = options.onError ?? (() => {});

  return {
    async subscribe(key, sink, scope) {
      await options.ready?.();
      const client = await getClient(options.client);
      const detach = await client.events.handle(key).attach(
        (update) => {
          const event = eventFromUpdate<FsWatchStreamEvent>(update);
          switch (event.kind) {
            case 'events':
              sink.events(event.events);
              break;
            case 'resync':
              sink.resync();
              break;
          }
        },
        {
          onReattach: () => sink.resync(),
          onReattachError: (error, context) => {
            const mode = context.retrying ? 'retrying' : 'terminal';
            onError(`watch ${keyId(key)} reattach ${mode}`, error);
          },
        }
      );
      scope.add(detach);
    },
  };
}

async function getClient(
  client: ProcessWatchBackendOptions['client']
): Promise<ContractClient<typeof fsWatchContract>> {
  if (typeof client === 'function') return await client();
  return client;
}

function keyId(key: WatchKey): string {
  return stableStringify(key);
}

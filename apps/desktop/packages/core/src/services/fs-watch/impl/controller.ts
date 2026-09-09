import type { Scope } from '@emdash/shared/concurrency';
import { stableStringify } from '@emdash/shared/util';
import { createEventStreamHost } from '@emdash/wire/live';
import { createController, type Controller } from '@emdash/wire/rpc';
import { fsWatchContract, requireWatchReady, type FsWatchKey } from '#services/fs-watch/api';
import type { IWatchService } from '#services/fs-watch/api';
import { nativeWatchBackend } from './native-backend';
import { createWatchService } from './watch-service';

export type CreateFsWatchControllerOptions = {
  scope: Scope;
  onError?: (context: string, error: unknown) => void;
  service?: IWatchService;
};

export function createFsWatchController(options: CreateFsWatchControllerOptions): Controller {
  const service =
    options.service ??
    createWatchService({
      backend: nativeWatchBackend({ onError: options.onError }),
      scope: options.scope,
      onError: options.onError,
    });
  const events = createEventStreamHost(fsWatchContract.events, {
    activate: async (key) => {
      const handle = service.watch(
        key.root,
        (batch) => events.emit(key, { kind: 'events', events: batch }),
        {
          ignore: key.ignore,
          onResync: () => events.emit(key, { kind: 'resync' }),
        }
      );
      try {
        await requireWatchReady(handle);
      } catch (error) {
        try {
          await handle.release();
        } catch (releaseError) {
          options.onError?.(`release failed watch ${keyId(key)}`, releaseError);
        }
        options.onError?.(`watch ${keyId(key)}`, error);
        throw error;
      }
      return () => {
        void handle
          .release()
          .catch((error) => options.onError?.(`release watch ${keyId(key)}`, error));
      };
    },
  });

  options.scope.add(async () => {
    events.dispose();
    await service.dispose();
  });

  return createController(fsWatchContract, {
    events,
  });
}

function keyId(key: FsWatchKey): string {
  return stableStringify(key);
}

import type { Scope } from '@emdash/shared/concurrency';
import type { IWatchService } from '#services/fs-watch/api';
import {
  nativeWatchBackend,
  type NativeWatchBackendOptions,
} from '#services/fs-watch/impl/native-backend';
import { createWatchService } from '#services/fs-watch/impl/watch-service';

export type CreateNativeWatchServiceOptions = Readonly<{
  scope?: Scope;
  graceMs?: number;
  onError?: NativeWatchBackendOptions['onError'];
  subscribe?: NativeWatchBackendOptions['subscribe'];
}>;

export function createNativeWatchService(
  options: CreateNativeWatchServiceOptions = {}
): IWatchService {
  return createWatchService({
    backend: nativeWatchBackend({ onError: options.onError, subscribe: options.subscribe }),
    scope: options.scope,
    graceMs: options.graceMs,
    onError: options.onError,
  });
}

export { fsWatchComponent, fsWatchComponentConfigSchema } from './component';
export { fsWatchWorkerSpec, type FsWatchWorkerSpecInput } from './worker-spec';

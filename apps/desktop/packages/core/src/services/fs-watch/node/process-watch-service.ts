import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import type { ContractClient } from '@emdash/wire/rpc';
import type { fsWatchContract } from '#services/fs-watch/api';
import { processWatchBackend } from '#services/fs-watch/impl/process-backend';
import { createWatchService } from '#services/fs-watch/impl/watch-service';

export function createProcessWatchServiceFromDependency({
  client,
  logger,
  scope,
}: {
  client: ContractClient<typeof fsWatchContract>;
  logger: Logger;
  scope: Scope;
}) {
  const onError = (context: string, error: unknown): void => logger.warn(context, { error });
  return createWatchService({
    backend: processWatchBackend({
      client,
      onError,
    }),
    scope,
    onError,
  });
}

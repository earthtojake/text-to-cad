import type { HostDependenciesContract } from '@emdash/core/services/host-dependencies/node';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import type { ContractClient } from '@emdash/wire/rpc';
import { remoteRuntimeUnavailable } from '@core/primitives/desktop-runtime/api/runtime-errors';

export type HostDependenciesClient = ContractClient<HostDependenciesContract>;

export function createDependencyManagerResolver(localDependencyManager: HostDependenciesClient) {
  return async function getDependencyManager(
    connectionId?: string
  ): Promise<Result<HostDependenciesClient, RuntimeResolveError>> {
    if (!connectionId) return ok(localDependencyManager);
    return err(remoteRuntimeUnavailable(connectionId, 'host-dependencies'));
  };
}

export async function ensureAgentDependenciesProbed(
  manager: HostDependenciesClient,
  _options: { refreshShellEnv?: boolean } = { refreshShellEnv: true }
): Promise<void> {
  await manager.snapshot.mutate('refresh', { key: undefined, input: {} });
}

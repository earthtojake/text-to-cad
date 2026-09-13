import type { HostDependencySnapshot } from '@emdash/core/services/host-dependencies/api';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { useCallback, useMemo } from 'react';
import { machinesContract, type MachineSystemDependencyStatus } from '@core/features/machines/api';
import { getMachinesClient } from '@core/features/machines/api/browser/client';
import { mapSystemDependencySnapshot } from '@core/features/machines/api/system-dependencies';
import { getHostDependencyErrorMessage } from '@core/primitives/host-dependencies/browser/error-message';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';

let systemDependenciesRemotePromise:
  | Promise<RemoteModel<typeof machinesContract.systemDependencies>>
  | undefined;

export type SystemDependencySnapshotState = {
  /** Raw host snapshot for consumers that need generation or host metadata. */
  snapshot: HostDependencySnapshot | undefined;
  data: MachineSystemDependencyStatus[] | undefined;
  error: Error | null;
  isLoading: boolean;
  /** Re-probes the host; the fresh snapshot streams in through the observed model. */
  refresh: () => Promise<void>;
};

/**
 * Observes the machine's dependency snapshot model. Observation alone creates the demand
 * that triggers and sustains probing (the runtime's snapshot is a kernel query with
 * revalidate-while-observed); `refresh` remains for user-initiated re-probes.
 */
export function useSystemDependencySnapshot(
  machineId: string | undefined,
  enabled: boolean
): SystemDependencySnapshotState {
  const modelKey = useMemo(() => ({ machineId }), [machineId]);
  const modelState = useRemoteModelState(
    machinesContract.systemDependencies,
    getSystemDependenciesRemote,
    modelKey,
    'current',
    { enabled }
  );
  const refresh = useCallback(() => refreshSystemDependencies(machineId), [machineId]);

  const data = useMemo(
    () => (modelState.value ? mapSystemDependencySnapshot(modelState.value) : undefined),
    [modelState.value]
  );
  const error = useMemo(() => toError(modelState.error), [modelState.error]);

  return {
    snapshot: modelState.value,
    data,
    error,
    isLoading: enabled && modelState.isLoading,
    refresh,
  };
}

async function refreshSystemDependencies(machineId: string | undefined): Promise<void> {
  const client = await getMachinesClient();
  const result = await client.systemDependencies.mutate('refresh', {
    key: { machineId },
    input: undefined,
  });
  if (!result.success) {
    throw new Error(getHostDependencyErrorMessage(result.error), { cause: result.error });
  }
}

function getSystemDependenciesRemote(): Promise<
  RemoteModel<typeof machinesContract.systemDependencies>
> {
  systemDependenciesRemotePromise ??= getMachinesClient().then((client) =>
    remote(machinesContract.systemDependencies, client.systemDependencies, {
      lingerMs: 15_000,
    })
  );
  return systemDependenciesRemotePromise;
}

function toError(error: unknown): Error | null {
  if (error === undefined) return null;
  return error instanceof Error ? error : new Error(String(error));
}

export async function resetSystemDependenciesRemoteForTests(): Promise<void> {
  const remoteModel = await systemDependenciesRemotePromise;
  systemDependenciesRemotePromise = undefined;
  await remoteModel?.dispose();
}

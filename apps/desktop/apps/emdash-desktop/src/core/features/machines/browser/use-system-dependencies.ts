import type { InstallMethod } from '@emdash/core/services/host-dependencies/api';
import { err } from '@emdash/shared';
import { toast } from '@emdash/ui/react/primitives';
import { useMutation, useMutationState } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import type {
  InstallMachineSystemDependenciesResult,
  InstallMachineSystemDependencyResult,
  MachineSystemDependencyStatus,
} from '@core/features/machines/api';
import { getHostDependencyErrorMessage } from '@core/primitives/host-dependencies/browser/error-message';
import { useDependencyOperationFailures } from '@core/primitives/host-dependencies/browser/use-dependency-operation-failures';
import type { SystemDependenciesStore } from './machines-store';
import { useSystemDependencySnapshot } from './use-system-dependency-snapshot';

const systemDependencyInstallKey = (machineId: string | undefined) =>
  ['machines', machineId, 'system-dependencies', 'install'] as const;

const systemDependencyBatchInstallKey = (machineId: string | undefined) =>
  ['machines', machineId, 'system-dependencies', 'install-batch'] as const;

type InstallVariables = {
  id: string;
  method?: InstallMethod;
  elevate?: boolean;
};

type BatchInstallVariables = {
  dependencies: InstallVariables[];
};

const selectInstallVariables = (mutation: { state: { variables?: unknown } }) =>
  mutation.state.variables as InstallVariables | undefined;

const selectBatchInstallVariables = (mutation: { state: { variables?: unknown } }) =>
  mutation.state.variables as BatchInstallVariables | undefined;

export function useSystemDependencies(
  machineId: string | undefined,
  enabled: boolean,
  machinesStore: SystemDependenciesStore
) {
  const { snapshot, data, error, isLoading, refresh } = useSystemDependencySnapshot(
    machineId,
    enabled
  );
  const failureMap = useDependencyOperationFailures();
  const installKey = systemDependencyInstallKey(machineId);
  const batchInstallKey = systemDependencyBatchInstallKey(machineId);

  const nameById = useMemo(() => {
    const names = new Map<string, string>();
    for (const dependency of data ?? []) names.set(dependency.id, dependency.name);
    return names;
  }, [data]);

  const nameOf = useCallback((id: string) => nameById.get(id) ?? id, [nameById]);

  const reportInstallResult = useCallback(
    (result: InstallMachineSystemDependencyResult, variables: InstallVariables) => {
      const name = nameOf(variables.id);
      if (result.success) {
        failureMap.clearFailure(variables.id);
        toast(`${name} successfully installed`);
        return;
      }
      if (result.error.type === 'permission-denied') {
        failureMap.setFailure(variables.id, {
          error: result.error,
          method: variables.method,
        });
        toast(`Permission denied installing ${name}`, {
          description: 'See the install panel for retry and recovery options.',
        });
        return;
      }
      failureMap.clearFailure(variables.id);
      toast.error(`Failed to install ${name}`, {
        description: getHostDependencyErrorMessage(result.error),
      });
    },
    [failureMap, nameOf]
  );

  const installMutation = useMutation<
    InstallMachineSystemDependencyResult,
    Error,
    InstallVariables
  >({
    mutationKey: installKey,
    mutationFn: async ({ id, method, elevate }) => {
      const results = await machinesStore.installSystemDependencies({
        machineId,
        dependencies: [{ id, method, elevate }],
      });
      return resultForId(results, id);
    },
    onSuccess: reportInstallResult,
    onError: (installError, variables) => {
      toast.error(`Failed to install ${nameOf(variables.id)}`, {
        description: installError.message,
      });
    },
  });

  const batchInstallMutation = useMutation<
    InstallMachineSystemDependenciesResult,
    Error,
    BatchInstallVariables
  >({
    mutationKey: batchInstallKey,
    mutationFn: async ({ dependencies }) =>
      await machinesStore.installSystemDependencies({ machineId, dependencies }),
    onSuccess: (results, variables) => {
      for (const dependency of variables.dependencies) {
        reportInstallResult(resultForId(results, dependency.id), dependency);
      }
    },
    onError: (installError) => {
      toast.error('Failed to install system dependencies', { description: installError.message });
    },
  });

  const pendingInstalls = useMutationState({
    filters: { mutationKey: installKey, status: 'pending' },
    select: selectInstallVariables,
  });
  const pendingBatchInstalls = useMutationState({
    filters: { mutationKey: batchInstallKey, status: 'pending' },
    select: selectBatchInstallVariables,
  });

  const installingIds = useMemo(() => {
    const ids = new Set<string>();
    for (const variables of pendingInstalls) {
      if (variables?.id) ids.add(variables.id);
    }
    for (const variables of pendingBatchInstalls) {
      for (const dependency of variables?.dependencies ?? []) ids.add(dependency.id);
    }
    return ids;
  }, [pendingBatchInstalls, pendingInstalls]);

  const install = useCallback(
    (id: string, method?: InstallMethod, elevate?: boolean) =>
      installMutation.mutateAsync({ id, method, elevate }),
    [installMutation]
  );

  const installAll = useCallback(
    async (dependencies: MachineSystemDependencyStatus[]) => {
      const requests = dependencies.flatMap((dependency) => {
        if (dependency.status === 'available' || dependency.installOptions.length === 0) return [];
        const option =
          dependency.installOptions.find((candidate) => candidate.recommended) ??
          dependency.installOptions[0];
        return [{ id: dependency.id, method: option?.method }];
      });
      if (requests.length === 0) return {};
      return await batchInstallMutation.mutateAsync({ dependencies: requests });
    },
    [batchInstallMutation]
  );

  return {
    snapshot,
    data,
    error,
    isLoading,
    refresh,
    install,
    installAll,
    installFailures: failureMap.failures,
    dismissInstallFailure: failureMap.clearFailure,
    installingIds,
    isInstalling: installMutation.isPending || batchInstallMutation.isPending,
  };
}

function resultForId(
  results: InstallMachineSystemDependenciesResult,
  id: string
): InstallMachineSystemDependencyResult {
  return (
    results[id] ?? err({ type: 'io', message: `Install result missing for dependency: ${id}` })
  );
}

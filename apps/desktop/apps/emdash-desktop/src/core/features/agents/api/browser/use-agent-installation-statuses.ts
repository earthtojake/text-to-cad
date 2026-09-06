import { hostRefKey, type HostRef } from '@emdash/core/primitives/host/api';
import {
  isRuntimeResolveError,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import type { Result } from '@emdash/shared';
import { toast } from '@emdash/ui/react/primitives';
import { useMutation, useMutationState, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { getAgentsClient, unwrapAgentsResult } from '@core/features/agents/api/browser/client';
import { useAgents } from '@core/features/agents/api/browser/use-agents';
import type {
  AgentInstallationStatus,
  AgentInstallError,
  AgentPayload,
  AgentUpdateError,
  AgentUninstallError,
  DependencyStatus,
  HostDependencySelection,
  Installation,
  InstallMethod,
  SelectedSource,
} from '@core/primitives/agents/api';
import {
  type DependencyOperationFailure,
  useDependencyOperationFailures,
} from '@core/primitives/host-dependencies/browser/use-dependency-operation-failures';
import { runDesktopLiveJob } from '@core/primitives/wire/browser/run-live-job';
import { agentsContract } from '../contract';
import { getAgentOperationErrorMessage } from './components/agent-selector/agent-install';

function statusQueryKey(host: HostRef) {
  return ['agents', 'status', hostRefKey(host)] as const;
}

function opKey(op: 'install' | 'update' | 'uninstall', host: HostRef) {
  return ['agents', op, hostRefKey(host)] as const;
}

type OpVars = { id: AgentProviderId; method?: InstallMethod; elevate?: boolean };
type AgentOperation = 'install' | 'update';
type AgentOperationResult = Result<AgentInstallationStatus, AgentInstallError | AgentUpdateError>;
const selectOpVars = (mutation: { state: { variables?: unknown } }) =>
  mutation.state.variables as OpVars | undefined;

export function useAgentInstallationStatuses(host: HostRef) {
  const queryClient = useQueryClient();
  const installFailureMap = useDependencyOperationFailures();
  const updateFailureMap = useDependencyOperationFailures();
  const key = statusQueryKey(host);
  const { data: agents } = useAgents(host);
  const agentNameMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents ?? []) map.set(agent.id, agent.name);
    return map;
  }, [agents]);
  const nameOf = useCallback((id: string) => agentNameMap.get(id) ?? id, [agentNameMap]);

  const query = useQuery<AgentInstallationStatus[], RuntimeResolveError>({
    queryKey: key,
    queryFn: async () =>
      unwrapAgentsResult((await getAgentsClient()).listAgentInstallationStatus({ host })),
    staleTime: 30_000,
  });

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: key });
  }, [key, queryClient]);

  const handleOperationResult = useCallback(
    (op: AgentOperation, result: AgentOperationResult, variables: OpVars) => {
      invalidate();
      const name = nameOf(variables.id);
      const failureMap = op === 'install' ? installFailureMap : updateFailureMap;
      if (result.success) {
        failureMap.clearFailure(variables.id);
        toast(`${name} successfully ${op === 'install' ? 'installed' : 'updated'}`);
        return;
      }

      const permissionError = result.error.type === 'permission-denied' ? result.error : null;
      if (permissionError) {
        failureMap.setFailure(variables.id, {
          error: permissionError,
          method: variables.method,
        });
        toast('Permission denied', {
          description: `See the ${op} panel for retry and recovery options.`,
        });
        return;
      }

      failureMap.clearFailure(variables.id);
      toast.error(`Failed to ${op} ${name}`, {
        description: getAgentOperationErrorMessage(result.error),
      });
    },
    [installFailureMap, invalidate, nameOf, updateFailureMap]
  );

  const installMutation = useMutation<
    Result<AgentInstallationStatus, AgentInstallError>,
    RuntimeResolveError,
    OpVars
  >({
    mutationKey: opKey('install', host),
    mutationFn: async ({ id, method, elevate }) => {
      const client = await getAgentsClient();
      const result = await runDesktopLiveJob(agentsContract.install, client.install, {
        host,
        id,
        method,
        elevate,
      });
      if (!result.success && isRuntimeResolveError(result.error)) throw result.error;
      return result as Result<AgentInstallationStatus, AgentInstallError>;
    },
    onSuccess: (result, variables) => handleOperationResult('install', result, variables),
    onError: (_, variables) => {
      toast.error(`Failed to install ${nameOf(variables.id)}`);
    },
  });

  const updateMutation = useMutation<
    Result<AgentInstallationStatus, AgentUpdateError>,
    RuntimeResolveError,
    OpVars
  >({
    mutationKey: opKey('update', host),
    mutationFn: async ({ id, method, elevate }) => {
      const client = await getAgentsClient();
      const result = await runDesktopLiveJob(agentsContract.update, client.update, {
        host,
        id,
        method,
        elevate,
      });
      if (!result.success && isRuntimeResolveError(result.error)) throw result.error;
      return result as Result<AgentInstallationStatus, AgentUpdateError>;
    },
    onSuccess: (result, variables) => handleOperationResult('update', result, variables),
    onError: (_, variables) => {
      toast.error(`Failed to update ${nameOf(variables.id)}`);
    },
  });

  const uninstallMutation = useMutation<
    Result<AgentInstallationStatus, AgentUninstallError>,
    RuntimeResolveError,
    { id: AgentProviderId; method?: InstallMethod }
  >({
    mutationKey: opKey('uninstall', host),
    mutationFn: async ({ id, method }) =>
      unwrapAgentsResult((await getAgentsClient()).uninstall({ host, id, method })),
    onSuccess: invalidate,
  });

  const setUsedMutation = useMutation<
    void,
    RuntimeResolveError,
    { id: string; selection: HostDependencySelection }
  >({
    mutationFn: async ({ id, selection }) =>
      unwrapAgentsResult((await getAgentsClient()).setUsedInstallation({ host, id, selection })),
    onSuccess: invalidate,
  });

  const refreshLatestMutation = useMutation<void, RuntimeResolveError, string>({
    mutationFn: async (id) =>
      unwrapAgentsResult((await getAgentsClient()).refreshLatestVersion({ host, id })),
    onSuccess: invalidate,
  });

  const probeAllMutation = useMutation<void, RuntimeResolveError, void>({
    mutationFn: async () => unwrapAgentsResult((await getAgentsClient()).probeAll({ host })),
    onSuccess: invalidate,
  });

  return {
    ...query,
    install: installMutation.mutate,
    update: updateMutation.mutate,
    uninstall: uninstallMutation.mutate,
    installFailures: installFailureMap.failures,
    updateFailures: updateFailureMap.failures,
    dismissInstallFailure: installFailureMap.clearFailure,
    dismissUpdateFailure: updateFailureMap.clearFailure,
    setUsedInstallation: setUsedMutation.mutate,
    refreshLatestVersion: refreshLatestMutation.mutate,
    probeAll: probeAllMutation.mutate,
    isInstalling: installMutation.isPending,
    isUpdating: updateMutation.isPending,
    isUninstalling: uninstallMutation.isPending,
    installingMethod: installMutation.isPending ? installMutation.variables?.method : undefined,
    updatingMethod: updateMutation.isPending ? updateMutation.variables?.method : undefined,
    uninstallingMethod: uninstallMutation.isPending
      ? uninstallMutation.variables?.method
      : undefined,
  };
}

export type HostDependencyInstallation = {
  runtimeError: RuntimeResolveError | null;
  data: AgentInstallationStatus | null;
  installations: Installation[];
  used: SelectedSource | undefined;
  status: DependencyStatus;
  isInstalling: boolean;
  isUpdating: boolean;
  isUninstalling: boolean;
  installingMethod: InstallMethod | undefined;
  updatingMethod: InstallMethod | undefined;
  uninstallingMethod: InstallMethod | undefined;
  installFailure: DependencyOperationFailure | null;
  updateFailure: DependencyOperationFailure | null;
  install(method: InstallMethod, elevate?: boolean): Promise<void>;
  update(method?: InstallMethod, elevate?: boolean): Promise<void>;
  uninstall(method?: InstallMethod): Promise<void>;
  dismissInstallFailure(): void;
  dismissUpdateFailure(): void;
  setUsed(selection: HostDependencySelection): Promise<void>;
  refresh(): Promise<void>;
  fetchLatestVersion(): Promise<void>;
  probeOverride(selection: { path?: string; cli?: string }): Promise<Installation | null>;
};

export function useAgentInstallationStatus(
  id: string,
  host: HostRef,
  agentPayload?: AgentPayload
): HostDependencyInstallation {
  const {
    data: statuses,
    error: runtimeError,
    install: installMutate,
    update: updateMutate,
    uninstall: uninstallMutate,
    installFailures,
    updateFailures,
    dismissInstallFailure,
    dismissUpdateFailure,
    setUsedInstallation,
    refreshLatestVersion,
    probeAll,
  } = useAgentInstallationStatuses(host);

  const { isPending: isInstalling, method: installingMethod } = usePendingOp('install', host, id);
  const { isPending: isUpdating, method: updatingMethod } = usePendingOp('update', host, id);
  const { isPending: isUninstalling, method: uninstallingMethod } = usePendingOp(
    'uninstall',
    host,
    id
  );
  const installFailure = installFailures[id] ?? null;
  const updateFailure = updateFailures[id] ?? null;

  const statusEntry = statuses?.find((status) => status.id === id) ?? null;
  const installations = useMemo<Installation[]>(() => {
    if (statusEntry) return statusEntry.installations;
    if (!agentPayload) return [];
    const syntheticPath = agentPayload.command;
    return [
      {
        id: syntheticPath ?? 'auto',
        realpath: syntheticPath ?? 'auto',
        pathEntry: syntheticPath,
        isActive: true,
        manageable: false,
        provenance: { kind: 'unknown', confidence: 'inferred' } as const,
        status: agentPayload.status,
        version: agentPayload.version,
        latestVersion: agentPayload.latestVersion,
        updateAvailable: agentPayload.updateAvailable,
      },
    ];
  }, [statusEntry, agentPayload]);

  const used: SelectedSource | undefined = statusEntry?.used ?? agentPayload?.used;
  const status: DependencyStatus = statusEntry?.status ?? agentPayload?.status ?? 'missing';

  const install = useCallback(
    (method: InstallMethod, elevate?: boolean) =>
      new Promise<void>((resolve) => {
        installMutate(
          { id: id as AgentProviderId, method, elevate },
          { onSettled: () => resolve() }
        );
      }),
    [installMutate, id]
  );

  const update = useCallback(
    (method?: InstallMethod, elevate?: boolean) =>
      new Promise<void>((resolve) => {
        updateMutate(
          { id: id as AgentProviderId, method, elevate },
          { onSettled: () => resolve() }
        );
      }),
    [updateMutate, id]
  );

  const uninstall = useCallback(
    (method?: InstallMethod) =>
      new Promise<void>((resolve) => {
        uninstallMutate({ id: id as AgentProviderId, method }, { onSettled: () => resolve() });
      }),
    [uninstallMutate, id]
  );

  const setUsed = useCallback(
    (selection: HostDependencySelection) =>
      new Promise<void>((resolve) => {
        setUsedInstallation({ id, selection }, { onSettled: () => resolve() });
      }),
    [setUsedInstallation, id]
  );

  const refresh = useCallback(
    () =>
      new Promise<void>((resolve) => {
        probeAll(undefined, { onSettled: () => resolve() });
      }),
    [probeAll]
  );

  const fetchLatestVersion = useCallback(
    () =>
      new Promise<void>((resolve) => {
        refreshLatestVersion(id, { onSettled: () => resolve() });
      }),
    [refreshLatestVersion, id]
  );

  const probeOverride = useCallback(
    async (selection: { path?: string; cli?: string }) =>
      unwrapAgentsResult(
        (await getAgentsClient()).probeOverride({
          host,
          id: id as AgentProviderId,
          selection,
        })
      ),
    [host, id]
  );

  return {
    runtimeError,
    data: statusEntry,
    installations,
    used,
    status,
    isInstalling,
    isUpdating,
    isUninstalling,
    installingMethod,
    updatingMethod,
    uninstallingMethod,
    installFailure,
    updateFailure,
    install,
    update,
    uninstall,
    dismissInstallFailure: () => dismissInstallFailure(id),
    dismissUpdateFailure: () => dismissUpdateFailure(id),
    setUsed,
    refresh,
    fetchLatestVersion,
    probeOverride,
  };
}

function usePendingOp(op: 'install' | 'update' | 'uninstall', host: HostRef, id: string) {
  const pending = useMutationState({
    filters: { mutationKey: opKey(op, host), status: 'pending' },
    select: selectOpVars,
  });
  const variables = pending.find((candidate) => candidate?.id === id);
  return { isPending: !!variables, method: variables?.method };
}

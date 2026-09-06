import type {
  DependencyId,
  HostDependencyOperationProgress,
  HostDependencySnapshot,
} from '@emdash/core/services/host-dependencies/node';
import { hostDependenciesContract } from '@emdash/core/services/host-dependencies/node';
import type { HostDependenciesContract } from '@emdash/core/services/host-dependencies/node';
import { runtimeResolveErrorAsError } from '@emdash/core/services/runtime-broker/api';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import type { Result } from '@emdash/shared';
import type { ContractClient } from '@emdash/wire/rpc';
import type { InstallMethod } from '@core/primitives/agents/api';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';
import { runRuntimeLiveJob } from '@core/services/runtime-clients/node/live-job';
import type { ProviderOverrideSettings } from '@core/services/settings/node/provider-settings-service';
import { toAgentUpdateError } from './agent-error-mapping';
import {
  buildAgentMetadataList,
  buildAgentPayload,
  buildAgentPayloads,
  toAgentInstallationStatus,
} from './agent-payload-builder';

export type HostDependenciesClient = ContractClient<HostDependenciesContract>;
export type AgentOperationContext = {
  signal?: AbortSignal;
  progress?: (progress: HostDependencyOperationProgress) => void;
};

export function createAgentOperations(dependencies: {
  ensureAgentDependenciesProbed(manager: HostDependenciesClient): Promise<void>;
  getDependencyManager(
    connectionId?: string
  ): Promise<Result<HostDependenciesClient, Parameters<typeof runtimeResolveErrorAsError>[0]>>;
  providerOverrideSettings: ProviderOverrideSettings;
}) {
  const { ensureAgentDependenciesProbed, getDependencyManager, providerOverrideSettings } =
    dependencies;
  return {
    // ── Metadata ────────────────────────────────────────────────────────────────

    list: async (connectionId?: string, manager?: HostDependenciesClient) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const snapshot = await snapshotFor(mgr, ensureAgentDependenciesProbed);
      return buildAgentPayloads(providerOverrideSettings, snapshot, connectionId);
    },

    get: async (id: string, connectionId?: string, manager?: HostDependenciesClient) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const snapshot = await snapshotFor(mgr, ensureAgentDependenciesProbed);
      return buildAgentPayload(providerOverrideSettings, id, snapshot, connectionId);
    },

    // ── Installation status ──────────────────────────────────────────────────────

    listAgentInstallationStatus: async (
      connectionId?: string,
      manager?: HostDependenciesClient
    ) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const snapshot = await snapshotFor(mgr, ensureAgentDependenciesProbed);
      return Object.values(snapshot.dependencies)
        .filter((view) => view.definition.category === 'agent')
        .map((view) => toAgentInstallationStatus(view.definition.id, connectionId, view));
    },

    getAgentInstallationStatus: async (
      id: string,
      connectionId?: string,
      manager?: HostDependenciesClient
    ) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const snapshot = await snapshotFor(mgr, ensureAgentDependenciesProbed);
      return toAgentInstallationStatus(id, connectionId, snapshot.dependencies[id]);
    },

    // ── Install / update ─────────────────────────────────────────────────────────

    update: async (
      id: AgentProviderId,
      connectionId?: string,
      method?: InstallMethod,
      elevate?: boolean,
      manager?: HostDependenciesClient,
      context: AgentOperationContext = {}
    ) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const result = method
        ? await runRuntimeLiveJob(
            hostDependenciesContract.runInstallCommand,
            mgr.runInstallCommand,
            { id, method, elevate, commandKind: 'update' },
            context.progress,
            { signal: context.signal }
          )
        : await runRuntimeLiveJob(
            hostDependenciesContract.runSelfUpdateCommand,
            mgr.runSelfUpdateCommand,
            { id },
            context.progress,
            { signal: context.signal }
          );
      if (result.success) {
        return {
          success: true as const,
          data: toAgentInstallationStatus(id, connectionId, result.data),
        };
      }
      return { success: false as const, error: toAgentUpdateError(result.error, id) };
    },

    install: async (
      id: AgentProviderId,
      connectionId?: string,
      method?: InstallMethod,
      elevate?: boolean,
      manager?: HostDependenciesClient,
      context: AgentOperationContext = {}
    ) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const result = await runRuntimeLiveJob(
        hostDependenciesContract.runInstallCommand,
        mgr.runInstallCommand,
        { id, method, elevate },
        context.progress,
        { signal: context.signal }
      );
      if (result.success) {
        return {
          success: true as const,
          data: toAgentInstallationStatus(id, connectionId, result.data),
        };
      }
      return { success: false as const, error: result.error };
    },

    uninstall: async (id: AgentProviderId, _connectionId?: string, _method?: InstallMethod) => ({
      success: false as const,
      error: { type: 'no-uninstall-strategy' as const, id },
    }),

    // ── Settings ─────────────────────────────────────────────────────────────────

    getDefaultSettings: async (id: string): Promise<ProviderCustomConfig> => {
      const meta = await providerOverrideSettings.getItemWithMeta(id);
      return meta.defaults;
    },

    getSettings: async (id: string) => {
      return providerOverrideSettings.getItemWithMeta(id);
    },

    updateSettings: (id: string, config: Partial<ProviderCustomConfig>): Promise<void> =>
      providerOverrideSettings.updateItem(id, config),

    // ── Selection + probe ────────────────────────────────────────────────────────

    setUsedInstallation: async (
      id: DependencyId,
      connectionId?: string,
      selection?: unknown,
      manager?: HostDependenciesClient
    ): Promise<void> => {
      // undefined = no-op; null = explicit auto (clear override)
      if (selection === undefined) return;
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      await mgr.snapshot.mutate('setSelection', {
        key: undefined,
        input: { id, selection: normalizeSelection(selection) },
      });
    },

    probe: async (id: DependencyId, connectionId?: string, manager?: HostDependenciesClient) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      const result = await mgr.snapshot.mutate('refresh', {
        key: undefined,
        input: { id },
      });
      return result.success ? result.data.data.dependencies[id] : result;
    },

    probeOverride: async (
      _id: DependencyId,
      _selection: { path?: string; cli?: string },
      _connectionId?: string
    ) => null,

    refreshLatestVersion: async (_id: DependencyId, _connectionId?: string): Promise<void> => {},

    probeAll: async (connectionId?: string, manager?: HostDependenciesClient) => {
      const mgr = await resolveDependencyManager(getDependencyManager, connectionId, manager);
      await ensureAgentDependenciesProbed(mgr);
    },

    listMetadata: async () => {
      return buildAgentMetadataList();
    },
  };
}

export type AgentOperations = ReturnType<typeof createAgentOperations>;

async function resolveDependencyManager(
  getDependencyManager: (
    connectionId?: string
  ) => ReturnType<Parameters<typeof createAgentOperations>[0]['getDependencyManager']>,
  connectionId?: string,
  manager?: HostDependenciesClient
): Promise<HostDependenciesClient> {
  if (manager) return manager;
  const result = await getDependencyManager(connectionId);
  if (!result.success) throw runtimeResolveErrorAsError(result.error);
  return result.data;
}

async function snapshotFor(
  manager: HostDependenciesClient,
  ensureProbed: (manager: HostDependenciesClient) => Promise<void>
): Promise<HostDependencySnapshot> {
  await ensureProbed(manager);
  const snapshot = await manager.snapshot.state(undefined, 'current').snapshot();
  return snapshot.data;
}

function normalizeSelection(selection: unknown): { kind: 'path'; path: string } | null {
  if (selection === null) return null;
  if (typeof selection !== 'object' || selection === null) return null;
  const candidate = selection as {
    kind?: unknown;
    path?: unknown;
    realpath?: unknown;
    command?: unknown;
  };
  if (candidate.kind === 'path' && typeof candidate.path === 'string') {
    return { kind: 'path', path: candidate.path };
  }
  if (candidate.kind === 'pinned' && typeof candidate.realpath === 'string') {
    return { kind: 'path', path: candidate.realpath };
  }
  if (
    candidate.kind === 'cli' &&
    typeof candidate.command === 'string' &&
    candidate.command.startsWith('/')
  ) {
    return { kind: 'path', path: candidate.command };
  }
  return null;
}

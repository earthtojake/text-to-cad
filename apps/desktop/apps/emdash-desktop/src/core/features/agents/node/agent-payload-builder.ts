import type {
  AgentAuthDescriptor,
  CLIAgentPluginProvider,
} from '@emdash/core/services/agent-plugins/api/plugins';
import type {
  HostDependencySnapshot,
  HostDependencyView,
} from '@emdash/core/services/host-dependencies/node';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { getPlugin, listPlugins } from '@core/features/agents/api/node/plugin-registry';
import type {
  AgentInstallationStatus,
  AgentMetadata,
  AgentPayload,
  Installation,
  SelectedSource,
} from '@core/primitives/agents/api';
import type { ProviderOverrideSettings } from '@core/services/settings/node/provider-settings-service';

function buildMetadata(provider: CLIAgentPluginProvider): AgentMetadata {
  const { metadata, capabilities, assets } = provider;
  return {
    id: metadata.id,
    name: metadata.name,
    description: metadata.description,
    websiteUrl: metadata.websiteUrl,
    icon: assets.icon,
    capabilities: {
      acp: capabilities.acp,
      auth: buildAuthDescriptor(provider),
      hostDependency: {
        updates: capabilities.hostDependency.updateCommand
          ? {
              kind: 'supported' as const,
              update: {
                kind: 'cli' as const,
                args: capabilities.hostDependency.updateCommand.args,
              },
            }
          : { kind: 'none' as const },
        uninstall: { kind: 'none' as const },
      },
      models: capabilities.models,
      effort: capabilities.effort,
      prompt: capabilities.prompt,
      sessions: capabilities.sessions,
      autoApprove: capabilities.autoApprove,
      hooks: capabilities.hooks,
      mcp: capabilities.mcp,
      plugins: capabilities.plugins,
      trust: capabilities.trust,
    },
    installDocs: capabilities.hostDependency.installDocs ?? null,
  };
}

function buildAuthDescriptor(provider: CLIAgentPluginProvider): AgentAuthDescriptor {
  const auth = provider.capabilities.auth as AgentAuthDescriptor | undefined;
  if (auth?.kind === 'supported') return auth;

  const binaryName = provider.capabilities.hostDependency.binaryNames[0] ?? provider.metadata.id;
  return {
    kind: 'supported',
    methods: [
      {
        kind: 'cli-login',
        id: 'cli-login',
        name: `Sign in with ${provider.metadata.name}`,
        args: [],
        description: `Open ${binaryName} in a terminal and complete the provider sign-in flow.`,
      },
    ],
  };
}

async function buildOne(
  providerSettings: ProviderOverrideSettings,
  id: AgentProviderId,
  snapshot?: HostDependencySnapshot,
  connectionId?: string
): Promise<AgentPayload | null> {
  const provider = getPlugin(id);
  if (!provider) return null;

  const settingsMeta = await providerSettings.getItemWithMeta(id);
  const view = snapshot?.dependencies[id];
  const used: SelectedSource = view?.selection ?? { kind: 'auto' };

  return {
    ...buildMetadata(provider),
    connectionId,
    status: view?.status ?? 'missing',
    version: null,
    latestVersion: null,
    updateAvailable: false,
    command: view?.resolved?.path ?? null,
    settings: settingsMeta,
    installOptions: view?.installOptions ?? [],
    installations: view ? installationsFromView(view) : [],
    used,
    usedId: sourceKey(used),
  };
}

export async function buildAgentPayload(
  providerSettings: ProviderOverrideSettings,
  id: string,
  snapshot?: HostDependencySnapshot,
  connectionId?: string
): Promise<AgentPayload | null> {
  return buildOne(providerSettings, id as AgentProviderId, snapshot, connectionId);
}

export async function buildAgentPayloads(
  providerSettings: ProviderOverrideSettings,
  snapshot?: HostDependencySnapshot,
  connectionId?: string
): Promise<AgentPayload[]> {
  const results = await Promise.all(
    listPlugins().map((provider) =>
      buildOne(providerSettings, provider.metadata.id as AgentProviderId, snapshot, connectionId)
    )
  );
  return results.filter((r): r is AgentPayload => r !== null);
}

export function buildAgentMetadataList(): AgentMetadata[] {
  return listPlugins().map(buildMetadata);
}

export function toAgentInstallationStatus(
  id: string,
  connectionId: string | undefined,
  view: HostDependencyView | undefined
): AgentInstallationStatus {
  const used: SelectedSource = view?.selection ?? { kind: 'auto' };
  return {
    id,
    connectionId,
    status: view?.status ?? 'missing',
    version: null,
    latestVersion: null,
    updateAvailable: false,
    command: view?.resolved?.path ?? null,
    installations: view ? installationsFromView(view) : [],
    used,
    usedId: sourceKey(used),
    installOptions: view?.installOptions ?? [],
  };
}

function installationsFromView(view: HostDependencyView): Installation[] {
  return view.candidates.map((candidate) => ({
    id: candidate.realpath,
    realpath: candidate.realpath,
    pathEntry: candidate.path,
    isActive: candidate.isPathDefault,
    manageable: false,
    provenance: { kind: 'unknown', confidence: 'inferred' },
    status: 'available',
    version: null,
    latestVersion: null,
    updateAvailable: false,
  }));
}

function sourceKey(source: SelectedSource): string {
  if (source.kind === 'auto') return 'auto';
  if (source.kind === 'pinned') return source.realpath;
  if (source.kind === 'method') return `method:${source.method}`;
  return source.kind;
}

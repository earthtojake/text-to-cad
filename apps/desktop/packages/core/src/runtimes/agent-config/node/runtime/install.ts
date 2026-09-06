import type { AgentConfigEntry, AgentConfigList } from '#runtimes/agent-config/api';
import type { AgentConfigAgentsModel } from '#runtimes/agent-config/node/state/live-models';
import { publishLiveModelState } from '#runtimes/agent-config/node/state/live-models';
import type { AgentConfigRuntimeDeps } from './types';

export class AgentInstallManager {
  private readonly providersById: Map<
    string,
    ReturnType<AgentConfigRuntimeDeps['agentHost']['getAll']>[number]
  >;
  private list: AgentConfigList = {};

  constructor(
    private readonly deps: AgentConfigRuntimeDeps,
    private readonly agentsModel: AgentConfigAgentsModel
  ) {
    const providers = deps.agentHost.getAll();
    this.providersById = new Map(providers.map((provider) => [provider.metadata.id, provider]));
    this.seedProviders();
  }

  initialize(): void {}

  updateAuth(providerId: string, auth: AgentConfigEntry['auth']): void {
    const current = this.entry(providerId);
    this.publish({
      ...this.list,
      [providerId]: { ...current, auth },
    });
  }

  getAuth(providerId: string): AgentConfigEntry['auth'] {
    return this.entry(providerId).auth;
  }

  dispose(): void {
    // The machine-scoped AgentPluginHost owns execution-context disposal through its scope.
  }

  private seedProviders(): void {
    const list: AgentConfigList = {};
    for (const provider of this.deps.agentHost.getAll()) {
      const id = provider.metadata.id;
      list[id] = {
        providerId: id,
        name: provider.metadata.name,
        auth: { status: { kind: 'unknown' }, login: null },
      };
    }
    this.publish(list);
  }

  private entry(providerId: string): AgentConfigEntry {
    const existing = this.list[providerId];
    if (existing) return existing;
    const provider = this.providersById.get(providerId);
    return {
      providerId,
      name: provider?.metadata.name ?? providerId,
      auth: { status: { kind: 'unknown' }, login: null },
    };
  }

  private publish(list: AgentConfigList): void {
    const previous = this.list;
    this.list = list;
    publishLiveModelState(this.agentsModel.states.list, list, previous);
  }
}

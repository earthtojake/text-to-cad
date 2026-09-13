import { acpApiContract } from '@emdash/core/runtimes/acp/api';
import { agentConfigContract } from '@emdash/core/runtimes/agent-config/api';
import { conversationsContract } from '@emdash/core/runtimes/conversations/api';
import { fileSearchContract } from '@emdash/core/runtimes/file-search/api';
import { filesContract } from '@emdash/core/runtimes/files/api';
import { gitContract } from '@emdash/core/runtimes/git/api';
import { hostSettingsContract } from '@emdash/core/runtimes/host-settings/api';
import { resourceUsageContract } from '@emdash/core/runtimes/resource-usage/api';
import { scriptsContract } from '@emdash/core/runtimes/scripts/api';
import { terminalsContract } from '@emdash/core/runtimes/terminals/api';
import { tuiAgentsContract } from '@emdash/core/runtimes/tui-agents/api';
import { workspaceRegistryContract } from '@emdash/core/runtimes/workspace-registry/api';
import { hostDependenciesContract } from '@emdash/core/services/host-dependencies/api';
import { client } from '@emdash/wire/rpc';
import type { Connection, Contract, ContractClient, ContractDefinitions } from '@emdash/wire/rpc';
import { createWorkspaceWireController, type WorkspaceWireControllerDeps } from '../api/controller';
import type { WorkspaceServerRuntimeClients } from '../gateway/workspace-workers';

type ControllerMetadata = Partial<
  Pick<WorkspaceWireControllerDeps, 'appVersion' | 'daemonId' | 'startedAt'>
>;

export function createTestWorkspaceWireController(
  runtimes: Partial<WorkspaceServerRuntimeClients> = {},
  metadata: ControllerMetadata = {}
) {
  return createWorkspaceWireController({
    ...metadata,
    runtimes: createTestRuntimeClients(runtimes),
    hostDependencies: createDisconnectedClient(hostDependenciesContract),
  });
}

export function createTestRuntimeClients(
  overrides: Partial<WorkspaceServerRuntimeClients> = {}
): WorkspaceServerRuntimeClients {
  return {
    acp: createDisconnectedClient(acpApiContract),
    agentConfig: createDisconnectedClient(agentConfigContract),
    conversations: createDisconnectedClient(conversationsContract),
    fileSearch: createDisconnectedClient(fileSearchContract),
    files: createDisconnectedClient(filesContract),
    git: createDisconnectedClient(gitContract),
    hostSettings: createDisconnectedClient(hostSettingsContract),
    resourceUsage: createDisconnectedClient(resourceUsageContract),
    scripts: createDisconnectedClient(scriptsContract),
    terminals: createDisconnectedClient(terminalsContract),
    tuiAgents: createDisconnectedClient(tuiAgentsContract),
    workspaceRegistry: createDisconnectedClient(workspaceRegistryContract),
    ...overrides,
  };
}

function createDisconnectedClient<Defs extends ContractDefinitions>(
  contract: Contract<Defs>
): ContractClient<Defs> {
  return client(contract, disconnectedConnection);
}

const disconnectedConnection: Connection = {
  call: async () => {
    throw new Error('Test runtime client is not connected');
  },
  openBlobConsumer: () => {
    throw new Error('Test runtime client is not connected');
  },
  openBlobProducer: () => {
    throw new Error('Test runtime client is not connected');
  },
  snapshot: async () => {
    throw new Error('Test runtime client is not connected');
  },
  attach: async () => {
    throw new Error('Test runtime client is not connected');
  },
  onDisconnect: () => () => {},
  dispose: () => {},
};

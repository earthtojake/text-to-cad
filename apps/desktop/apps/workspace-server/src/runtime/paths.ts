import { basename, dirname, join } from 'node:path';
import { daemonPaths } from '../daemon/paths';

export type WorkspaceServerRuntimePaths = {
  rootDirectory: string;
  stateDirectory: string;
  attachmentsDirectory: string;
  acpIntentsFile: string;
  tuiAgentsIntentsFile: string;
  conversationsDatabase: string;
  fileSearchDatabase: string;
  workspaceRegistryDatabase: string;
  hostDependenciesStore: string;
  hostSettingsFile: string;
};

export function workspaceServerRuntimePaths(socketPath?: string): WorkspaceServerRuntimePaths {
  const socketDirectory = dirname(daemonPaths(socketPath).socketPath);
  const rootDirectory =
    basename(socketDirectory) === 'run' ? dirname(socketDirectory) : socketDirectory;
  const stateDirectory = join(rootDirectory, 'state');

  return {
    rootDirectory,
    stateDirectory,
    attachmentsDirectory: join(stateDirectory, 'acp-attachments'),
    acpIntentsFile: join(stateDirectory, 'acp-session-intents.json'),
    tuiAgentsIntentsFile: join(stateDirectory, 'tui-agent-session-intents.json'),
    conversationsDatabase: join(stateDirectory, 'conversations.db'),
    fileSearchDatabase: join(stateDirectory, 'file-search.db'),
    workspaceRegistryDatabase: join(stateDirectory, 'workspace-registry.db'),
    hostDependenciesStore: join(stateDirectory, 'host-dependencies.json'),
    hostSettingsFile: join(stateDirectory, 'host-settings.json'),
  };
}

import { defineContract } from '@emdash/wire/rpc';
import { acpApiContract } from '../../../runtimes/acp/api';
import { agentConfigContract } from '../../../runtimes/agent-config/api';
import { conversationsContract } from '../../../runtimes/conversations/api';
import { fileSearchContract } from '../../../runtimes/file-search/api';
import { filesContract } from '../../../runtimes/files/api';
import { gitContract } from '../../../runtimes/git/api';
import { hostSettingsContract } from '../../../runtimes/host-settings/api';
import { resourceUsageContract } from '../../../runtimes/resource-usage/api';
import { scriptsContract } from '../../../runtimes/scripts/api';
import { terminalsContract } from '../../../runtimes/terminals/api';
import { tuiAgentsContract } from '../../../runtimes/tui-agents/api';
import { workspaceRegistryContract } from '../../../runtimes/workspace-registry/api';
import { hostDependenciesContract } from '../../host-dependencies/api';

/**
 * Raw host-scoped runtime surface. Desktop slice controllers adapt this
 * contract to app-id-keyed renderer contracts; it is never exposed directly.
 *
 * Scoping notes:
 * - `fs-watch` is a private intra-worker dependency, not a host runtime.
 * - `mementos` and `pull-requests` are app-scoped desktop workers keyed by
 *   `userData` databases, not by host, and are intentionally excluded.
 */
export const hostRuntimesDefinitions = {
  git: gitContract,
  fileSearch: fileSearchContract,
  files: filesContract,
  acp: acpApiContract,
  conversations: conversationsContract,
  tuiAgents: tuiAgentsContract,
  agentConfig: agentConfigContract,
  terminals: terminalsContract,
  workspaceRegistry: workspaceRegistryContract,
  resourceUsage: resourceUsageContract,
  hostDependencies: hostDependenciesContract,
  hostSettings: hostSettingsContract,
  scripts: scriptsContract,
} as const;

export const hostRuntimesContract = defineContract(hostRuntimesDefinitions);

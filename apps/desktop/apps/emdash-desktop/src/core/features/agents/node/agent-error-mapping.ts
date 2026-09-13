import type { HostDependencyError } from '@emdash/core/primitives/host-dependencies/api';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import type { AgentUpdateError } from '@core/primitives/agents/api';

export function toAgentUpdateError(
  error: HostDependencyError,
  id: AgentProviderId
): AgentUpdateError {
  switch (error.type) {
    case 'not-detected-after-install':
    case 'missing':
      return { type: 'not-detected-after-update', id };
    case 'no-update-command':
    case 'no-install-command':
      return { type: 'no-update-strategy', id };
    default:
      return error;
  }
}

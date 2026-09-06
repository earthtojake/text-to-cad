import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { acquireWorkspaceRuntime } from '@core/features/workspaces/api/node/runtime-access';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';

export function createDesktopWorkspaceRuntimeAcquirer(
  runtimes: RuntimeBroker,
  workspaceIdentity: WorkspaceIdentityService
) {
  return (workspaceId: string) => acquireWorkspaceRuntime(runtimes, workspaceIdentity, workspaceId);
}

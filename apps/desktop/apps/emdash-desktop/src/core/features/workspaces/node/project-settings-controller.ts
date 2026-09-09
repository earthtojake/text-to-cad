import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import {
  acquireWorkspaceRuntime,
  type WorkspaceRuntimeIdentityResolver,
} from '@core/features/workspaces/api/node/runtime-access';
import type { ProjectSettingsLoadResult } from '@core/primitives/project-settings/api';

export function createProjectSettingsOperations(dependencies: {
  runtimes: RuntimeBroker;
  workspaceIdentity: WorkspaceRuntimeIdentityResolver;
}) {
  async function getSettings(workspaceId: string): Promise<ProjectSettingsLoadResult> {
    const workspace = await acquireWorkspaceRuntime(
      dependencies.runtimes,
      dependencies.workspaceIdentity,
      workspaceId
    );
    if (!workspace) {
      return err({ type: 'not_found', entity: 'workspace', workspaceId });
    }

    const config = await workspace.client.workspaceRegistry.getProjectConfig({ workspaceId });
    if (!config.success) {
      return err({ type: 'not_found', entity: 'workspace', workspaceId });
    }
    const resolved = config.data.resolved;
    return ok({
      scripts: {
        prepare: resolved.prepare?.value,
        setup: resolved.setup?.value,
        run: resolved.run?.value,
        teardown: resolved.teardown?.value,
      },
      ...(resolved.shellSetup ? { shellSetup: resolved.shellSetup.value } : {}),
    });
  }

  return { getSettings };
}

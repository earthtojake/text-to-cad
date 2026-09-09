import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import type { Scope } from '@emdash/shared/concurrency';
import { createController, type Controller } from '@emdash/wire/rpc';
import { expose, family, query } from '@emdash/wire/state';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import type { HostWorkspaceGroupsData } from '@core/primitives/workspaces/api';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projectSettingsContract, projectWorkspacesContract } from '../api';
import type { WorkspaceGroupsHostKey } from './operations/list-host-workspace-groups';
import { createProjectSettingsOperations } from './project-settings-controller';
import {
  createProjectWorkspaceOperations,
  type ProjectWorkspaceOperationDependencies,
} from './project-workspaces-controller';

export function createProjectSettingsWireController(dependencies: {
  runtimes: RuntimeBroker;
  workspaceIdentity: WorkspaceIdentityService;
}): Controller {
  const projectSettingsOperations = createProjectSettingsOperations(dependencies);
  return createController(projectSettingsContract, {
    getSettings: ({ workspaceId }) => projectSettingsOperations.getSettings(workspaceId),
  });
}

export type ProjectWorkspacesWireController = {
  controller: Controller;
  dispose(): Promise<void>;
};

/**
 * Mirror-served workspace groups as a live model (planning ticket 09): the registry
 * sync pokes `appDbPokes.workspaces` on every applied snapshot, so the family
 * re-queries the mirror and streams updates — the renderer never polls.
 */
export function createProjectWorkspacesWireController(
  dependencies: ProjectWorkspaceOperationDependencies
): ProjectWorkspacesWireController {
  const projectWorkspaceOperations = createProjectWorkspaceOperations(dependencies);

  const groupsFamily = family(
    ({ hostKey }: { hostKey: string }, scope) =>
      query<HostWorkspaceGroupsData>({
        fetch: () =>
          projectWorkspaceOperations.listHostWorkspaceGroups(hostKey as WorkspaceGroupsHostKey),
        pokes: [
          appDbPokes.workspaces.subscription(() => true),
          appDbPokes.tasks.subscription(() => true),
          appDbPokes.projects.subscription(() => true),
        ],
        scope,
      }),
    { name: 'workspace-groups' }
  );

  const groupsProvider = expose(projectWorkspacesContract.workspaceGroups, {
    list: (key: { hostKey: string }, scope: Scope) => {
      scope.add(groupsFamily.retain(key));
      return groupsFamily(key);
    },
  });

  return {
    controller: createController(projectWorkspacesContract, {
      workspaceGroups: groupsProvider,
      measureProjectWorkspaces: (input) =>
        projectWorkspaceOperations.measureProjectWorkspaces(input),
      deleteProjectWorkspaces: (input) => projectWorkspaceOperations.deleteProjectWorkspaces(input),
    }),
    async dispose() {
      await groupsProvider.dispose();
      await groupsFamily.dispose();
    },
  };
}

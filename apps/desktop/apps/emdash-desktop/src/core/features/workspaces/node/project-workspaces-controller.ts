import { PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE } from '@core/features/projects/api/attachments';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { TaskService } from '@core/features/tasks/api/node/task-service';
import { deleteProjectWorkspaces } from './operations/delete-project-workspaces';
import {
  listHostWorkspaceGroups,
  type WorkspaceGroupsHostKey,
} from './operations/list-host-workspace-groups';
import type { ListProjectWorkspacesDependencies } from './operations/list-project-workspaces';
import { measureProjectWorkspaces } from './operations/measure-project-workspaces';

export type ProjectWorkspaceOperationDependencies = ListProjectWorkspacesDependencies & {
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
  taskService: Pick<TaskService, 'deleteTask'>;
};

export function createProjectWorkspaceOperations(
  dependencies: ProjectWorkspaceOperationDependencies
) {
  return {
    listHostWorkspaceGroups: (hostKey: WorkspaceGroupsHostKey) =>
      listHostWorkspaceGroups(dependencies, hostKey),
    measureProjectWorkspaces: (input: Parameters<typeof measureProjectWorkspaces>[1]) => {
      const attached = dependencies.projects.requireAttached(input.projectId);
      if (attached.success) return measureProjectWorkspaces(dependencies, input);
      const message =
        attached.error.type === 'project-missing'
          ? 'Project was not found.'
          : PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE;
      return Promise.resolve({
        scannedAt: new Date().toISOString(),
        projectId: input.projectId,
        results: input.paths.map((path) => ({ path, success: false as const, message })),
      });
    },
    deleteProjectWorkspaces: (input: Parameters<typeof deleteProjectWorkspaces>[1]) => {
      const attached = dependencies.projects.requireAttached(input.projectId);
      if (attached.success) return deleteProjectWorkspaces(dependencies, input);
      const projectMissing = attached.error.type === 'project-missing';
      return Promise.resolve({
        succeededCount: 0,
        failedCount: input.paths.length,
        results: input.paths.map((path) => ({
          path,
          success: false as const,
          reason: projectMissing ? ('project-missing' as const) : ('project-unavailable' as const),
          message: projectMissing ? 'Project was not found.' : PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
        })),
      });
    },
  };
}

import type { HostRef } from '@emdash/core/primitives/host/api';
import type { GitCredentialsService } from '@core/features/github/api/node/services/git-credentials-service';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectSettingsService } from '@core/features/projects/api/node/settings/project-settings-service';
import type { ProjectSettingsDomainPatch } from '@core/features/projects/api/project-settings-page';
import type { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import type {
  MigrateProjectConfigRequest,
  WriteProjectConfigRequest,
} from '@core/primitives/project-settings/api';
import type { CreateProjectDependencies } from './operations/create-project';
import { createProject, inspectProjectPath } from './operations/create-project';
import { deleteProject, type ProjectDeletionDependencies } from './operations/deleteProject';
import { ensureDefaultRepositoriesRoot } from './operations/ensure-default-repositories-root';
import { getProjects } from './operations/getProjects';
import { initializeRepository } from './operations/initialize-repository';
import { resolveRepositoryDestination } from './operations/resolve-repository-destination';
import { updateProjectConnection } from './operations/updateProjectConnection';
import { countProjectsUsingGithubAccount } from './settings/count-projects-using-github-account';

export type ProjectOperationDependencies = CreateProjectDependencies & {
  placement: WorkspacePlacementResolver;
  projectDeletion: ProjectDeletionDependencies;
  projectSettings: ProjectSettingsService;
  projects: Pick<ProjectAttachmentManager, 'invalidate' | 'recover' | 'track'>;
  mintCloneCredentials: GitCredentialsService['mintCloneCredentials'];
};

export function createProjectOperations(dependencies: ProjectOperationDependencies) {
  const { db, placement, projectDeletion, projectSettings, projects } = dependencies;
  return {
    createProject: (params: Parameters<typeof createProject>[1]) =>
      createProject(dependencies, params),
    inspectProjectPath: (params: Parameters<typeof inspectProjectPath>[1]) =>
      inspectProjectPath(dependencies, params),
    initializeRepository: (projectId: string) => initializeRepository(dependencies, projectId),
    resolveRepositoryDestination: (input: Parameters<typeof resolveRepositoryDestination>[1]) =>
      resolveRepositoryDestination(placement, input),
    getDefaultRepositoriesRoot: (host: HostRef) => placement.resolveRepositoriesRoot(host),
    ensureDefaultRepositoriesRoot: (host: HostRef) =>
      ensureDefaultRepositoriesRoot(dependencies, host),
    getProjects: () => getProjects(db),
    deleteProject: async (projectId: string) => {
      const result = await deleteProject(projectDeletion, projectId);
      if (!result.success && result.error.type !== 'project-not-found') {
        throw new Error(result.error.message);
      }
    },
    getProjectSettingsPage: (projectId: string) =>
      projectSettings.getProjectSettingsPage(projectId),
    updateProjectSettings: (projectId: string, patch: ProjectSettingsDomainPatch) =>
      projectSettings.updateProjectSettings(projectId, patch),
    shareProjectSettingsToConfig: (projectId: string, request: WriteProjectConfigRequest) =>
      projectSettings.shareProjectSettingsToConfig(projectId, request),
    migrateProjectConfig: (projectId: string, request: MigrateProjectConfigRequest) =>
      projectSettings.migrateProjectConfig(projectId, request),
    countProjectsUsingGithubAccount: (accountId: string) =>
      countProjectsUsingGithubAccount(db, accountId),
    updateProjectConnection: (projectId: string, connectionId: string) =>
      updateProjectConnection(db, dependencies.runtimes, projects, projectId, connectionId),
  };
}

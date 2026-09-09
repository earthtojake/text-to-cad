import { createController, type Controller } from '@emdash/wire/rpc';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import { repositoryContract } from '../api';
import { ProviderRepositoryService } from './provider-repository-service';

export function createRepositoryWireController(dependencies: {
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
  loadProject(projectId: string): Promise<unknown | undefined>;
}): Controller {
  const providerRepositoryService = new ProviderRepositoryService({
    projects: dependencies.projects,
    loadProject: dependencies.loadProject,
  });
  return createController(repositoryContract, {
    resolveProvider: ({ projectId }) => providerRepositoryService.resolveProject(projectId),
  });
}

import {
  projectSettingsStoreToken,
  type ProjectScopedStoreContext,
} from '@core/features/projects/contributions/project-stores';
import { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import { taskManagerStoreToken } from '@core/features/tasks/contributions/browser/project-store-tokens';
import {
  contributeScopedStore,
  scopedStoreToken,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';
import { TaskPrSyncCoordinator } from '../../browser/stores/task-pr-sync-coordinator';

export const gitRepositoryStoreToken = scopedStoreToken<GitRepositoryStore>(
  'source-control.repository'
);
export const taskPrSyncCoordinatorToken = scopedStoreToken<TaskPrSyncCoordinator>(
  'source-control.task-pr-sync'
);

export const sourceControlProjectStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: gitRepositoryStoreToken,
      create: ({ project, host }, stores) =>
        new GitRepositoryStore(project.id, stores.get(projectSettingsStoreToken), host),
      activate: (store) => store.start(),
      dispose: (store) => store.dispose(),
    }),
  ];

export const sourceControlTaskProjectStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: taskPrSyncCoordinatorToken,
      create: (_context, stores) =>
        new TaskPrSyncCoordinator(
          stores.get(taskManagerStoreToken),
          stores.get(gitRepositoryStoreToken)
        ),
      dispose: (coordinator) => coordinator.dispose(),
    }),
  ];

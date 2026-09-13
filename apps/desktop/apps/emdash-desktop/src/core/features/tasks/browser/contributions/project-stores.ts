import {
  projectSettingsStoreToken,
  type ProjectScopedStoreContext,
} from '@core/features/projects/contributions/project-stores';
import { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import { taskManagerStoreToken } from '@core/features/tasks/contributions/browser/project-store-tokens';
import {
  contributeScopedStore,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

export const taskProjectScopedStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: taskManagerStoreToken,
      create: ({ project, host }, stores) =>
        new TaskManagerStore(project.id, stores.get(projectSettingsStoreToken), host, stores),
      dispose: (store) => store.dispose(),
    }),
  ];

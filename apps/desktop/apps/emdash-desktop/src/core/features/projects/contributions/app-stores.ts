import { ProjectManagerStore } from '@core/features/projects/api/browser/stores/project-manager';
import { projectManagerStoreToken } from '@core/features/projects/contributions/app-store-tokens';
import type { ProjectScopedStoreContext } from '@core/features/projects/contributions/project-stores';
import {
  contributeScopedStore,
  type AppScopedStoreContribution,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

export function createProjectsAppStoreContributions(
  projectStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[]
): readonly AppScopedStoreContribution[] {
  return [
    contributeScopedStore({
      token: projectManagerStoreToken,
      create: () => new ProjectManagerStore(projectStoreContributions),
      dispose: (store) => store.dispose(),
    }),
  ];
}

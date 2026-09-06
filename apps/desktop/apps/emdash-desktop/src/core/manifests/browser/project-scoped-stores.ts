import {
  projectScopedStoreContributions,
  type ProjectScopedStoreContext,
} from '@core/features/projects/contributions/project-stores';
import {
  sourceControlProjectStoreContributions,
  sourceControlTaskProjectStoreContributions,
} from '@core/features/source-control/contributions/browser/project-stores';
import { taskProjectScopedStoreContributions } from '@core/features/tasks/browser/contributions/project-stores';
import type { ScopedStoreContribution } from '@core/primitives/scoped-stores/browser';

export const projectStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[] =
  [
    ...projectScopedStoreContributions,
    ...sourceControlProjectStoreContributions,
    ...taskProjectScopedStoreContributions,
    ...sourceControlTaskProjectStoreContributions,
  ];

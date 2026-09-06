import type { ProjectHostAccess } from '@core/features/projects/api/browser/stores/project-context';
import { ProjectSettingsStore } from '@core/features/projects/api/browser/stores/project-settings-store';
import {
  workspaceChromeStore,
  type WorkspaceChromeStore,
} from '@core/features/projects/api/browser/stores/workspace-chrome-store';
import { createChromeStore } from '@core/primitives/chrome-stores/browser';
import type { SubjectSpace } from '@core/primitives/mementos/browser';
import type { Project } from '@core/primitives/projects/api';
import {
  contributeScopedStore,
  scopedStoreToken,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';
import { ProjectViewStore } from '../browser/stores/project-view';
import { projectViewMemento } from './mementos';

export type ProjectScopedStoreContext = Readonly<{
  project: Project;
  space: SubjectSpace<'project'>;
  host: ProjectHostAccess;
}>;

export const projectViewStoreToken = scopedStoreToken<ProjectViewStore>('projects.view');
export const projectSettingsStoreToken =
  scopedStoreToken<ProjectSettingsStore>('projects.settings');
export const workspaceChromeStoreToken = scopedStoreToken<WorkspaceChromeStore>(
  'projects.workspace-chrome'
);

export const projectScopedStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: projectViewStoreToken,
      create: ({ space }) => new ProjectViewStore(space.handle(projectViewMemento)),
    }),
    contributeScopedStore({
      token: projectSettingsStoreToken,
      create: ({ project, host }) => new ProjectSettingsStore(project.id, host),
      dispose: (store) => store.dispose(),
    }),
    contributeScopedStore({
      token: workspaceChromeStoreToken,
      create: ({ space }) => createChromeStore(workspaceChromeStore, space),
    }),
  ];

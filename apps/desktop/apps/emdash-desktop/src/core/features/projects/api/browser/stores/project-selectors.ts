import {
  isUnregisteredProject,
  type ProjectStore,
} from '@core/features/projects/api/browser/stores/project';
import type {
  ProjectContext,
  ProjectHostAccess,
} from '@core/features/projects/api/browser/stores/project-context';
import type { ProjectManagerStore } from '@core/features/projects/api/browser/stores/project-manager';
import type { ProjectSettingsStore } from '@core/features/projects/api/browser/stores/project-settings-store';
import { projectManagerStoreToken } from '@core/features/projects/contributions/app-store-tokens';
import {
  projectSettingsStoreToken,
  projectViewStoreToken,
} from '@core/features/projects/contributions/project-stores';
import type { LocalProject, SshProject } from '@core/primitives/projects/api';
import { getAppStores } from '@core/primitives/scoped-stores/browser';
import type { ProjectViewStore } from '../../../browser/stores/project-view';

/** Returns the app-scoped ProjectManagerStore. Call only inside `observer` components (or other MobX reactions). */
export function getProjectManagerStore(): ProjectManagerStore {
  return getAppStores().get(projectManagerStoreToken);
}

/** Call only inside `observer` components (or other MobX reactions). */
export function getProjectStore(projectId: string): ProjectStore | undefined {
  return getProjectManagerStore().projects.get(projectId);
}

/** Summary for routing the project shell; call only inside `observer` (or other MobX reactions). */
export type ProjectViewKind = 'missing' | 'creating' | 'hydrating' | 'context_error' | 'ready';

export function projectViewKind(store: ProjectStore | undefined): ProjectViewKind {
  if (!store) return 'missing';
  if (isUnregisteredProject(store)) return 'creating';
  if (!store.context || store.context.kind === 'hydrating') return 'hydrating';
  if (store.context.kind === 'failed') return 'context_error';
  return 'ready';
}

/** Returns the desktop Project context when hydration has completed. */
export function asAvailableProject(store: ProjectStore | undefined): ProjectContext | undefined {
  return store?.context?.kind === 'available' ? store.context.context : undefined;
}

/** Returns the single project-owned seam for live Host access. */
export function getProjectHostAccess(projectId: string): ProjectHostAccess | undefined {
  return asAvailableProject(getProjectStore(projectId))?.host;
}

/** Returns the id of the first Project with an available desktop context. */
export function firstAvailableProjectId(): string | undefined {
  for (const [id, store] of getProjectManagerStore().projects.entries()) {
    if (asAvailableProject(store)) return id;
  }
  return undefined;
}

export function projectData(store: ProjectStore | undefined): LocalProject | SshProject | null {
  return store?.data ?? null;
}

/** Returns the SSH connection id for an SSH Project, otherwise undefined. */
export function getProjectSshConnectionId(projectId: string): string | undefined {
  const data = projectData(getProjectStore(projectId));
  return data?.type === 'ssh' ? data.connectionId : undefined;
}

/** Returns the display name from any project store variant. */
export function projectDisplayName(store: ProjectStore | undefined): string | undefined {
  return store?.name ?? undefined;
}

/** Returns the ProjectSettingsStore for an available Project context. */
export function getProjectSettingsStore(projectId: string): ProjectSettingsStore | undefined {
  return asAvailableProject(getProjectStore(projectId))?.get(projectSettingsStoreToken);
}

/** Returns the ProjectViewStore for an available Project context. */
export function getProjectViewStore(projectId: string): ProjectViewStore | undefined {
  return asAvailableProject(getProjectStore(projectId))?.get(projectViewStoreToken);
}

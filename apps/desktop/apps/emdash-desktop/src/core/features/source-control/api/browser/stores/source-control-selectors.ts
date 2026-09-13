import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import type { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import { gitRepositoryStoreToken } from '@core/features/source-control/contributions/browser/project-stores';
import {
  diffTabManagerStoreToken,
  gitCheckoutStoreToken,
} from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import { workspaceRegistry } from '@core/features/workspaces/api/browser/stores/workspace-registry';
import type { DiffTabManager } from '../../../browser/diff-view/stores/diff-tab-manager';
import type { GitCheckoutStore } from '../../../browser/stores/git-checkout-store';

/** Call only inside `observer` components (or other MobX reactions). */
export function getGitRepositoryStore(projectId: string): GitRepositoryStore | undefined {
  return asAvailableProject(getProjectStore(projectId))?.get(gitRepositoryStoreToken);
}

/** Call only inside `observer` components (or other MobX reactions). */
export function getGitCheckoutStore(workspaceId: string): GitCheckoutStore | undefined {
  return workspaceRegistry.get(workspaceId)?.get(gitCheckoutStoreToken);
}

export function getDiffTabManagerStore(workspaceId: string): DiffTabManager | undefined {
  return workspaceRegistry.get(workspaceId)?.get(diffTabManagerStoreToken);
}

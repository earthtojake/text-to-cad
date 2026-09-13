import type { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import { LifecycleScriptsStore } from '@core/features/workspaces/api/browser/lifecycle-scripts';
import {
  contributeScopedStore,
  scopedStoreToken,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

export type WorkspaceScopedStoreContext = Readonly<{
  projectId: string;
  workspaceId: string;
  path: string;
  gitRepository: GitRepositoryStore;
  sshConnectionId?: string;
}>;

export const lifecycleScriptsStoreToken = scopedStoreToken<LifecycleScriptsStore>(
  'workspaces.lifecycle-scripts'
);

export const workspacesScopedStoreContributions: readonly ScopedStoreContribution<WorkspaceScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: lifecycleScriptsStoreToken,
      create: ({ projectId, workspaceId, path, sshConnectionId }) =>
        new LifecycleScriptsStore(projectId, workspaceId, path, sshConnectionId),
      dispose: (store) => store.dispose(),
    }),
  ];

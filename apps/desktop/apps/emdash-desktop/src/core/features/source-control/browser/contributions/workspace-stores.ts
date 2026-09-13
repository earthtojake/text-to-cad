import {
  diffTabManagerStoreToken,
  gitCheckoutStoreToken,
} from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import type { WorkspaceScopedStoreContext } from '@core/features/workspaces/contributions/browser/workspace-stores';
import {
  contributeScopedStore,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';
import { DiffTabManager } from '../diff-view/stores/diff-tab-manager';
import { GitCheckoutStore } from '../stores/git-checkout-store';

export const sourceControlWorkspaceStoreContributions: readonly ScopedStoreContribution<WorkspaceScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: gitCheckoutStoreToken,
      create: ({ projectId, workspaceId, path, sshConnectionId }) =>
        new GitCheckoutStore(projectId, workspaceId, path, sshConnectionId),
      activate: (store) => store.start(),
      dispose: (store) => store.dispose(),
    }),
    contributeScopedStore({
      token: diffTabManagerStoreToken,
      create: () => new DiffTabManager(),
      dispose: (store) => store.dispose(),
    }),
  ];

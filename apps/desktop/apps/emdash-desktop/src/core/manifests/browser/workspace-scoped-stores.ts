import { sourceControlWorkspaceStoreContributions } from '@core/features/source-control/browser/contributions/workspace-stores';
import {
  workspacesScopedStoreContributions,
  type WorkspaceScopedStoreContext,
} from '@core/features/workspaces/contributions/browser/workspace-stores';
import type { ScopedStoreContribution } from '@core/primitives/scoped-stores/browser';

export const workspaceStoreContributions: readonly ScopedStoreContribution<WorkspaceScopedStoreContext>[] =
  [...sourceControlWorkspaceStoreContributions, ...workspacesScopedStoreContributions];

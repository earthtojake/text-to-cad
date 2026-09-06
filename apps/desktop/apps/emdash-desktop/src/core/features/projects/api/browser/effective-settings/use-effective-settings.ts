import { useGitHubAccounts } from '@core/features/github/api/browser/useGithubAccounts';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import {
  resolveEffectiveSettings,
  type EffectiveSettings,
  type PlacementContext,
  type RepoFacts,
  type StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';
import { getProjectSettingsStore } from '../stores/project-selectors';

/**
 * Renderer-side inputs for the blessed resolver (spec: github-git-settings
 * §2): stored explicit choices, repo facts from the synced repository live
 * model, and the connected GitHub accounts. Surfaces that preview a pending
 * (unsaved) choice re-run `resolveRendererEffectiveSettings` with their own
 * stored settings over the same facts.
 */
export type EffectiveSettingsInputs = {
  storedGitSettings: StoredProjectGitSettings;
  repoFacts: RepoFacts;
  accounts: GitHubAccountSummary[];
  /**
   * Placement layers shipped node-side over the Wire so preview and execution
   * resolve identical worktree-root and tmux inputs.
   */
  placementContext: PlacementContext;
};

export function resolveRendererEffectiveSettings(
  inputs: EffectiveSettingsInputs,
  storedGitSettings: StoredProjectGitSettings = inputs.storedGitSettings
): EffectiveSettings {
  return resolveEffectiveSettings(
    {
      project: storedGitSettings,
      hostWorktreeRoot: inputs.placementContext.hostWorktreeRoot,
      builtInWorktreeRoot: inputs.placementContext.builtInWorktreeRoot,
      homeDirectory: inputs.placementContext.homeDirectory,
    },
    inputs.repoFacts,
    inputs.accounts
  );
}

/**
 * Resolver inputs from the synced stores. Call only inside `observer`
 * components (or other MobX reactions). Returns null while the settings
 * page, the repository model, or the accounts list is still loading; a
 * repository that failed to load degrades to empty repo facts.
 */
export function useEffectiveSettingsInputs(projectId: string): EffectiveSettingsInputs | null {
  const settingsStore = getProjectSettingsStore(projectId);
  const repo = getGitRepositoryStore(projectId);
  const { data: accounts } = useGitHubAccounts();
  const domains = settingsStore?.domains ?? null;
  if (!domains || !accounts) return null;
  if (repo?.loading) return null;
  return {
    storedGitSettings: {
      ...domains.gitIdentity.stored,
      ...domains.placement.stored,
    },
    repoFacts: repo?.repoFacts ?? { remotes: [], localBranches: [] },
    accounts,
    placementContext: domains.placement.layers,
  };
}

/**
 * The effective per-project git settings with provenance, resolved by the
 * same portable function node execution uses. Call only inside `observer`
 * components. Returns null while inputs are loading.
 */
export function useEffectiveSettings(projectId: string): EffectiveSettings | null {
  const inputs = useEffectiveSettingsInputs(projectId);
  return inputs ? resolveRendererEffectiveSettings(inputs) : null;
}

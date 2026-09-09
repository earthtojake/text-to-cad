import type { GitHubAccountSummary } from '@core/primitives/github/api';
import {
  resolveEffectiveSettings,
  type RepoFacts,
  type Resolved,
  type StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';
import type { Project } from '@core/primitives/projects/api';

/**
 * The GitHub account a project's API calls run as, straight from the blessed
 * resolver (spec: github-git-settings §2, §7). There is no error vocabulary
 * here — consumers speak the resolver's provenance directly:
 *
 * - a value with `set` provenance is an explicit pin; with `inferred`, the
 *   host-matching inference;
 * - `null` with `set` provenance is the explicit "GitHub disabled" intent;
 * - `null` with `inferred` provenance means inference found nothing;
 * - `null` with `unresolvable` provenance is a dangling or host-mismatched
 *   pin — fail closed, never another identity.
 */
export type ProjectGitHubAccountResolution = Resolved<GitHubAccountSummary | null>;

export type ProjectGitHubAccountResolver = (
  projectId: string
) => Promise<ProjectGitHubAccountResolution>;

export function createProjectGitHubAccountResolver(deps: {
  getProjectById(projectId: string): Promise<Project | undefined>;
  getStoredGitSettings(projectId: string): Promise<StoredProjectGitSettings>;
  getRepoFacts(project: Project): Promise<RepoFacts | null>;
  listAccounts(): Promise<GitHubAccountSummary[]>;
}): ProjectGitHubAccountResolver {
  return async (projectId) => {
    const project = await deps.getProjectById(projectId);
    if (!project) {
      throw new Error(`Project ${projectId} does not exist.`);
    }
    const [stored, repoFacts, accounts] = await Promise.all([
      deps.getStoredGitSettings(projectId),
      deps.getRepoFacts(project),
      deps.listAccounts(),
    ]);
    const effective = resolveEffectiveSettings(
      { project: stored, builtInWorktreeRoot: '' },
      repoFacts ?? { remotes: [], localBranches: [] },
      accounts
    );
    return effective.githubAccount;
  };
}

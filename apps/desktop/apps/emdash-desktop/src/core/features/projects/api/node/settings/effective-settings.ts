import { log } from '@emdash/shared/logger';
import { eq } from 'drizzle-orm';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import {
  resolveEffectiveSettings,
  type EffectiveSettings,
  type PlacementContext,
  type RepoFacts,
  type StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { projectSettings } from '@core/services/app-db/node/schema';
import { legacyBaseProjectSettingsSchema } from '../../../node/settings/migrations/legacy-stored-project-settings';
import { migrateStoredBaseProjectSettings } from '../../../node/settings/migrations/stored-settings';

/**
 * The per-project repo-facts cache surface (spec: github-git-settings §2):
 * `null` means the facts are unavailable right now (degrade/skip and retry
 * later), never "the repository has no remotes".
 */
export type RepoFactsSource = {
  get(): Promise<RepoFacts | null>;
  dispose(): Promise<void>;
};

export type ProjectEffectiveSettingsSource = {
  getStoredGitSettings(): Promise<StoredProjectGitSettings>;
  getPlacementContext(): Promise<PlacementContext>;
};

export type ResolveProjectEffectiveSettingsOptions = {
  settings: ProjectEffectiveSettingsSource;
  repoFacts: RepoFactsSource;
  /**
   * Connected GitHub accounts for the account chain. Callers that only read
   * remotes/branches may omit this; the resolved `githubAccount` is
   * meaningless then and must not be consumed.
   */
  accounts?: GitHubAccountSummary[];
  /** Included in degrade warnings. */
  projectId?: string;
};

/**
 * Node-side entry to the blessed resolver (spec: github-git-settings §2):
 * every execution flow resolves effective values through this seam — stored
 * choices from the one settings provider, live facts from the per-project
 * repo-facts cache, accounts from the provider-account registry. No fallback
 * literals or ad-hoc default-account lookups may exist outside of it.
 *
 * Broken settings degrade inside the resolver (stale remote/branch → inferred
 * fallback) and are logged here once, so every flow warns consistently.
 */
export async function resolveProjectEffectiveSettings(
  options: ResolveProjectEffectiveSettingsOptions
): Promise<EffectiveSettings> {
  const [stored, facts, placementContext] = await Promise.all([
    options.settings.getStoredGitSettings(),
    options.repoFacts.get(),
    options.settings.getPlacementContext(),
  ]);
  const effective = resolveEffectiveSettings(
    {
      project: stored,
      hostWorktreeRoot: placementContext.hostWorktreeRoot,
      builtInWorktreeRoot: placementContext.builtInWorktreeRoot,
      homeDirectory: placementContext.homeDirectory,
    },
    facts ?? { remotes: [], localBranches: [] },
    options.accounts ?? []
  );
  warnAboutBrokenSettings(effective, options.projectId);
  return effective;
}

function warnAboutBrokenSettings(effective: EffectiveSettings, projectId?: string): void {
  for (const field of ['baseRemote', 'pushRemote', 'defaultBranch', 'worktreeRoot'] as const) {
    const resolved = effective[field];
    if (resolved.provenance.kind !== 'broken-setting') continue;
    log.warn(`Stale ${field} setting no longer matches the repository; using inferred fallback`, {
      projectId,
      staleValue: resolved.provenance.staleValue,
      fallback: resolved.value,
    });
  }
}

/**
 * Stored git settings parsed straight from a project-settings DB row, for
 * desktop flows that resolve without live Project Host access (for example,
 * automation deployment at boot). Applies the lazy stored-model migration in memory only — no
 * write-back; the settings provider persists it on its next read.
 */
export function storedGitSettingsFromRow(
  baseProjectSettingsJson: string,
  repoFacts: RepoFacts | null
): StoredProjectGitSettings {
  const raw = legacyBaseProjectSettingsSchema.parse(JSON.parse(baseProjectSettingsJson));
  return migrateStoredBaseProjectSettings(raw, repoFacts).next;
}

/**
 * Stored git settings for a registered Project, straight from the
 * project-settings row via `storedGitSettingsFromRow`. Desktop-only placement
 * may read this without a Host attachment; Host-backed features should use the
 * settings provider. An unreadable row
 * degrades to "nothing stored" — never a blocked flow.
 */
export async function loadStoredGitSettings(
  db: AppDb,
  projectId: string
): Promise<StoredProjectGitSettings> {
  const [row] = await db
    .select({ base: projectSettings.baseProjectSettingsJson })
    .from(projectSettings)
    .where(eq(projectSettings.projectId, projectId))
    .limit(1);
  if (!row) return {};
  try {
    return storedGitSettingsFromRow(row.base, null);
  } catch (error) {
    log.warn('Failed to read stored project git settings row; treating as unset', {
      projectId,
      error: error instanceof Error ? error.message : String(error),
    });
    return {};
  }
}

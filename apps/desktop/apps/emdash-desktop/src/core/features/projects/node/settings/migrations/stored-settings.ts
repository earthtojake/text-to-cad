import { isDeepEqual } from '@emdash/shared';
import {
  formatDefaultBranch,
  resolveEffectiveSettings,
  type BaseProjectSettings,
  type RepoFacts,
  type StoredBaseProjectSettings,
  type StoredDefaultBranch,
} from '@core/primitives/project-settings/api';
import { compactUndefined } from '../project-settings-json';
import type { LegacyBaseProjectSettings } from './legacy-stored-project-settings';

export type StoredSettingsMigrationResult = {
  next: StoredBaseProjectSettings;
  changed: boolean;
};

/**
 * Normalizes a historical DB JSON row into the current stored model. Pure: callers
 * may persist `next` when `changed`, or use it as a tolerant lazy reader.
 */
export function migrateStoredBaseProjectSettings(
  raw: LegacyBaseProjectSettings,
  repoFacts: RepoFacts | null,
  options: { tmuxDefault?: boolean } = {}
): StoredSettingsMigrationResult {
  const {
    remote: legacyRemote,
    worktreeDirectory: legacyWorktreeDirectory,
    githubAccountId: legacyGithubAccountId,
    defaultBranch: rawDefaultBranch,
    worktreeRoot,
    githubAccount,
    autoRunSetupScriptOnTaskCreation: _legacyAutoRunSetup,
    autoRunRunScriptOnTaskCreation: _legacyAutoRunRun,
    ...rest
  } = raw;

  const next: StoredBaseProjectSettings = { ...rest };

  const migratedWorktreeRoot = worktreeRoot ?? legacyWorktreeDirectory;
  if (migratedWorktreeRoot !== undefined) next.worktreeRoot = migratedWorktreeRoot;

  if (next.baseRemote === undefined && legacyRemote !== undefined) next.baseRemote = legacyRemote;

  if (githubAccount !== undefined) {
    next.githubAccount = githubAccount;
  } else if (typeof legacyGithubAccountId === 'string') {
    next.githubAccount = { kind: 'account', accountId: legacyGithubAccountId };
  }

  const migratedDefaultBranch = migrateDefaultBranch(rawDefaultBranch, next.baseRemote, repoFacts);
  if (migratedDefaultBranch !== undefined) next.defaultBranch = migratedDefaultBranch;

  if (repoFacts) demoteIfMatchesInference(next, repoFacts);
  if (options.tmuxDefault !== undefined && next.tmuxDefaultMigrated !== true) {
    if (next.tmux === options.tmuxDefault) delete next.tmux;
    next.tmuxDefaultMigrated = true;
  }

  return {
    next,
    changed: !isDeepEqual(compactUndefined({ ...raw }), compactUndefined({ ...next })),
  };
}

function migrateDefaultBranch(
  value: LegacyBaseProjectSettings['defaultBranch'],
  storedBaseRemote: string | undefined,
  repoFacts: RepoFacts | null
): StoredDefaultBranch | undefined {
  if (value === undefined) return undefined;
  if (typeof value === 'object') {
    if ('branch' in value) return value;
    return { remote: storedBaseRemote ?? 'origin', branch: value.name };
  }

  const trimmed = value.trim();
  if (!trimmed) return undefined;

  const knownRemote = repoFacts?.remotes.find((remote) =>
    trimmed.startsWith(`${remote.name}/`)
  )?.name;
  if (knownRemote) return { remote: knownRemote, branch: trimmed.slice(knownRemote.length + 1) };

  const slash = trimmed.indexOf('/');
  if (slash > 0) return { remote: trimmed.slice(0, slash), branch: trimmed.slice(slash + 1) };
  return { remote: null, branch: trimmed };
}

function demoteIfMatchesInference(next: StoredBaseProjectSettings, repoFacts: RepoFacts): void {
  if (next.baseRemote !== undefined) {
    const inferred = resolveEffectiveSettings(
      { project: {}, builtInWorktreeRoot: '' },
      repoFacts,
      []
    ).baseRemote;
    if (inferred.provenance.kind === 'inferred' && inferred.value === next.baseRemote) {
      delete next.baseRemote;
    }
  }

  if (next.defaultBranch !== undefined) {
    const inferred = resolveEffectiveSettings(
      { project: { baseRemote: next.baseRemote }, builtInWorktreeRoot: '' },
      repoFacts,
      []
    ).defaultBranch;
    if (
      inferred.provenance.kind === 'inferred' &&
      isDeepEqual(inferred.value, next.defaultBranch)
    ) {
      delete next.defaultBranch;
    }
  }
}

export function toLegacyBaseSettingsView(
  stored: LegacyBaseProjectSettings | StoredBaseProjectSettings
): BaseProjectSettings {
  const {
    worktreeRoot,
    githubAccount,
    defaultBranch,
    remote: legacyRemote,
    tmuxDefaultMigrated: _tmuxDefaultMigrated,
    ...rest
  } = stored as LegacyBaseProjectSettings;
  const view: BaseProjectSettings = { ...rest };

  if (worktreeRoot !== undefined) view.worktreeDirectory = worktreeRoot;
  if (view.baseRemote === undefined && legacyRemote !== undefined) {
    view.baseRemote = legacyRemote;
  }

  if (defaultBranch !== undefined) {
    view.defaultBranch =
      typeof defaultBranch === 'object' && 'branch' in defaultBranch
        ? formatDefaultBranch(defaultBranch)
        : defaultBranch;
  }

  if (githubAccount !== undefined) {
    view.githubAccountId = githubAccount.kind === 'account' ? githubAccount.accountId : null;
  }

  return view;
}

export function legacyBaseSettingsToStored(base: BaseProjectSettings): StoredBaseProjectSettings {
  const {
    worktreeDirectory,
    defaultBranch,
    githubAccountId,
    autoRunSetupScriptOnTaskCreation: _legacyAutoRunSetup,
    autoRunRunScriptOnTaskCreation: _legacyAutoRunRun,
    ...rest
  } = base;
  const stored: StoredBaseProjectSettings = { ...rest };

  if (worktreeDirectory !== undefined) stored.worktreeRoot = worktreeDirectory;

  const migratedDefaultBranch = migrateDefaultBranch(defaultBranch, base.baseRemote, null);
  if (migratedDefaultBranch !== undefined) stored.defaultBranch = migratedDefaultBranch;

  if (githubAccountId !== undefined) {
    stored.githubAccount =
      githubAccountId === null ? { kind: 'none' } : { kind: 'account', accountId: githubAccountId };
  }

  return stored;
}

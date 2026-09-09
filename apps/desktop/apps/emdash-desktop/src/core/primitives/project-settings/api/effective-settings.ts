import type { GitHubAccountSummary } from '@core/primitives/github/api';
import { normalizeRepositoryHost } from '@core/primitives/repository/api';
import type { PlacementContext } from './placement';
import type { AgentGitCredentialsSetting } from './project-settings';
import { normalizeWorktreeRootPath } from './worktree-root';

/**
 * The blessed resolver (spec: github-git-settings §2).
 *
 * One pure function resolves every effective per-project git/GitHub setting
 * from stored user choices, live repository facts, and the connected GitHub
 * accounts. Preview (renderer) and execution (node) must both call this
 * function over the same facts; no other resolution code may exist.
 *
 * Degrade semantics: stale remote/branch settings fall back with
 * `broken-setting` (worktree creation is never blocked by a stale setting).
 * A dangling or host-mismatched account pin is `unresolvable` — fail closed,
 * never a different GitHub identity.
 */

export type Provenance =
  | { kind: 'set' }
  | { kind: 'inferred'; from: string }
  | { kind: 'broken-setting'; staleValue: string }
  | { kind: 'unresolvable' };

export type Resolved<T> = { value: T; provenance: Provenance };

// ---------------------------------------------------------------------------
// Stored shapes (absence always means "infer")
// ---------------------------------------------------------------------------

/**
 * Structured stored default branch. `remote: null` means a local branch;
 * a remote name means "branch on that remote".
 */
export type StoredDefaultBranch = { remote: string | null; branch: string };

/**
 * Stored GitHub account choice. `{ kind: 'none' }` is explicit suppression
 * ("don't call GitHub APIs on this project"); absence of the field means
 * infer. `accountId` is the `provider_accounts` row id.
 */
export type StoredGithubAccount = { kind: 'account'; accountId: string } | { kind: 'none' };

/** Stored per-project settings the resolver consumes. Absent field = infer. */
export type StoredProjectGitSettings = {
  defaultBranch?: StoredDefaultBranch;
  baseRemote?: string;
  pushRemote?: string;
  githubAccount?: StoredGithubAccount;
  agentGitCredentials?: AgentGitCredentialsSetting;
  /** Per-project worktree root override. */
  worktreeRoot?: string;
};

/**
 * All stored choices the resolver needs: the per-project settings plus the
 * worktree-root layers below it (per-host default, built-in fallback).
 */
export type StoredSettings = {
  project: StoredProjectGitSettings;
  /** Per-host default worktree root from host settings, if configured. */
  hostWorktreeRoot?: string | null;
  /** Built-in worktree root for the host, e.g. `<home>/emdash/worktrees`. */
  builtInWorktreeRoot: string;
  /**
   * The host's home directory, for `~` expansion and validation of the
   * worktree-root layers. Callers that consume `worktreeRoot` must supply it;
   * without it the chain picks the first configured layer unvalidated.
   */
  homeDirectory?: string | null;
};

// ---------------------------------------------------------------------------
// Repository facts
// ---------------------------------------------------------------------------

export type RepoRemoteFacts = {
  name: string;
  /** Host parsed from the remote URL (e.g. "github.com"), null when unknown. */
  host: string | null;
  /** Branch the remote's HEAD points at, null when unknown. */
  headBranch: string | null;
  /** Branches known to exist on the remote. */
  branches: string[];
};

export type RepoFacts = {
  remotes: RepoRemoteFacts[];
  localBranches: string[];
};

// ---------------------------------------------------------------------------
// Effective values
// ---------------------------------------------------------------------------

export type EffectiveDefaultBranch = { remote: string | null; branch: string };

export type EffectiveSettings = {
  baseRemote: Resolved<string | null>;
  pushRemote: Resolved<string | null>;
  defaultBranch: Resolved<EffectiveDefaultBranch | null>;
  githubAccount: Resolved<GitHubAccountSummary | null>;
  worktreeRoot: Resolved<string>;
};

/** The git-only subset of the effective settings (base/push remote, default branch). */
export type EffectiveGitSettings = Pick<
  EffectiveSettings,
  'baseRemote' | 'pushRemote' | 'defaultBranch'
>;

/** Well-known default-branch candidates, in preference order (spec §2). */
export const DEFAULT_BRANCH_CANDIDATES = ['main', 'master', 'develop', 'trunk'] as const;

export function resolveEffectiveSettings(
  storedSettings: StoredSettings,
  repoFacts: RepoFacts,
  accounts: GitHubAccountSummary[]
): EffectiveSettings {
  const git = resolveEffectiveGitSettings(storedSettings.project, repoFacts);
  return {
    ...git,
    githubAccount: resolveGithubAccount(
      storedSettings.project.githubAccount,
      git.baseRemote.value,
      repoFacts,
      accounts
    ),
    worktreeRoot: resolveWorktreeRoot({
      projectWorktreeRoot: storedSettings.project.worktreeRoot,
      hostWorktreeRoot: storedSettings.hostWorktreeRoot,
      builtInWorktreeRoot: storedSettings.builtInWorktreeRoot,
      homeDirectory: storedSettings.homeDirectory,
    }),
  };
}

/**
 * Focused entry point for callers that only need the git values (base remote,
 * push remote, default branch) and have no account or worktree-root layers in
 * play — e.g. the renderer's repository store. Runs the *identical* internal
 * chains `resolveEffectiveSettings` composes; it exists so those callers never
 * fabricate the unrelated inputs, not as a second resolution path.
 */
export function resolveEffectiveGitSettings(
  storedSettings: Pick<StoredProjectGitSettings, 'baseRemote' | 'pushRemote' | 'defaultBranch'>,
  repoFacts: RepoFacts
): EffectiveGitSettings {
  const baseRemote = resolveBaseRemote(storedSettings.baseRemote, repoFacts);
  return {
    baseRemote,
    pushRemote: resolvePushRemote(storedSettings.pushRemote, baseRemote, repoFacts),
    defaultBranch: resolveDefaultBranch(storedSettings.defaultBranch, baseRemote.value, repoFacts),
  };
}

// ---------------------------------------------------------------------------
// Base remote: origin → sole remote → first alphabetical → none
// ---------------------------------------------------------------------------

function inferBaseRemote(repoFacts: RepoFacts): Resolved<string | null> {
  const names = repoFacts.remotes.map((remote) => remote.name);
  if (names.includes('origin')) {
    return { value: 'origin', provenance: { kind: 'inferred', from: 'origin remote' } };
  }
  if (names.length === 1) {
    return { value: names[0], provenance: { kind: 'inferred', from: 'sole remote' } };
  }
  if (names.length > 1) {
    const first = [...names].sort()[0];
    return { value: first, provenance: { kind: 'inferred', from: 'first remote alphabetically' } };
  }
  return { value: null, provenance: { kind: 'unresolvable' } };
}

function resolveBaseRemote(
  storedBaseRemote: string | undefined,
  repoFacts: RepoFacts
): Resolved<string | null> {
  if (storedBaseRemote === undefined) return inferBaseRemote(repoFacts);
  if (repoFacts.remotes.some((remote) => remote.name === storedBaseRemote)) {
    return { value: storedBaseRemote, provenance: { kind: 'set' } };
  }
  const fallback = inferBaseRemote(repoFacts);
  return {
    value: fallback.value,
    provenance: { kind: 'broken-setting', staleValue: storedBaseRemote },
  };
}

// ---------------------------------------------------------------------------
// Push remote: the effective base remote
// ---------------------------------------------------------------------------

function resolvePushRemote(
  storedPushRemote: string | undefined,
  baseRemote: Resolved<string | null>,
  repoFacts: RepoFacts
): Resolved<string | null> {
  if (storedPushRemote !== undefined) {
    if (repoFacts.remotes.some((remote) => remote.name === storedPushRemote)) {
      return { value: storedPushRemote, provenance: { kind: 'set' } };
    }
    return {
      value: baseRemote.value,
      provenance: { kind: 'broken-setting', staleValue: storedPushRemote },
    };
  }
  if (baseRemote.value === null) return { value: null, provenance: { kind: 'unresolvable' } };
  return { value: baseRemote.value, provenance: { kind: 'inferred', from: 'base remote' } };
}

// ---------------------------------------------------------------------------
// Default branch: remote HEAD → well-known remote branch → well-known local
// branch → none
// ---------------------------------------------------------------------------

function inferDefaultBranch(
  effectiveBaseRemote: string | null,
  repoFacts: RepoFacts
): Resolved<EffectiveDefaultBranch | null> {
  const baseRemote = repoFacts.remotes.find((remote) => remote.name === effectiveBaseRemote);
  if (baseRemote) {
    if (baseRemote.headBranch) {
      return {
        value: { remote: baseRemote.name, branch: baseRemote.headBranch },
        provenance: { kind: 'inferred', from: 'remote HEAD' },
      };
    }
    const remoteCandidate = DEFAULT_BRANCH_CANDIDATES.find((candidate) =>
      baseRemote.branches.includes(candidate)
    );
    if (remoteCandidate) {
      return {
        value: { remote: baseRemote.name, branch: remoteCandidate },
        provenance: { kind: 'inferred', from: 'well-known remote branch' },
      };
    }
  }
  const localCandidate = DEFAULT_BRANCH_CANDIDATES.find((candidate) =>
    repoFacts.localBranches.includes(candidate)
  );
  if (localCandidate) {
    return {
      value: { remote: null, branch: localCandidate },
      provenance: { kind: 'inferred', from: 'well-known local branch' },
    };
  }
  return { value: null, provenance: { kind: 'unresolvable' } };
}

function storedDefaultBranchExists(
  storedDefaultBranch: StoredDefaultBranch,
  repoFacts: RepoFacts
): boolean {
  if (storedDefaultBranch.remote === null) {
    return repoFacts.localBranches.includes(storedDefaultBranch.branch);
  }
  const remote = repoFacts.remotes.find((remote) => remote.name === storedDefaultBranch.remote);
  return remote !== undefined && remote.branches.includes(storedDefaultBranch.branch);
}

export function formatDefaultBranch(defaultBranch: StoredDefaultBranch): string {
  return defaultBranch.remote === null
    ? defaultBranch.branch
    : `${defaultBranch.remote}/${defaultBranch.branch}`;
}

function resolveDefaultBranch(
  storedDefaultBranch: StoredDefaultBranch | undefined,
  effectiveBaseRemote: string | null,
  repoFacts: RepoFacts
): Resolved<EffectiveDefaultBranch | null> {
  if (storedDefaultBranch === undefined) {
    return inferDefaultBranch(effectiveBaseRemote, repoFacts);
  }
  if (storedDefaultBranchExists(storedDefaultBranch, repoFacts)) {
    return { value: storedDefaultBranch, provenance: { kind: 'set' } };
  }
  const fallback = inferDefaultBranch(effectiveBaseRemote, repoFacts);
  return {
    value: fallback.value,
    provenance: { kind: 'broken-setting', staleValue: formatDefaultBranch(storedDefaultBranch) },
  };
}

// ---------------------------------------------------------------------------
// GitHub account: default account matching the base remote host → only
// host-matching account → none. Pins fail closed.
// ---------------------------------------------------------------------------

function baseRemoteHost(effectiveBaseRemote: string | null, repoFacts: RepoFacts): string | null {
  const remote = repoFacts.remotes.find((candidate) => candidate.name === effectiveBaseRemote);
  if (!remote || remote.host === null) return null;
  return normalizeRepositoryHost(remote.host);
}

function accountMatchesHost(account: GitHubAccountSummary, host: string): boolean {
  return normalizeRepositoryHost(account.host) === host;
}

/**
 * The single "default account for host" definition (spec §2): the provider
 * default account if its host matches → the only account whose host matches →
 * none. Project flows reach this through `resolveEffectiveSettings` (keyed off
 * the effective base remote's host); host-only flows with no project settings
 * in play (e.g. an explicit repository URL and nothing else) call it directly.
 * No other default-account inference may exist.
 */
export function resolveAccountForHost(
  host: string,
  accounts: GitHubAccountSummary[]
): Resolved<GitHubAccountSummary | null> {
  const normalizedHost = normalizeRepositoryHost(host);
  const defaultAccount = accounts.find((account) => account.isDefault);
  if (defaultAccount && accountMatchesHost(defaultAccount, normalizedHost)) {
    return { value: defaultAccount, provenance: { kind: 'inferred', from: 'default account' } };
  }
  const matching = accounts.filter((account) => accountMatchesHost(account, normalizedHost));
  if (matching.length === 1) {
    return {
      value: matching[0],
      provenance: { kind: 'inferred', from: 'only host-matching account' },
    };
  }
  return { value: null, provenance: { kind: 'inferred', from: 'no host-matching account' } };
}

function resolveGithubAccount(
  storedGithubAccount: StoredGithubAccount | undefined,
  effectiveBaseRemote: string | null,
  repoFacts: RepoFacts,
  accounts: GitHubAccountSummary[]
): Resolved<GitHubAccountSummary | null> {
  const host = baseRemoteHost(effectiveBaseRemote, repoFacts);

  if (storedGithubAccount?.kind === 'none') {
    return { value: null, provenance: { kind: 'set' } };
  }

  if (storedGithubAccount?.kind === 'account') {
    const pinned = accounts.find((account) => account.accountId === storedGithubAccount.accountId);
    // Fail closed: a dangling or host-mismatched pin never becomes another
    // identity. An unknown repository host is not mismatch evidence.
    if (!pinned) return { value: null, provenance: { kind: 'unresolvable' } };
    if (host !== null && !accountMatchesHost(pinned, host)) {
      return { value: null, provenance: { kind: 'unresolvable' } };
    }
    return { value: pinned, provenance: { kind: 'set' } };
  }

  if (host !== null) return resolveAccountForHost(host, accounts);
  return { value: null, provenance: { kind: 'inferred', from: 'no host-matching account' } };
}

// ---------------------------------------------------------------------------
// Worktree root: project override → host default → built-in
// ---------------------------------------------------------------------------

/**
 * The worktree-root chain (spec §6): per-project override (`set`) → per-host
 * default (`inferred` from "host default") → built-in root (`inferred` from
 * "built-in default"). When `homeDirectory` is available, each configured
 * layer is normalized (`~` expansion, absolute-path requirement); an unusable
 * layer degrades to the next one with `broken-setting` provenance carrying
 * the stale raw value — an invalid root warns, it never blocks creation.
 *
 * Exported so worktree placement resolves through the identical chain the
 * settings page and the create-task preview render. No other worktree-root
 * precedence code may exist.
 */
export function resolveWorktreeRoot(
  layers: Pick<StoredSettings, 'hostWorktreeRoot' | 'builtInWorktreeRoot' | 'homeDirectory'> & {
    projectWorktreeRoot?: string;
  }
): Resolved<string> {
  const chain: { raw: string; provenance: Provenance }[] = [];
  if (layers.projectWorktreeRoot !== undefined) {
    chain.push({ raw: layers.projectWorktreeRoot, provenance: { kind: 'set' } });
  }
  if (layers.hostWorktreeRoot != null) {
    chain.push({
      raw: layers.hostWorktreeRoot,
      provenance: { kind: 'inferred', from: 'host default' },
    });
  }
  chain.push({
    raw: layers.builtInWorktreeRoot,
    provenance: { kind: 'inferred', from: 'built-in default' },
  });

  const homeDirectory = layers.homeDirectory;
  if (homeDirectory == null) {
    const [first] = chain;
    return { value: first.raw, provenance: first.provenance };
  }

  let staleValue: string | null = null;
  for (const layer of chain) {
    const normalized = normalizeWorktreeRootPath(layer.raw, homeDirectory);
    if (normalized === null) {
      staleValue ??= layer.raw;
      continue;
    }
    return staleValue === null
      ? { value: normalized, provenance: layer.provenance }
      : { value: normalized, provenance: { kind: 'broken-setting', staleValue } };
  }
  // Even the built-in layer failed to normalize (a non-absolute home); fall
  // back to it raw rather than producing no placement at all.
  const builtIn = chain.at(-1)!;
  return staleValue === builtIn.raw || staleValue === null
    ? { value: builtIn.raw, provenance: builtIn.provenance }
    : { value: builtIn.raw, provenance: { kind: 'broken-setting', staleValue } };
}

// ---------------------------------------------------------------------------
// Tmux: project override → host default → app default
// ---------------------------------------------------------------------------

/**
 * The only tmux precedence chain: explicit per-project choice (`set`) →
 * per-host default (`inferred` from "host default") → desktop app default
 * (`inferred` from "app default"). Absence always means inherit.
 */
export function resolveTmux(
  layers: Pick<PlacementContext, 'hostTmux' | 'appDefaultTmux'> & { projectTmux?: boolean }
): Resolved<boolean> {
  if (layers.projectTmux !== undefined) {
    return { value: layers.projectTmux, provenance: { kind: 'set' } };
  }
  if (layers.hostTmux !== null) {
    return {
      value: layers.hostTmux,
      provenance: { kind: 'inferred', from: 'host default' },
    };
  }
  return {
    value: layers.appDefaultTmux,
    provenance: { kind: 'inferred', from: 'app default' },
  };
}

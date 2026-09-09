import { githubAccountReportingState } from '@core/features/github/api/account-reporting';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import type { Provenance, Resolved } from '@core/primitives/project-settings/api';

/**
 * React-free view state for the identity strip (spec: github-git-settings §9).
 * The strip shows who an account-relevant modal action (create PR, add remote,
 * create repository) will act as: a per-action override when the user picked
 * one in the popover, otherwise the blessed resolver's effective account.
 * Accountless outcomes map through the §7 reporting matrix so every surface
 * renders the same rows.
 */
export type IdentityStripView =
  | {
      kind: 'account';
      account: GitHubAccountSummary;
      /** `set` for an override or explicit pin, `inferred` for the silent default. */
      provenance: Provenance;
      /** True when the account was chosen in the popover for this action. */
      isActionOverride: boolean;
    }
  /** Explicit `{ kind: 'none' }` — quiet intent, not an error. */
  | { kind: 'disabled'; message: string }
  /** Zero accounts connected — the connect empty state. */
  | { kind: 'connect'; message: string }
  /** Accounts exist but none matches the repository host. */
  | { kind: 'no-match' }
  /** Dangling or host-mismatched pin — fail closed, never another identity. */
  | { kind: 'unresolvable'; message: string };

export function identityStripView(
  resolved: Resolved<GitHubAccountSummary | null>,
  override: GitHubAccountSummary | null,
  accounts: GitHubAccountSummary[]
): IdentityStripView {
  if (override) {
    return {
      kind: 'account',
      account: override,
      provenance: { kind: 'set' },
      isActionOverride: true,
    };
  }
  if (resolved.value) {
    return {
      kind: 'account',
      account: resolved.value,
      provenance: resolved.provenance,
      isActionOverride: false,
    };
  }
  const state = githubAccountReportingState(resolved.provenance, accounts.length > 0);
  switch (state.kind) {
    case 'disabled':
      return { kind: 'disabled', message: state.message };
    case 'connect':
      return { kind: 'connect', message: state.message };
    case 'silent':
      return { kind: 'no-match' };
    case 'unresolvable':
      return { kind: 'unresolvable', message: state.message };
  }
}

/**
 * Whether the surrounding modal must disable its primary action. Only actions
 * that genuinely require an account fail closed (create PR, create
 * repository); add-remote's link path proceeds on system credentials.
 */
export function identityStripBlocksAction(
  view: IdentityStripView,
  accountRequired: boolean
): boolean {
  return accountRequired && view.kind !== 'account';
}

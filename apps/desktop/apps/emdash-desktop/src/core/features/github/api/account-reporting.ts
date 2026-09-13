import type { Provenance } from '@core/primitives/project-settings/api';

/**
 * The §7 reporting matrix (spec: github-git-settings) for surfaces that act
 * as the project's GitHub account — issue pickers and PR panels. Input is the
 * blessed resolver's provenance for a `githubAccount` that resolved to null,
 * plus whether any GitHub accounts are connected at all; output is what the
 * surface shows:
 *
 * - `disabled` — explicit "no account" choice. Intent, not an error: quiet
 *   state, no error badging, no retry affordance.
 * - `connect` — nothing to infer and no accounts connected: the
 *   connect-flavored empty state.
 * - `silent` — nothing to infer but accounts exist: the silent default, no
 *   visible state; token resolution infers per repository host downstream.
 * - `unresolvable` — dangling or host-mismatched pin: fail closed with a fix
 *   affordance, never a silent fallback to another account.
 */
export type GitHubAccountReportingState =
  | { kind: 'disabled'; message: string }
  | { kind: 'connect'; message: string }
  | { kind: 'silent' }
  | { kind: 'unresolvable'; message: string };

export const GITHUB_DISABLED_MESSAGE = 'GitHub is disabled for this project.';
export const GITHUB_CONNECT_MESSAGE = 'Connect a GitHub account to get started.';
export const GITHUB_ACCOUNT_UNRESOLVABLE_MESSAGE =
  'The selected GitHub account is no longer connected.';

export function githubAccountReportingState(
  provenance: Provenance,
  accountsConnected: boolean
): GitHubAccountReportingState {
  switch (provenance.kind) {
    case 'set':
      return { kind: 'disabled', message: GITHUB_DISABLED_MESSAGE };
    case 'unresolvable':
    case 'broken-setting':
      return { kind: 'unresolvable', message: GITHUB_ACCOUNT_UNRESOLVABLE_MESSAGE };
    case 'inferred':
      return accountsConnected
        ? { kind: 'silent' }
        : { kind: 'connect', message: GITHUB_CONNECT_MESSAGE };
  }
}

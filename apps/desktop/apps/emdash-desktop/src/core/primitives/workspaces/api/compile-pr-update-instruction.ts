import { getPrNumber, isForkPr, type PullRequest } from '@root/src/core/services/pull-requests/api';
import { prCheckoutSourceRef } from './pr-source-refs';

/** The updateWorktree verb's git half: instruction-as-input, desktop-compiled. */
export type PrUpdateInstruction = { remote: string; sourceRef: string };

export type PrUpdateInstructionContext = {
  /** The project's base remote (default 'origin'); the remote PR heads fetch from. */
  baseRemote: string;
};

/**
 * Compiles the manual "Update now" instruction for a PR-associated checkout
 * (pr-workspace-model spec, Staleness — manual update): the same same-repo/fork
 * source-ref rule the createWorktree presets use, against the project's base remote.
 * Compiled from the association (the synced PR), never from workspace config or host
 * record fields — which is why it works unchanged for workspaces created before this
 * model shipped. Null when the PR number cannot be determined: no instruction can be
 * compiled.
 */
export function compilePrUpdateInstruction(
  pr: Pick<PullRequest, 'identifier' | 'headRefName' | 'headRepositoryUrl' | 'repositoryUrl'>,
  context: PrUpdateInstructionContext
): PrUpdateInstruction | null {
  const prNumber = getPrNumber(pr);
  if (prNumber === null) return null;
  return {
    remote: context.baseRemote,
    sourceRef: prCheckoutSourceRef({
      prNumber,
      headBranch: pr.headRefName,
      isFork: isForkPr(pr),
    }),
  };
}

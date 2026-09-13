import type { WorkspaceLifecycleStepInfo } from '@core/primitives/tasks/api';
import type { WorktreeGitPlan } from './compile-worktree-git-plan';
import { LIFECYCLE_STEP_TITLES } from './lifecycle-step-titles';

/**
 * The lifecycle steps a compiled plan can promise up front — a subset of the registry
 * pipeline's step ids, so the modal's "what will happen" and the Activity badge's
 * "what is happening" speak one vocabulary. Runtime-conditional steps the plan cannot
 * see (fetch-remote-base, fetch-refs, scripts) are never promised here.
 */
export type WorktreeSetupStepId = Extract<
  WorkspaceLifecycleStepInfo['id'],
  'fetch-branch' | 'create-worktree' | 'configure-branch' | 'copy-artifacts' | 'push-branch'
>;

export type WorktreeSetupStep = {
  id: WorktreeSetupStepId;
  title: string;
  description: string;
};

function step(id: WorktreeSetupStepId, description: string): WorktreeSetupStep {
  return { id, title: LIFECYCLE_STEP_TITLES[id], description };
}

/**
 * Projects a compiled `WorktreeGitPlan` into the ordered display steps the create-task
 * modal previews (pr-workspace-model spec, preview/execution unification). Pure and
 * renderer-safe; because the input is the exact object `createTask` sends to the
 * `createWorktree` verb, the preview cannot drift from execution.
 *
 * Steps follow the registry pipeline's lifecycle order. `copy-artifacts` mirrors the
 * pipeline's own guard: the host only plans the step when preservePatterns exist.
 */
export function describeWorktreeGitPlan(
  plan: WorktreeGitPlan,
  context: { preservePatterns: readonly string[] }
): WorktreeSetupStep[] {
  const steps: WorktreeSetupStep[] = [];
  const { fetchBranch, upstream, breadcrumb } = plan.gitSetup ?? {};

  if (fetchBranch) {
    steps.push(
      step(
        'fetch-branch',
        `Fetch ${fetchBranch.sourceRef} from ${fetchBranch.remote} into ${plan.branch}`
      )
    );
  }

  steps.push(step('create-worktree', describeCreateWorktree(plan, fetchBranch !== undefined)));

  // Mirrors the pipeline's own guard: configure-branch runs iff there is an upstream
  // or a breadcrumb to write.
  if (upstream) {
    steps.push(
      step(
        'configure-branch',
        `Set ${plan.branch} to track ${upstream.mergeRef} on ${upstream.remote}`
      )
    );
  } else if (breadcrumb) {
    steps.push(step('configure-branch', `Record the pull request association on ${plan.branch}`));
  }

  if (context.preservePatterns.length > 0) {
    steps.push(step('copy-artifacts', 'Copy preserved project files into the worktree'));
  }

  if (plan.publish) {
    steps.push(
      step('push-branch', `Push ${plan.branch} to ${plan.publish.remote} and set upstream tracking`)
    );
  }

  return steps;
}

function describeCreateWorktree(plan: WorktreeGitPlan, fetched: boolean): string {
  if (fetched) return `Create a worktree on the fetched branch ${plan.branch}`;
  if (plan.baseRef !== undefined && plan.baseRef !== plan.branch) {
    return `Create a worktree on new branch ${plan.branch} based on ${plan.baseRef}`;
  }
  return `Create a worktree on branch ${plan.branch}`;
}

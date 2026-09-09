import type {
  CreateWorktreeInput,
  WorkspaceLifecycle,
  WorkspaceLifecycleStep,
  WorkspaceLifecycleStepId,
} from '../api/schemas';
import type { CreateWorktreeExecutionResult } from './create-worktree';

/**
 * Canonical display/storage order of lifecycle steps. Upserts keep the steps array
 * sorted by this order so the Activity timeline never needs to sort.
 */
export const LIFECYCLE_STEP_ORDER: readonly WorkspaceLifecycleStepId[] = [
  'adopt-worktree',
  'fetch-branch',
  'fetch-remote-base',
  'create-worktree',
  'configure-branch',
  'copy-artifacts',
  'push-branch',
  'fetch-refs',
  'prepare',
  'setup',
  'run',
  'teardown',
];

/** The steps the runtime replays when left pending/running (restart, next activation). */
export const BACKGROUND_STEP_IDS = ['copy-artifacts', 'push-branch', 'fetch-refs'] as const;
export type BackgroundStepId = (typeof BACKGROUND_STEP_IDS)[number];

/** Activation-script steps: reset wholesale at each activation, never accumulated. */
export const SCRIPT_STEP_IDS: ReadonlySet<WorkspaceLifecycleStepId> = new Set([
  'prepare',
  'setup',
  'run',
  'teardown',
]);

export function getLifecycleStep(
  lifecycle: WorkspaceLifecycle | null,
  id: WorkspaceLifecycleStepId
): WorkspaceLifecycleStep | null {
  return lifecycle?.steps.find((step) => step.id === id) ?? null;
}

/** Replaces (or inserts, in canonical order) one step; never mutates the input. */
export function withLifecycleStep(
  lifecycle: WorkspaceLifecycle,
  step: WorkspaceLifecycleStep
): WorkspaceLifecycle {
  const existing = lifecycle.steps.some((entry) => entry.id === step.id);
  const steps = existing
    ? lifecycle.steps.map((entry) => (entry.id === step.id ? step : entry))
    : sortSteps([...lifecycle.steps, step]);
  return { ...lifecycle, steps };
}

export function sortSteps(steps: WorkspaceLifecycleStep[]): WorkspaceLifecycleStep[] {
  return [...steps].sort(
    (a, b) => LIFECYCLE_STEP_ORDER.indexOf(a.id) - LIFECYCLE_STEP_ORDER.indexOf(b.id)
  );
}

/** Pending/running steps are incomplete and replay; terminal statuses never re-run. */
export function isIncompleteStep(step: WorkspaceLifecycleStep | null): boolean {
  return step !== null && (step.status === 'pending' || step.status === 'running');
}

/**
 * Maps a foreground pipeline stage onto the lifecycle step it belongs to. Inspect,
 * add-worktree, and verify are all part of materializing the worktree; base fetches
 * and the gitSetup stages surface as their own steps.
 */
export function stepIdForStage(stage: string): WorkspaceLifecycleStepId {
  if (stage === 'fetch-branch' || stage === 'configure-branch') return stage;
  return stage === 'resolve-base' || stage === 'fetch-base'
    ? 'fetch-remote-base'
    : 'create-worktree';
}

export type CreationStageTimeline = Array<{ stage: string; at: number }>;

/**
 * Builds the durable lifecycle section for a settled foreground creation pipeline.
 * Conditional steps that never applied are absent: adopt and create are alternatives,
 * fetch-remote-base appears only when a base fetch actually ran, copy-artifacts only
 * for a freshly created worktree with preservePatterns configured, push-branch only
 * when a push was requested.
 */
export function buildCreationLifecycle(
  input: CreateWorktreeInput,
  result: CreateWorktreeExecutionResult,
  stages: CreationStageTimeline,
  now: number
): WorkspaceLifecycle {
  const stageAt = (stage: string): number | null =>
    stages.find((entry) => entry.stage === stage)?.at ?? null;
  // When the next stage began — the closest durable fact to "this stage finished".
  const stageEndAt = (stage: string): number | null => {
    const index = stages.findIndex((entry) => entry.stage === stage);
    return index >= 0 ? (stages[index + 1]?.at ?? null) : null;
  };
  const fetchBranch = input.gitSetup?.fetchBranch;
  const fetchedBranch = stageAt('fetch-branch') !== null;
  const fetchedBase = stageAt('fetch-base') !== null;
  const fetchBranchParams: WorkspaceLifecycleStep['params'] = fetchBranch
    ? { branch: input.branch, remote: fetchBranch.remote, source: fetchBranch.sourceRef }
    : {};
  const baseParams: WorkspaceLifecycleStep['params'] =
    input.baseRef !== undefined ? { base: input.baseRef } : {};
  const steps: WorkspaceLifecycleStep[] = [];

  // The gitSetup fetch, planned whenever fetchBranch was requested: succeeded when it
  // actually ran, skipped when an existing refs/heads/<branch> was reused (replay rule).
  const fetchBranchStep = (): WorkspaceLifecycleStep =>
    fetchedBranch
      ? {
          id: 'fetch-branch',
          status: 'succeeded',
          startedAt: stageAt('fetch-branch'),
          finishedAt: stageEndAt('fetch-branch') ?? now,
          params: fetchBranchParams,
        }
      : {
          id: 'fetch-branch',
          status: 'skipped',
          startedAt: null,
          finishedAt: now,
          message: `Branch ${input.branch} already exists; reused without fetching`,
          params: fetchBranchParams,
        };

  if (result.status === 'failed') {
    const failedStepId = stepIdForStage(result.stage);
    if (fetchedBranch && failedStepId !== 'fetch-branch') {
      steps.push(fetchBranchStep());
    }
    if (fetchedBase && failedStepId !== 'fetch-remote-base') {
      steps.push({
        id: 'fetch-remote-base',
        status: 'succeeded',
        startedAt: stageAt('fetch-base'),
        finishedAt: stageAt('add-worktree') ?? now,
        params: baseParams,
      });
    }
    steps.push({
      id: failedStepId,
      status: 'failed',
      startedAt: failedStepStartAt(failedStepId, stageAt) ?? now,
      finishedAt: now,
      message: result.message,
      params:
        failedStepId === 'fetch-branch'
          ? fetchBranchParams
          : failedStepId === 'configure-branch'
            ? { branch: input.branch }
            : failedStepId === 'fetch-remote-base'
              ? baseParams
              : { path: input.path, branch: input.branch },
    });
    return { steps, preservePatterns: input.preservePatterns };
  }

  if (!result.createdWorktree) {
    steps.push({
      id: 'adopt-worktree',
      status: 'succeeded',
      startedAt: stageAt('inspect') ?? now,
      finishedAt: now,
      params: { branch: input.branch, path: result.finalPath },
    });
    // An existing worktree means an existing branch: the planned fetch never ran.
    if (fetchBranch) steps.push(fetchBranchStep());
  } else {
    if (fetchBranch) steps.push(fetchBranchStep());
    if (fetchedBase) {
      steps.push({
        id: 'fetch-remote-base',
        status: 'succeeded',
        startedAt: stageAt('fetch-base'),
        finishedAt: stageAt('add-worktree') ?? now,
        params: baseParams,
      });
    }
    steps.push({
      id: 'create-worktree',
      status: 'succeeded',
      startedAt: stageAt('add-worktree') ?? stageAt('inspect') ?? now,
      finishedAt: now,
      params: {
        path: result.finalPath,
        branch: input.branch,
        branchCreated: result.createdBranch,
      },
    });
  }

  // The gitSetup config writes: idempotent, so they run on fresh and reused paths
  // alike — a stage entry is the fact that they ran.
  if (stageAt('configure-branch') !== null) {
    steps.push({
      id: 'configure-branch',
      status: 'succeeded',
      startedAt: stageAt('configure-branch'),
      finishedAt: stageEndAt('configure-branch') ?? now,
      params: { branch: input.branch },
    });
  }

  // The copy step exists only when the project deliberately names artifacts to
  // preserve — no patterns, no step (spec: preserved-artifact copy).
  if (result.createdWorktree && input.preservePatterns.length > 0) {
    steps.push({
      id: 'copy-artifacts',
      status: 'pending',
      startedAt: null,
      finishedAt: null,
      params: {},
    });
  }

  if (input.publish) {
    steps.push({
      id: 'push-branch',
      status: 'pending',
      startedAt: null,
      finishedAt: null,
      params: { branch: input.branch, remote: input.publish.remote },
    });
  }
  // No base ref, nothing to freshen: the advisory fetch step never applies.
  if (input.baseRef !== undefined) {
    steps.push({
      id: 'fetch-refs',
      status: 'pending',
      startedAt: null,
      finishedAt: null,
      params: { base: input.baseRef },
    });
  }

  return { steps, preservePatterns: input.preservePatterns };
}

/** Where a failed foreground step began, from the stage timeline. */
function failedStepStartAt(
  stepId: WorkspaceLifecycleStepId,
  stageAt: (stage: string) => number | null
): number | null {
  if (stepId === 'fetch-branch') return stageAt('fetch-branch');
  if (stepId === 'configure-branch') return stageAt('configure-branch');
  if (stepId === 'fetch-remote-base') return stageAt('resolve-base') ?? stageAt('inspect');
  return stageAt('inspect');
}

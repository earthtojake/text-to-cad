import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import type { BoundExec } from '#services/exec/api';
import type { WorkspaceLifecycleStep, WorkspaceLifecycleStepId } from '../api/schemas';
import { executeCopyArtifacts, type CopyArtifactsOutcome } from './copy-artifacts';
import type { RegistryGitContext } from './git-context';
import { getLifecycleStep, isIncompleteStep } from './lifecycle';
import type { DurableWorkspaceRecord } from './persistence/record-store';
import type { ScanRequest } from './scan/scheduler';

export type BackgroundStepOutcome =
  | { status: 'succeeded' }
  | { status: 'skipped'; reason: string }
  | { status: 'failed'; message: string };

export type BackgroundRunHandle = {
  /** The whole chain settled. Never rejects — failures land as durable step states. */
  settled: Promise<void>;
  /**
   * The copy step settled (succeeded, failed, or skipped), or resolved immediately when
   * copy was not part of this run. Never rejects — a rejected copy still opens the gate;
   * dependents proceed and a real install is the graceful degradation.
   */
  copySettled: Promise<void>;
};

/** The runner's one durable write: the runtime's lifecycle step writer behind it. */
export type BackgroundStepState = {
  status: WorkspaceLifecycleStep['status'];
  message?: string;
  params?: WorkspaceLifecycleStep['params'];
};

/** Step executors as a seam: tests inject fakes; production runs the real three. */
export type BackgroundStepExecutors = {
  copy(input: {
    repositoryPath: string;
    worktreePath: string;
    preservePatterns: readonly string[];
  }): Promise<CopyArtifactsOutcome>;
  push(input: {
    repositoryPath: string;
    branch: string;
    /** Absent only for lifecycle records written before publish targets were persisted. */
    remote?: string;
  }): Promise<BackgroundStepOutcome>;
  fetch(input: { repositoryPath: string; baseRef: string }): Promise<BackgroundStepOutcome>;
};

export type BackgroundStepRunnerDeps = {
  /** Read-only record access; every durable write goes through `steps`. */
  records: {
    get(id: string): DurableWorkspaceRecord | undefined;
    list(): DurableWorkspaceRecord[];
  };
  steps: {
    update(id: string, stepId: WorkspaceLifecycleStepId, state: BackgroundStepState): Promise<void>;
  };
  /** The scan self-suppression protocol: hold the mute while writing, settle once after. */
  scans: {
    mute(id: string): () => void;
    settle(request: ScanRequest): void;
  };
  /**
   * The runtime's git context: `schedule` for the repo hold, and the exec path the
   * default real executors run their subprocesses through.
   */
  git: RegistryGitContext;
  executors?: BackgroundStepExecutors;
  logger?: Logger;
  clock?: Clock;
};

/** Debounce window for the advisory fetch-refs step, per repository. */
const FETCH_DEBOUNCE_MS = 5 * 60_000;

/**
 * The background creation-step chain (spec: registry-runtime-carveout, PR 3): copy,
 * push, and fetch orchestration with durable per-step statuses, replayed idempotently
 * and never a gate on agent spawn. One concurrency rule: every step execution — the
 * chain, the activation replay, and manual retries — flows through the per-workspace
 * single-flight inside the repository hold. The run handle comes from the
 * `ensureRunning` call itself, never a map read afterward, so the activation artifact
 * gate cannot race the run's bookkeeping.
 */
export class BackgroundStepRunner {
  private readonly records: BackgroundStepRunnerDeps['records'];
  private readonly steps: BackgroundStepRunnerDeps['steps'];
  private readonly scans: BackgroundStepRunnerDeps['scans'];
  private readonly git: RegistryGitContext;
  private readonly executors: BackgroundStepExecutors;
  private readonly logger: Logger;
  private readonly clock: Clock;
  /** In-flight runs, coalesced per workspace id; internal by design. */
  private readonly runs = new Map<string, BackgroundRunHandle>();
  /**
   * Debounce stamps for the advisory fetch-refs step, keyed by repository path and
   * stamped only on a succeeded outcome — a failed fetch never suppresses the next
   * real attempt (spec: fetch honesty).
   */
  private readonly lastFetchAt = new Map<string, number>();

  constructor(deps: BackgroundStepRunnerDeps) {
    this.records = deps.records;
    this.steps = deps.steps;
    this.scans = deps.scans;
    this.git = deps.git;
    this.executors = deps.executors ?? {
      copy: (input) => executeCopyArtifacts({ git: deps.git, ...input }),
      push: (input) => executePushBranch({ git: deps.git, ...input }),
      fetch: (input) => executeFetchRefs({ git: deps.git, ...input }),
    };
    this.logger = deps.logger ?? noopLogger;
    this.clock = deps.clock ?? systemClock;
  }

  /** Runs every incomplete background step for one record, coalesced per workspace. */
  ensureRunning(id: string): BackgroundRunHandle {
    const existing = this.runs.get(id);
    if (existing) return existing;
    return this.register(id, 'background creation steps', (copySettled) =>
      this.executeChain(id, copySettled)
    );
  }

  /**
   * The single-flight's one entry point: registers a run's handle before the work
   * starts, so a gate opened at any moment observes this run — never a map race.
   * `settled` and `copySettled` never reject; whatever ends the run (early return,
   * copy done, or a rejection) the artifact gate is open once the run is over.
   */
  private register(
    id: string,
    what: string,
    work: (copySettled: () => void) => Promise<void>
  ): BackgroundRunHandle {
    let resolveCopy!: () => void;
    const copySettled = new Promise<void>((resolve) => {
      resolveCopy = resolve;
    });
    const settled = work(resolveCopy)
      .catch((error) => {
        this.logger.warn?.(`${what} for '${id}' failed unexpectedly`, { error });
      })
      .finally(() => {
        resolveCopy();
        this.runs.delete(id);
      });
    const handle: BackgroundRunHandle = { settled, copySettled };
    this.runs.set(id, handle);
    return handle;
  }

  /**
   * The activation artifact gate: resolves once the artifact copy settled (succeeded,
   * failed, or skipped — a terminal failure opens the gates anyway) so dependency-
   * consuming steps run against whatever exists. Incomplete durable state without an
   * in-flight run (post-restart) triggers a replay first.
   */
  async awaitArtifactCopy(id: string): Promise<void> {
    const record = this.records.get(id);
    if (!record?.lifecycle) return;
    if (!isIncompleteStep(getLifecycleStep(record.lifecycle, 'copy-artifacts'))) return;
    await this.ensureRunning(id).copySettled;
  }

  /**
   * Manual retry of a durably failed lifecycle step. 'failed' is the only status a
   * retry re-runs; anything else (succeeded, skipped, or settled by an in-flight run
   * this call waited out) is a no-op. The retry registers in the single-flight, so an
   * activation landing mid-retry gates on this run's `copySettled` instead of
   * spawning a second execution.
   */
  async retry(id: string, step: 'copy-artifacts' | 'push-branch'): Promise<void> {
    // The single-flight is the one concurrency rule: wait out any in-flight run and
    // re-check the failed status afterwards, closing the check-then-act window.
    while (this.runs.has(id)) {
      await this.runs.get(id)?.settled;
    }
    await this.register(id, `retry of ${step}`, (copySettled) =>
      this.executeRetry(id, step, copySettled)
    ).settled;
  }

  private async executeRetry(
    id: string,
    step: 'copy-artifacts' | 'push-branch',
    copySettled: () => void
  ): Promise<void> {
    const record = this.records.get(id);
    if (!record) return;
    const lifecycleStep = getLifecycleStep(record.lifecycle, step);
    const parent = record.parentId === null ? undefined : this.records.get(record.parentId);
    if (lifecycleStep?.status !== 'failed' || !parent) return;
    if (step === 'push-branch') {
      // Copy is not part of this run: the gate opens now, not when the push settles.
      copySettled();
      const target = pushTarget(record, lifecycleStep);
      if (target === null) return;
      await this.git.schedule.withRepoHold(parent.path, () =>
        this.executePushStep(id, parent.id, parent.path, target)
      );
      return;
    }
    await this.git.schedule.withRepoHold(parent.path, () =>
      this.executeCopyStep(id, parent.path, record.path).finally(copySettled)
    );
  }

  private async executeChain(id: string, copySettled: () => void): Promise<void> {
    const record = this.records.get(id);
    if (!record?.lifecycle || record.lastCreateOutcome?.status !== 'succeeded') return;
    const parent = record.parentId === null ? undefined : this.records.get(record.parentId);
    if (!parent) return;
    const repositoryPath = parent.path;
    const baseRef = record.creation?.baseRef ?? null;
    const lifecycle = record.lifecycle;
    const pushStep = getLifecycleStep(lifecycle, 'push-branch');
    const target = pushTarget(record, pushStep);

    // Copy inclusion is known from durable state alone: when copy is not part of
    // this run, the artifact gate opens now — not after the repo hold is acquired.
    const copyIncluded = isIncompleteStep(getLifecycleStep(lifecycle, 'copy-artifacts'));
    if (!copyIncluded) copySettled();

    // The whole chain holds the repository's idle gate (spec: scan minimization —
    // registry-owned background steps suppress idle-gated scans like creation does).
    await this.git.schedule.withRepoHold(repositoryPath, async () => {
      const work: Array<Promise<void>> = [];
      if (copyIncluded) {
        work.push(this.executeCopyStep(id, repositoryPath, record.path).finally(copySettled));
      }
      if (target !== null && isIncompleteStep(pushStep)) {
        work.push(this.executePushStep(id, parent.id, repositoryPath, target));
      }
      if (baseRef !== null && isIncompleteStep(getLifecycleStep(lifecycle, 'fetch-refs'))) {
        work.push(this.executeFetchStep(id, parent.id, repositoryPath, baseRef));
      }
      await Promise.all(work);
    });
  }

  private async executeCopyStep(
    id: string,
    repositoryPath: string,
    worktreePath: string
  ): Promise<void> {
    const preservePatterns = this.records.get(id)?.lifecycle?.preservePatterns ?? [];
    // The copy writes straight into the watched working tree: mute the workspace's
    // watcher-driven scans for the duration, then scan once deliberately.
    const release = this.scans.mute(id);
    try {
      await this.steps.update(id, 'copy-artifacts', { status: 'running' });
      const startedAt = this.clock.now();
      const outcome = await this.executors.copy({ repositoryPath, worktreePath, preservePatterns });
      this.logger.info?.(
        `copy-artifacts for '${id}': ${outcome.status} in ${this.clock.now() - startedAt}ms`,
        {
          ...(outcome.status === 'succeeded'
            ? { engine: outcome.engine, entries: outcome.entries, warnings: outcome.warnings }
            : {}),
          ...(outcome.status === 'failed' ? { message: outcome.message } : {}),
        }
      );
      await this.steps.update(id, 'copy-artifacts', {
        ...toStepState(outcome),
        ...(outcome.status === 'succeeded' ? { params: { fileCount: outcome.entries } } : {}),
      });
    } finally {
      release();
      this.scans.settle({ kind: 'workspace', id, mode: 'full' });
    }
  }

  private async executePushStep(
    id: string,
    repositoryId: string,
    repositoryPath: string,
    target: { branch: string; remote?: string }
  ): Promise<void> {
    // The push updates the repository's remote-tracking ref: mute the repository's
    // gitdir events (fanout included), then refresh the two records it affects.
    const release = this.scans.mute(repositoryId);
    try {
      await this.steps.update(id, 'push-branch', { status: 'running' });
      const outcome = await this.executors.push({ repositoryPath, ...target });
      await this.steps.update(id, 'push-branch', toStepState(outcome));
    } finally {
      release();
      this.scans.settle({ kind: 'workspace', id: repositoryId, mode: 'refs' });
      this.scans.settle({ kind: 'workspace', id, mode: 'refs' });
    }
  }

  private async executeFetchStep(
    id: string,
    repositoryId: string,
    repositoryPath: string,
    baseRef: string
  ): Promise<void> {
    const last = this.lastFetchAt.get(repositoryPath);
    if (last !== undefined && this.clock.now() - last < FETCH_DEBOUNCE_MS) {
      await this.steps.update(id, 'fetch-refs', {
        status: 'skipped',
        message: 'A recent fetch already freshened this repository',
      });
      return;
    }
    // The fetch rewrites refs/remotes and packed-refs: mute the repository so the
    // watcher does not fan refs scans across every worktree mid-write, then run
    // the same fanout once, deliberately, when it settles.
    const release = this.scans.mute(repositoryId);
    try {
      await this.steps.update(id, 'fetch-refs', { status: 'running' });
      const outcome = await this.executors.fetch({ repositoryPath, baseRef });
      // Fetch honesty (spec: PR 3): the debounce stamp lands only on success, so the
      // skip message stays true and a failed fetch never debounces the next attempt.
      if (outcome.status === 'succeeded') {
        this.lastFetchAt.set(repositoryPath, this.clock.now());
      }
      // Advisory by contract: a failed fetch is recorded, never surfaced as an error.
      await this.steps.update(id, 'fetch-refs', toStepState(outcome));
    } finally {
      release();
      this.scans.settle({ kind: 'workspace', id: repositoryId, mode: 'refs' });
      for (const record of this.records.list()) {
        if (record.parentId === repositoryId && record.observedStatus === 'present') {
          this.scans.settle({ kind: 'workspace', id: record.id, mode: 'refs' });
        }
      }
    }
  }
}

function toStepState(outcome: {
  status: 'succeeded' | 'skipped' | 'failed';
  message?: string;
  reason?: string;
}): BackgroundStepState {
  if (outcome.status === 'failed') return { status: 'failed', message: outcome.message };
  if (outcome.status === 'skipped') return { status: 'skipped', message: outcome.reason };
  return { status: 'succeeded' };
}

/**
 * The push-branch background step: one attempt in the parent repository, outside the
 * per-repository creation mutex (git ref locking handles overlap). Failure becomes a
 * durable "branch not pushed" state with a manual retry — never an automatic loop.
 */
export async function executePushBranch(input: {
  git: RegistryGitContext;
  repositoryPath: string;
  branch: string;
  /** Missing only when replaying a lifecycle record created by an older version. */
  remote?: string;
}): Promise<BackgroundStepOutcome> {
  const exec = input.git.exec(input.repositoryPath, {
    tier: 'background',
    repository: input.repositoryPath,
  });
  try {
    const remote = input.remote ?? (await legacyDefaultRemote(exec));
    if (!remote) {
      return { status: 'failed', message: 'Repository has no remote to push to' };
    }
    await exec.exec(['push', '-u', remote, input.branch]);
    return { status: 'succeeded' };
  } catch (error) {
    return { status: 'failed', message: describe(error) };
  }
}

/**
 * The fetch-refs background step: freshens the base remote's tracking refs so the next
 * creation's resolve-base finds a recent base. Advisory — the outcome is recorded but
 * a failure (offline) never surfaces as an error. Base remote only; never --all.
 */
export async function executeFetchRefs(input: {
  git: RegistryGitContext;
  repositoryPath: string;
  baseRef: string;
}): Promise<BackgroundStepOutcome> {
  const exec = input.git.exec(input.repositoryPath, {
    tier: 'background',
    repository: input.repositoryPath,
  });
  try {
    const remotes = (await exec.exec(['remote'])).stdout.trim().split('\n').filter(Boolean);
    if (remotes.length === 0) {
      return { status: 'skipped', reason: 'Repository has no remotes' };
    }
    const separator = input.baseRef.indexOf('/');
    const candidate = separator > 0 ? input.baseRef.slice(0, separator) : null;
    const remote =
      candidate !== null && remotes.includes(candidate)
        ? candidate
        : remotes.includes('origin')
          ? 'origin'
          : remotes[0]!;
    // Hygiene (spec: git concurrency model): freshen tracking refs without a
    // FETCH_HEAD write or an auto-maintenance child racing other operations.
    await exec.exec(['fetch', remote, '--prune', '--no-write-fetch-head', '--no-auto-maintenance']);
    return { status: 'succeeded' };
  } catch (error) {
    return { status: 'failed', message: describe(error) };
  }
}

/** Compatibility for pending/failed push steps persisted before the remote was recorded. */
async function legacyDefaultRemote(exec: BoundExec): Promise<string | null> {
  const remotes = (await exec.exec(['remote'])).stdout.trim().split('\n').filter(Boolean);
  if (remotes.includes('origin')) return 'origin';
  return remotes[0] ?? null;
}

function pushTarget(
  record: DurableWorkspaceRecord,
  step: WorkspaceLifecycleStep | null | undefined
): { branch: string; remote?: string } | null {
  const branchParam = step?.params.branch;
  const branch = typeof branchParam === 'string' ? branchParam : record.creation?.branch;
  if (!branch) return null;
  const remote = step?.params.remote;
  return typeof remote === 'string' ? { branch, remote } : { branch };
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

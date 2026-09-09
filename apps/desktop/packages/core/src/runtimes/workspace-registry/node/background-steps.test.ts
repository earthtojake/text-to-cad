import { ManualClock } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import type { WorkspaceLifecycleStep, WorkspaceLifecycleStepId } from '../api/schemas';
import {
  BackgroundStepRunner,
  type BackgroundStepExecutors,
  type BackgroundStepRunnerDeps,
  type BackgroundStepState,
} from './background-steps';
import type { CopyArtifactsOutcome } from './copy-artifacts';
import { createRegistryGitContext } from './git-context';
import { getLifecycleStep, withLifecycleStep } from './lifecycle';
import type { DurableWorkspaceRecord } from './persistence/record-store';

// The step chain in isolation (spec: registry-runtime-carveout, PR 3): fake executors
// and a mutable in-memory record store drive the runner directly. The handle contract,
// the single-flight, the retry no-op rule, and the fetch-honesty fix are all observable
// through the four ports.

function step(
  id: WorkspaceLifecycleStepId,
  status: WorkspaceLifecycleStep['status'],
  params: WorkspaceLifecycleStep['params'] = {}
): WorkspaceLifecycleStep {
  return { id, status, startedAt: null, finishedAt: null, params };
}

function worktree(overrides: Partial<DurableWorkspaceRecord> = {}): DurableWorkspaceRecord {
  return {
    id: 'ws-1',
    kind: 'worktree',
    path: '/tmp/repo-wt',
    parentId: 'repo-1',
    origin: 'registered',
    gitAdminName: null,
    observedStatus: 'present',
    creation: { branch: 'feature/x', baseRef: 'origin/main', requestedPath: '/tmp/repo-wt' },
    lastCreateOutcome: { status: 'succeeded', at: 1_000 },
    lifecycle: { steps: [step('copy-artifacts', 'pending')], preservePatterns: ['.env'] },
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1_000,
    updatedAt: 1_000,
    lastObservedAt: 1_000,
    ...overrides,
  };
}

function repository(overrides: Partial<DurableWorkspaceRecord> = {}): DurableWorkspaceRecord {
  return worktree({
    id: 'repo-1',
    kind: 'repository',
    path: '/tmp/repo',
    parentId: null,
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    ...overrides,
  });
}

type Harness = {
  runner: BackgroundStepRunner;
  stepWrites: Array<{ id: string; stepId: WorkspaceLifecycleStepId; status: string }>;
  clock: ManualClock;
  /** Direct store mutation, e.g. re-arming a settled step as pending between runs. */
  setStep(
    id: string,
    stepId: WorkspaceLifecycleStepId,
    status: WorkspaceLifecycleStep['status']
  ): void;
};

/** A mutable record store behind the read-only port: step writes land like the real writer. */
function harness(
  records: DurableWorkspaceRecord[],
  executors: Partial<BackgroundStepExecutors>
): Harness {
  const byId = new Map(records.map((record) => [record.id, record]));
  const stepWrites: Harness['stepWrites'] = [];
  const clock = new ManualClock(100_000);
  const deps: BackgroundStepRunnerDeps = {
    records: {
      get: (id) => byId.get(id),
      list: () => [...byId.values()],
    },
    steps: {
      update: async (id, stepId, state: BackgroundStepState) => {
        stepWrites.push({ id, stepId, status: state.status });
        const record = byId.get(id);
        if (!record) return;
        const lifecycle = record.lifecycle ?? { steps: [], preservePatterns: [] };
        const previous = getLifecycleStep(lifecycle, stepId);
        byId.set(id, {
          ...record,
          lifecycle: withLifecycleStep(lifecycle, {
            ...step(stepId, state.status),
            ...(state.message !== undefined ? { message: state.message } : {}),
            params: state.params ?? previous?.params ?? {},
          }),
        });
      },
    },
    scans: { mute: () => () => undefined, settle: () => undefined },
    git: createRegistryGitContext(),
    executors: {
      copy: async () => ({ status: 'skipped', reason: 'unused' }),
      push: async () => ({ status: 'succeeded' }),
      fetch: async () => ({ status: 'succeeded' }),
      ...executors,
    },
    clock,
  };
  const setStep: Harness['setStep'] = (id, stepId, status) => {
    const record = byId.get(id);
    if (!record) return;
    const lifecycle = record.lifecycle ?? { steps: [], preservePatterns: [] };
    const previous = getLifecycleStep(lifecycle, stepId);
    byId.set(id, {
      ...record,
      lifecycle: withLifecycleStep(lifecycle, step(stepId, status, previous?.params)),
    });
  };
  return { runner: new BackgroundStepRunner(deps), stepWrites, clock, setStep };
}

describe('BackgroundStepRunner', () => {
  it.each<[string, CopyArtifactsOutcome]>([
    ['succeeded', { status: 'succeeded', engine: 'cow', entries: 1, warnings: [] }],
    ['failed', { status: 'failed', message: 'no space' }],
    ['skipped', { status: 'skipped', reason: 'nothing to copy' }],
  ])('copySettled resolves when the copy settles as %s', async (_status, outcome) => {
    const { runner } = harness([repository(), worktree()], { copy: async () => outcome });
    const handle = runner.ensureRunning('ws-1');
    await expect(handle.copySettled).resolves.toBeUndefined();
    await handle.settled;
  });

  it('copySettled resolves even when the copy executor rejects — the gate never rejects', async () => {
    const { runner } = harness([repository(), worktree()], {
      copy: async () => {
        throw new Error('store write failed');
      },
    });
    const handle = runner.ensureRunning('ws-1');
    await expect(handle.copySettled).resolves.toBeUndefined();
    await handle.settled;
  });

  it('copySettled resolves immediately when copy is not part of the run', async () => {
    let releasePush = () => {};
    const { runner } = harness(
      [
        repository(),
        worktree({
          lifecycle: {
            steps: [step('copy-artifacts', 'succeeded'), step('push-branch', 'pending')],
            preservePatterns: [],
          },
        }),
      ],
      {
        push: async () => {
          await new Promise<void>((resolve) => {
            releasePush = resolve;
          });
          return { status: 'succeeded' };
        },
      }
    );
    const handle = runner.ensureRunning('ws-1');
    // The push is still wedged; the artifact gate must already be open.
    await expect(handle.copySettled).resolves.toBeUndefined();
    releasePush();
    await handle.settled;
  });

  it('an activation gate opened mid-run observes the same handle — one execution', async () => {
    let copyCalls = 0;
    let releaseCopy = () => {};
    const { runner } = harness([repository(), worktree()], {
      copy: async () => {
        copyCalls += 1;
        await new Promise<void>((resolve) => {
          releaseCopy = resolve;
        });
        return { status: 'succeeded', engine: 'cow', entries: 1, warnings: [] };
      },
    });
    const handle = runner.ensureRunning('ws-1');
    // Wait until the copy is genuinely in flight before opening the gate.
    await new Promise((resolve) => setTimeout(resolve, 10));
    let gateOpen = false;
    const gate = runner.awaitArtifactCopy('ws-1').then(() => {
      gateOpen = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(gateOpen).toBe(false);

    releaseCopy();
    await gate;
    await handle.settled;
    expect(copyCalls).toBe(1);
  });

  it('retry of a non-failed step no-ops — no execution, no step writes', async () => {
    let copyCalls = 0;
    const { runner, stepWrites } = harness(
      [
        repository(),
        worktree({
          lifecycle: { steps: [step('copy-artifacts', 'succeeded')], preservePatterns: ['.env'] },
        }),
      ],
      {
        copy: async () => {
          copyCalls += 1;
          return { status: 'succeeded', engine: 'cow', entries: 1, warnings: [] };
        },
      }
    );
    await runner.retry('ws-1', 'copy-artifacts');
    expect(copyCalls).toBe(0);
    expect(stepWrites).toEqual([]);
  });

  it('replays and retries a push against its durably recorded remote', async () => {
    const targets: Array<{ branch: string; remote?: string }> = [];
    const record = worktree({
      lifecycle: {
        steps: [step('push-branch', 'pending', { branch: 'feature/x', remote: 'fork' })],
        preservePatterns: [],
      },
    });
    const { runner, setStep } = harness([repository(), record], {
      push: async ({ branch, remote }) => {
        targets.push({ branch, ...(remote !== undefined && { remote }) });
        return { status: 'succeeded' };
      },
    });

    await runner.ensureRunning('ws-1').settled;
    setStep('ws-1', 'push-branch', 'failed');
    await runner.retry('ws-1', 'push-branch');

    expect(targets).toEqual([
      { branch: 'feature/x', remote: 'fork' },
      { branch: 'feature/x', remote: 'fork' },
    ]);
  });

  it('an activation landing mid-retry coalesces onto the retry single-flight', async () => {
    let copyCalls = 0;
    let releaseCopy = () => {};
    const { runner } = harness(
      [
        repository(),
        worktree({
          lifecycle: { steps: [step('copy-artifacts', 'failed')], preservePatterns: ['.env'] },
        }),
      ],
      {
        copy: async () => {
          copyCalls += 1;
          await new Promise<void>((resolve) => {
            releaseCopy = resolve;
          });
          return { status: 'succeeded', engine: 'cow', entries: 1, warnings: [] };
        },
      }
    );
    const retrying = runner.retry('ws-1', 'copy-artifacts');
    // Wait for the retry to mark the step running (the durable write lands first).
    await new Promise((resolve) => setTimeout(resolve, 10));
    let gateOpen = false;
    const gate = runner.awaitArtifactCopy('ws-1').then(() => {
      gateOpen = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(gateOpen).toBe(false);

    releaseCopy();
    await Promise.all([retrying, gate]);
    // The activation gate rode the retry's run instead of spawning a second copy.
    expect(copyCalls).toBe(1);
  });

  it('a failed fetch leaves lastFetchAt unset — the next fetch attempts for real', async () => {
    const outcomes: Array<'failed' | 'succeeded'> = [];
    let nextResult: 'failed' | 'succeeded' = 'failed';
    const record = worktree({
      lifecycle: { steps: [step('fetch-refs', 'pending')], preservePatterns: [] },
    });

    const { runner, stepWrites, setStep } = harness([repository(), record], {
      fetch: async () => {
        outcomes.push(nextResult);
        return nextResult === 'failed'
          ? { status: 'failed', message: 'offline' }
          : { status: 'succeeded' };
      },
    });
    await runner.ensureRunning('ws-1').settled;
    expect(outcomes).toEqual(['failed']);

    // Same debounce window: only a success stamps, so the next run fetches for real.
    nextResult = 'succeeded';
    setStep('ws-1', 'fetch-refs', 'pending');
    await runner.ensureRunning('ws-1').settled;
    expect(outcomes).toEqual(['failed', 'succeeded']);

    // Now stamped: a third run inside the window skips without calling the executor.
    setStep('ws-1', 'fetch-refs', 'pending');
    await runner.ensureRunning('ws-1').settled;
    expect(outcomes).toEqual(['failed', 'succeeded']);
    expect(stepWrites.at(-1)).toEqual({ id: 'ws-1', stepId: 'fetch-refs', status: 'skipped' });
  });

  it('writes each step running-then-outcome through the steps port, chain order per step', async () => {
    const { runner, stepWrites } = harness(
      [
        repository(),
        worktree({
          lifecycle: {
            steps: [
              step('copy-artifacts', 'pending'),
              step('push-branch', 'pending'),
              step('fetch-refs', 'pending'),
            ],
            preservePatterns: ['.env'],
          },
        }),
      ],
      {
        copy: async () => ({ status: 'succeeded', engine: 'cow', entries: 2, warnings: [] }),
        push: async () => ({ status: 'failed', message: 'no remote' }),
        fetch: async () => ({ status: 'succeeded' }),
      }
    );
    await runner.ensureRunning('ws-1').settled;

    const sequence = (stepId: WorkspaceLifecycleStepId) =>
      stepWrites.filter((write) => write.stepId === stepId).map((write) => write.status);
    expect(sequence('copy-artifacts')).toEqual(['running', 'succeeded']);
    expect(sequence('push-branch')).toEqual(['running', 'failed']);
    expect(sequence('fetch-refs')).toEqual(['running', 'succeeded']);
  });
});

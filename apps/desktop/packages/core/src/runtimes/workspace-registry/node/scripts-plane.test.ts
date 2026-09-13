import { createController } from '@emdash/wire/rpc';
import { cell, expose, family, type Cell } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// oxlint-disable-next-line emdash/core-module-boundaries -- the registry sequences lifecycle scripts through the scripts runtime (activation-scripts-via-terminals spec); the contract has no services-level home yet
import { scriptsContract } from '#runtimes/scripts/api';
// oxlint-disable-next-line emdash/core-module-boundaries -- see above
import type { ScriptRuns, ScriptRunState } from '#runtimes/scripts/api';
import { ScriptRunsObserver, type ObservedScriptRun } from './scripts-plane';

// Unit tests for the observation seam: the observer surfaces run transitions exactly
// once, and a run vanishing from the model without settling (a scripts worker
// restart) surfaces as a synthetic cancelled transition.

async function eventually(assertion: () => void, timeoutMs = 5_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
  }
}

function run(partial: Partial<ScriptRunState> & Pick<ScriptRunState, 'runId'>): ScriptRunState {
  return {
    script: 'setup',
    provenance: 'manual',
    status: 'running',
    startedAt: 1,
    outputTail: '',
    ...partial,
  };
}

describe('ScriptRunsObserver', () => {
  const states = family<{ workspacePath: string }, Cell<ScriptRuns>>(() => cell<ScriptRuns>({}), {
    name: 'fake-script-runs',
  });
  let wire: TestWire<typeof scriptsContract>;
  let observer: ScriptRunsObserver;
  let seen: ObservedScriptRun[];

  beforeEach(() => {
    seen = [];
    const runsHost = expose(scriptsContract.runs, {
      current: (key, scope) => {
        scope.add(states.retain(key));
        return states(key);
      },
    });
    const unused = () => {
      throw new Error('not exercised by these tests');
    };
    wire = createTestWire(
      scriptsContract,
      createController(scriptsContract, {
        runs: runsHost,
        output: unused,
        start: unused,
        wait: unused,
        stop: unused,
        sendInput: unused,
        resize: unused,
      })
    );
    observer = new ScriptRunsObserver({
      client: wire.client,
      onRun: (observedRun) => seen.push(observedRun),
    });
  });

  afterEach(() => {
    observer.dispose();
    wire.dispose();
    vi.restoreAllMocks();
  });

  it('surfaces each run transition once and ignores repeats', async () => {
    observer.sync(new Set(['/ws/a']));
    states({ workspacePath: '/ws/a' }).update(() => ({ setup: run({ runId: 'r1' }) }));
    await eventually(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toMatchObject({
      workspacePath: '/ws/a',
      script: 'setup',
      status: 'running',
      provenance: 'manual',
    });

    // Same runId + status again (e.g. an output-tail update): no new transition.
    states({ workspacePath: '/ws/a' }).update(() => ({
      setup: run({ runId: 'r1', outputTail: 'chatter' }),
    }));
    states({ workspacePath: '/ws/a' }).update(() => ({
      setup: run({ runId: 'r1', status: 'succeeded', finishedAt: 2 }),
    }));
    await eventually(() => expect(seen).toHaveLength(2));
    expect(seen[1]).toMatchObject({ status: 'succeeded' });
  });

  it('a running run vanishing from the model settles as cancelled (worker restart)', async () => {
    observer.sync(new Set(['/ws/a']));
    states({ workspacePath: '/ws/a' }).update(() => ({ run: run({ runId: 'r1', script: 'run' }) }));
    await eventually(() => expect(seen).toHaveLength(1));

    states({ workspacePath: '/ws/a' }).update(() => ({}));
    await eventually(() => expect(seen).toHaveLength(2));
    expect(seen[1]).toMatchObject({
      script: 'run',
      runId: 'r1',
      status: 'cancelled',
      message: 'Interrupted by a scripts runtime restart',
    });
  });

  it('a settled run vanishing from the model is not a cancellation', async () => {
    observer.sync(new Set(['/ws/a']));
    states({ workspacePath: '/ws/a' }).update(() => ({
      setup: run({ runId: 'r1', status: 'failed', finishedAt: 2 }),
    }));
    await eventually(() => expect(seen).toHaveLength(1));

    states({ workspacePath: '/ws/a' }).update(() => ({}));
    // Nothing further: removal of a settled run (workspace removal) is silent.
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(seen).toHaveLength(1);
  });

  it('unsynced paths stop being observed', async () => {
    observer.sync(new Set(['/ws/a']));
    states({ workspacePath: '/ws/a' }).update(() => ({ setup: run({ runId: 'r1' }) }));
    await eventually(() => expect(seen).toHaveLength(1));

    observer.sync(new Set());
    states({ workspacePath: '/ws/a' }).update(() => ({
      setup: run({ runId: 'r1', status: 'succeeded', finishedAt: 2 }),
    }));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(seen).toHaveLength(1);
  });
});

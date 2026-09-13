import { hostDependenciesContract } from '@emdash/core/services/host-dependencies/node';
import { err } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createAgentOperations } from './controller';

const runRuntimeLiveJob = vi.hoisted(() => vi.fn());

vi.mock('@core/services/runtime-clients/node/live-job', () => ({
  runRuntimeLiveJob,
}));

describe('createAgentOperations update routing', () => {
  beforeEach(() => {
    runRuntimeLiveJob.mockReset();
    runRuntimeLiveJob.mockResolvedValue(err({ type: 'no-update-command', id: 'codex' }));
  });

  it('routes package-manager updates through the install command job', async () => {
    const runInstallCommand = {};
    const manager = { runInstallCommand };
    const operations = createOperations();

    await operations.update('codex', undefined, 'npm', true, manager as never);

    expect(runRuntimeLiveJob).toHaveBeenCalledWith(
      hostDependenciesContract.runInstallCommand,
      runInstallCommand,
      {
        id: 'codex',
        method: 'npm',
        elevate: true,
        commandKind: 'update',
      },
      undefined,
      { signal: undefined }
    );
  });

  it('routes cli updates through the unelevated self-update job', async () => {
    const runSelfUpdateCommand = {};
    const manager = { runSelfUpdateCommand };
    const operations = createOperations();

    await operations.update('claude', undefined, undefined, undefined, manager as never);

    expect(runRuntimeLiveJob).toHaveBeenCalledWith(
      hostDependenciesContract.runSelfUpdateCommand,
      runSelfUpdateCommand,
      { id: 'claude' },
      undefined,
      { signal: undefined }
    );
  });

  it('forwards cancellation and progress context to the runtime job', async () => {
    const runInstallCommand = {};
    const manager = { runInstallCommand };
    const operations = createOperations();
    const signal = new AbortController().signal;
    const progress = vi.fn();

    await operations.install('codex', undefined, 'npm', false, manager as never, {
      signal,
      progress,
    });

    expect(runRuntimeLiveJob).toHaveBeenCalledWith(
      hostDependenciesContract.runInstallCommand,
      runInstallCommand,
      { id: 'codex', method: 'npm', elevate: false },
      progress,
      { signal }
    );
  });
});

function createOperations() {
  return createAgentOperations({
    ensureAgentDependenciesProbed: vi.fn(),
    getDependencyManager: vi.fn(),
    providerOverrideSettings: {} as never,
  });
}

import { deferred } from '@emdash/shared/testing';
import type { LiveSource } from '@emdash/wire/rpc';
import { flushStateTurn } from '@emdash/wire/state';
import { describe, expect, it, vi } from 'vitest';
import type { IExecutionContext } from '#primitives/exec/api';
import type {
  HostDependencyDefinition,
  HostDependencySnapshot,
  HostElevation,
} from '#primitives/host-dependencies/api';
import { createMemoryKeyValueStore } from '#primitives/kv/api';
import { HostDependenciesRuntime } from './runtime';

const aptCommandPrefix = 'DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60';
const aptUpdateCommand = `${aptCommandPrefix} update`;
const aptInstallCommand = (packages: string) => `${aptCommandPrefix} install -y ${packages}`;
const aptPreviewCommand = (packages: string) =>
  `${aptUpdateCommand} && ${aptInstallCommand(packages)}`;

const definition: HostDependencyDefinition = {
  id: 'fake-agent',
  name: 'Fake Agent',
  category: 'agent',
  binaryNames: ['fake-agent'],
  installCommands: {
    macos: [npmOption()],
    linux: [npmOption()],
  },
  status: 'active',
};

const elevatedDefinition: HostDependencyDefinition = {
  id: 'git',
  name: 'Git',
  category: 'core',
  binaryNames: ['git'],
  installCommands: {
    linux: [aptOption('git')],
    macos: [aptOption('git')],
  },
  status: 'active',
};

const neverElevateDefinition: HostDependencyDefinition = {
  id: 'brew-tool',
  name: 'Brew Tool',
  category: 'agent',
  binaryNames: ['brew-tool'],
  installCommands: {
    macos: [
      {
        method: 'homebrew',
        command: 'brew install brew-tool',
        recommended: true,
        elevation: 'never',
      },
    ],
    linux: [
      {
        method: 'homebrew',
        command: 'brew install brew-tool',
        recommended: true,
        elevation: 'never',
      },
    ],
  },
  status: 'active',
};

describe('HostDependenciesRuntime.runInstallCommand', () => {
  it('runs the selected install command and returns the refreshed view', async () => {
    const { exec } = createFakeExec({ installedAfterStreaming: true });
    const runtime = createRuntime(exec);
    const progress = vi.fn();

    const result = await runtime.runInstallCommand('fake-agent', 'npm', jobContext(progress));

    expect(result.success).toBe(true);
    expect(result.success && result.data.status).toBe('available');
    expect(exec.execStreaming).toHaveBeenCalledWith(
      '/bin/sh',
      ['-c', 'npm install -g fake-agent'],
      expect.any(Function),
      { signal: expect.any(AbortSignal) }
    );
    expect(exec.refreshShellEnv).toHaveBeenCalledOnce();
    expect(vi.mocked(exec.execStreaming).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(exec.refreshShellEnv!).mock.invocationCallOrder[0]!
    );
    expect(progress).toHaveBeenCalledWith({ phase: 'resolving' });
    expect(progress).toHaveBeenCalledWith({ phase: 'running' });
    expect(progress).toHaveBeenCalledWith({ phase: 'refreshing' });
  });

  it('classifies permission output for on-failure commands and offers sudo retry', async () => {
    const { exec } = createFakeExec({
      hostElevation: 'passwordless-sudo',
      exitCode: 243,
      streamOutput: 'npm error code EACCES\npermission denied, mkdir /usr/local/lib/node_modules',
    });
    const runtime = createRuntime(exec);

    const result = await runtime.runInstallCommand('fake-agent', 'npm', jobContext());

    expect(result).toEqual({
      success: false,
      error: {
        type: 'permission-denied',
        id: 'fake-agent',
        message: 'Installing fake-agent needs administrator privileges.',
        output: 'npm error code EACCES\npermission denied, mkdir /usr/local/lib/node_modules',
        exitCode: 243,
        canRetryWithSudo: true,
        elevatedCommand: "sudo -n -H /bin/sh -c 'npm install -g fake-agent'",
        interactiveCommand: "sudo /bin/sh -c 'npm install -g fake-agent'",
        command: 'npm install -g fake-agent',
      },
    });
  });

  it('keeps unrelated on-failure output as command-failed', async () => {
    const { exec } = createFakeExec({ exitCode: 127, streamOutput: 'package not found' });
    const runtime = createRuntime(exec);

    const result = await runtime.runInstallCommand('fake-agent', 'npm', jobContext());

    expect(result).toEqual({
      success: false,
      error: {
        type: 'command-failed',
        message: 'Install command exited with code 127',
        output: 'package not found',
        exitCode: 127,
      },
    });
  });

  it('does not classify permission output for never-elevated commands', async () => {
    const { exec } = createFakeExec({ exitCode: 1, streamOutput: 'Operation not permitted' });
    const runtime = createRuntime(exec, [neverElevateDefinition]);

    const result = await runtime.runInstallCommand('brew-tool', 'homebrew', jobContext());

    expect(result.success).toBe(false);
    expect(!result.success && result.error.type).toBe('command-failed');
  });

  it('fails always-elevated commands before execution when elevation is unavailable', async () => {
    const { exec } = createFakeExec({ hostElevation: 'unavailable' });
    const runtime = createRuntime(exec, [elevatedDefinition]);

    const result = await runtime.runInstallCommand('git', 'apt', jobContext());

    expect(result.success).toBe(false);
    expect(!result.success && result.error).toMatchObject({
      type: 'permission-denied',
      id: 'git',
      canRetryWithSudo: false,
      command: aptPreviewCommand('git'),
    });
    expect(exec.execStreaming).not.toHaveBeenCalled();
  });

  it('runs always-elevated commands plain as root', async () => {
    const { exec } = createFakeExec({
      hostElevation: 'root',
      installedAfterStreaming: true,
      binaryName: 'git',
    });
    const runtime = createRuntime(exec, [elevatedDefinition]);

    await runtime.runInstallCommand('git', 'apt', jobContext());

    expect(exec.execStreaming).toHaveBeenNthCalledWith(
      1,
      '/bin/sh',
      ['-c', aptUpdateCommand],
      expect.any(Function),
      expect.any(Object)
    );
    expect(exec.execStreaming).toHaveBeenNthCalledWith(
      2,
      '/bin/sh',
      ['-c', aptInstallCommand('git')],
      expect.any(Function),
      expect.any(Object)
    );
  });

  it('wraps always-elevated commands with passwordless sudo', async () => {
    const { exec } = createFakeExec({
      hostElevation: 'passwordless-sudo',
      installedAfterStreaming: true,
      binaryName: 'git',
    });
    const runtime = createRuntime(exec, [elevatedDefinition]);

    await runtime.runInstallCommand('git', 'apt', jobContext());

    expect(exec.execStreaming).toHaveBeenNthCalledWith(
      1,
      'sudo',
      ['-n', '-H', '/bin/sh', '-c', aptUpdateCommand],
      expect.any(Function),
      expect.any(Object)
    );
    expect(exec.execStreaming).toHaveBeenNthCalledWith(
      2,
      'sudo',
      ['-n', '-H', '/bin/sh', '-c', aptInstallCommand('git')],
      expect.any(Function),
      expect.any(Object)
    );
  });

  it('serializes concurrent install commands in the same method domain', async () => {
    const firstExecution = deferred<void>();
    const { exec } = createFakeExec({ initiallyInstalled: true });
    exec.execStreaming = vi.fn(async () => {
      if (vi.mocked(exec.execStreaming).mock.calls.length === 1) await firstExecution.promise;
      return { exitCode: 0 };
    });
    const runtime = createRuntime(exec);

    const first = runtime.runInstallCommand('fake-agent', 'npm', jobContext());
    await vi.waitFor(() => expect(exec.execStreaming).toHaveBeenCalledTimes(1));
    const secondProgress = vi.fn();
    const second = runtime.runInstallCommand('fake-agent', 'npm', jobContext(secondProgress));
    await vi.waitFor(() => expect(secondProgress).toHaveBeenCalledWith({ phase: 'running' }));

    expect(exec.execStreaming).toHaveBeenCalledTimes(1);
    firstExecution.resolve();
    await Promise.all([first, second]);
    expect(exec.execStreaming).toHaveBeenCalledTimes(2);
  });

  it('allows concurrent install commands in different method domains', async () => {
    const releaseExecutions = deferred<void>();
    const { exec } = createFakeExec({ initiallyInstalled: true });
    exec.execStreaming = vi.fn(async () => {
      await releaseExecutions.promise;
      return { exitCode: 0 };
    });
    const runtime = createRuntime(exec, [definition, neverElevateDefinition]);

    const npmInstall = runtime.runInstallCommand('fake-agent', 'npm', jobContext());
    const brewInstall = runtime.runInstallCommand('brew-tool', 'homebrew', jobContext());
    await vi.waitFor(() => expect(exec.execStreaming).toHaveBeenCalledTimes(2));

    releaseExecutions.resolve();
    await Promise.all([npmInstall, brewInstall]);
  });

  it('wraps an explicit on-failure retry with passwordless sudo', async () => {
    const { exec } = createFakeExec({
      hostElevation: 'passwordless-sudo',
      installedAfterStreaming: true,
    });
    const runtime = createRuntime(exec);

    await runtime.runInstallCommand('fake-agent', 'npm', jobContext(), { elevate: true });

    expect(exec.execStreaming).toHaveBeenCalledWith(
      'sudo',
      ['-n', '-H', '/bin/sh', '-c', 'npm install -g fake-agent'],
      expect.any(Function),
      expect.any(Object)
    );
  });

  it('rejects explicit elevation for never-elevated commands', async () => {
    const { exec } = createFakeExec({ hostElevation: 'passwordless-sudo' });
    const runtime = createRuntime(exec, [neverElevateDefinition]);

    const result = await runtime.runInstallCommand('brew-tool', 'homebrew', jobContext(), {
      elevate: true,
    });

    expect(result.success).toBe(false);
    expect(!result.success && result.error).toMatchObject({
      type: 'permission-denied',
      message: 'This install method does not allow administrator elevation.',
    });
    expect(exec.execStreaming).not.toHaveBeenCalled();
  });

  it('routes updates through updateCommand under the same elevation policy', async () => {
    const updateDefinition: HostDependencyDefinition = {
      ...definition,
      installCommands: {
        macos: [{ ...npmOption(), updateCommand: 'npm update -g fake-agent' }],
        linux: [{ ...npmOption(), updateCommand: 'npm update -g fake-agent' }],
      },
    };
    const { exec } = createFakeExec({ initiallyInstalled: true });
    const runtime = createRuntime(exec, [updateDefinition]);

    const result = await runtime.runInstallCommand('fake-agent', 'npm', jobContext(), {
      commandKind: 'update',
    });

    expect(result.success).toBe(true);
    expect(exec.execStreaming).toHaveBeenCalledWith(
      '/bin/sh',
      ['-c', 'npm update -g fake-agent'],
      expect.any(Function),
      expect.any(Object)
    );
  });

  it('falls back to the install command when an update command is not declared', async () => {
    const { exec } = createFakeExec({ initiallyInstalled: true });
    const runtime = createRuntime(exec);

    const result = await runtime.runInstallCommand('fake-agent', 'npm', jobContext(), {
      commandKind: 'update',
    });

    expect(result.success).toBe(true);
    expect(exec.execStreaming).toHaveBeenCalledWith(
      '/bin/sh',
      ['-c', 'npm install -g fake-agent'],
      expect.any(Function),
      expect.any(Object)
    );
  });
});

describe('HostDependenciesRuntime.runInstallBatch', () => {
  it('merges apt packages into one install command', async () => {
    const curlDefinition: HostDependencyDefinition = {
      ...elevatedDefinition,
      id: 'curl',
      name: 'curl',
      installCommands: {
        linux: [aptOption('curl')],
        macos: [aptOption('curl')],
      },
    };
    const { exec } = createFakeExec({
      hostElevation: 'root',
      installedAfterStreaming: true,
      binaryName: 'git',
    });
    const runtime = createRuntime(exec, [elevatedDefinition, curlDefinition]);

    const result = await runtime.runInstallBatch([{ id: 'git' }, { id: 'curl' }], jobContext());

    expect(result.success).toBe(true);
    expect(result.success && result.data.git?.success).toBe(true);
    expect(result.success && result.data.curl?.success).toBe(true);
    expect(exec.execStreaming).toHaveBeenCalledTimes(2);
    expect(exec.execStreaming).toHaveBeenNthCalledWith(
      1,
      '/bin/sh',
      ['-c', aptUpdateCommand],
      expect.any(Function),
      expect.any(Object)
    );
    expect(exec.execStreaming).toHaveBeenNthCalledWith(
      2,
      '/bin/sh',
      ['-c', aptInstallCommand('git curl')],
      expect.any(Function),
      expect.any(Object)
    );
  });

  it('skips apt-get update while the previous update is fresh', async () => {
    const { exec } = createFakeExec({
      hostElevation: 'root',
      initiallyInstalled: true,
      binaryName: 'git',
    });
    const runtime = createRuntime(exec, [elevatedDefinition]);

    await runtime.runInstallCommand('git', 'apt', jobContext());
    await runtime.runInstallCommand('git', 'apt', jobContext());

    expect(exec.execStreaming).toHaveBeenCalledTimes(3);
    expect(vi.mocked(exec.execStreaming).mock.calls.map(([, args]) => args)).toEqual([
      ['-c', aptUpdateCommand],
      ['-c', aptInstallCommand('git')],
      ['-c', aptInstallCommand('git')],
    ]);
  });
});

describe('HostDependenciesRuntime snapshot query', () => {
  it('prefers a host-installed binary over a project-local shim', async () => {
    const { exec } = createFakeExec({
      initiallyInstalled: true,
      dependencyProbe: () => '/workspace/node_modules/.bin/fake-agent\n/usr/local/bin/fake-agent',
    });
    const runtime = createRuntime(exec);
    const lease = runtime.liveHost().acquireState(undefined, 'current');
    const source = await lease.ready();

    const view = (await snapshotOf(source)).dependencies['fake-agent'];
    expect(view?.resolved?.path).toBe('/usr/local/bin/fake-agent');
    expect(view?.candidates.map((candidate) => candidate.path)).toEqual([
      '/usr/local/bin/fake-agent',
      '/workspace/node_modules/.bin/fake-agent',
    ]);

    await lease.release();
    runtime.dispose();
  });

  it('probes on first observation, not on construction', async () => {
    const { exec } = createFakeExec({ initiallyInstalled: true });
    const runtime = createRuntime(exec);

    expect(exec.exec).not.toHaveBeenCalled();

    const lease = runtime.liveHost().acquireState(undefined, 'current');
    const source = await lease.ready();
    const snapshot = await snapshotOf(source);
    expect(snapshot.generation).toBe(1);
    expect(snapshot.dependencies['fake-agent']?.status).toBe('available');

    await lease.release();
    runtime.dispose();
  });

  it('suppresses publishes when a re-probe returns unchanged content', async () => {
    const { exec } = createFakeExec({ initiallyInstalled: true });
    const runtime = createRuntime(exec);
    const lease = runtime.liveHost().acquireState(undefined, 'current');
    const source = await lease.ready();

    const result = await runtime.refresh();
    expect(result.success).toBe(true);
    flushStateTurn();

    const after = await snapshotOf(source);
    expect(after.generation).toBe(1);

    await lease.release();
    runtime.dispose();
  });

  it('writes install results through the observed snapshot', async () => {
    const { exec } = createFakeExec({ installedAfterStreaming: true });
    const runtime = createRuntime(exec);
    const lease = runtime.liveHost().acquireState(undefined, 'current');
    const source = await lease.ready();
    const before = await snapshotOf(source);
    expect(before.dependencies['fake-agent']?.status).toBe('missing');

    const installed = await runtime.runInstallCommand('fake-agent', 'npm', jobContext());
    expect(installed.success).toBe(true);
    flushStateTurn();

    const after = await snapshotOf(source);
    expect(after.dependencies['fake-agent']?.status).toBe('available');
    expect(after.generation).toBeGreaterThan(before.generation);

    await lease.release();
    runtime.dispose();
  });

  it('writes selection changes through the observed snapshot', async () => {
    const { exec } = createFakeExec({ initiallyInstalled: true });
    const runtime = createRuntime(exec);
    const lease = runtime.liveHost().acquireState(undefined, 'current');
    const source = await lease.ready();

    const result = await runtime.setSelection('fake-agent', {
      kind: 'path',
      path: '/usr/local/bin/fake-agent',
    });
    expect(result.success).toBe(true);
    flushStateTurn();

    const after = await snapshotOf(source);
    expect(after.dependencies['fake-agent']?.selection).toEqual({
      kind: 'path',
      path: '/usr/local/bin/fake-agent',
    });

    await lease.release();
    runtime.dispose();
  });

  it('does not let an older full probe overwrite a newer dependency write-through', async () => {
    const staleProbe = deferred<string | null>();
    const fullProbeStarted = deferred<void>();
    const { exec } = createFakeExec({
      dependencyProbe: ({ call }) => {
        if (call === 1) return null;
        if (call === 2) {
          fullProbeStarted.resolve();
          return staleProbe.promise;
        }
        return '/usr/local/bin/fake-agent';
      },
    });
    const runtime = createRuntime(exec);
    const lease = runtime.liveHost().acquireState(undefined, 'current');
    const source = await lease.ready();
    expect((await snapshotOf(source)).dependencies['fake-agent']?.status).toBe('missing');

    const fullRefresh = runtime.refresh();
    await fullProbeStarted.promise;

    const partialRefresh = await runtime.refresh('fake-agent');
    expect(partialRefresh.success && partialRefresh.data.dependencies['fake-agent']?.status).toBe(
      'available'
    );

    staleProbe.resolve(null);
    await fullRefresh;
    flushStateTurn();

    expect((await snapshotOf(source)).dependencies['fake-agent']?.status).toBe('available');

    await lease.release();
    runtime.dispose();
  });

  it('re-probes when demand returns after the exposed snapshot linger expires', async () => {
    vi.useFakeTimers();
    const { exec, setInstalled } = createFakeExec({ initiallyInstalled: false });
    const runtime = createRuntime(exec);
    const host = runtime.liveHost();

    try {
      const warmed = await host.runMutation('refresh', {
        key: undefined,
        input: {},
        mutationId: 'background-refresh',
      });
      expect(warmed.success && warmed.data.data.dependencies['fake-agent']?.status).toBe('missing');

      await vi.advanceTimersByTimeAsync(15_000);
      setInstalled(true);

      const lease = host.acquireState(undefined, 'current');
      const sourcePromise = lease.ready();
      await vi.advanceTimersByTimeAsync(0);
      const source = await sourcePromise;

      expect((await snapshotOf(source)).dependencies['fake-agent']?.status).toBe('available');

      await lease.release();
    } finally {
      runtime.dispose();
      vi.useRealTimers();
    }
  });
});

describe('HostDependenciesRuntime.refresh', () => {
  it.each([
    ['root', 'root'],
    ['passwordless-sudo', 'passwordless-sudo'],
    ['unavailable', 'unavailable'],
  ] as const)('reports %s host elevation', async (hostElevation, expected) => {
    const { exec } = createFakeExec({ hostElevation });
    const runtime = createRuntime(exec);

    const result = await runtime.refresh();

    expect(result.success && result.data.hostElevation).toBe(expected);
  });
});

function npmOption() {
  return {
    method: 'npm' as const,
    command: 'npm install -g fake-agent',
    recommended: true,
    elevation: 'on-failure' as const,
  };
}

function aptOption(packages: string) {
  return {
    method: 'apt' as const,
    command: aptPreviewCommand(packages),
    packages: packages.split(' '),
    recommended: true,
    elevation: 'always' as const,
  };
}

function jobContext(progress = vi.fn()) {
  return { signal: new AbortController().signal, progress };
}

async function snapshotOf(source: LiveSource): Promise<HostDependencySnapshot> {
  return (await source.snapshot()).data as HostDependencySnapshot;
}

function createRuntime(
  exec: IExecutionContext,
  definitions: HostDependencyDefinition[] = [definition]
): HostDependenciesRuntime {
  return new HostDependenciesRuntime({
    hostId: 'test-host',
    definitions,
    store: createMemoryKeyValueStore(),
    exec,
  });
}

function createFakeExec(options: {
  installedAfterStreaming?: boolean;
  initiallyInstalled?: boolean;
  exitCode?: number;
  installerMissing?: boolean;
  hostElevation?: HostElevation;
  binaryName?: string;
  streamOutput?: string;
  dependencyProbe?: (context: {
    call: number;
    installed: boolean;
  }) => string | null | Promise<string | null>;
}): { exec: IExecutionContext; setInstalled(installed: boolean): void } {
  let installed = options.initiallyInstalled ?? false;
  let dependencyProbeCall = 0;
  const binaryName = options.binaryName ?? 'fake-agent';
  const hostElevation = options.hostElevation ?? 'unavailable';
  const exec: IExecutionContext = {
    root: '',
    supportsLocalSpawn: true,
    exec: vi.fn(async (command, args = []) => {
      if (command === 'id' && args[0] === '-u') {
        return { stdout: hostElevation === 'root' ? '0\n' : '1000\n', stderr: '' };
      }
      if (command === 'which' && args[0] === 'sudo') {
        if (hostElevation === 'unavailable') throw new Error('not found');
        return { stdout: '/usr/bin/sudo\n', stderr: '' };
      }
      if (command === '/usr/bin/sudo' && args[0] === '-n' && args[1] === 'true') {
        if (hostElevation !== 'passwordless-sudo') throw new Error('sudo unavailable');
        return { stdout: '', stderr: '' };
      }
      if (command === 'which' && ['npm', 'apt-get', 'brew'].includes(args[0] ?? '')) {
        if (options.installerMissing) throw new Error('not found');
        return { stdout: `/usr/bin/${args[0]}\n`, stderr: '' };
      }
      if (command === 'which' && args[0] === '-a' && args[1] === binaryName) {
        if (options.dependencyProbe) {
          const path = await options.dependencyProbe({
            call: ++dependencyProbeCall,
            installed,
          });
          if (!path) throw new Error('not found');
          return { stdout: `${path}\n`, stderr: '' };
        }
        if (!installed) throw new Error('not found');
        return { stdout: `/usr/local/bin/${binaryName}\n`, stderr: '' };
      }
      if (command === 'realpath' && args[0] === `/usr/local/bin/${binaryName}`) {
        return { stdout: `/usr/local/bin/${binaryName}\n`, stderr: '' };
      }
      throw new Error(`Unexpected exec: ${command} ${args.join(' ')}`);
    }),
    execStreaming: vi.fn(async (_command, _args, onChunk) => {
      onChunk(options.streamOutput ?? 'install output');
      const exitCode = options.exitCode ?? 0;
      if (exitCode === 0) installed = options.installedAfterStreaming ?? installed;
      return { exitCode };
    }),
    refreshShellEnv: vi.fn(async () => {}),
    dispose: vi.fn(),
  };
  return {
    exec,
    setInstalled(value) {
      installed = value;
    },
  };
}

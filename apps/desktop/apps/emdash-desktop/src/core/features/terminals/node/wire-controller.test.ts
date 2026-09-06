import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import type { LiveSource } from '@emdash/wire/rpc';
import { encodeTopic } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { terminalsContract } from '../api';
import type { TerminalsRuntimeBroker } from '../api/runtime-adapter';
import { createTerminalsWireController } from './wire-controller';

const identity = {
  projectId: 'project-1',
  workspaceId: 'workspace-1',
  host: LOCAL_HOST_REF,
  path: '/repo/worktree',
} as const;
const controllerDeps = {
  db: {} as never,
  logger: { warn: vi.fn() } as never,
  projects: { requireAttached: vi.fn(() => ok({} as never)) },
  settings: { get: vi.fn(async () => ({ defaultShell: 'default' })) } as never,
  telemetry: { capture: vi.fn() } as never,
  terminalShell: {
    getColorEnv: vi.fn(async () => ({})),
  } as never,
  resolveSessionGitCredentials: vi.fn(async () => undefined),
};

describe('createTerminalsWireController', () => {
  it('translates terminal ids through the resolved client', async () => {
    const sendInput = vi.fn(async () => ok(undefined));
    const client = vi.fn(async () => ok({ terminals: { sendInput } }));
    const controller = createTerminalsWireController({
      ...controllerDeps,
      runtimes: { client } as unknown as TerminalsRuntimeBroker,
      workspaceIdentity: { resolve: vi.fn(async () => identity) },
    });

    await expect(
      controller.call('sendInput', {
        workspaceId: identity.workspaceId,
        terminalId: 'pty:project-1:task-1:terminal-1',
        data: 'echo ready\r',
      })
    ).resolves.toEqual(ok(undefined));

    expect(sendInput).toHaveBeenCalledWith(
      {
        key: {
          workspace: hostFileRefFromNativePath(identity.path),
          id: 'pty:project-1:task-1:terminal-1',
        },
        data: 'echo ready\r',
      },
      {}
    );
    expect(client).toHaveBeenCalledOnce();
  });

  it('returns RuntimeResolveError from fallible terminal procedures', async () => {
    const remoteHost = hostRef('remote', 'ssh-1');
    const resolveError = {
      type: 'host-unavailable' as const,
      host: remoteHost,
      reason: 'runtime-unavailable' as const,
      message: 'Remote runtime sessions are not enabled',
    };
    const controller = createTerminalsWireController({
      ...controllerDeps,
      runtimes: {
        client: async () => err(resolveError),
      } as unknown as TerminalsRuntimeBroker,
      workspaceIdentity: {
        resolve: vi.fn(async () => ({ ...identity, host: remoteHost })),
      },
    });

    await expect(
      controller.call('sendInput', {
        workspaceId: identity.workspaceId,
        terminalId: 'pty:project-1:task-1:terminal-1',
        data: 'echo ready\r',
      })
    ).resolves.toEqual(err(resolveError));
  });

  it('resolves shell availability against the requested host runtime', async () => {
    const availability = [
      { id: 'system' as const, label: 'zsh', isSystemDefault: true, available: true },
    ];
    const getShellAvailability = vi.fn(async () => ok(availability));
    const remoteHost = hostRef('remote', 'ssh-1');
    const client = vi.fn(async () => ok({ terminals: { getShellAvailability } }));
    const controller = createTerminalsWireController({
      ...controllerDeps,
      runtimes: { client } as unknown as TerminalsRuntimeBroker,
      workspaceIdentity: { resolve: vi.fn() },
    });

    await expect(controller.call('getShellAvailability', { host: remoteHost })).resolves.toEqual(
      ok(availability)
    );
    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(getShellAvailability).toHaveBeenCalledWith(undefined);
  });

  it('surfaces RuntimeResolveError when the availability host is unreachable', async () => {
    const remoteHost = hostRef('remote', 'ssh-1');
    const resolveError = {
      type: 'host-unavailable' as const,
      host: remoteHost,
      reason: 'runtime-unavailable' as const,
      message: 'Remote runtime sessions are not enabled',
    };
    const controller = createTerminalsWireController({
      ...controllerDeps,
      runtimes: {
        client: async () => err(resolveError),
      } as unknown as TerminalsRuntimeBroker,
      workspaceIdentity: { resolve: vi.fn() },
    });

    await expect(controller.call('getShellAvailability', { host: remoteHost })).resolves.toEqual(
      err(resolveError)
    );
  });

  it('starts terminals with registry shell setup and DB placement tmux', async () => {
    const terminalRow = {
      id: 'terminal-1',
      projectId: identity.projectId,
      taskId: 'task-1',
      name: 'Terminal',
      shellId: 'default',
      ssh: 0,
    };
    const taskRow = {
      id: 'task-1',
      projectId: identity.projectId,
      workspaceId: identity.workspaceId,
      name: 'Task one',
    };
    const select = vi
      .fn()
      .mockReturnValueOnce(selecting(terminalRow))
      .mockReturnValueOnce(selecting(taskRow));
    const getProjectConfig = vi.fn(async () =>
      ok({
        resolved: {
          preservePatterns: { value: [], from: 'built-in' as const },
          shellSetup: { value: 'source .workspace-env', from: 'team' as const },
          autoRunSetup: { value: true, from: 'built-in' as const },
          autoRunRun: { value: false, from: 'built-in' as const },
        },
      })
    );
    const resolveTmux = vi.fn(async () => ({
      value: true,
      provenance: { kind: 'set' as const },
    }));
    const start = vi.fn(async () => ok(undefined));
    const runtime = {
      workspaceRegistry: { getProjectConfig },
      terminals: { start },
    };
    const requireAttached = vi.fn(() =>
      ok({
        projectId: identity.projectId,
        repoPath: '/repo',
        settings: {
          resolveTmux,
          getStoredGitSettings: vi.fn(async () => ({
            defaultBranch: { remote: null, branch: 'main' },
          })),
          getPlacementContext: vi.fn(async () => ({
            hostWorktreeRoot: null,
            builtInWorktreeRoot: '/tmp/worktrees',
            homeDirectory: '/tmp',
            hostTmux: null,
            appDefaultTmux: false,
          })),
        },
        repoFacts: {
          get: vi.fn(async () => ({ remotes: [], localBranches: ['main'] })),
        },
      })
    );
    const controller = createTerminalsWireController({
      ...controllerDeps,
      db: { select } as never,
      projects: { requireAttached } as never,
      runtimes: {
        client: vi.fn(async () => ok(runtime)),
      } as unknown as TerminalsRuntimeBroker,
      workspaceIdentity: { resolve: vi.fn(async () => identity) },
    });

    await expect(
      controller.call('hydrate', {
        projectId: identity.projectId,
        taskId: taskRow.id,
        terminalId: terminalRow.id,
      })
    ).resolves.toEqual(
      ok({
        key: {
          workspaceId: identity.workspaceId,
          terminalId: `${identity.projectId}:${taskRow.id}:${terminalRow.id}`,
        },
      })
    );
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        spec: expect.objectContaining({
          shellSetup: 'source .workspace-env',
          tmux: true,
          env: expect.objectContaining({ EMDASH_DEFAULT_BRANCH: 'main' }),
        }),
      })
    );
    expect(getProjectConfig).toHaveBeenCalledWith({ workspaceId: identity.workspaceId });
    expect(requireAttached).toHaveBeenCalledWith(identity.projectId);
    expect(resolveTmux).toHaveBeenCalledOnce();
  });

  it('resolves the output source for the workspace host', async () => {
    const source = liveSource();
    const handle = vi.fn(() => ({ asLiveSource: () => source }));
    const controller = createTerminalsWireController({
      ...controllerDeps,
      runtimes: {
        client: async () => ok({ terminals: { output: { handle } } }),
      } as unknown as TerminalsRuntimeBroker,
      workspaceIdentity: { resolve: vi.fn(async () => identity) },
    });
    const key = {
      workspaceId: identity.workspaceId,
      terminalId: 'pty:project-1:task-1:terminal-1',
    };
    const lease = controller.acquireLive(encodeTopic(terminalsContract.output.id, key));

    const output = await lease?.ready();
    const unsubscribe = await output?.subscribe(vi.fn());
    expect(handle).toHaveBeenCalledWith({
      workspace: hostFileRefFromNativePath(identity.path),
      id: key.terminalId,
    });

    unsubscribe?.();
    await lease?.release();
  });
});

function liveSource(): LiveSource {
  return {
    snapshot: async () => ({
      generation: 1,
      sequence: 0,
      timestamp: 0,
      data: { baseOffset: 0, text: '', truncated: false },
    }),
    subscribe: () => () => {},
  };
}

function selecting<T>(row: T) {
  return {
    from: () => ({
      where: () => ({
        limit: async () => [row],
      }),
    }),
  };
}

import path from 'node:path';
import { createStubLogger, deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import type { AgentPluginHost, ITrustBehavior } from '#services/agent-plugins/api/plugins';
import { TuiWorkspaceTrust } from './workspace-trust';

describe('TuiWorkspaceTrust', () => {
  it('does nothing when the provider has no trust behavior', async () => {
    const { trust, agentHost, logs } = createTrust();

    await trust.ensureTrusted({ providerId: 'test', workspacePath: '/workspace' });

    expect(agentHost.get).toHaveBeenCalledWith('test');
    expect(logs).toEqual([]);
  });

  it('refuses non-absolute workspace paths', async () => {
    const trustWorkspace = vi.fn(async () => {});
    const { trust, logs } = createTrust({ trustWorkspace });

    await trust.ensureTrusted({ providerId: 'test', workspacePath: 'relative/workspace' });

    expect(trustWorkspace).not.toHaveBeenCalled();
    expect(logs).toContainEqual({
      level: 'warn',
      message: 'TuiWorkspaceTrust: refusing to trust non-absolute workspace path',
      fields: {
        providerId: 'test',
        workspacePath: 'relative/workspace',
      },
    });
  });

  it('logs and swallows trust behavior failures', async () => {
    const { trust, logs } = createTrust({
      trustWorkspace: vi.fn(async () => {
        throw new Error('boom');
      }),
    });

    await expect(
      trust.ensureTrusted({ providerId: 'test', workspacePath: '/workspace/../worktree' })
    ).resolves.toBeUndefined();

    expect(logs).toContainEqual({
      level: 'warn',
      message: 'TuiWorkspaceTrust: failed to trust workspace',
      fields: {
        providerId: 'test',
        workspacePath: path.normalize('/workspace/../worktree'),
        error: 'Error: boom',
      },
    });
  });

  it('serializes writes to the shared home configuration', async () => {
    const firstStarted = deferred<void>();
    const releaseFirst = deferred<void>();
    const workspacePaths: string[] = [];
    const trustWorkspace = vi.fn(async (_fs, context) => {
      workspacePaths.push(context.workspacePath);
      if (workspacePaths.length === 1) {
        firstStarted.resolve();
        await releaseFirst.promise;
      }
    });
    const { trust } = createTrust({ trustWorkspace });

    const first = trust.ensureTrusted({ providerId: 'test', workspacePath: '/workspace/one' });
    await firstStarted.promise;
    const second = trust.ensureTrusted({ providerId: 'test', workspacePath: '/workspace/two' });

    await Promise.resolve();
    expect(workspacePaths).toEqual(['/workspace/one']);

    releaseFirst.resolve();
    await Promise.all([first, second]);
    expect(workspacePaths).toEqual(['/workspace/one', '/workspace/two']);
  });
});

function createTrust(behavior?: ITrustBehavior) {
  const { logger, calls: logs } = createStubLogger();
  const agentHost = {
    homeDir: '/home/test-user',
    get: vi.fn(() => ({ behavior: behavior ? { trust: behavior } : {} })),
  } as unknown as AgentPluginHost;
  return {
    agentHost,
    logs,
    trust: new TuiWorkspaceTrust({ agentHost, logger }),
  };
}

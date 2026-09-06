import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it } from 'vitest';
import { makeAcpHarness } from '../acp-test-support';
import { discoverModels } from './discover-models';

describe('provider model discovery', () => {
  it('returns new and grouped provider models without a prompt, then releases the process', async () => {
    const { deps, agent, fakeHost } = makeAcpHarness();
    const scope = createScope({ label: 'discovery-test' });
    agent.newSession.mockResolvedValue({
      sessionId: 'discovery',
      configOptions: [
        {
          id: 'model',
          category: 'model',
          type: 'select',
          name: 'Model',
          currentValue: 'future-model',
          options: [
            {
              group: 'latest',
              name: 'Latest',
              options: [{ value: 'future-model', name: 'Future model' }],
            },
          ],
        },
      ],
    });
    try {
      expect(await discoverModels(deps, scope, { providerId: 'claude' })).toEqual([
        { id: 'future-model', name: 'Future model' },
      ]);
      expect(agent.prompt).not.toHaveBeenCalled();
      expect(agent.initialize).toHaveBeenCalledWith(
        expect.objectContaining({ clientCapabilities: {} })
      );
      expect(fakeHost.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
      expect(await agent.capturedClient?.requestPermission({} as never)).toEqual({
        outcome: { outcome: 'cancelled' },
      });
    } finally {
      await scope.dispose();
    }
  });

  it('releases the process when discovery times out', async () => {
    const { deps, agent, fakeHost } = makeAcpHarness();
    const scope = createScope({ label: 'discovery-test' });
    agent.newSession.mockImplementation(() => new Promise(() => {}));
    try {
      await expect(discoverModels(deps, scope, { providerId: 'claude' }, 20)).rejects.toThrow(
        'timed out'
      );
      expect(fakeHost.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
      expect(agent.prompt).not.toHaveBeenCalled();
    } finally {
      await scope.dispose();
    }
  });

  it('supports older providers that return a legacy models list', async () => {
    const { deps, agent } = makeAcpHarness();
    const scope = createScope({ label: 'discovery-test' });
    agent.newSession.mockResolvedValue({
      sessionId: 'discovery',
      models: {
        availableModels: [{ modelId: 'new-release', name: 'New release' }],
      },
    });
    try {
      expect(await discoverModels(deps, scope, { providerId: 'claude' })).toEqual([
        { id: 'new-release', name: 'New release' },
      ]);
    } finally {
      await scope.dispose();
    }
  });
});

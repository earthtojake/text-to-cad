import { hostRef } from '@emdash/core/primitives/host/api';
import { ok } from '@emdash/shared';
import type { LiveSource } from '@emdash/wire/rpc';
import { encodeTopic } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { skillsContract } from '../api';
import { createSkillsWireController } from './wire-controller';

const remoteHost = hostRef('remote', 'ssh-3');

describe('createSkillsWireController', () => {
  it('forwards skill procedures to the selected host', async () => {
    const installSkill = vi.fn(async () => ok({ skills: [] }));
    const client = vi.fn(async () => ok({ agentConfig: { installSkill } }));
    const controller = createSkillsWireController({ runtimes: { client } as never });
    const skill = {
      id: 'review-code',
      skillMdContent: '# Review code',
      source: 'local' as const,
    };

    await expect(controller.call('install', { host: remoteHost, skill })).resolves.toEqual(
      ok({ skills: [] })
    );

    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(installSkill).toHaveBeenCalledWith({ skill }, {});
  });

  it('resolves the host for the installed-skills model', async () => {
    const source = liveSource([]);
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const controller = createSkillsWireController({
      runtimes: {
        client: async () => ok({ agentConfig: { skills: { state } } }),
      } as never,
    });
    const topic = encodeTopic(skillsContract.installed.states.list.id, { host: remoteHost });

    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).resolves.toBe(source);
    expect(state).toHaveBeenCalledWith(undefined, 'list');

    await lease?.release();
  });
});

function liveSource(data: unknown): LiveSource {
  return {
    snapshot: async () => ({ generation: 1, sequence: 0, timestamp: 0, data }),
    subscribe: () => () => {},
  };
}

import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { makeStdinHookCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { describe, expect, it } from 'vitest';
import { QWEN_HOOKS_PATH } from './hooks';
import { provider } from './index';

const baseContext = {
  cli: 'qwen',
  autoApprove: false,
  initialPrompt: undefined,
  sessionId: 'emdash-session-id',
  providerSessionId: undefined,
  isResuming: false,
  model: '',
};

function createMemoryFs(files = new Map<string, string>()): PluginFs {
  return {
    read: async (path) => files.get(path) ?? null,
    write: async (path, content) => {
      files.set(path, content);
    },
    delete: async (path) => {
      files.delete(path);
    },
    exists: async (path) => files.has(path),
    list: async () => [],
  };
}

describe('qwen provider', () => {
  it('installs hooks globally because Qwen ignores project hooks in untrusted workspaces', () => {
    expect(provider.capabilities.hooks).toEqual({
      kind: 'config',
      scope: 'global',
      supportedEvents: ['notification', 'stop', 'session'],
    });
  });

  it('uses approval-mode=yolo for auto-approve', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      autoApprove: true,
    });

    expect(command).toEqual({
      command: 'qwen',
      args: ['--approval-mode=yolo'],
      env: {},
    });
  });

  it('resumes a stored provider session id with --resume', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      providerSessionId: '31477a03-961a-4451-82d4-efded56947fc',
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'qwen',
      args: ['--resume', '31477a03-961a-4451-82d4-efded56947fc'],
      env: {},
    });
  });

  it('falls back to the latest project session before Qwen reports its session id', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'qwen',
      args: ['--continue'],
      env: {},
    });
  });

  it('installs a SessionStart hook that reports the Qwen session id', async () => {
    const files = new Map<string, string>();
    const fs = createMemoryFs(files);

    await provider.behavior.hooks!.writeHooks(fs, []);

    const settings = JSON.parse(files.get(QWEN_HOOKS_PATH)!);
    expect(settings.hooks.SessionStart).toEqual([
      { hooks: [{ type: 'command', command: makeStdinHookCommand('session') }] },
    ]);

    expect(
      provider.behavior.hooks!.parseHookEvent!('session', {
        session_id: '31477a03-961a-4451-82d4-efded56947fc',
        hook_event_name: 'SessionStart',
      })
    ).toEqual({
      kind: 'session',
      providerSessionId: '31477a03-961a-4451-82d4-efded56947fc',
    });
  });
});

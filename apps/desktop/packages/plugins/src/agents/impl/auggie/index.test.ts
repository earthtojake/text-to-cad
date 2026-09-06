import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildNestedEntry,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { describe, expect, it } from 'vitest';
import { AUGGIE_HOOKS_PATH } from './hooks';
import { provider } from './index';

const baseContext = {
  cli: 'auggie',
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

describe('auggie provider', () => {
  it('resumes a stored provider session id with --resume', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      providerSessionId: 'auggie-session-id',
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'auggie',
      args: ['--allow-indexing', '--resume', 'auggie-session-id'],
      env: {},
    });
  });

  it('falls back to the most recent Auggie session before hooks report a session id', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'auggie',
      args: ['--allow-indexing', '--continue'],
      env: {},
    });
  });

  it('installs Auggie global hooks using the native settings schema', async () => {
    const files = new Map<string, string>();
    const fs = createMemoryFs(files);

    await provider.behavior.hooks!.writeHooks(fs, []);

    const settings = JSON.parse(files.get(AUGGIE_HOOKS_PATH)!);
    expect(settings.hooks.SessionStart).toEqual([
      buildNestedEntry(makeStdinHookCommand('session')),
    ]);
    expect(settings.hooks.PromptSubmit).toEqual([buildNestedEntry(makeStdinHookCommand('start'))]);
    expect(settings.hooks.PostToolUse).toEqual([buildNestedEntry(makeStdinHookCommand('start'))]);
    expect(settings.hooks.Notification).toEqual([
      buildNestedEntry(makeStdinHookCommand('notification')),
    ]);
  });

  it('treats partial hook installs as incomplete', async () => {
    const fs = createMemoryFs(
      new Map([
        [
          AUGGIE_HOOKS_PATH,
          JSON.stringify({
            hooks: {
              SessionStart: [buildNestedEntry(makeStdinHookCommand('session'))],
            },
          }),
        ],
      ])
    );

    await expect(provider.behavior.hooks!.getHooksInstalled(fs)).resolves.toBe(false);

    await provider.behavior.hooks!.writeHooks(fs, []);

    await expect(provider.behavior.hooks!.getHooksInstalled(fs)).resolves.toBe(true);
  });
});

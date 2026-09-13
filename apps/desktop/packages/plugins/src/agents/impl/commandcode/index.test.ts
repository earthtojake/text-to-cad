import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildNestedEntry,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { describe, expect, it } from 'vitest';
import { COMMANDCODE_SETTINGS_PATH } from './hooks';
import { provider } from './index';

const baseContext = {
  cli: 'command-code',
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

describe('commandcode provider', () => {
  it('does not use the Windows cmd shell name for dependency detection', () => {
    expect(provider.capabilities.hostDependency.binaryNames).toEqual([
      'command-code',
      'commandcode',
      'cmdc',
    ]);
  });

  it('starts a fresh session without resume flags', () => {
    const command = provider.behavior.prompt!.buildCommand(baseContext);

    expect(command).toEqual({
      command: 'command-code',
      args: ['--trust', '--skip-onboarding'],
      env: {},
    });
  });

  it('resumes a stored provider session id with --resume', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      providerSessionId: 'command-session-id',
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'command-code',
      args: ['--trust', '--skip-onboarding', '--resume', 'command-session-id'],
      env: {},
    });
  });

  it('installs a Stop hook that reports the Command Code session id', async () => {
    const files = new Map<string, string>();
    const fs = createMemoryFs(files);

    await provider.behavior.hooks!.writeHooks(fs, []);

    const settings = JSON.parse(files.get(COMMANDCODE_SETTINGS_PATH)!);
    expect(settings.hooks.Stop).toEqual([
      buildNestedEntry(makeStdinHookCommand('session')),
      buildNestedEntry(makeStdinHookCommand('stop')),
    ]);

    const stopHooksJson = JSON.stringify(settings.hooks.Stop);
    expect(stopHooksJson).toContain('EMDASH_HOOK_NONCE');
    expect(stopHooksJson).not.toContain('EMDASH_HOOK_TOKEN');
  });

  it('treats partial hook installs as incomplete', async () => {
    const fs = createMemoryFs(
      new Map([
        [
          COMMANDCODE_SETTINGS_PATH,
          JSON.stringify({
            hooks: {
              Stop: [{ hooks: [{ type: 'command', command: makeStdinHookCommand('session') }] }],
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

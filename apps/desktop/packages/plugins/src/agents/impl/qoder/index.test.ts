import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildNestedEntry,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { describe, expect, it } from 'vitest';
import { QODER_SETTINGS_PATH } from './hooks';
import { provider } from './index';

const baseContext = {
  cli: 'qodercli',
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

describe('qoder provider', () => {
  it('continues the latest session before Qoder reports its session id', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'qodercli',
      args: ['-c'],
      env: {},
    });
  });

  it('resumes a stored provider session id with -r', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      providerSessionId: 'qoder-session-id',
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'qodercli',
      args: ['-r', 'qoder-session-id'],
      env: {},
    });
  });

  it('declares global config hooks', () => {
    expect(provider.capabilities.hooks).toEqual({
      kind: 'config',
      scope: 'global',
      supportedEvents: ['notification', 'stop', 'session', 'start', 'tool-use', 'tool-use-failure'],
    });
  });

  it('installs Qoder lifecycle hooks in global settings', async () => {
    const files = new Map<string, string>();
    const fs = createMemoryFs(files);

    await provider.behavior.hooks!.writeHooks(fs, []);

    const settings = JSON.parse(files.get(QODER_SETTINGS_PATH)!);
    expect(settings.hooks.SessionStart).toEqual([
      buildNestedEntry(makeStdinHookCommand('session')),
    ]);
    expect(settings.hooks.UserPromptSubmit).toEqual([
      buildNestedEntry(makeStdinHookCommand('start')),
    ]);
    expect(settings.hooks.PermissionRequest).toEqual([
      buildNestedEntry(makeStdinHookCommand('notification')),
    ]);
    expect(settings.hooks.Notification).toEqual([
      buildNestedEntry(makeStdinHookCommand('notification')),
    ]);
    expect(settings.hooks.Stop).toEqual([buildNestedEntry(makeStdinHookCommand('stop'))]);

    const hooksJson = JSON.stringify(settings.hooks);
    expect(hooksJson).toContain('EMDASH_HOOK_NONCE');
    expect(hooksJson).toContain('EMDASH_HOOK_PORT');
  });

  it('maps PermissionRequest hooks to permission notifications', () => {
    const event = provider.behavior.hooks!.parseHookEvent!('notification', {
      hook_event_name: 'PermissionRequest',
      tool_name: 'Bash',
    });

    expect(event).toEqual({
      kind: 'status',
      type: 'notification',
      notificationType: 'permission_prompt',
      title: 'Permission Required',
      message: 'Qoder CLI is requesting permission to use Bash.',
    });
  });

  it('extracts the provider session id from SessionStart hook payloads', () => {
    const event = provider.behavior.hooks!.parseHookEvent!('session', {
      hook_event_name: 'SessionStart',
      session_id: 'qoder-session-id',
    });

    expect(event).toEqual({
      kind: 'session',
      providerSessionId: 'qoder-session-id',
    });
  });
});

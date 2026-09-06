import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it } from 'vitest';
import { DROID_HOOKS_PATH } from './hooks';
import { provider } from './index';

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

describe('droid provider hooks', () => {
  it('writes hooks into the global Factory settings schema', async () => {
    const files = new Map<string, string>();
    const fs = createMemoryFs(files);

    await provider.behavior.hooks!.writeHooks(fs, []);

    const raw = files.get(DROID_HOOKS_PATH);
    expect(raw).toBeDefined();
    const config = JSON.parse(raw!) as Record<string, Record<string, unknown[]>>;
    expect(config.hooks.UserPromptSubmit).toHaveLength(1);
    expect(config.hooks.Notification).toHaveLength(1);
    expect(config.hooks.Stop).toHaveLength(1);
    expect(config.hooks.SessionStart).toHaveLength(1);
    expect(JSON.stringify(config.hooks)).toContain('EMDASH_HOOK_CONFIG_VERSION=1');
  });

  it('preserves user hooks while replacing managed entries', async () => {
    const userHook = { hooks: [{ type: 'command', command: 'echo user-notification' }] };
    const files = new Map<string, string>([
      [
        DROID_HOOKS_PATH,
        JSON.stringify({
          hooks: {
            Notification: [
              userHook,
              { hooks: [{ type: 'command', command: 'echo EMDASH_HOOK_PORT && echo stale' }] },
            ],
          },
        }),
      ],
    ]);
    const fs = createMemoryFs(files);

    await provider.behavior.hooks!.writeHooks(fs, []);

    const config = JSON.parse(files.get(DROID_HOOKS_PATH)!) as Record<
      string,
      Record<string, unknown[]>
    >;
    expect(config.hooks.Notification).toEqual(
      expect.arrayContaining([userHook, expect.objectContaining({ hooks: expect.any(Array) })])
    );
    expect(JSON.stringify(config)).not.toContain('echo stale');
  });
});

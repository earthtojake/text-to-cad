import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it } from 'vitest';
import { KIRO_CLASSIC_HOOKS_PATH, KIRO_V3_HOOKS_PATH, buildKiroHookConfig } from './hooks';

function createMemoryFs(): PluginFs & { files: Map<string, string> } {
  const files = new Map<string, string>();
  return {
    files,
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

describe('Kiro hook config', () => {
  it('dual-writes both classic and v3 hooks', async () => {
    const hooks = buildKiroHookConfig();
    const fs = createMemoryFs();

    const paths = await hooks.writeHooks(fs, []);

    expect(paths).toContain(KIRO_CLASSIC_HOOKS_PATH);
    expect(paths).toContain(KIRO_V3_HOOKS_PATH);
    expect(fs.files.has(KIRO_CLASSIC_HOOKS_PATH)).toBe(true);
    expect(fs.files.has(KIRO_V3_HOOKS_PATH)).toBe(true);
  });

  it('writes valid v3 hook schema', async () => {
    const hooks = buildKiroHookConfig();
    const fs = createMemoryFs();

    await hooks.writeHooks(fs, []);

    const config = JSON.parse(fs.files.get(KIRO_V3_HOOKS_PATH)!) as {
      version: string;
      hooks: Array<Record<string, unknown>>;
    };
    expect(config.version).toBe('v1');
    expect(config.hooks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          trigger: 'SessionStart',
          action: expect.objectContaining({ type: 'command' }),
          enabled: true,
        }),
      ])
    );
  });

  it('reports installed only when both formats are present', async () => {
    const hooks = buildKiroHookConfig();
    const fs = createMemoryFs();

    await expect(hooks.getHooksInstalled(fs)).resolves.toBe(false);

    await hooks.writeHooks(fs, []);
    await expect(hooks.getHooksInstalled(fs)).resolves.toBe(true);

    fs.files.delete(KIRO_V3_HOOKS_PATH);
    await expect(hooks.getHooksInstalled(fs)).resolves.toBe(false);
    await expect(hooks.readHooks(fs)).resolves.toEqual([]);
  });

  it('does not partially write classic hooks when the v3 config has an invalid shape', async () => {
    const hooks = buildKiroHookConfig();
    const fs = createMemoryFs();
    fs.files.set(KIRO_V3_HOOKS_PATH, JSON.stringify({ hooks: 'invalid' }));

    await expect(hooks.writeHooks(fs, [])).rejects.toThrow('expected "hooks" to be an array');
    expect(fs.files.has(KIRO_CLASSIC_HOOKS_PATH)).toBe(false);
  });

  it('deletes hooks from both formats', async () => {
    const hooks = buildKiroHookConfig();
    const fs = createMemoryFs();

    await hooks.writeHooks(fs, []);
    await hooks.deleteHooks(fs);

    const classicConfig = JSON.parse(fs.files.get(KIRO_CLASSIC_HOOKS_PATH)!) as {
      hooks: Record<string, unknown[]>;
    };
    const v3Config = JSON.parse(fs.files.get(KIRO_V3_HOOKS_PATH)!) as {
      hooks: unknown[];
    };
    for (const entries of Object.values(classicConfig.hooks)) {
      expect(entries).toHaveLength(0);
    }
    expect(v3Config.hooks).toHaveLength(0);
  });
});

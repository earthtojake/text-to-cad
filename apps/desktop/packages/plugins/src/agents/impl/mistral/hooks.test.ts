import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it } from 'vitest';
import { MISTRAL_HOOKS_PATH, buildMistralHookConfig } from './hooks';

function createMemoryFs(initial: Record<string, string> = {}): PluginFs {
  const files = new Map(Object.entries(initial));
  return {
    read: async (path) => files.get(path) ?? null,
    write: async (path, content) => {
      files.set(path, content);
    },
    delete: async (path) => {
      files.delete(path);
    },
    exists: async (path) => files.has(path),
    list: async (path) => [...files.keys()].filter((file) => file.startsWith(path)),
  };
}

describe('buildMistralHookConfig', () => {
  it('writes the supported global hooks file without an experimental flag', async () => {
    const fs = createMemoryFs();
    const hooks = buildMistralHookConfig();

    await expect(hooks.writeHooks(fs, [])).resolves.toEqual([MISTRAL_HOOKS_PATH]);
    await expect(fs.read(MISTRAL_HOOKS_PATH)).resolves.toContain('emdash-post-agent-turn');
  });

  it('honors VIBE_HOME when resolving its config root', () => {
    const hooks = buildMistralHookConfig();
    expect(
      hooks.resolveConfigRoots({
        env: { VIBE_HOME: '/custom/vibe' },
        homeDir: '/home/test',
        platform: 'linux',
      })
    ).toEqual(['/custom/vibe']);
  });
});

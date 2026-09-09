import { describe, expect, it, vi } from 'vitest';
import type { PluginFs } from '#primitives/plugin-fs/api';
import {
  buildFlatJsonHookConfig,
  buildFlatTomlHookConfig,
  readJsonConfig,
  readTomlConfig,
} from './hook-config';

function configFs(content: string): PluginFs {
  return {
    read: async () => content,
    write: vi.fn(async () => {}),
    delete: async () => {},
    exists: async () => true,
    list: async () => [],
  };
}

describe('hook config parsing', () => {
  it('refuses to treat invalid JSON as an empty config', async () => {
    await expect(readJsonConfig(configFs('{ invalid'), 'settings.json')).rejects.toThrow(
      'Failed to parse settings.json'
    );
  });

  it('refuses non-object JSON roots', async () => {
    await expect(readJsonConfig(configFs('[]'), 'settings.json')).rejects.toThrow(
      'expected an object at the config root'
    );
  });

  it('refuses to treat invalid TOML as an empty config', async () => {
    await expect(readTomlConfig(configFs('invalid = ['), 'config.toml')).rejects.toThrow(
      'Failed to parse config.toml'
    );
  });

  it('does not overwrite a structurally incompatible TOML hooks field', async () => {
    const fs = configFs('hooks = "custom-command"\n');
    const hooks = buildFlatTomlHookConfig('config.toml', [{ command: 'emdash' }]);

    await expect(hooks.writeHooks(fs, [])).rejects.toThrow(
      'expected "hooks" to be an array of objects'
    );
    expect(fs.write).not.toHaveBeenCalled();
  });

  it('does not overwrite a structurally incompatible JSON hooks field', async () => {
    const fs = configFs('{"hooks":[]}');
    const hooks = buildFlatJsonHookConfig('hooks.json', [{ hookKey: 'Stop', command: 'emdash' }]);

    await expect(hooks.writeHooks(fs, [])).rejects.toThrow('expected "hooks" to be an object');
    expect(fs.write).not.toHaveBeenCalled();
  });
});

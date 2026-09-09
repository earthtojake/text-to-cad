import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it } from 'vitest';
import { provider } from './index';

function createMemoryFs(): PluginFs & { files: Map<string, string> } {
  const files = new Map<string, string>();

  return {
    files,
    async read(path) {
      return files.get(path) ?? null;
    },
    async write(path, content) {
      files.set(path, content);
    },
    async delete(path) {
      files.delete(path);
    },
    async exists(path) {
      return files.has(path);
    },
    async list(path) {
      return [...files.keys()].filter((file) => file.startsWith(path));
    },
  };
}

describe('kilocode plugin hooks', () => {
  it('installs the emdash notifications plugin relative to the global Kilo root', async () => {
    const fs = createMemoryFs();

    const written = await provider.behavior.plugins?.installPlugin(fs, { kind: 'global' });

    expect(written).toEqual(['plugin/emdash-notifications.js']);
    const content = await fs.read('plugin/emdash-notifications.js');
    expect(content).toContain('export const EmdashNotifications');
    expect(content).toContain('X-Emdash-Event-Type');
    expect(content).toContain("event.type === 'session.idle'");
    expect(content).toContain("event.type === 'session.error'");
    expect(content).toContain('getKiloSessionId');
  });
});

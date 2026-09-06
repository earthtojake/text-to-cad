import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it, vi } from 'vitest';
import { provider } from './index';

function createMemoryFs(initial: Record<string, string> = {}): PluginFs & {
  files: Map<string, string>;
  writes: Array<{ path: string; content: string }>;
} {
  const files = new Map(Object.entries(initial));
  const writes: Array<{ path: string; content: string }> = [];

  return {
    files,
    writes,
    read: async (path) => files.get(path) ?? null,
    write: vi.fn(async (path, content) => {
      writes.push({ path, content });
      files.set(path, content);
    }),
    delete: async (path) => {
      files.delete(path);
    },
    exists: async (path) => files.has(path),
    list: async () => [],
  };
}

describe('Copilot trust behavior', () => {
  it('adds trusted folders while preserving existing entries', async () => {
    const fs = createMemoryFs({
      '.copilot/config.json': JSON.stringify({ trustedFolders: ['/already/trusted'] }),
    });

    await provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' });

    expect(fs.writes).toHaveLength(1);
    expect(fs.writes[0].path).toBe('.copilot/config.json');
    expect(JSON.parse(fs.writes[0].content).trustedFolders).toEqual([
      '/already/trusted',
      '/tmp/worktree',
    ]);
  });

  it('does not rewrite when the folder is already trusted', async () => {
    const fs = createMemoryFs({
      '.copilot/config.json': JSON.stringify({ trustedFolders: ['/tmp/worktree'] }),
    });

    await provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' });

    expect(fs.writes).toHaveLength(0);
  });
});

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

describe('Claude trust behavior', () => {
  it('writes trusted project config when missing', async () => {
    const fs = createMemoryFs();

    await provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' });

    expect(fs.writes).toHaveLength(1);
    expect(fs.writes[0].path).toBe('.claude.json');
    expect(JSON.parse(fs.writes[0].content)).toEqual({
      projects: {
        '/tmp/worktree': {
          hasTrustDialogAccepted: true,
          hasCompletedProjectOnboarding: true,
        },
      },
    });
  });

  it('does not rewrite when the project is already trusted', async () => {
    const fs = createMemoryFs({
      '.claude.json': JSON.stringify({
        projects: {
          '/tmp/worktree': {
            hasTrustDialogAccepted: true,
            hasCompletedProjectOnboarding: true,
          },
        },
      }),
    });

    await provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' });

    expect(fs.writes).toHaveLength(0);
  });

  it('refuses to overwrite corrupt config', async () => {
    const fs = createMemoryFs({ '.claude.json': '{ invalid json' });

    await expect(
      provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' })
    ).rejects.toThrow(/corrupt config \.claude\.json/);

    expect(fs.writes).toHaveLength(0);
  });

  it('refuses to overwrite non-object config root', async () => {
    const fs = createMemoryFs({ '.claude.json': JSON.stringify([1, 2, 3]) });

    await expect(
      provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' })
    ).rejects.toThrow(/non-object config root/);

    expect(fs.writes).toHaveLength(0);
  });
});

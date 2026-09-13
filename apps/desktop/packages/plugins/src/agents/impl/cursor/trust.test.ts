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

describe('Cursor trust behavior', () => {
  it('writes the Cursor workspace trust marker using the CLI slug derivation', async () => {
    const fs = createMemoryFs();

    await provider.behavior.trust!.trustWorkspace(fs, {
      workspacePath: '/Users/janburzinski/emdash/worktrees/emdash-official/tough-falcons-notice',
    });

    expect(fs.writes).toHaveLength(1);
    expect(fs.writes[0].path).toBe(
      '.cursor/projects/Users-janburzinski-emdash-worktrees-emdash-official-tough-falcons-notice/.workspace-trusted'
    );
    expect(JSON.parse(fs.writes[0].content)).toEqual({
      trustedAt: expect.any(String),
      workspacePath: '/Users/janburzinski/emdash/worktrees/emdash-official/tough-falcons-notice',
      trustMethod: 'emdash-auto-trust',
    });
  });

  it('does not rewrite the marker when it already exists', async () => {
    const markerPath = '.cursor/projects/tmp-worktree/.workspace-trusted';
    const fs = createMemoryFs({ [markerPath]: 'existing' });

    await provider.behavior.trust!.trustWorkspace(fs, { workspacePath: '/tmp/worktree' });

    expect(fs.writes).toHaveLength(0);
  });
});

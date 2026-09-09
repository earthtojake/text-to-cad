import path from 'node:path';
import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { canonicalizeWorktreeDirectory, normalizeWorktreeDirectory } from './worktree-directory';

const invalidWorktreeDirectory = {
  success: false,
  error: { type: 'invalid-worktree-directory' },
} as const;

describe('worktree-directory', () => {
  describe('normalizeWorktreeDirectory', () => {
    it('rejects posix relative paths', async () => {
      await expect(
        normalizeWorktreeDirectory('worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
          homeDirectory: '/Users/test',
        })
      ).resolves.toEqual(invalidWorktreeDirectory);
    });

    it('accepts posix absolute paths', async () => {
      await expect(
        normalizeWorktreeDirectory('/Users/test/worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
          homeDirectory: '/Users/test',
        })
      ).resolves.toEqual({
        success: true,
        data: '/Users/test/worktrees',
      });
    });

    it('expands posix tilde paths from home', async () => {
      await expect(
        normalizeWorktreeDirectory('~/worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
          homeDirectory: '/Users/test',
        })
      ).resolves.toEqual({
        success: true,
        data: '/Users/test/worktrees',
      });
    });

    it('rejects windows absolute paths in posix mode', async () => {
      await expect(
        normalizeWorktreeDirectory('C:\\worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
          homeDirectory: '/Users/test',
        })
      ).resolves.toEqual(invalidWorktreeDirectory);
    });

    it('rejects windows UNC paths in posix mode', async () => {
      await expect(
        normalizeWorktreeDirectory('\\\\server\\share\\worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
          homeDirectory: '/Users/test',
        })
      ).resolves.toEqual(invalidWorktreeDirectory);
    });

    it('rejects win32 relative paths', async () => {
      await expect(
        normalizeWorktreeDirectory('worktrees', {
          pathApi: path.win32,
          pathPlatform: 'win32',
          homeDirectory: 'C:\\Users\\test',
        })
      ).resolves.toEqual(invalidWorktreeDirectory);
    });

    it('accepts win32 drive absolute paths', async () => {
      await expect(
        normalizeWorktreeDirectory('D:\\worktrees', {
          pathApi: path.win32,
          pathPlatform: 'win32',
          homeDirectory: 'C:\\Users\\test',
        })
      ).resolves.toEqual({
        success: true,
        data: 'D:\\worktrees',
      });
    });

    it('accepts win32 UNC paths', async () => {
      await expect(
        normalizeWorktreeDirectory('\\\\server\\share\\worktrees', {
          pathApi: path.win32,
          pathPlatform: 'win32',
          homeDirectory: 'C:\\Users\\test',
        })
      ).resolves.toEqual({
        success: true,
        data: '\\\\server\\share\\worktrees',
      });
    });

    it('expands win32 tilde paths from home', async () => {
      await expect(
        normalizeWorktreeDirectory('~\\worktrees', {
          pathApi: path.win32,
          pathPlatform: 'win32',
          homeDirectory: 'C:\\Users\\test',
        })
      ).resolves.toEqual({
        success: true,
        data: 'C:\\Users\\test\\worktrees',
      });
    });

    it('rejects posix absolute paths in win32 mode', async () => {
      await expect(
        normalizeWorktreeDirectory('/Users/test/worktrees', {
          pathApi: path.win32,
          pathPlatform: 'win32',
          homeDirectory: 'C:\\Users\\test',
        })
      ).resolves.toEqual(invalidWorktreeDirectory);
    });

    it('rejects tilde paths when home cannot be resolved', async () => {
      await expect(
        normalizeWorktreeDirectory('~/worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
        })
      ).resolves.toEqual(invalidWorktreeDirectory);
    });

    it('expands ssh tilde paths with async home resolver', async () => {
      await expect(
        normalizeWorktreeDirectory('~/worktrees', {
          pathApi: path.posix,
          pathPlatform: 'posix',
          resolveHomeDirectory: async () => '/home/ubuntu',
        })
      ).resolves.toEqual({
        success: true,
        data: '/home/ubuntu/worktrees',
      });
    });
  });

  describe('canonicalizeWorktreeDirectory', () => {
    it('creates and canonicalizes directory through fs provider', async () => {
      const fs = {
        mkdir: vi.fn().mockResolvedValue(ok()),
        realPath: vi.fn().mockResolvedValue(ok('/canonical/path')),
      };

      const resolved = await canonicalizeWorktreeDirectory('/input/path', fs);
      expect(resolved).toEqual({
        success: true,
        data: '/canonical/path',
      });
      expect(fs.mkdir).toHaveBeenCalledWith('/input/path', { recursive: true });
      expect(fs.realPath).toHaveBeenCalledWith('/input/path');
    });

    it('rejects inaccessible directories', async () => {
      const fs = {
        mkdir: vi.fn().mockResolvedValue(err({ message: 'permission denied' })),
        realPath: vi.fn(),
      };

      await expect(canonicalizeWorktreeDirectory('/input/path', fs)).resolves.toEqual(
        invalidWorktreeDirectory
      );
      expect(fs.realPath).not.toHaveBeenCalled();
    });
  });
});

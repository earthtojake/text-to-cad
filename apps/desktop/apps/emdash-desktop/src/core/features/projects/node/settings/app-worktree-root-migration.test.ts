import { describe, expect, it, vi } from 'vitest';
import {
  migrateAppWorktreeRootToLocalHostDefault,
  type AppWorktreeRootMigrationDeps,
} from './migrations/app-worktree-root';

function makeDeps(overrides: {
  override?: string;
  hostWorktreeRoot?: string;
  hostUnavailable?: boolean;
  setFails?: boolean;
}) {
  const clearAppDefaultWorktreeDirectory = vi.fn().mockResolvedValue(undefined);
  const setWorktreeRoot = vi.fn().mockResolvedValue({ success: !overrides.setFails });
  const deps: AppWorktreeRootMigrationDeps = {
    getAppDefaultWorktreeDirectoryOverride: async () => overrides.override,
    clearAppDefaultWorktreeDirectory,
    localHostSettings: {
      getWorktreeRoot: async () =>
        overrides.hostUnavailable
          ? { success: false }
          : { success: true, worktreeRoot: overrides.hostWorktreeRoot },
      setWorktreeRoot,
    },
  };
  return { deps, clearAppDefaultWorktreeDirectory, setWorktreeRoot };
}

describe('migrateAppWorktreeRootToLocalHostDefault', () => {
  it('does nothing when the app-wide setting was never overridden', async () => {
    const { deps, clearAppDefaultWorktreeDirectory, setWorktreeRoot } = makeDeps({});
    await migrateAppWorktreeRootToLocalHostDefault(deps);
    expect(setWorktreeRoot).not.toHaveBeenCalled();
    expect(clearAppDefaultWorktreeDirectory).not.toHaveBeenCalled();
  });

  it('copies the override into the local host default and clears the app setting', async () => {
    const { deps, clearAppDefaultWorktreeDirectory, setWorktreeRoot } = makeDeps({
      override: '/custom/worktrees',
    });
    await migrateAppWorktreeRootToLocalHostDefault(deps);
    expect(setWorktreeRoot).toHaveBeenCalledWith('/custom/worktrees');
    expect(clearAppDefaultWorktreeDirectory).toHaveBeenCalled();
  });

  it('keeps an already-set host default and still clears the app setting', async () => {
    const { deps, clearAppDefaultWorktreeDirectory, setWorktreeRoot } = makeDeps({
      override: '/custom/worktrees',
      hostWorktreeRoot: '/host/worktrees',
    });
    await migrateAppWorktreeRootToLocalHostDefault(deps);
    expect(setWorktreeRoot).not.toHaveBeenCalled();
    expect(clearAppDefaultWorktreeDirectory).toHaveBeenCalled();
  });

  it('clears a blank override without touching host settings', async () => {
    const { deps, clearAppDefaultWorktreeDirectory, setWorktreeRoot } = makeDeps({
      override: '   ',
    });
    await migrateAppWorktreeRootToLocalHostDefault(deps);
    expect(setWorktreeRoot).not.toHaveBeenCalled();
    expect(clearAppDefaultWorktreeDirectory).toHaveBeenCalled();
  });

  it('throws (for retry) when host settings are unavailable, keeping the app setting', async () => {
    const { deps, clearAppDefaultWorktreeDirectory } = makeDeps({
      override: '/custom/worktrees',
      hostUnavailable: true,
    });
    await expect(migrateAppWorktreeRootToLocalHostDefault(deps)).rejects.toThrow();
    expect(clearAppDefaultWorktreeDirectory).not.toHaveBeenCalled();
  });

  it('throws (for retry) when the host default write fails, keeping the app setting', async () => {
    const { deps, clearAppDefaultWorktreeDirectory } = makeDeps({
      override: '/custom/worktrees',
      setFails: true,
    });
    await expect(migrateAppWorktreeRootToLocalHostDefault(deps)).rejects.toThrow();
    expect(clearAppDefaultWorktreeDirectory).not.toHaveBeenCalled();
  });
});

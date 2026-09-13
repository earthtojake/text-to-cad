import { mkdir, mkdtemp, rm, utimes } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import {
  electronRebuildOptions,
  ensureElectronNativeRuntime,
  type ElectronNativeProbe,
  withNativeRebuildLock,
} from './ensure-electron-native.ts';

describe('Electron native startup preflight', () => {
  it('resolves hoisted native modules from the workspace root', () => {
    const options = electronRebuildOptions();

    expect(options.buildPath).toMatch(/apps\/emdash-desktop$/);
    // The workspace root is apps/desktop inside text-to-cad; never a hardcoded checkout name.
    expect(options.projectRootPath).toBe(path.resolve(options.buildPath, '..', '..'));
    expect(options.onlyModules).toEqual(['better-sqlite3']);
  });

  it('does not rebuild a healthy Electron native runtime', async () => {
    const rebuild = vi.fn(async () => {});

    await expect(
      ensureElectronNativeRuntime({
        probe: () => ({ ok: true, detail: 'ready' }),
        rebuild,
      })
    ).resolves.toEqual({ rebuilt: false, detail: 'ready' });

    expect(rebuild).not.toHaveBeenCalled();
  });

  it('rebuilds a stale native module once and verifies the repaired copy', async () => {
    const results: ElectronNativeProbe[] = [
      { ok: false, detail: 'NODE_MODULE_VERSION mismatch' },
      { ok: false, detail: 'NODE_MODULE_VERSION mismatch' },
      { ok: true, detail: 'ready' },
    ];
    const rebuild = vi.fn(async () => {});
    const log = vi.fn();

    await expect(
      ensureElectronNativeRuntime({
        probe: () => results.shift()!,
        rebuild,
        log,
      })
    ).resolves.toEqual({ rebuilt: true, detail: 'ready' });

    expect(rebuild).toHaveBeenCalledOnce();
    expect(log).toHaveBeenCalledWith(expect.stringContaining('repairing better-sqlite3'));
  });

  it('fails before Electron starts when rebuilding does not repair the module', async () => {
    const rebuild = vi.fn(async () => {});

    await expect(
      ensureElectronNativeRuntime({
        probe: () => ({ ok: false, detail: 'still incompatible' }),
        rebuild,
        log: vi.fn(),
      })
    ).rejects.toThrow(/still fails after rebuilding.*still incompatible/s);

    expect(rebuild).toHaveBeenCalledOnce();
  });

  it('re-probes after taking the lock because another launcher may have repaired it', async () => {
    const results: ElectronNativeProbe[] = [
      { ok: false, detail: 'stale before lock' },
      { ok: true, detail: 'repaired by another launcher' },
    ];
    const rebuild = vi.fn(async () => {});
    const withLock = vi.fn(async <T>(action: () => Promise<T>) => action());

    await expect(
      ensureElectronNativeRuntime({
        probe: () => results.shift()!,
        rebuild,
        withLock,
      })
    ).resolves.toEqual({ rebuilt: false, detail: 'repaired by another launcher' });

    expect(withLock).toHaveBeenCalledOnce();
    expect(rebuild).not.toHaveBeenCalled();
  });

  it('honors native-database escape hatches without launching a broken app', async () => {
    const probe = vi.fn(() => ({ ok: false, detail: 'incompatible' }));

    await expect(
      ensureElectronNativeRuntime({
        probe,
        env: { EMDASH_DISABLE_NATIVE_DB: '1' },
      })
    ).resolves.toEqual({
      rebuilt: false,
      detail: 'native database disabled by EMDASH_DISABLE_NATIVE_DB',
    });
    expect(probe).not.toHaveBeenCalled();

    await expect(
      ensureElectronNativeRuntime({
        probe,
        env: { EMDASH_SKIP_ELECTRON_REBUILD: '1' },
      })
    ).rejects.toThrow(/automatic rebuilding is disabled.*incompatible/s);
  });
});

describe('Electron native rebuild lock', () => {
  async function lockScratch(): Promise<{ directory: string; lockPath: string }> {
    const directory = await mkdtemp(path.join(tmpdir(), 'hardcore-native-lock-'));
    return { directory, lockPath: path.join(directory, 'rebuild.lock') };
  }

  it('keeps a long-running owner fresh beyond the stale threshold', async () => {
    const { directory, lockPath } = await lockScratch();
    let firstEntered = false;
    let secondEnteredWhileFirstActive = false;

    try {
      const first = withNativeRebuildLock(
        async () => {
          firstEntered = true;
          await new Promise((resolve) => setTimeout(resolve, 2_500));
          firstEntered = false;
        },
        {
          lockPath,
          retryMs: 10,
          staleMs: 2_000,
          timeoutMs: 4_000,
          updateMs: 1_000,
        }
      );
      await new Promise((resolve) => setTimeout(resolve, 2_100));
      const second = withNativeRebuildLock(
        async () => {
          secondEnteredWhileFirstActive = firstEntered;
        },
        {
          lockPath,
          retryMs: 10,
          staleMs: 2_000,
          timeoutMs: 4_000,
          updateMs: 1_000,
        }
      );

      await Promise.all([first, second]);
      expect(secondEnteredWhileFirstActive).toBe(false);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('allows only one contender to replace a stale orphaned lock', async () => {
    const { directory, lockPath } = await lockScratch();
    const lockDirectory = `${lockPath}.lock`;
    await mkdir(lockDirectory);
    const old = new Date(Date.now() - 10_000);
    await utimes(lockDirectory, old, old);
    let active = 0;
    let maximumActive = 0;
    const contender = () =>
      withNativeRebuildLock(
        async () => {
          active += 1;
          maximumActive = Math.max(maximumActive, active);
          await new Promise((resolve) => setTimeout(resolve, 20));
          active -= 1;
        },
        {
          lockPath,
          retryMs: 5,
          staleMs: 2_000,
          timeoutMs: 1_000,
          updateMs: 1_000,
        }
      );

    try {
      await Promise.all([contender(), contender()]);
      expect(maximumActive).toBe(1);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('serializes two ordinary contenders for the same lock', async () => {
    const { directory, lockPath } = await lockScratch();
    let releaseFirst!: () => void;
    let firstEntered!: () => void;
    const firstReady = new Promise<void>((resolve) => {
      firstEntered = resolve;
    });
    const firstRelease = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    let secondEntered = false;

    try {
      const first = withNativeRebuildLock(
        async () => {
          firstEntered();
          await firstRelease;
        },
        { lockPath, retryMs: 2, timeoutMs: 500 }
      );
      await firstReady;
      const second = withNativeRebuildLock(
        async () => {
          secondEntered = true;
        },
        { lockPath, retryMs: 2, timeoutMs: 500 }
      );

      await new Promise((resolve) => setTimeout(resolve, 15));
      expect(secondEntered).toBe(false);
      releaseFirst();
      await Promise.all([first, second]);
      expect(secondEntered).toBe(true);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});

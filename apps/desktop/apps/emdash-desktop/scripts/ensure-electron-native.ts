/**
 * Verifies that Electron can load the app's native database module before the
 * desktop process starts. Node-side tests may rebuild the hoisted copy of
 * better-sqlite3 for the system Node ABI, so a successful install is not a
 * permanent guarantee that the next Electron launch is healthy.
 */
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { rebuild, type RebuildOptions } from '@electron/rebuild';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const workspaceRoot = path.resolve(appRoot, '..', '..');
const appRequire = createRequire(path.join(appRoot, 'package.json'));
const rebuildLockPath = path.join(
  workspaceRoot,
  'node_modules',
  '.hardcore-electron-native-rebuild'
);
const REBUILD_LOCK_TIMEOUT_MS = 60_000;

export type ElectronNativeProbe = {
  ok: boolean;
  detail: string;
};

export type ElectronNativeEnsureResult = {
  rebuilt: boolean;
  detail: string;
};

type EnsureOptions = {
  probe?: () => ElectronNativeProbe;
  rebuild?: () => Promise<void>;
  withLock?: <T>(action: () => Promise<T>) => Promise<T>;
  log?: (message: string) => void;
  env?: NodeJS.ProcessEnv;
};

export type NativeRebuildLockOptions = {
  lockPath?: string;
  retryMs?: number;
  staleMs?: number;
  timeoutMs?: number;
  updateMs?: number;
};

type ProperLockfile = {
  lock(
    target: string,
    options: {
      realpath: false;
      retries: {
        factor: number;
        maxTimeout: number;
        minTimeout: number;
        randomize: false;
        retries: number;
      };
      stale: number;
      update: number;
    }
  ): Promise<() => Promise<void>>;
};

const PROBE_SOURCE = `
const { createRequire } = require('node:module');
const req = createRequire(${JSON.stringify(path.join(appRoot, 'package.json'))});
const Database = req('better-sqlite3');
const db = new Database(':memory:');
db.prepare('select 1').get();
db.close();
`;

/** Runs the real Electron executable as Node, so the probe uses Electron's ABI. */
export function probeElectronNativeRuntime(): ElectronNativeProbe {
  const electronBinary = appRequire('electron') as string;
  const result = spawnSync(electronBinary, ['-e', PROBE_SOURCE], {
    cwd: appRoot,
    encoding: 'utf8',
    env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    timeout: 15_000,
  });

  if (result.error) {
    return { ok: false, detail: result.error.message };
  }
  if (result.status === 0) {
    return { ok: true, detail: 'better-sqlite3 opens a database with Electron' };
  }

  const detail = [result.stderr, result.stdout].map((value) => value?.trim()).find(Boolean);
  return {
    ok: false,
    detail: detail ?? `Electron native probe exited with status ${result.status ?? 'unknown'}`,
  };
}

export function electronRebuildOptions(): RebuildOptions {
  const electronVersion = (appRequire('electron/package.json') as { version: string }).version;
  return {
    buildPath: appRoot,
    projectRootPath: workspaceRoot,
    electronVersion,
    arch: process.arch,
    onlyModules: ['better-sqlite3'],
    force: true,
  };
}

async function rebuildElectronNativeRuntime(): Promise<void> {
  await rebuild(electronRebuildOptions());
}

export async function withNativeRebuildLock<T>(
  action: () => Promise<T>,
  options: NativeRebuildLockOptions = {}
): Promise<T> {
  const lockPath = options.lockPath ?? rebuildLockPath;
  const retryMs = options.retryMs ?? 250;
  const timeoutMs = options.timeoutMs ?? REBUILD_LOCK_TIMEOUT_MS;
  const staleMs = options.staleMs ?? 30_000;
  const updateMs = options.updateMs ?? Math.max(1_000, Math.floor(staleMs / 3));
  const properLockfile = appRequire('proper-lockfile') as ProperLockfile;
  let release: (() => Promise<void>) | undefined;

  try {
    release = await properLockfile.lock(lockPath, {
      realpath: false,
      stale: staleMs,
      update: updateMs,
      retries: {
        retries: Math.max(0, Math.ceil(timeoutMs / retryMs) - 1),
        factor: 1,
        minTimeout: retryMs,
        maxTimeout: retryMs,
        randomize: false,
      },
    });
    return await action();
  } catch (error) {
    if (
      error instanceof Error &&
      'code' in error &&
      (error as NodeJS.ErrnoException).code === 'ELOCKED'
    ) {
      throw new Error('Timed out waiting for another Electron native-module rebuild.', {
        cause: error,
      });
    }
    throw error;
  } finally {
    await release?.();
  }
}

/** Repairs a stale native binary once, then verifies the repaired copy in a new process. */
export async function ensureElectronNativeRuntime(
  options: EnsureOptions = {}
): Promise<ElectronNativeEnsureResult> {
  const probe = options.probe ?? probeElectronNativeRuntime;
  const runRebuild = options.rebuild ?? rebuildElectronNativeRuntime;
  const withLock = options.withLock ?? withNativeRebuildLock;
  const log = options.log ?? console.log;
  const env = options.env ?? process.env;

  if (env.EMDASH_DISABLE_NATIVE_DB === '1') {
    return { rebuilt: false, detail: 'native database disabled by EMDASH_DISABLE_NATIVE_DB' };
  }

  const before = probe();

  if (before.ok) {
    return { rebuilt: false, detail: before.detail };
  }

  if (env.EMDASH_SKIP_ELECTRON_REBUILD === '1') {
    throw new Error(
      `Electron native preflight failed while automatic rebuilding is disabled.\n${before.detail}`
    );
  }

  return withLock(async () => {
    // Another launcher may have completed the repair while this process waited
    // for the lock, so avoid an unnecessary second rebuild.
    const afterWait = probe();
    if (afterWait.ok) {
      return { rebuilt: false, detail: afterWait.detail };
    }

    log(`Electron native preflight failed; repairing better-sqlite3.\n${afterWait.detail}`);
    await runRebuild();

    const after = probe();
    if (!after.ok) {
      throw new Error(
        `Electron native preflight still fails after rebuilding better-sqlite3.\n${after.detail}`
      );
    }

    return { rebuilt: true, detail: after.detail };
  });
}

async function main(): Promise<void> {
  const result = await ensureElectronNativeRuntime();
  console.log(
    result.rebuilt
      ? `Electron native runtime repaired: ${result.detail}`
      : `Electron native runtime ready: ${result.detail}`
  );
}

const isDirectRun =
  process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;

if (isDirectRun) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}

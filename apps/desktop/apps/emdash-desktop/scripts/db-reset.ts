/**
 * Deletes the development databases so the app starts fresh.
 *
 * Honors EMDASH_DB_FILE: when set, the override family (main DB plus the
 * derived file-search / automations / operations siblings and their SQLite
 * sidecars) is deleted instead of the default dev databases. Runs on plain
 * Node so it works on every platform — no shell `rm -f` with hardcoded paths.
 */
import { rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export type DbResetOptions = {
  dbFile: string | undefined;
  platform: NodeJS.Platform;
  home: string;
  appData?: string | undefined;
};

const SIBLING_SUFFIXES = ['-file-search', '-automations', '-operations'];
const SIDECAR_SUFFIXES = ['', '-wal', '-shm'];

/** Mirrors the app's sibling-path derivation (see file-search/database-path.ts). */
function siblingPath(appDbPath: string, suffix: string): string {
  const extension = path.extname(appDbPath);
  const basename = path.basename(appDbPath, extension);
  return path.join(path.dirname(appDbPath), `${basename}${suffix}${extension || '.db'}`);
}

function withSidecars(files: string[]): string[] {
  return files.flatMap((file) => SIDECAR_SUFFIXES.map((suffix) => `${file}${suffix}`));
}

function defaultUserDataDir(options: DbResetOptions): string {
  const dirName = 'emdash-dev';
  switch (options.platform) {
    case 'darwin':
      return path.join(options.home, 'Library', 'Application Support', dirName);
    case 'win32':
      return path.join(options.appData ?? path.join(options.home, 'AppData', 'Roaming'), dirName);
    default:
      return path.join(options.home, '.config', dirName);
  }
}

export function resolveDbResetTargets(options: DbResetOptions): string[] {
  if (options.dbFile) {
    const family = [
      options.dbFile,
      ...SIBLING_SUFFIXES.map((suffix) => siblingPath(options.dbFile as string, suffix)),
    ];
    return withSidecars(family);
  }

  const dir = defaultUserDataDir(options);
  const family = [
    path.join(dir, 'emdash3.db'),
    path.join(dir, 'emdash4.db'),
    ...SIBLING_SUFFIXES.map((suffix) => path.join(dir, `emdash4${suffix}.db`)),
  ];
  return withSidecars(family);
}

function main(): void {
  const targets = resolveDbResetTargets({
    dbFile: process.env.EMDASH_DB_FILE?.trim() || undefined,
    platform: process.platform,
    home: os.homedir(),
    appData: process.env.APPDATA,
  });

  for (const target of targets) {
    rmSync(target, { force: true });
  }

  const scope = process.env.EMDASH_DB_FILE
    ? `EMDASH_DB_FILE family at ${process.env.EMDASH_DB_FILE}`
    : 'default dev databases';
  console.log(`db:reset: removed the ${scope} (${targets.length} paths checked).`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}

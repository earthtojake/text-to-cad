import { spawn, type ChildProcess } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { fail, info, step } from './lib/log.ts';

const STARTUP_TIMEOUT_MS = 60_000;
const SQLITE_HEADER = Buffer.from('SQLite format 3\0', 'utf8');
const FAILURE_MARKERS = [
  'Boot failed; entering recovery mode',
  'Failed to open recovery window',
  'Renderer bootstrap failed',
  'Renderer startup failed; opening recovery',
  'Uncaught exception',
] as const;

export type PackagedStartupLogResult =
  | { status: 'waiting' }
  | { status: 'failed'; detail: string }
  | { status: 'ready'; usableWorkspaceMs: number };

export function parsePackagedStartupLog(source: string): PackagedStartupLogResult {
  const failure = FAILURE_MARKERS.find((marker) => source.includes(marker));
  if (failure) return { status: 'failed', detail: failure };

  for (const line of source.split(/\r?\n/)) {
    if (!line.startsWith('{')) continue;
    let entry: Record<string, unknown>;
    try {
      entry = JSON.parse(line) as Record<string, unknown>;
    } catch {
      continue;
    }
    if (entry.msg !== 'boot-report') continue;

    const phases = entry.phases;
    const usableWorkspaceMs = entry.usableWorkspaceMs;
    if (
      typeof usableWorkspaceMs !== 'number' ||
      typeof phases !== 'object' ||
      phases === null ||
      typeof (phases as Record<string, unknown>)['db-initialize'] !== 'number' ||
      typeof (phases as Record<string, unknown>)['db-startup-repairs'] !== 'number'
    ) {
      return {
        status: 'failed',
        detail: 'boot-report did not include a usable workspace and both database phases',
      };
    }
    return { status: 'ready', usableWorkspaceMs };
  }

  return { status: 'waiting' };
}

export function findPackagedApplications(
  releaseDir: string,
  platform: NodeJS.Platform = process.platform,
  architecture: string = process.arch
): string[] {
  if (!existsSync(releaseDir)) return [];
  const candidates: string[] = [];
  const visit = (directory: string, depth: number): void => {
    if (depth > 3) return;
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const candidate = path.join(directory, entry.name);
      if (platform === 'darwin' && entry.isDirectory() && entry.name.endsWith('.app')) {
        candidates.push(candidate);
        continue;
      }
      if (
        platform === 'win32' &&
        entry.isFile() &&
        /^hardcore(?: canary)?\.exe$/i.test(entry.name) &&
        path.basename(path.dirname(candidate)).toLowerCase() === 'win-unpacked'
      ) {
        candidates.push(candidate);
        continue;
      }
      if (
        platform === 'linux' &&
        entry.isFile() &&
        /^hardcore(?:[ -]canary)?$/i.test(entry.name) &&
        (statSync(candidate).mode & 0o111) !== 0
      ) {
        candidates.push(candidate);
        continue;
      }
      if (entry.isDirectory()) visit(candidate, depth + 1);
    }
  };
  visit(releaseDir, 0);

  return candidates.sort((left, right) => {
    const score = (candidate: string): number => {
      if (platform !== 'darwin') return 0;
      const armBuild = /mac-arm64/i.test(candidate);
      return armBuild === (architecture === 'arm64') ? 0 : 1;
    };
    return score(left) - score(right) || left.localeCompare(right);
  });
}

export function resolvePackagedExecutable(
  application: string,
  platform: NodeJS.Platform = process.platform
): string {
  if (platform !== 'darwin' || !application.endsWith('.app')) return application;
  const macosDirectory = path.join(application, 'Contents', 'MacOS');
  const executable = readdirSync(macosDirectory, { withFileTypes: true }).find((entry) =>
    entry.isFile()
  );
  if (!executable) throw new Error(`No executable found in ${macosDirectory}`);
  return path.join(macosDirectory, executable.name);
}

export function hasValidSqliteHeader(databasePath: string): boolean {
  if (!existsSync(databasePath)) return false;
  return readFileSync(databasePath).subarray(0, SQLITE_HEADER.length).equals(SQLITE_HEADER);
}

export function createPackagedStartupEnvironment(
  input: {
    scratch: string;
    userData: string;
    database: string;
    logFile: string;
  },
  baseEnvironment: NodeJS.ProcessEnv = process.env
): NodeJS.ProcessEnv {
  return {
    ...baseEnvironment,
    // Background CAD provisioning mutates provider plugin configuration. Keep
    // those writes inside the disposable smoke profile as well as app data.
    CODEX_HOME: path.join(input.scratch, 'codex-home'),
    CLAUDE_CONFIG_DIR: path.join(input.scratch, 'claude-config'),
    XDG_CONFIG_HOME: path.join(input.scratch, 'xdg-config'),
    EMDASH_USER_DATA_DIR: input.userData,
    EMDASH_DB_FILE: input.database,
    EMDASH_LOG_FILE: input.logFile,
    HARDCORE_LOG_FILE: input.logFile,
    EMDASH_LOG_LEVEL: 'info',
    EMDASH_DISABLE_NATIVE_DB: '0',
    EMDASH_FORCE_BOOT_FAILURE: '0',
    HARDCORE_CAD_RUNTIME_ROOT: path.join(input.scratch, 'cad-runtime'),
    TELEMETRY_ENABLED: 'false',
  };
}

async function verifyPackagedStartup(application: string): Promise<void> {
  const scratch = mkdtempSync(path.join(tmpdir(), 'hardcore-packaged-startup-'));
  const userData = path.join(scratch, 'user-data');
  const database = path.join(userData, 'startup-smoke.db');
  const logFile = path.join(scratch, 'startup.log');
  const executable = resolvePackagedExecutable(application);
  const launchArgs = [
    ...(process.platform === 'darwin' ? ['--use-mock-keychain'] : []),
    ...(process.platform === 'linux' ? ['--no-sandbox', '--disable-dev-shm-usage'] : []),
    '--disable-gpu',
  ];
  const environment = createPackagedStartupEnvironment({
    scratch,
    userData,
    database,
    logFile,
  });
  for (const directory of [
    environment.CODEX_HOME,
    environment.CLAUDE_CONFIG_DIR,
    environment.XDG_CONFIG_HOME,
  ]) {
    if (directory) mkdirSync(directory, { recursive: true });
  }

  let child: ChildProcess | undefined;
  let passed = false;
  try {
    step(`Launching packaged app with isolated profile: ${application}`);
    // Own process group (POSIX) so Chromium helpers and any CAD runtime provisioner
    // the app spawns are signalled with it, and stop writing the scratch profile.
    child = spawn(executable, launchArgs, {
      env: environment,
      stdio: 'ignore',
      detached: process.platform !== 'win32',
    });
    const deadline = Date.now() + STARTUP_TIMEOUT_MS;
    while (Date.now() < deadline) {
      const source = existsSync(logFile) ? readFileSync(logFile, 'utf8') : '';
      const result = parsePackagedStartupLog(source);
      if (result.status === 'failed') throw new Error(result.detail);
      if (result.status === 'ready') {
        if (!hasValidSqliteHeader(database)) {
          throw new Error(`The startup database is missing or invalid: ${database}`);
        }
        passed = true;
        info(`Packaged app reached a usable workspace in ${result.usableWorkspaceMs} ms`);
        return;
      }
      if (child.exitCode !== null || child.signalCode !== null) {
        throw new Error(
          `The packaged app exited before startup completed (${child.signalCode ?? child.exitCode})`
        );
      }
      await delay(250);
    }
    throw new Error(`Packaged app startup timed out after ${STARTUP_TIMEOUT_MS} ms`);
  } finally {
    if (child) await stopChild(child);
    if (passed) {
      // The app may still be tearing down a CAD runtime provisioner it spawned;
      // outwait the last writes instead of failing a passed smoke on ENOTEMPTY.
      rmSync(scratch, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 });
    } else {
      if (existsSync(logFile)) {
        const source = readFileSync(logFile, 'utf8');
        const tail = source.slice(-32_000);
        console.error(`Packaged startup log tail:\n${tail}`);
      }
      console.error(`Packaged startup diagnostics retained at ${scratch}`);
    }
  }
}

function signalTree(child: ChildProcess, signal: NodeJS.Signals): void {
  if (child.pid !== undefined && process.platform !== 'win32') {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch {
      // The group is already gone; fall back to the process itself.
    }
  }
  child.kill(signal);
}

async function stopChild(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()));
  signalTree(child, 'SIGTERM');
  const stopped = await Promise.race([exited.then(() => true), delay(5_000).then(() => false)]);
  if (!stopped && child.exitCode === null) {
    signalTree(child, 'SIGKILL');
    await exited;
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function main(args = process.argv.slice(2)): Promise<void> {
  const { values } = parseArgs({
    args,
    options: {
      app: { type: 'string' },
      'release-dir': { default: 'release', type: 'string' },
    },
    strict: true,
  });
  const applications = values.app
    ? [path.resolve(values.app)]
    : findPackagedApplications(path.resolve(values['release-dir']));
  if (applications.length === 0) {
    fail(`No launchable packaged app was found under ${values['release-dir']}`);
  }
  await verifyPackagedStartup(applications[0]);
}

const isDirectRun =
  process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;

if (isDirectRun) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}

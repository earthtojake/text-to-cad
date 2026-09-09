/**
 * Packaged-build cold-boot benchmark.
 *
 * Boots the packaged app N times against an isolated fixture profile and
 * reports the two boot metrics against their targets:
 *
 *   launch → window visible   (target ≤ 1.5 s)
 *   launch → usable workspace (target ≤ 5 s)
 *
 * Measurement conditions (see .scratch/boot-time/issues/03-choose-metric-and-target.md):
 * packaged build, isolated profile with 8 local projects, cold-app/warm-OS,
 * median of N runs. This script is the release-checklist boot check — run it
 * before releases and when touching boot code.
 *
 * Usage:
 *   pnpm run boot:bench [-- --app <path/to/Hardcore.app>] [--runs 5] [--reset]
 *
 * The app must be built with `VITE_LOG_LEVEL=info` so renderer boot-timeline
 * marks are emitted:
 *   VITE_LOG_LEVEL=info pnpm run build && pnpm exec electron-builder --mac --dir \
 *     --config electron-builder.config.ts
 *
 * The profile lives under $TMPDIR/emdash-boot-bench and is fully isolated from
 * any real install via EMDASH_USER_DATA_DIR + EMDASH_DB_FILE. `--reset`
 * rebuilds it from scratch.
 */

import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const TARGETS = {
  windowVisibleMs: 1500,
  usableWorkspaceMs: 5000,
};

const PROJECT_COUNT = 8;
const WARMUP_TIMEOUT_MS = 120_000;
const RUN_TIMEOUT_MS = 60_000;
const BETWEEN_RUNS_MS = 3_000;

export type RunResult = {
  windowVisibleMs: number | undefined;
  usableWorkspaceMs: number | undefined;
  /** All boot-timeline marks with ms since process start, for diagnostics. */
  marks: Record<string, number>;
  workerReadyMs: Record<string, number>;
};

// --- log parsing ------------------------------------------------------------

/**
 * Parses one run's log file into the two metrics plus a mark breakdown.
 *
 * Main-process lines are pino JSON: { time, msg: 'boot-timeline', mark,
 * sinceProcessStartMs }. Renderer lines are intake JSON: { timestamp, source:
 * 'renderer', data: ['boot-timeline renderer', { mark, sincePageStartMs }] }.
 * Renderer marks are placed on the process-start axis via their intake
 * timestamps (adds ~1 wire round-trip of skew, small relative to the budget).
 */
export function parseRunLog(text: string): RunResult {
  const result: RunResult = {
    windowVisibleMs: undefined,
    usableWorkspaceMs: undefined,
    marks: {},
    workerReadyMs: {},
  };
  let processStartEpochMs: number | undefined;
  type RendererMark = { mark: string; epochMs: number };
  const rendererMarks: RendererMark[] = [];

  for (const line of text.split('\n')) {
    if (!line.startsWith('{')) continue;
    let entry: Record<string, unknown>;
    try {
      entry = JSON.parse(line) as Record<string, unknown>;
    } catch {
      continue;
    }

    if (entry.msg === 'boot-timeline' && typeof entry.sinceProcessStartMs === 'number') {
      const mark = String(entry.mark);
      result.marks[mark] = entry.sinceProcessStartMs;
      if (mark === 'main-entered') {
        const lineEpochMs =
          typeof entry.time === 'number' ? entry.time : Date.parse(String(entry.time));
        if (!Number.isNaN(lineEpochMs)) {
          processStartEpochMs = lineEpochMs - entry.sinceProcessStartMs;
        }
      }
      // 'window-visible' is the actual show() moment (window-first boot);
      // 'window-ready-to-show' is kept as a fallback for older builds.
      if (mark === 'window-visible') {
        result.windowVisibleMs = entry.sinceProcessStartMs;
      }
      if (mark === 'window-ready-to-show' && result.windowVisibleMs === undefined) {
        result.windowVisibleMs = entry.sinceProcessStartMs;
      }
      continue;
    }

    if (
      entry.msg === 'boot-timeline worker ready' &&
      typeof entry.sinceWorkersStartMs === 'number'
    ) {
      result.workerReadyMs[String(entry.worker)] = entry.sinceWorkersStartMs;
      continue;
    }

    if (entry.source === 'renderer' && Array.isArray(entry.data)) {
      const [label, fields] = entry.data as [unknown, Record<string, unknown> | undefined];
      if (label !== 'boot-timeline renderer' || !fields || typeof fields.mark !== 'string') {
        continue;
      }
      const epochMs = Date.parse(String(entry.timestamp));
      if (Number.isNaN(epochMs)) continue;
      rendererMarks.push({ mark: fields.mark, epochMs });
    }
  }

  if (processStartEpochMs !== undefined) {
    for (const { mark, epochMs } of rendererMarks) {
      const sinceProcessStartMs = Math.round(epochMs - processStartEpochMs);
      result.marks[`renderer:${mark}`] = sinceProcessStartMs;
      if (mark === 'app-content-ready') result.usableWorkspaceMs = sinceProcessStartMs;
    }
  }

  return result;
}

export function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

// --- profile setup ----------------------------------------------------------

type Profile = {
  root: string;
  userDataDir: string;
  dbFile: string;
  logsDir: string;
  reposDir: string;
};

function profilePaths(root: string): Profile {
  return {
    root,
    userDataDir: path.join(root, 'user-data'),
    dbFile: path.join(root, 'user-data', 'emdash4.db'),
    logsDir: path.join(root, 'logs'),
    reposDir: path.join(root, 'repos'),
  };
}

function appEnv(profile: Profile, logFile: string): NodeJS.ProcessEnv {
  return {
    ...process.env,
    EMDASH_USER_DATA_DIR: profile.userDataDir,
    EMDASH_DB_FILE: profile.dbFile,
    EMDASH_LOG_FILE: logFile,
    EMDASH_LOG_LEVEL: 'info',
    TELEMETRY_ENABLED: 'false',
  };
}

function createFixtureRepo(dir: string, index: number): void {
  fs.mkdirSync(dir, { recursive: true });
  const git = (...args: string[]) => execFileSync('git', args, { cwd: dir, stdio: 'pipe' });
  git('init', '-b', 'main');
  fs.writeFileSync(
    path.join(dir, 'README.md'),
    `# bench-project-${index}\n\nBoot benchmark fixture.\n`
  );
  fs.mkdirSync(path.join(dir, 'src'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'src', 'index.ts'), `export const projectIndex = ${index};\n`);
  git('add', '-A');
  git(
    '-c',
    'user.name=boot-bench',
    '-c',
    'user.email=boot-bench@example.invalid',
    'commit',
    '-m',
    'fixture commit'
  );
}

function seedProjects(profile: Profile): void {
  const statements: string[] = [];
  for (let i = 1; i <= PROJECT_COUNT; i++) {
    const projectId = `bench-proj-${i}`;
    const workspaceId = `bench-ws-${i}`;
    const repoPath = path.join(profile.reposDir, `bench-project-${i}`);
    statements.push(
      `INSERT INTO workspaces (id, type, kind, location, path) VALUES ('${workspaceId}', 'local', 'repository', 'local', '${repoPath}');`,
      `INSERT INTO projects (id, name, base_ref, repository_workspace_id) VALUES ('${projectId}', 'bench-project-${i}', 'main', '${workspaceId}');`,
      `INSERT INTO project_settings (project_id) VALUES ('${projectId}');`
    );
  }
  execFileSync('sqlite3', [profile.dbFile], {
    input: statements.join('\n'),
    stdio: ['pipe', 'pipe', 'inherit'],
  });
}

// --- app lifecycle ----------------------------------------------------------

function resolveAppBinary(appPath: string): string {
  const macosDir = path.join(appPath, 'Contents', 'MacOS');
  const [binary] = fs.readdirSync(macosDir);
  if (!binary) throw new Error(`No executable found in ${macosDir}`);
  return path.join(macosDir, binary);
}

/**
 * Locally packaged builds are unsigned: the electron-builder fuses step
 * invalidates Electron's ad-hoc signature and macOS then SIGKILLs the app at
 * launch (Code Signature Invalid). Re-sign ad-hoc, bottom-up with the app's
 * entitlements (a bare `codesign --deep` strips them and the app dies
 * silently at launch).
 */
function ensureRunnableSignature(appPath: string): void {
  try {
    execFileSync('codesign', ['--verify', '--deep', '--strict', appPath], { stdio: 'pipe' });
    return;
  } catch {
    console.log('Signature invalid (local unsigned build) — re-signing ad-hoc...');
  }
  const entitlements = path.resolve(__dirname, '..', 'build', 'entitlements.mac.plist');
  const frameworksDir = path.join(appPath, 'Contents', 'Frameworks');
  const sign = (target: string, withEntitlements: boolean) =>
    execFileSync(
      'codesign',
      [
        '--force',
        '--sign',
        '-',
        ...(withEntitlements ? ['--entitlements', entitlements] : []),
        target,
      ],
      { stdio: 'pipe' }
    );
  for (const entry of fs.readdirSync(frameworksDir)) {
    const target = path.join(frameworksDir, entry);
    if (entry.endsWith('.framework')) sign(target, false);
    if (entry.endsWith('.app')) sign(target, true);
  }
  sign(appPath, true);
}

function launchApp(binary: string, env: NodeJS.ProcessEnv): ChildProcess {
  // --use-mock-keychain: ad-hoc signed local builds trigger a macOS Keychain
  // password prompt on every launch (cookie-encryption fuse + unrecognized
  // signature), which both blocks the run and skews the timings.
  return spawn(binary, ['--use-mock-keychain'], { env, stdio: 'ignore', detached: false });
}

async function waitForLogMark(
  logFile: string,
  predicate: (text: string) => boolean,
  timeoutMs: number
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(logFile) && predicate(fs.readFileSync(logFile, 'utf8'))) return true;
    await sleep(250);
  }
  return false;
}

async function stopApp(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null) return;
  const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()));
  child.kill('SIGTERM');
  const killTimer = setTimeout(() => child.kill('SIGKILL'), 5_000);
  await exited;
  clearTimeout(killTimer);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- main -------------------------------------------------------------------

function parseArgs(argv: string[]) {
  const args = {
    app: undefined as string | undefined,
    runs: 5,
    reset: false,
    profile: undefined as string | undefined,
  };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--app') args.app = argv[++i];
    else if (argv[i] === '--runs') args.runs = Number(argv[++i]);
    else if (argv[i] === '--profile') args.profile = argv[++i];
    else if (argv[i] === '--reset') args.reset = true;
  }
  return args;
}

function findDefaultApp(): string {
  const releaseDir = path.resolve(__dirname, '..', 'release');
  const candidates = fs
    .readdirSync(releaseDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith('mac'))
    .flatMap((entry) => {
      const dir = path.join(releaseDir, entry.name);
      return fs
        .readdirSync(dir)
        .filter((name) => name.endsWith('.app'))
        .map((name) => path.join(dir, name));
    });
  if (candidates.length === 0) {
    throw new Error(
      'No packaged .app found under release/. Build one first:\n' +
        '  VITE_LOG_LEVEL=info pnpm run build && pnpm exec electron-builder --mac --dir --config electron-builder.config.ts'
    );
  }
  return candidates[0];
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const appPath = args.app ?? findDefaultApp();
  ensureRunnableSignature(appPath);
  const binary = resolveAppBinary(appPath);
  const profile = profilePaths(args.profile ?? path.join(os.tmpdir(), 'emdash-boot-bench'));

  console.log(`app:     ${appPath}`);
  console.log(`profile: ${profile.root}`);

  if (args.reset && fs.existsSync(profile.root)) {
    fs.rmSync(profile.root, { recursive: true, force: true });
  }

  if (!fs.existsSync(profile.dbFile)) {
    console.log(`\nSetting up fixture profile (${PROJECT_COUNT} projects)...`);
    fs.mkdirSync(profile.userDataDir, { recursive: true });
    fs.mkdirSync(profile.logsDir, { recursive: true });
    for (let i = 1; i <= PROJECT_COUNT; i++) {
      createFixtureRepo(path.join(profile.reposDir, `bench-project-${i}`), i);
    }

    // Warm-up run: the app itself creates and migrates the database, so the
    // seed only inserts rows against the exact production schema.
    const warmupLog = path.join(profile.logsDir, 'warmup.log');
    const child = launchApp(binary, appEnv(profile, warmupLog));
    const booted = await waitForLogMark(
      warmupLog,
      (text) => text.includes('window-did-finish-load'),
      WARMUP_TIMEOUT_MS
    );
    await stopApp(child);
    if (!booted)
      throw new Error(`Warm-up boot did not finish within ${WARMUP_TIMEOUT_MS}ms (${warmupLog})`);
    seedProjects(profile);
    console.log('Fixture profile ready.');
  }

  const results: RunResult[] = [];
  for (let run = 1; run <= args.runs; run++) {
    const logFile = path.join(profile.logsDir, `run-${run}.log`);
    fs.rmSync(logFile, { force: true });
    const child = launchApp(binary, appEnv(profile, logFile));
    const ready = await waitForLogMark(
      logFile,
      (text) => text.includes('app-content-ready'),
      RUN_TIMEOUT_MS
    );
    // Give trailing Project-context and attachment marks a moment to flush before stopping.
    await sleep(1_000);
    await stopApp(child);
    const parsed = parseRunLog(fs.readFileSync(logFile, 'utf8'));
    results.push(parsed);
    console.log(
      `run ${run}: window ${fmt(parsed.windowVisibleMs)}  usable ${fmt(parsed.usableWorkspaceMs)}` +
        (ready ? '' : '  (timed out waiting for app-content-ready)')
    );
    await sleep(BETWEEN_RUNS_MS);
  }

  const windowValues = results.map((r) => r.windowVisibleMs).filter(isNumber);
  const usableValues = results.map((r) => r.usableWorkspaceMs).filter(isNumber);
  if (windowValues.length === 0 || usableValues.length === 0) {
    throw new Error('No successful runs produced both metrics; inspect the run logs.');
  }

  const windowMedian = median(windowValues);
  const usableMedian = median(usableValues);
  const windowPass = windowMedian <= TARGETS.windowVisibleMs;
  const usablePass = usableMedian <= TARGETS.usableWorkspaceMs;

  console.log('\n=== boot-bench result (median of successful runs) ===');
  console.log(
    `launch → window visible:   ${windowMedian} ms  (target ≤ ${TARGETS.windowVisibleMs} ms)  ${windowPass ? 'PASS' : 'FAIL'}`
  );
  console.log(
    `launch → usable workspace: ${usableMedian} ms  (target ≤ ${TARGETS.usableWorkspaceMs} ms)  ${usablePass ? 'PASS' : 'FAIL'}`
  );
  console.log(`run logs: ${profile.logsDir}`);

  if (!windowPass || !usablePass) process.exitCode = 1;
}

function isNumber(value: number | undefined): value is number {
  return typeof value === 'number';
}

function fmt(value: number | undefined): string {
  return value === undefined ? 'n/a' : `${value}ms`;
}

const isDirectRun =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isDirectRun) {
  main().catch((error: unknown) => {
    console.error(error);
    process.exit(1);
  });
}

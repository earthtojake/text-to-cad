/**
 * `pnpm run doctor` — report-only environment health check. It answers "is my
 * setup fine, or is HEAD just red?" in one command and never fixes anything;
 * every failing line names the fixing command instead.
 *
 * Checks (see doctor-checks.ts for the classification logic):
 * - node / pnpm versions against the package.json pins.
 * - The system-Node better-sqlite3 side copy (tooling/node-deps) loads and can
 *   open a database.
 * - The app better-sqlite3 copy is built for the installed Electron's ABI.
 *   Loading an Electron-ABI binary from system Node is impossible, so this is
 *   an indirect probe: dlopen it and match the NODE_MODULE_VERSION in the
 *   failure against the expected Electron ABI (from node-abi).
 * - node-pty loads (its N-API prebuild serves Node and Electron) and its macOS
 *   spawn-helper is executable.
 * - Playwright browsers are installed (chromium executablePath exists).
 * - Docker reachability — needed only for remote flows, never a failure.
 * - A running Nx daemon (informational; a stale daemon can serve stale state).
 * - Active escape-hatch env vars.
 */
import { spawnSync } from 'node:child_process';
import { accessSync, constants, existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  checkEscapeHatches,
  checkPinnedVersion,
  classifyElectronAbiProbe,
  formatReport,
  overallExitCode,
  parsePnpmVersion,
  type CheckResult,
} from './doctor-checks.ts';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(appRoot, '..', '..');
const appRequire = createRequire(path.join(appRoot, 'package.json'));

function readJson(file: string): Record<string, unknown> {
  return JSON.parse(readFileSync(file, 'utf8'));
}

function checkNodeVersion(): CheckResult {
  const rootPackage = readJson(path.join(repoRoot, 'package.json')) as {
    devEngines?: { runtime?: { version?: string } };
  };
  const pinned = rootPackage.devEngines?.runtime?.version ?? 'unknown';
  return checkPinnedVersion('node', process.versions.node, pinned);
}

function checkPnpmVersion(): CheckResult {
  const rootPackage = readJson(path.join(repoRoot, 'package.json')) as {
    packageManager?: string;
  };
  const pinned = rootPackage.packageManager?.split('@')[1] ?? 'unknown';
  return checkPinnedVersion('pnpm', parsePnpmVersion(process.env.npm_config_user_agent), pinned);
}

function checkSideProjectSqlite(): CheckResult {
  const name = 'better-sqlite3 (system-Node copy, tooling/node-deps)';
  try {
    const sideRequire = createRequire(path.join(appRoot, 'tooling', 'node-deps', 'package.json'));
    const Database = sideRequire('better-sqlite3');
    const db = new Database(':memory:');
    db.prepare('select 1').get();
    db.close();
    return { name, status: 'ok', detail: 'loads and opens a database under system Node' };
  } catch (error) {
    return {
      name,
      status: 'fail',
      detail: `not loadable: ${error instanceof Error ? error.message.split('\n')[0] : String(error)}`,
      fix: 'pnpm install  (postinstall reinstalls tooling/node-deps via pnpm)',
    };
  }
}

function checkAppSqliteElectronAbi(): CheckResult {
  let expectedElectronAbi: string;
  try {
    const electronVersion = (appRequire('electron/package.json') as { version: string }).version;
    const nodeAbi = appRequire('node-abi') as {
      getAbi: (version: string, runtime: string) => string;
    };
    expectedElectronAbi = nodeAbi.getAbi(electronVersion, 'electron');
  } catch (error) {
    return {
      name: 'better-sqlite3 (app copy, Electron ABI)',
      status: 'fail',
      detail: `could not resolve the installed Electron ABI: ${String(error)}`,
      fix: 'pnpm install',
    };
  }

  try {
    // require() alone is not a probe: better-sqlite3 loads its native binding
    // lazily, so the addon is only dlopen'd when a Database is constructed.
    const Database = appRequire('better-sqlite3') as new (path: string) => { close: () => void };
    new Database(':memory:').close();
    return classifyElectronAbiProbe({ loaded: true, expectedElectronAbi });
  } catch (error) {
    return classifyElectronAbiProbe({
      loaded: false,
      errorMessage: error instanceof Error ? error.message : String(error),
      expectedElectronAbi,
    });
  }
}

function checkNodePty(): CheckResult {
  const name = 'node-pty (N-API, shared by Node and Electron)';
  try {
    appRequire('node-pty');
  } catch (error) {
    return {
      name,
      status: 'fail',
      detail: `not loadable: ${error instanceof Error ? error.message.split('\n')[0] : String(error)}`,
      fix: 'pnpm install',
    };
  }
  if (process.platform === 'darwin') {
    const helper = path.join(
      path.dirname(appRequire.resolve('node-pty/package.json')),
      'prebuilds',
      `${process.platform}-${process.arch}`,
      'spawn-helper'
    );
    if (existsSync(helper)) {
      try {
        accessSync(helper, constants.X_OK);
      } catch {
        return {
          name,
          status: 'fail',
          detail: 'loads, but the macOS spawn-helper prebuild is not executable',
          fix: 'pnpm install  (postinstall restores the exec bit)',
        };
      }
    }
  }
  return { name, status: 'ok', detail: 'loads under system Node' };
}

function checkPlaywrightBrowsers(): CheckResult {
  const name = 'Playwright browsers (app browser test project)';
  try {
    const playwright = appRequire('playwright-core') as {
      chromium: { executablePath: () => string };
    };
    const executable = playwright.chromium.executablePath();
    if (existsSync(executable)) {
      return { name, status: 'ok', detail: `chromium present at ${executable}` };
    }
    return {
      name,
      status: 'fail',
      detail: 'chromium is not installed',
      fix: 'pnpm exec playwright install',
    };
  } catch (error) {
    return {
      name,
      status: 'fail',
      detail: `playwright-core not resolvable: ${String(error)}`,
      fix: 'pnpm install',
    };
  }
}

function checkDocker(): CheckResult {
  const name = 'Docker (needed only for remote flows)';
  const result = spawnSync('docker', ['info', '--format', '{{.ServerVersion}}'], {
    timeout: 5000,
    encoding: 'utf8',
  });
  // `docker info --format` exits 0 even when the daemon is unreachable, so a
  // reachable daemon must also report a server version on stdout.
  const serverVersion = result.stdout?.trim();
  if (result.status === 0 && serverVersion) {
    return { name, status: 'ok', detail: `daemon reachable (server ${serverVersion})` };
  }
  return {
    name,
    status: 'info',
    detail:
      'daemon not reachable — fine unless you run the workspace-server stack or the gated remote tests',
  };
}

function checkNxDaemon(): CheckResult {
  const name = 'Nx daemon';
  const processFile = path.join(repoRoot, '.nx', 'workspace-data', 'd', 'server-process.json');
  try {
    const info = readJson(processFile) as { processId?: number };
    if (typeof info.processId === 'number') {
      process.kill(info.processId, 0);
      return {
        name,
        status: 'info',
        detail: `running (pid ${info.processId}) — if task results look stale, stop it with: pnpm exec nx daemon --stop`,
      };
    }
  } catch {
    // No daemon metadata or the recorded pid is dead — nothing running.
  }
  return { name, status: 'ok', detail: 'not running' };
}

function main(): void {
  const results: CheckResult[] = [
    checkNodeVersion(),
    checkPnpmVersion(),
    checkSideProjectSqlite(),
    checkAppSqliteElectronAbi(),
    checkNodePty(),
    checkPlaywrightBrowsers(),
    checkDocker(),
    checkNxDaemon(),
    checkEscapeHatches(process.env),
  ];

  console.log('emdash doctor — report only, fixes nothing\n');
  console.log(formatReport(results));

  const exitCode = overallExitCode(results);
  console.log(
    exitCode === 0
      ? '\nEnvironment looks healthy.'
      : '\nEnvironment problems found — each failing line above names the fixing command.'
  );
  process.exit(exitCode);
}

main();

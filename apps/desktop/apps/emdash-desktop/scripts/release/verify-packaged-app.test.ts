import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  createPackagedStartupEnvironment,
  findPackagedApplications,
  hasValidSqliteHeader,
  parsePackagedStartupLog,
  resolvePackagedExecutable,
} from './verify-packaged-app.ts';

const scratchDirectories: string[] = [];

afterEach(() => {
  for (const directory of scratchDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

function scratch(): string {
  const directory = mkdtempSync(path.join(tmpdir(), 'hardcore-startup-test-'));
  scratchDirectories.push(directory);
  return directory;
}

describe('packaged startup log', () => {
  it('requires renderer usability and both database phases', () => {
    const source = JSON.stringify({
      msg: 'boot-report',
      usableWorkspaceMs: 1240,
      phases: { 'db-initialize': 80, 'db-startup-repairs': 12 },
    });

    expect(parsePackagedStartupLog(source)).toEqual({
      status: 'ready',
      usableWorkspaceMs: 1240,
    });
    expect(
      parsePackagedStartupLog(
        JSON.stringify({ msg: 'boot-report', usableWorkspaceMs: 1240, phases: {} })
      )
    ).toEqual({
      status: 'failed',
      detail: 'boot-report did not include a usable workspace and both database phases',
    });
  });

  it('fails immediately when startup enters recovery', () => {
    expect(parsePackagedStartupLog('{"msg":"Boot failed; entering recovery mode"}')).toEqual({
      status: 'failed',
      detail: 'Boot failed; entering recovery mode',
    });
  });
});

describe('packaged app discovery', () => {
  it('prefers a macOS app matching the host architecture and resolves its executable', () => {
    const release = scratch();
    const x64App = path.join(release, 'mac', 'Hardcore.app');
    const armApp = path.join(release, 'mac-arm64', 'Hardcore.app');
    const armExecutable = path.join(armApp, 'Contents', 'MacOS', 'Hardcore');
    mkdirSync(path.join(x64App, 'Contents', 'MacOS'), { recursive: true });
    mkdirSync(path.dirname(armExecutable), { recursive: true });
    writeFileSync(path.join(x64App, 'Contents', 'MacOS', 'Hardcore'), '');
    writeFileSync(armExecutable, '');

    expect(findPackagedApplications(release, 'darwin', 'arm64')).toEqual([armApp, x64App]);
    expect(resolvePackagedExecutable(armApp, 'darwin')).toBe(armExecutable);
  });

  it('discovers unpacked Windows and Linux executables', () => {
    const release = scratch();
    const windows = path.join(release, 'win-unpacked', 'Hardcore.exe');
    const windowsInstaller = path.join(release, 'hardcore-x64.exe');
    const linux = path.join(release, 'linux-unpacked', 'hardcore');
    const linuxCanary = path.join(release, 'linux-canary-unpacked', 'hardcore-canary');
    mkdirSync(path.dirname(windows), { recursive: true });
    mkdirSync(path.dirname(linux), { recursive: true });
    mkdirSync(path.dirname(linuxCanary), { recursive: true });
    writeFileSync(windows, '');
    writeFileSync(windowsInstaller, '');
    writeFileSync(linux, '');
    writeFileSync(linuxCanary, '');
    chmodSync(linux, 0o755);
    chmodSync(linuxCanary, 0o755);

    expect(findPackagedApplications(release, 'win32')).toEqual([windows]);
    expect(findPackagedApplications(release, 'linux')).toEqual([linuxCanary, linux]);
  });
});

describe('packaged app profile isolation', () => {
  it('isolates provider plugin configuration as well as app data', () => {
    const root = scratch();
    const environment = createPackagedStartupEnvironment(
      {
        scratch: root,
        userData: path.join(root, 'user-data'),
        database: path.join(root, 'startup.db'),
        logFile: path.join(root, 'startup.log'),
      },
      {
        PATH: '/usr/bin',
        CODEX_HOME: '/real/codex',
        CLAUDE_CONFIG_DIR: '/real/claude',
      }
    );

    expect(environment.CODEX_HOME).toBe(path.join(root, 'codex-home'));
    expect(environment.CLAUDE_CONFIG_DIR).toBe(path.join(root, 'claude-config'));
    expect(environment.XDG_CONFIG_HOME).toBe(path.join(root, 'xdg-config'));
    expect(environment.HARDCORE_CAD_RUNTIME_ROOT).toBe(path.join(root, 'cad-runtime'));
    expect(environment.PATH).toBe('/usr/bin');
  });
});

it('recognizes a real SQLite database header', () => {
  const database = path.join(scratch(), 'app.db');
  writeFileSync(database, Buffer.concat([Buffer.from('SQLite format 3\0'), Buffer.alloc(32)]));

  expect(hasValidSqliteHeader(database)).toBe(true);
  writeFileSync(database, 'not sqlite');
  expect(hasValidSqliteHeader(database)).toBe(false);
});

import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { classifySpawnPurpose, recordSpawn } from '@emdash/shared/perf';
import type { CommandRunner } from '@core/primitives/command-runner/api/command-runner';

const execFileAsync = promisify(execFile);

export type {
  CommandRunner,
  CommandRunnerOptions,
  CommandRunnerResult,
} from '@core/primitives/command-runner/api/command-runner';

export const runLocalCommand: CommandRunner = async (command, args = [], opts = {}) => {
  recordSpawn(classifySpawnPurpose(command, args), command);
  const { stdout, stderr } = await execFileAsync(command, args, {
    timeout: opts.timeout,
  });
  return { stdout, stderr };
};

function windowsExecutableExtensions(env: NodeJS.ProcessEnv): string[] {
  const pathExt = env.PATHEXT || '.COM;.EXE;.BAT;.CMD';
  return pathExt
    .split(';')
    .map((extension) => extension.trim().toLowerCase())
    .filter(Boolean)
    .map((extension) => (extension.startsWith('.') ? extension : `.${extension}`));
}

function findExecutableOnPath(name: string, env: NodeJS.ProcessEnv = process.env): string | null {
  const pathValue = env.PATH;
  if (!pathValue) return null;

  const extensions =
    process.platform === 'win32' && !path.extname(name)
      ? ['', ...windowsExecutableExtensions(env)]
      : [''];

  for (const directory of pathValue.split(path.delimiter)) {
    if (!directory) continue;

    for (const extension of extensions) {
      const candidate = path.join(directory, `${name}${extension}`);
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        return candidate;
      } catch {}
    }
  }

  return null;
}

export function resolveGitBin(env: NodeJS.ProcessEnv = process.env): string {
  const pathGit = findExecutableOnPath('git', env);
  const candidates = [
    (env.GIT_PATH || '').trim(),
    pathGit,
    '/opt/homebrew/bin/git',
    '/usr/local/bin/git',
    '/usr/bin/git',
  ].filter(Boolean) as string[];
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {}
  }
  return 'git';
}

/** Initial fallback path for Git before the host dependency probe completes. */
export const GIT_EXECUTABLE = resolveGitBin();

let localGitExecutableOverride: string | null = null;
const remoteGitExecutableOverrides = new Map<string, string>();

export function setGitExecutableOverride(executable: string | null, connectionId?: string): void {
  if (connectionId) {
    if (executable) remoteGitExecutableOverrides.set(connectionId, executable);
    else remoteGitExecutableOverrides.delete(connectionId);
    return;
  }

  localGitExecutableOverride = executable;
}

/** Current Git executable selected by the host dependency system, with startup fallback. */
export function getGitExecutable(connectionId?: string): string {
  if (connectionId) return remoteGitExecutableOverrides.get(connectionId) ?? 'git';
  return localGitExecutableOverride ?? GIT_EXECUTABLE;
}

export function isMissingGitExecutableError(error: unknown): boolean {
  const err = error as NodeJS.ErrnoException | undefined;
  return (
    err?.code === 'ENOENT' &&
    (err.path === 'git' || err.path === GIT_EXECUTABLE || err.path === localGitExecutableOverride)
  );
}

export function missingGitExecutableError(): Error {
  return new Error(
    'Git is not installed or Hardcore cannot find it. Install Git, then restart Hardcore.'
  );
}

import { statSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  DEFAULT_SHELL_ENV_PRESERVE_KEYS,
  type ShellEnvCapture,
  type ShellEnvPlatform,
  type ShellEnvPolicy,
} from './types';
import {
  getWindowsEnvValue,
  getWindowsPathEnvKey,
  prependWindowsPathEntry,
  windowsNpmGlobalBin,
} from './windows-env';

export type ApplyShellEnvOptions = {
  readonly mergeBaseEnv?: NodeJS.ProcessEnv;
};

export function applyShellEnvCapture(
  target: NodeJS.ProcessEnv,
  capture: ShellEnvCapture,
  policy: Partial<ShellEnvPolicy> = {},
  options: ApplyShellEnvOptions = {}
): void {
  const platform = policy.platform ?? currentShellEnvPlatform();
  const preserveKeys = policy.preserveKeys ?? DEFAULT_SHELL_ENV_PRESERVE_KEYS;
  const mergeBaseEnv = options.mergeBaseEnv ?? target;

  for (const [key, value] of Object.entries(capture.env)) {
    if (shouldPreserveKey(key, preserveKeys, platform)) continue;

    if (isPathKey(key, platform)) {
      setPathValue(
        target,
        mergePath(value, getPathValue(mergeBaseEnv, platform), platform),
        platform
      );
    } else {
      target[key] = value;
    }
  }

  ensureUserBinDirsInPath(
    target,
    policy.userBinDirs ?? defaultUserBinDirs(target, platform),
    platform
  );
}

export function mergePath(
  shellPath: string,
  currentPath: string,
  platform = currentShellEnvPlatform()
): string {
  const separator = pathSeparator(platform);
  const shellEntries = shellPath.split(separator).filter(Boolean);
  const currentEntries = currentPath.split(separator).filter(Boolean);
  const seen = new Set(normalizedPathEntries(shellEntries, platform));
  const extra = currentEntries.filter((entry) => !seen.has(normalizePathEntry(entry, platform)));
  return [...shellEntries, ...extra].join(separator);
}

export function ensureUserBinDirsInPath(
  env: NodeJS.ProcessEnv = process.env,
  candidates: readonly string[] = defaultUserBinDirs(env, currentShellEnvPlatform()),
  platform = currentShellEnvPlatform()
): string[] {
  const additions = candidates.filter((candidate) => pathEntryExists(candidate));
  if (platform === 'windows') {
    return additions.filter((candidate) => prependWindowsPathEntry(env, candidate));
  }

  const currentPath = env.PATH ?? '';
  const entries = currentPath.split(path.posix.delimiter).filter(Boolean);
  const existing = new Set(entries);
  const missing = additions.filter((candidate) => !existing.has(candidate));
  if (missing.length === 0) return [];
  env.PATH = [...missing, ...entries].join(path.posix.delimiter);
  return missing;
}

export function createDefaultShellEnvPolicy(
  env: NodeJS.ProcessEnv = process.env,
  platform = currentShellEnvPlatform()
): ShellEnvPolicy {
  return {
    preserveKeys: DEFAULT_SHELL_ENV_PRESERVE_KEYS,
    userBinDirs: defaultUserBinDirs(env, platform),
    platform,
  };
}

export function currentShellEnvPlatform(): ShellEnvPlatform {
  return process.platform === 'win32' ? 'windows' : 'posix';
}

function defaultUserBinDirs(env: NodeJS.ProcessEnv, platform: ShellEnvPlatform): string[] {
  if (platform === 'windows') {
    const npmPath = windowsNpmGlobalBin(env);
    return npmPath ? [npmPath] : [];
  }

  return [path.join(os.homedir(), '.local', 'bin')];
}

function shouldPreserveKey(
  key: string,
  preserveKeys: ReadonlySet<string>,
  platform: ShellEnvPlatform
): boolean {
  if (platform !== 'windows') return preserveKeys.has(key);
  const lowerKey = key.toLowerCase();
  return [...preserveKeys].some((candidate) => candidate.toLowerCase() === lowerKey);
}

function isPathKey(key: string, platform: ShellEnvPlatform): boolean {
  return platform === 'windows' ? key.toLowerCase() === 'path' : key === 'PATH';
}

function getPathValue(env: NodeJS.ProcessEnv, platform: ShellEnvPlatform): string {
  if (platform === 'windows') {
    return getWindowsEnvValue(env, 'PATH') ?? '';
  }
  return env.PATH ?? '';
}

function setPathValue(env: NodeJS.ProcessEnv, value: string, platform: ShellEnvPlatform): void {
  if (platform === 'windows') {
    env[getWindowsPathEnvKey(env)] = value;
    return;
  }
  env.PATH = value;
}

function pathSeparator(platform: ShellEnvPlatform): string {
  return platform === 'windows' ? path.win32.delimiter : path.posix.delimiter;
}

function normalizedPathEntries(entries: readonly string[], platform: ShellEnvPlatform): string[] {
  return entries.map((entry) => normalizePathEntry(entry, platform));
}

function normalizePathEntry(entry: string, platform: ShellEnvPlatform): string {
  return platform === 'windows' ? entry.toLowerCase() : entry;
}

function pathEntryExists(entry: string): boolean {
  try {
    return statSync(entry).isDirectory();
  } catch {
    return false;
  }
}

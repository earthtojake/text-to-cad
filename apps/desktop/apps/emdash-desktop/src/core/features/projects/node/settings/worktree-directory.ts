import type path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';

export type PathPlatform = 'posix' | 'win32';

type PathApi = Pick<typeof path, 'join'>;

export type WorktreeDirectoryFileSystem = {
  mkdir(
    path: string,
    options?: { recursive?: boolean }
  ): Promise<Result<void, { message: string }>>;
  realPath(path: string): Promise<Result<string, { message: string }>>;
};

function isWindowsDriveAbsolute(input: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(input);
}

function isWindowsUncAbsolute(input: string): boolean {
  return input.startsWith('\\\\');
}

function isPosixAbsolute(input: string): boolean {
  return input.startsWith('/');
}

function isNativeAbsolute(input: string, platform: PathPlatform): boolean {
  if (platform === 'win32') return isWindowsDriveAbsolute(input) || isWindowsUncAbsolute(input);
  return isPosixAbsolute(input);
}

export async function normalizeWorktreeDirectory(
  input: string,
  options: {
    pathApi: PathApi;
    pathPlatform: PathPlatform;
    homeDirectory?: string;
    resolveHomeDirectory?: () => Promise<string>;
  }
): Promise<Result<string, UpdateProjectSettingsError>> {
  try {
    const trimmed = input.trim();
    let normalized = trimmed;

    if (trimmed === '~' || trimmed.startsWith('~/') || trimmed.startsWith('~\\')) {
      const resolvedHomeDirectory = options.resolveHomeDirectory
        ? (await options.resolveHomeDirectory()).trim()
        : undefined;
      const homeDirectory = options.homeDirectory ?? resolvedHomeDirectory;
      if (!homeDirectory) {
        return err({ type: 'invalid-worktree-directory' });
      }
      normalized =
        trimmed === '~' ? homeDirectory : options.pathApi.join(homeDirectory, trimmed.slice(2));
    }

    if (isNativeAbsolute(normalized, options.pathPlatform)) {
      return ok(normalized);
    }
    return err({ type: 'invalid-worktree-directory' });
  } catch {
    return err({ type: 'invalid-worktree-directory' });
  }
}

export async function canonicalizeWorktreeDirectory(
  directory: string,
  fs: WorktreeDirectoryFileSystem
): Promise<Result<string, UpdateProjectSettingsError>> {
  const madeDir = await fs.mkdir(directory, { recursive: true });
  if (!madeDir.success) return err({ type: 'invalid-worktree-directory' });

  const realPath = await fs.realPath(directory);
  if (!realPath.success) return err({ type: 'invalid-worktree-directory' });
  return ok(realPath.data);
}

export async function resolveAndValidateWorktreeDirectory(
  input: string | undefined,
  options: {
    pathApi: PathApi;
    pathPlatform: PathPlatform;
    fs: WorktreeDirectoryFileSystem;
    homeDirectory?: string;
    resolveHomeDirectory?: () => Promise<string>;
  }
): Promise<Result<string | undefined, UpdateProjectSettingsError>> {
  const trimmed = input?.trim();
  if (!trimmed) {
    return ok(undefined);
  }

  const normalized = await normalizeWorktreeDirectory(trimmed, {
    pathApi: options.pathApi,
    pathPlatform: options.pathPlatform,
    homeDirectory: options.homeDirectory,
    resolveHomeDirectory: options.resolveHomeDirectory,
  });
  if (!normalized.success) {
    return normalized;
  }
  return canonicalizeWorktreeDirectory(normalized.data, options.fs);
}

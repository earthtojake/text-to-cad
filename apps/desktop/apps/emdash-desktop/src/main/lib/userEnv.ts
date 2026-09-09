import os from 'node:os';
import path from 'node:path';
import {
  createShellEnvManager,
  ensureUserBinDirsInPath as ensureCoreUserBinDirsInPath,
  ensureWindowsNpmGlobalBinInPath as ensureCoreWindowsNpmGlobalBinInPath,
  parseEnvOutput,
  SHELL_ENV_CAPTURE_GUARD,
} from '@emdash/core/services/shell-env/node';
import { log } from '@main/lib/logger';
import { buildExternalToolEnv } from './childProcessEnv';

/**
 * Keys that must never be overwritten from the shell env capture.
 *
 * - AppImage runtime vars would corrupt child-process environments when
 *   running from a Linux AppImage bundle.
 * - Electron-specific vars must retain the values Electron set at boot.
 * - NODE_ENV is set by the build toolchain and must not be overridden.
 */
const PRESERVE_KEYS = new Set([
  // AppImage
  'APPDIR',
  'APPIMAGE',
  'ARGV0',
  'CHROME_DESKTOP',
  'GSETTINGS_SCHEMA_DIR',
  'OWD',
  // Electron
  'ELECTRON_RUN_AS_NODE',
  'ELECTRON_NO_ATTACH_CONSOLE',
  'ELECTRON_ENABLE_LOGGING',
  'ELECTRON_ENABLE_STACK_DUMPING',
  // Build toolchain
  'NODE_ENV',
]);

export { SHELL_ENV_CAPTURE_GUARD };

const USER_BIN_DIRS = [path.join(os.homedir(), '.local', 'bin')];

export const userShellEnvManager = createShellEnvManager({
  target: process.env,
  baseEnvForProbe: buildExternalToolEnv,
  policy: {
    preserveKeys: PRESERVE_KEYS,
    userBinDirs: USER_BIN_DIRS,
  },
  logger: log,
});

export function ensureUserBinDirsInPath(candidates: string[] = USER_BIN_DIRS): string[] {
  return ensureCoreUserBinDirsInPath(process.env, candidates);
}

export function ensureWindowsNpmGlobalBinInPath(
  env: NodeJS.ProcessEnv = process.env
): string | null {
  return ensureCoreWindowsNpmGlobalBinInPath(env);
}

/** Returns a synchronous copy for compatibility consumers that cannot spawn. */
export function getUserShellEnv(): Record<string, string> {
  return userShellEnvManager.getUserShellEnv();
}

/**
 * Starts `$SHELL -ilc 'env'` with a 5 s timeout and returns immediately. On
 * any error (timeout, missing shell, restricted environment) the manager logs
 * a warning and retains a sanitized usable environment.
 *
 * Spawn-capable runtimes request the separately owned snapshot through the
 * parent controller; the manager makes their first request await this capture.
 */
export function startUserEnvCapture(): void {
  void refreshUserEnv().catch((error: unknown) => {
    log.warn('[shell-env] Unexpected initial capture failure', { error });
  });
}

export async function refreshUserEnv(): Promise<void> {
  if (process.platform === 'win32') {
    // Windows PATH is managed differently; refresh still snapshots the cleaned
    // environment after adding npm's global bin directory.
    ensureWindowsNpmGlobalBinInPath();
  }

  // Route through buildExternalToolEnv so AppImage runtime vars (APPIMAGE,
  // APPDIR, ARGV0, ...) and `/tmp/.mount_*` PATH entries don't leak into
  // the probe shell. Otherwise login-shell hooks that resolve a binary by
  // name through PATH (mise/starship/oh-my-zsh) can re-enter the AppImage
  // and fork-bomb the app on Linux. See #1679.
  await userShellEnvManager.refresh();
}

/**
 * Parses a remote `env` command output into a key→value map.
 * Exported for use by the SSH connection manager.
 */
export function parseRemoteEnvOutput(raw: string): Record<string, string> {
  return parseEnvOutput(raw);
}

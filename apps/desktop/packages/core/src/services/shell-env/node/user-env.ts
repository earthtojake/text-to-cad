import { SHELL_ENV_CAPTURE_GUARD } from './types';

const RUNTIME_ONLY_KEYS = new Set([
  'INIT_CWD',
  'LOG_LEVEL',
  'NODE',
  'NODE_ENV',
  'NODE_ENV_ELECTRON_VITE',
  'NO_SANDBOX',
  'NX_STREAM_OUTPUT',
  'NX_WORKSPACE_ROOT',
  'PNPM_PACKAGE_NAME',
  'PNPM_SCRIPT_SRC_DIR',
  'REMOTE_DEBUGGING_PORT',
  'TELEMETRY_ENABLED',
  'V8_INSPECTOR_BRK_PORT',
  'V8_INSPECTOR_PORT',
  'VITE_DEBUG_FILTER',
  'VITE_LOG_LEVEL',
  'VITE_POSTHOG_HOST',
  'VITE_POSTHOG_KEY',
  ...Object.keys(SHELL_ENV_CAPTURE_GUARD),
]);

const RUNTIME_ONLY_PREFIXES = [
  'ELECTRON_',
  'EMDASH_',
  'MAIN_VITE_',
  'NX_TASK_',
  'NX_TERMINAL_',
  'PRELOAD_VITE_',
  'RENDERER_VITE_',
  'VITE_',
  'npm_',
] as const;

/**
 * Builds the inherited seed for resolving a user's login-shell environment.
 *
 * A host process environment is an implementation detail of the process that
 * happens to run Emdash. Electron, electron-vite, pnpm/Nx, and Emdash itself
 * all add control variables to it. Those variables are not part of a user's
 * terminal environment, so they must not be present in the seed inherited by
 * the login-shell probe. A shell startup file can still deliberately export
 * any of these names; that value appears in the capture and is preserved.
 */
export function buildUserShellEnvSeed(
  processEnv: NodeJS.ProcessEnv = process.env
): NodeJS.ProcessEnv {
  const seed: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(processEnv)) {
    if (value === undefined || isRuntimeOnlyKey(key)) continue;
    seed[key] = value;
  }
  return seed;
}

function isRuntimeOnlyKey(key: string): boolean {
  if (RUNTIME_ONLY_KEYS.has(key)) return true;
  return RUNTIME_ONLY_PREFIXES.some((prefix) => key.startsWith(prefix));
}

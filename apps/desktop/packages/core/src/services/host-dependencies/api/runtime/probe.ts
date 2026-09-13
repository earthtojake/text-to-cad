import type { IExecutionContext } from '#primitives/exec/api';
import type { HostElevation, Platform, ProbeResult } from '#primitives/host-dependencies/api';

const WHICH_TIMEOUT_MS = 5_000;
const VERSION_PROBE_TIMEOUT_MS = 10_000;
const REALPATH_TIMEOUT_MS = 5_000;
const ELEVATION_PROBE_TIMEOUT_MS = 5_000;

function targetPlatform(platform?: Platform): Platform {
  if (platform) return platform;
  if (process.platform === 'darwin') return 'macos';
  if (process.platform === 'win32') return 'windows';
  return 'linux';
}

/**
 * Resolves all absolute paths for a command binary in PATH order.
 * Uses `where` on Windows (which already lists all matches) and `which -a` on
 * macOS/Linux. Returns an empty array when the command is not found.
 *
 * The first entry is the PATH winner (same result as resolveCommandPath).
 */
export async function resolveAllCommandPaths(
  command: string,
  ctx: IExecutionContext,
  platform?: Platform
): Promise<string[]> {
  const plat = targetPlatform(platform);
  try {
    if (plat === 'windows') {
      const { stdout } = await ctx.exec('where', [command], { timeout: WHICH_TIMEOUT_MS });
      return stdout
        .trim()
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
    }
    const { stdout } = await ctx.exec('which', ['-a', command], { timeout: WHICH_TIMEOUT_MS });
    return stdout
      .trim()
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

/**
 * Resolves the absolute path of a command binary.
 * Uses `where` on Windows and `which` on macOS/Linux.
 * Returns `null` if the command is not found or the resolution fails.
 */
export async function resolveCommandPath(
  command: string,
  ctx: IExecutionContext,
  platform?: Platform
): Promise<string | null> {
  const resolveCmd = targetPlatform(platform) === 'windows' ? 'where' : 'which';
  try {
    const { stdout } = await ctx.exec(resolveCmd, [command], { timeout: WHICH_TIMEOUT_MS });
    const firstLine = stdout.trim().split('\n')[0]?.trim();
    return firstLine ?? null;
  } catch {
    return null;
  }
}

/**
 * Resolves the canonical realpath of a binary by following symlinks.
 * Runs `realpath` on Unix or falls back to the given path on failure/Windows.
 * Used to determine the true install location for method inference.
 */
export async function resolveRealpath(
  resolvedPath: string,
  ctx: IExecutionContext,
  platform?: Platform
): Promise<string> {
  if (targetPlatform(platform) === 'windows') return resolvedPath;
  try {
    const { stdout } = await ctx.exec('realpath', [resolvedPath], {
      timeout: REALPATH_TIMEOUT_MS,
    });
    const real = stdout.trim();
    return real || resolvedPath;
  } catch {
    return resolvedPath;
  }
}

/**
 * Runs `command args` and collects stdout/stderr up to a timeout.
 * Never throws — all failures are captured in the returned `ProbeResult`.
 */
export async function runVersionProbe(
  command: string,
  resolvedPath: string | null,
  args: string[],
  ctx: IExecutionContext,
  timeoutMs: number = VERSION_PROBE_TIMEOUT_MS
): Promise<ProbeResult> {
  const bin = resolvedPath ?? command;
  try {
    const { stdout, stderr } = await ctx.exec(bin, args, { timeout: timeoutMs });
    return { command, path: resolvedPath, stdout, stderr, exitCode: 0, timedOut: false };
  } catch (err: unknown) {
    const e = err as { stdout?: string; stderr?: string; code?: number; killed?: boolean };
    return {
      command,
      path: resolvedPath,
      stdout: e.stdout ?? '',
      stderr: e.stderr ?? '',
      exitCode: e.code ?? null,
      timedOut: !!e.killed,
    };
  }
}

/**
 * Probes how the current process can elevate non-interactively.
 *
 * - Windows: returns `null` (no non-interactive elevation model; unused today).
 * - POSIX: distinguishes root from passwordless sudo and unavailable elevation.
 */
export async function probeHostElevation(
  exec: IExecutionContext,
  platform: NodeJS.Platform = process.platform
): Promise<HostElevation | null> {
  if (platform === 'win32') return null;

  try {
    const { stdout } = await exec.exec('id', ['-u'], { timeout: ELEVATION_PROBE_TIMEOUT_MS });
    if (stdout.trim() === '0') return 'root';
  } catch {
    // Fall through to sudo probe.
  }

  const sudoPath = await resolveCommandPath('sudo', exec);
  if (!sudoPath) return 'unavailable';

  try {
    await exec.exec(sudoPath, ['-n', 'true'], { timeout: ELEVATION_PROBE_TIMEOUT_MS });
    return 'passwordless-sudo';
  } catch {
    return 'unavailable';
  }
}

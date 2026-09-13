/**
 * Per-process spawn counters. Every own-code child-process spawn (and the
 * preview-port probe attempts, which are rate-tracked the same way) is recorded
 * here with a purpose tag so the dev instruments and telemetry can report
 * spawns-per-minute broken down by purpose.
 *
 * Recording is a map increment — cheap enough to stay always-on. Reporting is
 * separate (see dev-instruments.ts) and only runs when debug logging is enabled.
 */

/**
 * Single source of truth for the purpose key set — the `SpawnPurpose` union,
 * the vitals iteration order, and the `spawns_*` telemetry field names are all
 * derived from this array.
 */
export const SPAWN_PURPOSES = [
  'git',
  'fetch',
  'tmux',
  'probe',
  'pty',
  'agent',
  'worker',
  'shell',
  'ssh',
  'other',
] as const;

export type SpawnPurpose = (typeof SPAWN_PURPOSES)[number];

export type SpawnObserver = (purpose: SpawnPurpose, command: string | undefined) => void;

const counts = new Map<SpawnPurpose, number>();
let observer: SpawnObserver | null = null;

export function recordSpawn(purpose: SpawnPurpose, command?: string): void {
  counts.set(purpose, (counts.get(purpose) ?? 0) + 1);
  observer?.(purpose, command);
}

/**
 * Derive the purpose tag from the executable and its arguments. Callers with
 * better context (e.g. agent process hosts) should tag explicitly instead.
 */
export function classifySpawnPurpose(file: string, args: readonly string[] = []): SpawnPurpose {
  const executable = executableName(file);
  if (executable === 'git') return firstGitSubcommand(args) === 'fetch' ? 'fetch' : 'git';
  if (executable === 'tmux') return 'tmux';
  if (executable === 'ssh') return 'ssh';
  return 'other';
}

export function snapshotSpawnCounts(
  options: { reset?: boolean } = {}
): Partial<Record<SpawnPurpose, number>> {
  const snapshot: Partial<Record<SpawnPurpose, number>> = {};
  for (const [purpose, count] of counts) {
    if (count > 0) snapshot[purpose] = count;
  }
  if (options.reset) counts.clear();
  return snapshot;
}

export function resetSpawnCounts(): void {
  counts.clear();
}

/**
 * Install a per-spawn observer (verbose spawn logging for burst forensics).
 * Pass null to remove. Only one observer is supported.
 */
export function setSpawnObserver(next: SpawnObserver | null): void {
  observer = next;
}

function executableName(file: string): string {
  const normalized = file.replace(/\\/g, '/');
  const base = normalized.slice(normalized.lastIndexOf('/') + 1).toLowerCase();
  return base.endsWith('.exe') ? base.slice(0, -'.exe'.length) : base;
}

/** Global git options that take a separate value argument. */
const GIT_VALUE_OPTIONS = new Set(['-C', '-c', '--git-dir', '--work-tree', '--exec-path']);

function firstGitSubcommand(args: readonly string[]): string | undefined {
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i]!;
    if (GIT_VALUE_OPTIONS.has(arg)) {
      i += 1;
      continue;
    }
    if (arg.startsWith('-')) continue;
    return arg;
  }
  return undefined;
}

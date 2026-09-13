import { execFile } from 'node:child_process';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { recordSpawn } from '@emdash/shared/perf';

export interface PidPpidPair {
  pid: number;
  ppid: number;
}

export interface ProcessInfo extends PidPpidPair {
  pgid?: number;
  sessionId?: number;
  startTime?: string;
}

export interface ProcessTreeSnapshot {
  root?: ProcessInfo;
  descendants: ProcessInfo[];
}

const PS_TREE_COLUMNS = 'pid=,ppid=,pgid=,sess=,lstart=';

/**
 * Parse process-table output into process identity records. The first two
 * columns (`pid`, `ppid`) are required; `pgid`, `sess`, and the start-time tail
 * are optional so tests and platform-specific `ps` variants can reuse this.
 */
export function parseProcessTable(output: string): ProcessInfo[] {
  const processes: ProcessInfo[] = [];
  for (const line of output.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split(/\s+/);
    if (parts.length < 2) continue;
    const pid = Number(parts[0]);
    const ppid = Number(parts[1]);
    if (!Number.isInteger(pid) || !Number.isInteger(ppid)) continue;

    const pgid = Number(parts[2]);
    const sessionId = Number(parts[3]);
    const startTime = parts.slice(4).join(' ').trim();
    processes.push({
      pid,
      ppid,
      ...(Number.isInteger(pgid) ? { pgid } : {}),
      ...(Number.isInteger(sessionId) ? { sessionId } : {}),
      ...(startTime ? { startTime } : {}),
    });
  }
  return processes;
}

/**
 * Parse the output of `ps -o pid=,ppid=` into (pid, ppid) pairs.
 * Lines that do not start with two integers are skipped, so the parser is
 * tolerant of a stray header row or platform formatting quirks.
 */
export function parsePidPpidPairs(output: string): PidPpidPair[] {
  return parseProcessTable(output).map(({ pid, ppid }) => ({ pid, ppid }));
}

/**
 * Given a process-table snapshot and a set of root pids, return every
 * transitive descendant process (excluding the roots themselves). Cycle-safe.
 */
export function collectDescendantProcesses<T extends PidPpidPair>(
  processes: T[],
  roots: number[]
): T[] {
  const childrenByParent = new Map<number, T[]>();
  for (const processInfo of processes) {
    const existing = childrenByParent.get(processInfo.ppid);
    if (existing) existing.push(processInfo);
    else childrenByParent.set(processInfo.ppid, [processInfo]);
  }

  const seen = new Set<number>(roots);
  const descendants: T[] = [];
  const queue = [...roots];
  while (queue.length > 0) {
    const parent = queue.shift()!;
    const children = childrenByParent.get(parent);
    if (!children) continue;
    for (const child of children) {
      if (seen.has(child.pid)) continue;
      seen.add(child.pid);
      descendants.push(child);
      queue.push(child.pid);
    }
  }
  return descendants;
}

/**
 * Given a process-table snapshot and a set of root pids, return every
 * transitive descendant pid (excluding the roots themselves). Cycle-safe.
 */
export function collectDescendantPids(pairs: PidPpidPair[], roots: number[]): number[] {
  return collectDescendantProcesses(pairs, roots).map(({ pid }) => pid);
}

function snapshotLocalProcesses(
  args: string[],
  logger: Logger = noopLogger
): Promise<ProcessInfo[]> {
  return new Promise((resolve) => {
    recordSpawn('other', 'ps');
    execFile(
      'ps',
      args,
      { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 2000 },
      (error, stdout) => {
        if (error && !stdout) {
          logger.debug('process-tree: ps snapshot failed', {
            args,
            error: String(error),
          });
          resolve([]);
          return;
        }
        if (error) {
          logger.debug('process-tree: ps snapshot partially failed', {
            args,
            error: String(error),
          });
        }
        resolve(parseProcessTable(stdout));
      }
    );
  });
}

/**
 * Snapshot the local process table and resolve the root plus transitive
 * descendants of `rootPid`. Best-effort: resolves an empty descendant list if
 * `ps` is unavailable or fails.
 *
 * Asynchronous on purpose -- this runs on the Electron main process or a utility
 * process, so spawning `ps` must not block the event loop. POSIX only; callers
 * guard the platform. `ps -A -o pid=,ppid=,pgid=,sess=,lstart=` is supported by
 * both Linux (procps) and macOS (BSD) `ps`.
 */
export async function collectLocalProcessTreeAsync(
  rootPid: number,
  logger: Logger = noopLogger
): Promise<ProcessTreeSnapshot> {
  const processes = await snapshotLocalProcesses(['-A', '-o', PS_TREE_COLUMNS], logger);
  return {
    root: processes.find(({ pid }) => pid === rootPid),
    descendants: collectDescendantProcesses(processes, [rootPid]),
  };
}

/**
 * Snapshot specific pids for delayed signal identity checks. Missing pids are
 * omitted from the returned map.
 */
export async function collectLocalProcessInfosByPidAsync(
  pids: number[],
  logger: Logger = noopLogger
): Promise<Map<number, ProcessInfo>> {
  const uniquePids = [...new Set(pids.filter((pid) => Number.isInteger(pid) && pid > 0))];
  if (uniquePids.length === 0) return new Map();

  const processes = await snapshotLocalProcesses(
    ['-p', uniquePids.join(','), '-o', PS_TREE_COLUMNS],
    logger
  );
  return new Map(processes.map((processInfo) => [processInfo.pid, processInfo]));
}

import { noopLogger, type Logger } from '@emdash/shared/logger';
import {
  collectLocalProcessInfosByPidAsync,
  collectLocalProcessTreeAsync,
  type ProcessInfo,
  type ProcessTreeSnapshot,
} from './process-tree';

const KILL_GRACE_MS = 2000;

function signalPids(pids: number[], signal: NodeJS.Signals): void {
  for (const pid of pids) {
    try {
      process.kill(pid, signal);
    } catch {}
  }
}

function pidsOf(processes: ProcessInfo[]): number[] {
  return processes.map(({ pid }) => pid);
}

function isKnownPositiveInteger(value: number | undefined): value is number {
  return value !== undefined && Number.isInteger(value) && value > 0;
}

function isEscapedDescendant(root: ProcessInfo | undefined, descendant: ProcessInfo): boolean {
  if (!root) return true;

  if (isKnownPositiveInteger(root.sessionId) && isKnownPositiveInteger(descendant.sessionId)) {
    return descendant.sessionId !== root.sessionId;
  }

  if (isKnownPositiveInteger(root.pgid) && isKnownPositiveInteger(descendant.pgid)) {
    return descendant.pgid !== root.pgid;
  }

  return true;
}

function isSameProcessIdentity(expected: ProcessInfo, current: ProcessInfo | undefined): boolean {
  if (!current || current.pid !== expected.pid) return false;
  if (expected.startTime && current.startTime) return current.startTime === expected.startTime;
  return true;
}

export class PosixPtyTerminator {
  private rootKillTimer: ReturnType<typeof setTimeout> | null = null;
  private descendantKillTimer: ReturnType<typeof setTimeout> | null = null;
  private exited = false;

  constructor(private readonly logger: Logger = noopLogger) {}

  kill(rootPid: number, killPty: () => void): void {
    void collectLocalProcessTreeAsync(rootPid, this.logger).then(
      (snapshot) => this.terminate(rootPid, snapshot, killPty),
      () => this.terminate(rootPid, { descendants: [] }, killPty)
    );
  }

  markExited(): void {
    this.exited = true;
    if (this.rootKillTimer) {
      clearTimeout(this.rootKillTimer);
      this.rootKillTimer = null;
    }
  }

  private terminate(rootPid: number, snapshot: ProcessTreeSnapshot, killPty: () => void): void {
    if (!this.exited) {
      try {
        process.kill(-rootPid, 'SIGTERM');
      } catch {}
      if (!this.exited) {
        this.rootKillTimer = setTimeout(() => {
          try {
            process.kill(-rootPid, 'SIGKILL');
          } catch {}
          this.rootKillTimer = null;
        }, KILL_GRACE_MS);
      }
    }

    const descendants = snapshot.descendants;
    if (descendants.length > 0) {
      signalPids(pidsOf(descendants), 'SIGTERM');
    }

    const escapedDescendants = descendants.filter((descendant) =>
      isEscapedDescendant(snapshot.root, descendant)
    );
    if (escapedDescendants.length > 0) {
      this.descendantKillTimer = setTimeout(() => {
        void this.signalMatchingProcessIdentities(escapedDescendants, 'SIGKILL').finally(() => {
          this.descendantKillTimer = null;
        });
      }, KILL_GRACE_MS);
    }

    if (!this.exited) {
      killPty();
    }
  }

  private async signalMatchingProcessIdentities(
    processes: ProcessInfo[],
    signal: NodeJS.Signals
  ): Promise<void> {
    const currentByPid = await collectLocalProcessInfosByPidAsync(pidsOf(processes), this.logger);
    const matchingPids = processes
      .filter((processInfo) =>
        isSameProcessIdentity(processInfo, currentByPid.get(processInfo.pid))
      )
      .map(({ pid }) => pid);
    signalPids(matchingPids, signal);
  }
}

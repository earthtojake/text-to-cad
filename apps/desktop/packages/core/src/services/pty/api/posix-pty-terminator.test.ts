import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PosixPtyTerminator } from './posix-pty-terminator';
import {
  collectLocalProcessInfosByPidAsync,
  collectLocalProcessTreeAsync,
  type ProcessInfo,
  type ProcessTreeSnapshot,
} from './process-tree';

vi.mock('./process-tree', () => ({
  collectLocalProcessInfosByPidAsync: vi.fn(() => Promise.resolve(new Map())),
  collectLocalProcessTreeAsync: vi.fn(() => Promise.resolve({ descendants: [] })),
}));

/** Let the async descendant snapshot (a resolved promise + its .then) settle. */
async function flushSnapshot(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

describe('PosixPtyTerminator', () => {
  const rootProcess: ProcessInfo = {
    pid: 1234,
    ppid: 1,
    pgid: 1234,
    sessionId: 1234,
    startTime: 'root-start',
  };
  let terminator: PosixPtyTerminator;
  let killPty: () => void;

  function processInfo(pid: number, overrides: Partial<ProcessInfo> = {}): ProcessInfo {
    return {
      pid,
      ppid: 1234,
      pgid: pid,
      sessionId: pid,
      startTime: `start-${pid}`,
      ...overrides,
    };
  }

  function treeSnapshot(descendants: ProcessInfo[] = []): ProcessTreeSnapshot {
    return {
      root: rootProcess,
      descendants,
    };
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(treeSnapshot());
    vi.mocked(collectLocalProcessInfosByPidAsync).mockImplementation(async (pids) => {
      return new Map(pids.map((pid) => [pid, processInfo(pid)]));
    });
    vi.useFakeTimers();

    terminator = new PosixPtyTerminator();
    killPty = vi.fn();
    vi.spyOn(process, 'kill').mockImplementation(() => true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('sends SIGTERM to the root process group', async () => {
    terminator.kill(1234, killPty);
    await flushSnapshot();

    expect(process.kill).toHaveBeenCalledWith(-1234, 'SIGTERM');
    expect(killPty).toHaveBeenCalled();
  });

  it('escalates the root process group to SIGKILL after 2 seconds if not exited', async () => {
    terminator.kill(1234, killPty);
    await flushSnapshot();
    expect(process.kill).not.toHaveBeenCalledWith(-1234, 'SIGKILL');

    vi.advanceTimersByTime(2000);
    expect(process.kill).toHaveBeenCalledWith(-1234, 'SIGKILL');
  });

  it('does not send the root group SIGKILL if the shell exits before the timeout', async () => {
    terminator.kill(1234, killPty);
    await flushSnapshot();
    terminator.markExited();

    vi.advanceTimersByTime(2000);
    expect(process.kill).not.toHaveBeenCalledWith(-1234, 'SIGKILL');
  });

  it('SIGTERMs descendants individually', async () => {
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(
      treeSnapshot([processInfo(5678), processInfo(9012)])
    );

    terminator.kill(1234, killPty);
    await flushSnapshot();

    expect(collectLocalProcessTreeAsync).toHaveBeenCalledWith(1234, expect.anything());
    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGTERM');
    expect(process.kill).toHaveBeenCalledWith(9012, 'SIGTERM');
  });

  it('escalates escaped descendants to SIGKILL after 2 seconds', async () => {
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(treeSnapshot([processInfo(5678)]));

    terminator.kill(1234, killPty);
    await flushSnapshot();
    expect(process.kill).not.toHaveBeenCalledWith(5678, 'SIGKILL');

    vi.advanceTimersByTime(2000);
    await flushSnapshot();
    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGKILL');
  });

  it('still SIGKILLs escaped descendants even when the shell exits first', async () => {
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(treeSnapshot([processInfo(5678)]));

    terminator.kill(1234, killPty);
    await flushSnapshot();
    // The shell exits right after SIGTERM, while watchman/ts-checker daemons keep running.
    terminator.markExited();

    vi.advanceTimersByTime(2000);
    await flushSnapshot();
    // The dead group's SIGKILL is cancelled...
    expect(process.kill).not.toHaveBeenCalledWith(-1234, 'SIGKILL');
    // ...but the detached descendant is still force-killed - this is the bug the
    // independent descendant timer fixes.
    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGKILL');
  });

  it('snapshots descendants once and reuses the snapshot for both passes', async () => {
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(treeSnapshot([processInfo(5678)]));

    terminator.kill(1234, killPty);
    await flushSnapshot();
    vi.advanceTimersByTime(2000);

    expect(collectLocalProcessTreeAsync).toHaveBeenCalledTimes(1);
  });

  it('does not schedule group signals if the shell exits before the snapshot resolves', async () => {
    let resolveSnapshot: (snapshot: ProcessTreeSnapshot) => void = () => {};
    vi.mocked(collectLocalProcessTreeAsync).mockReturnValue(
      new Promise((resolve) => {
        resolveSnapshot = resolve;
      })
    );

    terminator.kill(1234, killPty);
    terminator.markExited();
    resolveSnapshot(treeSnapshot([processInfo(5678)]));
    await flushSnapshot();

    expect(process.kill).not.toHaveBeenCalledWith(-1234, 'SIGTERM');
    expect(killPty).not.toHaveBeenCalled();
    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGTERM');

    vi.advanceTimersByTime(2000);
    await flushSnapshot();
    expect(process.kill).not.toHaveBeenCalledWith(-1234, 'SIGKILL');
    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGKILL');
  });

  it('does not independently SIGKILL same-session descendants', async () => {
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(
      treeSnapshot([processInfo(5678, { pgid: 5678, sessionId: 1234 })])
    );

    terminator.kill(1234, killPty);
    await flushSnapshot();
    vi.advanceTimersByTime(2000);
    await flushSnapshot();

    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGTERM');
    expect(process.kill).not.toHaveBeenCalledWith(5678, 'SIGKILL');
  });

  it('skips descendant SIGKILL if the pid identity changed before escalation', async () => {
    vi.mocked(collectLocalProcessTreeAsync).mockResolvedValue(treeSnapshot([processInfo(5678)]));
    vi.mocked(collectLocalProcessInfosByPidAsync).mockResolvedValue(
      new Map([[5678, processInfo(5678, { startTime: 'different-start' })]])
    );

    terminator.kill(1234, killPty);
    await flushSnapshot();
    vi.advanceTimersByTime(2000);
    await flushSnapshot();

    expect(process.kill).toHaveBeenCalledWith(5678, 'SIGTERM');
    expect(process.kill).not.toHaveBeenCalledWith(5678, 'SIGKILL');
  });
});

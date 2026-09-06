import { err, ok, type Result } from '@emdash/shared';
import { daemonPaths, type DaemonPaths } from './paths';
import { isProcessAlive, readPidFile, removePidFile, type ProcessSignaler } from './pid-file';
import { probeDaemon, type DaemonHealth, type DaemonProbeError } from './probe';

export type StopDaemonResult = {
  status: 'not-running' | 'stopped';
  paths: DaemonPaths;
  pid?: number;
};

export type StopDaemonError = {
  type: 'signal' | 'timeout';
  message: string;
};

export type StopDaemonOptions = {
  socketPath?: string;
  timeoutMs?: number;
  retryMs?: number;
  signaler?: ProcessSignaler;
  probe?: (
    socketPath: string,
    options?: { timeoutMs?: number }
  ) => Promise<Result<DaemonHealth, DaemonProbeError>>;
  sleep?: (ms: number) => Promise<void>;
};

export async function stopDaemon(
  options: StopDaemonOptions = {}
): Promise<Result<StopDaemonResult, StopDaemonError>> {
  const paths = daemonPaths(options.socketPath);
  const signaler = options.signaler ?? process.kill;
  const pid = await readPidFile(paths.pidPath);

  if (!pid.success) {
    await removePidFile(paths.pidPath);
    return ok({ status: 'not-running' as const, paths });
  }

  if (!isProcessAlive(pid.data, signaler)) {
    await removePidFile(paths.pidPath);
    return ok({ status: 'not-running' as const, paths, pid: pid.data });
  }

  try {
    signaler(pid.data, 'SIGTERM');
  } catch (error) {
    return err({
      type: 'signal',
      message: error instanceof Error ? error.message : String(error),
    });
  }

  const stopped = await waitForStopped(paths.socketPath, pid.data, signaler, options);
  if (!stopped.success) return stopped;

  await removePidFile(paths.pidPath);
  return ok({ status: 'stopped' as const, paths, pid: pid.data });
}

async function waitForStopped(
  socketPath: string,
  pid: number,
  signaler: ProcessSignaler,
  options: StopDaemonOptions
): Promise<Result<void, StopDaemonError>> {
  const timeoutMs = options.timeoutMs ?? 5_000;
  const retryMs = options.retryMs ?? 50;
  const sleep = options.sleep ?? defaultSleep;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() <= deadline) {
    const health = await (options.probe ?? probeDaemon)(socketPath, {
      timeoutMs: Math.min(1_000, timeoutMs),
    });
    if (!isProcessAlive(pid, signaler) && !health.success) {
      return ok();
    }
    await sleep(retryMs);
  }

  return err({ type: 'timeout', message: `Timed out stopping workspace daemon pid ${pid}` });
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

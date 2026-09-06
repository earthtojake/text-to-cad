import { spawn as nodeSpawn, type ChildProcess, type SpawnOptions } from 'node:child_process';
import { unlink } from 'node:fs/promises';
import { open } from 'node:fs/promises';
import { err, ok, type Result } from '@emdash/shared';
import { withFileLock } from './lock';
import { daemonPaths, type DaemonPaths } from './paths';
import { isProcessAlive, readPidFile, removePidFile, type ProcessSignaler } from './pid-file';
import { probeDaemon, type DaemonHealth, type DaemonProbeError } from './probe';

export type StartDaemonResult = {
  status: 'already-running' | 'started';
  paths: DaemonPaths;
  health: DaemonHealth;
  pid?: number;
};

export type StartDaemonError = {
  type: 'lock' | 'spawn' | 'timeout' | 'unhealthy';
  message: string;
};

export type SpawnDaemon = (
  command: string,
  args: string[],
  options: SpawnOptions
) => Pick<ChildProcess, 'pid' | 'unref'>;

export type StartDaemonOptions = {
  socketPath?: string;
  entrypoint?: string;
  execPath?: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
  retryMs?: number;
  lockTimeoutMs?: number;
  spawn?: SpawnDaemon;
  probe?: (
    socketPath: string,
    options?: { timeoutMs?: number }
  ) => Promise<Result<DaemonHealth, DaemonProbeError>>;
  signaler?: ProcessSignaler;
  sleep?: (ms: number) => Promise<void>;
};

export async function startDaemon(
  options: StartDaemonOptions = {}
): Promise<Result<StartDaemonResult, StartDaemonError>> {
  const paths = daemonPaths(options.socketPath);
  const timeoutMs = options.timeoutMs ?? 5_000;
  const retryMs = options.retryMs ?? 50;

  try {
    return await withFileLock(
      paths.lockPath,
      async () => {
        const existing = await probe(paths.socketPath, options);
        if (existing.success) {
          return ok({ status: 'already-running' as const, paths, health: existing.data });
        }
        if (existing.error.type === 'unhealthy') {
          return err({
            type: 'unhealthy',
            message: existing.error.message,
          });
        }

        await cleanupDeadDaemonFiles(paths, options.signaler);
        let child: Pick<ChildProcess, 'pid' | 'unref'>;
        try {
          child = await spawnServeProcess(paths, options);
        } catch (error) {
          return err({
            type: 'spawn' as const,
            message: error instanceof Error ? error.message : String(error),
          });
        }
        const started = await waitForHealthy(paths.socketPath, timeoutMs, retryMs, options);
        if (!started.success) return started;
        return ok({
          status: 'started' as const,
          paths,
          health: started.data,
          pid: child.pid,
        });
      },
      { timeoutMs: options.lockTimeoutMs ?? timeoutMs, retryMs }
    );
  } catch (error) {
    return err({
      type: 'lock',
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

async function spawnServeProcess(
  paths: DaemonPaths,
  options: StartDaemonOptions
): Promise<Pick<ChildProcess, 'pid' | 'unref'>> {
  const entrypoint = options.entrypoint ?? process.argv[1];
  if (!entrypoint) {
    throw new Error('Cannot start workspace daemon without an entrypoint path');
  }

  const log = await open(paths.logPath, 'a');
  try {
    const child = (options.spawn ?? nodeSpawn)(
      options.execPath ?? process.execPath,
      [entrypoint, 'serve', '--socket', paths.socketPath],
      {
        detached: true,
        env: options.env ?? process.env,
        stdio: ['ignore', log.fd, log.fd],
      }
    );
    child.unref();
    return child;
  } finally {
    await log.close();
  }
}

async function waitForHealthy(
  socketPath: string,
  timeoutMs: number,
  retryMs: number,
  options: StartDaemonOptions
): Promise<Result<DaemonHealth, StartDaemonError>> {
  const sleep = options.sleep ?? defaultSleep;
  const deadline = Date.now() + timeoutMs;
  let lastMessage = 'Workspace daemon did not become healthy';

  while (Date.now() <= deadline) {
    const result = await probe(socketPath, options);
    if (result.success) return ok(result.data);
    lastMessage = result.error.message;
    await sleep(retryMs);
  }

  return err({ type: 'timeout', message: lastMessage });
}

async function probe(socketPath: string, options: StartDaemonOptions) {
  return (options.probe ?? probeDaemon)(socketPath, { timeoutMs: options.timeoutMs ?? 1_000 });
}

async function cleanupDeadDaemonFiles(
  paths: DaemonPaths,
  signaler: ProcessSignaler = process.kill
): Promise<void> {
  const pid = await readPidFile(paths.pidPath);
  if (!pid.success || !isProcessAlive(pid.data, signaler)) {
    await removePidFile(paths.pidPath);
  }
  await unlink(paths.socketPath).catch(() => {});
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

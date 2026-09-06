import { err, ok, type Result } from '@emdash/shared';
import { daemonPaths, type DaemonPaths } from './paths';
import { probeDaemon, type DaemonHealth } from './probe';

export type DaemonStatus = {
  status: 'running';
  paths: DaemonPaths;
  health: DaemonHealth;
};

export type DaemonStatusError = {
  type: 'not-running' | 'unhealthy';
  paths: DaemonPaths;
  message: string;
};

export async function statusDaemon(
  socketPath?: string
): Promise<Result<DaemonStatus, DaemonStatusError>> {
  const paths = daemonPaths(socketPath);
  const health = await probeDaemon(paths.socketPath);
  if (!health.success) {
    return err({
      type: health.error.type,
      paths,
      message: health.error.message,
    });
  }
  return ok({
    status: 'running' as const,
    paths,
    health: health.data,
  });
}

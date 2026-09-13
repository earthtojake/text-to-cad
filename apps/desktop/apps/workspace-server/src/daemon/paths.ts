import { homedir } from 'node:os';
import { join } from 'node:path';

export const DEFAULT_WORKSPACE_SERVER_SOCKET_PATH = join(
  homedir(),
  '.emdash',
  'workspace-server',
  'run',
  'workspace.sock'
);

export type DaemonPaths = {
  socketPath: string;
  pidPath: string;
  lockPath: string;
  logPath: string;
};

export function daemonPaths(socketPath = DEFAULT_WORKSPACE_SERVER_SOCKET_PATH): DaemonPaths {
  return {
    socketPath,
    pidPath: `${socketPath}.pid`,
    lockPath: `${socketPath}.lock`,
    logPath: `${socketPath}.log`,
  };
}

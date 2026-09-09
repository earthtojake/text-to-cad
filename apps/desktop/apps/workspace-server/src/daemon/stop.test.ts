import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { daemonPaths } from './paths';
import { writePidFile } from './pid-file';
import { stopDaemon } from './stop';

const health = {
  status: 'ok' as const,
  version: '1.2.3',
  uptimeMs: 10,
  protocolVersion: '1.0.0',
};

describe('stopDaemon', () => {
  it('sends SIGTERM and waits for the daemon to stop', async () => {
    const socketPath = await tempSocketPath();
    const paths = daemonPaths(socketPath);
    await writePidFile(paths.pidPath, 1234);
    let killed = false;

    const result = await stopDaemon({
      socketPath,
      sleep: async () => {},
      signaler: (_pid, signal) => {
        if (signal === 'SIGTERM') killed = true;
        if (signal === 0 && killed) throw new Error('dead');
        return true;
      },
      probe: async () =>
        killed
          ? { success: false, error: { type: 'not-running' as const, message: 'stopped' } }
          : { success: true, data: health },
    });

    expect(result).toMatchObject({
      success: true,
      data: {
        status: 'stopped',
        pid: 1234,
      },
    });
    await expect(readFile(paths.pidPath, 'utf8')).rejects.toThrow();
  });

  it('cleans up a stale pid file', async () => {
    const socketPath = await tempSocketPath();
    const paths = daemonPaths(socketPath);
    await writePidFile(paths.pidPath, 1234);

    const result = await stopDaemon({
      socketPath,
      signaler: (_pid, signal) => {
        if (signal === 0) throw new Error('dead');
        return true;
      },
    });

    expect(result).toMatchObject({
      success: true,
      data: {
        status: 'not-running',
        pid: 1234,
      },
    });
    await expect(readFile(paths.pidPath, 'utf8')).rejects.toThrow();
  });
});

async function tempSocketPath(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'emdash-workspace-daemon-stop-'));
  return join(dir, 'workspace.sock');
}

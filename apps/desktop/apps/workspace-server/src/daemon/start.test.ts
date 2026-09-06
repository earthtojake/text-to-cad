import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { daemonPaths } from './paths';
import { startDaemon, type SpawnDaemon } from './start';

const health = {
  status: 'ok' as const,
  version: '1.2.3',
  uptimeMs: 10,
  protocolVersion: '1.0.0',
};

describe('startDaemon', () => {
  it('does not spawn when the daemon is already healthy', async () => {
    const socketPath = await tempSocketPath();
    const spawn = vi.fn<SpawnDaemon>();

    const result = await startDaemon({
      socketPath,
      spawn,
      probe: async () => ({ success: true, data: health }),
    });

    expect(result).toMatchObject({
      success: true,
      data: {
        status: 'already-running',
      },
    });
    expect(spawn).not.toHaveBeenCalled();
  });

  it('spawns serve and waits for health when the daemon is absent', async () => {
    const socketPath = await tempSocketPath();
    const unref = vi.fn();
    const spawn = vi.fn<SpawnDaemon>(() => ({ pid: 1234, unref }));
    let probeCount = 0;

    const result = await startDaemon({
      socketPath,
      entrypoint: '/tmp/entry.mjs',
      execPath: '/usr/bin/node',
      spawn,
      sleep: async () => {},
      probe: async () => {
        probeCount += 1;
        return probeCount === 1
          ? { success: false, error: { type: 'not-running' as const, message: 'missing' } }
          : { success: true, data: health };
      },
    });

    expect(result).toMatchObject({
      success: true,
      data: {
        status: 'started',
        pid: 1234,
      },
    });
    expect(spawn).toHaveBeenCalledWith(
      '/usr/bin/node',
      ['/tmp/entry.mjs', 'serve', '--socket', socketPath],
      expect.objectContaining({ detached: true })
    );
    expect(unref).toHaveBeenCalledTimes(1);
  });

  it('fails instead of spawning when another start holds the lock', async () => {
    const socketPath = await tempSocketPath();
    await writeFile(daemonPaths(socketPath).lockPath, 'locked\n');

    const result = await startDaemon({
      socketPath,
      timeoutMs: 1,
      retryMs: 1,
      spawn: vi.fn<SpawnDaemon>(),
      probe: async () => ({
        success: false,
        error: { type: 'not-running' as const, message: 'missing' },
      }),
    });

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'lock',
      },
    });
  });
});

async function tempSocketPath(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'emdash-workspace-daemon-start-'));
  return join(dir, 'workspace.sock');
}

import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createTestWorkspaceWireController } from '../testing/controller';
import { serveSocket, type SocketServeHandle } from '../wire/serve-socket';
import { probeDaemon } from './probe';

const handles: SocketServeHandle[] = [];

afterEach(async () => {
  for (const handle of handles.splice(0)) await handle.dispose();
});

describe('probeDaemon', () => {
  it('returns daemon health for a running workspace socket', async () => {
    const socketPath = await tempSocketPath();
    const handle = await serveSocket(
      createTestWorkspaceWireController({}, { appVersion: '1.2.3' }),
      { socketPath }
    );
    handles.push(handle);

    const result = await probeDaemon(socketPath);

    expect(result).toMatchObject({
      success: true,
      data: {
        status: 'ok',
        version: '1.2.3',
      },
    });
  });

  it('reports not-running for an absent socket', async () => {
    const result = await probeDaemon(await tempSocketPath(), { timeoutMs: 50 });

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'not-running',
      },
    });
  });
});

async function tempSocketPath(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'emdash-workspace-daemon-probe-'));
  return join(dir, 'workspace.sock');
}

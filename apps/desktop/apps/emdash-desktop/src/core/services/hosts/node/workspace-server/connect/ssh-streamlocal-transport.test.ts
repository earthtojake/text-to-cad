import { PassThrough } from 'node:stream';
import type { ClientChannel } from 'ssh2';
import { describe, expect, it, vi } from 'vitest';
import type { SshClientProxy } from '@core/primitives/ssh/api/node/ssh-client-proxy';
import { openSshWorkspaceServerTransport } from './ssh-streamlocal-transport';

describe('openSshWorkspaceServerTransport', () => {
  it('uses the current managed proxy and owns the returned channel', async () => {
    const channel = new PassThrough() as unknown as ClientChannel;
    const destroy = vi.spyOn(channel, 'destroy');
    const forwardOutStreamLocal = vi
      .fn<SshClientProxy['forwardOutStreamLocal']>()
      .mockResolvedValue(channel);
    const proxy = { forwardOutStreamLocal } as Pick<
      SshClientProxy,
      'forwardOutStreamLocal'
    > as SshClientProxy;
    const ensureProxy = vi.fn(async () => proxy);

    const transport = await openSshWorkspaceServerTransport(
      {
        kind: 'ssh',
        sshConnectionId: 'ssh-1',
        socketPath: '/home/devuser/.emdash/workspace-server/run/workspace.sock',
      },
      { ensureProxy }
    );
    transport.close?.();
    transport.close?.();

    expect(ensureProxy).toHaveBeenCalledWith('ssh-1');
    expect(forwardOutStreamLocal).toHaveBeenCalledWith(
      '/home/devuser/.emdash/workspace-server/run/workspace.sock'
    );
    expect(destroy).toHaveBeenCalledOnce();
  });
});

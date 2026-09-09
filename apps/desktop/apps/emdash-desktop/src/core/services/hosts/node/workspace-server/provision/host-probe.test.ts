import { describe, expect, it, vi } from 'vitest';
import type { SshClientProxy } from '@core/primitives/ssh/api/node/ssh-client-proxy';
import { RemoteHostProbe } from './host-probe';

describe('RemoteHostProbe', () => {
  it('reads and caches the remote home directory until explicitly dropped', async () => {
    const execScript = vi
      .fn<SshClientProxy['execScript']>()
      .mockResolvedValue({ stdout: '/home/devuser\n', stderr: '', exitCode: 0 });
    const proxy = { execScript } as Pick<SshClientProxy, 'execScript'> as SshClientProxy;
    const ensureProxy = vi.fn(async () => proxy);
    const probe = new RemoteHostProbe({ ensureProxy });

    await expect(probe.probe('ssh-1')).resolves.toEqual({ home: '/home/devuser' });
    await probe.probe('ssh-1');
    expect(execScript).toHaveBeenCalledOnce();

    probe.drop('ssh-1');
    await probe.probe('ssh-1');
    expect(execScript).toHaveBeenCalledTimes(2);
  });
});

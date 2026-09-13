import { PROTOCOL_VERSION, type WireInitializeResult } from '@emdash/core/workspace-server';
import { createScope } from '@emdash/shared/concurrency';
import { snapshot } from '@emdash/wire/state';
import { describe, expect, it, vi } from 'vitest';
import { HostStateModel } from '../../state-model';
import { WorkspaceServerProtocolError } from '../connect/protocol';
import { WorkspaceServerInstallError } from './installer';
import { WorkspaceServerProvisioner } from './provisioner';

describe('WorkspaceServerProvisioner', () => {
  it('coalesces compatible fast-path ensures without installing or starting', async () => {
    const fixture = createProvisionerFixture();
    const first = fixture.provisioner.ensure('ssh-1');
    const second = fixture.provisioner.ensure('ssh-1');

    await expect(first).resolves.toMatchObject({
      kind: 'ssh',
      sshConnectionId: 'ssh-1',
      socketPath: '/home/devuser/.emdash/workspace-server/run/workspace.sock',
    });
    await expect(second).resolves.toEqual(await first);
    expect(first).toBe(second);
    expect(fixture.installer.install).not.toHaveBeenCalled();
    expect(fixture.daemon.start).not.toHaveBeenCalled();
    expect(fixture.status('ssh-1')).toEqual({
      status: 'healthy',
      version: '1.2.3',
      startedAt: 1,
    });
    await fixture.dispose();
  });

  it('returns the cached target without re-dialing once provisioned', async () => {
    const fixture = createProvisionerFixture();
    const first = await fixture.provisioner.ensure('ssh-1');
    const second = await fixture.provisioner.ensure('ssh-1');

    expect(second).toBe(first);
    expect(fixture.dialOnce).toHaveBeenCalledTimes(1);
    await fixture.dispose();
  });

  it('re-verifies after drop() without republishing an identical healthy state', async () => {
    const fixture = createProvisionerFixture();
    await fixture.provisioner.ensure('ssh-1');

    const before = snapshot(fixture.model.runtime).revision;
    fixture.provisioner.drop('ssh-1');
    await fixture.provisioner.ensure('ssh-1');

    expect(fixture.dialOnce).toHaveBeenCalledTimes(2);
    expect(snapshot(fixture.model.runtime).revision).toBe(before);
    expect(fixture.status('ssh-1')).toMatchObject({ status: 'healthy' });
    await fixture.dispose();
  });

  it('installs and starts an absent daemon before returning a ready target', async () => {
    const fixture = createProvisionerFixture();
    fixture.dialOnce.mockRejectedValueOnce(new Error('socket missing'));

    await expect(fixture.provisioner.ensure('ssh-1')).resolves.toMatchObject({ kind: 'ssh' });

    expect(fixture.installer.install).toHaveBeenCalledOnce();
    expect(fixture.daemon.start).toHaveBeenCalledOnce();
    expect(fixture.daemon.restart).not.toHaveBeenCalled();
    expect(fixture.dialOnce).toHaveBeenCalledTimes(2);
    expect(fixture.status('ssh-1')).toEqual({
      status: 'healthy',
      version: '1.2.3',
      startedAt: 1,
    });
    await fixture.dispose();
  });

  it('reinstalls and restarts when the handshake requires a server upgrade', async () => {
    const fixture = createProvisionerFixture();
    fixture.dialOnce.mockRejectedValueOnce(
      new WorkspaceServerProtocolError({
        type: 'protocol-incompatible',
        action: 'upgrade-server',
        clientProtocolVersion: '5.0.0',
        serverProtocolVersion: '4.0.0',
      })
    );

    await fixture.provisioner.ensure('ssh-1');

    expect(fixture.installer.install).toHaveBeenCalledOnce();
    expect(fixture.daemon.restart).toHaveBeenCalledOnce();
    expect(fixture.daemon.start).not.toHaveBeenCalled();
    await fixture.dispose();
  });

  it('dev auto-updates a compatible running daemon when its channel pointer advertises a newer version', async () => {
    const fixture = createProvisionerFixture({ devAutoUpdate: true });
    fixture.installer.availableVersion.mockResolvedValue('1.2.4-dev.abc123');
    fixture.dialOnce
      .mockResolvedValueOnce(handshake('1.2.3'))
      .mockResolvedValueOnce(handshake('1.2.4-dev.abc123'));

    await fixture.provisioner.ensure('ssh-1');

    expect(fixture.installer.availableVersion).toHaveBeenCalledWith(
      'ssh-1',
      expect.any(AbortSignal)
    );
    expect(fixture.installer.install).toHaveBeenCalledWith(
      expect.objectContaining({
        connectionId: 'ssh-1',
        signal: expect.any(AbortSignal),
        version: '1.2.4-dev.abc123',
      })
    );
    expect(fixture.daemon.restart).toHaveBeenCalledOnce();
    expect(fixture.daemon.start).not.toHaveBeenCalled();
    expect(fixture.status('ssh-1')).toMatchObject({
      status: 'healthy',
      version: '1.2.4-dev.abc123',
    });
    await fixture.dispose();
  });

  it('dev auto-update leaves matching running daemons alone', async () => {
    const fixture = createProvisionerFixture({ devAutoUpdate: true });
    fixture.installer.availableVersion.mockResolvedValue('1.2.3');

    await fixture.provisioner.ensure('ssh-1');

    expect(fixture.installer.availableVersion).toHaveBeenCalledOnce();
    expect(fixture.installer.install).not.toHaveBeenCalled();
    expect(fixture.daemon.restart).not.toHaveBeenCalled();
    await fixture.dispose();
  });

  it('dev auto-update bypasses the provisioned target cache', async () => {
    const fixture = createProvisionerFixture({ devAutoUpdate: true });
    await fixture.provisioner.ensure('ssh-1');
    await fixture.provisioner.ensure('ssh-1');

    expect(fixture.dialOnce).toHaveBeenCalledTimes(2);
    expect(fixture.installer.availableVersion).toHaveBeenCalledTimes(2);
    await fixture.dispose();
  });

  it('dev auto-update treats latest-version resolution failures as non-fatal', async () => {
    const fixture = createProvisionerFixture({ devAutoUpdate: true });
    fixture.installer.availableVersion.mockRejectedValue(new Error('metadata unavailable'));

    await fixture.provisioner.ensure('ssh-1');

    expect(fixture.installer.install).not.toHaveBeenCalled();
    expect(fixture.daemon.restart).not.toHaveBeenCalled();
    expect(fixture.logger.warn).toHaveBeenCalledWith(
      'Could not resolve latest workspace-server dev version',
      expect.objectContaining({ connectionId: 'ssh-1' })
    );
    expect(fixture.status('ssh-1')).toMatchObject({ status: 'healthy', version: '1.2.3' });
    await fixture.dispose();
  });

  it('publishes typed failures and keeps them observable', async () => {
    const fixture = createProvisionerFixture();
    fixture.dialOnce.mockRejectedValueOnce(new Error('socket missing'));
    fixture.installer.install.mockRejectedValue(
      new WorkspaceServerInstallError('unsupported-platform', 'musl is unsupported')
    );

    await expect(fixture.provisioner.ensure('ssh-1')).rejects.toMatchObject({
      code: 'unsupported-platform',
    });
    expect(fixture.status('ssh-1')).toMatchObject({
      status: 'failed',
      error: { code: 'unsupported-platform' },
    });
    await fixture.dispose();
  });

  it('cancels an in-flight host probe and removes its stale state', async () => {
    const fixture = createProvisionerFixture({ blockHostProbe: true });
    const pending = fixture.provisioner.ensure('ssh-1');
    const rejected = expect(pending).rejects.toThrow('cancelled for ssh-1');
    await Promise.resolve();

    await fixture.provisioner.cancel('ssh-1');

    await rejected;
    expect(fixture.status('ssh-1')).toBeUndefined();
    await fixture.dispose();
  });

  it('does not enter the install path when the initial dial is cancelled', async () => {
    const fixture = createProvisionerFixture({ blockDial: true });
    const pending = fixture.provisioner.ensure('ssh-1');
    const rejected = expect(pending).rejects.toThrow('cancelled for ssh-1');
    await Promise.resolve();

    await fixture.provisioner.cancel('ssh-1');

    await rejected;
    expect(fixture.installer.install).not.toHaveBeenCalled();
    expect(fixture.daemon.start).not.toHaveBeenCalled();
    await fixture.dispose();
  });
});

function createProvisionerFixture(
  options: { blockDial?: boolean; blockHostProbe?: boolean; devAutoUpdate?: boolean } = {}
) {
  const scope = createScope({ label: 'workspace-server-provisioner-test' });
  const model = new HostStateModel();
  const hostProbe = vi.fn((_connectionId: string, signal?: AbortSignal) => {
    if (!options.blockHostProbe) {
      return Promise.resolve({ home: '/home/devuser' });
    }
    return new Promise<never>((_resolve, reject) => {
      signal?.addEventListener(
        'abort',
        () => reject(signal.reason instanceof Error ? signal.reason : new Error('aborted')),
        { once: true }
      );
    });
  });
  const installer = {
    install: vi.fn(async () => {}),
    availableVersion: vi.fn(async () => '1.2.3'),
  };
  const daemon = {
    start: vi.fn(async () => {}),
    restart: vi.fn(async () => {}),
  };
  const dialOnce = vi.fn((_target, dialOptions: { signal: AbortSignal }) => {
    if (!options.blockDial) return Promise.resolve(handshake());
    return new Promise<never>((_resolve, reject) => {
      dialOptions.signal.addEventListener(
        'abort',
        () =>
          reject(
            dialOptions.signal.reason instanceof Error
              ? dialOptions.signal.reason
              : new Error('aborted')
          ),
        { once: true }
      );
    });
  });
  const logger = { warn: vi.fn() };
  const provisioner = new WorkspaceServerProvisioner({
    scope,
    ssh: { ensureProxy: vi.fn() },
    host: { probe: hostProbe } as never,
    installer: installer as never,
    daemon: daemon as never,
    model,
    wire: { dialOnce },
    devAutoUpdate: options.devAutoUpdate,
    logger,
  });

  return {
    provisioner,
    installer,
    daemon,
    dialOnce,
    logger,
    model,
    status(connectionId: string) {
      return model.snapshot()[connectionId];
    },
    async dispose() {
      model.dispose();
      await scope.dispose();
    },
  };
}

function handshake(appVersion = '1.2.3'): WireInitializeResult {
  return {
    protocolVersion: PROTOCOL_VERSION,
    agreedVersion: PROTOCOL_VERSION,
    agreedMinor: 0,
    server: { appVersion, daemonId: 'daemon', startedAt: 1 },
  };
}

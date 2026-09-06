import { PROTOCOL_VERSION, type WireInitializeResult } from '@emdash/core/workspace-server';
import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it, vi } from 'vitest';
import { HostServerOperations } from './server-operations';
import { HostStateModel } from './state-model';
import { WorkspaceServerProtocolError } from './workspace-server/connect/protocol';

describe('HostServerOperations', () => {
  it('reports a missing installation without dialing the workspace server', async () => {
    const fixture = createFixture();
    fixture.installer.installedVersion.mockResolvedValueOnce(undefined);

    await fixture.operations.refresh('ssh-1');

    expect(fixture.status('ssh-1')).toEqual({ status: 'not-installed' });
    expect(fixture.wire.dialOnce).not.toHaveBeenCalled();
    await fixture.dispose();
  });

  it('reports an installed but unreachable workspace server as stopped', async () => {
    const fixture = createFixture();
    fixture.wire.dialOnce.mockRejectedValueOnce(new Error('socket missing'));

    await fixture.operations.refresh('ssh-1');

    expect(fixture.status('ssh-1')).toEqual({
      status: 'stopped',
      version: '1.2.3',
      latestVersion: '1.2.4',
      updateAvailable: true,
    });
    await fixture.dispose();
  });

  it('publishes handshake metadata and the latest available version for a healthy server', async () => {
    const fixture = createFixture();

    await fixture.operations.refresh('ssh-1');

    expect(fixture.status('ssh-1')).toEqual({
      status: 'healthy',
      version: '1.2.3',
      latestVersion: '1.2.4',
      updateAvailable: true,
      startedAt: 100,
    });
    await fixture.dispose();
  });

  it('publishes protocol incompatibility as a running server with a typed error', async () => {
    const fixture = createFixture();
    fixture.wire.dialOnce.mockRejectedValueOnce(protocolError('upgrade-server'));

    await fixture.operations.refresh('ssh-1');

    expect(fixture.status('ssh-1')).toMatchObject({
      status: 'healthy',
      version: '1.2.3',
      latestVersion: '1.2.4',
      updateAvailable: true,
      error: { code: 'protocol-upgrade-server' },
    });
    await fixture.dispose();
  });

  it('preserves the running lifecycle when restart hits a protocol incompatibility', async () => {
    const fixture = createFixture();
    fixture.wire.dialOnce.mockRejectedValueOnce(protocolError('upgrade-client'));

    await expect(fixture.operations.restart('ssh-1')).rejects.toBeInstanceOf(
      WorkspaceServerProtocolError
    );

    expect(fixture.status('ssh-1')).toMatchObject({
      status: 'healthy',
      version: '1.2.3',
      error: { code: 'protocol-upgrade-client' },
    });
    await fixture.dispose();
  });

  it('preserves the latest available version when latest-version resolution fails', async () => {
    const fixture = createFixture();
    fixture.installer.availableVersion.mockRejectedValueOnce(new Error('metadata unavailable'));

    await fixture.operations.refresh('ssh-1');

    expect(fixture.status('ssh-1')).toEqual({
      status: 'healthy',
      version: '1.2.3',
      startedAt: 100,
    });
    await fixture.dispose();
  });

  it('publishes an older fallback version without offering a downgrade', async () => {
    const fixture = createFixture();
    fixture.installer.installedVersion.mockResolvedValue('1.2.4-canary.42');
    fixture.installer.availableVersion.mockResolvedValue('1.2.3');
    fixture.wire.dialOnce.mockResolvedValue(handshake('1.2.4-canary.42'));

    await fixture.operations.refresh('ssh-1');

    expect(fixture.status('ssh-1')).toEqual({
      status: 'healthy',
      version: '1.2.4-canary.42',
      latestVersion: '1.2.3',
      startedAt: 100,
    });
    await fixture.dispose();
  });

  it('caches latest-version checks unless refresh is forced', async () => {
    const fixture = createFixture();
    fixture.installer.availableVersion
      .mockResolvedValueOnce('1.2.4')
      .mockResolvedValueOnce('1.2.5');

    await fixture.operations.refresh('ssh-1');
    await fixture.operations.refresh('ssh-1');
    expect(fixture.installer.availableVersion).toHaveBeenCalledOnce();
    expect(fixture.status('ssh-1')?.latestVersion).toBe('1.2.4');

    await fixture.operations.refresh('ssh-1', { force: true });

    expect(fixture.installer.availableVersion).toHaveBeenCalledTimes(2);
    expect(fixture.status('ssh-1')?.latestVersion).toBe('1.2.5');
    await fixture.dispose();
  });

  it('invalidates the wire client before stopping the daemon', async () => {
    const fixture = createFixture();

    await fixture.operations.stop('ssh-1');

    expect(fixture.provision.drop).toHaveBeenCalledWith('ssh-1');
    expect(fixture.wire.invalidateConnection).toHaveBeenCalledWith('ssh-1');
    expect(fixture.daemon.stop).toHaveBeenCalledOnce();
    expect(fixture.status('ssh-1')).toEqual({ status: 'stopped', version: '1.2.3' });
    await fixture.dispose();
  });
});

function createFixture() {
  const scope = createScope({ label: 'host-server-operations-test' });
  const state = new HostStateModel();
  const host = {
    probe: vi.fn(async () => ({ home: '/home/devuser' })),
  };
  const installer = {
    installedVersion: vi.fn(async () => '1.2.3' as string | undefined),
    availableVersion: vi.fn(async () => '1.2.4'),
    install: vi.fn(async () => {}),
  };
  const daemon = {
    start: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
  };
  const wire = {
    dialOnce: vi.fn(async () => handshake()),
    invalidateConnection: vi.fn(async () => {}),
  };
  const provision = {
    drop: vi.fn(),
  };
  const operations = new HostServerOperations({
    scope,
    state,
    host,
    installer,
    daemon,
    wire,
    provision,
  });

  return {
    operations,
    installer,
    daemon,
    wire,
    provision,
    status(connectionId: string) {
      return state.snapshot()[connectionId];
    },
    async dispose() {
      state.dispose();
      await scope.dispose();
    },
  };
}

function protocolError(action: 'upgrade-client' | 'upgrade-server'): WorkspaceServerProtocolError {
  return new WorkspaceServerProtocolError({
    type: 'protocol-incompatible',
    action,
    clientProtocolVersion: '2.0.0',
    serverProtocolVersion: '1.0.0',
  });
}

function handshake(appVersion = '1.2.3'): WireInitializeResult {
  return {
    protocolVersion: PROTOCOL_VERSION,
    agreedVersion: PROTOCOL_VERSION,
    agreedMinor: 0,
    server: {
      appVersion,
      daemonId: 'daemon-1',
      startedAt: 100,
    },
  };
}

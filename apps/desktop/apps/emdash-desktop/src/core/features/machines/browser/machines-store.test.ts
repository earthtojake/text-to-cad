import type { HostDependencySnapshot } from '@emdash/core/services/host-dependencies/api';
import { ok } from '@emdash/shared';
import { cell, expose, peek, produce } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  machinesContract,
  type InstallMachineSystemDependenciesInput,
  type SaveMachineInput,
} from '@core/features/machines/api';
import type { SshConfig } from '@core/primitives/ssh/api';
import { sshContract, type SshConnectionsRuntime } from '@core/services/ssh/api';
import { MachinesStore } from './machines-store';

const hostCommands = vi.hoisted(() => ({
  requestReady: vi.fn(async () => {}),
  disconnect: vi.fn(async () => {}),
}));

const savedConnection: SshConfig = {
  id: 'ssh-1',
  name: 'Corp',
  host: 'corp.example.com',
  port: 22,
  username: 'alice',
  authType: 'agent',
  useAgent: true,
};

describe('MachinesStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('routes Connect through the Hosts-owned explicit readiness command', async () => {
    const fixture = setup({
      runtime: {
        'ssh-1': runtimeEntry('disconnected'),
      },
    });

    await fixture.store.start();
    await fixture.store.connect('ssh-1');

    expect(hostCommands.requestReady).toHaveBeenCalledWith({
      host: { type: 'remote', id: 'ssh-1' },
      cause: 'connect',
    });
    expect(fixture.connect).not.toHaveBeenCalled();

    await fixture.dispose();
  });

  it('reads health and state from the merged runtime model', async () => {
    const fixture = setup();
    await fixture.store.start();

    fixture.updateRuntime((runtime) => {
      runtime['ssh-1'] = {
        state: 'disconnected',
        health: { status: 'degraded' },
      };
    });
    await vi.waitFor(() =>
      expect(fixture.store.healthFor('ssh-1')).toEqual({ status: 'degraded' })
    );
    expect(fixture.store.stateFor('ssh-1')).toBe('disconnected');

    fixture.updateRuntime((runtime) => {
      runtime['ssh-1']!.health = { status: 'ok' };
    });
    await vi.waitFor(() => expect(fixture.store.healthFor('ssh-1')).toEqual({ status: 'ok' }));
    expect(fixture.store.healthStates).toEqual({ 'ssh-1': { status: 'ok' } });

    await fixture.dispose();
  });

  it('routes Retry through the same Hosts-owned explicit readiness command', async () => {
    const fixture = setup({
      runtime: { 'ssh-1': runtimeEntry('reconnecting') },
    });
    await fixture.store.start();

    await fixture.store.retry('ssh-1');

    expect(hostCommands.requestReady).toHaveBeenCalledWith({
      host: { type: 'remote', id: 'ssh-1' },
      cause: 'retry',
    });
    expect(fixture.connect).not.toHaveBeenCalled();
    await fixture.dispose();
  });

  it('routes Disconnect through Hosts without tearing down SSH from the browser', async () => {
    const fixture = setup({
      runtime: { 'ssh-1': runtimeEntry('connected') },
    });
    await fixture.store.start();

    await fixture.store.disconnect('ssh-1');

    expect(hostCommands.disconnect).toHaveBeenCalledWith({
      host: { type: 'remote', id: 'ssh-1' },
    });
    expect(fixture.disconnect).not.toHaveBeenCalled();

    await fixture.dispose();
  });

  it('passes CRUD and test operations through while updating only the saved list locally', async () => {
    const fixture = setup({
      saved: [savedConnection],
      runtime: { 'ssh-1': runtimeEntry('connected') },
      removeRuntimeOnDelete: true,
    });
    await fixture.store.start();

    await fixture.store.saveConnection({
      ...savedConnection,
      name: 'Corp updated',
      sshConfigAlias: 'corp-dev',
      forwardAgent: true,
      proxyJump: 'bastion',
    });
    expect(fixture.saveMachine.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        sshConfigAlias: 'corp-dev',
        forwardAgent: true,
        proxyJump: 'bastion',
      })
    );
    expect(fixture.store.connections[0]?.name).toBe('Corp updated');

    await fixture.store.renameConnection('ssh-1', 'Renamed');
    expect(fixture.renameMachine.mock.calls[0]?.[0]).toEqual({
      id: 'ssh-1',
      name: 'Renamed',
    });
    expect(fixture.store.connections[0]?.name).toBe('Renamed');

    await expect(fixture.store.getSshConfigHosts()).resolves.toEqual([]);
    await expect(fixture.store.getSshConfigHost('corp-dev')).resolves.toMatchObject({
      host: 'corp-dev',
    });
    await expect(fixture.store.testConnection(savedConnection)).resolves.toEqual({
      success: true,
    });

    await fixture.store.deleteConnection('ssh-1');
    expect(fixture.deleteMachine.mock.calls[0]?.[0]).toEqual({ id: 'ssh-1' });
    expect(fixture.store.connections).toEqual([]);
    await vi.waitFor(() => expect(fixture.store.stateFor('ssh-1')).toBe('disconnected'));

    await fixture.dispose();
  });

  it('runs system dependency installs through the live job client', async () => {
    const fixture = setup();

    await expect(
      fixture.store.installSystemDependencies({
        machineId: 'ssh-1',
        dependencies: [{ id: 'git' }, { id: 'node', method: 'apt' }],
      })
    ).resolves.toEqual({
      git: { success: false, error: { type: 'unknown-dependency', id: 'git' } },
      node: { success: false, error: { type: 'unknown-dependency', id: 'node' } },
    });
    expect(fixture.installSystemDependencies).toHaveBeenCalledWith(
      {
        machineId: 'ssh-1',
        dependencies: [{ id: 'git' }, { id: 'node', method: 'apt' }],
      },
      expect.anything()
    );

    await fixture.dispose();
  });
});

function runtimeEntry(
  state: SshConnectionsRuntime[string]['state']
): SshConnectionsRuntime[string] {
  return { state, health: { status: 'ok' } };
}

function setup(
  options: {
    runtime?: SshConnectionsRuntime;
    saved?: SshConfig[];
    removeRuntimeOnDelete?: boolean;
  } = {}
) {
  const connect = vi.fn(async (_connectionId: string) => {});
  const disconnect = vi.fn(async (_connectionId: string) => {});
  const runtime = cell<SshConnectionsRuntime>(options.runtime ?? {});
  const connections = expose(sshContract.connections, { runtime });
  const updateRuntime = (update: (runtime: SshConnectionsRuntime) => void): void => {
    runtime.set(produce(peek(runtime), update));
  };
  const saveMachine = vi.fn(
    async (input: SaveMachineInput): Promise<SshConfig> => ({
      ...input,
      id: input.id ?? 'ssh-1',
    })
  );
  const renameMachine = vi.fn(async (_input: { id: string; name: string }) => {});
  const deleteMachine = vi.fn(async ({ id }: { id: string }) => {
    if (!options.removeRuntimeOnDelete) return;
    updateRuntime((runtime) => {
      delete runtime[id];
    });
  });
  const installSystemDependencies = vi.fn(
    async ({ dependencies }: InstallMachineSystemDependenciesInput) =>
      ok(
        Object.fromEntries(
          dependencies.map(({ id }) => [
            id,
            {
              success: false as const,
              error: { type: 'unknown-dependency' as const, id },
            },
          ])
        )
      )
  );
  const systemDependenciesSnapshot = cell<HostDependencySnapshot>({
    hostId: 'test-host',
    generation: 0,
    hostElevation: null,
    dependencies: {},
  });
  const systemDependencies = expose(
    machinesContract.systemDependencies,
    { current: systemDependenciesSnapshot },
    {
      mutations: {
        refresh: async () => ok(peek(systemDependenciesSnapshot)),
      },
    }
  );
  const sshWire = createTestWire(sshContract, {
    connections,
    connect: async ({ connectionId }) => {
      updateRuntime((runtime) => {
        runtime[connectionId] = runtimeEntry('connecting');
      });
      try {
        await connect(connectionId);
      } catch (error) {
        updateRuntime((runtime) => {
          runtime[connectionId] = runtimeEntry('error');
        });
        throw error;
      }
      updateRuntime((runtime) => {
        runtime[connectionId] = runtimeEntry('connected');
      });
      return 'connected' as const;
    },
    ensureConnected: async ({ connectionId }) => {
      updateRuntime((runtime) => {
        runtime[connectionId] = runtimeEntry('connecting');
      });
      updateRuntime((runtime) => {
        runtime[connectionId] = runtimeEntry('connected');
      });
      return 'connected' as const;
    },
    disconnect: async ({ connectionId }) => {
      await disconnect(connectionId);
      updateRuntime((runtime) => {
        runtime[connectionId] = runtimeEntry('disconnected');
      });
    },
    getSshConfigHosts: async () => [],
    getSshConfigHost: async ({ alias }) => ({ host: alias }),
    testConnection: async () => ({ success: true }),
  });
  const hostSettings = expose(machinesContract.hostSettings, {
    current: () => cell({ settings: {}, parseError: false }),
  });
  const machinesWire = createTestWire(machinesContract, {
    getMachines: async () => options.saved ?? [],
    getMachineUsage: async () => ({}),
    getMachineMetrics: async () => null as never,
    systemDependencies,
    hostSettings,
    updateHostSettings: async () => ok({ settings: {}, parseError: false }),
    installSystemDependencies: {
      run: installSystemDependencies,
      toError: (error) => ({
        type: 'io' as const,
        message: error instanceof Error ? error.message : String(error),
      }),
    },
    saveMachine,
    deleteMachine,
    renameMachine,
  });
  const store = new MachinesStore({
    sshClient: sshWire.client,
    machinesClient: machinesWire.client,
    hostsClient: hostCommands,
  });

  return {
    store,
    updateRuntime,
    connect,
    disconnect,
    saveMachine,
    renameMachine,
    deleteMachine,
    installSystemDependencies,
    async dispose() {
      store.dispose();
      await Promise.all([sshWire.dispose(), machinesWire.dispose()]);
    },
  };
}

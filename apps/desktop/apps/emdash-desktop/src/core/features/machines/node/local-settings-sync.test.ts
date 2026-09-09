import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { LocalSettingsSync, type LocalSettingsSyncDeps } from './local-settings-sync';

const remoteHost = hostRef('remote', 'ssh-1');
const otherHost = hostRef('remote', 'ssh-2');

function createSync(overrides: Partial<LocalSettingsSyncDeps> = {}) {
  const update = vi.fn(async () => ok({ settings: {}, parseError: false }));
  const client = vi.fn(async () => ok({ hostSettings: { update } }));
  const sync = new LocalSettingsSync({
    runtimes: { client: client as never },
    getWatcherExclude: async () => ['**/node_modules/**'],
    isSyncEnabled: async () => true,
    logger: { warn: vi.fn() },
    ...overrides,
  });
  return { sync, update, client };
}

describe('LocalSettingsSync', () => {
  it('mirrors watcherExclude on attach when sync is enabled', async () => {
    const { sync, update } = createSync();
    await sync.attachHost(remoteHost);
    expect(update).toHaveBeenCalledWith({ watcherExclude: ['**/node_modules/**'] });
  });

  it('does not push on attach when sync is disabled', async () => {
    const { sync, update } = createSync({ isSyncEnabled: async () => false });
    await sync.attachHost(remoteHost);
    expect(update).not.toHaveBeenCalled();
  });

  it('ignores the local host', async () => {
    const { sync, update, client } = createSync();
    await sync.attachHost(LOCAL_HOST_REF);
    expect(client).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });

  it('pushes to every attached sync-enabled host on local setting change', async () => {
    const enabled = new Set(['ssh-1']);
    const { sync, update, client } = createSync({
      isSyncEnabled: async (connectionId) => enabled.has(connectionId),
    });
    await sync.attachHost(remoteHost);
    await sync.attachHost(otherHost);
    update.mockClear();
    client.mockClear();

    await sync.handleLocalSettingsChanged();
    expect(client).toHaveBeenCalledTimes(1);
    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it('does not push to detached hosts', async () => {
    const { sync, update } = createSync();
    await sync.attachHost(remoteHost);
    sync.detachHost(remoteHost);
    update.mockClear();

    await sync.handleLocalSettingsChanged();
    expect(update).not.toHaveBeenCalled();
  });

  it('pushes immediately when the toggle flips ON for an attached host', async () => {
    const { sync, update } = createSync({ isSyncEnabled: async () => false });
    await sync.attachHost(remoteHost);
    expect(update).not.toHaveBeenCalled();

    await sync.handleSyncToggled('ssh-1', true);
    expect(update).toHaveBeenCalledWith({ watcherExclude: ['**/node_modules/**'] });
  });

  it('toggling OFF pushes nothing (last mirrored value stands)', async () => {
    const { sync, update } = createSync();
    await sync.attachHost(remoteHost);
    update.mockClear();

    await sync.handleSyncToggled('ssh-1', false);
    expect(update).not.toHaveBeenCalled();
  });

  it('toggle ON for an unattached host is a no-op', async () => {
    const { sync, update } = createSync();
    await sync.handleSyncToggled('ssh-1', true);
    expect(update).not.toHaveBeenCalled();
  });

  it('logs and swallows push failures', async () => {
    const warn = vi.fn();
    const update = vi.fn(async () => err({ type: 'io-failed', message: 'disk full' }));
    const client = vi.fn(async () => ok({ hostSettings: { update } }));
    const sync = new LocalSettingsSync({
      runtimes: { client: client as never },
      getWatcherExclude: async () => [],
      isSyncEnabled: async () => true,
      logger: { warn },
    });

    await expect(sync.attachHost(remoteHost)).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalledOnce();
  });
});

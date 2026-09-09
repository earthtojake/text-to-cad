import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as drizzleClientModule from '@main/db/drizzleClient';
import * as databaseInitializeModule from '@main/db/initialize';
import { getAppDb, resetAppDbForTests, setAppDb } from '@main/db/instance';
import { bootDatabase } from './database';

const mocks = vi.hoisted(() => {
  const db = {
    run: vi.fn(),
    select: vi.fn(() => ({
      from: vi.fn(async () => []),
    })),
  };
  const sqlite = {};
  const client = {
    close: vi.fn(),
    db,
    sqlite,
  };
  return {
    cleanupLegacyBrowserPartitions: vi.fn(),
    client,
    createDrizzleClient: vi.fn(() => client),
    editorBufferDispose: vi.fn(),
    editorBufferPrune: vi.fn(),
    initializeDatabase: vi.fn(async () => sqlite),
    resetStaleAcpAgentStatuses: vi.fn(),
    resetStaleTuiAgentStatuses: vi.fn(),
    runInBackground: vi.fn(),
    setWorkspaceIdentityService: vi.fn(),
  };
});

vi.mock('@core/features/editor/node/editor-buffer-service', () => ({
  createEditorBufferService: () => ({
    dispose: mocks.editorBufferDispose,
    pruneStale: mocks.editorBufferPrune,
  }),
  editorBufferDatabasePath: (appDatabasePath: string) => `${appDatabasePath}-editor-buffers`,
}));
vi.mock('@main/db/path', () => ({
  resolveDatabasePath: () => '/tmp/emdash-test.db',
}));
vi.mock('@core/features/workspaces/node/workspace-identity-source', () => ({
  createWorkspaceIdentityService: () => ({}),
}));
vi.mock('@core/features/workspaces/api/node/runtime-access', () => ({
  acquireWorkspaceRuntime: vi.fn(),
}));
vi.mock('@core/services/settings/node', () => ({
  createAppSettingsService: () => ({}),
}));
vi.mock('@core/features/conversations/node/reset-stale-acp-agent-statuses', () => ({
  resetStaleAcpAgentStatuses: mocks.resetStaleAcpAgentStatuses,
}));
vi.mock('@core/features/conversations/node/reset-stale-tui-agent-statuses', () => ({
  resetStaleTuiAgentStatuses: mocks.resetStaleTuiAgentStatuses,
}));
vi.mock('@main/host/browser/browser-partition-cleanup', () => ({
  cleanupLegacyBrowserPartitions: mocks.cleanupLegacyBrowserPartitions,
}));
vi.mock('@main/lib/logger', () => ({
  log: { warn: vi.fn(), info: vi.fn(), error: vi.fn() },
}));
vi.mock('../../core/background', () => ({
  runInBackground: mocks.runInBackground,
}));
vi.mock('../../core/service-instances', () => ({
  setWorkspaceIdentityService: mocks.setWorkspaceIdentityService,
}));

describe('database boot phase', () => {
  beforeEach(() => {
    resetAppDbForTests();
    vi.clearAllMocks();
    mocks.initializeDatabase.mockResolvedValue(mocks.client.sqlite);
    vi.spyOn(drizzleClientModule, 'createDrizzleClient').mockImplementation(
      mocks.createDrizzleClient as never
    );
    vi.spyOn(databaseInitializeModule, 'initializeDatabase').mockImplementation(
      mocks.initializeDatabase as never
    );
    mocks.resetStaleAcpAgentStatuses.mockImplementation(() => {
      expect(getAppDb()).toBe(mocks.client.db);
    });
  });

  afterEach(() => {
    resetAppDbForTests();
  });

  it('initializes and publishes one client before startup repairs', async () => {
    await bootDatabase({ forceBootFailure: false } as never);

    expect(mocks.createDrizzleClient).toHaveBeenCalledOnce();
    expect(mocks.initializeDatabase).toHaveBeenCalledWith(mocks.client.sqlite);
    expect(getAppDb()).toBe(mocks.client.db);
    expect(mocks.client.close).not.toHaveBeenCalled();
    expect(mocks.resetStaleAcpAgentStatuses).toHaveBeenCalledOnce();
  });

  it('disposes the buffer store when startup repairs fail', async () => {
    mocks.resetStaleAcpAgentStatuses.mockImplementation(() => {
      throw new Error('repairs failed');
    });

    await expect(bootDatabase({ forceBootFailure: false } as never)).rejects.toThrow(
      'repairs failed'
    );

    expect(mocks.editorBufferDispose).toHaveBeenCalledOnce();
    expect(() => getAppDb()).toThrow('App database has not been initialized');
  });

  it('closes an unpublished client when initialization fails', async () => {
    mocks.initializeDatabase.mockRejectedValue(new Error('migration failed'));

    await expect(bootDatabase({ forceBootFailure: false } as never)).rejects.toThrow(
      'migration failed'
    );

    expect(() => getAppDb()).toThrow('App database has not been initialized');
    expect(mocks.client.close).toHaveBeenCalledOnce();
  });

  it('closes the new client when publishing fails', async () => {
    setAppDb({ db: {} as never, sqlite: {} as never, close: vi.fn() });

    await expect(bootDatabase({ forceBootFailure: false } as never)).rejects.toThrow(
      'already initialized'
    );

    expect(mocks.client.close).toHaveBeenCalledOnce();
    expect(mocks.resetStaleAcpAgentStatuses).not.toHaveBeenCalled();
  });

  it('does not create a client for a forced pre-database boot failure', async () => {
    await expect(bootDatabase({ forceBootFailure: true } as never)).rejects.toThrow(
      'Boot failure forced'
    );

    expect(mocks.createDrizzleClient).not.toHaveBeenCalled();
  });
});

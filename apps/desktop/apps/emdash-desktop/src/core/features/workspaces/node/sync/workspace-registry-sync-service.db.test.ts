import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import {
  workspaceRegistryContract,
  type WorkspaceRecord,
  type WorkspaceRecords,
} from '@emdash/core/runtimes/workspace-registry/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { createController } from '@emdash/wire/rpc';
import { cell, expose, type Cell } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { WorkspaceRegistrySyncService } from './workspace-registry-sync-service';

function hostRecord(id: string, path: string): WorkspaceRecord {
  return {
    id,
    kind: 'repository',
    path,
    parentId: null,
    origin: 'registered',
    gitAdminName: null,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1,
    updatedAt: 1,
    lastObservedAt: 1,
    config: null,
    runtime: null,
  };
}

describe('WorkspaceRegistrySyncService identity invariant', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let hostRecords: Cell<WorkspaceRecords>;
  let recordsHost: ReturnType<typeof expose<typeof workspaceRegistryContract.records>>;
  let projectConfigHost: ReturnType<typeof expose<typeof workspaceRegistryContract.projectConfig>>;
  let wire: TestWire<typeof workspaceRegistryContract>;
  let service: WorkspaceRegistrySyncService;
  let onError: ReturnType<typeof vi.fn<(context: string, error: unknown) => void>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    hostRecords = cell<WorkspaceRecords>({}, { name: 'test-workspace-records' });
    recordsHost = expose(workspaceRegistryContract.records, { list: () => hostRecords });
    projectConfigHost = expose(workspaceRegistryContract.projectConfig, {
      current: () => cell({} as never),
    });
    const unused = () => {
      throw new Error('not exercised by the sync service');
    };
    wire = createTestWire(
      workspaceRegistryContract,
      createController(workspaceRegistryContract, {
        records: recordsHost,
        projectConfig: projectConfigHost,
        getProjectConfig: unused,
        refreshProjectConfig: unused,
        patchPersonalProjectConfig: unused,
        importLegacyLifecycleSettings: unused,
        createWorkspace: unused,
        createWorktree: unused,
        retryStep: unused,
        runScript: unused,
        activateWorkspace: unused,
        deactivateWorkspace: unused,
        deleteWorkspace: unused,
        deleteWorktree: unused,
        updateWorktree: unused,
        measureUsage: unused,
        refresh: unused,
      } as never)
    );
    onError = vi.fn();
    const broker = {
      client: async () => ({ success: true, data: { workspaceRegistry: wire.client } }),
    } as unknown as RuntimeBroker;
    service = new WorkspaceRegistrySyncService({ db: fixture.db, runtimes: broker, onError });
  });

  afterEach(async () => {
    service?.dispose();
    await recordsHost.dispose();
    await projectConfigHost.dispose();
    await wire.dispose();
    fixture.close();
  });

  it('reports one diagnostic and stops a conflicting attachment without partial sync', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'desktop-id',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });
    hostRecords.set({ 'host-id': hostRecord('host-id', '/repo') });

    await service.attachHost(LOCAL_HOST_REF);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(
      'workspace registry identity invariant',
      expect.objectContaining({
        incomingId: 'host-id',
        conflictingId: 'desktop-id',
        path: '/repo',
      })
    );
    expect(registry.getLive('host-id')).toBeUndefined();

    hostRecords.set({
      'host-id': hostRecord('host-id', '/repo'),
      later: hostRecord('later', '/later'),
    });
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(registry.getLive('later')).toBeUndefined();

    await service.attachHost(LOCAL_HOST_REF);
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

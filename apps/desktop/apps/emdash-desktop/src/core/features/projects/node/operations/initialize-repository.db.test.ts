import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { ok } from '@emdash/shared';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import { projects } from '@core/services/app-db/node/schema';
import { initializeRepository } from './initialize-repository';

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

describe('initializeRepository', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => fixture.close());

  it('rebinds the Project when the Host returns another canonical Repository id', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'desktop-repository',
      type: 'local',
      kind: 'directory',
      location: 'local',
      path: '/repo',
    });
    fixture.db
      .insert(projects)
      .values({
        id: 'project',
        name: 'Project',
        repositoryWorkspaceId: 'desktop-repository',
      })
      .run();

    const createWorkspace = vi.fn(async () => ok(hostRecord('host-repository', '/repo')));
    const runtimes = {
      client: vi.fn(async () =>
        ok({
          git: {
            ensureRepository: vi.fn(async () =>
              ok({ rootPath: hostPathFromNative('/repo'), baseRef: 'main' })
            ),
          },
          workspaceRegistry: { createWorkspace },
        })
      ),
    } as unknown as Pick<RuntimeBroker, 'client'>;

    const result = await initializeRepository(
      {
        db: fixture.db,
        runtimes,
        projects: { invalidate: vi.fn(async () => undefined) },
      },
      'project'
    );

    expect(result).toMatchObject({
      success: true,
      data: { repositoryWorkspaceId: 'host-repository', baseRef: 'main' },
    });
    expect(fixture.db.select().from(projects).get()).toMatchObject({
      repositoryWorkspaceId: 'host-repository',
    });
    expect(registry.getLive('desktop-repository')).toBeUndefined();
    expect(registry.getLive('host-repository')).toMatchObject({
      id: 'host-repository',
      kind: 'repository',
      path: '/repo',
    });
  });
});

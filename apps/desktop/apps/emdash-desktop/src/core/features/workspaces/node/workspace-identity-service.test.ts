import { LOCAL_HOST_REF, hostRef } from '@emdash/core/primitives/host/api';
import { hostRefFromParts } from '@emdash/core/primitives/host/api';
import { describe, expect, it, vi } from 'vitest';
import {
  WorkspaceIdentityService,
  workspaceHostStorage,
  type WorkspaceIdentityRow,
  type WorkspaceIdentitySource,
} from '@core/features/workspaces/api/node/workspace-identity-service';

const localRow: WorkspaceIdentityRow = {
  workspaceId: 'workspace-local',
  type: 'local',
  location: 'local',
  sshConnectionId: null,
  path: '/local/repo',
  projectId: 'project-local',
};

const remoteRow: WorkspaceIdentityRow = {
  workspaceId: 'workspace-remote',
  type: 'project-ssh',
  location: 'remote',
  sshConnectionId: 'ssh-1',
  path: '/remote/repo',
  projectId: 'project-remote',
};

function createSource(rows: readonly WorkspaceIdentityRow[]): WorkspaceIdentitySource {
  return {
    findById: vi.fn(
      async (workspaceId) => rows.find((row) => row.workspaceId === workspaceId) ?? null
    ),
    findRepositoryForProject: vi.fn(
      async (projectId) => rows.find((row) => row.projectId === projectId) ?? null
    ),
    findByPath: vi.fn(async (path) => rows.filter((row) => row.path === path)),
  };
}

describe('WorkspaceIdentityService', () => {
  it('maps local and remote rows to host refs', async () => {
    const service = new WorkspaceIdentityService(createSource([localRow, remoteRow]));

    expect(await service.resolve(localRow.workspaceId)).toEqual({
      workspaceId: localRow.workspaceId,
      host: LOCAL_HOST_REF,
      path: localRow.path,
      projectId: localRow.projectId,
    });
    expect(await service.resolve(remoteRow.workspaceId)).toEqual({
      workspaceId: remoteRow.workspaceId,
      host: hostRef('remote', 'ssh-1'),
      path: remoteRow.path,
      projectId: remoteRow.projectId,
    });
  });

  it('caches by id and reverse-indexes host plus path', async () => {
    const source = createSource([remoteRow]);
    const service = new WorkspaceIdentityService(source);

    await service.resolve(remoteRow.workspaceId);
    expect(await service.resolve(remoteRow.workspaceId)).not.toBeNull();
    expect(
      await service.findByPath(remoteRow.path, hostRef('remote', remoteRow.sshConnectionId!))
    ).toMatchObject({ workspaceId: remoteRow.workspaceId });
    expect(source.findById).toHaveBeenCalledTimes(1);
    expect(source.findByPath).not.toHaveBeenCalled();
  });

  it('resolves repository identities by project id', async () => {
    const source = createSource([localRow]);
    const service = new WorkspaceIdentityService(source);

    expect(await service.resolveProject(localRow.projectId)).toMatchObject({
      workspaceId: localRow.workspaceId,
      projectId: localRow.projectId,
    });
    await service.resolveProject(localRow.projectId);

    expect(source.findRepositoryForProject).toHaveBeenCalledTimes(1);
  });

  it('retries id misses instead of caching them', async () => {
    const rows: WorkspaceIdentityRow[] = [];
    const source = createSource(rows);
    const service = new WorkspaceIdentityService(source);

    expect(await service.resolve(localRow.workspaceId)).toBeNull();
    rows.push(localRow);

    expect(await service.resolve(localRow.workspaceId)).toMatchObject({
      workspaceId: localRow.workspaceId,
    });
    expect(source.findById).toHaveBeenCalledTimes(2);
  });

  it('retries project misses instead of caching them', async () => {
    const rows: WorkspaceIdentityRow[] = [];
    const source = createSource(rows);
    const service = new WorkspaceIdentityService(source);

    expect(await service.resolveProject(localRow.projectId)).toBeNull();
    rows.push(localRow);

    expect(await service.resolveProject(localRow.projectId)).toMatchObject({
      projectId: localRow.projectId,
    });
    expect(source.findRepositoryForProject).toHaveBeenCalledTimes(2);
  });

  it('selects the same identity for an ambiguous path regardless of row or cache order', async () => {
    const remoteAtLocalPath = { ...remoteRow, path: localRow.path };
    const remoteFirst = new WorkspaceIdentityService(createSource([remoteAtLocalPath, localRow]));
    const localFirst = new WorkspaceIdentityService(createSource([localRow, remoteAtLocalPath]));

    await remoteFirst.resolve(remoteAtLocalPath.workspaceId);

    expect(await remoteFirst.findByPath(localRow.path)).toMatchObject({
      workspaceId: localRow.workspaceId,
    });
    expect(await localFirst.findByPath(localRow.path)).toMatchObject({
      workspaceId: localRow.workspaceId,
    });
    expect(
      await remoteFirst.findByPath(localRow.path, hostRef('remote', remoteRow.sshConnectionId!))
    ).toMatchObject({ workspaceId: remoteRow.workspaceId });
  });

  it('invalidates cached identities', async () => {
    const source = createSource([localRow]);
    const service = new WorkspaceIdentityService(source);
    await service.resolve(localRow.workspaceId);

    service.invalidate(localRow.workspaceId);
    await service.resolve(localRow.workspaceId);

    expect(source.findById).toHaveBeenCalledTimes(2);
  });

  it('does not silently route an invalid remote workspace to local', async () => {
    const service = new WorkspaceIdentityService(
      createSource([{ ...remoteRow, sshConnectionId: null }])
    );

    await expect(service.resolve(remoteRow.workspaceId)).rejects.toThrow(
      'Remote workspace row has no SSH connection.'
    );
  });

  it('derives host refs from canonical workspace row fields', () => {
    expect(hostRefFromParts('local', null)).toEqual(LOCAL_HOST_REF);
    expect(hostRefFromParts('remote', 'ssh-1')).toEqual(hostRef('remote', 'ssh-1'));
  });

  it('maps canonical host refs back to legacy workspace storage fields', () => {
    expect(workspaceHostStorage(LOCAL_HOST_REF)).toEqual({
      type: 'local',
      location: 'local',
      sshConnectionId: null,
    });
    expect(workspaceHostStorage(hostRef('remote', 'ssh-1'))).toEqual({
      type: 'project-ssh',
      location: 'remote',
      sshConnectionId: 'ssh-1',
    });
  });
});

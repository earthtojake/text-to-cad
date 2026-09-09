import { hostRef } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import { createProjectFromRemote } from './create-project-from-remote';

const mocks = vi.hoisted(() => ({
  createProject: vi.fn(),
  runRuntimeLiveJob: vi.fn(),
}));

vi.mock('./create-project', () => ({
  createProject: mocks.createProject,
}));

vi.mock('@core/services/runtime-clients/node/live-job', () => ({
  runRuntimeLiveJob: mocks.runRuntimeLiveJob,
}));

describe('createProjectFromRemote', () => {
  const exists = vi.fn();
  const stat = vi.fn();
  const enumerate = {};
  const deleteMutation = vi.fn();
  const cloneRepository = {};
  const client = vi.fn();

  const dependencies = {
    db: {} as never,
    runtimes: { client },
    mintCloneCredentials: vi.fn(async () => undefined),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    exists.mockResolvedValue(ok(false));
    stat.mockResolvedValue(ok({ type: 'directory' }));
    deleteMutation.mockResolvedValue(ok());
    client.mockResolvedValue(
      ok({
        files: {
          fs: { exists, stat, enumerate, delete: deleteMutation },
        },
        git: { cloneRepository },
      })
    );
    mocks.runRuntimeLiveJob.mockResolvedValue(ok({ path: hostPathFromNative('/remote/repo') }));
    mocks.createProject.mockResolvedValue(
      ok({
        type: 'ssh',
        id: 'project-1',
        name: 'repo',
        path: '/remote/repo',
        baseRef: 'main',
        connectionId: 'ssh-1',
        repositoryWorkspaceId: null,
        createdAt: '2026-01-01',
        updatedAt: '2026-01-01',
      })
    );
  });

  it('clones and registers against the SSH host runtime', async () => {
    const progress = vi.fn();
    const publish = vi.fn();
    const result = await createProjectFromRemote(
      dependencies,
      {
        projectId: 'project-1',
        host: { type: 'ssh', connectionId: 'ssh-1' },
        mode: 'clone',
        repositoryUrl: 'https://github.com/acme/repo.git',
        targetPath: '/remote/repo',
        name: 'repo',
      },
      { signal: new AbortController().signal, progress } as never,
      publish
    );

    expect(client).toHaveBeenCalledWith(hostRef('remote', 'ssh-1'));
    expect(exists).toHaveBeenCalledWith({
      path: hostPathFromNative('/remote/repo'),
    });
    expect(mocks.runRuntimeLiveJob).toHaveBeenCalledWith(
      expect.anything(),
      cloneRepository,
      expect.objectContaining({
        repositoryUrl: 'https://github.com/acme/repo.git',
        targetPath: hostPathFromNative('/remote/repo'),
      }),
      expect.any(Function),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(mocks.runRuntimeLiveJob.mock.calls[0]?.[2]).toEqual({
      repositoryUrl: 'https://github.com/acme/repo.git',
      targetPath: hostPathFromNative('/remote/repo'),
    });
    expect(mocks.createProject).toHaveBeenCalledWith(dependencies, {
      type: 'ssh',
      id: 'project-1',
      name: 'repo',
      path: '/remote/repo',
      connectionId: 'ssh-1',
    });
    expect(result).toEqual({
      success: true,
      data: expect.objectContaining({ type: 'ssh', connectionId: 'ssh-1' }),
    });
    expect(publish).toHaveBeenCalledWith('project-1', expect.objectContaining({ phase: 'ready' }));
  });

  it('reports host filesystem inspection errors without starting a clone', async () => {
    exists.mockResolvedValueOnce(err({ type: 'permission-denied', path: '/remote/repo' } as const));
    const progress = vi.fn();
    const publish = vi.fn();

    const result = await createProjectFromRemote(
      dependencies,
      {
        projectId: 'project-1',
        host: { type: 'ssh', connectionId: 'ssh-1' },
        mode: 'clone',
        repositoryUrl: 'https://github.com/acme/repo.git',
        targetPath: '/remote/repo',
        name: 'repo',
      },
      { signal: new AbortController().signal, progress } as never,
      publish
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'inspect-failed',
        message: 'permission-denied: /remote/repo',
      },
    });
    expect(mocks.runRuntimeLiveJob).not.toHaveBeenCalled();
    expect(publish).toHaveBeenCalledWith('project-1', {
      phase: 'error',
      message: 'permission-denied: /remote/repo',
      error: {
        type: 'inspect-failed',
        message: 'permission-denied: /remote/repo',
      },
    });
  });

  it('explains disabled credential prompts as missing Git authentication', async () => {
    const rawMessage =
      "fatal: could not read Username for 'https://github.com': terminal prompts disabled";
    mocks.runRuntimeLiveJob.mockResolvedValueOnce(
      err({ type: 'auth_required', message: rawMessage })
    );
    const publish = vi.fn();

    const result = await createProjectFromRemote(
      dependencies,
      {
        projectId: 'project-1',
        host: { type: 'ssh', connectionId: 'ssh-1' },
        mode: 'clone',
        repositoryUrl: 'https://github.com/acme/repo.git',
        targetPath: '/remote/repo',
        name: 'repo',
      },
      { signal: new AbortController().signal, progress: vi.fn() } as never,
      publish
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'auth_required',
        message: 'Git is not authenticated on the remote.',
      },
    });
    expect(publish).toHaveBeenCalledWith('project-1', {
      phase: 'error',
      message: 'Git is not authenticated on the remote.',
      error: {
        type: 'auth_required',
        message: 'Git is not authenticated on the remote.',
      },
    });
  });

  it.each([
    {
      failure: { type: 'auth_failed', message: 'fatal: authentication failed' },
      expected: 'Git authentication failed on the remote.',
    },
    {
      failure: { type: 'network_error', message: 'fatal: could not resolve host' },
      expected: 'Cannot reach the repository from the remote.',
    },
    {
      failure: { type: 'remote_not_found', message: 'fatal: repository not found' },
      expected: 'Repository not found or inaccessible.',
    },
    {
      failure: {
        type: 'target_exists',
        path: hostPathFromNative('/remote/repo'),
        message: 'fatal: destination path already exists',
      },
      expected: 'Clone destination is not empty: /remote/repo',
    },
  ])(
    'provides a friendly message for $failure.type clone failures',
    async ({ failure, expected }) => {
      mocks.runRuntimeLiveJob.mockResolvedValueOnce(err(failure));

      const result = await createProjectFromRemote(
        dependencies,
        {
          projectId: 'project-1',
          host: { type: 'ssh', connectionId: 'ssh-1' },
          mode: 'clone',
          repositoryUrl: 'https://github.com/acme/repo.git',
          targetPath: '/remote/repo',
          name: 'repo',
        },
        { signal: new AbortController().signal, progress: vi.fn() } as never,
        vi.fn()
      );

      expect(result).toEqual({
        success: false,
        error: { type: failure.type, message: expected },
      });
    }
  );

  it('preserves unclassified Git clone errors for diagnosis', async () => {
    const message = 'fatal: unable to write file: No space left on device';
    mocks.runRuntimeLiveJob.mockResolvedValueOnce(err({ type: 'git_error', message }));

    const result = await createProjectFromRemote(
      dependencies,
      {
        projectId: 'project-1',
        host: { type: 'local' },
        mode: 'clone',
        repositoryUrl: 'https://github.com/acme/repo.git',
        targetPath: '/local/repo',
        name: 'repo',
      },
      { signal: new AbortController().signal, progress: vi.fn() } as never,
      vi.fn()
    );

    expect(result).toEqual({
      success: false,
      error: { type: 'git_error', message },
    });
  });
});

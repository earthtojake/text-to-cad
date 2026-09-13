import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { githubRepositoryResolver } from '@core/features/github/api/node/services/github-repository-resolver';
import { ProviderRepositoryService } from './provider-repository-service';

vi.mock('@core/features/github/api/node/services/github-repository-resolver', () => ({
  githubRepositoryResolver: {
    resolve: vi.fn(),
  },
}));

const mockRepositoryResolver = vi.mocked(githubRepositoryResolver);
const mockProjectManager = { requireAttached: vi.fn() };
const loadProject = vi.fn<(projectId: string) => Promise<{ id: string } | undefined>>(async () => ({
  id: 'project-1',
}));

function mockProject(remoteState: { hasRemote: boolean; selectedRemoteUrl?: string | null }) {
  mockProjectManager.requireAttached.mockReturnValue(
    ok({
      getRemoteState: vi.fn().mockResolvedValue(remoteState),
    } as never)
  );
}

describe('ProviderRepositoryService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns no_remote when the project is missing', async () => {
    loadProject.mockResolvedValueOnce(undefined);

    await expect(
      new ProviderRepositoryService({
        projects: mockProjectManager,
        loadProject,
      }).resolveProject('project-1')
    ).resolves.toEqual(err({ type: 'project-missing', projectId: 'project-1' }));
    expect(mockProjectManager.requireAttached).not.toHaveBeenCalled();
  });

  it('preserves the typed effective-attachment error when Host access races', async () => {
    const unavailable = {
      type: 'attachment-unavailable' as const,
      host: { type: 'local' as const },
      phase: 'waiting' as const,
    };
    mockProjectManager.requireAttached.mockReturnValue(err(unavailable));

    await expect(
      new ProviderRepositoryService({
        projects: mockProjectManager,
        loadProject,
      }).resolveProject('project-1')
    ).resolves.toEqual(err(unavailable));
  });

  it('returns invalid_remote when the project has no selected remote URL', async () => {
    mockProject({ hasRemote: true, selectedRemoteUrl: '' });

    await expect(
      new ProviderRepositoryService({
        projects: mockProjectManager,
        loadProject,
      }).resolveProject('project-1')
    ).resolves.toEqual(err({ type: 'invalid_remote' }));
  });

  it('returns GitHub provider capabilities for GHES repositories', async () => {
    mockProject({ hasRemote: true, selectedRemoteUrl: 'https://ghe.example.com/acme/repo' });
    mockRepositoryResolver.resolve.mockResolvedValue(
      ok({
        host: 'ghe.example.com',
        owner: 'acme',
        repo: 'repo',
        nameWithOwner: 'acme/repo',
        repositoryUrl: 'https://ghe.example.com/acme/repo',
      })
    );

    await expect(
      new ProviderRepositoryService({
        projects: mockProjectManager,
        loadProject,
      }).resolveProject('project-1')
    ).resolves.toEqual(
      ok({
        provider: 'github',
        host: 'ghe.example.com',
        repositoryUrl: 'https://ghe.example.com/acme/repo',
        nameWithOwner: 'acme/repo',
        capabilities: {
          pullRequests: true,
          issues: true,
        },
      })
    );
  });

  it('maps unsupported providers from GitHub resolution', async () => {
    mockProject({ hasRemote: true, selectedRemoteUrl: 'https://gitlab.example.com/acme/repo' });
    mockRepositoryResolver.resolve.mockResolvedValue(
      err({ type: 'not_github', host: 'gitlab.example.com', reason: 'not GitHub' })
    );

    await expect(
      new ProviderRepositoryService({
        projects: mockProjectManager,
        loadProject,
      }).resolveProject('project-1')
    ).resolves.toEqual(
      err({ type: 'unsupported_provider', host: 'gitlab.example.com', reason: 'not GitHub' })
    );
  });
});

import { ok } from '@emdash/shared';
import type { Octokit } from '@octokit/rest';
import { describe, expect, it, vi } from 'vitest';
import { getOctokit } from './octokit-provider';
import { createGitHubRepositoryService } from './repo-service';

vi.mock('./octokit-provider', () => ({
  getOctokit: vi.fn(),
}));

const mockGetOctokit = vi.mocked(getOctokit);
const authService = {} as never;
const repoService = createGitHubRepositoryService(authService);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeOctokit(
  overrides: Partial<{
    reposListForAuthenticatedUser: ReturnType<typeof vi.fn>;
    usersGetAuthenticated: ReturnType<typeof vi.fn>;
    orgsListForAuthenticatedUser: ReturnType<typeof vi.fn>;
    reposCreateForAuthenticatedUser: ReturnType<typeof vi.fn>;
    reposCreateInOrg: ReturnType<typeof vi.fn>;
    reposDelete: ReturnType<typeof vi.fn>;
  }> = {}
): Octokit {
  return {
    rest: {
      repos: {
        listForAuthenticatedUser:
          overrides.reposListForAuthenticatedUser ?? vi.fn().mockResolvedValue({ data: [] }),
        createForAuthenticatedUser: overrides.reposCreateForAuthenticatedUser ?? vi.fn(),
        createInOrg: overrides.reposCreateInOrg ?? vi.fn(),
        delete: overrides.reposDelete ?? vi.fn().mockResolvedValue({}),
      },
      users: {
        getAuthenticated:
          overrides.usersGetAuthenticated ??
          vi.fn().mockResolvedValue({
            data: { login: 'testuser', avatar_url: 'https://avatars.githubusercontent.com/u/1' },
          }),
      },
      orgs: {
        listForAuthenticatedUser:
          overrides.orgsListForAuthenticatedUser ?? vi.fn().mockResolvedValue({ data: [] }),
      },
    },
  } as unknown as Octokit;
}

// REST-shaped mock data (snake_case)
const restRepo = {
  id: 1,
  name: 'my-repo',
  full_name: 'testuser/my-repo',
  description: 'A test repo',
  html_url: 'https://github.com/testuser/my-repo',
  clone_url: 'https://github.com/testuser/my-repo.git',
  ssh_url: 'git@github.com:testuser/my-repo.git',
  default_branch: 'main',
  private: false,
  updated_at: '2024-01-01T00:00:00Z',
  language: 'TypeScript',
  stargazers_count: 10,
  forks_count: 2,
};

// Expected camelCase output
const expectedRepo = {
  id: 1,
  name: 'my-repo',
  nameWithOwner: 'testuser/my-repo',
  description: 'A test repo',
  url: 'https://github.com/testuser/my-repo',
  cloneUrl: 'https://github.com/testuser/my-repo.git',
  sshUrl: 'git@github.com:testuser/my-repo.git',
  defaultBranch: 'main',
  isPrivate: false,
  updatedAt: '2024-01-01T00:00:00Z',
  language: 'TypeScript',
  stargazersCount: 10,
  forksCount: 2,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GitHubRepositoryServiceImpl', () => {
  describe('listRepositories', () => {
    it('maps REST response to camelCase', async () => {
      const octokit = makeOctokit({
        reposListForAuthenticatedUser: vi.fn().mockResolvedValue({ data: [restRepo] }),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      const result = await repoService.listRepositories();

      expect(result).toEqual([expectedRepo]);
    });
  });

  describe('getOwners', () => {
    it('returns user + orgs', async () => {
      const octokit = makeOctokit({
        orgsListForAuthenticatedUser: vi.fn().mockResolvedValue({
          data: [{ login: 'acme', avatar_url: 'https://avatars.githubusercontent.com/u/2' }],
        }),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      const owners = await repoService.getOwners();

      expect(owners).toEqual([
        { login: 'testuser', type: 'User', avatarUrl: 'https://avatars.githubusercontent.com/u/1' },
        {
          login: 'acme',
          type: 'Organization',
          avatarUrl: 'https://avatars.githubusercontent.com/u/2',
        },
      ]);
    });

    it('returns user only if orgs fail', async () => {
      const octokit = makeOctokit({
        orgsListForAuthenticatedUser: vi.fn().mockRejectedValue(new Error('forbidden')),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      const owners = await repoService.getOwners();

      expect(owners).toEqual([
        { login: 'testuser', type: 'User', avatarUrl: 'https://avatars.githubusercontent.com/u/1' },
      ]);
    });

    it('uses the requested GitHub account for owner lookup', async () => {
      const octokit = makeOctokit();
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.getOwners({ accountId: 'github.com:42' });

      expect(mockGetOctokit).toHaveBeenCalledWith(authService, 'github.com', {
        accountId: 'github.com:42',
      });
    });

    it('uses the selected GitHub Enterprise account host for owner lookup', async () => {
      const octokit = makeOctokit();
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.getOwners({ accountId: 'ghe.example.com:168' });

      expect(mockGetOctokit).toHaveBeenCalledWith(authService, 'ghe.example.com', {
        accountId: 'ghe.example.com:168',
      });
    });
  });

  describe('createRepository', () => {
    it('creates for authenticated user', async () => {
      const octokit = makeOctokit({
        reposCreateForAuthenticatedUser: vi.fn().mockResolvedValue({
          data: {
            html_url: 'https://github.com/testuser/new',
            clone_url: 'https://github.com/testuser/new.git',
            default_branch: 'main',
            full_name: 'testuser/new',
          },
        }),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      const result = await repoService.createRepository({
        name: 'new',
        owner: 'testuser',
        isPrivate: false,
      });

      expect(octokit.rest.repos.createForAuthenticatedUser).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'new', private: false, auto_init: true })
      );
      expect(result).toEqual({
        url: 'https://github.com/testuser/new',
        cloneUrl: 'https://github.com/testuser/new.git',
        defaultBranch: 'main',
        nameWithOwner: 'testuser/new',
      });
    });

    it('creates in org when owner differs', async () => {
      const octokit = makeOctokit({
        reposCreateInOrg: vi.fn().mockResolvedValue({
          data: {
            html_url: 'https://github.com/acme/new',
            clone_url: 'https://github.com/acme/new.git',
            default_branch: 'main',
            full_name: 'acme/new',
          },
        }),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.createRepository({ name: 'new', owner: 'acme', isPrivate: true });

      expect(octokit.rest.repos.createInOrg).toHaveBeenCalledWith(
        expect.objectContaining({ org: 'acme', name: 'new', private: true, auto_init: true })
      );
    });

    it('uses the requested GitHub account for repository creation', async () => {
      const octokit = makeOctokit({
        reposCreateForAuthenticatedUser: vi.fn().mockResolvedValue({
          data: {
            html_url: 'https://github.com/testuser/new',
            clone_url: 'https://github.com/testuser/new.git',
            default_branch: 'main',
            full_name: 'testuser/new',
          },
        }),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.createRepository({
        name: 'new',
        owner: 'testuser',
        isPrivate: false,
        authContext: { accountId: 'github.com:42' },
      });

      expect(mockGetOctokit).toHaveBeenCalledWith(authService, 'github.com', {
        accountId: 'github.com:42',
      });
    });

    it('uses the selected GitHub Enterprise account host for repository creation', async () => {
      const octokit = makeOctokit({
        reposCreateForAuthenticatedUser: vi.fn().mockResolvedValue({
          data: {
            html_url: 'https://ghe.example.com/testuser/new',
            clone_url: 'https://ghe.example.com/testuser/new.git',
            default_branch: 'main',
            full_name: 'testuser/new',
          },
        }),
      });
      mockGetOctokit.mockResolvedValue(ok(octokit));

      const result = await repoService.createRepository({
        name: 'new',
        owner: 'testuser',
        isPrivate: false,
        authContext: { accountId: 'ghe.example.com:168' },
      });

      expect(mockGetOctokit).toHaveBeenCalledWith(authService, 'ghe.example.com', {
        accountId: 'ghe.example.com:168',
      });
      expect(result.cloneUrl).toBe('https://ghe.example.com/testuser/new.git');
    });
  });

  describe('deleteRepository', () => {
    it('calls repos.delete', async () => {
      const octokit = makeOctokit();
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.deleteRepository('testuser', 'old-repo');

      expect(octokit.rest.repos.delete).toHaveBeenCalledWith({
        owner: 'testuser',
        repo: 'old-repo',
      });
    });

    it('uses the requested GitHub account for repository deletion', async () => {
      const octokit = makeOctokit();
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.deleteRepository('testuser', 'old-repo', { accountId: 'github.com:42' });

      expect(mockGetOctokit).toHaveBeenCalledWith(authService, 'github.com', {
        accountId: 'github.com:42',
      });
      expect(octokit.rest.repos.delete).toHaveBeenCalledWith({
        owner: 'testuser',
        repo: 'old-repo',
      });
    });

    it('uses the selected GitHub Enterprise account host for repository deletion', async () => {
      const octokit = makeOctokit();
      mockGetOctokit.mockResolvedValue(ok(octokit));

      await repoService.deleteRepository('testuser', 'old-repo', {
        accountId: 'ghe.example.com:168',
      });

      expect(mockGetOctokit).toHaveBeenCalledWith(authService, 'ghe.example.com', {
        accountId: 'ghe.example.com:168',
      });
    });
  });
});

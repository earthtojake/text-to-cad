import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createProjectGitHubAccountResolver,
  type ProjectGitHubAccountResolver,
} from '@core/features/github/api/node/services/project-github-account-resolver';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import type { RepoFacts, StoredProjectGitSettings } from '@core/primitives/project-settings/api';
import type { Project } from '@core/primitives/projects/api';

type FakeProject = {
  record: Project;
  stored: StoredProjectGitSettings;
  facts: RepoFacts | null;
};

class FakeProjectLookup {
  private readonly projects = new Map<string, FakeProject>();
  readonly getProjectById = vi.fn(
    async (projectId: string) => this.projects.get(projectId)?.record
  );
  readonly getStoredGitSettings = vi.fn(
    async (projectId: string) => this.projects.get(projectId)?.stored ?? {}
  );
  readonly getRepoFacts = vi.fn(
    async (project: Project) => this.projects.get(project.id)?.facts ?? null
  );

  setProject(projectId: string, project: FakeProject): void {
    this.projects.set(projectId, project);
  }
}

const GITHUB_FACTS: RepoFacts = {
  remotes: [{ name: 'origin', host: 'github.com', headBranch: 'main', branches: ['main'] }],
  localBranches: ['main'],
};

function account(overrides: Partial<GitHubAccountSummary> = {}): GitHubAccountSummary {
  return {
    accountId: 'github.com:42',
    host: 'github.com',
    login: 'octocat',
    avatarUrl: '',
    credentialSource: 'secure_storage',
    isDefault: false,
    ...overrides,
  };
}

function makeProject(
  stored: StoredProjectGitSettings = {},
  facts: RepoFacts | null = GITHUB_FACTS
): FakeProject {
  return {
    record: {
      type: 'local',
      id: 'project-1',
      name: 'Project',
      path: '/repo',
      baseRef: 'main',
      repositoryWorkspaceId: 'repository-1',
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    },
    stored,
    facts,
  };
}

describe('createProjectGitHubAccountResolver', () => {
  let projects: FakeProjectLookup;
  let accounts: GitHubAccountSummary[];
  let resolve: ProjectGitHubAccountResolver;

  beforeEach(() => {
    projects = new FakeProjectLookup();
    accounts = [];
    resolve = createProjectGitHubAccountResolver({
      getProjectById: projects.getProjectById,
      getStoredGitSettings: projects.getStoredGitSettings,
      getRepoFacts: projects.getRepoFacts,
      listAccounts: async () => accounts,
    });
  });

  it('resolves a pinned account with set provenance', async () => {
    accounts = [account()];
    projects.setProject(
      'project-1',
      makeProject({ githubAccount: { kind: 'account', accountId: 'github.com:42' } })
    );

    await expect(resolve('project-1')).resolves.toEqual({
      value: accounts[0],
      provenance: { kind: 'set' },
    });
  });

  it('resolves a durable account pin while repository facts are unavailable', async () => {
    accounts = [account()];
    projects.setProject(
      'project-1',
      makeProject({ githubAccount: { kind: 'account', accountId: 'github.com:42' } }, null)
    );

    await expect(resolve('project-1')).resolves.toEqual({
      value: accounts[0],
      provenance: { kind: 'set' },
    });
  });

  it('infers the host-matching account when no account is pinned', async () => {
    accounts = [account()];
    projects.setProject('project-1', makeProject({}));

    await expect(resolve('project-1')).resolves.toEqual({
      value: accounts[0],
      provenance: { kind: 'inferred', from: 'only host-matching account' },
    });
  });

  it('resolves null with inferred provenance when inference finds nothing', async () => {
    accounts = [account({ accountId: 'ghe.corp:7', host: 'ghe.corp' })];
    projects.setProject('project-1', makeProject({}));

    await expect(resolve('project-1')).resolves.toEqual({
      value: null,
      provenance: { kind: 'inferred', from: 'no host-matching account' },
    });
  });

  it('resolves null with set provenance for an explicit stored none', async () => {
    accounts = [account()];
    projects.setProject('project-1', makeProject({ githubAccount: { kind: 'none' } }));

    await expect(resolve('project-1')).resolves.toEqual({
      value: null,
      provenance: { kind: 'set' },
    });
  });

  it('fails closed with unresolvable provenance on a dangling account pin', async () => {
    accounts = [account()];
    projects.setProject(
      'project-1',
      makeProject({ githubAccount: { kind: 'account', accountId: 'github.com:999' } })
    );

    await expect(resolve('project-1')).resolves.toEqual({
      value: null,
      provenance: { kind: 'unresolvable' },
    });
  });

  it('fails closed with unresolvable provenance on a host-mismatched pin', async () => {
    accounts = [account({ accountId: 'ghe.corp:7', host: 'ghe.corp' })];
    projects.setProject(
      'project-1',
      makeProject({ githubAccount: { kind: 'account', accountId: 'ghe.corp:7' } })
    );

    await expect(resolve('project-1')).resolves.toEqual({
      value: null,
      provenance: { kind: 'unresolvable' },
    });
  });

  it('throws a plain invariant error for a missing durable Project', async () => {
    await expect(resolve('project-1')).rejects.toThrow('Project project-1 does not exist.');
  });

  it('propagates resolution failures instead of re-encoding them', async () => {
    projects.setProject('project-1', makeProject());
    projects.getStoredGitSettings.mockRejectedValueOnce(new Error('settings failed'));

    await expect(resolve('project-1')).rejects.toThrow('settings failed');
  });
});

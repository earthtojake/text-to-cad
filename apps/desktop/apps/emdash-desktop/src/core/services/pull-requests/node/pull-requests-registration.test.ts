import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PullRequestsRuntimeClient } from '@core/services/pull-requests/api';
import { PullRequestsRegistration } from './pull-requests-registration';

const mocks = vi.hoisted(() => ({
  projects: new Map<
    string,
    { remoteUrls: string[]; subscribeRemotes?: (handler: () => void) => () => void }
  >(),
  resolveAuth: vi.fn(),
}));

vi.mock('@emdash/shared/logger', () => ({
  log: { warn: vi.fn() },
}));

function createClient() {
  return {
    registerRepository: vi.fn(async () => ok()),
    unregisterRepository: vi.fn(async () => ok()),
    cancelSync: vi.fn(async () => ok()),
    getPullRequestsForBranch: vi.fn(async () =>
      ok({ prs: [] as Array<{ identifier: string | null }> })
    ),
    syncSingle: vi.fn(async () => ok({ pr: {} })),
  };
}

function createRegistration(client: ReturnType<typeof createClient>) {
  return new PullRequestsRegistration({
    getClient: async () => client as unknown as PullRequestsRuntimeClient,
    onProjectOpened: vi.fn(() => () => {}),
    onProjectClosed: vi.fn(() => () => {}),
    onTaskProvisioned: vi.fn(() => () => {}),
    subscribeToProjectRemotes: (projectId, handler) => {
      const project = mocks.projects.get(projectId);
      return project?.subscribeRemotes?.(handler);
    },
    resolveProjectRepositoryUrls: async (projectId) =>
      mocks.projects.get(projectId)?.remoteUrls ?? [],
    resolveProjectAuthContext: mocks.resolveAuth,
  });
}

describe('PullRequestsRegistration', () => {
  beforeEach(() => {
    mocks.projects.clear();
    mocks.resolveAuth.mockReset();
    mocks.resolveAuth.mockResolvedValue(ok({ accountId: 'account-1' }));
  });

  it('registers repositories without an account binding', async () => {
    const repositoryUrl = 'https://github.com/acme/repo';
    mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
    const client = createClient();
    const registration = createRegistration(client);

    await registration.onProjectOpened('project-1');

    expect(client.registerRepository).toHaveBeenCalledWith({ repositoryUrl });
    expect(mocks.resolveAuth).not.toHaveBeenCalled();
  });

  it('only cancels a shared repository after its last project closes', async () => {
    const repositoryUrl = 'https://github.com/acme/shared';
    mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
    mocks.projects.set('project-2', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
    const client = createClient();
    const registration = createRegistration(client);

    await registration.onProjectOpened('project-1');
    await registration.onProjectOpened('project-2');
    await registration.onProjectClosed('project-1');
    expect(client.cancelSync).not.toHaveBeenCalled();

    await registration.onProjectClosed('project-2');
    expect(client.cancelSync).toHaveBeenCalledWith({ repositoryUrl });
  });

  it('refreshes matching branch pull requests after task provisioning', async () => {
    const repositoryUrl = 'https://github.com/acme/repo';
    mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
    const client = createClient();
    client.getPullRequestsForBranch.mockResolvedValue(ok({ prs: [{ identifier: '#42' }] }));
    const registration = createRegistration(client);

    await registration.onProjectOpened('project-1');
    await registration.onTaskProvisioned('project-1', 'feature-branch');

    expect(client.getPullRequestsForBranch).toHaveBeenCalledWith({
      repositoryUrl,
      branch: 'feature-branch',
    });
    expect(client.syncSingle).toHaveBeenCalledWith({ repositoryUrl, number: 42 });
  });

  it('does not subscribe or register repositories when a project has no repository', async () => {
    mocks.projects.set('project-1', { remoteUrls: [] });
    const client = createClient();
    const registration = createRegistration(client);

    await registration.onProjectOpened('project-1');

    expect(client.registerRepository).not.toHaveBeenCalled();
  });

  it('unregisters repositories when their project is deleted', async () => {
    const repositoryUrl = 'https://github.com/acme/deleted';
    mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
    const client = createClient();
    const registration = createRegistration(client);

    await registration.onProjectOpened('project-1');
    await registration.deleteProjectData('project-1');

    expect(client.unregisterRepository).toHaveBeenCalledWith({ repositoryUrl });
  });

  describe('resolveSyncIdentity', () => {
    it('resolves the effective account of an open project at request time', async () => {
      const repositoryUrl = 'https://github.com/acme/repo';
      mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
      const registration = createRegistration(createClient());
      await registration.onProjectOpened('project-1');

      await expect(registration.resolveSyncIdentity(repositoryUrl)).resolves.toEqual(
        ok({ accountId: 'account-1' })
      );

      // An account change is visible on the very next request — no event plumbing.
      mocks.resolveAuth.mockResolvedValue(ok({ accountId: 'account-2' }));
      await expect(registration.resolveSyncIdentity(repositoryUrl)).resolves.toEqual(
        ok({ accountId: 'account-2' })
      );
    });

    it('fails closed when no open project references the repository', async () => {
      const registration = createRegistration(createClient());

      await expect(
        registration.resolveSyncIdentity('https://github.com/acme/unknown')
      ).resolves.toEqual(
        err({
          type: 'account_unresolvable',
          host: 'github.com',
          message: 'No open project references this repository.',
        })
      );
      expect(mocks.resolveAuth).not.toHaveBeenCalled();
    });

    it('fails closed on an unresolvable account pin, never a fallback identity', async () => {
      const repositoryUrl = 'https://github.com/acme/repo';
      mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
      mocks.resolveAuth.mockResolvedValue(
        err({
          type: 'account_selection_failed',
          message: 'The pinned GitHub account no longer exists.',
        })
      );
      const registration = createRegistration(createClient());
      await registration.onProjectOpened('project-1');

      await expect(registration.resolveSyncIdentity(repositoryUrl)).resolves.toEqual(
        err({
          type: 'account_unresolvable',
          host: 'github.com',
          message: 'The pinned GitHub account no longer exists.',
        })
      );
    });

    it('maps an explicitly disabled account to a quiet disabled status', async () => {
      const repositoryUrl = 'https://github.com/acme/repo';
      mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
      mocks.resolveAuth.mockResolvedValue(
        err({ type: 'disabled', message: 'GitHub API is disabled for this project.' })
      );
      const registration = createRegistration(createClient());
      await registration.onProjectOpened('project-1');

      await expect(registration.resolveSyncIdentity(repositoryUrl)).resolves.toEqual(
        err({
          type: 'github_disabled',
          host: 'github.com',
          message: 'GitHub API is disabled for this project.',
        })
      );
    });

    it('maps a missing account inference to a connect prompt', async () => {
      const repositoryUrl = 'https://github.com/acme/repo';
      mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
      mocks.resolveAuth.mockResolvedValue(
        err({ type: 'unconfigured', message: 'No connected GitHub account matches this project.' })
      );
      const registration = createRegistration(createClient());
      await registration.onProjectOpened('project-1');

      await expect(registration.resolveSyncIdentity(repositoryUrl)).resolves.toEqual(
        err({
          type: 'auth_required',
          host: 'github.com',
          message: 'No connected GitHub account matches this project.',
          hint: 'Connect a GitHub account from settings.',
        })
      );
    });

    it('uses the first referencing project that resolves an account', async () => {
      const repositoryUrl = 'https://github.com/acme/shared';
      mocks.projects.set('project-1', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
      mocks.projects.set('project-2', { remoteUrls: [repositoryUrl], subscribeRemotes: vi.fn() });
      const registration = createRegistration(createClient());
      await registration.onProjectOpened('project-1');
      await registration.onProjectOpened('project-2');
      mocks.resolveAuth
        .mockResolvedValueOnce(err({ type: 'account_selection_failed', message: 'Broken pin.' }))
        .mockResolvedValueOnce(ok({ accountId: 'account-2' }));

      await expect(registration.resolveSyncIdentity(repositoryUrl)).resolves.toEqual(
        ok({ accountId: 'account-2' })
      );
    });
  });
});

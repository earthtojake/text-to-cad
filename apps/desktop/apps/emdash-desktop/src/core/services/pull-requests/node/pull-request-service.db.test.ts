import { err, ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { requestPriorities } from '@emdash/shared/requests';
import { createStubLogger } from '@emdash/shared/testing';
import type { ContractClient } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import type { GitHubAuthContract, PullRequest } from '../api';
import type { PullRequestEngine } from './engine';
import { PullRequestService } from './pull-request-service';
import { PullRequestStore, pullRequestSqliteStore } from './store';

describe('PullRequestService lifecycle', () => {
  it('cancels and settles scoped syncs before closing the database', async () => {
    const scope = createScope({ label: 'pull-request-service-test' });
    const handle = await pullRequestSqliteStore.openTemp();
    scope.add(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    let started = false;
    let databaseOpenDuringCancellation = false;
    const engine = {
      sync: async (_repositoryUrl: string, signal: AbortSignal) =>
        await new Promise((resolve) => {
          started = true;
          signal.addEventListener(
            'abort',
            () => {
              databaseOpenDuringCancellation =
                handle.connection.get<{ value: number }>('SELECT 1 AS value')?.value === 1;
              resolve(err({ type: 'sync_failed', message: 'cancelled' }));
            },
            { once: true }
          );
        }),
    } as unknown as PullRequestEngine;
    const { logger } = createStubLogger();
    const service = new PullRequestService({
      store,
      githubAuth: fakeGitHubAuth(),
      scope,
      logger,
      engine,
    });
    service.registerRepository(repositoryUrl);

    const sync = service.sync(repositoryUrl);
    await vi.waitFor(() => expect(started).toBe(true));
    await scope.dispose();
    await expect(sync).resolves.toEqual(
      err({ type: 'sync_failed', message: 'Pull request sync cancelled' })
    );
    expect(databaseOpenDuringCancellation).toBe(true);
    expect(() => handle.connection.get('SELECT 1')).toThrow();
  });

  it('settles scoped RPC operations before closing the database', async () => {
    const scope = createScope({ label: 'pull-request-operation-test' });
    const handle = await pullRequestSqliteStore.openTemp();
    scope.add(() => handle.close());
    const store = new PullRequestStore(handle);
    const { logger } = createStubLogger();
    const service = new PullRequestService({
      store,
      githubAuth: fakeGitHubAuth(),
      scope,
      logger,
      engine: {} as PullRequestEngine,
    });
    let started = false;
    let databaseOpenDuringCancellation = false;
    const operation = service.runOperation('test', undefined, async (signal) => {
      started = true;
      await new Promise<void>((resolve) =>
        signal.addEventListener(
          'abort',
          () => {
            databaseOpenDuringCancellation =
              handle.connection.get<{ value: number }>('SELECT 1 AS value')?.value === 1;
            resolve();
          },
          { once: true }
        )
      );
      return ok();
    });

    await vi.waitFor(() => expect(started).toBe(true));
    await scope.dispose();

    await expect(operation).rejects.toThrow();
    expect(databaseOpenDuringCancellation).toBe(true);
    expect(() => handle.connection.get('SELECT 1')).toThrow();
  });

  it('refreshes the derived store after GitHub mutations', async () => {
    const scope = createScope({ label: 'pull-request-mutation-test' });
    const handle = await pullRequestSqliteStore.openTemp();
    scope.add(() => handle.close());
    const store = new PullRequestStore(handle);
    const syncSingle = vi.fn(async () => ok({}));
    const engine = {
      createPullRequest: vi.fn(async () =>
        ok({ url: 'https://github.com/emdash/emdash/pull/42', number: 42 })
      ),
      mergePullRequest: vi.fn(async () => ok({ sha: 'abc', merged: true })),
      markReadyForReview: vi.fn(async () => ok()),
      syncSingle,
    } as unknown as PullRequestEngine;
    const { logger } = createStubLogger();
    const service = new PullRequestService({
      store,
      githubAuth: fakeGitHubAuth(),
      scope,
      logger,
      engine,
    });
    const repositoryUrl = 'https://github.com/emdash/emdash';

    await service.createPullRequest(
      {
        repositoryUrl,
        title: 'Created PR',
        head: 'feature',
        base: 'main',
        body: '',
        draft: false,
      },
      new AbortController().signal
    );
    await service.mergePullRequest(
      repositoryUrl,
      42,
      { strategy: 'merge' },
      new AbortController().signal
    );
    await service.markReadyForReview(repositoryUrl, 42, new AbortController().signal);

    expect(syncSingle).toHaveBeenCalledTimes(3);
    expect(syncSingle).toHaveBeenCalledWith(repositoryUrl, 42, expect.any(AbortSignal), {
      emit: false,
    });
    await scope.dispose();
  });

  it('starts sync on registration and skips fresh incremental syncs', async () => {
    const scope = createScope({ label: 'pull-request-staleness-test' });
    const handle = await pullRequestSqliteStore.openTemp();
    scope.add(() => handle.close());
    const store = new PullRequestStore(handle);
    const sync = vi.fn(async () => ok());
    const forceFullSync = vi.fn(async () => ok());
    const engine = { sync, forceFullSync } as unknown as PullRequestEngine;
    const { logger } = createStubLogger();
    const service = new PullRequestService({
      store,
      githubAuth: fakeGitHubAuth(),
      scope,
      logger,
      engine,
      minSyncIntervalMs: 60_000,
    });
    const repositoryUrl = 'https://github.com/emdash/emdash';

    expect(service.registerRepository(repositoryUrl)).toEqual(ok());
    await vi.waitFor(() => expect(sync).toHaveBeenCalledTimes(1));
    expect(sync).toHaveBeenCalledWith(
      repositoryUrl,
      expect.any(AbortSignal),
      requestPriorities.background
    );
    await expect(service.sync(repositoryUrl)).resolves.toEqual(ok());
    expect(sync).toHaveBeenCalledTimes(1);

    await expect(service.forceFullSync(repositoryUrl)).resolves.toEqual(ok());
    expect(forceFullSync).toHaveBeenCalledTimes(1);
    expect(forceFullSync).toHaveBeenCalledWith(
      repositoryUrl,
      expect.any(AbortSignal),
      requestPriorities.task
    );
    await scope.dispose();
  });

  it('validates canonical PR URLs against the cache scoped to one repository', async () => {
    const scope = createScope({ label: 'pull-request-by-url-test' });
    const handle = await pullRequestSqliteStore.openTemp();
    scope.add(() => handle.close());
    const store = new PullRequestStore(handle);
    const { logger } = createStubLogger();
    const service = new PullRequestService({
      store,
      githubAuth: fakeGitHubAuth(),
      scope,
      logger,
      engine: {} as PullRequestEngine,
    });
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const otherRepositoryUrl = 'https://github.com/other/project';
    service.registerRepository(repositoryUrl);
    const pr = store.savePullRequest(pullRequestFixture({ url: `${repositoryUrl}/pull/42` }));

    expect(service.getPullRequestByUrl(repositoryUrl, pr.url)).toEqual(ok({ pr }));
    // Normalization applies to the repository scope, not the opaque cache key.
    expect(service.getPullRequestByUrl(`${repositoryUrl}.git`, pr.url)).toEqual(ok({ pr }));
    // Unknown URLs are ordinary misses — the association layer falls back silently.
    expect(service.getPullRequestByUrl(repositoryUrl, `${repositoryUrl}/pull/9999`)).toEqual(
      ok({ pr: null })
    );
    // A cached PR is invisible through another repository's scope.
    expect(service.getPullRequestByUrl(otherRepositoryUrl, pr.url)).toEqual(ok({ pr: null }));
    // Unregistered repositories validate nothing (mirrors getPullRequestsForBranch).
    await service.unregisterRepository(repositoryUrl);
    expect(service.getPullRequestByUrl(repositoryUrl, pr.url)).toEqual(ok({ pr: null }));
    expect(service.getPullRequestByUrl('not a repository', pr.url)).toEqual(
      err({ type: 'invalid_repository', input: 'not a repository' })
    );
    await scope.dispose();
  });

  it('keeps a successful mutation result when its derived refresh fails', async () => {
    const scope = createScope({ label: 'pull-request-refresh-failure-test' });
    const handle = await pullRequestSqliteStore.openTemp();
    scope.add(() => handle.close());
    const store = new PullRequestStore(handle);
    const engine = {
      mergePullRequest: vi.fn(async () => ok({ sha: 'abc', merged: true })),
      syncSingle: vi.fn(async () =>
        err({ type: 'refresh_failed' as const, message: 'Refresh failed' })
      ),
    } as unknown as PullRequestEngine;
    const { logger, calls } = createStubLogger();
    const service = new PullRequestService({
      store,
      githubAuth: fakeGitHubAuth(),
      scope,
      logger,
      engine,
    });
    const repositoryUrl = 'https://github.com/emdash/emdash';

    await expect(
      service.mergePullRequest(
        repositoryUrl,
        42,
        { strategy: 'merge' },
        new AbortController().signal
      )
    ).resolves.toEqual(ok({ sha: 'abc', merged: true }));
    expect(calls).toContainEqual({
      level: 'warn',
      message: 'Pull request refresh failed after mutation',
      fields: {
        repositoryUrl,
        number: 42,
        error: { type: 'refresh_failed', message: 'Refresh failed' },
      },
    });
    await scope.dispose();
  });
});

function pullRequestFixture(overrides: Partial<PullRequest> = {}): PullRequest {
  const repositoryUrl = 'https://github.com/emdash/emdash';
  return {
    url: `${repositoryUrl}/pull/1`,
    provider: 'github',
    repositoryUrl,
    baseRefName: 'main',
    baseRefOid: 'base',
    headRepositoryUrl: repositoryUrl,
    headRefName: 'feature',
    headRefOid: 'head',
    identifier: '#1',
    title: 'Feature',
    description: null,
    status: 'open',
    isDraft: false,
    additions: 10,
    deletions: 2,
    changedFiles: 1,
    commitCount: 1,
    mergeableStatus: 'MERGEABLE',
    mergeStateStatus: 'CLEAN',
    reviewDecision: null,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-02T00:00:00.000Z',
    author: null,
    labels: [],
    assignees: [],
    checks: [],
    ...overrides,
  };
}

function fakeGitHubAuth(): ContractClient<GitHubAuthContract> {
  return {
    resolveAuth: async () =>
      ok({
        token: 'test-token',
        host: 'github.com',
        apiBaseUrl: 'https://api.github.com',
      }),
  };
}

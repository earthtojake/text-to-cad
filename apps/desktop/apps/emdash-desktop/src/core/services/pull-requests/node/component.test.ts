import { err, ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { createController } from '@emdash/wire/rpc';
import { FakeWorkerProcessSpawner } from '@emdash/wire/testing';
import { createWireWorkerHost, runWireComponentWorker } from '@emdash/wire/worker';
import { describe, expect, it } from 'vitest';
import { githubAuthContract } from '../api';
import { pullRequestsComponent } from './component';

const githubAuthController = createController(githubAuthContract, {
  resolveAuth: () =>
    err({
      type: 'auth_required',
      host: 'github.com',
      message: 'GitHub authentication required',
      hint: 'Connect GitHub',
    }),
});

describe('pullRequestsComponent', () => {
  it('runs in process with full validation and its private database', async () => {
    const scope = createScope({ label: 'pull-requests-test' });
    const component = pullRequestsComponent.create({
      scope,
      dependencies: {
        githubAuth: {
          resolveAuth: async () =>
            err({
              type: 'auth_required',
              host: 'github.com',
              message: 'GitHub authentication required',
              hint: 'Connect GitHub',
            }),
        },
      },
      config: { databasePath: ':memory:' },
    });
    const repositoryUrl = 'https://github.com/emdash/emdash';

    await expect(component.client.registerRepository({ repositoryUrl })).resolves.toEqual(ok());
    await expect(
      component.client.listPullRequests({
        repositoryUrls: [repositoryUrl],
        cursor: null,
        limit: 10,
      })
    ).resolves.toEqual(ok({ prs: [], nextCursor: null }));
    await component.dispose();
  });

  it('boots through WorkerHost and forwards the GitHub auth dependency', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'pull-requests-worker-test' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner });
    const worker = host.create(pullRequestsComponent, {
      executable: 'pull-requests-worker',
      dependencies: { githubAuth: githubAuthController },
      config: { databasePath: ':memory:' },
      shutdownGraceMs: 0,
    });

    const ready = worker.ready();
    await flush();
    void runWireComponentWorker(pullRequestsComponent, {
      port: spawner.latest().childPort,
      exit: () => {},
    });
    const client = await ready;
    const repositoryUrl = 'https://github.com/emdash/emdash';
    await expect(client.registerRepository({ repositoryUrl })).resolves.toEqual(ok());
    await expect(client.sync({ repositoryUrl })).resolves.toEqual(
      err({
        type: 'github_auth_required',
        host: 'github.com',
        hint: 'Connect GitHub',
      })
    );
    await expect(
      client.listPullRequests({ repositoryUrls: [repositoryUrl], cursor: null, limit: 10 })
    ).resolves.toEqual(ok({ prs: [], nextCursor: null }));

    await host.dispose();
  });
});

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

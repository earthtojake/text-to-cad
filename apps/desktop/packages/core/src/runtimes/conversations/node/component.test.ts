import { createScope } from '@emdash/shared/concurrency';
import { FakeWorkerProcessSpawner } from '@emdash/wire/testing';
import { createWireWorkerHost, runWireComponentWorker } from '@emdash/wire/worker';
import { describe, expect, it } from 'vitest';
import { conversationsComponent, conversationsComponentConfigSchema } from './component';

// The conversations component is the sole writer of its own database (conv.sole-writer):
// it takes no dependencies and owns the SQLite file it is configured with (spec §3.4).

const createInput = {
  conversationId: 'conv-worker-1',
  provider: 'claude-code',
  type: 'acp' as const,
  cwd: '/work/repo',
  workspacePath: '/work/repo',
  idRegime: 'provider-minted' as const,
  createdAt: 1_000,
  title: 'Worker conversation',
  config: {},
};

describe('conversationsComponent', () => {
  it('rejects relative database paths', () => {
    expect(
      conversationsComponentConfigSchema.safeParse({ databasePath: 'relative.db' }).success
    ).toBe(false);
    expect(conversationsComponentConfigSchema.safeParse({ databasePath: ':memory:' }).success).toBe(
      true
    );
    expect(
      conversationsComponentConfigSchema.safeParse({ databasePath: '/abs/path.db' }).success
    ).toBe(true);
  });

  it('runs in process with full validation and its private database', async () => {
    const scope = createScope({ label: 'conversations-test' });
    const component = conversationsComponent.create({
      scope,
      dependencies: {},
      config: { databasePath: ':memory:' },
    });

    const created = await component.client.create(createInput);
    expect(created.success).toBe(true);
    await component.dispose();
  });

  it('boots through WorkerHost as its own worker', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'conversations-worker-test' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner });
    const worker = host.create(conversationsComponent, {
      executable: 'conversations-worker',
      dependencies: {},
      config: { databasePath: ':memory:' },
      shutdownGraceMs: 0,
    });

    const ready = worker.ready();
    await flush();
    void runWireComponentWorker(conversationsComponent, {
      port: spawner.latest().childPort,
      exit: () => {},
    });
    const client = await ready;

    const created = await client.create(createInput);
    expect(created).toMatchObject({ success: true, data: { conversationId: 'conv-worker-1' } });
    const replay = await client.create(createInput);
    expect(replay).toEqual(created);

    await host.dispose();
  });
});

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

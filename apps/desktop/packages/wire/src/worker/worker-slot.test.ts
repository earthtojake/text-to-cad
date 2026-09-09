import { createScope } from '@emdash/shared/concurrency';
import { retrySchedules } from '@emdash/shared/scheduling';
import { createManualClock, createStubLogger } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { defineContract, procedure } from '../api/define';
import { createController } from '../rpc/controller';
import { FakeWorkerProcessSpawner } from '../testing';
import { defineWireComponent, requireContract } from './component';
import { createWireWorkerHost } from './host';
import { runWireComponentWorker } from './run-component-worker';
import { WORKER_NAME_ENV_VAR, type WorkerParentPort } from './types';

const api = defineContract({
  ping: procedure({ input: z.string(), output: z.string() }),
});

const apiComponent = defineWireComponent({
  id: 'demo',
  contract: api,
  requirements: {},
  configSchema: z.object({}),
  create: ({ instance, scope }) =>
    instance({
      scope,
      controller: createController(api, {
        ping: (input) => `pong:${input}`,
      }),
    }),
});

const dependencyApi = defineContract({
  suffix: procedure({ input: z.string(), output: z.string() }),
});

describe('WireWorkerHost and WorkerSlot', () => {
  it('lazily starts a worker and keeps a stable client', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner });
    const worker = host.create(apiComponent, {
      name: 'demo',
      executable: 'worker',
      dependencies: {},
      config: {},
      shutdownGraceMs: 0,
    });

    expect('client' in worker).toBe(false);

    const ready = worker.ready();
    await flush();
    void startChild(spawner.latest());
    const firstClient = await ready;
    const secondClient = await worker.ready();

    await expect(firstClient.ping('one')).resolves.toBe('pong:one');
    expect(secondClient).toBe(firstClient);

    await host.dispose();
  });

  it('injects the worker name into the spawned process environment', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner });
    const worker = host.create(apiComponent, {
      name: 'custom-demo',
      executable: 'worker',
      env: {
        EXISTING_VALUE: 'preserved',
        [WORKER_NAME_ENV_VAR]: 'overridden',
      },
      dependencies: {},
      config: {},
      shutdownGraceMs: 0,
    });

    const ready = worker.ready();
    await flush();
    expect(spawner.latest().spec.env).toEqual({
      EXISTING_VALUE: 'preserved',
      [WORKER_NAME_ENV_VAR]: 'custom-demo',
    });
    void startChild(spawner.latest());
    await ready;

    await host.dispose();
  });

  it('restarts failed generations without replacing the public client', async () => {
    const clock = createManualClock();
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner, clock });
    const worker = host.create(apiComponent, {
      name: 'demo',
      executable: 'worker',
      dependencies: {},
      config: {},
      shutdownGraceMs: 0,
      supervision: {
        restart: 'on-failure',
        schedule: retrySchedules.sequence([0]),
      },
    });

    const ready = worker.ready();
    await flush();
    void startChild(spawner.latest());
    const firstClient = await ready;
    const previousGeneration = worker.state.kind === 'ready' ? worker.state.generation : 0;
    spawner.latest().emitExit({ code: 1 });
    await clock.runAll();
    await waitFor(() => spawner.processes.length === 2);
    void startChild(spawner.latest());
    await waitFor(
      () => worker.state.kind === 'ready' && worker.state.generation > previousGeneration
    );

    expect(await worker.ready()).toBe(firstClient);
    await expect(firstClient.ping('two')).resolves.toBe('pong:two');
    expect(spawner.processes).toHaveLength(2);

    await host.dispose();
  });

  it('fails startup when the retry schedule is exhausted', async () => {
    const clock = createManualClock();
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner, clock });
    const worker = host.create(apiComponent, {
      name: 'demo',
      executable: 'worker',
      dependencies: {},
      config: {},
      shutdownGraceMs: 0,
      supervision: {
        restart: 'on-failure',
        schedule: retrySchedules.sequence([]),
      },
    });

    const pending = worker.ready();
    await flush();
    spawner.latest().emitExit({ code: 1 });

    await expect(pending).rejects.toThrow('Worker exited before ready');
    expect(worker.state.kind).toBe('failed');
    await host.dispose();
  });

  it('starts workers explicitly and reports structured runtime logs', async () => {
    const { logger, calls } = createStubLogger();
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root', logger });

    const worker = createWireWorkerHost({ scope, processSpawner: spawner, logger }).create(
      apiComponent,
      {
        name: 'demo',
        executable: 'worker',
        dependencies: {},
        config: {},
        shutdownGraceMs: 0,
      }
    );

    scope.run(
      'start-demo',
      async () => {
        await worker.ready();
      },
      { onFailure: 'report' }
    );
    await flush();
    void startChild(spawner.latest());
    await flush();
    spawner.latest().emitStdio('stderr', '{"level":"info","proc":"demo","msg":"child ready"}\n');

    expect(calls).toContainEqual({
      level: 'info',
      message: 'child ready',
      fields: { worker: 'demo', source: 'demo-runtime', proc: 'demo' },
    });
    await scope.dispose();
  });

  it('stops back to idle and can be started again', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner });
    const worker = host.create(apiComponent, {
      name: 'demo',
      executable: 'worker',
      dependencies: {},
      config: {},
      shutdownGraceMs: 0,
    });

    const firstReady = worker.ready();
    await flush();
    void startChild(spawner.latest());
    await firstReady;
    expect(worker.state.kind).toBe('ready');

    await worker.stop();
    expect(worker.state.kind).toBe('idle');
    const firstClient = await firstReady;
    // A call issued while stopped is held until the worker comes back.
    const heldPing = firstClient.ping('stopped');

    const secondReady = worker.ready();
    await waitFor(() => spawner.processes.length === 2);
    void startChild(spawner.latest());
    const secondClient = await secondReady;
    await expect(heldPing).resolves.toBe('pong:stopped');
    await expect(secondClient.ping('again')).resolves.toBe('pong:again');

    await host.dispose();
    expect(worker.state.kind).toBe('disposed');
  });

  it('spawns a component worker with explicit bridged dependencies', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const scope = createScope({ label: 'root' });
    const host = createWireWorkerHost({ scope, processSpawner: spawner });
    const component = defineWireComponent({
      id: 'demo-component',
      contract: api,
      requirements: {
        dependency: requireContract(dependencyApi),
      },
      configSchema: z.object({ prefix: z.string() }),
      create: ({ config, dependencies, instance, scope }) =>
        instance({
          scope,
          controller: createController(api, {
            ping: async (input) =>
              `${config.prefix}:${await dependencies.dependency.suffix(input)}`,
          }),
        }),
    });
    const dependencyController = createController(dependencyApi, {
      suffix: (input) => `dep:${input}`,
    });

    const worker = host.create(component, {
      executable: 'worker',
      dependencies: {
        dependency: dependencyController,
      },
      config: { prefix: 'component' },
      shutdownGraceMs: 0,
    });

    const ready = worker.ready();
    await flush();
    void runWireComponentWorker(component, {
      port: spawner.latest().childPort,
      exit: () => {},
    });
    const client = await ready;

    await expect(client.ping('one')).resolves.toBe('component:dep:one');

    await host.dispose();
  });
});

async function startChild(process: { childPort: WorkerParentPort }) {
  await runWireComponentWorker(apiComponent, { port: process.childPort, exit: () => {} });
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await flush();
    if (predicate()) return;
  }
  throw new Error('Timed out waiting for condition');
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

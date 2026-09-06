import { err, ok, type Result } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { retrySchedules } from '@emdash/shared/scheduling';
import { createTestWire, FakeWorkerProcessSpawner } from '@emdash/wire/testing';
import { defineWireComponent } from '@emdash/wire/worker';
import {
  createWireWorkerHost,
  isWorkerSignal,
  runWireComponentWorker,
  type WorkerParentPort,
  type WorkerSupervision,
} from '@emdash/wire/worker';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import {
  fsWatchContract,
  requireWatchReady,
  type IWatchService,
  type WatchEvent,
  type WatchHandle,
  type WatchOptions,
} from '#services/fs-watch/api';
import { fsWatchComponent } from '#services/fs-watch/node/component';
import { createFsWatchController } from './controller';
import { processWatchBackend } from './process-backend';
import { createWatchService } from './watch-service';

describe('processWatchBackend', () => {
  it('waits for the child watcher ready event before resolving watch readiness', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const childService = new FakeWatchService();
    const scope = createScope({ label: 'test' });
    const service = createProcessWatchService({
      scope,
      processSpawner: spawner,
      supervision: {
        restart: 'on-failure',
        schedule: retrySchedules.sequence([0]),
      },
    });

    const readyStates: string[] = [];
    const handle = service.watch('/tmp/project', () => {});
    const ready = requireWatchReady(handle).then(() => readyStates.push('ready'));
    await waitFor(() => spawner.processes.length === 1);
    await startChild(spawner.latest(), childService);
    await flush();

    expect(readyStates).toEqual([]);
    await waitFor(() => childService.watches.length === 1);
    childService.latest().readyDeferred.resolve(ok(undefined));
    await ready;
    expect(readyStates).toEqual(['ready']);

    await handle.release();
    await service.dispose();
  });

  it('resyncs after a worker reconnect only when the native watcher reports ready again', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const childService = new FakeWatchService();
    const scope = createScope({ label: 'test' });
    const service = createProcessWatchService({
      scope,
      processSpawner: spawner,
      supervision: {
        restart: 'on-failure',
        schedule: retrySchedules.sequence([0]),
      },
    });
    const resyncs: string[] = [];

    const handle = service.watch('/tmp/project', () => {}, {
      onResync: () => resyncs.push('resync'),
    });
    const ready = requireWatchReady(handle);
    await waitFor(() => spawner.processes.length === 1);
    await startChild(spawner.latest(), childService);
    await waitFor(() => childService.watches.length === 1);
    childService.latest().readyDeferred.resolve(ok(undefined));
    await ready;

    spawner.latest().emitExit({ code: 1 });
    await waitFor(() => spawner.processes.length === 2);
    await startChild(spawner.latest(), childService);
    await flush();

    expect(resyncs).toEqual([]);
    await waitFor(() => childService.watches.length === 2);
    childService.latest().readyDeferred.resolve(ok(undefined));
    await waitFor(() => resyncs.length === 1);
    expect(resyncs).toEqual(['resync']);

    await handle.release();
    await service.dispose();
  });

  it('makes two consumers on the same connection ready from one activation', async () => {
    const spawner = new FakeWorkerProcessSpawner();
    const childService = new FakeWatchService();
    const scope = createScope({ label: 'test' });
    const workerHost = createWireWorkerHost({
      scope: scope.child('fs-watch-worker-host'),
      processSpawner: spawner,
    });
    const worker = workerHost.create(fsWatchComponent, {
      name: 'fs-watch',
      executable: 'worker',
      dependencies: {},
      config: {},
      supervision: { restart: 'never' },
    });
    const backend = processWatchBackend({ client: () => worker.ready() });
    const firstService = createWatchService({ backend, scope });
    const secondService = createWatchService({ backend, scope });
    const first = firstService.watch('/tmp/project', () => {});
    const second = secondService.watch('/tmp/project', () => {});

    await waitFor(() => spawner.processes.length === 1);
    await startChild(spawner.latest(), childService);
    await waitFor(() => childService.watches.length === 1);
    childService.latest().readyDeferred.resolve(ok(undefined));

    await expect(Promise.all([first.ready(), second.ready()])).resolves.toEqual([
      ok(undefined),
      ok(undefined),
    ]);
    expect(childService.watches).toHaveLength(1);

    await first.release();
    await second.release();
    await firstService.dispose();
    await secondService.dispose();
    await scope.dispose();
  });

  it('makes consumers on separate connections ready from one activation', async () => {
    const service = new FakeWatchService();
    const scope = createScope({ label: 'test' });
    const controller = createFsWatchController({ scope, service });
    const firstWire = createTestWire(fsWatchContract, controller);
    const secondWire = createTestWire(fsWatchContract, controller);
    const key = { root: '/tmp/project', ignore: [] };

    const firstSubscription = firstWire.client.events.subscribe(key, { onEvent: () => {} });
    const secondSubscription = secondWire.client.events.subscribe(key, { onEvent: () => {} });
    await waitFor(() => service.watches.length === 1);
    service.latest().readyDeferred.resolve(ok(undefined));

    const [first, second] = await Promise.all([firstSubscription, secondSubscription]);
    expect(service.watches).toHaveLength(1);

    first();
    second();
    firstWire.dispose();
    secondWire.dispose();
    await scope.dispose();
    expect(service.latest().released).toBe(true);
  });

  it('rejects attach when watcher startup fails', async () => {
    const service = new FakeWatchService();
    const scope = createScope({ label: 'test' });
    const controller = createFsWatchController({ scope, service });
    const wire = createTestWire(fsWatchContract, controller);
    const subscription = wire.client.events.subscribe(
      { root: '/tmp/project', ignore: [] },
      { onEvent: () => {} }
    );

    await waitFor(() => service.watches.length === 1);
    service.latest().readyDeferred.resolve(err(new Error('native startup failed')));

    await expect(subscription).rejects.toThrow('native startup failed');
    expect(service.latest().released).toBe(true);

    wire.dispose();
    await scope.dispose();
  });
});

function createProcessWatchService({
  scope,
  processSpawner,
  supervision,
}: {
  scope: ReturnType<typeof createScope>;
  processSpawner: FakeWorkerProcessSpawner;
  supervision: WorkerSupervision;
}): IWatchService {
  const workerHost = createWireWorkerHost({
    scope: scope.child('fs-watch-worker-host'),
    processSpawner,
  });
  const worker = workerHost.create(fsWatchComponent, {
    name: 'fs-watch',
    executable: 'worker',
    dependencies: {},
    config: {},
    supervision,
  });
  return createWatchService({
    backend: processWatchBackend({
      client: () => worker.ready(),
    }),
    scope,
    graceMs: 2_500,
  });
}

async function startChild(
  process: { childPort: WorkerParentPort; childMessages: unknown[] },
  service: IWatchService
): Promise<void> {
  void runWireComponentWorker(
    defineWireComponent({
      id: 'fs-watch',
      contract: fsWatchContract,
      requirements: {},
      configSchema: z.object({}),
      create: ({ instance, scope }) =>
        instance({
          scope,
          controller: createFsWatchController({
            scope,
            service,
          }),
        }),
    }),
    { port: process.childPort, exit: () => {} }
  );
  await waitFor(() => process.childMessages.some((message) => isWorkerSignal(message, 'ready')));
}

class FakeWatchService implements IWatchService {
  readonly watches: FakeWatch[] = [];

  watch(
    root: string,
    onEvents: (events: WatchEvent[]) => void,
    options?: WatchOptions
  ): WatchHandle {
    const watch = new FakeWatch(root, onEvents, options);
    this.watches.push(watch);
    return watch;
  }

  latest(): FakeWatch {
    const watch = this.watches.at(-1);
    if (!watch) throw new Error('No fake watch started');
    return watch;
  }

  async dispose(): Promise<void> {}
}

class FakeWatch implements WatchHandle {
  readonly readyDeferred = createDeferred<Result<void, unknown>>();
  released = false;

  constructor(
    readonly root: string,
    readonly onEvents: (events: WatchEvent[]) => void,
    readonly options?: WatchOptions
  ) {}

  ready(): Promise<Result<void, unknown>> {
    return this.readyDeferred.promise;
  }

  async release(): Promise<void> {
    this.released = true;
  }
}

function createDeferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: unknown): void;
} {
  let resolve: (value: T) => void = () => {};
  let reject: (error: unknown) => void = () => {};
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    await flush();
    await new Promise((resolve) => setTimeout(resolve, 5));
    if (predicate()) return;
  }
  throw new Error('Timed out waiting for predicate');
}

# Components

`WireComponent` is the authored abstraction for runtime and service contracts that can be created
in-process or served from a worker process.

Use a component when a contract has a reusable runtime implementation and the composition root should
choose whether it runs in the current process or in a supervised worker. A component is not a
dependency injection container: it describes one contract implementation, its explicit requirements,
its config schema, and how to synchronously create a scope-owned instance.

## Define A Component

```ts
import { defineContract, procedure, createController } from '@emdash/wire/rpc';
import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';

export const clockContract = defineContract({
  now: procedure({ input: z.void().optional(), output: z.number() }),
});

export const counterContract = defineContract({
  increment: procedure({ input: z.void().optional(), output: z.number() }),
});

const component = defineWireComponent({
  id: 'counter',
  contract: counterContract,
  requirements: {
    clock: requireContract(clockContract),
  },
  configSchema: z.object({
    initialValue: z.number().int().default(0),
  }),
  create: ({ scope, dependencies, config, instance }) => {
    let value = config.initialValue;
    scope.add(() => {
      value = 0;
    });

    return instance({
      scope,
      controller: createController(counterContract, {
        increment: async () => {
          await dependencies.clock.now(undefined);
          value += 1;
          return value;
        },
      }),
    });
  },
});
```

`create` is synchronous. Expected async work belongs in domain procedures, `LiveJobSource`s, machines,
live state, or other explicit runtime APIs. Directory creation, installs, probing, and startup
operations should expose their own lifecycle and errors rather than hiding inside component
construction.

`instance({ scope, controller })` adapts the controller into a typed in-process client using a memory
transport. The controller should be unvalidated; the component creation boundary applies validation
according to the caller's `validate` policy.

## Explicit Requirements

Requirements are plain object keys. A component can require another Wire contract with
`requireContract(contract)`. Deployment values such as paths, limits, executable names, and feature
flags belong in typed component config, not dependency requirements.

There is no container, provider registry, singleton policy, recursive construction, or automatic
resolution. Composition roots create or spawn the dependencies they want and pass dependency clients
explicitly. Worker hosts may also accept dependency controllers and forward them over dependency
channels.

```ts
const clock = defineWireComponent({
  id: 'clock',
  contract: clockContract,
  requirements: {},
  configSchema: z.object({}),
  create: ({ instance, scope }) =>
    instance({
      scope,
      controller: createController(clockContract, {
        now: () => Date.now(),
      }),
    }),
});
```

## In-Process Creation

`component.create({ scope, dependencies, config, validate })` validates config and dependency keys,
creates a child scope, wires a memory transport, serves the controller, and returns a typed client.
Disposing the instance stops the in-memory server and disposes the component scope.

Controller factories used by components should return unvalidated controllers. The component
creation or worker serving boundary applies validation once.

```ts
import { createScope } from '@emdash/shared/concurrency';

const scope = createScope({ label: 'app' });
const clockInstance = clock.create({
  scope,
  dependencies: {},
  config: {},
  validate: 'inputs',
});

const counterInstance = component.create({
  scope,
  dependencies: {
    clock: clockInstance.client,
  },
  config: {
    initialValue: 41,
  },
  validate: 'inputs',
});

await counterInstance.client.increment(undefined); // 42
await scope.dispose();
```

The caller owns the parent scope. Each component creates a child scope under it. Disposing either the
instance or the parent scope releases the component resources.

## Worker Deployment

`WireWorkerHost.create(component, options)` returns a lazy supervised worker. `worker.ready()`
starts it and returns the stable typed client. `spawn(component, options)` eagerly starts the
worker and returns that client.

Worker component IPC uses internal framed logical channels:

- `runtime` for the served component contract.
- bootstrap messages for config and readiness.
- one `dep:<name>` channel per contract requirement.

Dependency channels are forwarded only from the explicit `dependencies` object supplied by the
composition root. Child workers receive typed clients for those channels; they do not locate or
start dependencies themselves.

Parent process:

```ts
import { createScope } from '@emdash/shared/concurrency';
import { createWireWorkerHost } from '@emdash/wire/worker';
import { childProcessSpawner } from '@emdash/wire/worker/node';
import { clock, component as counterComponent } from './component';
import { workerPath } from './worker-manifest';

const scope = createScope({ label: 'app' });
const host = createWireWorkerHost({
  scope,
  processSpawner: childProcessSpawner(),
});

const clockInstance = clock.create({
  scope,
  dependencies: {},
  config: {},
});

const counterWorker = host.create(counterComponent, {
  executable: workerPath('counter'),
  dependencies: {
    clock: clockInstance.client,
  },
  config: {
    initialValue: 0,
  },
});

const counterClient = await counterWorker.ready();
await counterClient.increment(undefined);
```

Worker entry:

```ts
import { runWireComponentWorker } from '@emdash/wire/worker';
import { component as counterComponent } from './component';

void runWireComponentWorker(counterComponent);
```

The client returned by `ready()` is stable across process generations. Calls fail while the worker is
unavailable; the client does not buffer calls during restarts.

## Testing Components

For in-process tests, create the component under a test scope and pass fake dependency clients
explicitly.

```ts
import { createScope } from '@emdash/shared/concurrency';
import { createController } from '@emdash/wire/rpc';
import { defineWireComponent } from '@emdash/wire/worker';
import { z } from 'zod';

const scope = createScope({ label: 'test' });
const fakeClockComponent = defineWireComponent({
  id: 'fake-clock',
  contract: clockContract,
  requirements: {},
  configSchema: z.object({}),
  create: ({ instance, scope }) =>
    instance({
      scope,
      controller: createController(clockContract, {
        now: () => 1,
      }),
    }),
});
const fakeClock = fakeClockComponent.create({
  scope,
  dependencies: {},
  config: {},
});

const counter = component.create({
  scope,
  dependencies: {
    clock: fakeClock.client,
  },
  config: {
    initialValue: 0,
  },
  validate: 'full',
});

await expect(counter.client.increment(undefined)).resolves.toBe(1);
await scope.dispose();
```

For worker tests, use `FakeWorkerProcessSpawner` and run the child side with
`runWireComponentWorker(component, { port: fakeProcess.childPort })`. This exercises bootstrap,
logical channel isolation, dependency forwarding, readiness, and reconnect behavior without starting
a real child process.

## Build Metadata

Manual worker manifests in the desktop app and workspace-server are temporary build metadata. They
map thin entry files to emitted worker artifacts until a bundler plugin owns worker artifact
generation. They are not part of the component runtime API.

## Guidelines

- Keep component factories synchronous and cheap.
- Pass dependencies by name from the composition root; never look them up from a global registry.
- Prefer contract requirements for shared capabilities that may cross process boundaries.
- Use typed config for deployment-specific values such as paths, limits, executable names, and
  feature flags.
- Keep controller validation at the component creation or worker serving boundary, not inside every
  controller factory.
- Keep manual worker manifests and entry files thin; they should only select a component and call
  `runWireComponentWorker(component)`.

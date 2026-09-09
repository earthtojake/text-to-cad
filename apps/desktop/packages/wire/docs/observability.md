# Observability

`@emdash/wire` exposes observability at the same boundaries that own runtime
behavior: server calls, client calls, live topic attachment, mutation dedupe,
live-client resyncs, transport messages, and scope cleanup.

## Ambient Logger

The logger interface and redaction utilities live in `@emdash/shared/logger`.
Wire uses the shared ambient logger to attach call context without passing a
logger through every domain function:

```ts
import { log, runWithLogger } from '@emdash/shared/logger';

await runWithLogger(logger.child({ requestId: 'r1' }), async () => {
  log.info('handling request');
});
```

Node entry points can install the `AsyncLocalStorage` store:

```ts
import { installAsyncLogContext } from '@emdash/shared/logger/node';

installAsyncLogContext();
```

Browser and renderer code use a synchronous fallback. It still supports a root
logger and scoped synchronous blocks, but it does not preserve context across
`await`.

## Instrumentation Hooks

Use `WireInstrumentation` (exported from `@emdash/wire/rpc`) for typed events
that can be adapted to logs, metrics, or tracing. The seam is threaded through
the public options of `serve()`, `connect()`, replicas, and `expose()`:

```ts
import type { WireInstrumentation } from '@emdash/wire/rpc';

const instrumentation: WireInstrumentation = {
  callEnd: (event) => logger.debug('call finished', event),
  resyncFailed: (event) => logger.warn('resync failed', event),
};

serve(transport, controller, { logger, instrumentation });
const connection = connect(clientTransport, { instrumentation });
const contractClient = client(api, connection);
```

Hooks currently cover:

- procedure start/end, cancellation, and duration.
- snapshot timing and errors.
- live topic attach/detach.
- live model/log resync reasons and resync failures.
- replica cursor-translation timeouts.
- mutation dedupe hits.
- scope cleanup errors.
- transport connect/disconnect events.

There are no bundled logger adapters: adapt the typed events to your logging or
metrics stack at the application edge.

Serving and client options are documented in [API serving](./api/serving.md).
Transport construction is documented in [API transports](./api/transports.md).

## Scope Logging

`createScope({ logger, label })` attaches a logger to the scope tree. Children
inherit the logger with a `scope` binding containing their label path:

```ts
const runtimeScope = createScope({ label: 'runtime', logger });
const sessionScope = runtimeScope.child('session:abc');

sessionScope.log.info('session started');
```

Cleanup errors and failed runs are reported through the scope logger by default.
Use `describeScope(scope)` for a lightweight label tree when debugging retained
resources or stuck async work. Scope descriptions include active run labels,
start times, and cancellation state. When the scope is created with a custom
`Clock`, those start times come from that clock, which keeps lifecycle diagnostics
deterministic in tests.

Scope lifecycle behavior is documented in [runtime lifecycle](./runtime/lifecycle.md)
and [structured concurrency](./runtime/structured-concurrency.md).

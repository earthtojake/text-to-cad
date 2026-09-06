# Event Streams

`eventStream({ key, event })` exposes a keyed server-to-client event channel for
loss-tolerant notifications. It reuses the wire live attachment protocol but does
not retain events or expose meaningful snapshots.

Use event streams when subscribers can recover from missed events by resyncing
from another source of truth, such as a file tree, cache, or database query. Use
`liveLog` for retained append-only text and `liveModel` for convergent state.

## Contract

```ts
const api = defineContract({
  fileEvents: eventStream({
    key: z.object({ rootPath: z.string() }),
    event: z.object({
      kind: z.enum(['create', 'update', 'delete']),
      path: z.string(),
    }),
  }),
});
```

The key addresses an event stream instance. The event schema types the
client-side `onEvent` callback and documents the payload shape.

## Server

Most servers use `createEventStreamHost()`:

```ts
const fileEvents = createEventStreamHost(api.fileEvents);

const controller = createController(api, {
  fileEvents,
});

fileEvents.emit(
  { rootPath: '/repo' },
  { kind: 'update', path: '/repo/package.json' }
);
```

`emit()` is fire-and-forget. If no client is attached to that key, the event is
dropped. When the last subscriber detaches, the host discards the keyed source.

If attachment presence owns an external resource, pass lifecycle hooks to the
host. `onActive` runs when the first subscriber attaches to a key, and `onIdle`
runs when the last subscriber detaches:

```ts
const fileEvents = createEventStreamHost(api.fileEvents, {
  onActive(key) {
    void startWatcher(key);
  },
  onIdle(key) {
    void stopWatcher(key);
  },
});
```

This is useful for resources that should be recreated after reconnect. The wire
client automatically reattaches live topics after reconnect, so `onActive` runs
again in the new server process.

You can also pass a resolver to `createController()` if another component owns
the source:

```ts
createController(api, {
  fileEvents: (key) => sources.get(key.rootPath),
});
```

## Client

```ts
const unsubscribe = await client.fileEvents.subscribe(
  { rootPath: '/repo' },
  {
    onEvent(event) {
      console.log(event.kind, event.path);
    },
    onGap() {
      void reloadFileTree();
    },
    onError(error, { retrying }) {
      if (!retrying) showFileEventStreamError(error.message);
    },
  }
);
```

`onGap` runs after the underlying transport reattaches. Events may have been lost
while the link was disconnected or while a supervised subprocess restarted, so
consumers should refresh any derived state in that callback.

Initial attachment does not call `onGap`; subscribers should perform their own
initial load before or after subscribing.

The `subscribe()` promise rejects if the initial attachment fails. After an
attachment is established, `DISCONNECTED` reattach failures call `onError` with
`retrying: true` and remain registered for a later reconnect. Non-retryable
reattach errors call `onError` with `retrying: false` and terminate the
attachment.

## Semantics

- Events are at-most-once and only delivered to currently attached clients.
- No historical events are retained for late subscribers.
- Event stream keys are validated by controller validation.
- Event payloads are not validated on the push path, matching other live updates.
- Forwarding preserves upstream gaps and reattach errors even when the downstream
  transport remains connected.

## Example

See [../../examples/event-stream/client.ts](../../examples/event-stream/client.ts)
for a runnable in-process example.

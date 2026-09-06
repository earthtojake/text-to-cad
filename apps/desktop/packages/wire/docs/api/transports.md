# Transports

A `WireTransport` is the protocol boundary:

```ts
type WireTransport = {
  post(message: WireMessage): void;
  onMessage(cb: (message: WireMessage) => void): Unsubscribe;
  onDisconnect(cb: () => void): Unsubscribe;
  onReconnect?(cb: () => void): Unsubscribe;
  onTerminalFailure?(cb: (error: unknown) => void): Unsubscribe;
  close?(): void;
};
```

The same `serve()`, `connect()`, and `client()` code works across every
transport. Only construction changes.

`onReconnect` is optional and fires whenever the transport establishes
connectivity, including the first time. Its presence marks the transport as
reconnect-capable: `connect()` then holds calls issued while disconnected until
the next reconnect or the call deadline, and re-attaches live topics after each
reconnect; replicas then force a fresh snapshot. Transports without it fail
calls immediately while disconnected. `onTerminalFailure` fires once when the
transport gives up permanently; `connect()` rejects all held and future calls
with a `WireError('DISCONNECTED')` carrying the cause. `close()` releases
listeners registered by the adapter. It closes the underlying channel only when
the adapter owns a closeable channel, such as a `MessagePort`.

## Memory

`memoryTransportPair()` creates paired in-process transports for tests and
examples:

```ts
const pair = memoryTransportPair();
serve(pair.right, controller);

const contractClient = client(api, connect(pair.left));
```

`pair.disconnect()` disconnects both sides. Each endpoint also exposes `close()`,
which aliases the pair disconnect for test cleanup.

`left` and `right` are the two ends of one duplex channel, not semantic roles.
Posting on `left` delivers to listeners registered on `right`, and posting on
`right` delivers to listeners registered on `left`. This mirrors
`MessageChannel`'s `port1`/`port2`: tests commonly call `serve(pair.right, ...)`
and `connect(pair.left)`, but the opposite assignment is equally valid.

## DOM MessagePort

`domPortTransport(port)` adapts browser `MessagePort` objects:

```ts
const channel = new MessageChannel();
serve(domPortTransport(channel.port1), controller);

const connection = connect(domPortTransport(channel.port2));
```

The adapter calls `port.start?.()` and listens for `message` and `close` events.
`close()` removes those listeners and calls `port.close?.()`.

## Electron Windows

`exposeWireToWindows()` serves one controller to many Electron renderer windows
using `MessageChannelMain`-style ports:

```ts
const stop = exposeWireToWindows(
  {
    ipcMain,
    createMessageChannel: () => new MessageChannelMain(),
  },
  controller,
  { channel: 'wire' }
);
```

The renderer asks for a port, then waits for the browser-side transfer:

```ts
await requestWirePort({ ipcRenderer, window }, { channel: 'wire' });
const port = await awaitWirePort(window, { channel: 'wire' });
const contractClient = client(api, connect(domPortTransport(port as MessagePort)));
```

Opening a new port for the same `webContents.id` closes the old one. Naturally
closed ports are removed from the session map. Internally, the helper uses
`createWireSessionHub(controller)`, so session teardown also closes the transport.

## Node Streams

`streamTransport(input, output)` frames messages as newline-delimited JSON. It is
useful for subprocess, stdio, and SSH-style boundaries:

```ts
const transport = streamTransport(child.stdout, child.stdin);
const contractClient = client(api, connect(transport));
```

Malformed frames are ignored. `close`, `end`, and `error` on the readable side
trigger disconnect listeners. `close()` stops parsing and clears local listeners;
it does not close the readable or writable streams because those streams are owned
by the caller.

## Reconnecting

`reconnectingTransport(connectOnce, options?)` wraps an async transport factory:

```ts
const transport = reconnectingTransport(
  async () => {
    const pair = await openRemoteWirePair();
    return pair.left;
  },
  { backoffMs: [100, 250, 500, 1000] }
);

await transport.ready();
```

`connectOnce` is the readiness boundary for one physical connection. The returned
transport remains private until the promise resolves. Applications that require a
handshake should open the candidate, run the handshake against it, dispose the
temporary logical `Connection`, and only then return the candidate:

```ts
const transport = reconnectingTransport(
  async () => {
    const candidate = await openRemoteTransport();
    const handshakeConnection = connect(candidate);
    const handshakeClient = client(api, handshakeConnection);
    try {
      const result = await handshakeClient.initialize({ version: PROTOCOL_VERSION });
      if (!result.success) throw new ProtocolMismatchError(result.error);
      return candidate;
    } catch (error) {
      candidate.close?.();
      throw error;
    } finally {
      handshakeConnection.dispose();
    }
  },
  {
    shouldRetry: (error) => !(error instanceof ProtocolMismatchError),
  }
);

await transport.ready();
const stableClient = client(api, connect(transport));
```

This ordering guarantees that held calls and live-topic reattachments cannot
overtake an application handshake. Wire itself remains version-agnostic; the
application owns the handshake contract and permanent-error classification.

The reconnecting transport does not queue messages. `post()` while no ready
inner transport exists throws a `WireError('DISCONNECTED')`; robustness is
owned entirely by `connect()`, which holds calls issued while disconnected
until the next reconnect or the call deadline. When an inner transport
disconnects, listeners are notified, readiness resets, and reconnection starts.

`ready()` resolves after the current `connectOnce` succeeds and its candidate is
installed. After a disconnect, a new call to `ready()` waits for the replacement
generation. A previously resolved readiness promise does not become pending
again, so disconnect observers should call `ready()` after receiving the
disconnect event.

`shouldRetry(error, { attempt, isReconnect })` classifies factory or handshake
failures. Returning `false`, or exhausting a finite `retrySchedule`, permanently
stops that transport, rejects its current readiness promise, and fires
`onTerminalFailure` with the terminal error. Future `post()` calls fail with the
terminal error. By default, failures remain retryable under the configured
schedule.

`onReconnect` fires whenever an inner transport reaches readiness, including
the first one. `Connection` listens for that signal to flush held calls and
re-issue active `attach` requests; replicas refresh their snapshots after
reattach. `close()` stops the retry loop, closes the current inner transport if
present, fires `onTerminalFailure`, and clears listeners.

## Composition Notes

`reconnectingTransport()` accepts `clock` and `retrySchedule` options. The legacy
`backoffMs` array is normalized to a repeat-last retry schedule. Closing the
transport synchronously aborts pending reconnect sleeps and disposes late
connections.

Electron window exposure returns an async cleanup function. Await it when tearing
down a runtime host so session hubs and controllers finish disposal before the
worker or window bridge is replaced.

Transport composition is ordinary function wrapping, so order matters when
stacking adapters around `reconnectingTransport()`. For semantic telemetry (one
event per logical call, snapshot, attachment, cancellation, resync, or mutation
dedupe), attach a `WireInstrumentation`; see
[observability](../observability.md).

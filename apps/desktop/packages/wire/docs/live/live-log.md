# Live Logs

Live logs are append-only text streams with retained tail snapshots. They are a
good fit for terminal output, build logs, and agent process output where clients
need to attach late and still see recent context.

## Server

`LiveLogSource` stores a bounded text buffer. `append(chunk)` emits
`{ chunk }` deltas to subscribers and updates the retained snapshot:

```ts
const server = new LiveLogSource({ generation: 3000, maxBufferBytes: 12 });

export function appendLine(line: string): void {
  server.append(`${line}\n`);
}
```

Options:

- `generation`: optional fixed generation, useful in tests.
- `maxBufferBytes`: retained buffer size. The default is 1 MiB.

Snapshots contain `LiveLogSnapshotData`:

```ts
type LiveLogSnapshotData = {
  baseOffset: number;
  text: string;
  truncated: boolean;
};
```

`baseOffset` is the byte offset of `text` in the logical full log. When the
server drops old bytes because `maxBufferBytes` was exceeded, `truncated` is
`true`. The server keeps at least the newest chunk even if it exceeds the byte
limit.

`reseed()` starts a new generation and resets sequence to `0`. With no argument,
it clears retained text and resets `baseOffset` to `0`; with retained snapshot
data, it seeds the buffer from that data.

## Consumers

Consumers normally reach logs through the API layer. The client handle is useful
when you want to stream directly into a terminal or log viewer:

```ts
const output = contractClient.activity.handle(session);
const snapshot = await output.snapshot();
term.write(snapshot.data.text);

const detach = await output.attach((update) => {
  term.write((update.delta as { chunk: string }).chunk);
});
```

Use `createLiveLogReplicaCache()` when a process wants a retained local buffer that can
also be served downstream. Without a custom sink, the replica keeps an eager
bounded `LiveLogSource` buffer and `text()` remains readable. With a custom `LogSink`,
the sink owns storage; readable `LogStore`s add `text()`, while write-only sinks
can stream directly into xterm without a duplicate text buffer.

The replica's internal log follower tracks the followed generation/sequence
plus the UTF-8 byte offset already written to its sink. On reconnect or explicit `refresh()`, it
splices from the retained snapshot when the generation still matches, appending
only missing bytes instead of resetting rendered output. Generation changes or
evicted gaps still reset the sink from the retained snapshot.

The underlying protocol follower resyncs on update-before-seed, generation
mismatch, sequence gap, or invalid log delta. Resync events use the same `resync`
instrumentation hook as live models.

## API Layer Usage

Contracts expose logs with `liveLog({ key })`:

```ts
const api = defineContract({
  activity: liveLog({ key: sessionKeySchema }),
});

const controller = createController(api, {
  activity: () => activityLogServer,
});

const activity = contractClient.activity.handle(session);
const detach = await activity.attach((update) => {
  console.log((update.delta as { chunk: string }).chunk);
});

detach();
```

The API layer handles topic encoding, snapshots, attachment, and detachment.

See [../../examples/live-log/client.ts](../../examples/live-log/client.ts).

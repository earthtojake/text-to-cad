# ACP Runtime Architecture

The ACP runtime is the domain service that serves the ACP API contract. It owns
the host-scoped dependencies needed to run provider ACP sessions, but it should
not mix cross-session routing with per-session state projection.

## Ownership

- `AcpRuntime` is the composition root. It wires the ACP API contract to shared
  ports, the resource-cached connection source, and the session manager.
- `SessionManager` owns cross-session lifecycle: session creation, routing ACP
  `sessionId`s to conversation cells, process cleanup, and the sessions-list live
  model. Activity tracking, idle sweeping, intent persistence, lifecycle reports,
  and eviction sequencing are delegated to the shared session-lifecycle chassis
  (`packages/core/src/services/session-lifecycle/`), which the TUI-agents and
  terminals runtimes also compose.
- `SessionCell` owns one conversation: the state machine, transcript reducer,
  per-session live models, permission broker, prompt queue effects, and turn
  quiescence.
- The ACP connection source owns provider processes through `createResourceCache`.
  Cache identity includes provider, workspace, and cwd; the process route id stays
  provider/workspace and can host multiple ACP sessions.
- Models under `packages/core/src/acp/models/` are the shared vocabulary for
  reducer output, live model state, and the public ACP API contract.
- Runtime implementation code lives under `packages/core/src/runtimes/acp/node/`; the portable
  contract and client models stay under `packages/core/src/runtimes/acp/api/`.
- The Node surface exports `createAcpComponent()`. App-owned worker entries call
  `runWireComponentWorker(createAcpComponent(...))`; `@emdash/core` does not export
  process bootstrap helpers.

```mermaid
flowchart TD
  subgraph api [ACP API]
    commands[Commands]
    liveModels[LiveModels]
    queries[Queries]
  end
  subgraph runtime [Runtime]
    root[AcpRuntime]
    manager[SessionManager]
  end
  subgraph session [Session Cell]
    machine[SessionMachine]
    reducer[Transcript Reducer]
    state[Per-session LiveModels]
  end
  subgraph connection [Connection]
    source[ConnectionSource]
    ports[AgentPorts]
  end
  agent[ACP Agent]

  commands --> root --> manager --> machine
  machine --> source --> agent
  agent --> ports --> reducer
  reducer --> state --> liveModels
  manager --> liveModels
  reducer --> queries
```

## Command and Read Paths

Commands enter through the API and are routed by `AcpRuntime` to the
`SessionManager`. Lifecycle commands such as starting and stopping sessions are
handled by the manager because there is no cell before a session exists. Session
commands are routed to an existing `SessionCell`, where the pure
`SessionMachine` decides whether the command is valid and emits effects for the
cell to interpret.

Provider updates move in the opposite direction. The connection handler receives
ACP callbacks, normalizes raw `SessionUpdate`s through the provider's enrich
hook, and asks the `SessionManager` to route the event to a cell. The cell folds
the event through the reducer and publishes changed slices through live models.

Provider `sessionId` persistence is owned by the host that consumes the ACP API.
The runtime returns the session id from `start` and `resume`; desktop
persists that returned value at the client boundary instead of using a child-to-host
callback.

`editCurrentPrompt` and `exportAcpTranscript` are intentionally contract-only
placeholders for now. Workspace-server stubs should keep typechecking against
the contract, but core does not serve implementations until those workflows are
designed.

## Process Hosting

Desktop-local ACP and workspace-server ACP both register logical workers through
`WireWorkerHost` and use the Node `childProcessSpawner()` by default. The child
process entry calls `runWireComponentWorker(createAcpComponent(...))`, which constructs
`AcpRuntime`, a machine-scoped `AgentPluginHost`, `ChildAcpProcessHost`, and
`LocalAttachmentStore`. Host executable resolution comes from the injected
`HostDependencies` resolver contract; ACP does not construct a dependency manager or keep a
runtime-local executable cache. ACP-specific resources such as process handles, ACP ports,
terminal management, attachment storage, and session cells stay inside the ACP runtime. Each host
owns a worker manifest that maps the ACP worker id to the emitted child-process entry path for that
host's build.

Desktop composes the ACP client and renderer exposure in
`apps/emdash-desktop/src/main/core/wire-workers/desktop-workers.ts`: the raw
stable worker client is wrapped there for session-ID persistence, then forwarded
to Electron windows through `exposeWireToWindows()`. `WireWorkerHost` itself
does not own client decoration, startup policy, or renderer exposure.

The concrete plugin registry is injected by each host entry (`emdash-desktop` and
`workspace-server`) rather than imported by `@emdash/core/runtimes`; this keeps runtime
from depending back on `@emdash/plugins` while still letting plugin resolution be
owned by the runtime composition root.

Desktop relies on Electron's `child_process.fork` behavior, which runs children
with `ELECTRON_RUN_AS_NODE`. The packaged app must keep the `RunAsNode` fuse
enabled while this fork model is used. If the app later disables that fuse for
macOS hardening, the wire package exposes the Electron
`utilityProcessSpawner()` seam for utility-process generations.

## Models and Protocol Versioning

The ACP API contract should reference the schemas in `packages/core/src/acp/models/`
instead of maintaining duplicate workspace-server schemas. This means wire-facing
model changes are protocol changes. Follow the workspace-server compatibility
rules:

- Add optional fields for backward-compatible minor changes.
- Treat required field changes, removals, renames, and incompatible union changes
  as major protocol changes.
- Keep wire envelopes such as history pages, terminal output stream events, and
  runtime errors in the ACP API layer because they are transport framing, not
  domain models.

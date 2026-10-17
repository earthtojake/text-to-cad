# Workspace CAD services and resources

`CadWorkspaceService` is the renderer's domain boundary. A host constructs one
service per workspace and lends it to every mounted CAD view. The HTTP adapter,
`createCadClient`, implements this contract and retains its catalog, request,
cache and worker-session lifetimes. Disposing a view releases its render session;
disposing the service aborts its resources and sessions.

Part resolution and editing-preview observation belong to the service.
The HTTP implementation owns request encoding, bounded polling, subscriber
cancellation, replacement views and immutable store URL validation. A pending
derivation is asked after again at 80 ms, doubling to 640 ms, then at a tenth of
the wait so far, at most every 5 s: a derivation stuck behind a daemon that cannot
start a worker is not asked many times a second until it fails. A part
request keeps its tree, view and each component's part; an answer for another
view or part, or a ready row without a valid part record, fails before
publication. UI consumes the resulting tickets and never supplies a same-origin
transport fallback.

`service.resources` owns JSON, text, binary and size reads, dependency resolution
and worker tickets. Pass it as `{ resources }` to render loaders, peeks, sidecar
loads and robot loads. Relative package assets and URDF/SDF mesh references are
resolved by the provider. Direct glTF buffers and textures are read through it
as well; the Three.js loader receives temporary object URLs that are revoked
once parsing completes. Up to six nested glTF reads run together, each limited
to 64 MiB. Workers broker nested references back to the owning provider.

A normal HTTP provider gives workers serializable URL tickets, preserving the
existing worker fetch/decode path, including the configured HTTP cache policy.
Configured headers stay on the provider origin; external nested references do
not inherit them. Custom fetch implementations remain host-owned. A provider with a custom fetch reads bounded
bytes on its owning thread and transfers an owned ArrayBuffer to the worker.
The worker never receives a service function or detaches an admitted cache
buffer. Selector-table tickets are acquired only after reserving a worker slot, so
queued components cannot accumulate eagerly transferred buffers. Drawing a part
reads its display mesh alone, from the part store on the owning thread, and
requests no ticket. Aborting a worker request retains the existing scheduler and owner rules in
[resource ownership](resource-ownership.md).

Each service wraps its provider in an opaque cache generation. URL-addressed
JSON, text, mesh and descriptor caches include this scope; the completed package
cache does too. A fresh server-metadata read that observes a changed
identity token retires the generation and aborts its pending reads.
The provider exposes that generation signal on the main thread. Worker clients
subscribe before acquiring tickets, so already-issued URL
tickets cannot publish a late result after retirement. The signal itself never
crosses into a serializable worker message.
Replacement services and authentication providers cannot inherit another
service's URL cache. Mounts borrowing the same service retain warm reuse.
Decoded display meshes are keyed by their part and its mesh's object
(`partCacheKey`) and keep bounded geometry ownership.

The public low-level core loaders continue to support omitted providers for
standalone static HTTP callers. This is an explicit transport API default,
using ordinary fetch and URL-addressed caches; it is not a mutable process-wide
workspace provider. Shared UI requires its injected service. `loadSource` is the
static/source composition boundary and creates an HTTP provider when none is
supplied; docs and the snapshot entrypoint compose theirs explicitly. Hosts
requiring custom credentials, native transfer or workspace isolation must pass
a provider consistently to both loads and peeks.

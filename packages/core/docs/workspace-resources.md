# Workspace CAD services and resources

`CadWorkspaceService` is the renderer's domain boundary. A host constructs one
service per workspace and lends it to every mounted CAD view. The HTTP adapter,
`createCadClient`, implements this contract and retains its catalog, request,
cache and worker-session lifetimes. Disposing a view releases its render session;
disposing the service aborts its resources and sessions.

Where a document the cadgen engine serves is read belongs to the service too:
`engineDocument(file)` (an `.xbf`, or a STEP) answers the document's API URL through
the viewer, `/__cad/api/doc/<id>`, asked again after the server's `retryMs` while
the engine still reads the file, and the fetch every read of it is made with. The
HTTP implementation owns request encoding and cancellation. UI consumes the
resulting tickets and never supplies a same-origin transport fallback.

`service.resources` owns JSON, text, binary and size reads, dependency resolution
and worker tickets. Pass it as `{ resources }` to render loaders, peeks and robot
loads. Relative references and URDF/SDF mesh references are resolved by the
provider. Direct glTF buffers and textures are read through it
as well; the Three.js loader receives temporary object URLs that are revoked
once parsing completes. Up to six nested glTF reads run together, each limited
to 64 MiB. Workers broker nested references back to the owning provider.

A normal HTTP provider gives workers serializable URL tickets, preserving the
existing worker fetch/decode path, including the configured HTTP cache policy.
Configured headers stay on the provider origin; external nested references do
not inherit them. Custom fetch implementations remain host-owned. A provider with a custom fetch reads bounded
bytes on its owning thread and transfers an owned ArrayBuffer to the worker.
The worker never receives a service function or detaches an admitted cache
buffer. Aborting a worker request retains the owner rules in
[resource ownership](resource-ownership.md).

Each service wraps its provider in an opaque cache generation. URL-addressed
JSON, text, mesh and descriptor caches include this scope. A fresh server-metadata read that observes a changed
identity token retires the generation and aborts its pending reads.
The provider exposes that generation signal on the main thread. Worker clients
subscribe before acquiring tickets, so already-issued URL
tickets cannot publish a late result after retirement. The signal itself never
crosses into a serializable worker message.
Replacement services and authentication providers cannot inherit another
service's URL cache. Mounts borrowing the same service retain warm reuse.

The public low-level core loaders continue to support omitted providers for
standalone static HTTP callers. This is an explicit transport API default,
using ordinary fetch and URL-addressed caches; it is not a mutable process-wide
workspace provider. Shared UI requires its injected service. Hosts
requiring custom credentials, native transfer or workspace isolation must pass
a provider consistently to both loads and peeks.

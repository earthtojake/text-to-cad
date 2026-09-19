# @hardcore/core

The shared JavaScript half of cadgen: everything the distribution and its
clients need to turn cached geometry into pixels, meshes, and motion.
Source builds to ordinary ESM and package-owned declarations in `dist/`.
Apps and UI consume compiled exports; Node and snapshot bundlers carry
self-contained outputs in the Python distribution. Consumers neither alias
this package's source nor supply ambient module declarations.

**May depend on:** Three.js, three-mesh-bvh, meshoptimizer and framework-independent
helpers. Never React, ReactDOM, Electron, Next.js, UI or application source.
Browser entry points never import Node-only code. Node builders remain in `bin/`.

**Consumers:** `@hardcore/ui`, docs, web and desktop apps, and runtime bundlers.
`@hardcore/core/client` communicates with `cadgen.viewer` over HTTP; this
protocol relationship never imports Python or discovers an interpreter.

`@hardcore/core/drawing` validates bounded Excalidraw v2 scene snapshots for the
desktop's temporary sketch tabs. It imports no editor, React, filesystem or
storage service. Document limits and shared editor/host ownership are described
in [the drawing contract](../ui/docs/drawing.md); the mechanism is
[`src/drawing/index.js`](src/drawing/index.js).

## The laws that live here

- **Viewer three-input law**: a client renders from the file, its optional
  sidecar (`<name>.step.json`), and the cache — never source, never a build.
  Animation source is embedded in that one sidecar; no adjacent JavaScript
  file is discovered or fetched. The
  code in this package must be writable against exactly those inputs.
  An explicitly attached editing session may provide an immutable preview
  tree and resolved kinematics instead; it must not alias that tree to saved
  STEP bytes. Saved schema-9 sidecars require a matching document digest and
  use a closed declaration envelope. Their appearance section supplies named,
  sparse PBR materials plus canonical leaf assignments. Composition carries
  material ids and names into mesh data, owns its appearance wrappers, and never
  mutates the stored tree or component tessellation. Materials are read-only in
  viewers: Inspect and Render honor authored color, finish and opacity, with
  scene settings supplying fallbacks. Live annotation updates and assignment
  removal use `applySourceAppearanceToMeshData`; `sourceAppearanceGeometry`
  retains the exact publication identity for LOD ownership. These mechanisms
  live in [sourceSidecar.js](src/common/sourceSidecar.js). There are no session
  material overlays.
  Authored finishes use a small fixed reflection fill in Inspect so metals
  remain legible. [inspectEnvironment.js](src/common/inspectEnvironment.js) owns
  its procedural texture; it loads no studio or external HDR asset.
- **Resource ownership**: component geometry and edge textures can have more
  than one scene owner; only the LAST release disposes shared GPU/BVH state,
  and a failed construction or disposal leaves ownership charged and retryable
  rather than released twice. Mechanism:
  [docs/resource-ownership.md](docs/resource-ownership.md) §1.
- **Demand boundary**: a render-only load builds no selector topology, and no
  raycast accelerator until a ray reaches a component's bounds. Refinement
  honours that boundary — a component with active topology replaces its
  selectors at the same concrete tessellation before publishing new triangles.
  Mechanism: [docs/resource-ownership.md](docs/resource-ownership.md) §2.
- **Reuse never changes what is exact**: recomposition, instanced draws,
  frustum culling, material pass keys and detail swaps may all reuse previous
  work, but none may change exact geometry, persistent cache identity or
  occurrence identity — and changing viewport detail never changes export
  defaults. Canonical geometry trees carry no surface-producer selection;
  reuse requires the exact SURF binding, tolerance pair and payload version.
  Mechanism: [docs/resource-ownership.md](docs/resource-ownership.md) §3.
- **Worker isolation**: each tessellation worker runs one request at a time;
  excess requests wait on the client. A failed worker request reports an error
  instead of retrying expensive tessellation on the UI thread, and memory
  estimates stay on the client — never in worker messages, never in cache keys.
  Mechanism: [docs/resource-ownership.md](docs/resource-ownership.md) §4.
- **Cache loss is never silent extra work**: a mesh-cache read probes, admits,
  verifies the v4 header and content address, then adopts; a strict read
  reports a typed miss before tessellation starts rather than turning a cheap
  decoded-mesh request into unbudgeted surface tessellation. Mechanism:
  [docs/resource-ownership.md](docs/resource-ownership.md) §5.
- **One scene or the other**: `common/sceneSettings.js` is the public
  scene-policy boundary shared by the Viewer and the snapshot runtime, and
  `resolveSceneSettings()` returns EITHER an Inspect theme or a Render recipe,
  never a blend of the two. The closed Render envelope and the rig it drives:
  [docs/render-pipeline.md](docs/render-pipeline.md).
- **Kinematics is data, choreography is JS, independently**: the FK
  evaluator (`kinematicsRuntime.js`) folds sidecar mate data into
  transforms and is the operation-for-operation twin of the Python
  evaluator (`cadgen/_internal/kinematics_fk.py`) — a viewer slider and an
  exported bake agree to the bit. The animation runtime
  (`animationRuntime.js`) evaluates the `clips` exported by the self-contained
  JavaScript source in `sidecar.animation` (compiled by `renderModule.js`), with the
  `m.get(target)` handle contract (premultiplying calls, reset to rest every
  frame, pure in t). Neither half references the other; they
  meet only in the effect records. Flexible swept bodies use
  [tube deformation](docs/tube-deformation.md), deforming the original STEP
  tessellation through analytic centerlines in that same shared effects pass.
  Browser imports use temporary Blob URLs, revoked after module evaluation;
  hosts with a content security policy allow `blob:` in `script-src`. Node
  imports use data URLs because its ESM loader does not support Blob URLs.
- **Direct GLB animation stays native**: interactive direct-GLB loading retains
  the glTF scene graph and standard translation, rotation, scale, skin, and
  morph-weight tracks for a Three `AnimationMixer`. Static mesh normalization
  remains the fallback for unanimated files. Interactive documents are mutable,
  uncached, and explicitly disposed by their viewer owner; a bounded load-time
  pose sample supplies a stable framing estimate rather than resizing the stage
  during playback.
- **Byte determinism**: the tessellator and mesh serializers here produce
  the shipped export bytes — same geometry in, same bytes out. Deterministic
  algorithm changes advance `TESSELLATION_VERSION` and its Python mirror so
  old cached meshes cannot masquerade as current output. Meshing preserves
  shared trim references and treats Float32 transport precision explicitly,
  including periodic seams and primitive poles/apices.
  **Same bytes in every ENGINE, too**: the tessellator runs in Node for the
  export builders and in the snapshot browser for renders, and both publish
  into the same content-addressed mesh store, so whichever ran first decides
  what a document exports. ECMA-262 specifies `Math.sin`, `Math.cos`,
  `Math.hypot` and friends to no accuracy at all, and the two engines really do
  disagree — measurably, on a few percent of arguments. So nothing that writes
  bytes may call one, on the way into a tessellation or out of a serializer:
  `surf/trig.js` is engine-independent `sin`, `cos`, `acos`, `atan` and `atan2`
  (fdlibm kernels in plain arithmetic), lengths use `Math.sqrt`, which IEEE 754
  requires correctly rounded, and an integer power is a multiplication.
  `surf/trig.test.js` holds the line by scanning the whole import CLOSURE of
  the tessellator and the mesh-export builder, so a new dependency is covered
  the moment it is pulled in — and pins a golden vector, because a unit test
  only ever runs on one engine at a time.
  GLB material RGB decoded from sRGB hex is serialized at Float32 precision,
  so differences in JavaScript exponentiation do not change the output bytes.
  Every 8-bit sRGB channel survives the round trip; authored opacity and PBR
  values keep their precision. `GLB_SERIALIZATION_VERSION` and its Python
  mirror invalidate final GLB exports independently of cached tessellations.
- **Loud failure**: unresolved refs, unknown labels, and unknown presets
  throw with the known set listed; nothing renders a plausible wrong frame.

## The shape of the package

```
src/
  client/          # CAD service/resource contracts, HTTP adapter and worker tickets
  prompt/          # typed context bundles, identity/targets and pure serialization
  common/          # rendering + runtime entries shared by every consumer:
                   #   cadScene (scene build), renderMeshScene/renderModel/
                   #   renderOptions (stills), headlessRenderEntry (the
                   #   snapshot browser bundle's entrypoint),
                   #   kinematicsRuntime + kinematicsModule (FK + sidecar ->
                   #   pose definition), animationRuntime (clips),
                   #   stepModule/stepModuleEffects (effects application),
                   #   source (render-source loading), sceneSettings (shared
                   #   CAD/Render contract), camera, themeSettings internals,
                   #   displaySettings, stepTopology
  lib/             # subsystems: surf/ (tessellation + caches), selectors/
                   #   (ref runtime), assembly/ (package composition),
                   #   render/ (format mesh loaders), viewer/ (exploded
                   #   view, part visual state), urdf/ (robot loading),
                   #   export/ (packageMeshExport), cadRefs (grammar,
                   #   parity-tested against cad_ref_syntax.py)
bin/               # node builders the bundler ships into _runtime/node:
                   #   mesh-export.mjs (the ONE mesh path), dxf-mesh.mjs
docs/              # subsystem docs (the map below)
```

Contract mirrors that must stay in lockstep (each has a sync test):
`lib/cadRefs.js` ↔ `cadgen/cad_ref_syntax.py`;
`common/kinematicsRuntime.js` ↔ `cadgen/_internal/kinematics_fk.py`;
tessellation v4 keys, headers and mesh-index records ↔ `cadgen/store/meshes.py`.

Where the mechanism is written:

| Document | Covers |
|---|---|
| [docs/render-pipeline.md](docs/render-pipeline.md) | The staged pipeline (`loadSource` → `buildModel` → `renderModel` → `captureModel`), each module's options, `sceneSettings`' two scenes and the closed Render envelope, the photographic rig, display modes, CAD edges and per-component geometry sharing |
| [docs/resource-ownership.md](docs/resource-ownership.md) | Ownership and disposal, the selector/BVH demand boundary, recomposition and instancing reuse, the tessellation worker pool, mesh-cache admission |
| [docs/tube-deformation.md](docs/tube-deformation.md) | Deforming a swept body's original STEP tessellation through analytic centerlines |

## Public modules and lifetimes

Use `@hardcore/core/client`, `/common/*`, `/lib/*` and `/glb/*` exports.
Construct `createCadClient({ origin, workspaceId })` in a host. Construction is
inert; subscriptions start catalog polling. `dispose()` stops polling, aborts
requests and disposes render sessions. The client lazily owns its cache provider
and bounded write-back queue; each render session borrows a cancellable cache
view and owns its abort signal and worker leases. Switching views preserves
admitted cache writes, while disposing the client releases them. Root identity
comes from the server's stable
`rootId`, not its port. Multiple roots render concurrently without replacing
one another's provider. Request failures retain operation, URL, method, kind
and HTTP status for host-owned error presentation.
`serverInfo()` caches stable metadata; `serverInfo({ fresh: true })` performs
a new request so development restart polling observes identity changes and
connection failures.

`resolveEntry(file)` hydrates path-only catalog placeholders before returning.
Pass the displayed file to `createRenderSession({ file })` so polling refreshes
its metadata. Partial replies preserve other resolved entries; newer complete
entries and directory removals still invalidate them. A cancelled or older
request cannot overwrite a newer file revision.

`CadWorkspaceService` exposes typed surface resolution, preview observation and
a scoped `resources` provider. Its HTTP adapter owns the protocol; renderers
consume domain results and resource tickets. See [workspace services and resource
transport](docs/workspace-resources.md) for worker transfer, nested dependencies,
cache generations and the standalone static-HTTP default. No client reads model
source or starts a source build.

Inspect and Render each resolve their fixed scene base. Legacy host theme input
cannot replace either base.

## Working on core

From the root workspace run `npm ci`, `npm run build:packages`,
`npm test --workspace @hardcore/core` and `npm run check:boundaries`.
Rebuild compiled packages after shared edits; apps resolve `dist/` exports.

The Node test runner collects `*.test.js` and `*.test.mjs` under `src/` and
`scripts/`. It overlaps process startup and fixture reads with a concurrency
floor of four. Tests use synthetic or test-owned fixtures, fake clocks for
scheduled work, and tolerances appropriate to the behavior under test.

Changes consumed by the bundlers require `scripts/bundle/bundle.sh`, followed
by `scripts/bundle/bundle.sh --check`. Generated runtimes are wheel build
outputs; the source here remains the reviewable implementation. Do not change
canonical release versions during normal development.

## Portable prompt context

`@hardcore/core/prompt` exports lightweight non-React bundle/reference types,
runtime validation and canonical text serialization. Text, typed resource
references and attachments travel in one ordered, immutable snapshot with an
operation ID; attachment relationships name reference parts. Text ranges use
zero-based UTF-16 coordinates with an exclusive end. CAD targets retain the
existing selector grammar and document revision, without interpreting a code
range as a CAD fragment. Apps own clipboard/draft delivery, MIME/size limits and
acknowledged outcomes; this package never submits a prompt or knows a session.

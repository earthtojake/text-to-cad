# @text-to-cad/core

The shared JavaScript half of cadgen: everything the distribution and its
clients need to turn cached geometry into pixels, meshes, and motion.
Source builds to ordinary ESM and package-owned declarations in `dist/`.
Apps and UI consume compiled exports; Node and snapshot bundlers carry
self-contained outputs in the Python distribution. Consumers neither alias
this package's source nor supply ambient module declarations.

**May depend on:** Three.js, three-mesh-bvh, meshoptimizer and framework-independent
helpers. Never React, ReactDOM, Electron, Next.js, UI or application source.
Browser entry points never import Node-only code. Node builders remain in `bin/`.

**Consumers:** `@text-to-cad/ui`, docs, web and desktop apps, and runtime bundlers.
`@text-to-cad/core/client` communicates with `cadgen.viewer` over HTTP; this
protocol relationship never imports Python or discovers an interpreter.

`@text-to-cad/core/drawing` validates bounded Excalidraw v2 scene snapshots for the
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
- **One grouped view state**: `common/viewSettings.js` validates the public
  Solid, Render, X-ray, Hidden line and Wireframe presets. Every preset exposes
  the same independent camera, surfaces, edges, lighting, background, floor,
  grid and axes groups. `resolveViewSceneSettings()` in `common/sceneSettings.js`
  is the Viewer/snapshot policy boundary: enabled capabilities select scene
  resources, never the preset name. Disabled lighting retains neutral CAD
  illumination; disabled background restores the workbench canvas. Camera pose,
  clipping and explode remain model tools, outside preset selection and Custom
  comparison. View Reset clears display overrides and disables those tools. The grouped contract and the rig it drives:
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
- **One scene builder per file family, two callers**: a GLB, an STL or 3MF, and a
  robot description (URDF, SRDF, SDF) are each drawn by ONE builder here
  (`lib/render/glbScene.js`, `lib/render/meshScene.js`, `lib/urdf/robotScene.js`, over
  `lib/urdf/loadRobot.js` and `lib/urdf/robotParts.js`), which the viewer's renderer
  for that family and the snapshot CLI's headless stage (`common/headlessScene.js`)
  both call; the look they wear is resolved in one place (`resolveSceneSurfaceLook`,
  `common/sceneSettings.js`) and a robot opens at one pose (`robotOpeningPose`). A
  snapshot therefore cannot draw one of them differently from the viewer, and none is
  flattened into mesh data for a render. `npm run check:boundaries` holds both callers
  to the shared modules. A STEP document's scene is `buildModel`, shared the same way.
- **Direct GLB stays native**: a direct GLB is its glTF scene graph (nodes, skins,
  morph targets, authored materials) with its translation, rotation, scale, skin and
  morph-weight tracks for a Three `AnimationMixer`, in the viewer and in a snapshot.
  Its documents are mutable, uncached, and explicitly disposed by their one owner; a
  bounded load-time pose sample supplies a stable framing estimate rather than
  resizing the stage during playback.
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
                   #   cadScene (a STEP's scene build), renderMeshScene/
                   #   renderModel/renderOptions (stills), headlessRenderEntry
                   #   (the snapshot browser bundle's entrypoint), headlessScene
                   #   (a GLB, mesh or robot job through its family builder),
                   #   kinematicsRuntime + kinematicsModule (FK + sidecar ->
                   #   pose definition), animationRuntime (clips),
                   #   stepModule/stepModuleEffects (effects application),
                   #   source (render-source loading), sceneSettings (shared
                   #   CAD/Render contract), camera, themeSettings internals,
                   #   displaySettings, stepTopology
  lib/             # subsystems: surf/ (tessellation + caches), selectors/
                   #   (ref runtime), assembly/ (package composition),
                   #   render/ (format mesh loaders; the GLB and mesh scene
                   #   builders), viewer/ (exploded view, part visual state,
                   #   the surface look, the scene contract), urdf/ (robot
                   #   parsing and loading; the robot parts and scene builder),
                   #   drawing2d/ (a GET /__cad/drawing payload -> Canvas 2D, text by fillText:
                   #   fit/pan/zoom maths, batched Path2D, hairline strokes),
                   #   export/ (packageMeshExport), cadRefs (grammar,
                   #   parity-tested against cad_ref_syntax.py)
bin/               # node builders the bundler ships into _runtime/node:
                   #   mesh-export.mjs (the ONE mesh path)
scripts/           # chunk-ids.mjs (the pages' builds: a chunk's debug id) and
                   #   source-maps.mjs (the pages' builds: maps into the packages'
                   #   src/), beside the package's own build and test runners
docs/              # subsystem docs (the map below)
```

Contract mirrors that must stay in lockstep (each has a sync test):
`lib/cadRefs.js` ↔ `cadgen/cad_ref_syntax.py`;
`common/kinematicsRuntime.js` ↔ `cadgen/_internal/kinematics_fk.py`;
tessellation v4 keys, headers and mesh-index records ↔ `cadgen/store/meshes.py`;
`common/renderModule.js`'s animation exports and their refusals ↔ the build's
check in `cadgen/_internal/animation_source.py` (both read `common/renderModule.parity.json`).

Where the mechanism is written:

| Document | Covers |
|---|---|
| [docs/render-pipeline.md](docs/render-pipeline.md) | The staged pipeline (`loadSource` → `buildModel` → `renderModel` → `captureModel`), the unified display state, the two lighting recipes, the photographic rig, display modes, CAD edges and per-component geometry sharing |
| [docs/resource-ownership.md](docs/resource-ownership.md) | Ownership and disposal, the selector/BVH demand boundary, recomposition and instancing reuse, the tessellation worker pool, mesh-cache admission |
| [docs/tube-deformation.md](docs/tube-deformation.md) | Deforming a swept body's original STEP tessellation through analytic centerlines |

## Public modules and lifetimes

Use `@text-to-cad/core/client`, `/common/*`, `/lib/*` and `/glb/*` exports.
Construct `createCadClient({ origin, fetch })` in a host. Construction is
inert; subscriptions start catalog polling, which the host's `shouldPoll` gates
(the web's pauses while its page is hidden). The client also carries what every
CAD view asks of its server, so each host reaches it the same way: the model
library (`recents`, `changeRecents`, `thumbnail`, `keepThumbnail`), Open
(`pick`), Reveal (`reveal`), the person's analytics answer and features
(`consent`, `features`), the update check (`version`) and what the page did for
telemetry (`reportActivity`: a touch, a Quick Edit that went, or a crash); every
change is a POST with the viewer's guard header. A host reports its page's crashes
with `createCrashReporter(send, { fileOf })`, which makes each with `crashOf` (a
cancellation, an `AbortError`, is none) -- the
error's type and its script frames, oldest first, never its message, a value or a
URL (`fileOf` names a script by its file's own name, `scriptFileOf` by default, and
a frame in one of the page's own chunks also names its debug id, from the table the
page's build wrote, `__cadChunkIds`) -- and sends each distinct one once a page, a few
at most. A page's build stamps each chunk with the id its text and its source map decide
(`@text-to-cad/core/chunk-ids`, a Node module the builds import), never the bundler's,
which names the code alone: PostHog keeps one map an id. That map leads into the shared
packages' `src/`, not their `dist/`: the build loads their modules with the maps their own
builds wrote (`@text-to-cad/core/source-maps`), and fails if a chunk's map still ends in
compiled code. `dispose()` stops polling, aborts
requests and disposes render sessions. The client lazily owns its cache provider
and bounded write-back queue; each render session borrows a cancellable cache
view and owns its abort signal and worker leases. A host whose transport
caps one reply passes `maxBatchBytes`: no batched read asks for more, nor ever
more than the server's own bound; a longer body is the transport's to carry in
parts, and the client sees it whole. Switching views preserves
admitted cache writes, while disposing the client releases them. Request
failures retain operation, URL, method, kind and HTTP status for host-owned
error presentation.
`serverInfo()` caches stable metadata; `serverInfo({ fresh: true })` performs
a new request so development restart polling observes identity changes and
connection failures.

Files are named by absolute path. The catalog holds the files on screen:
`resolveEntry(file)` reads one (a file the server lacks is an
`isMissingFileError`), and `createRenderSession({ file })` keeps the displayed
file's entry current as polling refreshes it. A cancelled or older request
cannot overwrite a newer file revision. `folder(path)` lists one folder and
`search(path, query)` finds the CAD files under it, for the explorer.

`CadWorkspaceService` exposes typed surface resolution, preview observation and
a scoped `resources` provider. Its HTTP adapter owns the protocol; renderers
consume domain results and resource tickets. See [workspace services and resource
transport](docs/workspace-resources.md) for worker transfer, nested dependencies,
cache generations and the standalone static-HTTP default. No client reads model
source or starts a source build.

`createHttpAttachmentStore({ origin, fetch })` is the viewer server's store for a
picture a prompt names by path: `save(png, name)` posts it to `POST /__cad/sketches`
and answers the saved file's absolute path.

Inspect and Render each resolve their fixed scene base. Legacy host theme input
cannot replace either base.

## Working on core

From the root workspace run `npm ci`, `npm run build:packages`,
`npm test --workspace @text-to-cad/core` and `npm run check:boundaries`.
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

`@text-to-cad/core/prompt` exports lightweight non-React bundle/reference types,
runtime validation and canonical text serialization: `formatPromptContextText`, the
parts as lines, and `formatPromptMessage`, the one message a Quick Edit is — what the
person wrote, then `File:`, `References:` and, for a picture that travels as a file,
its label and path. Text, typed resource
references and attachments travel in one ordered, immutable snapshot with an
operation ID; attachment relationships name reference parts, and an attachment's
optional `label` ("Sketch") names it in that message. Text ranges use
zero-based UTF-16 coordinates with an exclusive end. CAD targets retain the
existing selector grammar and document revision, without interpreting a code
range as a CAD fragment. Apps own clipboard/draft delivery, MIME/size limits and
acknowledged outcomes: `PromptContextPort.deliver` hands a context to its destination
(`added`, `copied`) and `send`, where a host has a chat to post to, posts it as the
person's message (`sent`); this package never submits a prompt or knows a session.

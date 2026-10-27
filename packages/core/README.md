# @text-to-cad/core

The shared JavaScript half of cadgen: everything the distribution and its
clients need to turn the meshes the engine made into pixels and motion.
Source builds to ordinary ESM and package-owned declarations in `dist/`.
Apps and UI consume compiled exports; the OCCT parity bench bundles the
headless entry into a snapshot page of its own, outside the Python
distribution. Consumers neither alias
this package's source nor supply ambient module declarations.

**May depend on:** Three.js, three-mesh-bvh, meshoptimizer and framework-independent
helpers. Never React, ReactDOM, Electron, Next.js, UI or application source.
Browser entry points never import Node-only code.

**Consumers:** `@text-to-cad/ui`, the docs, web and CAD (`apps/mcp`) apps, and the parity
bench's bundler.
`@text-to-cad/core/client` communicates with `cadgen.viewer` over HTTP; this
protocol relationship never imports Python or discovers an interpreter.

## The laws that live here

- **Viewer three-input law**: a client renders from the file, what cadgen
  resolved of it, and the bytes cadgen made — never source, never a build. A
  document the cadgen engine serves (an `.xbf`, or a STEP, which opens as one) is
  what the engine serves of it: its structure and one buffer per part
  (`lib/xbf/xbfDocument.js`), with its mechanism, its configurations and motions
  as definitions, and per occurrence what its appearance resolves to (material,
  finish, base colour, opacity). The page reads nothing beside the document. A
  document ships no code, and no adjacent file is discovered or fetched. The code in this package must be
  writable against exactly those inputs. The engine document's scene
  (`lib/xbf/xbfScene.js`) places one group per instance over its prototype's buffer and
  wears the colour and material the structure gives it (`xbfLookParameters`); it decides no
  precedence of its own and never mutates the document. Materials are read-only in viewers:
  the regular modes (Inspect) and Render honor
  authored color, finish and opacity, with scene settings supplying fallbacks.
  There are no session material overlays.
  Authored finishes use a small fixed reflection fill in Inspect so metals
  remain legible. [inspectEnvironment.js](src/common/inspectEnvironment.js) owns
  its procedural texture; it loads no studio or external HDR asset.
- **Resource ownership**: a scene's sibling (Preview beside the editor) draws over
  its source's buffers and frees only what is its own; the source stays their owner
  and is disposed after its siblings. Mechanism:
  [docs/resource-ownership.md](docs/resource-ownership.md) §1.
- **Demand boundary**: no raycast accelerator is built until a ray reaches a
  component's bounds. Mechanism: [docs/resource-ownership.md](docs/resource-ownership.md) §2.
- **Reuse never changes what is exact**: recomposition and a prototype's geometry
  shared by its instances may reuse previous work, but neither may change exact
  geometry, persistent cache identity or occurrence identity. Canonical geometry
  trees carry no producer selection.
  Mechanism: [docs/resource-ownership.md](docs/resource-ownership.md) §3.
- **Worker leases**: the GLB and STL decode workers are leased by render
  sessions; releasing one owner never cancels another's work, and the last
  release retires the worker and its pending work. Mechanism:
  [docs/resource-ownership.md](docs/resource-ownership.md) §4.
- **One view state, a mode and a grid**: `common/viewSettings.js` validates the
  display: a mode (Solid, Shaded, Parts, X-ray, Hidden line, Wireframe), each a look
  at its own defaults with nothing to set, the Grid switch, and what modes share
  (appearance, camera, clipping, explode). Preview's own settings are kept apart
  from it, and Preview's look (Render) is no mode but asked for on its own
  (`preview`). `resolveViewSceneSettings()` maps the mode, or Render, into renderer
  groups, preserving the Viewer/snapshot policy boundary.
  Format capabilities are injected. There are no legacy display aliases or
  saved-shape migrations. The contract and rendering mechanism:
  [docs/render-pipeline.md](docs/render-pipeline.md).
- **Kinematics and choreography are data, independently**: the articulation
  player (`articulation.js`) plays a robot's articulation as cadgen resolved it —
  controls with their limits, joints with affine rows over the controls (and, where
  a joint follows its driver nonlinearly, a curve cadgen sampled from the
  mechanism's closed form, played by linear interpolation as a glTF sampler is),
  what a drag writes — by dot products into one motion per joint, which the robot's
  scene writes as the joint node's matrix; it mints no id, decides no default or
  ownership, solves no mechanism, and checks nothing cadgen checked. A GLB's clips
  are played as the file carries them (`lib/render/glbAnimationRuntime.js`, three's
  `AnimationMixer`), and an engine document's motions by `lib/xbf/xbfMotion.js`, whose
  `values(t)` is the engine's `mechanism.Timeline.values`: an evaluation is a pure function
  of t, so scrub, loop and seek are free. Neither runs model code, resolves names or checks
  anything cadgen checked, and neither references the articulation player.
- **One scene builder per file family, two callers**: a GLB, an STL or 3MF, a
  robot description (URDF, SRDF, SDF) and an engine document (an `.xbf`, or a STEP,
  which opens as one) are each drawn by ONE builder here
  (`lib/render/glbScene.js`, `lib/render/meshScene.js`, `lib/urdf/robotScene.js`, over
  `lib/urdf/loadRobot.js` and `lib/urdf/robotParts.js`, and `lib/xbf/xbfScene.js`, over
  `lib/xbf/xbfDocument.js`), which the viewer's renderer
  for that family and the OCCT parity bench's headless page (`common/headlessScene.js`)
  both call; the look they wear is resolved in one place (`resolveSceneSurfaceLook`,
  `common/sceneSettings.js`) and a robot opens at one pose: the opening of the
  articulation cadgen resolved for it (`cadgen.robot_payload`, played by
  `common/articulation.js`). The
  parity page therefore cannot draw one of them differently from the viewer (cadgen's own
  stills are OCCT's), and none is flattened into mesh data for a render. They are cut, exploded and measured the same
  way in both, too: Clip through `lib/viewer/sceneClip.js`, Explode through the scene's
  `setExplode` (`lib/viewer/sceneExplode.js`, a GLB's), Measure's snapping through
  `lib/viewer/meshMeasure.js`, every number in the FILE's unit (`lib/viewer/sceneUnits.js`)
  and a mesh's measurement marked approximate. What a file's view offers is one rule,
  `viewFeaturesForKind` (`common/viewSettings.js`). `npm run check:boundaries` holds both callers
  to the shared modules. The docs hero is a GLB, read by `lib/render/glbMeshData.js` and played by
  `lib/render/glbAnimationRuntime.js`, the viewer's own GLB path.
- **Direct GLB stays native**: a direct GLB is its glTF scene graph (nodes, skins,
  morph targets, authored materials) with its translation, rotation, scale, skin and
  morph-weight tracks for a Three `AnimationMixer`, in the viewer and in a snapshot.
  Its documents are mutable, uncached, and explicitly disposed by their one owner; a
  bounded load-time pose sample supplies a stable framing estimate rather than
  resizing the stage during playback.
- **No shipped bytes**: core neither meshes nor writes an export. cadgen's engine
  meshes every part with OCCT in its warm worker and writes STL, 3MF and GLB itself;
  core reads those meshes and draws them. The GLBs its tests and the UI's open
  are files cadgen wrote, and one compressed sample (`lib/render/fixtures`): no
  JS writes a GLB.
- **Loud failure**: unresolved refs, unknown labels, and unknown presets
  throw with the known set listed; nothing renders a plausible wrong frame.

## The shape of the package

```
src/
  client/          # CAD service/resource contracts, HTTP adapter and worker tickets
  prompt/          # typed context bundles, identity/targets and pure serialization
  common/          # rendering + runtime entries shared by every consumer:
                   #   renderModel/renderOptions (interactive canvases, the docs
                   #   hero), renderMeshScene (the parity page's stills),
                   #   headlessRenderEntry (that page's entrypoint), headlessScene
                   #   (a GLB, mesh, robot or engine document job through its
                   #   family builder), articulation (cadgen's articulation,
                   #   played), sceneSettings (shared CAD/Render contract),
                   #   camera, themeSettings internals, displaySettings,
                   #   animationClock (the playback transport)
  lib/             # subsystems: xbf/ (an engine document: its structure and
                   #   XBM2 part buffers, scene, look, kinematics and motions),
                   #   render/ (format mesh loaders; the GLB and mesh scene
                   #   builders), viewer/ (exploded view, part highlight,
                   #   the surface look, the scene contract), urdf/ (a robot
                   #   payload's meshes loaded; the robot parts and scene
                   #   builder, played by common/articulation),
                   #   drawing2d/ (a cadgen drawing payload, a DXF's ->
                   #   Canvas 2D, text by fillText:
                   #   fit/pan/zoom maths, batched Path2D, screen-width strokes),
                   #   cadRefs (the ref grammars: the engine's, for an .xbf
                   #   and a STEP, parity-tested against engine/refs.py;
                   #   a label, for any other file)
scripts/           # chunk-ids.mjs (the pages' builds: a chunk's debug id) and
                   #   source-maps.mjs (the pages' builds: maps into the packages'
                   #   src/), beside the package's own build and test runners
docs/              # subsystem docs (the map below)
```

Contract mirrors that must stay in lockstep (each has a sync test):
`lib/cadRefs.js` ↔ `cadgen/engine/refs.py` (an engine document's refs, an `.xbf`'s and
a STEP's: their parse and their canonical spelling), one fixture, `lib/cadRefs.parity.json`,
which also holds the element names (`elementNameCases`) that the engine's `ELEMENT_NAME`
(`cadgen/engine/kernel/trace.py`) must accept (`test_naming.py`).

Where the mechanism is written:

| Document | Covers |
|---|---|
| [docs/render-pipeline.md](docs/render-pipeline.md) | The family scene builders and the staged render (`renderModel` → `captureModel`), the unified display state, the two lighting recipes, the photographic rig, display modes and CAD edges |
| [docs/resource-ownership.md](docs/resource-ownership.md) | Ownership and disposal, the selector/BVH demand boundary, reuse across a rebuild, the decode worker pool |
| [docs/workspace-resources.md](docs/workspace-resources.md) | The workspace service and resource provider: where an engine document is read, worker tickets, nested glTF reads, cache generations |
| [src/lib/render/fixtures/README.md](src/lib/render/fixtures/README.md) | The GLB fixtures the core and UI suites open, and how each is regenerated |

## Public modules and lifetimes

Use `@text-to-cad/core/client`, `/common/*` and `/lib/*` exports.
Construct `createCadClient({ origin, fetch })` in a host. Its `exports` service
(`client/exports.js`) asks the session's epoch, submits idempotent jobs, long-polls their
status and names a ready job's file URL (`fileUrl`). It
starts no download; the host hands that URL to the browser. Construction is
inert; subscriptions start catalog polling, which the host's `shouldPoll` gates
(the web's pauses while its page is hidden). The client also carries what every
CAD view asks of its server, so each host reaches it the same way: the model
library (`recents`, `changeRecents`, `thumbnail`, `keepThumbnail`), Open
(`pick`), Reveal (`reveal`), the person's analytics answer and language (`consent`, `language`), the
update check (`version`) and what the page did for
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
compiled code. Each page's build also writes `THIRD_PARTY_LICENSES.txt` beside it
(`@text-to-cad/core/third-party-licenses`): every `node_modules` package its chunks and its
workers' chunks hold, by name, version and declared licence, with the licence text the package
ships, and a build fails on a bundled package that declares no licence. `dispose()` stops polling, aborts
requests and disposes render sessions. Each render session owns its abort signal and
worker leases. A body longer than a host's transport carries in one reply is the
transport's to carry in parts, and the client sees it whole. Request
failures retain operation, URL, method, kind and HTTP status for host-owned
error presentation.
`serverInfo()` caches stable metadata; `serverInfo({ fresh: true })` performs
a new request so development restart polling observes identity changes and
connection failures.

Files are named by absolute path, and a document the engine holds by its id alone (a model's)
by that id. The catalog holds the documents on screen, each row carrying its document's `id`,
by which rows join: one file however its path is spelled (a symlink, a case variant) is one row.
`resolveEntry(file)` reads one, asking by `?id=` for an id and by `?file=` for a path (one the
server lacks is an `isMissingFileError`, in the engine's words for an id it does not hold),
`entryOf(file)` is the row the catalog has, and `createRenderSession({ file })` keeps the displayed
file's entry current as polling refreshes it. A cancelled or older request
cannot overwrite a newer file revision. `folder(path)` lists one folder and
`search(path, query)` finds the CAD files under it, for the explorer.

`CadWorkspaceService` exposes a scoped `resources` provider and, where its host serves
the cadgen engine, where the page reads a document the engine serves
(`engineDocument`: an `.xbf`, or a STEP, read through the viewer at
`/__cad/api/doc/<id>` with the client's own fetch). Its HTTP adapter owns the protocol; renderers
consume domain results and resource tickets. See [workspace services and resource
transport](docs/workspace-resources.md) for worker transfer, nested dependencies,
cache generations and the standalone static-HTTP default. No client reads model
source or starts a source build.

`createHttpPromptFiles({ origin, fetch })` is the viewer server's maker of a Quick
Edit's files: `create(request)` posts its views and annotation to `POST /__cad/prompt-files`,
validates the packet without rendering and answers `{ inline: compactJson }` up to
1024 UTF-8 bytes, otherwise writes one `.snapshot.json` and answers `{ snapshot: absolutePath }`.
The client sends `acceptInline: true`; without this capability the server always saves
and returns a path for compatibility with already-open viewers;
`read(path)` fetches a JSON file. The annotation format, and
the code that draws an annotation in a scene for the viewer and for a snapshot alike, is
`common/annotation.js`.

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
optional `label` ("Annotation") names it in that message. Text ranges use
zero-based UTF-16 coordinates with an exclusive end. CAD targets retain the
existing selector grammar and document revision, without interpreting a code
range as a CAD fragment. Apps own clipboard/draft delivery, MIME/size limits and
acknowledged outcomes: `PromptContextPort.deliver` hands a context to its destination
(`added`, `copied`) and `send`, where a host has a chat to post to, posts it as the
person's message (`sent`); this package never submits a prompt or knows a session.

Native KiCad board plots use the read-only payload contract in [plot-payload](docs/plot-payload.md).
`lib/plot2d` draws its layers; `lib/board2d` handles picking and nets. File loading rereads
`/__cad/plot`; no browser snapshot bundle is shipped.

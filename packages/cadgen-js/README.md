# cadgen-js

The shared JavaScript half of cadgen: everything the distribution and its
clients both need to turn cached geometry into pixels, meshes, and motion.
This is SOURCE; the built, stamped copies that ship live in
`packages/cadgen/src/cadgen/_runtime/` — one sentence that resolves the one
ambiguity the name carries.

**PURPOSE** — the shared dependencies between cadgen (as it relates to
rendering files) and its clients: the CAD Viewer, the docs app, and any
future client. One package, one copy of each shared primitive.

**MAY DEPEND ON** — three (pinned; the repo pins 0.160.0 deliberately),
meshoptimizer, and nothing else at runtime. **Never React, never app or
workflow state, never Python coupling.** Framework-agnostic by law,
enforced by the imports-direction policy test.

**DEPENDED ON BY** — `apps/viewer` and `apps/docs` (source, via the
`cadgen-js` specifier and each app's alias), and the bundlers
(`scripts/bundle/`), which build it into cadgen's `_runtime/` (the browser
snapshot renderer and the node builders in `bin/`).

## The laws that live here

- **Viewer three-input law**: a client renders from the file, its sidecar
  (`<name>.step.json`), its optional adjacent render module
  (`<name>.step.js`), and the cache — never source, never a build. The
  code in this package must be writable against exactly those inputs.
- **Kinematics is data, choreography is JS, independently**: the FK
  evaluator (`kinematicsRuntime.js`) folds sidecar mate data into
  transforms and is the operation-for-operation twin of the Python
  evaluator (`cadgen/_internal/kinematics_fk.py`) — a viewer slider and an
  exported bake agree to the bit. The animation runtime
  (`animationRuntime.js`) evaluates the `clips` the render module beside the
  document (`<name>.step.js`, loaded by `renderModule.js`) exports, with the
  `m.get(target)` handle contract (premultiplying calls, reset to rest every
  frame, pure in t). That module is authored, never generated: editing it is
  a reload, never a rebuild. Neither half references the other; they
  meet only in the effect records. Flexible swept bodies use
  [tube deformation](docs/tube-deformation.md), deforming the original STEP
  tessellation through analytic centerlines in that same shared effects pass.
- **Byte determinism**: the tessellator and mesh serializers here produce
  the shipped export bytes — same geometry in, same bytes out.
- **Loud failure**: unresolved refs, unknown labels, and unknown presets
  throw with the known set listed; nothing renders a plausible wrong frame.

## The shape of the package

```
src/
  common/          # rendering + runtime entries shared by every consumer:
                   #   cadScene (scene build), renderMeshScene/renderModel/
                   #   renderOptions (stills), headlessRenderEntry (the
                   #   snapshot browser bundle's entrypoint),
                   #   kinematicsRuntime + kinematicsModule (FK + sidecar ->
                   #   pose definition), animationRuntime (clips),
                   #   stepModule/stepModuleEffects (effects application),
                   #   source (render-source loading), themeSettings,
                   #   displaySettings, stepTopology
  lib/             # subsystems: surf/ (tessellation + caches), selectors/
                   #   (ref runtime), assembly/ (package composition),
                   #   render/ (format mesh loaders), viewer/ (exploded
                   #   view, part visual state), urdf/ (robot loading),
                   #   export/ (packageMeshExport), cadRefs (grammar,
                   #   parity-tested against cad_ref_syntax.py)
bin/               # node builders the bundler ships into _runtime/node:
                   #   mesh-export.mjs (the ONE mesh path), dxf-mesh.mjs
docs/              # subsystem docs (render-pipeline.md)
```

Contract mirrors that must stay in lockstep (each has a sync test):
`lib/cadRefs.js` ↔ `cadgen/cad_ref_syntax.py`;
`common/kinematicsRuntime.js` ↔ `cadgen/_internal/kinematics_fk.py`;
tessellation cache keys ↔ `cadgen/_internal/cache_paths.py`;
`apps/viewer/server/store_paths.py` ↔ `cadgen/_internal/`
schema constants.

Browser mesh-cache traffic is best effort and unrestricted in size, but it
must reach its host without passing through a debugging transport: an
intercepted request's body is handed to the driver as escaped text in one
message, which a large tessellation overruns. `createHttpTessellationCacheProvider`
therefore takes an `origin` for hosts whose cache is not on the page's own
origin (the snapshot renderer's loopback asset server passes one; the viewer
serves the cache itself and leaves it empty). Batched reads are split by key
count and by the bytes the host returns per entry, so no single response has
to be allocated whole.

Scene geometry is the tessellator's INDEXED output: a surf component's
meshData shares the tessellation's vertex, normal and index buffers by
reference (a decoded `.tess` cache entry is copied out of its one entry
buffer) and is never expanded per triangle corner. CAD edges are not a
surface shader: `surfMeshData.js` emits per-class line segments
(`cadEdgeSegments` + `cadEdgeClassRanges`, from the same tessellation's
boundary polylines) and `cadScene.js` draws them through the line pass as one
`LineSegments2` per record and edge class, so `display.edges.classes` styles
colour, opacity and thickness per class and the lines ride the record's
transform, visibility, highlight and tube deformation exactly like the
GLB-era derived edges. One line geometry per component and class is shared by
every occurrence. Effects that change vertex positions or normals acquire
writable attributes before deforming them; material refreshes leave component
data unchanged. This keeps large assemblies from duplicating these buffers for
display. Assemblies keep geometry in their component buffers; they allocate no
combined copy of all positions, normals and indices. Rendering and section
views visit the placed components directly, and the Viewer accepts that
component geometry.

## Working on cadgen-js

- `npm --prefix packages/cadgen-js test` (node:test; no browser needed).
- Anything here that the bundlers consume changes the shipped runtimes:
  run `scripts/bundle/bundle.sh` and commit the regenerated `_runtime/node`
  and `_runtime/browser`. The staleness gate in CI enforces this.
- The viewer dev server aliases this package's source, and Vite's
  transform cache can outlive HMR — if an edit doesn't show up, restart
  the dev server and delete `apps/viewer/node_modules/.vite`.

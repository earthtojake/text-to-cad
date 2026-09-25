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
  (`<name>.step.json`), and the cache — never source, never a build. The
  code in this package must be writable against exactly those inputs.
- **Kinematics is data, choreography is JS, independently**: the FK
  evaluator (`kinematicsRuntime.js`) folds sidecar mate data into
  transforms and is the operation-for-operation twin of the Python
  evaluator (`cadgen/_internal/kinematics_fk.py`) — a viewer slider and an
  exported bake agree to the bit. The animation runtime
  (`animationRuntime.js`) evaluates the sidecar's copied `.anim.js` text
  with the `m.get(target)` handle contract (premultiplying calls, reset to
  rest every frame, pure in t). Neither half references the other; they
  meet only in the effect records.
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

## Working on cadgen-js

- `npm --prefix packages/cadgen-js test` (node:test; no browser needed).
- Anything here that the bundlers consume changes the shipped runtimes:
  run `scripts/bundle/bundle.sh` and commit the regenerated `_runtime/node`
  and `_runtime/browser`. The staleness gate in CI enforces this.
- The viewer dev server aliases this package's source, and Vite's
  transform cache can outlive HMR — if an edit doesn't show up, restart
  the dev server and delete `apps/viewer/node_modules/.vite`.

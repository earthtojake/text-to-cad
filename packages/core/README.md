# @hardcore/core

The shared JavaScript half of cadgen: everything the distribution and its
clients both need to turn cached geometry into pixels, meshes, and motion.
Its source builds to ordinary ESM and package-owned declarations in `dist/`.
Apps and UI import those exports by name; Node and snapshot bundlers carry
self-contained outputs in the Python distribution. No consumer aliases this
package's source or supplies ambient module declarations.

This migration is a pure refactor: exported geometry, rendering, animation,
cache formats and all app UI/UX and functionality remain unchanged.

**May depend on:** Three.js, meshoptimizer and framework-independent helpers.
Never React, ReactDOM, Electron, Next.js, UI or application source. Browser
entry points must not import Node-only code. Node builders remain in `bin/`.

**Consumers:** `@hardcore/ui`, the docs, web and desktop apps, and the runtime
bundlers. `@hardcore/core/client` communicates with `cadgen.viewer` over HTTP;
that protocol relationship does not import Python or discover an interpreter.

## The laws that live here

- **Viewer document boundary**: a client renders from the file, its optional
  kinematics sidecar (`<name>.step.json`), its optional authored render module
  (`<name>.step.js`), and the cache — never model source, never a build. The
  code in this package must be writable against exactly those inputs.
- **Kinematics is data, choreography is JS, independently**: the FK
  evaluator (`kinematicsRuntime.js`) folds sidecar mate data into
  transforms and is the operation-for-operation twin of the Python
  evaluator (`cadgen/_internal/kinematics_fk.py`) — a viewer slider and an
  exported bake agree to the bit. The animation runtime
  (`animationRuntime.js`) evaluates clips from the render module beside the
  document with the `m.get(target)` handle contract (premultiplying calls,
  reset to rest every frame, pure in t). Neither half references the other;
  they meet only in the effect records.
- **Byte determinism**: the tessellator and mesh serializers here produce
  the shipped export bytes — same geometry in, same bytes out.
- **Loud failure**: unresolved refs, unknown labels, and unknown presets
  throw with the known set listed; nothing renders a plausible wrong frame.

## The shape of the package

```
src/
  client/          # explicit CAD HTTP client, polling and render-session lifetime
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
`cadgen/store/tess_cache.py` ↔ the tessellation-cache wire format.

## Public modules and lifetimes

Use `@hardcore/core/client`, `/common/*`, `/lib/*` and `/glb/*` exports.
Construct `createCadClient({ origin, workspaceId })` in a host. Construction is
inert; subscriptions start catalog polling. `dispose()` stops polling, aborts
requests and disposes render sessions. Each render session owns its cache
provider, abort signal and worker leases. Root identity comes from the server's
stable `rootId`, not its port. Multiple roots can render concurrently.

## Working on core

Run commands from the repository root:

```sh
npm ci
npm run build:packages
npm test --workspace @hardcore/core
npm run check:boundaries
```

Rebuild packages when changing shared code; app development servers resolve the
compiled exports. Changes consumed by the bundlers require
`scripts/bundle/bundle.sh`, followed by `scripts/bundle/bundle.sh --check`.
Commit regenerated `_runtime/node` and `_runtime/browser`; the web client
runtime is generated for the wheel. Do not change the canonical release
version during a refactor.

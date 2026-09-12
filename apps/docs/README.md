# Docs site

The documentation website (Next.js) — texttocad.dev. A @hardcore/core CLIENT: the
hero and example scenes render real CAD models in the browser through the
same shared runtime the viewer uses.

**PURPOSE** — the public documentation and marketing site.

**MAY DEPEND ON** — compiled `@hardcore/core` exports and this app's own
npm dependencies. Never another app or the running cadgen Python service.
The root npm workspace and lockfile resolve dependencies; no source aliases
or consumer-owned declarations are required.

**DEPENDED ON BY** — nothing in the repo. It is a website, not an install.

The package migration is a pure refactor: the site's UI, UX, functionality, content and static
CAD showcases remain unchanged. Normal development, checks and deployment use
existing static assets and do not start Python. Asset regeneration is still an
explicit operation.

Install from the repository root with `npm ci` (or the docs-only workspace
filter), then `npm run build:docs`. `apps/docs/vercel.json` runs the root
workspace install and build from Vercel's `apps/docs` root directory. Shared
package outputs are built first; production uses the same package exports as
local development.


## Build and deploy

```bash
npm --prefix apps/docs run check    # the CI gate: lint + typecheck + build
```

Deployment is the `Deploy Docs` workflow only. It deploys a ref of this
repository (default `main`; a release passes its own commit, and a past release
is redeployed from its tag). The Vercel project's Root Directory setting (in
Vercel, not this repo) must point at `apps/docs`.

Hero STEP assets under `public/hero/` are a view of the tree behind the
planetary gear STEP (`assembly.json` + each component's `.surf`) plus its
kinematics sidecar and authored `.step.js` render module, committed as PLAIN
files (never LFS — Vercel serves them statically with no backend). Refresh them
after rebuilding the model:

```
python models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py
node apps/docs/scripts/sync-hero-step-assets.mjs   # same CADGEN_CACHE_DIR as the build
```

The sync script asks cadgen for the tree by the STEP's bytes and exports a
view of it, so it never restates a store path. The check script
(`scripts/check-hero-step-assets.mjs`, part of `npm run check`) pins the surf
container and sidecar contracts against @hardcore/core so a schema bump cannot
silently break the hero render.

## The shape of the app

```
src/app/         # routes
src/components/  # site components incl. the CAD hero renderers
src/lib/         # site utilities
public/hero/     # showcase tree view + sidecar, plain files (never LFS)
scripts/         # asset checks
```

## Icon

The `/icon` route contains the animated 3D mark, with play/pause, a speed
slider, five palettes (Blue, Silver, Graphite, Gold and Violet), and PNG/GLB
downloads. Drag to rotate and scroll to zoom. It starts paused when reduced
motion is preferred. The header, browser favicon, shortcut icon and Apple
icon use the static blue mark, without hover animation.

Everything for the icon lives in this app:

- `src/lib/icon/model.mjs`: the Three.js mesh and animation generator.
- `src/lib/icon/stage.mjs`: shared camera, palettes and studio lighting.
- `src/components/icon-playground.tsx`: the interactive preview and PNG render.
- `scripts/icon/`: GLB export, geometry/animation verification and favicon bake.
- `public/icon/icon.glb`: generated before `npm run dev` and `npm run build`,
  ignored by Git. The deployed asset needs neither Git LFS nor `models/`.

The mesh has an icosahedral hub and twenty triangular prongs. Every root
shares the hub's exact face perimeter, including in the contracted pose.
The crowns translate rigidly as their trunks grow and retract in unison.
One GLB clip includes ten contraction cycles and a complete 360° orbit.
At the default 4× playback, a contraction takes 2 seconds and the orbit takes
20 seconds. The fully expanded reference orientation is stored in the GLB.

```bash
npm --prefix apps/docs run icon:generate
npm --prefix apps/docs run icon:verify
```

`npm run check` also generates and verifies the GLB. Verification reloads
the exported file and checks closed meshes, face winding, flush roots, rigid
crowns, contraction endpoints and the full orbit loop.

To refresh both static favicons after editing the model or lighting:

1. Start the docs app and open `/icon`.
2. Download **Blue PNG**. This always renders the fully expanded reference
   pose at 512 × 512 with transparency, regardless of the preview controls.
3. Bake the PNG and multi-size ICO together (requires Pillow):

   ```bash
   python apps/docs/scripts/icon/bake-favicon.py /path/to/icon-blue.png
   ```

Commit both favicon files with the source changes. The PNG renderer runs in
the browser; the hosted page has no filesystem write endpoint.

# Docs site

The documentation website (Next.js) — texttocad.dev. A cadgen-js CLIENT: the
hero and example scenes render real CAD models in the browser through the
same shared runtime the viewer uses.

**PURPOSE** — the public documentation and marketing site.

**MAY DEPEND ON** — `cadgen-js` (source, mapped by `tsconfig.json` and
aliased in `next.config.ts` to `../../packages/cadgen-js/src`) and its own
npm dependencies. Never the viewer, never cadgen Python.

**DEPENDED ON BY** — nothing in the repo. It is a website, not an install.

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
sidecar, committed as PLAIN files (never LFS — Vercel serves them statically
with no backend). Refresh them after rebuilding the model:

```
python models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py
node apps/docs/scripts/sync-hero-step-assets.mjs   # same CADGEN_CACHE_DIR as the build
```

The sync script asks cadgen for the tree by the STEP's bytes and exports a
view of it, so it never restates a store path. The check script
(`scripts/check-hero-step-assets.mjs`, part of `npm run check`) pins the surf
container and sidecar contracts against cadgen-js so a schema bump cannot
silently break the hero render.

## The shape of the app

```
src/app/         # routes
src/components/  # site components incl. the CAD hero renderers
src/lib/         # site utilities
public/hero/     # showcase tree view + sidecar, plain files (never LFS)
scripts/         # asset checks
```

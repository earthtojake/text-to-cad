# Docs site

The documentation website (Next.js) — texttocad.dev. A cadgen-js CLIENT: the
hero and example scenes render real CAD packages in the browser through the
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

Hero STEP assets under `public/hero/` are the model's render package +
sidecar, committed as PLAIN files (never LFS — Vercel serves them statically
with no backend). Refresh them with `scripts/sync-hero-step-assets.mjs`; the
check script (`scripts/check-hero-step-assets.mjs`) pins the surf container
and sidecar contracts against cadgen-js so a schema bump cannot silently
break the hero render.

## The shape of the app

```
src/app/         # routes
src/components/  # site components incl. the CAD hero renderers
src/lib/         # site utilities
public/hero/     # LFS-tracked showcase packages
scripts/         # asset checks
```

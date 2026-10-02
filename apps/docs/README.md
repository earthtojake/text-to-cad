# Docs site

The documentation website (Next.js) — texttocad.dev. A @text-to-cad/core CLIENT: the
hero and example scenes render real CAD models in the browser through the
same shared runtime the viewer uses.

**PURPOSE** — the public documentation and marketing site.

**MAY DEPEND ON** — compiled `@text-to-cad/core` exports and this app's own
npm dependencies. Never another app or the running cadgen Python service.
The root npm workspace and lockfile resolve dependencies; no source aliases
or consumer-owned declarations are required.

**DEPENDED ON BY** — nothing in the repo imports it. It is a website, not an install;
`cadgen mcp` and `cadgen viewer` send their consented analytics to its `/v1` routes over HTTPS.

The package migration is a pure refactor: the site's UI, UX, functionality, content and static
CAD showcases remain unchanged. Normal development, checks and deployment use
existing static assets and do not start Python. Asset regeneration is still an
explicit operation. The hero composes an explicit static HTTP resource provider
from core for descriptors, surfaces and sidecars. It needs no FileViewer host,
Electron services or Python backend; the resource-provider migration keeps its
existing static asset URLs and rendering behavior.

Install from the repository root with `npm ci` (or the docs-only workspace
filter), then `npm run build:docs`. `apps/docs/vercel.json` runs the root
workspace install and build from Vercel's `apps/docs` root directory. Shared
package outputs are built first; production uses the same package exports as
local development.


## Build and deploy

```bash
npm ci --workspace packages/core --workspace apps/docs
npm run build --workspace @text-to-cad/core
npm --prefix apps/docs run check    # the CI gate: lint + typecheck + build
```

Deployment is the `Deploy Docs` workflow only. It deploys a ref of this
repository (default `main`; a release passes its own commit, and a past release
is redeployed from its tag). The Vercel project's Root Directory setting (in
Vercel, not this repo) must point at `apps/docs`.

Hero STEP assets under `public/hero/` are a view of the tree behind the
planetary gear STEP (`assembly.json` + each component's `.surf`) plus its
schema-v9 sidecar with embedded animation, committed as PLAIN files (never LFS — Vercel serves them statically
with no backend). Refresh them after rebuilding the model:

```
python models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py
node apps/docs/scripts/sync-hero-step-assets.mjs   # same CADGEN_CACHE_DIR as the build
```

The sync script asks cadgen for the tree by the STEP's bytes and exports a
view of it, so it never restates a store path. The check script
(`scripts/check-hero-step-assets.mjs`, part of `npm run check`) pins the surf
container and sidecar contracts against @text-to-cad/core so a schema bump cannot
silently break the hero render.

## The shape of the app

```
src/app/         # routes
src/components/  # site components incl. the CAD hero renderers
src/lib/         # site utilities
public/hero/     # showcase tree view + sidecar, plain files (never LFS)
scripts/         # asset checks
```

## Brand and loading icon

The header uses the blue CAD wordmark and favicons use C, both with soft relief shading. The homepage
and repository README use the TEXTTOCAD PNG. `/icon` provides downloadable
C, CAD and TEXTTOCAD SVGs and PNGs, followed by the original animated loading-icon
playground. The original mesh, animation and the shared UI loading assets stay
unchanged.

The vectors in `public/brand/` come from `node scripts/brand/generate-logos.mjs`;
`node scripts/brand/export-logos.mjs` then refreshes the PNGs, favicons and every
app's copy (run both from the repository root). See [the brand recipe](../../scripts/brand/README.md)
for the letters, projection and palette. These are checked-in assets; ordinary
builds do not regenerate them.

The loading-icon playground retains play/pause, speed, five palettes, drag to
rotate, zoom, and PNG/GLB downloads. It starts paused for reduced motion.
Its source remains here:

- `src/lib/icon/model.mjs`: the Three.js mesh and animation generator.
- `src/lib/icon/stage.mjs`: camera, palettes and studio lighting.
- `src/components/icon-playground.tsx`: preview and PNG render.
- `scripts/icon/`: GLB export and geometry/animation verification.
- `public/icon/icon.glb`: generated before dev/build, ignored by Git.

The mesh has an icosahedral hub and twenty triangular prongs with flush roots
and rigid crowns. The GLB carries ten contraction cycles and a complete orbit;
at 4× playback these take two seconds and twenty seconds respectively.

```bash
npm --prefix apps/docs run icon:generate
npm --prefix apps/docs run icon:verify
```

`npm run check` also generates and verifies the GLB, checking closed meshes,
face winding, flush roots, rigid crowns, endpoints and the orbit loop.

## Visual system

The site uses shadcn's neutral light surfaces and the viewer's charcoal dark
surfaces, system sans-serif type, and the same 0.625rem radius scale. Blue primary
actions use muted shades of the logo's pastel blue through shadcn semantic
tokens: #2c7197 in light mode and #30779d in dark mode, with #f5fbff labels.
Text contrast is 5.14:1 and 4.73:1 respectively; the solid darker hover shades
also exceed 4.5:1. Focus rings use a deeper brand blue on white and the logo's
pale highlight on charcoal. All installation Copy buttons use the same blue
primary action style. Install uses the same heading scale as Skills. The header lists Install, Skills
and Plugins, with Install active by default and the active link following the
visible section. Install has one Skills CLI command; Plugins contains only
provider-native installation commands and guidance. Install boxes and explanatory text fill the content width.
Command text remains monospace. The unboxed wordmark and one prominent tagline
sit above the independently framed CAD demo. “100% open source and free.” follows
“Give your agent CAD superpowers.” in blue, using a lighter brand shade on dark
surfaces. The app owns
its tokens and primitives in `src/app/globals.css` and `src/components/ui/`,
without importing another app or the CAD UI package. Keep the palette aligned
with `packages/ui/src/styles/tokens.css` when the viewer's base theme changes.


## api.texttocad.dev: CAD's analytics

The same project answers `api.texttocad.dev` (a second domain on it). Its `/v1`
routes receive CAD's anonymous usage analytics (`cadgen/analytics.py` in
`packages/cadgen`), from the CAD app (`cadgen mcp`) and the browser viewer
(`cadgen viewer`, presentation `browser`); `www.texttocad.dev/v1/...` reaches the same routes. Clients
know only `api.texttocad.dev`, so the receiver can move to another host without
a release of cadgen.

| Route | What it does |
| --- | --- |
| `POST /v1/events` | One batch: `{schema: 1, install, session, version, source, platform, arch, client: {name, version}, presentation, events: [{name: "tool", tool, calls, errors} \| {name: "view", calls} \| {name: "file", file, kind}]}` → `204`. `file` is 16 hex characters, an HMAC of the path under a salt that never leaves the machine: distinct files can be counted, not named. Anything else is `400` and stores nothing (`src/lib/analytics/events.mjs`). |
| `POST /v1/forget` | `{install}`: deletes every row sent under an install id → `204`. `cadgen analytics off` calls it; the random id is the only authority needed. The id rides in the body because Vercel's request logs keep each path beside the caller's IP. |
| `GET /v1/prune` | The daily cron (`vercel.json`): deletes rows older than 13 months. Needs `Authorization: Bearer $CRON_SECRET`. |
| `GET /v1/health` | → `200` |

- **Nothing outside the contract is stored**: unknown fields, tool names that are
  not `cad_*`, free-text strings are refused. No IP address or header is stored.
- **The privacy policy describes this table.** A new field is a change to
  `src/app/privacy-policy/page.tsx` in the same PR.
- **Portable.** `src/lib/analytics/handler.mjs` is a plain `fetch(Request) →
  Response` handler over a store (`insert`, `forget`, `prune`);
  `app/v1/[...route]/route.ts` is all that ties it to Next.js. `postgres.mjs` is
  the store for any Postgres (`DATABASE_URL`, the pooled string); `schema.sql`
  creates its one table. The driver loads on first request, so the build and the
  tests (`npm test`, part of `check`) need no database.

Setup, once: a Postgres database (Neon today) with `schema.sql` run in it; the
domain `api.texttocad.dev` on the docs Vercel project (a DNS-only CNAME at
Cloudflare, like `www`); and the GitHub Actions secrets `DATABASE_URL` (the
pooled connection string) and `CRON_SECRET` (any long random string). `Deploy
Docs` writes those two secrets into the project's production environment
variables on every deploy (`deploy-vercel-app.sh --env-from`), so changing one
is `gh secret set` and a redeploy; it also checks `api.texttocad.dev/v1/health`.
Until it answers, clients drop their batches silently.

What it answers: how many people use CAD (installs: one per machine and OS user,
a new one after an opt-out and back), how often (active days and minutes, from
when rows arrive: a server sends at most once a minute, and only when used), and
on how many files (distinct `file` codes per install). A server nobody used
sends nothing.

```sql
-- daily, weekly and monthly active installs
select count(distinct install_id) filter (where received_at > now() - interval '1 day')   as dau,
       count(distinct install_id) filter (where received_at > now() - interval '7 days')  as wau,
       count(distinct install_id) filter (where received_at > now() - interval '30 days') as mau
from events;

-- how often: active days and active minutes per install, last 30 days
select install_id, count(distinct received_at::date) as active_days,
       count(distinct date_trunc('minute', received_at)) as active_minutes
from events where received_at > now() - interval '30 days' group by 1 order by 2 desc;

-- unique files worked on per install, and by format, last 30 days
select install_id, count(distinct file) as files from events
where event = 'file' and received_at > now() - interval '30 days' group by 1 order by 2 desc;
select kind, count(distinct (install_id, file)) as files from events where event = 'file' group by 1 order by 2 desc;

-- tool calls and failure rate, last 30 days
select tool, sum(calls) as calls, round(100.0 * sum(errors) / sum(calls), 1) as error_pct
from events where event = 'tool' and received_at > now() - interval '30 days'
group by 1 order by 2 desc;
```

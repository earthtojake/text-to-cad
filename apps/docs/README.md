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
hero builds the TEXTTOCAD wordmark in with its animated SVG (sketch, extrude, cut, chamfer,
render), and the repository README shows the same animated SVG. The header slides the CAD wordmark
in at its left once the homepage's TEXTTOCAD has scrolled out of sight (a page without one shows it
throughout), pushing right what follows it: a desktop's section links, a phone's burger. `/icon` plays each
mark's build, with Replay, and provides downloadable C, CAD, TEXTTOCAD and stacked TEXT TO CAD
SVGs, PNGs and animated SVGs, followed by the original animated loading-icon playground.
`LogoBuild` (`src/components/logo-build.tsx`) shows a build: a plain `<img>`, since the animation
is the SVG's own SMIL, inside a `<picture>` whose reduced-motion source is the static mark. The
original mesh, animation and the shared UI loading assets stay unchanged.

The vectors in `public/brand/` come from `node scripts/brand/generate-logos.mjs` and
`node scripts/brand/animate-logos.mjs`; `node scripts/brand/export-logos.mjs` then
refreshes the PNGs, favicons and every app's copy (run all three from the repository root). See [the brand recipe](../../scripts/brand/README.md)
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
pale highlight on charcoal. Every Copy is a plain icon button, one size with the buttons beside the install
message that open it in an app, and each icon button has a tooltip. Install in Codex, the official listing, is
the one blue button. Every button shows a pointer. Every section title
shares one heading scale, and the header lists Overview, Install, Skills and
Contributing, the active link following the visible section; a phone's header has
a burger that drops them down. The header shows the version as its release tag
names it (`v<VERSION>`), on a phone 360px or wider too. Overview opens with Available for
these agents, first so a phone shows it on load: the agents' logos scrolling as
skills.sh's do, skills.sh's logo set in `public/agents/` with Grok's glyph from
Lobe Icons (MIT) in the same tile, each tile blended into the page's background.
A logo leads to its install. Then the plugin's description, which every manifest
and the README's Overview say word for word (`test_plugin_manifests.py` holds
them to one text). Install
leads with the message to send to an agent, monospace like the commands, with buttons that open it
in Claude Code (Claude Desktop), Codex or Cursor, prefilled and unsent, beside Copy; then a sub-section per agent app, its update
and remove commands folded under Update or reinstall; Codex leads with a button to its listing in
Codex's plugin directory, its commands, update and remove folded under Manual install. Other Agents
(the Skills CLI) for the rest, and Request Plugin, a new GitHub issue. Contributing closes the page. Install boxes and explanatory text fill the
content width. Command text remains monospace.

The homepage and the repository README share their structure and are changed
together: the plugin's description, the install message,
each install's commands (to install, update and remove it), the skills and
Contributing. Both speak to whoever installs text-to-cad, a person or their agent,
and the README says more: numbered steps to install it yourself and fuller notes
under each install. The site has the
hero and the agents carousel. The page's copy lives in `src/lib/content.ts`, which `/llms.txt`
(`src/app/llms.txt/route.ts`, the homepage as markdown for agents) renders too.
`/install` redirects to the Install section (`/#install`, `next.config.ts`): the stable address
of the full install instructions, which the CAD app's update button links to.
`tests/python/global/test_plugin_manifests.py` holds the description, the install
message and every install, update and remove command to one text. The unboxed wordmark and one prominent tagline
sit above the independently framed CAD demo. “100% open source and free.” follows
“Give your agent CAD superpowers.” in blue, using a lighter brand shade on dark
surfaces. The app owns
its tokens and primitives in `src/app/globals.css` and `src/components/ui/`,
without importing another app or the CAD UI package. Keep the palette aligned
with `packages/ui/src/styles/tokens.css` when the viewer's base theme changes.


## api.texttocad.dev: the version feed and CAD's analytics

The same project answers `api.texttocad.dev` (a second domain on it). Its `/v1`
routes serve the version feed cadgen's daily check reads (`cadgen/updates.py` in
`packages/cadgen`), and receive CAD's anonymous usage analytics
(`cadgen/analytics.py`), from the CAD app (`cadgen mcp`) and the browser viewer
(`cadgen viewer`, presentation `browser`); `www.texttocad.dev/v1/...` reaches the same routes. Clients
know only `api.texttocad.dev`, so the service can move to another host without
a release of cadgen.

| Route | What it does |
| --- | --- |
| `GET /v1/versions` | The version feed, the same for everyone: `{latest}` → `200`, kept by Vercel's edge until the next deploy (`src/lib/api/versions.mjs`). `latest` is this app's version, which the release stamps from `VERSION`. Only a copy installed by hand reads it; a store's copy never checks. It reads no database. |
| `POST /v1/events` | One batch: `{schema: 2, install, session, version, channel, platform, arch, client: {name, version}, presentation, events: [{name: "tool", tool, calls, errors} \| {name: "view", calls} \| {name: "file", file, kind}]}` → `204`. `channel` is where the install came from, as its package named it: `claude-github`, `codex-github`, `cursor-github`, `gemini-github`, `claude-desktop`, `claude-directory`, `openai-directory`, `cursor-marketplace`, `cursor-directory`, `dev` or `unknown`. A schema 1 batch (cadgen 0.7.7 to 0.7.11) says how the install was made, `source` (`store` or `manual`), in place of `channel`: its rows keep that as `source`, with the channel `unknown`. `file` is 16 hex characters, an HMAC of the path under a salt that never leaves the machine: distinct files can be counted, not named. One event per tool and per `file`, and one `view` at most. Anything else is `400` and stores nothing (`src/lib/api/events.mjs`). The country Vercel places the request in (`x-vercel-ip-country`, from its IP address) adds the install to `countries` once a week and once a month: totals only, never beside the batch. |
| `POST /v1/forget` | `{install}`: deletes every row sent under an install id → `204`. `cadgen analytics off` calls it; the random id is the only authority needed. The id rides in the body because Vercel's request logs keep each path beside the caller's IP. |
| `GET /v1/prune` | The daily cron (`vercel.json`): deletes rows older than 13 months. Needs `Authorization: Bearer $CRON_SECRET`. |
| `GET /v1/health` | → `200`, or `503` naming a missing setting (`DATABASE_URL`, `CRON_SECRET`), or the database's error code when it cannot take a batch (unreachable, or tables missing a column after a schema change that `schema.sql` was not re-run for). `Deploy Docs` checks it. |

- **Every release keeps counting.** The receiver reads every schema a released
  cadgen sends, for as long as that release can still be running: a copy nobody
  updates is counted like a current one. A new schema adds a reader beside the old
  ones in `events.mjs`, and `schema.sql` only ever adds (a column, a default),
  never renames or drops one, so it can run before the deploy while the live
  receiver still writes the columns it knows.
- **Nothing outside the contract is stored**: unknown fields, tool names that are
  not `cad_*`, free-text strings are refused. No IP address is stored, and the one
  header read, the country, is kept only in `countries`' weekly and monthly totals
  (`ZZ` where Vercel could not tell). Those totals are kept indefinitely and an
  opt-out leaves them: nothing in them names an install.
- **No browser posts.** Both POSTs must be `application/json` (`415` otherwise) and
  carry no `Origin` header (`403`): cadgen posts from Python, which sends none, and a
  browser sends one with every POST, a form's, `sendBeacon`'s and a no-cors fetch's
  included. There are no CORS headers.
- **The privacy policy describes this table.** A new field is a change to
  `src/app/privacy-policy/page.tsx` in the same PR.
- **Portable.** `src/lib/api/handler.mjs` is a plain `fetch(Request) →
  Response` handler over a store (`insert`, `seen`, `tally`, `forget`, `prune`, `ready`);
  `app/v1/[...route]/route.ts` is all that ties it to Next.js, and to Vercel (the
  country header). `postgres.mjs` is the store for any Postgres (`DATABASE_URL`,
  the pooled string); `schema.sql` creates its tables. The driver loads on first request, so the build and the
  tests (`npm test`, part of `check`) need no database.

Setup, once: a Postgres database (Neon today) with `schema.sql` run in it; the
domain `api.texttocad.dev` on the docs Vercel project (a DNS-only CNAME at
Cloudflare, like `www`); and two of the project's own production environment
variables, set as Sensitive in the Vercel dashboard: `DATABASE_URL` (the pooled
connection string) and `CRON_SECRET` (any long random string; Vercel sends it to
the prune cron as `Authorization: Bearer …`). Nothing in GitHub holds them. A
changed value takes effect with the next deploy, and `Deploy Docs` checks
`api.texttocad.dev/v1/health`, which answers `503` while either is missing.
A schema change means running `schema.sql` again (it is idempotent, and only
adds) on the database before deploying; a deploy that went out without it fails
that check.

The feed changes with each release, which deploys the site after its PyPI
upload, so `latest` never names a release that cannot be installed yet. Only a
copy installed by hand reads it: a store's copy (`claude-directory`,
`openai-directory`, `cursor-marketplace`) never checks and is never told, since its
store updates it.
A Vercel Firewall rate-limit rule on `/v1/*` (answering `429`) is recommended: a
real client sends at most once a minute per running app, so a per-IP limit well
above that turns a flood away at no cost to real clients.

A client keeps a batch it could not send (offline, a `5xx` while the receiver is
down, a `404` before it is deployed, a firewall's `403` or a `429`) and sends it again
with the next one, for as long as its app runs; a deletion an opt-out owes is asked
for again the same way. It drops only a batch the receiver read and refused (`400`,
`413`, `415` or `422`): that batch would be refused again.

What it answers: how many people use CAD (installs: one per machine and OS user,
a new one after an opt-out and back), how often (active days and minutes, from
when rows arrive: a server sends at most once a minute, and only when used), and
on how many files (distinct `file` codes per install), and where (installs per
country, each ISO week and calendar month, in UTC). A server nobody used sends
nothing.

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

-- where: installs per country this month, and each country's weeks over time
select country, installs from countries
where period = 'month' and starts = date_trunc('month', now() at time zone 'UTC')::date order by 2 desc;
select starts, country, installs from countries where period = 'week' order by 1 desc, 3 desc;
```

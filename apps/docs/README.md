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
`cadgen mcp` and `cadgen viewer` send their telemetry to its `/v1` routes over HTTPS.

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
shares one heading scale. Each title, a section's or an install's, links to its
own anchor (`#install`, `#cursor`), as GitHub's headings do, so following it puts
that address in the bar. The header lists Overview, Install, Skills and
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
in Claude Code (Claude Desktop), Codex or Cursor, prefilled and unsent, beside Copy; under it, one
sentence says what text-to-cad sends and how to turn it off, with the privacy policy (`telemetryNote`:
only what holds for every release that sends anything by default, since a copy that has not updated
reads it too); then a sub-section per agent app, its update
and remove commands folded under Update or reinstall; Codex leads with a button to its listing in
Codex's plugin directory, its commands, update and remove folded under Manual install. Other Agents
(the Skills CLI) for the rest, and Request Plugin, a new GitHub issue. Contributing closes the page. Install boxes and explanatory text fill the
content width. Command text remains monospace.

The homepage and the repository README share their structure and are changed
together: the plugin's description, the install message and what it sends,
each install's commands (to install, update and remove it), the skills and
Contributing. Both speak to whoever installs text-to-cad, a person or their agent,
and the README says more: numbered steps to install it yourself and fuller notes
under each install. The site has the
hero and the agents carousel. The page's copy lives in `src/lib/content.ts`, which `/llms.txt`
(`src/app/llms.txt/route.ts`, the homepage as markdown for agents) renders too.
`/install` redirects to the Install section (`/#install`, `next.config.ts`): the stable address
of the full install instructions, which the CAD app's update button links to.
`tests/python/global/test_plugin_manifests.py` holds the description, the install
message, what it sends and every install, update and remove command to one text. The unboxed wordmark and one prominent tagline
sit above the independently framed CAD demo. “100% open source and free.” follows
“Give your agent CAD superpowers.” in blue, using a lighter brand shade on dark
surfaces. The app owns
its tokens and primitives in `src/app/globals.css` and `src/components/ui/`,
without importing another app or the CAD UI package. Keep the palette aligned
with `packages/ui/src/styles/tokens.css` when the viewer's base theme changes.


## api.texttocad.dev: the version feed and cadgen's telemetry

The same project answers `api.texttocad.dev` (a second domain on it). Its `/v1`
routes serve the version feed cadgen's daily check reads (`cadgen/updates.py` in
`packages/cadgen`), and receive cadgen's telemetry (`cadgen/analytics.py`): the usage
counts the CAD app (`cadgen mcp`), the browser viewer (`cadgen viewer`) and the build
daemon send, which it checks and passes on to PostHog. `www.texttocad.dev/v1/...`
reaches the same routes. Clients know only `api.texttocad.dev`, so the service behind it
can change without a release of cadgen.

| Route | What it does |
| --- | --- |
| `GET /v1/versions` | The version feed, the same for everyone: `{latest}` → `200`, kept by Vercel's edge until the next deploy (`src/lib/api/versions.mjs`). `latest` is this app's version, which the release stamps from `VERSION`. Only a copy installed by hand reads it; a store's copy never checks. It asks no service. |
| `POST /v1/events` | One batch: `{schema: 3, install, session, process, version, channel, platform, arch, client: {name, version}, presentation, events: [...]}` → `204`, once PostHog has taken it. `process` is the sender: `app` (the CAD app), `viewer` (the browser viewer) or `daemon` (the build daemon, which names no `client` or `presentation`). `channel` is where the install came from, as its package named it: `claude-github`, `codex-github`, `cursor-github`, `gemini-github`, `claude-desktop`, `claude-directory`, `openai-directory`, `cursor-marketplace`, `agent-plugins`, `dev` or `unknown`. Each event counts what the process saw since its last batch, one event per thing counted (`FIELDS` in `src/lib/api/events.mjs`): `tool` `{tool, calls, errors}`; `view` `{calls}`; `files` `{kind, count}`, distinct files of a format shown for the first time that day; `build` `{kind, via, count, failed, crashed, cancelled, cached, seconds, longest}`, builds of a format by who asked (`script` or `command`); `snapshot` `{kind, count, failed, seconds}`; `feature` `{feature, count}` (`assembly`, `declared_mesh`, `kinematics`, `animation`, `drawing`, `quick_edit`); `health` `{workers, crashes, recycles, refusals}`, the daemon's build workers; `exception` `{where, tool?, type, handled, status?, frames: [{file, function, line?, column?}], count}`, one crash and how many times it happened: where (`tool`, `route`, `request`, `build`, `command` or `page`), the error's type, whether the process went on, and up to 30 innermost frames, each a file inside cadgen, the standard library, a dependency or the page's assets (never an absolute path, `..` or a drive), with the person's own code `<user>`; a dead worker's exit status in `status`. Never a message. Schemas 1 and 2 (cadgen 0.7.7 to 0.7.15) are read too: they name no `process` (the browser viewer's `presentation` was `browser`; anything else was the CAD app), a schema 1 batch says how the install was made (`source`: `store` or `manual`) in place of `channel`, and their `file` event named one distinct file by a salted code, of which the receiver passes on the format alone, as `files`. Anything else is `400` and passes nothing on. |
| `POST /v1/forget` | `{install}`: deletes the install's person in PostHog and every event sent under its id → `204` once PostHog has queued it (it deletes in the background). `cadgen telemetry off` calls it; the random id is the only authority needed. The id rides in the body because Vercel's request logs keep each path beside the caller's IP. |
| `GET /v1/health` | → `200`, or `503` naming a missing or malformed setting (`POSTHOG_REGION`, `POSTHOG_PROJECT_KEY`, `POSTHOG_PERSONAL_KEY`, `POSTHOG_PROJECT_ID`), or PostHog's status when it will not take the personal key for the project. `Deploy Docs` checks it. |

Each event of a batch becomes one PostHog event (`src/lib/api/posthog.mjs`): `tool_used`,
`view_used`, `files_shown`, `models_built`, `snapshots_rendered`, `feature_used`,
`daemon_health` or, for a crash, `$exception`, which PostHog's error tracking groups into
issues (`$exception_list`: the type, a value that is only ever a dead worker's exit
status, `mechanism.handled`, and raw frames, only cadgen's own or the page's `in_app`),
with the install id as its distinct id, the batch's context (`session`,
`process`, `version`, `channel`, `source`, `platform`, `arch`, `client`, `client_version`,
`presentation`) and the event's own counts as properties, and `country`: the ISO code
Vercel places the request in (`x-vercel-ip-country`), left out where it cannot tell.
PostHog's own location lookup is off for every event (`$geoip_disable`): the receiver
posts from Vercel's servers, and nothing finer than the country is wanted. An event is a
window's counts, so a question adds up a property (`calls`, `count`, `seconds`): it never
counts events.

- **Every release keeps counting.** The receiver reads every schema a released
  cadgen sends, for as long as that release can still be running: a copy nobody
  updates is counted like a current one. A new schema adds a reader beside the old
  ones in `events.mjs`.
- **Nothing outside the contract is passed on**: unknown fields, tool names that are
  not `cad_*`, names outside an event's vocabulary, free-text strings are refused. The receiver keeps no IP address, and
  sends PostHog none.
- **No browser posts.** Both POSTs must be `application/json` (`415` otherwise) and
  carry no `Origin` header (`403`): cadgen posts from Python, which sends none, and a
  browser sends one with every POST, a form's, `sendBeacon`'s and a no-cors fetch's included.
  There are no CORS headers.
- **The privacy policy describes these events.** A new field is a change to
  `src/app/privacy-policy/page.tsx` in the same PR.
- **Portable.** `src/lib/api/handler.mjs` is a plain `fetch(Request) → Response` handler
  over a store (`insert`, `forget`, `ready`); `posthog.mjs` is PostHog's, and
  `app/v1/[...route]/route.ts` is all that ties it to Next.js, and to Vercel (the
  country header). The tests (`npm test`, part of `check`) hand the store a `fetch` of
  their own, so they need no network.

Setup, once: a PostHog project; the domain `api.texttocad.dev` on the docs Vercel
project (a DNS-only CNAME at Cloudflare, like `www`); and four of the project's own
production environment variables, set as Sensitive in the Vercel dashboard:
`POSTHOG_REGION` (`us` or `eu`, where the PostHog project lives),
`POSTHOG_PROJECT_KEY` (the project's API key, which captures), `POSTHOG_PERSONAL_KEY`
(a personal API key with `person:write`, which deletes, and `project:read`, which health
checks the project with; scope it to this project alone), and
`POSTHOG_PROJECT_ID`. Nothing in GitHub holds them. A changed value takes effect with
the next deploy, and `Deploy Docs` checks `api.texttocad.dev/v1/health`, which answers
`503` while any is missing or PostHog refuses the personal key.

Retention is PostHog's: events go after the period its plan keeps them (a year on the
free plan), and the privacy policy says so.

The feed changes with each release, which deploys the site after its PyPI
upload, so `latest` never names a release that cannot be installed yet. Only a
copy installed by hand reads it: a store's copy (`claude-directory`,
`openai-directory`, `cursor-marketplace`) never checks and is never told, since its
store updates it.
A Vercel Firewall rate-limit rule on `/v1/*` (answering `429`) is recommended: a
real client sends at most once every five minutes per running process, and once more
as it exits, so a per-IP limit well above that turns a flood away at no cost to real
clients.

A client keeps a batch it could not send (offline, a `5xx` while the receiver or
PostHog is down, a `404` before it is deployed, a firewall's `403` or a `429`) and sends
it again with the next one, for as long as its process runs; a deletion an opt-out owes is
asked for again the same way. It drops only a batch the receiver read and refused
(`400`, `413`, `415` or `422`): that batch would be refused again.

What it answers, in PostHog: how many people use CAD (installs: one per machine and OS
user, a new one after an opt-out and back), how often (active days, from when events
arrive: a process sends at most every five minutes, and only when used), which CAD tools
are used and how often they fail (`tool_used`: sum of `calls` and `errors` by `tool`), on
how many files (`files_shown`: sum of `count` by `kind`, each file once a day per
process), how many models are built and how that goes (`models_built`: sums of `count`,
`failed`, `crashed`, `cancelled`, `cached` and `seconds` by `kind` and `via`, and the
largest `longest`), snapshots likewise (`snapshots_rendered`), which features are used
(`feature_used`), how the daemon's workers fare (`daemon_health`), and where (installs by
`country`). A process nobody used sends nothing.

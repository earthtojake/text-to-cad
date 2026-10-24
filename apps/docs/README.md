# Docs site

The documentation website (Next.js) — texttocad.dev. A @text-to-cad/core CLIENT: the
hero and example scenes render real CAD models in the browser through the
same shared runtime the viewer uses.

**PURPOSE** — the public documentation and marketing site.

**MAY DEPEND ON** — compiled `@text-to-cad/core` exports and this app's own
npm dependencies. Never another app or the running cadgen Python service.
The root npm workspace and lockfile resolve dependencies; no source aliases
or consumer-owned declarations are required.

**DEPENDED ON BY** — nothing in the repo imports it. It is a website, not an install.
`api.texttocad.dev`, which cadgen talks to, is its own project: [`apps/api`](../api/README.md).

Normal development, checks and deployment use existing static assets and do not
start Python; regenerating an asset is an explicit operation. The hero reads one
static GLB with core's GLB path, the CAD Viewer's, and plays its clip with core's
GLB animation runtime. It needs no FileViewer host, Electron services or Python
backend.

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

The hero is one GLB, `public/hero/planetary.glb`: the planetary gear model
(`models/assemblies/src/planetary_gear_assembly/`) exported from its document by
`cadgen export`, its parts, colours and its `meshCycle` motion, which the export bakes
into a clip. It is committed as a PLAIN file (never LFS: Vercel serves it statically
with no backend). The page frames it, draws each part's folds and outline in the
hero's edge colour, and plays the clip slowed to a display pace. Refresh it after
changing the model:

```
node apps/docs/scripts/sync-hero-glb.mjs
```

The sync script builds the model with this checkout's cadgen (`PYTHON_BIN`, default the
repository's `.venv`), exports the document the model wrote, and runs the check. The check
script (`scripts/check-hero-glb.mjs`, part of `npm run check`) holds the GLB to the
model's source (the motion's name, duration and loop) and to the page (the clip it
plays), then reads it and plays the clip through @text-to-cad/core's GLB path, so an
export or format change cannot silently break the hero.

## The shape of the app

```
src/app/         # routes
src/components/  # site components incl. the CAD hero renderers
src/lib/         # site utilities
public/hero/     # the hero's GLB, a plain file (never LFS)
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
them to one text), and How it works: three steps from a model's script to the CAD viewer
(`howItWorks`), the README's How it works. Install
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
together: the plugin's description, how it works, the install message and what
it sends, each install's commands (to install, update and remove it), the skills and
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


## api.texttocad.dev

cadgen's version feed and its telemetry receiver are their own Vercel project:
[`apps/api/README.md`](../api/README.md). This site's part is the privacy policy
(`src/app/privacy-policy/page.tsx`), which describes every event the receiver passes
on: a new field is a change to it in the same PR.

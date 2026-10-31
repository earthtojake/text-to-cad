# Docs site

The documentation website (Next.js) — texttocad.dev. A @text-to-cad/core CLIENT: the
hero and example scenes render real CAD models in the browser through the
same shared runtime the viewer uses.

**PURPOSE** — the public documentation and marketing site.

**MAY DEPEND ON** — compiled `@text-to-cad/core` exports and this app's own
npm dependencies. Never another app or the running CAD server.
The root npm workspace and lockfile resolve dependencies; no source aliases
or consumer-owned declarations are required.

**DEPENDED ON BY** — nothing in the repo imports it. It is a website, not an install.
`api.texttocad.dev`, which the CAD server talks to, is its own project: [`apps/api`](../api/README.md).

Normal development, checks and deployment use existing static assets and do not
start Python; regenerating an asset is an explicit operation. The hero reads one
static GLB with core's GLB path, the CAD Viewer's, and plays its clip with core's
GLB animation runtime. It needs no FileViewer host or Python backend.

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
`cad export`, its parts, colours and its `meshCycle` motion, which the export bakes
into a clip. It is committed as a PLAIN file (never LFS: Vercel serves it statically
with no backend), one of the few CAD files Git holds
(`tests/python/global/test_no_cad_assets_tracked.py` lists it, with a size cap). The page
frames it, draws each part's folds and outline in the hero's edge colour, and plays the
clip slowed to a display pace. The site and its checks read only that committed file;
nothing in the docs app's build or `npm run check` reads the sample corpus. Refresh it
by hand after changing the model using `cad export`. Preserve the `meshCycle`
clip and verify playback before committing the refreshed GLB.

## The shape of the app

```
src/app/         # routes
src/components/  # site components incl. the CAD hero renderers
src/lib/         # site utilities
public/hero/     # the hero's GLB, a plain file (never LFS)
scripts/         # loading-icon export and verification
```

## Brand and loading icon

The header always shows the C mark (`public/brand/logo-c.svg`) and the name, text-to-cad, at its
left, one link home, and favicons use C, both with soft relief shading.
The homepage hero builds the TEXTTOCAD wordmark in with its animated SVG (sketch, extrude, cut,
chamfer, render), and the repository README shows the same animated SVG. `/icon` plays each
mark's build, with Replay, and provides downloadable C, CAD, TEXTTOCAD and stacked TEXT TO CAD
SVGs, PNGs and animated SVGs, followed by the original animated loading-icon playground.
`LogoBuild` (`src/components/logo-build.tsx`) shows a build: a plain `<img>`, since the animation
is the SVG's own SMIL, inside a `<picture>` whose reduced-motion source is the static mark. The
original mesh, animation and the shared UI loading assets stay unchanged.

The source vectors are committed in `public/brand/`. After editing them, run
`node scripts/brand/export-logos.mjs` from the repository root to refresh PNGs,
favicons and app copies. See [the export instructions](../../scripts/brand/README.md).
Artwork authoring stays local; ordinary builds use the committed assets.

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
pale highlight on charcoal. Every Copy is a plain icon button, and each icon button has a tooltip.
Every button shows a pointer. Every section title
shares one heading scale. Each section title links to its
own anchor (`#skills`), as GitHub's headings do, so following it puts
that address in the bar. The header is bare: at the left the C mark and "text-to-cad" set as a
title (semibold), one link home, on every size and always shown; at the right the version as its
release tag names it (`v<VERSION>`, on a phone 360px or wider) and GitHub with its star count, the
two at one size and weight (text-sm, medium). It has no
section links, no burger, no Discord link and no theme toggle: the site follows the system's light
or dark theme, on load and as it changes (`layout.tsx`'s theme script sets the `.dark` class).

The hero is centred: the TEXTTOCAD wordmark at full size (up to 800px), the tagline, then the two
calls to action, the site's own outline Buttons at one neutral style (GitHub with a divider and its
star count, Join Discord; `src/components/hero-section.tsx`, the links and the star count from
`src/lib/github.ts`, which the header shares). Then the one-line install box, which is the page's
Install and carries its stable address, `#install` (`src/components/install-box.tsx`: the ONE-LINE
INSTALL label, a macOS / Linux | Windows toggle over `installCommands`, the command with Copy; a
Windows browser has Windows preselected), with nothing under it: what the command does
(`installSummary`) and the link to installing by hand, app by app, and updates, the repository's
`docs/install.md` (`manualInstall`), are in the README's Quickstart and `/llms.txt`, not on the
homepage. Then the framed CAD demo, then a small
uppercase label, WORKS WITH THESE AGENTS, over the agents' logos (no section title): the logos
scrolling as skills.sh's do, skills.sh's logo set in `public/agents/` with Grok's glyph from Lobe
Icons (MIT) in the same tile, each tile blended into the page's background. The logos are not
links; under them one line asks for a plugin request (a new GitHub issue). Overview has the
plugin's description, which every manifest and the README's Overview say word for word
(`test_plugin_manifests.py` holds them to one text), and How it works: three steps from a model's
script to the CAD viewer (`howItWorks`), the README's How it works. Then Skills. The site has no
Install section, no per-app install of its own and no telemetry note: the privacy policy, linked
from the footer and from `/llms.txt`, says what is sent and how to turn it off. Contributing closes
the page (`contributing`, the README's Contributing in substance): its intro, then each way to take
part, bugs and plugin requests, questions and ideas, and code, skills and models, with
its links. The footer links the privacy policy and the terms of service, then Made by @earthtojake.
Explanatory
text fill the content width. Command text remains monospace.

The homepage and the repository README share their structure and are changed
together: the plugin's description, how it works, the install commands, what they
do, the link to installing by hand, the skills and Contributing. Updates are on
`docs/install.md`, with each app's own commands, which both link, and the telemetry in full is
the privacy policy. The site has the hero and the agents carousel. The page's copy lives in
`src/lib/content.ts`, which `/llms.txt`
(`src/app/llms.txt/route.ts`, the homepage as markdown for agents) renders too.
`/install` redirects to the hero's install box (`/#install`, `next.config.ts`): the stable address
of the install instructions.
`tests/python/global/test_plugin_manifests.py` holds the description, the install
commands, what they do and the link to installing by hand to one text, and holds the `#install`
anchor to the hero. The unboxed
wordmark and one prominent tagline, centred, sit above the two calls to action, the install box and the
independently framed CAD demo. “100% open source and free.” follows
“Design physical products with AI.” in blue, using a lighter brand shade on dark
surfaces. The app owns
its tokens and primitives in `src/app/globals.css` and `src/components/ui/`,
without importing another app or the CAD UI package. Keep the palette aligned
with `packages/ui/src/styles/tokens.css` when the viewer's base theme changes.


## Social previews

`public/social-preview-products.png` is the static share image, paired with
`public/social-preview-products.mp4`: a 12-second, 1200×630 recording of the
animated TEXTTOCAD SVG and the planetary GLB's existing `meshCycle` clip
at half speed. The recording uses the real exported model at `public/hero/planetary.glb`.
The composition uses a large animated wordmark, the byline “Design physical
products with AI.”, the blue subtitle “100% open source and free.”, and an enlarged
gear assembly. Both text blocks use the same font size. A smooth caret-led mask
reveals the typeset lines at 60 fps, preserving kerning. The byline begins at
2.35 seconds and finishes at 3.35; after a 0.2-second pause, the subtitle begins
at 3.55 and finishes at 4.42. The caret fades between lines and disappears when
finished. The gears fade and scale in over 0.65 seconds from the byline's start,
during the SVG's build animation. `[[ texttocad.dev ]]` sits in the bottom-left
corner at 25px, with the two text blocks raised to balance the space. It reveals
from 4.62 to 5.22 seconds, 0.2 seconds after the subtitle finishes, with a matching
caret. There are no format labels.
It is made for link previews rather than captured from the homepage.

`src/app/layout.tsx` declares the image fallback and the direct MP4 through
Open Graph video metadata. Video playback depends on the receiving client;
the X card remains a large-image card. Keep the MP4 below the repository's
5 MiB file limit, use H.264/yuv420p with fast-start metadata, and preserve the
image fallback. Rename preview assets when replacing them so social caches
can fetch the new versions; update the structured-data image in `src/app/page.tsx`
as well.

## api.texttocad.dev

The version feed and the telemetry receiver are their own Vercel project:
[`apps/api/README.md`](../api/README.md). This site's part is the privacy policy
(`src/app/privacy-policy/page.tsx`), which describes every event the receiver passes
on: a new field is a change to it in the same PR.

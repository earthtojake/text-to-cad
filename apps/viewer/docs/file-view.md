# Embedding the file view

`<CadFileView>` is the CAD Viewer's per-file surface — the render pane, the
floating toolbar, the file sheets (STEP, mesh, URDF/SRDF/SDF, DXF), the theme
editor panel, the loading overlay, the status toasts and the alert dialog —
for exactly one file. The panels are drawn in a right-hand column of its own,
or in the host's ("Where the panels are drawn"). The standalone viewer's shell
(`src/client/components/CadWorkspace.js`) is one consumer; a host application
(the desktop app's explorer tab) is the other. There is one implementation.

What it is NOT: the workspace top bar, the file sidebar and the home screen.
Those are chrome around the surface, and a host that wants them injects them
through the render slots below.

## The entry point

```js
import { CadFileView } from "cad-viewer/file-view";
```

This package exports `./file-view` as **source**, not a build. The consumer's
bundler compiles it, so the settings below are not optional — a missing one is
a build error or, worse, a silently unstyled surface.

## Props

| Prop | Default | Meaning |
| --- | --- | --- |
| `origin` | `""` | The `cadgen viewer` backend to talk to. `""` means same origin (the standalone case). A host passes the absolute origin of the instance it spawned, e.g. `"http://127.0.0.1:3250"`. |
| `file` | `""` | The served-root-relative path of the file to show — the same value the standalone viewer keeps in `?file=`. Empty renders the surface with nothing open. |
| `onOpenFile` | — | `(path, { history }) => void`. Called when the surface wants to be pointed at another file: a linked STEP, an entry picked out of injected chrome, or the surface settling on the configured default file. The host is expected to feed the new path back in as `file`. |
| `className` | `""` | Merged onto the surface's root (`tailwind-merge`, so `h-full` beats the default `h-svh`). |
| `catalog` | `null` | `{ entries, revision, hydrated, refreshing, error }` when the host already subscribes to the catalog. Omit it and the surface reads the store for `origin` itself — which is all an embedded consumer needs. |
| `manageDocumentTitle` | `true` | Whether the surface writes `document.title`. Pass `false` from a host that owns its own window. |
| `renderTopBar` / `renderSidebar` / `renderHome` | `null` | Render slots for injected chrome; each is called with the `chrome` object and placed in the surface's layout. Omit all three for a bare file surface. Without `renderSidebar` there is no sidebar and the viewport owns the full width. |
| `layout` | `"auto"` | `"desktop"` pins the desktop layout — the file sheet is a column beside the model, never a drawer over it — however narrow the root is. `"auto"` measures the root and picks desktop or compact. |
| `fileSheetWidth` | `null` | The sheet's width in px, when the host sizes it for its pane. Clamped to the sheet's own range (240–448) and not resizable from inside the surface. `null` uses the stored width. Ignored when `panelSlot` is given — the host's frame owns the width then. |
| `panelSlot` | `null` | A DOM element the open panel's content is drawn into. Given one, the surface portals the theme editor or the file sheet there and draws no column of its own; without one it draws the column, which is the standalone case. See "Where the panels are drawn". |
| `colorScheme` | `null` | `"light"` or `"dark"`: the host's resolved colour scheme, which is the chrome's light/dark. The CAD "system" theme resolves the same way — its light/dark half and the background it borrows from the host's chrome — and the surface stops writing `.dark` / `color-scheme` to the document, because the host owns those. `null` is the standalone case: the surface follows its own colour-scheme preference and the OS, and writes the document itself. Never the CAD theme, in either case: see "Theme is the scene". |
| `selectReference` | `null` | `{ selector, key }`: select a reference — `o1.2`, `label.f45`, `bracket`, a comma-separated list (its first member) — once the model is up. Applied once per `key`; a new `key` selects again. See "References and captures". |
| `onReference` | `null` | `({ file, selector, text }) => void`. Called for every reference the person copies out of the surface, beside the clipboard write. `null` (standalone) means the clipboard alone. |
| `onCapture` | `null` | `({ blob, file }) => void`. Given, the floating toolbar shows a camera button that renders the viewport to a PNG and hands it over; `null` shows no button. |
| `captureRequest` | `null` | `{ key }`: take that same capture now, asked for from outside the viewport. Applied once per `key`, like `selectReference`; the picture goes to `onCapture`. |
| `themeEditing` / `onThemeEditingChange` | `null` / — | The theme panel's open flag, and every change to it. A boolean makes the panel controlled; `null` leaves it to the surface. See "Driving the panels from a host". |
| `fileSheetOpen` / `onFileSheetOpenChange` | `null` / — | The file sheet's open flag and its changes, the same way. |

`origin` is also published through context:

```js
import { ViewerOriginProvider, useViewerOrigin } from "cad-viewer/file-view";
```

`<CadFileView>` provides it for its own subtree; `useViewerOrigin()` is how any
component under it builds a backend URL. `packages/cadgen-js` stays React-free
and takes the origin as a plain argument instead.

The surface also installs cadgen-js's shared **tessellation cache provider**
for its origin when it mounts (`hostTessellationCache.js`): a package load asks
`origin`'s `/__tess_cache/batch` once for every component before tessellating,
and writes the misses back after the load has gone quiet, so a component
tessellated once is a cache hit on every later open, in the standalone viewer
and in a host alike. A host does nothing for this beyond passing `origin`; the
provider is per page, and the last surface mounted owns it, which is safe
because every `cadgen viewer` reads and writes the one store.

## References and captures

The surface copies references — the render pane's Copy Reference button, the
tree's and the viewport's context menus, the reference sheet's copy buttons,
the file menu's Copy Link — to the clipboard, and standalone that is the end
of it. A host usually wants them somewhere of its own (the desktop app's
composer), so every one of those sites also calls `onReference` when the host
gives one, once per copied line:

```js
{ file: "parts/STEP/bracket.step", selector: "o1.2", text: "bracket.step#o1.2" }
```

`file` is the served-root-relative path of the file the reference belongs to
(what `?file=` would carry), always in full — the prefix on the copied `text`
is the viewer's shortest-unique suffix, right for a prompt and wrong for a
host that wants to open the file. `selector` is the half after `#` without
it, `""` for a whole file. Copy Link hands over the file with no selector
rather than the URL: a viewer link is the one thing an agent inside a host
cannot use. `hostReference.js` holds the parser (`referenceFromCopyText`,
exported from the entry) and the context the sheet's copy buttons read.

`onCapture` is the other direction for pictures: given, the floating toolbar
gains a camera button ("Send view to chat") beside Copy screenshot, and
clicking it renders the current viewport — the same composite the clipboard
gets, drawings included — to a PNG `Blob` and calls `onCapture({ blob, file })`.
Without it there is no button; standalone there is no chat.

`captureRequest` is that same button pressed from outside the viewport: the
host holds a nonce (`{ key }`) and bumps it, and the surface takes one
picture per new key and hands it to `onCapture` exactly as the button does.
The desktop app's composer offers `Capture from viewer` in its `+` menu
this way, so there is one capture path and not two.

`selectReference` goes the other way: a host holding a reference from
elsewhere (a link in a transcript) asks the surface to select it. The
selector is resolved against what is loaded — the reference map for
entities, the tree for occurrences by id, name or label, and `label.f45`
through the labelled node's occurrence (`resolveSelectorSelection`) — and
applied through the same `toggleReferenceSelection` / `togglePartSelection`
a click uses, so the sheet reveals it and the copy button names it. It is
applied once per `key`, when it first resolves: the maps fill as the model
and its topology arrive, so a selector for a face not yet loaded waits for
the next change rather than being dropped, and one already selected is
revealed, not toggled off. Pass a new `key` to select the same reference
again.

## Driving the panels from a host

The surface has two right-hand panels — the **theme editor** and the file's
own sheet (STEP, mesh, URDF/SRDF/SDF, DXF) — and they are one panel with two
contents: one width, one resize handle, one inset on the 3D viewport. So
opening either closes the other, and the surface enforces that wherever a
panel is opened.

That second panel is `fileSheet*` in this contract and in the code. What a
person is shown calling it is the app's to choose: standalone its toggle is
named for the file it is reading ("Expand STEP details"), and the desktop app
calls it the **Inspector**. Renaming it here would rename a prop.

Standalone, the workspace top bar carries a toggle for each and the surface
keeps both flags. A host that hides that top bar — `layout="desktop"` does —
has to draw its own toggles, and a toggle needs to know whether its panel is
open. Four props make that possible:

```jsx
<CadFileView
  themeEditing={themeOpen}
  onThemeEditingChange={setThemeOpen}
  fileSheetOpen={sheetOpen}
  onFileSheetOpenChange={setSheetOpen}
  …
/>
```

- **A boolean makes that panel controlled.** The surface stops keeping its own
  flag for it and reads the prop instead, so the host's state is the one
  answer. `null`/omitted is uncontrolled and is the standalone case, unchanged.
- **A callback with no value is *observing*.** The surface still owns the flag
  and reports it, its opening value included — so a host can start at `null`,
  hear what the surface opened with (a STEP file opens with its sheet up, at a
  width the surface decides), echo that back, and be controlling from then on.
  That is one report on mount, not a copy of the default over on the host's
  side. A host with a default of its own — the desktop app decides which of
  its panels a CAD tab opens with — passes booleans from the first render
  instead, and never sees the surface's.
- **The callback fires on every change**, including the changes the surface
  makes itself: opening the sheet reports `themeEditing` false as well as
  `fileSheetOpen` true, and the sheet opens on its own when a measurement
  lands. A host that only ever echoes its callbacks into its own state stays
  in step with the surface without knowing any of those rules.
- **The two are controlled separately.** Controlling one and leaving the other
  alone works: the surface keeps its own flag for whichever it still owns and
  the exclusion still holds across the pair.
- **Nothing new persists.** The theme itself is a user preference and already
  persists in the viewer's own storage; these props are about which panel is
  showing, which is a property of the moment.

A host that ignores its own callback is a host whose toggle does nothing —
the usual bargain of a controlled component. The rule and the resolution live
in `hostPanels.js`, which is pure and tested (`hostPanels.test.js`).

## Where the panels are drawn

Standalone, the surface draws the column those panels sit in: a width, a
border, a resize handle, and an inset on the 3D viewport. A host application
usually has panels of its own beside them — a file tree, an outline — and two
columns of two designs, each with its own width and its own header, is the
first thing a person notices. So a host may hand over the box:

```jsx
const [slot, setSlot] = useState(null);

<aside className="w-72 border-l">     {/* the host's frame: one width, one border */}
  <div className="h-full" ref={setSlot} />
</aside>

<CadFileView panelSlot={slot} … />
```

- **With a slot**, the open panel's content is portaled into it and the
  surface draws no column at all: no aside, no width, no resize handle, no
  drawer in compact mode, and no inset on the viewport — the render pane is
  the whole surface, and the host's pane is what got narrower. The host's
  frame is the only frame, so the panel looks like the host's own chrome.
- **Without one** — `null`, or a ref that has not attached yet — nothing
  changes: the surface draws its column exactly as before.
- **The slot does not decide what is open.** `themeEditing` and
  `fileSheetOpen` still do, and the exclusivity between the two still holds.
  A host that keeps one open panel across its own panels and the surface's
  gets the whole rule for free: at most one of the two props is ever true.
- **Give the slot a box to fill.** The content lays itself out as a flex
  column filling its parent; a slot with no height shows nothing.
- Popovers, menus and toasts still portal to `body` — they are overlays, not
  panels.

The desktop app does exactly this: its file tab has one panel column and one
list of panels — the file tree, the theme editor, the Inspector — with one
toggle each, and the surface's two are drawn in that column.

`normalizeHostPanelSlot` / `resolveHostPanelPlacement` in `hostPanelSlot.js`
are the pure half, tested in `hostPanelSlot.test.js`.

## Theme is the scene

A CAD theme paints the **scene** and nothing else: the background, the
lighting rig, the materials, the linework, the floor and its grid, the
projection. It does not paint chrome — not the panels, not the toolbars, not
the document's light/dark.

That used to be false. The theme's dominant background luminance was read as
a "scene tone" and written onto `documentElement`, so opening a file under a
dark preset repainted every panel and menu on the page, and a light window
over a dark studio was not a thing you could have. The chrome now follows the
app: `colorScheme` when a host passes one, and otherwise the viewer's own
colour-scheme preference resolved against `prefers-color-scheme` — which is
the pair the pre-paint script in `index.html` already used, so the first frame
and every later one agree.

What a theme still reaches, in a host as well as standalone:

- everything in the scene, the background included;
- which colour bucket the theme editor writes to, for a theme whose
  `colorMode` is `"system"`: that follows the app's colour scheme, so editing
  a colour in a light window edits the light one.

### The one theme that follows the app

The theme named **System** is the exception, and it is an exception about the
*background* only. It means "follow the app", so it paints the scene on the
chrome's own ground: the computed `--background` custom property on
`documentElement`, which the standalone viewer's token layer and a host's
both define, with the shadcn neutral pair (`#ffffff` / `#0a0a0a`) written out
as the fallback for a page that has no such token. Its light/dark half comes
from the app's colour scheme — `colorScheme` from a host, the resolved
preference standalone — never from the theme.

Every other preset, and a custom theme, paints the backdrop its own settings
ask for. So picking Cinematic changes the background, in a host exactly as it
does standalone, and switching the app between light and dark then leaves
that background alone.

A host passes nothing for this. The surface reads the token itself
(`chromeBackdrop.js`, pure and tested in `chromeBackdrop.test.js`) and
watches `documentElement` for the class or style change that swaps it, so a
host flipping light and dark needs no prop and no callback. There used to be
one — a hex colour a host handed over — and it applied to every theme, which
made a theme picker's presets one colour inside a host.

The third context is a headless render: `cadgen step snapshot` runs the same
theme model with no document and no stylesheet. There is no token to read
there, so System resolves to the written-out pair — the same colours the
tokens compute to, so one theme is one background whether it is on screen or
in a rendered picture.

The box the canvas fills is painted the scene's edge colour too — a
gradient's outer stop, a solid's colour — because the canvas is resized on
the frame after its box is, and one frame of the app's background above a
dark stage is a visible band.

## What the consumer's bundler needs

### 1. The JSX-in-`.js` loader

The viewer's components are JSX in `.js` files. esbuild will not parse them as
JSX unless told to, and the failure is a parse error on the first `<`:

```js
// vite.config.mjs (mirrors this package's own vite.config.mjs)
esbuild: {
  loader: "jsx",
  include: /.*\.[jt]sx?$/,
  exclude: [],
},
optimizeDeps: {
  esbuildOptions: {
    loader: { ".js": "jsx" },
  },
},
```

Both halves are required: `esbuild` covers the build and the dev transform,
`optimizeDeps.esbuildOptions` covers dependency pre-bundling.

### 2. Resolve aliases

The viewer's own imports use two specifiers the consumer must resolve:

```js
// viewerRoot: this package's directory; cadgenJsRoot: the cadgen-js source package
resolve: {
  alias: {
    // `@/…` is the viewer client root
    "@": path.resolve(viewerRoot, "src/client"),
    // the shared render/runtime package, imported by name from source
    "cadgen-js": path.resolve(cadgenJsRoot, "src"),
  },
},
worker: { format: "es" },
```

`worker: { format: "es" }` matters because the surf tessellation workers are ES
modules; the classic-worker default fails at runtime, not at build time.

In dev, Vite also has to be allowed to serve both directories:

```js
server: { fs: { allow: [repoRoot] } },
```

### 3. Peer dependencies

The whole `./file-view` closure reaches exactly these packages:

`react`, `react-dom`, `three`, `radix-ui`, `lucide-react`,
`class-variance-authority`, `clsx`, `tailwind-merge`, and `cadgen-js`.

`react-dom` is there for `createPortal`: a panel drawn into a host's
`panelSlot`, and a compact-mode drawer, are both portals.

Keep `three` on a single copy — `0.185.1`, the version this package and
the cadgen-js runtime both pin. Two copies of three.js in one bundle is a
silent-wrong-render class of bug, not a build error.

### 4. Tailwind: scan the viewer's source

Tailwind v4 only emits the utility classes it can see. The viewer's components
are outside the consumer's own source tree, so its Tailwind entry has to name
them:

```css
@import "tailwindcss";
@source "../../viewer/src/client";
```

(path relative to the CSS file). Without it the surface renders with correct
markup and no layout at all — the markup is there, the classes are not.

The viewer's own entry is `src/client/styles/globals.css`, which uses
`@import "tailwindcss" source(none)` plus explicit `@source` lines for the same
reason. Do not import that file from the consumer's entry: it imports Tailwind
itself, and two Tailwind entries in one stylesheet is not a supported shape.
Take its token blocks instead — see below.

### 5. Tokens

The surface is written entirely against **shadcn's token names**:
`--background`, `--foreground`, `--card`, `--popover`, `--primary`,
`--secondary`, `--muted`, `--accent`, `--destructive`, `--border`, `--input`,
`--ring`, `--sidebar*`, `--radius`. A consumer that has run `shadcn init`
already defines every one of them, and the surface adopts the host's theme
rather than bringing its own — that is the point of using them.

Every panel is opaque and painted with those tokens — the sheets and the
sidebar with `--sidebar`, the top bar and the toolbars likewise, popovers and
menus with `--popover` — so the surface looks like the host's own chrome and
never shows the scene through itself.

It also reads a small viewer-owned layer that has no shadcn equivalent: the
surface ladders (`--surface-sunken`, `--surface-base`, `--surface-elevated`,
`--surface-paper` and their `-hover` / `-selected` steps), the numbered
backgrounds and borders (`--background-1..3`, `--border-1..2`,
`--border-primary`), the foreground variants (`--foreground-inverse`,
`--foreground-muted`, `--foreground-passive`), `--selection` and
`--selection-foreground`, the status colours (`--foreground-success`,
`--background-success`, `--border-success` and the error / warning / info
triples), and the loading veil over the scene (`--ui-loading-overlay`,
`--ui-loading-overlay-strong`). These are declarations, not runtime values,
and nothing sets them for you.

So the consumer's token layer needs:

1. `@custom-variant dark (&:is(.dark *));` — the surface switches light/dark by
   putting `.dark` on the root element, which `shadcn init` already sets up.
2. Its own shadcn palette (or the viewer's, copied), for both `:root` and
   `.dark`.
3. The viewer-owned declarations from the `:root` and `.dark` blocks of
   this package's `src/client/styles/globals.css`, copied verbatim.

That layer being viewer-only is the one real coupling here. Every value in it
is derived from the shadcn tokens above it, so a consumer that changes its
shadcn palette and copies the block unchanged gets panels that follow its
theme; a consumer that renames a shadcn token has to carry the rename into
the copy.

## Laying out inside a host

The surface lays itself out against **its own root**, not the window: the
layout hook measures the root element (a `ResizeObserver`, plus the window's
resize events) to pick desktop or compact mode and to size the sidebar and
the sheet. In the standalone app the two are the same box; in a host pane
they are not, and a layout computed for the window's width would leave a
narrow pane with no viewport at all. Two more things follow for a host:

- The WebGL canvas is exactly the area between the sidebar and the sheet —
  the render pane fills that column and nothing else, so the camera fits and
  centres the model in what is visible, and a sheet opening or closing reaches
  the scene as a plain resize of the canvas. The standalone shell gives the
  root the whole viewport (`h-svh`), a host gives it `h-full min-h-0` (the
  `min-h-0` beats the sidebar wrapper's own `min-h-svh`).
- Compact mode's file sheet is a drawer — when the surface is drawing the
  panel at all. With a `panelSlot` there is no drawer and no breakpoint for
  one: the host's column is the panel at every width. Standalone it portals to `body`,
  modal, and closes on an outside click, as a drawer should. Embedded it
  portals into the surface's root instead (`FileSheetPortalContext`, set by
  `<CadFileView>` itself), is not modal — a modal dialog would make the rest of
  the host inert — and ignores outside clicks. A host should also give the
  surface's ancestor a `transform` (any, `translateZ(0)` will do) so the
  drawer's `position: fixed` resolves against the pane rather than the window.
  Popovers and menus still portal to `body`; they are overlays and belong there.
- The same-origin catalog store starts polling at import time only on an
  `http(s)` page. A host loading this module from `file://` has no backend
  beside it, and asks for its backend's store by origin.
- A host whose pane can be narrower than the compact breakpoint but still
  wants the sheet beside the model — a review pane in a three-column window —
  passes `layout="desktop"`, and either sizes the sheet itself with
  `fileSheetWidth` or draws the frame itself with `panelSlot`. The desktop app
  passes `layout="desktop"` and a `panelSlot`: its file tab has one panel
  column, so the sheet's width is that column's and nothing is ever a drawer
  over the model. The surface still measures its root for everything else
  (the viewport, the toolbar), so the pinned layout is never wider than the
  pane.

## Known consequences of embedding

- **The surface writes to `document.documentElement`** — unless the host
  passes `colorScheme`. Standalone, the viewer's colour-scheme preference and
  the OS decide light/dark and the surface applies it to the root element
  (`.dark`, `data-theme`, `data-theme-preference`, `style.color-scheme`),
  because the viewer's own popovers and toolbars portal out of the surface and
  read them there. With `colorScheme` the direction reverses: the host's
  scheme resolves the CAD "system" preset and the surface writes nothing to
  the root. The CAD theme is not part of this in either case ("Theme is the
  scene").
- **One tessellation cache provider per page.** `setTessellationCacheProvider`
  in `cadgen-js` is a module singleton, so a page showing two backends at once
  shares one provider. Register it with the origin you care about:
  `createHttpTessellationCacheProvider({ origin, headers: { "x-cadgen-viewer": "1" } })`.
- **Session state is namespaced by `origin`**, so two backends' per-file session
  state (open sections, pose, camera) cannot collide in one `localStorage`.
- **Theme choice is global**, shared by every surface on the page — it is a user
  preference, not a property of a file. So is the colour scheme, and they are
  two preferences, not one: a page may be light with a dark scene in it.

# Embedding the file view

`<CadFileView>` is the CAD Viewer's per-file surface — the render pane, the
floating toolbar, the right-hand file sheets (STEP, mesh, URDF/SRDF/SDF, DXF),
the theme editor panel, the loading overlay, the status toasts and the alert
dialog — for exactly one file. The standalone viewer's shell
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
| `fileSheetWidth` | `null` | The sheet's width in px, when the host sizes it for its pane. Clamped to the sheet's own range (240–448) and not resizable from inside the surface. `null` uses the stored width. |
| `sceneBackground` | `null` | A hex colour to paint the scene on instead of the theme's own backdrop, so the model sits on the host's ground; lights, grid, floor and materials are the theme's. |
| `colorScheme` | `null` | `"light"` or `"dark"`: the host's resolved theme. The CAD "system" preset resolves the same way and the surface stops writing `.dark` / `color-scheme` to the document — the host owns those. `null` is the standalone case: the surface follows the OS and writes the document itself. |
| `selectReference` | `null` | `{ selector, key }`: select a reference — `o1.2`, `label.f45`, `bracket`, a comma-separated list (its first member) — once the model is up. Applied once per `key`; a new `key` selects again. See "References and captures". |
| `onReference` | `null` | `({ file, selector, text }) => void`. Called for every reference the person copies out of the surface, beside the clipboard write. `null` (standalone) means the clipboard alone. |
| `onCapture` | `null` | `({ blob, file }) => void`. Given, the floating toolbar shows a camera button that renders the viewport to a PNG and hands it over; `null` shows no button. |

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
{ file: "models/STEP/bracket.step", selector: "o1.2", text: "bracket.step#o1.2" }
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

The whole `./file-view` closure (113 modules) reaches exactly these packages:

`react`, `three`, `radix-ui`, `lucide-react`, `class-variance-authority`,
`clsx`, `tailwind-merge`, and `cadgen-js`.

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

It also reads a `--ui-*` layer that has no shadcn equivalent: panels, glass,
control and status colours (`--ui-panel`, `--ui-glass-*`, `--ui-text*`,
`--ui-border*`, `--ui-status-*`, `--ui-shadow-*` and friends). These are
declarations, not runtime values, and nothing sets them for you.

So the consumer's token layer needs:

1. `@custom-variant dark (&:is(.dark *));` — the surface switches light/dark by
   putting `.dark` on the root element, which `shadcn init` already sets up.
2. Its own shadcn palette (or the viewer's, copied), for both `:root` and
   `.dark`.
3. The `--ui-*` declarations from the `:root` and `.dark` blocks of
   this package's `src/client/styles/globals.css`, copied verbatim.

The `--ui-*` layer being viewer-only is the one real coupling here; a consumer
that changes its shadcn palette and copies the `--ui-*` block unchanged gets a
surface whose panels do not follow its theme.

## Laying out inside a host

The surface lays itself out against **its own root**, not the window: the
layout hook measures the root element (a `ResizeObserver`, plus the window's
resize events) to pick desktop or compact mode and to size the sidebar and
the sheet. In the standalone app the two are the same box; in a host pane
they are not, and a layout computed for the window's width would leave a
narrow pane with no viewport at all. Two more things follow for a host:

- The render pane is `absolute inset-0` inside the root, so it fills the
  surface and nothing else; the standalone shell gives the root the whole
  viewport (`h-svh`), a host gives it `h-full min-h-0` (the `min-h-0` beats
  the sidebar wrapper's own `min-h-svh`).
- Compact mode's file sheet is a drawer. Standalone it portals to `body`,
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
  passes `layout="desktop"` and sizes the sheet itself with `fileSheetWidth`.
  The desktop app does exactly this: the sheet is `clamp(36% of the pane,
  240, 365)`, and the app's own file tree hides itself for a CAD tab in a pane
  too narrow to hold both. The surface still measures its root for everything
  else (the viewport, the toolbar), so the pinned layout is never wider than
  the pane.

## Known consequences of embedding

- **The surface writes to `document.documentElement`** — unless the host
  passes `colorScheme`. Standalone, the active CAD theme decides light/dark and
  the surface applies it to the root element (`.dark`, `data-theme`,
  `data-theme-preference`, `style.color-scheme`), because the viewer's own
  popovers and toolbars portal out of the surface and read them there. With
  `colorScheme` the direction reverses: the host's theme resolves the CAD
  "system" preset, and the surface writes only `data-glass-tone` and
  `--cad-scene-backdrop` (which its glass chrome reads) to the root. A host
  that did not pass it would find a STEP file flipping its whole window light.
- **One tessellation cache provider per page.** `setTessellationCacheProvider`
  in `cadgen-js` is a module singleton, so a page showing two backends at once
  shares one provider. Register it with the origin you care about:
  `createHttpTessellationCacheProvider({ origin, headers: { "x-cadgen-viewer": "1" } })`.
- **Session state is namespaced by `origin`**, so two backends' per-file session
  state (open sections, pose, camera) cannot collide in one `localStorage`.
- **Theme choice is global**, shared by every surface on the page — it is a user
  preference, not a property of a file.

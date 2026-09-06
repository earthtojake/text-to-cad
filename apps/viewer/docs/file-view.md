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

`origin` is also published through context:

```js
import { ViewerOriginProvider, useViewerOrigin } from "cad-viewer/file-view";
```

`<CadFileView>` provides it for its own subtree; `useViewerOrigin()` is how any
component under it builds a backend URL. `packages/cadgen-js` stays React-free
and takes the origin as a plain argument instead.

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

## Known consequences of embedding

- **The surface writes to `document.documentElement`.** The active CAD theme
  decides light/dark, and the surface applies it to the root element (`.dark`,
  `data-theme`, `data-theme-preference`, `style.color-scheme`) along with
  `data-glass-tone` and `--cad-scene-backdrop` — because the viewer's own
  popovers and toolbars portal out of the surface and read them there. In a host
  window that means the CAD theme drives the whole app's light/dark. Nothing
  else about the host is touched.
- **One tessellation cache provider per page.** `setTessellationCacheProvider`
  in `cadgen-js` is a module singleton, so a page showing two backends at once
  shares one provider. Register it with the origin you care about:
  `createHttpTessellationCacheProvider({ origin, headers: { "x-cadgen-viewer": "1" } })`.
- **Session state is namespaced by `origin`**, so two backends' per-file session
  state (open sections, pose, camera) cannot collide in one `localStorage`.
- **Theme choice is global**, shared by every surface on the page — it is a user
  preference, not a property of a file.

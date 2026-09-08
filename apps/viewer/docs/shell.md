# The shared chrome

`cad-viewer/shell` is the row ABOVE a file — the breadcrumb, the menus it
drops down, the file icons and the panel toggles. `./file-view` is the file's
contents; this is everything around it that both apps that draw one need.

```js
import { FileNavRow, PanelToggle, buildCrumbs } from "cad-viewer/shell";
```

Two consumers, one implementation: the standalone viewer's
`components/workbench/CadWorkspaceTopBar.js`, and the file tab of the host
application that embeds `./file-view`. The dependency runs one way — the host
depends on this package, and nothing here may import from a host — so the one
thing the two genuinely differ on is injected rather than imported.

Exported as **source**, like `./file-view`: `.jsx` for components, `.js` for
pure modules, JSDoc where a type earned its keep. The consumer's bundler
compiles it and needs the same settings `file-view.md` lists — the JSX loader,
the `@` and `cadgen-js` aliases, and a Tailwind `@source` line covering this
directory.

## The source adapter

Everything in a crumb's menu comes from one question — *what is in this
directory* — and the two apps answer it differently. So `Breadcrumbs` takes a
`source` rather than importing a listing:

```js
{
  // Root-relative entries, or null while they are on their way. Called as a
  // React hook, unconditionally, once per open menu — so the object must be
  // stable in SHAPE across renders. Sorting is not its job.
  useListing: (directory) => ListingEntry[] | null,

  // Optional, and the host's own: the right-click menu around a crumb, the
  // `⋯` after the file crumb, and the inline field that replaces it while
  // the host is renaming. Omit them for a breadcrumb that only navigates.
  wrapCrumb:          ({ crumb, children }) => ReactNode,
  renderCrumbActions: ({ crumb }) => ReactNode,
  renderRename:       ({ crumb }) => ReactNode,
}
```

A `ListingEntry` is `{ path, name, kind: "file"|"directory", value? }`, with
`path` root-relative — the same space `buildCrumbs` splits and a directory id
extends. `value` is the host's own payload and comes back through `onOpen`,
so a host that already had the object does not look it up again by path.

The two implementations:

- **`catalogFileSource.js`** (here) — the standalone's. The viewer's backend
  has no directory-listing route and needs none: one instance serves ONE
  directory, the client polls its whole catalog, and `workbench/sidebar.js`
  builds a directory tree from it. So a listing is a synchronous walk of a
  structure already in memory. Only CAD files are in the catalog, so the menus
  list what the app can OPEN.
- **`crumb-source.tsx`** (the desktop) — a directory at a time over IPC,
  cached in the explorer store beside the tree's own listings, so a folder the
  tree has read costs the menu nothing and the two never disagree.

## What is in here

| Module | |
| --- | --- |
| `crumbs.js` | The breadcrumb as data: `buildCrumbs`, `menuEntries`, `stepToward`, `worktreeMark`, `parentOf`, `nameOf`. Pure, and tested directly (`crumbs.test.js`). |
| `Breadcrumbs.jsx` | The crumbs and their menus, over a `source`. |
| `FileNavRow.jsx` | The row: the breadcrumb, then `leading` / `status` / `trailing` slots. Also `PanelToggle` and `PANEL_TOGGLE_CLASSES`. |
| `icons.jsx` | One icon per file type. The nine formats the viewer renders go through `EntryIcon`, so a `.stl` is the triangle it is made of; everything else is one lucide table. |
| `catalogFileSource.js` | The standalone's source adapter (`catalogFileSource.test.js`). |
| `useElementWidth.js` | An element's width through a `ResizeObserver`; `0` until first measured. |

## The rules that keep the two apps identical

- **The crumbs are the segments below the root, and nothing else.** No crumb
  for the served directory, the project, or the worktree: a root's neighbours
  are outside what either app may list. `worktreeMark` draws a label for it
  instead, which is why that label has no menu.
- **A crumb's menu is its PARENT's listing**, with the crumb marked. The
  redundancy between `crumb.current` and what the component computes from the
  open file is deliberate and asserted in the test.
- **The `ui/` primitives this directory uses are shared too.** `@` resolves to
  this client in both apps, so `Breadcrumbs` draws the VIEWER's
  `components/ui/dropdown-menu.jsx` even inside the desktop. Keep it at the
  desktop's shadcn generation — its icon rules and its open-submenu highlight
  are load-bearing here — or the desktop regresses without anything failing.
- **Which nine formats are CAD is `cadgen-js`'s** `lib/fileFormats.js`, the
  one authority both apps can reach.

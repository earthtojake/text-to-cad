# The shared chrome

`cad-viewer/shell` is everything a person sees AROUND a file: the nav row above
it, the breadcrumb in that row, the menus a crumb and a tree row drop down, the
panel column at the right end, the file tree that lives in it, and the empty
state when nothing is open. `./file-view` is the file's contents; this is the
rest of the file explorer, and both apps that draw one draw this.

```js
import { FileNavRow, FilePanelColumn, FileTree, buildCrumbs } from "cad-viewer/shell";
```

Two consumers, one implementation: the standalone viewer's
`components/workbench/CadWorkspaceTopBar.js` + `components/CadWorkspace.js`,
and the file tab of the host application that embeds `./file-view`. The
dependency runs one way — the host depends on this package, and nothing here
may import from a host — so the things the two genuinely differ on are injected
rather than imported.

**The two apps differ in exactly two ways**, and both are declared rather than
forked:

1. The standalone's nav row ends with Discord, GitHub and a version chip. The
   desktop's does not.
2. What a host can DO with a file is a **capability set** (`entry-menu.js`).
   The desktop has a filesystem and an OS, so it has all thirteen actions; a
   browser tab has neither, so it has four — open, and three ways to name the
   file on the clipboard. An item a host cannot perform is not in its menu,
   rather than in it and broken.

Everything else — the row, the crumbs, the menus, the toggles, the column, the
tree's rows, glyphs, indentation, expand/collapse, keyboard and filter box — is
one piece of code drawn twice.

Exported as **source**, like `./file-view`: `.jsx` for components, `.js` for
pure modules, JSDoc where a type earned its keep. The consumer's bundler
compiles it and needs the same settings `file-view.md` lists — the JSX loader,
the `@` and `cadgen-js` aliases, and a Tailwind `@source` line covering this
directory.

## The source adapters

Everything in a crumb's menu — and every row of the tree — comes from one
question, *what is in this directory*, and the two apps answer it differently.
So both components take a `source` rather than importing a listing.

### The breadcrumb's

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

### The tree's

`FileTree` takes the same idea, widened: where the listings come from, AND what
an entry menu's items do. One object (`FileTreeSource`):

```js
{
  rootName,                 // named in the "… is empty" line
  expanded, setExpanded,    // which folders are open — the HOST holds this
  listings,                 // directory id -> entries; absent = not read yet
  load,                     // fetch one directory (a no-op for a host that has it)
  revision,                 // bumped when the filesystem moved on
  paths,                    // () => Promise<string[]>, the filter's corpus
  platform, capabilities,   // which items the menu offers
  onAction,                 // everything except the three that start a field
  rename, create, trash,    // finish an inline field; omit what you cannot do
}
```

The three field-starting items — Rename, New file, New folder — never reach
`onAction`: the tree draws the field itself, because a field belongs to the row
it is in, and finishes it through `rename` / `create`. A host without those
capabilities never offers them, so the callbacks may be omitted entirely.

- **`catalogTreeSource.js`** (here) — the standalone's. `load` is a no-op and
  the corpus is a flatten: the catalog is already in memory. Only CAD files are
  in it, so the web tree lists the CAD files the served directory holds and the
  directories containing them. **That is the one place the two trees differ in
  content**, and it differs because the viewer's backend has no directory to
  list, not because the component does.
- **`tree-source.ts`** (the desktop) — `explorer.list` over IPC with gitignore
  semantics and a watcher, cached in the explorer store.

## What is in here

| Module | |
| --- | --- |
| `crumbs.js` | The breadcrumb as data: `buildCrumbs`, `menuEntries`, `stepToward`, `worktreeMark`, `parentOf`, `nameOf`. Pure, and tested directly (`crumbs.test.js`). |
| `Breadcrumbs.jsx` | The crumbs and their menus, over a `source`. |
| `FileNavRow.jsx` | The row: the breadcrumb, then `leading` / `status` / `trailing` slots. Also `PanelToggle` and `PANEL_TOGGLE_CLASSES`. |
| `icons.jsx` | One icon per file type. The nine formats the viewer renders go through `EntryIcon`, so a `.stl` is the triangle it is made of; everything else is one lucide table. |
| `catalogFileSource.js` | The standalone's breadcrumb source (`catalogFileSource.test.js`). |
| `catalogTreeSource.js` | The standalone's tree source (`catalogTreeSource.test.js`). |
| `entry-menu.js` | What the menu on a file or a folder offers, as data, filtered by a capability set. Pure, and tested directly (`entry-menu.test.js`). |
| `EntryMenu.jsx` | That table drawn — as a right-click menu or as a dropdown — over one `onAction` handler. Also `EntryContextMenu` and the focus guard. |
| `FileTree.jsx` | The tree: rows, glyphs, indentation, expand/collapse, reveal, keyboard, filter box and per-row menu, over a `FileTreeSource`. |
| `fuzzy.js` | Subsequence ranking for the tree's `Filter files…` box (`fuzzy.test.js`). |
| `InlineName.jsx` | The field a name is typed into, in place: a rename over a row or a crumb, a new entry in a folder. |
| `panels.js` | The panel list and the rule that only one is open: `cadPanels`, `markdownPanels`, `treePanel`, `panelsFor`, `resolveOpenPanel`, `nextOpenPanel` (`panels.test.js`). |
| `FilePanelColumn.jsx` | The one frame every panel is drawn in — one border, one width, one resize handle — and the width's range. |
| `EmptyState.jsx` | The one empty state, used by every pane in both apps. |
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
- **Which nine formats are CAD is `cadgen-js`'s** `lib/fileFormats.js`
  (`isCadFile`), the one authority both apps can reach. The entry menu asks it
  whether to offer `Copy reference`.
- **A host omits an action, it does not reimplement one.** Everything a
  browser tab cannot do is missing from `WEB_ENTRY_CAPABILITIES`, so it is
  missing from the menu, from the keyboard (F2, ⌘⌫) and from the code paths
  behind them. There is no second menu and no `if (web)` anywhere in here.
- **ONE panel column, and one panel open in it.** The tree is an entry in that
  list, appended last (`panelsFor`), not a second column beside it with a
  design of its own. Both apps hand the surface a `panelSlot`, so the CAD
  theme editor and Inspector are portaled into the same frame the tree uses.
- **A shared component's state lives with whoever persists it.** The tree's
  open folders are the host's (`expanded` / `setExpanded`), because the host
  owns the session record; the tree reads and writes them through the adapter.

# Viewer interaction and settings design system

This is the binding contract for the viewer's tools, its panel and its
settings, in both apps. Build from the shared pieces — the
[toolbar button](../src/primitives/toolbar-button.jsx),
[FloatingToolBar](../src/renderers/kit/tools/FloatingToolBar.js),
[SubToolbar](../src/renderers/kit/tools/SubToolbar.jsx),
[ToolPopover](../src/renderers/kit/tools/ToolPopover.jsx),
[FlatPanel](../src/renderers/kit/shell/FlatPanel.jsx),
[ToolStack](../src/renderers/kit/tools/ToolStack.jsx),
[ToolPanel](../src/renderers/kit/tools/ToolPanel.jsx),
[the floating surface](../src/lib/floatingSurface.js) and the
[FileSheet primitives](../src/renderers/kit/inspector/FileSheet.js) — and extend
them rather than recreating their layout in a renderer. Environmental effects
belong to apps through the [host contract](viewer-host.md).

## Ownership and layout

FileViewer owns the navbar — the logo's app menu ([Settings](#settings)) included, built from
the host's `links` and the `appSettings` `CadViewer` hands it — and the name menu (a popover
under the file's name: Models and Files, the file explorer). The view's one frame (`kit/shell/ViewFrame.jsx`, which
every renderer mounts, 2D or 3D) owns the scene's chrome: the tool strip and the view's controls at its end (a 3D
view's Preview), the sub-toolbar of the tool in hand under it, the update status, the view's one
panel, Quick Edit, the view's corner at the top-right (the cube, or a flat view's zoom) and Preview, with Preview's own
bar in the navbar's place. Renderers supply
their tools, their tools' rows, their panel's sections and their document state; the shell never
inspects a format's parts, joints or topology. No pick or tool opens or closes the explorer.

| The host (web, the CAD app) supplies | The shared UI decides |
| --- | --- |
| Where the tab record lives (`TabRecordStorage`: the web's sessionStorage, the CAD app's memory) | The record: its settings (the view's panel's and tool stack's layout, the appearance, the home's layout, the folder the explorer was last in) and the view of the file on screen (its camera, Display settings, Preview's Render settings, its playback settings, and renderer slices), what is written when, and what is never stored (`@cad/ui/tab-store`, `kit/shell/fileView.js`) |
| `chrome` (the navbar, `"page"`, or the view alone, `"bare"`), `navigation.home`, `links` (its version, GitHub, Discord, where a new issue opens, how a link opens), `appSettings` (the person's own settings), `colorScheme` (the person's theme and how it changes) | The navbar's order and look, over a file and over the home, the app menu (one menu in the viewer and on the home) and what a new issue says |
| `host.files`, `fileActions`, `navigation`, `clipboard`, `promptContext`, `promptFiles` | When a copy, capture or open happens and what it carries |
| `host.environment`: color scheme, keyboard `platform`, `reducedMotion` | How the chrome honours them |
| `onError`, for errors the viewer hands up | Preview, tooltips, keyboard scope, the tool strip and panel, the camera |

Hosts pass no Preview or notification props; there are none. A host's one say over the chrome
is `chrome`: the navbar (`"page"`, the default) or the view alone (`"bare"`).

- **Navbar.** One row, the same wherever it is drawn, over every file and over the home: in a page's
  chrome (`chrome: "page"`: the web viewer's, and the CAD app's sidebar, tabs and cards), never in a
  host that shows the view alone (`chrome: "bare"`, the CAD app's file handler: below), and never in Preview, which draws its
  own bar in its place, in every host (see [Preview](#camera-animation-and-preview)). Left: over a file that has a
  panel, first, **the panel's toggle** (the same neutral button open or shut, the sidebar's icon: [The panel](#the-panel)),
  then the text-to-cad logo,
  named Menu, with no chevron: the "C" mark, 16px, in the row's 28px button, the same over the
  home and over a document (no wordmark, and nothing that changes between the two). The row is
  40px, the floating tool strip's height, its controls centred in it and each icon button 28px (the
  logo, Back, Forward, the ⋯, the right end's), as the strip's and the panel head's are. The mark's
  left edge is the page's 16px gutter and the view's panel's line, over the home and over a page
  alike (the row starts 8px in, the button's padding is 6px, the artwork 2px in from its image). The logo opens the
  **app menu** (see [Settings](#settings)) — a host with no home has it too — then, where the
  host keeps the view's own history (`history`: the CAD app's views, which no browser holds),
  **Back** and **Forward**, two arrows walking it as a browser's do, from file to file and to
  and from the home (a step like a file), each there always and disabled where it has
  nowhere to go — on a desktop's row alone: a phone's (`useViewerMobile`, a view under 600px)
  has no room for them and draws neither, the history kept; then the open file's name, alone (no glyph: the name and, where it opens the
  name menu, its chevron), and its ⋯. Each of these that
  is a control (`NAV_ITEM_CLASS`) is transparent at rest, takes the same accent background
  while the pointer is on it and while its menu is open, has a pointer cursor and no tooltip:
  it says what it is. The name
  is that control where it opens the name menu (below), where the view can show another
  document; where it cannot it is plain text. The ⋯
  is the file menu, stock shadcn items and submenus (`DropdownMenuSub`), the menu and each
  submenu shadcn's own width (`min-w-[8rem]`, sized to its items: no width of their own), in this order:
  **Copy path**; **Copy link** (the document's page with its link, `<engine origin>/<id>?token=<link>`,
  the address the page itself holds: on every document, model or file of any kind, always enabled,
  its source there or not; copied silently, as Copy path is; `fileActions.perform["copy-link"]`); **Open in**, a submenu of **Browser** (the document's page in the person's
  browser: the CAD app's, where a launch carried the web viewer's page, `fileActions.perform.browser`)
  and the desktop's file manager by its plain name — **Finder** on macOS, **File Explorer** on
  Windows, **File manager** on Linux (`reveal`); then, where the host has this computer's apps
  (`fileActions.apps`), in groups parted by separators: the apps that take the source (a model's
  script: Visual Studio Code, Cursor …; a file's: FreeCAD, Bambu Studio …, by their product names,
  untranslated as Finder is); each file the model's last build wrote that is on disk, its apps as
  **App (file name)** (FreeCAD (bracket.step)); and **Default app**, the OS's own handler for the
  source. A KiCad board or schematic takes each KiCad this computer has, a channel's newest, by a name
  that says which (**KiCad 9.0.6**, **KiCad 10.99 nightly**), and no Default app. A KiCad that cannot
  read the file's format is never silently hidden: its row is drawn disabled, with the reason as its
  hint (**KiCad 9.0.6 can't open this board: it was saved by a newer KiCad.**, `file.kicadBoardTooNew`,
  `file.kicadSchematicTooNew`), so the person learns what to install. A group with no item is left out
  with its separator, and an export whose file is gone is
  left out. The apps are asked for as the menu opens, never before: what needs no answer is there
  at once, the apps join it when it comes, and a failed or slow answer leaves the menu as without
  them. Choosing one is counted as `file_open_app`, never which app. Then the host's own items, the viewer's
  **Export**, a submenu of the formats the document's kind writes (where the host can download,
  the web viewer's). Each only where the host can do it. A model's document, which has no file of
  its own, has the same menu on the script that builds it (its envelope's `source.path`,
  `FileMetadata.sourceFile`): Copy path copies the script's path and the file manager reveals it,
  while Browser opens the model's own page; where the engine names no script, only Browser and
  Export. A document whose source was moved or deleted (a model's script gone or never on disk, a
  file gone: the envelope's `source.present` false, `FileMetadata.sourceMissing`) keeps Copy path
  (where it was) and draws what opens the source disabled, with one hint, **The source was moved
  or deleted.** (`file.sourceMissing`, on a wrapper, as shadcn hints a disabled control): Open in
  itself where nothing in it can open (the web viewer's), else each such entry — the card's Browser
  needs no source and stays enabled, its Finder disabled. The source's apps and Default app are
  disabled the same way; an export on disk still opens. Open in's entries are one list, each with
  whether it opens now and why not (`openInMenu`). Each Open in row leads with its mark, 14px in the
  row's muted icon colour, so every row reads alike (`OpenInMark`, `navigation/appMarks.jsx`): an app's
  own single-colour mark where one is published under a licence the package can ship (provenance:
  `src/assets/README.md`), else Lucide's `AppWindow`, never a mark drawn by hand; **Browser** `Globe`,
  the file manager `Folder`, **Default app** `ExternalLink`. No ⋯ where there is nothing. The home has no file and no ⋯. The name has
  no right-click menu and there are no crumbs. The left's controls sit edge to edge, spaced
  by their own padding alone: the logo, Back, Forward and the ⋯ in 28px buttons, and the name
  4px in from its edges. Right,
  only what a host or a file adds, in this order: first, while
  a person has put an alert card away, the card's own icon (a circle
  with an exclamation mark, red for an error and amber for a warning, named and hinted by
  the alert's title), which brings the card back and goes with it — the renderer's one
  navbar action. Then the host's own actions (`actions`): inline, where the host can show the view full size,
  **Full size** (the CAD app's: two diagonal arrows, a ghost icon button) — today the slot's
  only control. Export and Open in are the file menu's, never here. A CAD file publishes no
  navbar action but that icon. The person's own settings, the theme among them, are never here: they are the app
  menu's.

  *Design note: the view's settings are the navbar's, the picture keeps the camera's own control.* How the file is
  looked at is ONE button, **View** (`ViewSettingsMenu.jsx`), at the navbar's right end for every kind of file, left
  of **Preview** where the file has one (host actions after them): a cube for its icon (a 3D view's, and a board's in
  3D, the projection on screen's; a flat view's the plain cube, Orthographic's), no chevron, its name and tooltip
  "View", ONE menu of every view setting, grouped ([The View menu](#the-view-menu-and-a-phones-sheets)), ending with
  **Reset view** where the view has a camera to bring back. The picture keeps only the camera's own control in its
  top-right corner: a 3D view's cube, alone; a flat view's zoom, one "100%" dropdown (a board's in 2D and in 3D, a
  schematic's, a drawing's). Why (the owner's decision): one place and one icon for how the file is looked at, on every
  file, where every file keeps it, beside Preview; and the picture stays clear — nothing of the view's settings stands
  over the model, and the corner is the camera's alone. The strip is only tools (Select, Draw, Measure, Explode, Clip).
  On a phone the navbar's right end is the same View and Preview, the same menu, and the picture has no corner control
  at all (gestures: a pinch zooms; Reset view brings the view back). Where there is no navbar (a host's inline card),
  View and Preview end the strip, in that order, in every kind of view; that host's phone has their rows in its More.
  What a host or the file adds (an alert's icon, the host's actions) is the navbar's right end too, the host's after the
  view's; what can be done with the document (copy its path, open it elsewhere, export it) is its ⋯, beside its name.
  The view's settings act on the
  whole view, whatever tool is in hand, so they are no tools, and a new per-file button that is no tool
  goes with them. In Preview, Preview's own
  controls, **Preview settings** and **Exit preview**, are its bar's. So a host may leave the
  navbar out (`chrome: "bare"`; no host does today: the CAD app's file handler has it too, for the panel's toggle), and
  Preview hides it.

  **A host's home has the same navbar**, Onshape's way, the same 40px bar with Home's own contents: at the left the
  logo and its app menu (without Back to home: the same menu as over a file), and where the host keeps the view's
  history **Back** and **Forward** (a desktop's alone); then, in the slot where a file's page shows its name,
  **Recent** (13/20, weight 500) and the count of what is shown (11/16 on a `muted` pill); at the right the **search**
  (a stock Input, 28px tall and 240px wide, "Search"; under 700px of navbar its 28px icon button alone, which opens into
  a 200px field with the keyboard in it and goes back to its icon when left empty) and, where the host's computer has a
  file chooser (`ModelLibrarySource.pick`), **Open**, a stock `outline` button (28px, never a filled primary) with the
  folder icon and "Open", which opens the desktop's own chooser (`POST /api/v1/local/pick`) and shows the file picked;
  and the host's actions, outermost. No panel toggles and no ⋯ on the home (the app menu is the logo's). **The bar's
  contents stand on the grid's column**, not the window's edges: at a wide window "Recent" starts over the grid's left
  edge and Open ends over its right edge (the bar's background full width, the logo at the window's left as on a
  file's page); in a narrow pane they meet the page's gutters, clear of the logo (`ViewerNavbar.jsx`'s
  `useHomeColumn`; the home portals its controls into the navbar's two slots, `file-viewer/navbarSlots.js`). Under it,
  the page, after Figma's Recents, with no hero (no wordmark, tagline or links: GitHub and
  Discord are the app menu's, X its footer's "Made by"; no light/dark button: Theme is the
  menu's). The Home is the chrome's **type scale**: the controls `text-ui` (13/20); a tile's and a row's name 12/16,
  weight 500, over or beside its facts, 11/16 and muted (`src/designSystem.test.js` holds it). It has **no heading row
  of its own**: a light row directly above the grid, 28px, on the grid's column, holds the **type filter** at its left
  (a stock DropdownMenu whose ghost trigger names what it shows, "All ▾", its text on the grid's edge; its radio items
  All, Models and Files, there only where models and files are both listed) and the **grid/list switch** at its right
  (two 28px icon buttons, the chosen one on the pressed fill, `accent`, with its icon the brand's, `--brand-icon`, as
  the tool in hand's is). A home drawn with no navbar has Recent, the search and Open in that row. Then the
  documents opened or built before, pinned first, then by last activity. The home is the
  library and Open alone: no folder of a launch. It is a **centred column**, 1128px wide at most,
  on 24px gutters of its own (not the navbar's 16px, which the logo keeps), 20px under the navbar,
  its filter row 12px over the tiles; its spacing on the 4/8/16 scale. Every picture, a tile's and a
  row's, is the light viewport's on the **model area's light gradient** (#f4f5f6 to #dfe2e5) in both
  themes, as the view's own canvas draws it: no picture is inverted for the dark theme, and a board's
  dark picture is not used. In the grid, a **tile** is a framed card (variant B): the picture edge to
  edge over its caption inside one box on the `card` colour, a 1px `border` and a 10px radius; under
  the pointer its border a step darker with a faint shadow; selected (in keyboard focus, or being
  opened) the brand's ring, its caption on `--brand-subtle`. Columns at least 232px (four across the
  full column), 16px apart, 24px between rows. Its picture is 330:185, contained (its placeholder cube
  24px), a small **format badge** at its top-left (STEP, GLB, KiCad PCB, DXF, STL, 3MF, or Model for a
  document built from code), light on the picture in both themes; its caption (8px by 12px): its kind's
  16px glyph, 8px before its name over a file's size and its last activity with its verb
  ("122 KB · Viewed 16m ago"; a model's activity alone: "Edited 2m ago" for a change after the last
  opening, "Viewed 16m ago" for an opening after the last change; `lib/age.ts`). A file's size is the
  server's (`size`, from the file's stat: `RecentStore.list`), a document built from code has none. In
  the list, a **table**: a 28px header row of muted 11/16 labels (Name, Kind, Size, Updated, Created)
  over 44px rows, each its picture (40 by 28, on the model area) and name, then its kind, its size ("—"
  for a model) and its `updated` and `created` ages with no verb, 11/16 and muted (Created dropped under
  an 820px page, Kind too under 560px), transparent, the palette's hover (`muted`) under the pointer and
  `--brand-subtle` while selected. With nothing opened yet the page is a **welcome**: the C mark (64px)
  on the model area, "Nothing opened yet" (15/20), one short line, **Open file** where the host has a
  chooser (the same neutral button), and the formats the viewer opens. Each has a **pin** toggle and **one ⋯ menu** (a stock DropdownMenu), shown on hover
  or focus, at a tile's picture's top-right (Figma's star, light on the picture) or a row's end; a pinned one keeps its
  filled pin at rest. The menu holds Open, a file's Copy path, Copy link (every card's) and a file's Reveal where the host can, Pin or
  Unpin, a rule, then Delete (destructive), which asks first in a stock AlertDialog saying
  what goes and what stays on disk ("Delete wheel?"), Cancel / Delete; the card leaves the
  list at once. Every model is a tile and a row of its own, nothing folded, opened, pinned and
  deleted alone, and nothing on the Home or in the menus ties a model to the script it was
  built from: a model shows its name, its glyph and its age; its menu is Open, Copy link, Pin or Unpin and
  Delete, with no Copy path or Reveal (a file's alone); a search matches a model's name (a
  file's name and path); and the Delete dialog's words name no path.
  A file that will not open
  shows a page under the navbar: "File does not exist" and the file's path, or "Could not
  open that file" and the reason, each with **Go home** where the host has a home. A view
  drawn as a picture (`compact`, the home's thumbnails) has no navbar either, and draws the
  model alone: no tools, view actions, cube or Quick Edit.

  A host that shows the view alone (`chrome: "bare"`: the CAD app's file handler, Codex's *Open
  with CAD*, one file whose host's file tree is its navigation) draws no navbar over the file or
  over a page that will not open: no logo or app menu, no Back and Forward, no name or name menu,
  no ⋯ (so no Export and no Open in). What it still adds is its corner at the viewport's
  top-right, the host's notice (`ViewportTopRight`): where
  the host can show the view full size, **Full size**. In Preview it is gone with the rest of the column.
- **Name menu** is a popover under the file's name, aligned to the name's left edge, 17.5rem
  (280px, the explorer's natural width) wide and never resized: two stock shadcn Tabs on top,
  **Models** and **Files**, in the explorer's type (`text-xs`, a 28px list) and each as wide as its
  label (the list `w-fit` at the left, not the menu's width), and under them the explorer's own
  style. It opens on Models over a model and on Files over a file; a host with one of the two has
  no tabs, and one with neither a plain name. **Models** (`ModelList.jsx`) is the host's library's
  models alone (no file: those are Files' and the Home's), by last activity, eight at most, in the
  explorer's compact rows: the model's glyph, its name, and at the right its age with no verb ("2h
  ago"), under its filter, as Files' rows are under theirs ("Filter models...", the explorer's
  `TreeFilterInput`, matching every word in a model's name, before the eight are taken; "No
  models match" where none does); the model on screen is highlighted, a press opens a model as a
  pick in the explorer does, Up and Down walk the filter and the rows, and there is no footer: the
  home is one click away. **Files** is the file explorer (`FolderExplorer.jsx`),
  below. The menu is as tall as its rows up to 28rem or the room below it: past that its list
  scrolls. It floats over the view and its panel, so opening it resizes and moves
  nothing. The explorer starts in the open file's folder; a model, which has no file of its
  own, starts it where the explorer was last in this tab (the tab's `explorer.folder`, kept as
  it moves), else in the person's home folder (the server's `home`), never in the folder of the
  script that built it. It lists one folder at a time — its subfolders, then its CAD files,
  `.xbf` among them, hidden folders left out but the engine's cache (`~/.cache/cad` and the
  folders on the way to it), which holds each model's `documents/<id>/document.xbf` — in compact rows: one 24px
  line of 12px text each, its kind a small light glyph in one column 5px in from the row's
  left end and 4px before the name (a folder its disclosure chevron, with no folder icon; a
  file its glyph), as the panel's trees draw theirs. Every CAD file, whatever its kind, has
  one glyph, lucide's plain `File` (`EntryIcon.jsx`), and a model, built from code, lucide's `Box`
  (`DocumentGlyph.jsx`), both 16px wherever documents are listed: the Home's tiles and table,
  the explorer and the name menu (in a compact row drawn 2px past each side of the 12px glyph
  column, so the names start where they do). The name beside it says which kind; a file still
  loading is the spinner. A press on a subfolder opens it
  inline, under itself, its rows 10px further in and hung from a faint line under its
  chevron, read once when it first opens; another press closes it, and Right and Left do the
  same from the keyboard, as in every tree (Right on an open folder into its first row, Left on a
  row up to its folder's, Home and End to the first and last rows: [Keyboard](#keyboard)). A
  double-click opens it in the explorer's place, as a crumb does —
  the breadcrumb then names it. The breadcrumb is
  as many of the last three folders as fit whole: every crumb is its folder's whole name, the
  farthest giving way first to the "…" (an ellipsis icon), which lists every folder above the crumbs to jump to,
  and only the folder it is in, left alone beside the "…", is cut (its name a hint while it
  is). The folder it is in reads in the foreground color, the others muted; there is no up
  arrow, and the open file is highlighted, the list opening scrolled to centre its row, once (a
  long folder's too). Opened on either tab, its filter has the keyboard, so typing
  finds a file or a model at once, and Down takes it into the rows; on
  a phone the menu itself holds focus, keeping the keyboard down. "Filter files..." under the breadcrumb searches
  every file nested under the folder (the server's bounded search, debounced 150ms, each
  keystroke cancelling the search before it); a search that stopped early says "Stopped
  early. Keep typing to narrow the search." Up and Down move between the filter and the
  rows on screen, the rows of a folder open inline among them. A pick opens the file and
  closes it, as do Escape and a press anywhere outside it.
- **Tool strip** at the top centre, 8px down, never wider than the view less 8px at each
  side (it wraps before it would be): the tools, left to right, **one row with no rule** (a tool's `group`
  orders it: the tools that pick, Select, Draw (a plain button) and Measure; then the model's effects, Explode and Clip),
  then, outside a file's navbar (a host's inline card), **the view's own controls on the strip** (`data-view-controls`,
  `FloatingToolBar`'s `views`), directly after the last tool: **View** (the strip's tile), then a 3D file's
  **Preview**. Under a file's navbar the strip is its tools alone: View and Preview are the navbar's (the design note
  above). The tools are what you do to the model, the view's controls how you look at it, as Figma keeps them out of
  its toolbar. **What goes on the screen is what is changed often**: a tool, the cube, the zoom.
  What is changed now and then goes in the view's panel or behind a menu: a board's layers and layer display
  are its Layers tab's, Show grid is the View menu's (a phone with no navbar, Display's list's), Zoom to selection
  and Zoom to 100% the zoom's menu's. **Figma's toolbar's proportions at a 28px tile** (Figma measured: a 48px
  bar, 13px corners, 32px buttons with 5px corners; ours a size down, every measure from the tile): a 40px bar with
  its 1px border, (40 − 2 − 28) / 2 = 5px in, 28px tiles with corners 5/32 of a tile (4px) and 16px icons, an even
  4px apart, the bar's corners its padding, a tile's corner and 1 (10px), so the two curves run parallel; a tool's
  chevron half a tile wide, its own 14x28 target touching its button, its glyph 9px (`stripTouch.js`'s
  `TOP_STRIP_BUTTON_CLASS`, `TOP_STRIP_SHAPE_CLASS`; `ToolModeMenu.jsx`; `FloatingToolBar`, `data-cad-toolbar`);
  the strip's colours and surface its own. A tool's sub-toolbar under it takes the same proportions (below; the
  drawing tools' two rows of seven 72px), and so do the panel's head buttons and the navbar's panel toggle (below); the corner's
  zoom is 28px tall (below), and Preview's playbar keeps its 24px buttons. **The toolbar and the Quick Edit bar are centred on
  the window, always; panels never move them; where they meet a panel they sit above it** (`ViewFrame.jsx`'s top
  layer, `data-view-top-layer`, over the panel). A person finds the strip where it always is,
  whatever is open beside it; a strip that slid with each panel moved under the pointer as a panel came and went.
  A file with no tools and no 3D view has no strip. On a phone
  ([mobile](#the-views-panel-and-the-tool-stack)) the tiles are 36px with 18px icons, a chevron
  20px wide, in one row that never wraps, its bar 46px (the desktop's 40 does not fit a finger). It is
  centred in the whole view, on a phone as on a desktop and in every renderer (all of them mount
  `kit/shell/ViewFrame.jsx`), 8px from the edges at the least; what does not fit goes into
  **More tools** (an ellipsis, last): the tools that do not fit, from the strip's end, a tool there a row ticked while
  it is in hand (`touchStripFit`). Under a file's navbar a phone's strip is its tools alone — Select, Draw, Measure,
  Explode and Clip, as a desktop's — which fit a phone's width, so it has no More: View and Preview are the navbar's.
  Outside a navbar (a host's inline card) the view's controls are More's rows too: Projection's row switches the
  projection as its tile does, and Display's row opens its choices under it, in More itself, as the app menu's
  Language does on a phone ([mobile](#the-views-panel-and-the-tool-stack)).
- **Sub-toolbar** under the strip, 8px below it, centred: the tool in hand's one row of
  controls (`SubToolbar`, `data-cad-sub-toolbar`), there for as long as the tool is up (see
  [Tools and lifecycle](#tools-and-lifecycle)). Select and Measure have none. On a phone its
  buttons are the strip's 36px tiles and its sliders as tall, the slider rows 20rem wide.
- **Tool stack** under the sub-toolbar, in the same centred column: a renderer's own
  `toolPanels`, where it hands any (see
  [The view's panel and the tool stack](#the-views-panel-and-the-tool-stack)). The column
  stops clear of Quick Edit's row (`VIEWPORT_STACK_BOTTOM`, 68px and 16px off the bottom), so it never runs past the
  view.
- **The panel**, the view's one sidebar, docked at the left: its tabs, with one search over the tree-like ones (an icon at
  the head row's right end) — first the file's structure (a
  STEP's Model, a robot's Links, a board's Parts, Nets and Layers, a drawing's Layers), then, only where the file has
  them, its **Parameters**, **Joints** and **Animation** — whatever tool is in hand; collapsed, nothing over the model
  (its toggle is the navbar's); on a phone the same toggle opens it as a sheet from the left (see [A phone's
  sidebar](#a-phones-sidebar)).
  Every file has it, from the view's first frame (a GLB's, a 3MF's and an STL's Model too, a row at the least). What is
  selected is read in Quick Edit's chip list.
- **Quick Edit** at the bottom, 16px up, centred on the window as the strip is, over the panel where it meets it:
  400px wide at most, else the window less 16px a side (`QUICK_EDIT_MAX_PX`, `QUICK_EDIT_MARGIN_PX`), a STEP's or a
  robot's: the bar of the note a person writes to their agent, there only while something is picked or drawn
  (see [Quick Edit](#quick-edit)). **The bottom row is Quick Edit's alone**: nothing of the corner stands there.
- **View cube** at the **top-right**, its 68px box 12px from the right edge and 12px off the top (the corner's inset:
  the host's corner variable, 2px unset, and `CUBE_GUTTER_PX`; `VIEWPORT_CUBE_TOP`), the cube drawn as before, scaled
  uniformly, its drawing cropped to the cube (`ViewPlaneControl.js`'s view box), its X, Y and Z lines on its own edges
  nearest the camera (X and Y the bottom's near edges, Z the upright edge at their corner), each drawn from its negative
  end to its positive one and lettered just inside its positive end, so nothing it draws sticks out past the cube.
  The cube has enlarged face/edge/corner hit areas and neutral hover and XYZ guides, and it stands alone in its corner
  (**The view's corner**, below). A host whose own control floats over that corner lowers it clear with
  `--cad-viewport-corner-top`, the room that control takes from the top edge. A host can instead anchor it at the
  top-left with `--cad-viewport-corner-left: 2px` and `--cad-viewport-corner-right: auto`, and the whole
  corner follows it there (**The corner at the left**, below).
  Codex's tab presentation uses this for all its views, clear of its floating chat button.
  Preview omits it, and so does a phone. **The strip and the cube**: the strip is centred on the window and the cube
  hugs the right edge, so they meet only where the window is narrower than the strip and about 200px (under 600px for
  a 3D file's strip, which is a phone's layout, with no cube); where they would, the strip, in the layer over the
  corner (`data-view-top-layer`), stands over the cube: a tool is never under anything.
- **The host's notice** (a question it asks once) stands under the corner, at the right, an inset under the corner's
  control (the cube, or the zoom) (`ViewportTopRight`, `--cad-corner-below`, the frame's measure of the corner); at the top-right itself
  where the host anchors the corner at the left.
- **Preview** is the navbar's last view button under a file's navbar (`data-view-preview`), right of View, a phone's too; elsewhere it ends the tool strip, after View, for a 3D file (`data-view-controls`, `FloatingToolBar`'s `views`):
  lucide's Play (a play triangle), the way into Preview — a mode of the whole view, not a setting of it. It
  is no tool: pressing it leaves the tool in hand as it is. Outside a navbar, on a phone it is a row of the strip's More.
- **The view's corner** (`kit/shell/ViewCorner.jsx`), at the **top-right**, is where the picture is
  looked at from, never a tool. A **3D view's** is the cube: its faces,
  edges and corners turn the view, its darker right-front-top corner to the usual isometric view, and Zoom to
  fit (F, a double-click on empty space under Select, the view's menu) frames what is shown from where it is
  looked at; it stands alone, nothing under or beside it. Its way back to the view the file opened with — framed whole
  from the opening direction, eased (`ShellViewport.jsx`'s `goHome`; telemetry `view_home`) — is View's **Reset view**
  ([The View menu](#the-view-menu)), no longer a Home button on the picture. A **flat view's** corner — a board's, in 2D
  and in 3D, a schematic's, a drawing's — is its **zoom** (`ZoomControl.jsx`): ONE dropdown, the percentage in the
  type scale's `text-tiny` and tabular digits with a small chevron, no − or + and no Home, on a faint resting surface
  (the foreground at 6%, a step more under the pointer and while its menu is open) so it reads as a control over the
  drawing, the digits haloed in the viewport's background; 28px tall, its middle on the tool strip's middle line, its
  outer edge on the cube box's line (`chromeInset.js`'s `CORNER_INSET_PX`, 12px from the right; `viewCornerLayout`'s
  `pill`). Its menu, under it, is the zoom's commands alone ([The zoom](#camera-animation-and-preview)). A board in 3D
  keeps its zoom, which zooms its camera: there is no cube, and its way back is View's Reset view. The corner's
  controls stand bare on the picture, so they take **the viewport's theme** (below), not the app's. A phone has no
  corner control (no cube, no zoom: a pinch zooms, and View's Reset view brings the view back). The side, 2D/3D and a
  board's presets are View's submenus (Side ▸, Mode ▸, Display ▸), counted as `board_side` and `board_dimension`; with
  no navbar a phone has them as rows of the strip's More, in the strip's order (a 3D view's Projection, Display, the
  zoom's, Preview; a board's View from bottom and 3D view, ticked while they are, then Display, whose choices in 3D end
  with the projection, in 3D Reset view, then the zoom's). A view drawn as a picture, or one that is loading or failed
  to load, has none of them. In Preview the strip is gone and Preview's own controls are its bar's (see
  [Preview](#camera-animation-and-preview)).
- **The corner at the left** (`viewportLayout.js`'s `viewCornerLayout`): a host that anchors the cube at the
  top-left (`--cad-viewport-corner-left`) moves the corner there, mirrored: the cube or the zoom the corner's inset
  from the left edge, the zoom's menu opening to the right; `--cad-viewport-corner-top` lowers it either way. The zoom
  is placed from the host's corner variable as the cube's box is, so a host that moves the corner moves the zoom with it.
- **A file's routines are the panel's Animation tab** in the tools view (see [Preview](#camera-animation-and-preview)):
  nothing of them is on the strip or under the model, and a file without routines has no tab. In Preview, Preview's
  own playbar under the model. Nothing else sits at the bottom centre.
- **Model update status** sits under the strip and its sub-toolbar, centred, and where
  there is no strip (Preview, a compact view, a load) at the top centre, in the strip's
  34px row, in every host and every view, 2D or 3D: the one frame draws it (`ViewFrame.jsx`'s
  `status`) from what the view says — a newer revision loading behind the picture, a Display change
  being prepared, or that change's failure with its **Retry** (a flat view's Display needs no
  preparing, so it has none to offer: a failed update is the alert card's, whose Retry reloads) — and
  nothing while the alert card says why the view's chrome is gone. It is renderer chrome: the navbar
  carries no status. On mobile it is a tappable progress icon whose popover names what is loading.

## Tools and lifecycle

| File | Tool strip, left to right |
| --- | --- |
| STEP | Select, Draw, Measure; Explode (two or more parts), Clip |
| URDF / SRDF | Select, Draw, Measure; Clip |
| GLB | Select, Draw, Measure; Explode (several rigid nodes that draw), Clip |
| 3MF | Select, Draw, Measure; Clip |
| STL | Select (in hand: its bodies), Draw; Clip |
| DXF | Select (in hand: a tap picks an entity, a plain drag draws [the box](#box-selection); a right or middle drag, or a drag with Ctrl, Cmd or Shift, pans, as a trackpad's two-finger scroll does, a mouse's wheel and a pinch zoom), Draw, Measure |
| KiCad board | Select (in hand, as KiCad's: a click picks what its filter ticks, on a layer the Display draws, a click on nothing clearing; a plain drag draws [the box](#box-selection), naming the area on the view's working layer where it takes nothing; the rest are the 3D views' drags: a right or middle drag, or a drag with Ctrl, Cmd or Shift, pans, as a trackpad's two-finger scroll does, a mouse's wheel and a pinch zoom, a double-click fits: the board whole, 6% of the pane’s smaller side clear round it (16px at least) and clear of the strip, as it opens and as its snapshot frames it), Draw, Measure |
| KiCad schematic | Select (in hand, as a board's: a click picks what its filter ticks, a click on nothing clearing; a plain drag draws [the box](#box-selection), taking what it touches; the rest are a board's drags; a double-click on a sheet symbol enters its sheet, anywhere else fits: the page whole, with a board's margin and clear of the strip), Draw, Measure |

The view's controls are not on the strip under a file's navbar: they are the navbar's **View** and a 3D view's
**Preview**, View left of Preview, for every kind of file ([The View menu](#the-view-menu-and-a-phones-sheets): a 3D
view's Projection, Display, Background, Show grid and Reset view; a board's Side, Mode, Display, in 3D Projection,
Background and in 3D Reset view; a drawing's and a schematic's Background), and the picture keeps the camera's own
control: a 3D view's cube, a flat view's zoom. Outside a navbar (a host's inline card) View and Preview end the strip
([The view's corner](#ownership-and-layout)).

There is no activity dot, and no rule on the strip. The view's controls are no tools (see [Ownership and layout](#ownership-and-layout)). Position is no tool:
its knobs are Select's, while Select's filter picks Position, and its controls are the
[panel](#the-panel)'s Joints tab; the file's routines play from its Animation tab (see [Preview](#camera-animation-and-preview)). A file with no tools
and no 3D view has no strip at all.

**A tool the file cannot offer is not on the strip**: never shown disabled.
Renderers leave it out of the `tools` they hand over; `FloatingToolBar` draws
what it is given. Until a file has loaded, what it offers is not known: a tool
that depends on it (Explode) is shown idle meanwhile, a robot's filter offers
Position meanwhile, and the whole strip is disabled while loading. Unavailable and
idle are different states.

One tool owns pointer input, and it alone is lit on the strip. **A press on the tool in hand
does nothing**: a tool is put down by taking up another (Select, most often), or by Escape, which
takes Select up. **Explode and Clip are tools**, as Draw is: a press takes one up, its button
pressed, its row docked under the strip (`SubToolbar`, the drawing tools' width). In hand it stands over
Select, the mode underneath (`useRendererShell`'s `effectTool`), so a press on the model picks as Select's
does and orbit, pan and zoom are as ever. What it sets stays on the model once another tool is taken up
(tools coexist), until its Reset: an explosion, a cut, like a pose, has nothing on screen for it then but
the model and the dot in its tile's corner (`ChangedDot`, while it is set and not in hand). Taken up again,
it is as it was. Preview's tile alone is a mode.

| Tool | Pressing it | Its sub-toolbar | Leaving it |
| --- | --- | --- | --- |
| Select | The default tool of every 3D file; picks what its filter ticks, or a GLB's nodes, a 3MF's objects, an STL's bodies (Shift adds; Delete deletes annotations and measurements); what is picked is Quick Edit's chips | None: its filter is the chevron after its button | The selection stays, lit and in Quick Edit, under any tool |
| Draw | Draws on the view with the tool in hand: the pen, the highlighter, a shape (line, arrow, rectangle, ellipse), text, Fill (a closed shape's interior) or the eraser; its button shows that tool | One row: the drawing tools (Pen, Highlighter, Line, Arrow, Rectangle, Ellipse, Text, Fill, Eraser), a rule, then Color, Stroke width, Placement and Clear annotations (Undo and Redo are ⌘Z, ⇧⌘Z) | The annotations stay in the model, their chip in Quick Edit; Draw keeps what it last drew with, the strip showing its icon |
| Measure | Arms picking two entities and reading what the pair makes (an engine document's — an `.xbf`'s or a STEP's — exact vertices, edges and faces, what its filter ticks; on a mesh, two points on its surface, approximately, in its file's unit; a drawing's ends, centres and lines, in the unit it declares, else "units"); each result a chip in its colour | Its measurements, as chips, then Clear measurements; none while nothing is measured | Unfinished picks are cancelled; completed measurements stay, drawn on the model, their row back with the tool |
| Explode / Clip | Takes it up over Select (a press on the model still picks); an edit applies the effect (Explode's, as a motion: see below) | One row, the drawing tools' width: the slider, its amount beside it, Reset; Clip's axis first, whose dropdown holds its settings | The effect stays on the model, the dot on its tile |

**One motion at a time.** Every tool's state stands beside every other's — the selection,
measurements, the annotations, Clip — except the two that move the parts: **Explode** and
the **Joints** pose. They replace each other: exploding puts the pose back at its
default, and using Joints (a knob dragged, a value set or a named pose chosen) takes
Explode off, with nothing set aside to come back. While the model is exploded there are no
knobs. Its popover closed, the explosion stays under every tool until Position is used. A
routine played from the playbar is the third motion: playing it puts Explode and the
pose back at rest, and using either puts the routine back at rest; paused, its frame stays on the
model as a pose does. **Nothing that moves the model ever disables another**: whatever holds the model,
every other motion's controls stay live, and using one resets the other to its default and takes over.
Joints shows a paused routine's frame in its controls and knobs; a Joints edit lets the routine go first
(explicitly) and then poses the model, a slider or a knob from the frame it showed, so nothing jumps, a
named position or Reset outright. A parameter edited lets a routine go too, whether or not its preview
builds; it keeps the Joints pose while the joints are the same and puts it back at Default when they changed.
Joints and Explode never reset the parameters. While a routine plays, its knobs step aside (they would
stand where the model was) and come back as it pauses. Preview's routine is its own and moves nothing of the tools view's.
Another file has the motions its tools have, under the same rule, decided by value
(`kit/tools/model-effects/motionExclusion.js` for a GLB and an engine document; the robot
renderer's own rule, `RobotRenderer.jsx`, for a robot): a GLB's Explode, routine and Clip; a robot's
Position and Clip; an engine document's Explode, Position and its motions (its **Motion**
section, where Position shows a motion's frame while it owns the pose, and an edit takes over from it).

A tree is the view's panel's, there under every tool; a pick in it takes Select up
before it acts.

**Removing an effect.** Explode's and Clip's rows end in
Reset ("Reset explode", "Reset clip"): always there, disabled while there
is nothing to take away, it removes the effect — the amount back at zero, nothing else (Clip's
axis and its settings stay as set) — and leaves the popover up. Position's way back is its Pose row's Default. A
measurement's chip X deletes it, and Measure's Clear measurements all of them; the Annotation chip's X clears the annotations.

**Select and Measure are the tools with a menu on the strip** (Measure's on a STEP only), each its selection filter: the
chevron right after the button (`ToolSettingsMenu`'s "chevron" trigger, `kit/tools/ToolModeMenu.jsx`),
as tall as the tile and touching it. The button and its chevron are **one control**
(`FloatingToolBar.js`): one rounded fill lights the pair on hover, while the tool is in hand and
while its menu is open, and the chevron's half only brightens over it, on its own hover and
while its menu is open, with no line between the halves. A change
to a filter takes its tool up. A press on any other tool is its only action. Whatever a tool can
be set to while it is up is its sub-toolbar. A dropdown is ordinary — under its own button,
free to overlap the view — and closes with no exit animation, so a quick second tap (touch
included) always reaches its trigger. Choosing a value closes it; ticking an option leaves
it open, as do Clip's axes and the app menu's Theme. Menu checks sit on the right. The other dropdowns over the viewport are Display,
the sub-toolbars' (Clip's axis and settings, the drawing tools' colour, stroke width and placement), its
context menu, and the playbars' routines and Playback settings (`PlaybackMenu.jsx`, on
`ToolPopover`). Preview's settings are a panel, not a dropdown (see [Preview](#camera-animation-and-preview)).

**A picking tool's chevron menu has one anatomy, every file's** (`kit/tools/select/SelectionSettings.jsx`,
after Fusion's Select menu and KiCad's Selection Filter): an optional **Selection tool** section, then
**one row, Filter**, never its boxes laid in the menu itself. The row is a stock submenu
(`DropdownMenuSub`): its name, what is ticked muted at its right against the chevron (as the app menu's
Language), and its boxes in the submenu, which is named after it. It is one shared component, `FilterRow`,
under one shared menu, `kit/tools/select/SelectFilterMenu.jsx`, that no renderer rebuilds. A menu holds
its one row even where it holds nothing else (a board's). The menus built on it: Select's on an `.xbf` and
a STEP (`xbf/XbfSelectionModes.jsx`'s `SelectMenu`), Measure's (`kit/tools/measure/MeasureFilterMenu.jsx`),
a robot's Select (`robot/RobotRenderer.jsx`), a board's and a schematic's Select
(`board/BoardSelectFilter.jsx`, `schematic/SchematicSelectFilter.jsx`). Labels are sentence case ("Rule
areas"). A phone has no room beside the menu for a submenu (a stock one ran off the screen's edge at
390px, either side): there the row opens its boxes under it, in the menu itself (`DropdownMenuInlineSub`,
below).

**Filter** is KiCad's Selection Filter, every picking tool's: what a click may take, as a list of kinds,
each ticked on its own (`kit/tools/select/selectFilter.js`); a kind left out is not pickable. Its submenu
holds **All** (ticked when every kind is, a dash while some are; it ticks or unticks every kind), a rule,
then the kinds in ONE column, each a stock checkbox item, its name alone, its check at the row's right
end; then, after another rule, the **extras** that are no kind, which All leaves as they are: a board's
**Locked items**, a posable model's **Position**. Ticking a box leaves the submenu up (a press on the
view puts the menu away) and takes the tool up. **Glyphs**: the boxes are names alone in every file,
as KiCad's are, because most kinds (a board's nine, a schematic's six, the annotations and
measurements) have no drawing of their own and a column that mixed glyphs with bare names would not
line up; the glyphs live on the strip's button instead (below). The row sums up the kinds ticked —
**All** when every kind is, the kind's name when one is, **None** when none is, else how many of how many
("3 of 9"). The chevron's name says what is ticked: "Filter: everything" while every kind and every
extra that is a thing of its own (Position) is, with a ticked modifier after it ("Filter: everything,
Locked items"); else the kinds and extras ticked ("Filter: Pads, Vias", "Filter: Faces, Position"); else
"Filter: nothing" (Measure's "Measure filter: …"). Every box is `data-<tool>-filter` (its id, "all" for
All), the row `data-<tool>-filter-row`, the chevron `data-<tool>-filter-trigger` ("all", the ticked ids,
or "none"). Each press on a box is counted (`selectFilter.js`'s `filterControl`: `select_filter_faces`,
`measure_filter_vertices`, `select_filter_rule_areas`, `select_filter_all`). Every box is ticked when a
file opens (but a board's Locked items); the filter holds while the file is open, across updates of it,
and another file starts with every box ticked.

**The strip's badge.** The tool's button wears what its Filter ticks as a badge on its glyph
(`modeGlyphs.jsx`'s `ToolModeIcon`, `selectFilter.js`'s `filterBadge`), so what a click takes is on
the strip, not only in the menu: none while every kind is ticked; the kind's glyph when exactly one is
(Parts a whole cube, Faces a faint cube with its top face filled, Edges one with an edge heavy,
Vertices a dot in a ring); Position's knobs where no kind is and Position is; otherwise — several kinds,
none, or one with no glyph of its own (a board's Pads) — a funnel, "filtered".

**An `.xbf`'s and a STEP's Select** (`xbfSelectKinds`, `xbfSelectExtras`): **Parts** (an assembly's
only — in a part file a press that reaches no face or edge picks the whole part), **Faces**, **Edges**,
**Annotations** and **Measurements** (drawn over the model, so a click on one is never taken for the
face under it), then **Position** (where the file has joints to move: its knobs show while it is ticked,
beside whatever the kinds pick, as they always did with every box ticked; Position alone is the knobs
with the model picking nothing). Any mix of kinds picks through the scene's one pick (below). With no
kind ticked the model offers nothing: the pointer lights nothing and the hover tip names nothing, a
click lets the selection go as a click on empty space does, and a box takes nothing. **Measure's**:
**Vertices**, **Edges** and **Faces** (`measureFilter.js`): the vertex near the pointer, else the edge,
else the face, each where it is ticked, a kind unticked falling to the next the filter allows; with none
ticked a press takes the free point on the model. **A robot's**: **Links**, then **Position** (where a
joint can be driven; a robot with nothing to drive has no menu). How a face or edge pick grows is no
setting: a face's or an edge's tangent chain is an action of the view's menu (Select tangent faces,
Select tangent edges, below).

**A board's** (`board/BoardSelectFilter.jsx`): **Footprints**, **Text**, **Tracks**, **Vias**,
**Pads**, **Graphics**, **Zones**, **Rule areas**, **Dimensions**, in KiCad's order, then **Locked
items**: ticked, a click takes what KiCad saved locked as well (a pad is taken whatever its part, as
KiCad's single click), and it is unticked as a board opens, as KiCad's. Every kind is ticked as a board
opens; the filter holds while the file is open. A click takes the most specific thing the boxes tick
(`board/boardPick.js`): with Footprints ticked a footprint's graphics are its part's; with the zones
alone a zone is taken anywhere inside it. KiCad's Grid Items, Points and Other items have no box: the
board's index holds none of them. A whole net is picked from the panel's Nets, not by the filter. Select
on a board has no modes: a click picks and a
plain drag draws [the box](#box-selection), which takes what it touches as the filter does, and names
its area on the view's working layer where it takes nothing; every other drag
is the 3D views' (`useViewerRuntime.js`'s OrbitControls, the left button's orbit being the box): the right button's drag pans (a Mac trackpad's two-finger click and
drag), as does the middle button's and a left drag with Ctrl, Cmd or Shift held (a Shift click still
adds), and so does a trackpad's two-finger scroll, as Figma's does; a mouse's wheel, a wheel with
Cmd or Ctrl and a pinch zoom (`kit/viewport/wheelGesture.js`); the browser's menu is kept off
the board, as off a 3D view.

**A schematic's** (`schematic/SchematicSelectFilter.jsx`): **Symbols**, **Pins**, **Wires**, **Labels**,
**Sheets** and **Other items** (junctions, no-connects), and no Locked items. A click takes
the nearest ink, and of what is about as near the most specific — a pin, a junction or a no-connect, a
label (a sheet pin, its net), a wire, a field (its symbol) — then the symbol body or sheet symbol it is
inside. A whole net is picked from the panel's Nets.

**Select tangent faces and Select tangent edges** are the 3D view's menu's (`kit/shell/viewMenu.js`'s
`tangentGroup`, `xbf/xbfMenuItems.js`), in its pick group after Select or Deselect: actions, not
settings that stay on, as Fusion's and SolidWorks' tangent chain. Each shows only where it applies:
tangent faces over a face, or while faces are selected; tangent edges likewise for edges
(`xbf/xbfMenus.js`'s `xbfTangentSources`); over empty space they open the menu while faces or edges are
selected. Running one adds to the selection the tangent chain (`xbf/xbfSelectionFilter.js`'s
`tangentChain`, from the engine's groups of the part) of the face or edge pressed and of every one of
its kind selected: the faces joined across tangent edges, the edges that continue one another. A click
and a box take what they land on, never a chain.

The geometry ticked, whatever its mix, is picked as one mode (`xbf/xbfSelectionFilter.js`'s
`selectGeometryMode` and `xbfGeometryPicks`, the booleans the scene's `pickElement` and `pickBox`
take): Parts with Faces, Edges or both, a press takes the face or edge it lands on (of those ticked)
where the part's topology can be picked, and the part elsewhere; Parts alone, the part; Faces, Edges,
or both, that topology alone; none, nothing. The mode sets the model tree's shape: with Parts and
topology ticked, or no geometry at all, it is the person's own (put back as it
was when they left it, with the owners of what is still selected kept open); Parts alone
opens every assembly and shuts every part; Faces, Edges or both open every assembly. A
part is a leaf in every shape: nothing opens under it, and a face or edge picked in the
viewport is revealed at its part's row. Outside the person's own shape the disclosure is
locked (chevrons shown, not pressable) and Expand/Collapse leave the row menus. Every face and
edge is to hand from the start: nothing waits on a part's topology.

Above the Filter row, in its own section headed "Selection tool", an `.xbf`'s and a STEP's Select menu
chooses how a pick is made, apart from what it takes: **Select** (the pointer, the default) or
**Box select** (lucide's square mouse pointer). Choosing one puts the menu away, takes Select up,
and puts its glyph on Select's button (named "Box select" while it is chosen), still badged with
what the Filter ticks. Under Select a drag turns the camera. Under Box select a drag that starts on empty space
draws [the box](#box-selection); one that starts on the model's visible geometry, on ink or on a
measurement turns the camera as Select's does (Shift with it too), so the camera is never lost.
What the box takes of the model is what is *visible*: hidden faces, parts behind others, an
isolation's dimmed neighbours and clipped geometry never join, and a face or a part partly behind
another part counts by the part of it that shows. It takes
what a click would under the Filter: with Parts and topology ticked, the faces and edges ticked of the
parts that are open (expanded or isolated in the Model tree; a part file's always) and every other part
whole, as the node a click takes; Parts alone, the parts; Faces or Edges, those alone, never their tangent
chains. With the model it takes the measurements and the annotation's
ink by the same rule (a dimension's lines, arrowheads or label; a mark's ink at its drawn width,
with what was drawn with it), while Measurements and Annotations are ticked. Ctrl/Cmd/Alt drags and other buttons
still turn the camera, a second finger or Escape lets the box go, and Quick Edit, Copy Reference
and `cad_view` see the selection as any other.

**Sub-toolbars** (`kit/tools/SubToolbar.jsx`): the tool in hand's controls, one row hung
under the strip, centred, 8px below it, on the strip's surface **at the strip's proportions** — a 40px row with its
border, 10px corners, 5px in, 28px buttons with 4px corners and 16px icons (the drawing tools' two rows alike; a word button its own width at that
height; a measurement's chip its own size) — one rule in the shared component for every tool's row, its groups — what the tool does, then how it looks and what clears it — parted by a
thin rule. It stays up for as long as its tool does, and has no heading: the tool's lit
button above names it. Explode's and Clip's rows are the same component (`model-effects/ModelTools.jsx`), under the
strip while the tool is in hand: one shape — the
[slider control](#the-slider-control) on one line (what leads it, its slider, its value), the
tool's actions (neither has any), then Reset, last, at the same spot in both, with no rules — and
one width (`SLIDER_SUB_TOOLBAR_CLASS`, 240px, the drawing tools' row's too, `SUB_TOOLBAR_WIDTH_CLASS`; a phone's 320px). The slider takes the rest of the
row. A tool's options never sit in the row as checkboxes, labels or
buttons of their own, which would squeeze the slider: they are the dropdown of what leads it
(Clip's axis).

**Draw.** Drawing is ONE strip tool, **Draw** (`annotation/toolbar.jsx`'s `drawStripTool`), a plain button with no
chevron or menu: it shows the icon of what it draws with now (the pen at first; a shape's once one is chosen), its
tooltip that tool and its key ("Rectangle R"), and a press takes up the one last chosen. What it draws with is its
row's (below): the **Pen** (the freehand ink, tapering with pressure or speed), the **Highlighter**, the **Line**,
**Arrow**, **Rectangle**, **Ellipse**, **Text** (a mark put down in place), **Fill** and the **Eraser**. **Fill** (lucide's
PaintBucket, its key **G**, a bucket for its cursor, its tooltip "Fill closed shapes") draws nothing of its own: a press
inside a closed shape — a rectangle, an ellipse, or a pen or highlighter loop whose ends are less than 20px apart on the
screen as it is now (`geometry.js`'s `FILL_LOOP_GAP_PX`, `fillableOutline`) — fills it with the colour in hand — the
same fill, in the same data, as the selected shape's Fill toggle (an area grouped with the shape, lying where it does) —
a press within 6px of its outline counting as inside it, and where shapes overlap the topmost (last drawn) taking it
(`fillTargetAt`); the shape a press would fill is haloed while the pointer rests on it. A press on a shape filled in
that colour unfills it, and on one filled in another colour recolours its fill; a press on an open mark (a line, an
arrow, a pen stroke whose ends are apart) or on nothing does nothing; each is one step to undo. Under it Stroke width and Placement are off (Colour is what it puts down). Under it
the two are still two modes of the tool (`pencil`, `shapes`: what each draws with, kept apart), a
tool chosen in the row taking its family up, sharing the annotation and its history but not the style: the colour, stroke width
and placement are kept **per drawing kind** — the Pen, the Highlighter (which opens in neon yellow) and Shapes (all five
shapes share one) — and the row shows and sets the tool in hand's own — and **one sub-toolbar**,
"Annotation controls" (`annotation/toolbar.jsx`'s `AnnotationToolbar`), **two rows of seven on one surface**, left-aligned,
4px apart and no rule between them: the first **the tools that put ink down**, one group ("Drawing tools"), a button
each, its key in its tooltip, the one in hand pressed, in the order a person reaches for them, as design tools order
theirs — **Pen, Highlighter, Line, Arrow, Rectangle, Ellipse, Text** (choosing one is how Draw changes what it draws
with); the second the two that change ink already down, **Fill** and the **Eraser** ("Editing tools"), then what is
drawn next, each a dropdown whose button shows its value, no chevron: **Colour** (no heading, a grid of swatches, unnamed but for assistive technology: the neons and
one neutral that reads against the viewer, white in dark mode and near-black in light, then
the colour wheel, which opens the system's colour picker for any other colour, kept once the
picker closes), **Stroke width** (no heading, four weights, 1, 2, 4 and 6px, the pen drawn to look the
same weight; each row a straight line drawn at that weight, unnamed but for assistive technology, the current one
checked; the button a fixed glyph whatever the weight, three lines thin to thick), **Line style** (headed with its name,
**Solid**, **Dashed** and **Dotted**, each a line drawn in it, the current one checked; the button a fixed glyph, three
lines solid, dashed and dotted, so the two buttons read apart, as Figma's and Excalidraw's do, and each names
itself on a hover, "Stroke width" and "Line style"; telemetry `annotate_line_style`: the pen's and a
shape's outline — an arrow's shaft, its head always solid — drawn in it, its pattern in screen pixels scaled with the
stroke's width, a dash four widths with three between, a dot its round caps two widths apart, `dashPattern`; kept per
drawing kind as the colour is; greyed for the Highlighter, Text and Fill, which draw no line, so the row never
jumps; on Select's selection bar it restyles the strokes picked; a mark written before there were line styles is
solid; the 3D view, the 2D views, a Quick Edit's packet and a snapshot all draw it) and **Placement** (laid out as the strip's menus are: headed with its name, a
row per choice, the check on the right: **On surface**, the default, its glyph a sphere: each point of the next mark on the visible
surface under it; **On plane**, its glyph a sheet: the whole mark on the plane of the surface it
starts on; a flat view, a DXF, has none); then **Clear annotations** (the trash), disabled while there is
nothing to clear. Under the **Eraser**, which draws nothing, Color, Stroke width and Placement are disabled (greyed out, still
on the row so it does not jump). Undo and Redo have no buttons: they are ⌘Z and ⇧⌘Z (Ctrl+Z, Ctrl+Y). The two rows are the same at every width; on a phone their
buttons are 36px tiles and, where the tools are wider than the view, they wrap rather than scroll (there is no second menu on
the strip for it). The **Highlighter** draws a freehand stroke like the pen's, but broad and translucent: five times
the chosen stroke width, 35% opaque, round at its ends, with no pressure taper; it is an ordinary stroke, picked,
erased and recoloured as any (its Stroke width in the selection's bar is the same setting). The tools have no Select or Pan of their own (Select picks
annotations; a right or middle drag is the view's, exactly as under Select — the press handed to the canvas with its
own button, so a 3D view's right drag pans, a flat view's does what Select's does — and Space hands the pointer to the
view: `AnnotationOverlay.jsx`'s `viewPressInit`). Never a restyle of ink already down: the
annotations Select picks have their own bar, a small floating toolbar on the tool strip's
surface just above them — Color and Stroke width dropdowns, Fill for a closed
shape (what the Fill tool takes: a pen or highlighter loop too), a rule, Delete. An update of the model forgets the annotations too, their history with
them (Undo has nothing to bring back), and leaves the tool in hand, with its tool, colour,
weight and placement. The pen and the shapes share one default stroke
width. The annotations have no panel: while there are any they are Quick Edit's
**Annotation** chip (its X clears them), and while Draw is up the copy shortcut writes
the view with its annotations to the clipboard as a PNG. A first stroke opens
[Quick Edit](#quick-edit), whose context row carries the **Annotation** chip while there is ink. The drawing tools
disable the cube without hiding it.

**Measure.** Its button is the ruler, badged as Select's is with what it
picks alone. On an engine document (an `.xbf`, or a STEP, which opens as one), its menu is
Select's own (`kit/tools/measure/MeasureFilterMenu.jsx`): **All** (when a file opens),
**Vertices**, **Edges** or **Faces**, one chosen. A press takes an ENTITY, whole, as a CAD measure
tool does: an edge's end within 10px of the pointer is its vertex, else the edge, else the face
(`measureFilter.js`, `xbf/xbfMeasurePick.js`), of any part, open in the Model or not. What
lights under the resting pointer is what a press takes, with what it is worth on its own beside
it (a vertex's X Y Z; an edge's length or ⌀, a face's ⌀ or normal and its area, the length along
a curve and the area the engine's facts of it, shown once they are in). With one kind chosen,
only that kind is taken: an edge's end is still its vertex under Vertices, and anywhere else a
press takes nothing. Shift held, a press takes the point on the model as it is.

The reading follows from the pair (`@cad/core/lib/viewer/measureEntities.js`), not from
where on each the pointer happened to be:

- two vertices: the distance, with ΔX ΔY ΔZ;
- parallel faces, parallel edges, a vertex to a face or an edge: the perpendicular distance, "⟂";
- a hole (a circular edge or a cylinder) to anything: from its centre or axis, so two holes
  read "C-C" and a hole to a face its distance from that face;
- faces or edges at an angle: the angle, "∠", the acute one;
- anything else: the shortest distance between the two.

A pair with no gap (an edge in its face, two flats at one height) reads as the distance between
the two points picked. A press on the entity already held lets go of it, as does a press on
nothing. On a mesh there are no vertices, edges or faces to take: a press takes the point on its
surface under the pointer, and the menu goes. A drawing's Measure has no filter.

Its sub-toolbar is its measurements (`kit/tools/measure/measurementChips.jsx`'s `MeasurementsBar`),
there while Measure is the tool and something is measured, and no row at all while nothing is:
each completed measurement a chip, Quick Edit's own (`ReferenceChips.jsx`, a few then "+N more"),
the ruler in the measurement's colour (the colour of its line on the model) and its reading; its
X deletes it, resting on it lights its line and labels it, and its card, opening under it, is the
full reading (what the pair makes, the angle or the shortest distance with it, the delta along
each axis between two points, what each end bound to); then a rule and **Clear measurements**.
Measurements are the person's alone: none of them goes to the agent, in Quick Edit or its
snapshots, and measuring never opens Quick Edit. They stay, drawn on the model, under every other
tool; a press on Measure while it is up does nothing.

**Explode and Clip** have no enabled checkbox, and their rows are drawn alike, each under the strip while it is in hand.
Explode's: its name, its slider, the amount (a percentage), **Reset explode**. Clip's: its axis — a
borderless button reading the axis in hand, "X ⌄", lit while its menu is open — its slider, the
amount, **Reset clip**. The axis's dropdown holds all of Clip's settings, on Display's surface
and in its type, as narrow as its content, with no heading and no glyphs: first X, Y and Z, a
compact group of the app menu's Theme buttons (24px squares, its radius, no track) in a row as
tall as an item (a phone's 40px, as Theme's row), the axis in hand in the accent a highlighted
item wears; a rule; then two of Display's `DropdownMenuCheckboxItem`s, plain text with the check
at the right: **Part colours** (ticked by default: each section cap in its
part's normal colour, without hover or selection tints; unticked, every cap one amber) and
**Reverse** (unticked by default: which side of the plane is kept). Caps stay opaque, a
transparent part's too. A press on any of them leaves the menu open, and none of them applies a
cut; on a cut, a new axis or Reverse turns it keeping its share. The menu is part of the popover:
choosing in it, or Escape closing it, leaves the row up. They are settings of the
file's view (`clip.axis`, `clip.partColors`, `clip.invert`, stored and restored with its
display), kept as the tool is put down and by Reset clip. Explode opens at 0%, Clip at no
cut; an edit applies the effect, and the slider back at zero removes it. An axis alone is not
an effect. The view settings own both effects, so a mode reset preserves them and a restored
effect reappears on the model. Clip's slider, left to right, cuts deeper through the original
bounding box; pose, animation and Explode never redefine the range. It shows the share cut
away, while the view stores where the plane stands (`clip.at`, in millimetres), so a model
edit leaves the plane where it was and the slider reads 0% or 100% if the plane ends up
outside the new box. Explode is offered only where there are parts to separate: a STEP
assembly and a GLB of several rigid nodes. A STEP part file has no Explode tile: it has one
part (`STEP_PART_VIEW_FEATURES`).

### Box selection

One box in every viewer that has one (`kit/tools/select/useBoxSelectGesture.js`): a 3D view's Box
select, and a board's, a schematic's and a drawing's Select, where a plain left drag draws it
wherever it starts, on an item too. It has one rule and one look, whichever way it is drawn: it
takes anything it touches, even in part (in 3D, only what is visible), and it is a solid outline in
the selection's blue (`#2979ff`) over a light blue fill. It takes what Select's filter would with a
click, the annotation's ink and the measurements with it, and all it takes stays selected together.
Shift adds to the selection (on a flat view, Shift held at the release: a Shift drag pans there);
otherwise the box replaces all of it, measurements and ink too. A tap still picks. A board's box that
takes nothing names its area on the view's working layer (`#F.Cu@x10y5..x20y15`, what an
agent places, pours or keeps out over), Shift adding it.

## The view's panel and the tool stack

**The view's panel** (`kit/shell/FlatPanel.jsx`, placed by every view's one frame, `kit/shell/ViewFrame.jsx`,
one state, `useFlatPanelState`) holds what there is to read of the
file, whatever tool is in hand, after KiCad's Appearance panel: docked at the view's left edge, the
full height of the view, on the chrome's colour (the navbar's, `bg-sidebar`: a step off the canvas,
`bg-canvas`, the content area behind every view, 2D and 3D, which sits darker than the chrome in
both themes, as Figma's, VS Code's and Linear's canvas does)
with a rule at its right, and the canvas the narrower for it while it pushes (see [The panel](#the-panel)):
the picture is drawn in what it leaves, nothing of it under the panel. It is **the view's one sidebar**: the file's
structure, then what the file lets the person set. Its tabs: a board's Parts, Nets and Layers, a schematic's Parts, Nets and Hierarchy, a drawing's Layers (handed in); a 3D
view's its renderer's structure (`ToolPanel`s, each a tab by its name: a STEP's or an `.xbf`'s **Model** — an assembly's
tree, a part file's one row —, the Model's Show all on a line over its rows, the trees searched by the panel's search;
a robot's **Links**). A GLB's Model tab is its node tree, a 3MF's its objects and an STL's its bodies
(`kit/inspector/SceneTreeSection.jsx`: a row a node, an object or a body, a pick in it the same as on the model). **Every
file has the panel, from the view's first frame**: its structure's tab is there while the file loads, so neither the
panel nor its toggle comes in late and pushes the model aside, and it is open or collapsed then as it is once the file
is in; a load that fails has none. **While the file loads, a structure tab with no row yet shows placeholder rows**
(`FlatPanel.jsx`'s `FlatPanelRowsLoading`, `primitives/tree-row.jsx`'s `TreeRowsLoading`, in the pinned panel, a peek
and a phone's sheet alike): six of the rows' own 28px lines, each a block the glyph's size on the inset and a bar where
a name starts, of uneven widths, fading out downwards, in the muted ink, pulsing gently (still where less motion is
asked for); its tabpanel `aria-busy`, and "Loading" said to assistive technology. No spinner and no words in the panel:
the view's loading cover says what is loading. They go as the tab's first row is drawn (an engine document's tree
fills before its model is drawn, so its rows replace them early), and never stand in for a search's hits. Loaded, a tab
with nothing to list shows what it always has, and a failed load has no panel. A file whose tree is optional always shows it, even of one row, as a
STEP part does: a 3MF of one object its one row, a GLB of one node its one, a GLB with no node one row named for the
file, which picks nothing. An STL lists its bodies (`stlBodies.js`: the triangles that share corners, welded at a
millionth of the model's diagonal), largest first by triangles, as **Body 1**…**Body N** (a named solid of an ASCII STL
its own row, by its name); an STL of one body is one row named for the file (or for its one named solid), and one of
more than 2,000 bodies is not split: one row. The bodies are split after the model shows (on a million triangles the
split takes about twice the parse), so the row for the file stands until they are in. A drawing always has its Layers,
a drawing of one layer its one row. After the structure's
tabs, **only where the file has them**, what it lets the person set, each a tab by its name (`ToolPanel`s, the
renderer's `fileSections`, then the shell's Animation): **Params** ([Parameters](#parameters)), **Joints** (Reset in
its actions row, last, as Parameters' Reset and Save are), **Animation** (`kit/tools/playbar/AnimationSection.jsx`,
below). The strip is for using tools, the panel for reading the file and setting what it declares, the corner for how
it is looked at, and Quick Edit's chip list for what is selected.

### The panel

One panel, a sidebar at the left, as Figma's Layers panel and VS Code's Explorer are (`kit/shell/sidebars.js`, placed by
`ViewFrame.jsx`). The view once had a second one at the right (Details, View and the file's settings as sections); it
went, because two panels left the model too little room in a narrow pane and split the file's settings from its
structure. Every rule here, and why:

- **Its toggle is the navbar's** (`file-viewer/panelToggles.js`: the frame says it, `FileViewer` hands it to the navbar),
  **the navbar's first control, before the logo**: the strip's 28px tile, its icon the sidebar's (`SidebarIcon`: a
  rounded rectangle, 14 × 12 in the 16px box, its corners 3px, and a short line inside near its left edge, half its
  height, centred, at lucide's stroke), **the same neutral button whether the panel is open or shut** — no pressed
  fill, no brand colour: the panel beside the model says which — its state said to assistive technology by
  `aria-expanded` (the panel pinned open or not; a peek, below, is not said) and by its name, "Hide panel" or "Show
  panel", its tooltip that name and its key (⌘\, Ctrl+\), **at its right**, on the navbar's row, so the tooltip never
  stands over the panel when it peeks under the toggle. Its
  icon stands on the panel's inset, 16px in (the row's 8px, 2px before the tile and the tile's own 6px), so it is on the
  line every text and control in the panel stands on. Home has no panel, so no toggle.
- **⌘\ (Ctrl+\) shows and hides it**, as its toggle does (while it peeks, pins it). **\** alone is no key of the
  viewer's: it hides nothing.
- **Collapsed, it leaves nothing over the model**: its toggle in the navbar, or its key, brings it back; nothing opens
  on a hover of the view's **edge** (no hot zone, no rail). **A mouse resting on its toggle peeks it**
  (`kit/shell/usePanelPeek.js`, as VS Code's and Linear's unpinned sidebars show themselves): collapsed by the person or
  by a narrow view, the panel shows after the pointer has rested on the toggle 500ms (`PANEL_PEEK_DELAY_MS`), never
  while a mouse button is held (a drag passing over it), and never for a pointer that cannot rest (a finger: a phone's,
  or a touch screen's press, is a click) nor on keyboard focus — ⌘\ is the keyboard's way to it. It goes once the
  pointer has been outside both the toggle and the panel for the same 500ms, so the pointer can travel from the button
  down into it; it stays while the pointer is in either, and while a popup opened from it is up (a dropdown, ⋯: the
  pointer is in that popup then), and the delay runs again once that popup is shut. **The keyboard in it does not hold
  it**: the pointer gone, it goes, whatever has focus, and focus that was in it goes to the toggle, never left on a
  panel that is gone. Everything in it works as in the docked panel — the same component: tabs, search (/ opens it in
  the peek), a row's pick, sliders — but its width: a peek is passing, so it has **no grip** (none to drag, no hover
  line in the gap at its right, nothing in the tab order); its width is the docked panel's, changed once it is pinned. **Escape** puts it away (before anything else of the view's: the tool in hand and
  the selection stay), and so does a press on the model. **Only the toggle pins it**: a click on it while it peeks
  (or its key, ⌘\) pins it — open, pushing and kept, as a click on a collapsed panel always is (a click with no peek
  up opens it, as ever); nothing done inside it pins it, neither a pick, a tab, a search nor a slider, so moving off a
  peek always closes it. A peek is never kept: the file's `open` is the person's pin or close alone. **It slides**: in
  from the window's left edge as it opens and back out as it goes, the card and all it holds as one (a transform, at the
  menus' 150ms, eased out coming and in going: nothing laid out again, the canvas and camera untouched), removed once
  it is out; the pointer back on the toggle or the card while it slides out brings it back. Pinned from a peek it does
  not slide (the card becomes the docked panel in place), and where less motion is asked for it appears and goes. Once
  it is up, **the toggle's tooltip goes**, and stays away while it is: the panel is showing, which is what the tip
  offered.
- **Pinned, it always pushes.** Open, it takes its width beside the model, the model's area the narrower for it (the
  model centred in what is left); nothing pinned overlays the model at any width, and Escape and a press on the model
  mean what they always mean. **A peek is the one thing that overlays**: it floats over the view at the docked panel's
  place and width (the file's, or the 232px default) and pushes nothing — the canvas keeps its size and the camera does
  not move — because a glance at the tree should not resize the picture; the strip and Quick Edit stay centred on the
  window, over it, as over the docked panel. **A peek is a card**, so it reads as hovering, as Codex's and other apps'
  unpinned sidebars do: its surface stands 4px in (`PanelSurface.jsx`'s `PANEL_PEEK_GAP_PX`) from the window's left
  edge, the navbar's bottom and the view's bottom, its right edge 4px short of the docked panel's, with the floating
  chrome's own rounded corners (the strip's 10px), border and shadow (`shadow-md`), on the chrome's colour. **Nothing
  in it moves**: every tab, row, label, control and icon stands where it does in the docked panel at that width (the
  16px line from the window's edge, the right content line where the docked panel's is) — the card cuts into the
  panel's padding, never its content — and the head's rule, a scrolled row and the sticky actions foot end inside the
  card, clipped to its rounded inside; 4px leaves a row's fill, 8px out from the content line, 3px of the card's inside
  at the left and 4px at the right. Pinned, the panel is as it always was: full height, touching the edges, its rule at
  its right. **A narrow pane starts it collapsed**: it starts open only where the model's area keeps 640px beside
  it (`sidebars.js`'s `MIN_MODEL_WIDTH`), so the view at least 640px and the panel's width (872px with the 232px
  panel), and collapsed below. **That
  collapse isn't remembered**, so widening the view brings back the person's choice; opened over it, it pushes. The
  strip and Quick Edit stay centred on the window, over the panel (the hard rule above).
- **What is kept is the person's choice, per file, for the session** (the file's entry in the tab's settings,
  `filePanel.js`: `open`, `width`, `tab`); a record from when the view had a right panel (`right`,
  `rightWidth`, `sections`), or from when \ alone hid everything (`hidden`), is read as nothing.
- **Its tabs**: the structure's first (Model; a board's Parts, Nets and Layers; a schematic's Parts, Nets and
  Hierarchy; a drawing's Layers; a robot's Links), then **Params**, **Joints** and **Animation**, each only where
  the file has it. Their content is as it was in the right panel's sections: Parameters' two-row sliders with the
  borderless value field, its foot and its locked state; Joints' Position dropdown; Animation's Clip dropdown, its play
  button and scrubber, its Speed dropdown and its Loop and Autoplay switches. Tabs that do not fit the head
  are ⋯'s items (below), never truncated and never scrolled.
- **Animation** is one control group, not a form, in the panel's 28px rows 4px apart, every control's right edge on
  the right 16px line: the routine's dropdown, a labelled row as Speed is (the tab and the label are the routines' own
  words: an animation's, "Animation" and "Animation"; a mechanism's motion, "Motion" and "Sequence", from the renderer's
  `kind`; the tab's id stays `animation`; a choice plays it from its start), then the transport, a playbar's — Play/Pause and
  **Reset** (the strip's 28px tiles; Reset puts the routine back at its start and the model at rest, idle while it is
  there), then the scrubber the rest of the row, with no time readout (the time is the scrubber's value, read out to
  assistive technology) — then **Speed** a dropdown ("1×"), **Loop** and **Autoplay** switch rows: the label left, its
  switch right, no icon.
- **Parameters** keeps its controls as they were; its status ("Run the script again to edit.") stands right-aligned
  directly above Reset and Save, one or two lines, and is the disabled buttons' tooltip, so why they are off is read
  where they are. **Locked, only the controls look it**: labels and values keep their colours; the sliders and fields
  are at half strength with a not-allowed pointer; a Save that cannot save is drawn as Reset is off (the neutral
  button's disabled look), never a filled grey that reads as pressable. Its foot (`PanelActions`) is sticky at the
  tab's bottom while a long tab scrolls under it. **Joints' Reset** is the same foot.
- **What is selected is read in Quick Edit's chip list** ([Quick Edit](#quick-edit)).
- **A phone**'s panel is a sheet from the left ([A phone's sidebar](#a-phones-sidebar)).

- **One surface, one text size.** The panel is 12px throughout (`globals.css`'s
  `--cad-text-panel`, which the panel sets every step of the scale to inside it, so no list draws another
  size whatever class it names): the search, the tabs, every row, label, value, status and heading. A
  heading is told apart by its colour or weight, never its size, and every line of it is 16px. Every row and control
  in it is 28px — a tab's pill, the search row, a tree row, a settings
  row, a slider's label line, the pose row, an action button — but the head's own row, 32px (a tile and 4).
  A Quick Edit chip's card (`ItemDetail.jsx`'s `data-detail-card`) takes the same one size, so a pick
  reads alike there and in the panel. A menu or hint portalled out of either keeps the chrome's own
  scale (Display's, Clip's and every other dropdown's are unchanged).
- **Its head**, one row as Figma's Layers panel's, the same on a desktop and a phone, built of the same components:
  **the tabs** at its left, then, at its right end, **⋯** where some tabs do not fit and **the search's icon** where a tab
  is searchable, ⋯ directly left of the search, the two 4px apart as every icon pair is; the room left over stands
  between the last tab shown and ⋯. No other button stands in it (the panel's toggle is the navbar's,
  [The panel](#the-panel)). The row is 32px, 8px over it and 8px under it to its rule, which runs the panel's width: the
  rule stands on the strip's bottom line (the strip 8px down and 40px tall). **A tab never shrinks, and the panel keeps
  its width**: the tabs keep their whole width and padding (no truncation, no ellipsis, no wrap). **The panel is
  budgeted for three tabs**: a file seldom has four at once, so every three a file can have — a model's Model and two of
  Params, Joints and Motion, a board's Parts, Nets and Layers, a schematic's Parts, Nets and Hierarchy — fit the default
  width in English beside the search's icon, the widest (Model, Params, Motion) with 7.5px to spare; a fourth, and a
  translation that runs longer (Japanese's model tabs), is ⋯'s. **The tabs that do not fit are ⋯'s items**
  (`FlatPanel.jsx`'s `fitTabs`, measured on a hidden ruler of every tab and the row's own width as a ResizeObserver
  sees them, no fixed breakpoint), in order, each with its icon (and, searching, its count); **the open tab always
  shows**: where it would be in ⋯ it takes the last shown tab's place. Nothing in the row scrolls. The panel's width is
  its own: one fixed default (232px, `sidebars.js`'s `DEFAULT_PANEL_WIDTH`: the least width on the 8px grid where every
  three tabs fit, so the panel takes no more of the model than three need), or what the person's grip set it to, never
  the view's or what the tabs need; the grip alone is bounded as it moves (200px, and the model kept 640px). A narrow
  view collapses the panel; it never shrinks it.
- **A tab's changed dot**: Params, Joints and Animation carry a dot (`kit/tools/ChangedDot.jsx`: 4px, `--brand-icon`)
  against their name's top-right, which moves neither the name nor the tab's width, while their state is off its
  default, exactly while the tab's Reset is on, from the state that turns Reset on (`FlatPanelChanged`, beside the
  button): Params a draft off the document, Joints the pose off the default, Animation the routine off its start.
  Speed, Loop and Autoplay are preferences and never set it. The tab's name then says ", changed"; a hidden tab's
  dot is on its ⋯ item, and ⋯ itself carries one where any hidden tab does. A single tab's title carries it too.
- **The search** covers the tree-like tabs alone — a STEP's or an `.xbf`'s Model, a robot's Links, a board's Parts,
  Nets and Layers, a schematic's Parts, Nets and Hierarchy, a drawing's Layers (`isStructureTab`: the `tree` section,
  or a tab handed in unless it says `search: false`) — never Params, Joints or Animation; its icon is there only where
  the file has a searchable tab. Pressed (or **/**), the head row becomes the search box (`TreeFilterInput`, dense,
  placeholder "Search", its accessible name what it searches — "Search the board", "Search the schematic", "Search the
  drawing", "Search the model"), its X (**Close search**) where the icon was, and the tabs stand in a row under it; its
  magnifier starts on the inset and its X's glyph ends on the right inset, as every icon in the panel does.
  Like Figma's layer search it is **no box**: no border, fill or ring, only its icon and its text, 28px. **Escape or
  the X closes it**, the query gone. A query filters **every searchable tab at once** (KiCad's Parts, Nets and Layers
  alike), each searchable tab's name saying how many it finds (`useFlatPanelMatches`), the open tab showing its own;
  opened from a tab it does not cover it opens the first it does, and a query that finds nothing in the open tab and
  something in another opens the first such, until a tab is chosen by hand.
- **One tab is a title.** A panel with a single tab (a Model with nothing to Position or set, a drawing's Layers, a board
  read without its index) draws no pill: its name, a plain title at the tabs' size and the open tab's weight (500) in
  the tab's place, and no rule under the head, so the title flows straight into its list. **The title is a list row**:
  the head 28px tall (a row's height, not the 32px tab row), 8px over it and nothing under it (`PanelSurface`'s
  `headCompact`), its name on the rows' icons' line, the panel's inset where a row's chevron or icon starts (the head's
  padding, the inset less 8px, and the title's own 8px, a pill's), and the list 4px under it (the
  body's `pt-1`), so no gap stands between the title and its first row. The search's icon stands at the row's right
  end. Several tabs are pills over the rule.
- **Its tabs**, the head's row, pills as Figma's right panel draws them (Design / Prototype), with Figma's room: 28px, 8px
  of padding either side and 4px between pills, so two names stand 20px apart (`FlatPanel.jsx`'s `TAB_PAD_PX`,
  `TAB_GAP_PX`); three fit the 232px panel, and at the grip's 200px the last go into ⋯. The first pill's box hangs 8px
  out past the inset, as a selected row's fill does, so its name stands on it,
  the search's icon (in its 28px button, 7px of it either side) ending on the right inset; the open one a rounded pill on the accent's subtle fill, its name the foreground's at
  medium weight, the others muted on no fill (the accent's half fill and the foreground on hover); each as
  wide as its name in medium weight, so choosing one moves nothing; the head's rule 8px under them; a board's **Parts**, **Nets** then **Layers**, a schematic's **Parts**, **Nets** then, for more than one
  sheet, **Hierarchy**. Arrow keys move between them. The tab shown is the person's, the file's
  (its view's `panel.tab`, below), the first at first. Every tab stays mounted, and each keeps its own scroll.
- **One inset, the same on both sides: `--panel-inset`, 16px** (`styles/globals.css`, on `:root`; in Tailwind
  `px-(--panel-inset)`). Everything read in the panel stands on it, left and right — the search's icon and its text,
  a tab's name, a row's one glyph (a branch's chevron or a leaf's icon), then a row's name after it at 32px, the edge
  of a section's own controls (a settings row's label, as Joints' Pose; a full-width field; a dropdown; a slider's
  track) and the start of every line of text that follows no icon: a heading, a parameter's or a joint's label, a
  file's name over its parameters, a status line ("12 matches", "Saved"), a settings label; a value, a switch and a
  row's last action end on the right inset — and so does the navbar's panel toggle's icon, over it. A box drawn round
  what is read hangs out past the inset by its own padding, so what it holds stays on it: a row's fill (hover,
  selected) by half the inset (8px in from the panel's edge), a tab's pill by its 8px, the head's icon buttons and a
  number field's outline by their 7px. The panel owns the line: its body pads by the inset, and it sets the rows'
  `--tree-row-pad` and `--tree-row-hang` (half the inset) and `--tree-row-actions-pad` (half the inset less 2px), which
  the one row reads (`PanelSurface.jsx`, `primitives/tree-row.jsx`); no section and no list pads itself. Every rule runs the
  panel's width. A settings row's label column is 4rem (its labels are short
  words) and its control fills the rest (`FileSheetSettingRow`). Over a file the navbar's panel toggle's icon stands
  on the same 16px line; over the home, which has no toggle, the navbar's logo does: its drawn mark, not its image's
  edge.
- **One spacing scale**: 4, 8 and 16px, 16 the outer keyline. Vertically the panel steps by 8: 8px over
  the head's row, 8px under it to its rule, 8px between the rule and the lists, 8px under a slider
  before the next control (a slider control is 48px: its 28px line, its 12px slider, 8px), and an actions
  row (Params' Reset and Save, Joints' Reset: `kit/inspector/PanelActions.jsx`) 8px above and below its
  28px buttons, 8px apart. No 6px or 10px step anywhere in it.
- **The Parts and the Nets** (`kit/inspector/CircuitTree.jsx`: `board/BoardSection.jsx`,
  `schematic/SchematicSection.jsx`), two lists as Altium's PCB panel lists Components and Nets. The
  Parts: a board's parts in the schematic blocks their footprints record (a sheet's name without
  `.sch`/`.kicad_sch`; on a board that records none, the kinds: ICs, Resistors, ...), a schematic's in
  the sheets they are placed on; a part is a row with no pads or pins under it. The Nets: flat, each
  its pad or pin count, the `unconnected-(...)` pins shut under their own group, a label. A block's
  name opens or shuts it, as a folder's, and selects nothing; its row menu's **Select all N parts**
  selects every part in it, which Quick Edit shows as ONE chip ("graphic · 34 parts", its X letting
  them all go; `kit/tools/select/groupChips.js`), and **Zoom to** the block frames them. Every row but
  a group's has the view's menu (Copy Reference, Select, Isolate, Zoom to it). A part's or net's selects it as a click on the picture
  does, and leaves the view where it is (a schematic shows the sheet it is on, if it is not the one
  shown); a **double-click** frames what it picked, as KiCad's and Altium's lists zoom to what is
  double-clicked. A row's chevron
  opens or shuts it, and a block's name does too (its chevron, then, is the pointer's alone: the name
  is the keyboard's button). The Parts open as their blocks, a block of several parts shut. A pick
  made anywhere but in the list — on the picture, in Selected, a search hit's once the search is cleared,
  a host's — brings its row into view, once, as a pick in the 3D views does the Model tree's: a part's, or
  a pad's or a pin's part's, in the Parts; a net's, or the net of what is on one (a pad, a pin, a track, a
  via, a pour, a wire, a label, a junction), in the Nets; a row that holds the pick without being it is
  tinted (the search cursor's tint), where a selected row is lit. A text, a graphic or an area moves nothing, and
  a press in the list opens and scrolls nothing (its row is in view). **One block follows the pick**:
  what a reveal opens is not the person's, and the next reveal that goes elsewhere shuts it again; a
  block the person opened stays open, one they shut stays shut until a pick needs it, and one the
  reveal opened is theirs from the moment they open or shut it — so a list is the shape the person left,
  and at most the one block the last pick opened. Nothing picked shuts what the last pick opened, and
  leaves the rest as the person left it. Only a list on screen
  follows: one on a tab not shown, or in a collapsed panel, waits, and brings the pick's row into view
  once it is shown. A
  selected net is lit and the rest stepped back, as KiCad's net highlight. The panel's search reads
  the parts with their pads or pins, so a pasted `#U3.9` finds the pad.
- **No Selected pane.** The panel is its tabs, its search and its lists, at its full height: nothing of
  a pick is drawn under the lists, in any view. What is picked is read in its Quick Edit chip's card
  ([Quick Edit](#quick-edit)), the one place a pick is read in detail, from ONE description the view
  gives of it (`kit/inspector/inspect.js`'s `DetailItem`, through the frame's `inspect`: its
  `describe(id)`; `kit/inspector/ItemDetail.jsx` draws it). **The thing in focus alone**: its name and a
  few key facts, never what it holds or is connected to (the panel's lists are the hierarchy, and a press
  on a row there picks it). The card: the name as its heading, medium weight, 16px in, no fill and no
  glyph, the icon that copies its reference (`<file>#<selector>`, the chip's copy) at the row's right end,
  the whole row that one button; then its facts as one grid — muted labels in a fixed 4.5rem first
  column, values left-aligned in the second in tabular figures — every row 28px, 8px above and below,
  in the panel's 12px. Numbers are for reading at a glance: three significant figures (a number of four figures
  or more whole: 1,037 mm³), in the unit their size reads best in (8.14 g, not 0.008138 kg; 140 cm³, not
  140,073 mm³; 0.378 kg); only the card rounds,
  never what the engine reports or an agent reads. What each view says:
  - an engine document's part or subassembly (`xbf/xbfChips.jsx`'s `xbfDescriber`): a subassembly's
    part count (every part under it), then size (mm), volume and mass; a face its part and area; an edge
    its part and length (an arc's, a circle's circumference);
  - a board's pick (`board/boardTree.js`'s `describeBoardPick`, a few of `boardFacts.js`'s): a part's
    value, footprint, side and **3D model** (the STEP its 3D view draws, or why it has none: "Not found ·
    R_Foo.wrl", "VRML only", "Outside the allowed folders", "None named", from the board's models table,
    in 2D as in 3D, never on hover); a pad's net, pin and type; a net's class and pad count; a track's
    net, layer, width and length; a via's net, diameter, drill, layers and type; a zone's net and
    layers; a text's words and layer;
  - a schematic's pick (`schematic/schematicTree.js`'s `describeSchematicPick`): a part's value,
    footprint, symbol, MPN and sheets; a pin's name, type, net and sheet; a net's pins and sheets; a
    label's kind, net and sheet;
  - a drawing's entity (`dxf/drawingReferences.js`'s `describeDrawingPick`): its layer, an insert's
    block, and what it measures in the drawing's unit (Measure's formatter, `formatMeasurement`, "units"
    where the file declares none) — a line's or a straight polyline's length, a circle's diameter, else
    its box's size;
  - a robot's link (`robot/LinkDetails.jsx`'s `robotLinkItem`): its mass, and its joint to its parent —
    name, type, and the parent link, a press selecting it ("Root link" for the root); a named mesh object
    its link and size;
  - a GLB's node, a 3MF's object and an STL's body (their scenes' `describePart`): a node's index, triangles, size in
    the file's metres and authored material; an object's build item and triangles; a body's number ("2 of 5") and
    triangles.
- **A hover tip** — the frame's, every view's that picks (`ViewFrame.jsx`, `kit/shell/HoverTip.jsx`'s
  `useFrameHoverTip`): under Select, the name of what a press would pick there (the view's `hovered`) and
  its short kind — a pad's or a pin's net, a part's value (`U12.57 · /TVRAM12`); a drawing entity's
  headline measure in the drawing's unit (`Line on CUT · 25.00 mm`, `Ø 12.00 mm`); a link's parent
  joint's type; a part's or subassembly's owner; a face's part, kind and number — in a small tip beside
  where the pointer came onto it, once the pointer has rested on it a moment (450ms), gone the moment it
  leaves, a button is held (a drag, a pan) or Select is put down; it takes no pointer. It runs as the
  pointer moves, so it is **cheap by rule**: each view gives it a short path of its own (`inspect.js`'s
  `tip`), names from what is in hand, measuring and listing nothing (a 3D scene's `nameOf`, `xbfTipper`,
  `useRobotTip`, `drawingPickTip`, `boardPickTip`, `schematicPickTip`); the full description runs only
  for the pane and a card. No view draws a tip of its own (`check-kit-boundaries.mjs`' frame guard).
- **The Layers** (`board/LayersSection.jsx`), a list as Altium's Layers panel is: the layers, grouped
  Front, Inner, Back, Other, each its colour, name, count and eye, a press on a board layer's row
  making it the active layer (a filled dot after its name), drawn on top; last in Other, **3D models**
  (a box glyph, how many parts stand on a model, and an eye: the parts' models in the 3D view, a
  seldom-used control, so here, in both modes, inert in 2D, kept with the file's view). Which preset draws
  the board is the strip's Display (below); under the layers, the rest of how it is drawn, its layer
  display. The board's **Parts** end, once its models table is in, with a shut block **No 3D model**:
  every part the 3D view stands no model on, each row saying why, a block as any other (Select all
  parts, Isolate) — the list of what is missing, reachable in 2D and 3D alike.
- **A drawing's Layers** (`dxf/LayersSection.jsx`): each layer drawn on, in the drawing's order, its
  pen, name, entity count and eye (hidden: not drawn, picked or snapped to), and under a layer the
  block references placed on it, open, a press on one picking it as a tap on the drawing does
  (Shift adds). Its rows are the Model tree's, one glyph slot each: a layer's slot holds its pen, its
  colour in place of a kind icon, and a layer with blocks under it holds its chevron there, as every
  branch does, its pen then a mark after its name, before its count; its name 32px in, as every list's.
  A block reference's row is a level under its layer's, hung from its line: its slot its block's glyph,
  its name, then as its detail its handle as the entity's id it is, `#9C` (the
  payload carries no insertion point to show instead), its tooltip **Handle 9C**; Copy Reference names
  it by that handle (`drawing.dxf#h9C`), and the search finds it by it. Searching, the layers whose names match,
  and the blocks whose names do under their layer, open, whatever the person had folded: the search
  decides which rows are candidates, and among them a layer's chevron works as it does unsearched. A
  collapse hides the hits under that layer (every block reference of a layer kept by its own name, the
  matching ones of a layer kept by a block), never the layer's row, and an expand shows them again. Those
  folds are the search's own, as its hits are: they hold while it is up, however the query is edited (a
  layer folded stays folded as long as the search keeps it), and clearing the search drops them, so the
  layers come back folded and open exactly as the person left them before searching.
- **A board's view controls** are View's (`board/BoardDisplay.jsx`'s `boardViewGroups`), the navbar's on a desktop
  and a phone, or the strip's end with no navbar: **Side ▸** (Top, Bottom; ⇧F, KiCad's View ▸ Flip Board View: the
  board as two stacked layers, Lucide's `layers-2`, the side it is seen from solid, `board/boardSideIcons.jsx`; from the
  bottom the board is mirrored, its back layers on top), **Mode ▸** (2D, 3D; 3, below, [A board in
  3D](#a-board-in-3d): its glyphs the words, as KiCad, EasyEDA and the maps apps label their 3D switch,
  `kit/shell/TextGlyph.jsx`, a word drawn as an icon on Lucide's grid), **Display ▸** (its presets as one radio group —
  Board, Copper, Assembly, Placement — the one on screen ticked, and Custom, ticked and not a choice, while the Layers
  tab's eyes have left the preset's set), in 3D **Projection ▸**, then **Background ▸**, and in 3D, after a separator,
  **Reset view** (what the board's 3D Home was: the camera back where 3D opened, eased; `view_home`). With no navbar a
  phone has them as rows of its More (`boardViewControls`: View from bottom and 3D view, ticked while they are on,
  then Display, its row opening the presets under it, in 3D then Projection, then in 3D Reset view). The rest of how a
  board is drawn is changed now and then, so it is the Layers tab's, as KiCad's Appearance panel has it,
  in the settings form's rows: under the layers, **Layer display**: **Others** (KiCad's high-contrast
  modes, a Select: every layer but the active one **Shown**, **Dimmed** or **Hidden**; the outline, and
  with a copper layer active every drill and via through it, stay at full strength; **Ctrl+H** (⌘H)
  cycles them while the board has the keyboard), **Pours** (a checkbox, while copper is drawn), and
  the **Zones**' (60%) and **Tracks**' (100%) opacities, each the [slider control](#the-slider-control). On a phone the side, the mode and the presets are the View menu's submenus too. All of it is the board's Display (`plot2d/boardDisplay.js`), which `cad kicad_pcb
  snapshot --display` draws too. A schematic has none: its colours are the theme's.

- **The Hierarchy** (`schematic/SheetsSection.jsx`), KiCad's Hierarchy Navigator: the root (by its
  file's name) and the sheets each places, in page order, each row the Model tree's — a branch's
  chevron or a sheet's glyph, its name, its page number as its detail, its file in its tooltip — every
  sheet open, the sheet shown lit; a press on a row shows that sheet, the way back up from one entered.
- **Search is the panel's.** What is typed filters every searchable tab at once; the open tab shows its hits, the match
  lit (`TreeFilterHighlight`) — the layers or sheets whose names match, the Parts' and the Nets' ranked hits (the
  arrows and Enter walk and pick the open tab's, else the first list's) — and one line where it finds nothing there.
  Escape or the box's X closes it, each tree folded and open as the person left it: a search opens or shuts no tree's
  own rows. Most tabs list their hits flat, with
  no chevron (the Model's, the Links', the Parts', the Nets', a board's layers, the Hierarchy); a
  drawing's Layers keep each hit under its layer, whose chevron folds them for the search alone (above).
- **Collapsed, it goes whole**: its toggle is the navbar's (**Hide panel** / **Show panel**, the sidebar's own icon, the
  navbar's first control, before the logo: [The panel](#the-panel)), and nothing of it stays over the model. No rail, no
  reveal on a hover of the view's edge, and a pick on the picture never opens it; a mouse resting on its toggle peeks it,
  over the view and pushing nothing, until the pointer has left both ([The panel](#the-panel)).
  ⌘\ (Ctrl+\) shows and hides it, and / opens it on its search with the keyboard in the box, while the view has
  the keyboard. Docked, open or collapsed is the person's, and so is its width (232px at first; from a grip on its
  right edge, Left/Right by 16px, from 200px to what leaves the model 640px, and, before the view is measured, no
  wider than it is). **All of the panel's state is
  the file's**, as its camera and its layers are: open or collapsed, the width and the tab are kept in
  the file's view (`panel`, `file-viewer/filePanel.js`), written by the panel's
  own state (`useFlatPanelState`) for every view that has a panel, 2D and 3D alike, and merged into the
  file's record by the file viewer whatever the renderer writes. A reload brings each file's back;
  another file starts at its own, or at the defaults.
- **Open (pinned), it is always docked**: the canvas is the narrower for it, at any width; it never covers
  the picture (a peek alone does, and never resizes it). Showing or hiding it is a resize of the canvas, as a 3D viewport's: a view still at
  its fit refits to the room it has now, and a view the person has moved keeps its zoom against
  the fit and the point of the picture at its centre at the centre of the room left
  (`kit/viewport/useFlatCanvasView.js`, a drawing's `dxf/useDrawingView.js`). A flat view is kept with
  the pane it was framed in (`kit/viewport/flatView.js`), so a file reopened with its panel open (the
  canvas the whole view until the panel docks) comes back exactly as it was left. Zoom to fit and 100%
  measure the room beside the panel. A file whose panel the person has not opened or closed has it open, and collapsed
  (by the width, not kept) where open it would leave the model under 640px; once they have chosen, the choice is the file's at any width, and a
  panel opened always pushes ([The panel](#the-panel)). **On a phone** (under 600px) the panel is a sheet from the
  left, in every renderer ([A phone's sidebar](#a-phones-sidebar)): `FlatPanel`'s phone page (`mode: "page"`, the
  desktop's head, tabs, search and rows) inside shadcn's Sheet; ⌘\\ opens and shuts it
  too, and / does nothing there.

**The tool stack** (`ToolStack`) is the column under the strip and the sub-toolbar, centred
with them, for a renderer's own `toolPanels`. STEP and the robot renderer hand none: their
tools' controls are sub-toolbars and what there is to read of their files is the panel's.
Its panels follow these rules:

- **Two kinds of panel.** A `resizable` panel is the person's to size, on its own; every
  other panel is *fixed*: one width, its content's height, and no grip.
- **One width.** Every panel opens at `TOOL_PANEL_WIDTH`: 164px, a strip of six tools (six
  24px buttons, 2px gaps, 4px padding and a 1px border). A fixed panel is exactly that wide; a
  resizable one is only ever made wider, up to half the viewer. The panels hang left-aligned
  in the column, each at its own width. Content truncates to fit; it never widens a panel.
- **Heights.** A panel is exactly its content's height — never padded to a minimum. A
  resizable panel has a *cap* the content grows up to and then scrolls inside: it opens capped
  at the stack's own height (`toolPanelDefaultHeight`). A cap is never a floor.
- **One grip, on a resizable panel only**: its bottom-right corner, moving
  its width and cap at once, a separator in the tab order named after its panel (Left/Right
  nudge the width and Up/Down the cap by 16px, Home and End take both to their bounds). A folded panel has no grip: there is no height to set.
- **Never past the viewer.** The column stops 8px above the cube's line
  (`VIEWPORT_STACK_BOTTOM`, `calc(68px + 16px)`). When the panels need more, a `"tree"` panel
  gives way first, down to 128px or its content, then the `"details"` panels together, each in
  proportion to its height, down to 96px or its content; a `"fixed"` panel keeps its height.
  If what cannot give way still does not fit, the column itself scrolls — a panel is never cut.
- **Headings.** A stack panel's heading row (a section of the view's panel has none: its tab names
  it) reads as the settings form's section headings do (12px, regular, `TOOL_PANEL_HEADING_TEXT_CLASS`,
  `FileSheet.js`'s `FILE_SHEET_SECTION_HEADING_CLASSES`), 28px tall, 8px in: a title, a summary where there is one,
  then at its right end its own actions, the chevron where it folds (up while open, down while
  folded) and an X where it has something to remove. Every small button in a heading is 20px,
  2px apart and 4px from the edge.

- **Surfaces.** Four, defined once (`lib/floatingSurface.js`), each the popover's colour (a step
  off the app's background, lighter in the dark theme) with one border, nearly opaque, so chrome
  reads over any canvas — a flat view's, which is the app's own background, and a 3D scene's alike:
  the tool strip, its sub-toolbars, the stack's panels and a collapsed panel's pill share
  `FLOATING_CHROME_SURFACE_CLASS` (a flat view's zoom has a faint surface of its own, [The view's
  corner](#ownership-and-layout)) (90%, a small blur, a medium shadow); Preview's settings panel,
  mostly text, `SETTINGS_PANEL_SURFACE_CLASS` (92%); every menu and popover over the viewport, the app
  menu and Display included, `FLOATING_SURFACE_CLASS` (95%, blurred).
- **Scrolling.** Every scroll region in the viewer's chrome — the view's panel, a panel's
  body, the stack's column, the explorer, a menu, the alert card — is the
  `ScrollArea` primitive (`primitives/scroll-area.jsx`, shadcn's): thin overlay
  bars in the theme's colours, shown while the pointer is over the region. No
  native `overflow-auto` scroller in chrome; `src/designSystem.test.js` holds it.
  The home (the model library) is a page, not chrome: it scrolls as a page does,
  with the platform's scrollbar, and only when there is more of it than fits.
- **Nothing opens elsewhere.** A pick shows as Quick Edit's chips; the panel is there
  under every tool. No pick or tool opens or closes the explorer, on desktop or mobile.

**The one row.** Every list of the view's panel — the Parts, the Nets, the Hierarchy, a
board's and a drawing's Layers, the Model (an engine document's, a GLB's, a 3MF's, an STL's), the Links, a
model's parameters' headings, every search hit — is built of the STEP/xbf Model tree's base components
(`primitives/tree-row.jsx`, `primitives/tree-filter.jsx`), never a view's own: ONE row,
`TreeRowSurface`, which alone sets its horizontal geometry, so a fix to it lands in every list; its
slot (`TreeRowGlyph`, `TreeRowToggle`), its name and detail (`TreeRowName`, `TreeRowDetail`), its actions
(`TreeRowActions`); a heading over a run of rows (`TreeRowHeading`); a long list mounted as it scrolls
(`VirtualRows`); a search's lit match (`TreeFilterHighlight`, `TreeFilterMatch` for a plain substring
search) and its count (`TreeSearchStatus`). No view sets a text size of its own (`text-tiny`,
`text-ui`): every row, detail, count and heading is the panel's 12px (`tree-row.test.tsx` holds it). In the panel's numbers (232px wide, its body padded by the inset, 16px):

- **The box**: 28px (36px on a phone), the background 8px from each edge, its radius and its hover,
  selected and cursor fills; the panel's 12px text (`dense`), the name at full strength.
- **The slot**: ONE glyph a row, its first child, always (`TreeRowGlyph`, `TreeRowToggle`): 12px wide (a
  phone's 16px glyphs widen it), its glyph centred and muted, its left edge on the search icon's, 16px in,
  and 10px further a level (the row's padding: `--tree-row-pad` plus 10px a level, from its `depth`). It
  holds a branch's chevron, the button that opens or shuts it (`TreeRowToggle`: a block's, whose name is
  that button, the pointer's alone; a locked one a mark at half strength) — and nothing else: a group or
  an assembly row shows its chevron alone, no kind icon beside it — or a leaf's own glyph: its kind's
  light icon (an engine document's part lucide's `Box`; a board's part, pad or net; a schematic's sheet;
  a robot's mesh object `Box`, its root the anchor), or a marker in its place, a layer's colour; or
  nothing: a leaf keeps its slot, so the names of a level all start on one column whatever their slots
  hold. Never two glyphs: a row that needs a marker as well as its chevron (a drawing's layer with
  blocks under it) shows the marker after its name, as a board's active layer shows its dot.
- **The name**: 4px after the slot, at full strength, the label first to truncate (`TreeRowName`), its
  detail — a count, a page, an owner's path — muted 4px after it in the row's own text (`TreeRowDetail`,
  every count's one style), ending 8px before the row's end (`TREE_ROW_NAME_CLASS`). A top-level row's
  name stands 32px in, in every list.
- **The headings** (`TreeRowHeading`): a 28px muted line in the panel's text, its words on the slot's
  line, 16px in — a board's Front, Back and Other over their layers, a model's parameters' file over its
  parameters, a tab's name over its search hits.
- **The guides**: a faint line under each owner's slot, drawn by the row from its `depth`, its full height, so the rows under an open branch draw its line unbroken.
- **The actions** (`TreeRowActions`), shown on hover and kept while one is on, float over the row's
  right end: each a 16x20 button with a 12px glyph, 2px apart, the last one's glyph ending 16px from
  the panel's right edge (`--tree-row-actions-pad`, 6px, and its button's 2px; a phone's 16px glyphs
  fill their buttons, so its pad is 8px): 8px inside the background, as the slot is at the left. The row's `actions`
  says how many, so its name, which runs the row's full width, fades out half a rem before them (a
  mask, `ROW_NAME_UNDER_ACTIONS`): nothing is drawn behind the buttons and the row keeps its own
  colour. An assembly row's are **Isolate** then the **Hide/Reveal** eye (a part file has no
  Isolate); while the row is isolated its Isolate is the way out, an X (**Exit isolate**), shown the
  whole time, and its eye is off; a part's or a net's, and a layer's, the eye alone. A Links row that draws something — a
  link with visuals, or one visual — has the eye alone, in its search hit too: a link's hides its
  own visuals, never its child links, and on a partly hidden link hides the rest.

A list pads nothing: no `pl-`, `px-` or padding on a row, no inset constant, no chevron of its own
(`src/designSystem.test.js` holds it). The explorer's rows are the same primitive with its own
numbers (the defaults: 5px in, 3px at the right), in 12px text, and pad themselves.
Model and link finds and the explorer's filter share `TreeFilterInput`; the explorer's rows are compact
24px lines, as the trees' are, but in 12px text.

**Mobile** is below 600px of FileViewer width (Material's compact window class) — the one viewer breakpoint
(`useViewerMobile`); chrome never uses window breakpoints, nor the pointer's kind: a small window
is worked as a phone is. What a finger reaches is the gesture's own (`pointerType`): a touch takes an
edge from 20px off (an edge within 16px wins over the face under it), ink, a measurement and the
eraser's ring from 16px (`TOUCH_HIT_PX`), and a joint's knob from 22px; a mouse keeps its few px.
On a phone every slider is a 36px band with a 20px thumb, and the selected ink's bar has 36px
buttons. A pinch zooms at the touch speed from the first gesture after a load. A phone is read at arm's length
and worked with a finger, so its chrome is one step up the scale, after the platforms' own
guidance (Apple's 44pt and Material's 48dp touch targets, an 11pt type floor and 15-17pt body
text, and iOS Safari zooming into any field under 16px): type 12, 13 and 14px for `text-tiny`, `text-xs` and
`text-ui`, the heading 16px, on the desktop's line heights ([the type scale](#the-type-scale)); text entry at the panel's own size (the page's viewport,
not a 16px font, stops a phone zooming in on a field); menu, select and tree rows 36-40px; the
navbar, and Preview's bar in its place, a 48px row of 36px controls; the strip and the sub-toolbars 36px tiles (the strip one row,
**More tools** holding what does not fit; the drawing tools' row the same single row, wrapping where it must — Shapes' does
at 375px, its style group under its tools, and a row that wrapped draws no rule between its groups, the line
break parting them, `SubToolbar`'s `data-wrapped`).
The scale is set once, in `globals.css`, for the whole page while a phone's view is on it, so a
portalled menu, select or hint is the same size as the chrome it opened from. A phone has no room beside
the app menu or the strip's More for a submenu (one placed beside More, which a board's rows make wide,
ran off the screen's edge): there a submenu opens in place, its row showing the choices under it, in the
menu itself and indented, the chevron turning down while they show; a press on the row, or Left, hides
them again, and each opening of the menu starts them hidden (`primitives/dropdown-menu.jsx`'s
`DropdownMenuInlineSub`: the app menu's Language, More's Display and Zoom, a picking tool's chevron menu's Filter row). There is no view
cube and no view's panel; and
Quick Edit is the same bar across the view's bottom, above the safe area (see
[Quick Edit](#quick-edit)). The explorer is the same popover, never wider than the window less
1rem. The shortcut hint is hidden.
Touch works for every tool: one finger orbits, two pan and
zoom, a tap picks; a pinch, a cancelled pointer or a camera drag is never a
pick.

### A board in 3D

**2D/3D** shows the same view of a board in 3D (`board/Board3dView.jsx`, a lazy chunk): the board as a
slab cut to its outline, its two faces the 2D drawer's own pictures of the two sides, in the Layers
tab's Display and the view's theme, on the 2D canvas's colour; what the 2D view draws past the outline (a
dimension, a fab note, ink) is drawn as it falls, on a see-through plane round the slab at each face's
height, so nothing the 2D view shows is lost. It is the view's other canvas in the same
frame (`ViewFrame.jsx`, through the flat views' `FlatViewFrame.jsx`), never another view: the strip, the panel and its tabs, Quick Edit, the
selection, the ink, the measurements and the corner are the same mounted components, with the same
names, in both: View and the zoom stand where they stood, and the zoom zooms the 3D camera. There is no cube (a board
turns over by Side ▸) and no Home on the picture: Projection is the View menu's, and so is Reset view, the way back to
where 3D opened. The key **3** switches,
as KiCad's Alt+3 opens its 3D view.

A board whose file names its stack-up's colours (`(stackup ... (color "Black") ... (copper_finish "ENIG"))`)
is shown in 3D as it is made, in Board mode: each face its substrate, its copper in the finish, its solder
mask laid over with the pads' openings cut, its silkscreen, its edge the substrate's colour, in KiCad's
3D viewer's colours for those names (`@cad/core/lib/plot2d/stackup.js`), the same in either theme. The
Layers tab's rows still choose among what a made board has (the facing copper, mask and silkscreen, the
drills and vias): unticking the mask shows the bare copper. Copper, Assembly and Placement, and a layer in
focus with the others dimmed or hidden, are views for working on layers, so 3D draws them in the layers'
colours, as 2D does. 2D keeps the layers' colours always, as KiCad's PCB editor does (its 2D canvas is
for telling layers apart and editing them; a black mask and gold copper would hide which copper is
which), and so does every snapshot. A board that saved no stack-up colours looks as it always did.

| Control | In 3D |
| --- | --- |
| Select: a click, Shift, a click on nothing | the same pick where the pointer's ray meets the face it enters, from that side, with the same filter and the layers that side draws |
| Select: a drag | turns the view, as in every 3D view; naming an area is the 2D view's, and an area named stays selected and drawn |
| Draw | the same ink, laid on the face the camera sees; ink drawn in either mode shows in the other; over the board, in 2D and 3D alike, each opaque mark is edged with a thin keyline in the canvas's contrast (dark on the dark canvas, white on the light: `boardOverlay.js`'s `inkKeyline`), so neon red reads on red copper |
| Measure | the same snaps and measurements, on the board's plane, drawn through the camera |
| Hover tip, the context menu, double-click | the same; the menu's groups are every view's; a double-click on nothing fits, under Select as in every view |
| Display, the Layers tab | the same Display: both faces redraw; the Layers' 3D models eye shows or hides the parts' bodies |
| The parts | each footprint's 3D model (a STEP from the board's folder, KiCad's installed 3D library or `CAD_KICAD_3DMODELS`; a `.wrl` name read as the `.step` beside it) in its authored colours under the stage's lights; a missing one a see-through block a millimetre tall on its outline, in the theme's muted ink. A press on a body picks its part (with Footprints ticked), in front of the face; a picked or hovered part's body takes the highlight; isolating fades the bodies that are not it |
| Flip (⇧F) | a camera move, as KiCad's 3D viewer's F and Altium's Bottom Side are: it turns the camera over the board's left-to-right axis, which way is up kept, so the back is seen as the 2D view's back, mirrored left to right; eased as every camera move is, round its target (`kit/camera/runtimeCamera.js`), never through the board: from straight above or below the board turns over about its own top-to-bottom axis, the one the 2D view mirrors across, its eye passing the side it leans to (the screen's right where it leans to neither), and near there the same way. Its icon is the side the camera is on, so it changes as the camera passes the board's plane, turned by Flip or by hand, and a file reopened in 3D shows its camera's side |
| The zoom | the same "100%" dropdown, zooming the 3D camera: the 3D views' percentage (100% the board framed whole at the camera's angle, as 3D opens), its menu and the zoom's keys (F, + and −, ⇧1, ⇧2, ⇧0) |
| Projection | the View menu's **Projection ▸** (a phone with no navbar, Display's list's, after a rule under the presets): Orthographic or Perspective, orthographic by default, kept per file with its 3D camera (its view's `board3d`) |
| Reset view | the View menu's last row in 3D: the camera back where 3D opened, eased, from the side it is on (what its Home was; `view_home`) |
| A panel shown or hidden | the canvas takes what the panel leaves, the camera centred in it; the strip stays at the view's centre |

Entering 3D opens head on, on the window the 2D view shows, from the side it shows (in perspective too,
the eye where the face is drawn at the 2D scale), and eases, on that same side, to the 3D views' opening
tilt, the board framed whole — from the bottom, that view turned over the board as Flip turns it (behind,
right and below, the world's up still up) — or to the camera the file was left at in 3D, turned over to
that side if it looks at the other: the ease never crosses the board's plane, so Flip shows the side the
2D view showed throughout. The 2D picture stays on screen until the 3D
view has drawn that same picture, so the switch shows no frame of anything else. Leaving gives the 2D
view back its own window, as it was left — or fitted, when a file reopened in 3D was never moved in 2D —
whatever the camera did in 3D: each mode keeps its own last view, as KiCad's 3D viewer, a window of its
own, never moves the PCB editor's. Framing the 2D view on the 3D camera's window brought an orbit's zoom
and centre into the plan, off the board. Only the side carries over, as it does entering: the 2D view
comes back from the side Flip showed, its window kept as a Flip in 2D keeps it. The 3D view stays until
the 2D canvas has painted its window. Which is up, the 3D camera and its projection are the file's view (`board3d`).
The library card's picture is the flat board in either mode. On a phone, 2D/3D is the View menu's **Mode ▸**, and in 3D
Projection follows the presets.

## The View menu and a phone's sheets

One description of the view's settings (`kit/shell/ViewSettingsMenu.jsx`: groups, each `{ id, label, value, options,
onChange }` or a switch), drawn by ONE component, the same dropdown on a desktop and a phone, for every kind of file:
a group's `onChange` is what counts it (`display_<mode>`, `projection_<value>`, `display_grid`,
`viewport_background_<choice>`, `board_side`, `board_dimension`, and Reset view's `view_home`: the names the buttons
it replaced sent). Each file type's rows, top to bottom:

| File | Rows |
| --- | --- |
| A 3D view (a model, STEP, mesh, robot) | Projection ▸ (Perspective, Orthographic), Display ▸ (its modes), Background ▸, Show grid, Reset view |
| A board | Side ▸ (Top, Bottom), Mode ▸ (2D, 3D), Display ▸ (its presets), in 3D Projection ▸, Background ▸, in 3D Reset view |
| A drawing (DXF) or a schematic | Background ▸ |

On a phone **Reset view** ends each: a 3D view's and a board's in 3D as on a desktop, a flat view's fit.

### The View menu

The view's settings are ONE button, **View**, at the navbar's right end for every kind of file, left of Preview where
the file has one, on a desktop and a phone alike (with no navbar, a tile at the strip's end, before Preview): the
navbar's 28px button, icon only, no chevron, a cube — a 3D view's, and a board's in 3D, the projection on screen's (the
Perspective or Orthographic cube its options wear: projection is the setting changed most, the owner's call), a flat
view's the plain cube (Orthographic's) — its name and tooltip "View" (no tooltip on a phone). Its menu is a stock
shadcn DropdownMenu under it, its end on the button's (on a phone, on the screen's right edge, 8px in, so its submenus
have the room at its left), at least 13rem wide, in the menus' type (`text-xs`, 16px lines; a phone's one step up, as
every menu's). **A choice is a submenu** (`DropdownMenuSub`): its row the group's name at the left and, at the right,
the choice's name muted and the chevron — **no icon on the menu's own rows** (the owner found them clunky; the value
says the choice) (`data-view-sub`, `data-view-sub-value`); its submenu (`DropdownMenuSubContent`,
`data-view-sub-content`) the options, each with its icon (a row with none keeps an icon's room), the one on screen
ticked at the right, a key shown on the choice it would make (a board's ⇧F on the other side, 3 on the other mode). A
submenu opens beside its row on the side with room (Radix flips it: the left, as View stands at the screen's right),
on hover or a press, so a tap opens it on a phone; on a phone it overlaps its parent's left edge by 16px so it stays on
the 375px screen, never past its edge (its width capped at the room there). **Show grid** is a check row of the menu
itself (`DropdownMenuCheckboxItem`: its name, the tick at the right while on), after a separator, and leaves the menu
open. **Reset view** (`data-view-reset`) is the last row, after a separator, its name alone: the view the file opened
with, framed whole from the opening direction, eased — what the cube's and a board's 3D Home did, its telemetry still
`view_home`. "Reset view" is the name because it resets the orientation as well as the framing, and it was already
this product's name for it (the phone's row, in every locale); **Zoom to fit** (F, the context menu, the zoom's menu)
keeps the orientation and frames what is shown, and stays a command of its own. A choice closes the menu. The button
says each group's value to a host or a test (`data-view-<group>`, `data-display-mode`). Projection, Side and 2D/3D are
not buttons of their own: changed now and then, they are submenus of the one menu. There is no bottom sheet.

### A phone's sidebar

On a phone the navbar's panel toggle (its first control) opens the view's panel as a standard mobile sidebar: shadcn's
**Sheet** from the left, 85% of the screen wide and 20rem at most, over the model with the Sheet's scrim, starting
closed each time (kept nowhere). In it **the desktop's panel, the same components at the same sizes, gaps and type**:
its head (the tabs, ⋯, the search's icon; no Back), its search, its tree rows (`primitives/tree-row.jsx`: the same 4px
gap, 12px glyph slot, 16x20 actions 2px apart, 6px from the right; the row's own touch height, 36px, the one thing a
phone changes in it) and every tab's content (`FlatPanel`'s `mode: "page"`). Only what a phone cannot do differs: a
row's actions are always shown, as nothing hovers (`globals.css`'s `[data-panel-surface="page"]`). A tap outside it, a
swipe back to the left (the sheet's `onSwipeClose`: 48px towards its edge, more across than along it), Escape or the
toggle again close it; ⌘\ too. Nothing hovers, so a phone has no peek.

## Display settings and section primitives

Display is not a tool. It is a submenu of the View menu, on a desktop and a phone ([The View
menu](#the-view-menu-and-a-phones-sheets)): its options the file's modes, each with its icon (a board's presets), the
one on screen ticked; choosing one closes the menu. Show grid is a row of the View menu itself, and the viewport's
**Background** (**Light** and **Dark**, each with its icon — the sun, the moon; telemetry
`viewport_background_<choice>`) its own submenu. Where the host has no navbar, a phone's strip **More** has a Display
row that opens one list (`DisplayPopover.jsx`'s `DisplayMenuItems`) under it, in More itself: the modes, a separator,
**Show grid** (which leaves the list open), (a board in 3D) the camera's **Projection**, then, after a separator, the
Background. Checks sit at the row's right end. Clicking outside or pressing Escape closes it. Opening it leaves the
active tool and its controls in place. A DXF view's View menu is Background alone, and it has no Preview. A native
KiCad board's view settings are rows of View — Side ▸, Mode ▸ (2D/3D), Display ▸ (its presets), in 3D Projection ▸,
Background ▸ and Reset view ([The View menu](#the-view-menu-and-a-phones-sheets)) — and its Layers tab's layer display
(see [A flat view's panel](#the-views-panel-and-the-tool-stack)); it has no Preview.
It is drawn in the viewport's theme as every view is (the person's Background, [below](#the-viewports-theme-background)):
its canvas (the light or the dark one) and a palette for it (`plot2d/theme.js`: KiCad's default colours
on the dark one, the same hues darkened to 3:1 on white on the light one), its highlight, hover and
net dim with it (`board2d/boardOverlay.js`), and its layer swatches; a switch of Background draws it
again in the browser, from the payload it holds. A net in focus (selected, or lit by a reference)
steps the rest of the board back lightly, more than half its contrast kept, so the board still reads
as a board round the lit net; what is isolated steps it back further. The lit net's copper (its tracks,
pads, vias and pour outlines) is edged, 1.5 px round each piece in a dark tone of the highlight under it
(KiCad lights a net by brightening it over the rest dimmed; the edge adds what a light wash takes away): the net then stands out by its edge at 3:1 or more against
the washed board in light (7.6:1 measured on a routed board, where its fill alone reads 2.8:1), and the
edge parts the light net from the copper round it in dark. In 3D the step back is laid on the board alone,
never on the see-through plane round the slab, and the edge is drawn on the face as in 2D.

A 3D view's Display is a choice of mode and the Grid switch, and nothing else: a mode has no settings
of its own, and there is no settings page. The modes, in order, are **Solid** (shaded with
the model's CAD edges, the default), **Shaded** (no edges), **Parts** (Solid with each part
its own colour), **X-ray**, **Hidden line** and **Wireframe**, filtered by the view's
injected capabilities (`viewFeaturesForKind`, `@cad/core/common/viewSettings.js`; the
rows and icons `DisplayModeOptions.js`): a STEP assembly
offers all six, a STEP part file all but Parts, and a file without CAD edges (STL, 3MF, GLB,
a robot) Solid, with Parts when it has several parts, objects or links. **Show grid** draws the
measuring grid in every mode, off by default. Each row has its icon, the sphere drawn as the
mode draws a model (and a tile of floor grid for Grid). Render is no display mode: Preview
draws the model in Render whatever the file's mode, with its own settings (see
[Preview](#camera-animation-and-preview)). Per-file storage keeps the mode and the grid;
old-shaped stored display settings are dropped setting by setting, never migrated.
Projection is a menu of its own, orthographic by default, kept per file with its Display (`display.camera`);
Preview's Render resolves to perspective while preserving the file's choice.

Preview's settings panel (`PreviewSettings.jsx`, its body `PreviewRenderSettings.jsx`) is
the one settings form: Orbit, then Render's Part colours, Lighting, Background and Floor.
It shows all groups under static section headings and dividers, with no collapsible
sections or cascading settings menus. A heading is 24px of regular `text-xs` in the
foreground colour, a rule above every one but the first. A feature that switches on and off
(Orbit, Floor) is the checkbox at its heading's right end, the title naming it; there is no
separate row for it. While the feature is off its section is that heading alone. Every
setting is one 24px row: its label in a 4rem muted column, its control filling the rest, so
a form's controls start on one line. A label is short under its heading ("Colour",
"Opacity" under Floor); the control's accessible name stays whole ("Floor opacity"). A
dropdown or colour is as wide as its value, at the row's right end. A continuous value is the
[slider control](#the-slider-control), its two lines in place of the row. By part's palette is a
row of swatches, then add and remove. Choices use Select controls. Colours
retain swatches and a custom colour picker. Floor is on by default, at the model's lowest
point (its Placement, **Lowest point**; **Model origin** stands it at Z=0). A long form scrolls within the available viewer height. A nested Select or colour
picker owns Escape and outside interaction before its parent surface. The last item is
**Reset to default**, disabled at Preview's defaults; it removes only Preview's overrides,
never the display.

Preview's settings use shared settings field primitives under their static headings; other inspector
sections retain their own disclosure rules. Hover, focus and rendering never write
settings. Light and dark are the app menu's Theme.

Text is drawn as Figma draws its interface, greyscale-antialiased (`-webkit-font-smoothing: antialiased`,
`-moz-osx-font-smoothing: grayscale`, `globals.css`), on the whole page while a viewer is on it, portalled
menus included: macOS's subpixel default draws light text on the dark theme a weight heavier. It changes no
family, size or weight. Type comes from [the type scale](#the-type-scale) only; no pixel font sizes. Sections use
8px gutters and bottom insets and 4px row and column gaps. `FileSheetFieldGrid` owns horizontal spacing; its
children never pad again. Menu, select and context-menu typography comes from the primitives, portals included.
Selected values show their icon where it means something.

Use the slider control for a useful bounded range, `FileSheetNumberProperty` for other scalars,
`FileSheetColorProperty` for color with opacity, and ordinary Select controls for choices. Drafts
stay local until Enter or blur; Escape cancels. Clamp at the owner's write boundary, which sliders
and number inputs share. Omit a visible label only where the value or icon is unambiguous, and
always keep the accessible name.

### The type scale

Three interface sizes and one heading, each on a fixed line height, as Figma's UI type is: the tokens
`text-tiny`, `text-xs`, `text-ui` and `text-heading` (`styles/tokens.css`, their values `globals.css`'s
`--cad-text-*` and `--cad-leading-*`). Nothing else sets a size (`src/designSystem.test.js`; a page computes them in
`RendererShell.browser.test.mjs`).

| Role | Size / line height / weight | Token |
| --- | --- | --- |
| Tooltips, shortcut hints (a menu's, a tooltip's key), small metadata (a tile's age, the app menu's version, a value badge, the zoom's percentage, a status under the view) | 11 / 16, regular | `text-tiny` |
| The view's panel (every step of the scale inside it: `--cad-text-panel`, [One surface, one text size](#the-views-panel-and-the-tool-stack)), Quick Edit, the sub-toolbars and their popovers, Preview's settings, the tool stack's panels, and every menu, dropdown, select, context menu and toast | 12 / 16, regular (a menu's label too) | `text-xs` |
| App chrome: the navbar and the file's name, dialogs (What's new), the Home's body | 13 / 20, regular | `text-ui` (`text-sm`, `text-base`) |
| The one heading: the CAD app's notice title (the Home's **Recent** is the navbar's, 13/20 at 500) | 15 / 20, semibold | `text-heading` |

A phone takes one step up on the same line heights: 12, 13 and 14px, the heading 16px
([mobile](#the-views-panel-and-the-tool-stack)). There is no 10px step. A menu item is 16px of line in 6px of
padding (`dropdown-menu.jsx`, `select.jsx`, `context-menu.jsx` and `tooltip.jsx` set `leading-4`), and no menu brings
a size of its own (the viewport's context menu, the zoom's and the view menus take the primitives').

Text drawn into the viewport is the picture's, not the chrome's, and keeps its own sizes, none under 10px: the
view cube's axis letters 10px (`ViewPlaneControl.js`) and its faces' names 10px on a face seen square-on (half the
face's half-size), foreshortened with the face as it turns; a measurement's label and the snap chip 10px semibold on
a 14px line (`@cad/core/lib/viewer/measureDimension.js`); a drawn text mark 16, 20 or 28px by the stroke width in
hand (`annotate/AnnotationOverlay.jsx`).

### The viewport's theme: Background

The model area is its own surface, not the app's chrome, as a CAD program's is: **Background** (Display's, the
person's, the tab's settings' `viewportBackground`, the same in every file and view and in the CAD app) is **Light**
(the default: a soft grey gradient down the view, `#f4f5f6` to `#dfe2e5`, never white), **Dark** (the dark canvas,
`#1e1e1e`), and nothing else: there is no "follow the app's theme" (a stored `theme`, the old Follow theme, reads as
Light, `normalizeViewportBackground`). `@cad/core/lib/viewportTheme.js`
writes the looks out once with the scene's own colours; `kit/look/useViewportTheme.js` resolves it for a view.
**Everything drawn in the model area follows it, never the app's theme**: the scene (its background, lighting and
environment, edges and outlines, the grid and its axes), the cube, the labels, chips and hover tip over the picture
(the canvas box is a `.light` or `.dark` token scope, `ViewFrame.jsx`), the loading cover, the corner's bare buttons
and their halo, a 2D view's paper and strokes (a drawing's, a board's, a schematic's), and Preview's studio, which
takes the viewport's light or dark but keeps its own backdrop colour: Preview is a photographic render whose backdrop
and floor are its own settings (Background colour, Floor), so it does not take the canvas's gradient. Chrome on a
surface of its own — the strip and the sub-toolbars, the panel, Quick Edit, the playbar, every menu — keeps the app's
theme. A picture taken off screen (a card's) is the light viewport's whatever the setting, and the server's
snapshots are always light.

### The palette

The shadcn variables are the semantic tokens (`styles/tokens.css`); Figma's names map onto them:

| Figma | Token | Light | Dark |
| --- | --- | --- | --- |
| canvas | `--canvas` | #ebebeb | #1e1e1e |
| bg | `--background`, `--sidebar` | #ffffff / oklch 0.985 | #2c2c2c |
| bg-elevated | `--popover`, `--card` | #ffffff | oklch 0.31 |
| bg-secondary / hover | `--secondary`, `--muted` (and `--accent` at 50%) | oklch 0.97 | oklch 0.34 |
| bg-tertiary / selected | `--accent`, `--sidebar-accent` | oklch 0.92 | #444444 |
| border | `--border`, `--sidebar-border` | oklch 0.922 | rgba(255,255,255,.12) |
| text / -secondary / -tertiary | `--foreground` / `--muted-foreground` / `--muted-foreground` at 70% | | |
| brand | `--brand` | #249ddd | #62b7ec |
| text-brand | `--brand-text` (text: a search's match) | #2c7197 | #62b7ec |
| icon-brand | `--brand-icon` (a glyph: the tool in hand's icon; 3:1 on the pressed fill and on white, the graphics minimum) | #1683c7 | #62b7ec |
| brand-subtle | `--brand-subtle` (the brand 12% / 22% into the background) | ≈#e3f2fb | ≈#2a4553 |

The brand is the focus ring (`--ring`), a text selection (`::selection`), a selected tree row's fill
(`--brand-subtle`, `primitives/tree-row.jsx`), a search's match in a tree (`--brand-text`, medium weight), the tool in
hand's icon on the strip and the sub-toolbars (`--brand-icon`, nearer the logo's hue than the text's darker blue,
which read dark and odd on a glyph; its fill stays neutral) and the logo — nothing else (the panel's toggle in the
navbar is the same neutral button open or shut). **The brand is for state** (the focus ring, a
selection, the active tool, a search's match) **and the logo, not for links in the chrome**: a small link (the app
menu's footer, its version and "Made by") is muted, 11/16, and turns the foreground, underlined, under the pointer or
the keyboard's focus. Buttons stay neutral. A warning is `--warning` (its icon, edge and tint) and `--warning-foreground` (its words); an error the
destructive's. The scene's blues — selection (#2979ff, more saturated than the brand on purpose: it is read against
a model, not the chrome), its fill, hover, the box select, the grid and the XYZ palette — are
`@cad/core/lib/viewportTheme.js`'s, written once (`kit/look/sceneColors.test.js` holds it).

### A control's label and value

One rule, Figma's, for every labelled control — a slider, a select or settings row, a toggle, a number field, a menu's
setting row, a card's fact, in the panel, a sub-toolbar (Explode's and Clip's amount) or Preview's
settings: its **label** is `--muted-foreground`, its **value** (the number, the option chosen, a field's text) the
`--foreground`. Every label is one primitive, `FieldLabel` (`primitives/field-label.jsx`): no control sets its label's
colour, weight or size of its own; the label takes its place's size (the panel's 12px), at normal weight
(`kit/inspector/FieldLabels.test.tsx` holds it).

### The slider control

A number a slider sets is ONE control everywhere (`kit/inspector/SliderField.jsx`), shadcn's
labelled slider: no site brings its own slider and number (`src/designSystem.test.js`; the
playbars' scrubber, a timeline, is the one other slider).

- **In a panel**, two lines. The first (28px, a panel row): the label at the left (`FieldLabel`, muted, as every
  control's), and the value at the right, its text's right edge on the slider's (its field's outline hanging past by its
  own 7px, as every box round what is read does). The second: the slider (a 12px band) the
  control's full width, from the label's left edge to the value's text's right edge. No icon before the label,
  no indent. 8px under the slider, the next control: 48px a control, the gap between a label line and
  its slider and between one control and the next the same in Params and Joints, so each label reads
  with the slider under it. In the view's panel it stands on the panel's lines: the label and the track
  from 16px in, the value's text and the track ending 16px from the right.
- **In a toolbar row** (Explode's, Clip's), one line: the tool's button or name as its label,
  the slider, the value.
- **The value** is Figma's number field (`kit/inspector/SliderValueField.jsx`, the same in every slider: Params,
  Joints, Preview's settings, a board's opacities, Explode's and Clip's rows):
  - **As wide as what it holds**: the number and its unit, 22px tall, 6px in (so neither the outline nor the editing
    edge touches the text), 5px corners; 32px at least (two or three digits) and 96px at most, never past its edge and
    never over the label. Its text ends where the slider does, so a longer value grows it to the left; nothing moves
    between rest, hover and editing.
  - **Its states**: at rest no fill, so it reads with the panel's text and its dropdowns; under the pointer a 1px
    outline (the foreground at 20%), the cue that it is edited in place; editing, the background with a `--brand` edge
    (its 1px border and 1px inside it); what is no number, the destructive's edge; off, at half strength with no hover.
  - **The number is the value, the unit is not**: the number in the foreground, tabular figures, right-aligned; the
    unit after it (`mm`, `°`, `%`, `EV`) muted, outside the input: never selected, typed over or deleted.
  - **Editing**: a click selects the number; a later click places the caret (as any field); a click on its padding or
    unit is a click on the number. Enter or leaving it commits, Escape puts back what it held (and the slider with
    it); a value left as it shows commits nothing (its text may round the value it shows). Up and Down step it by
    the control's step, Shift by ten, within the range.
  - **What is typed**: a length in another unit converts where the field's is a length ("1 in" in a mm field is
    25.4 mm; cm, m, in, ft, µm), an angle likewise (rad, deg); another unit says "Unknown unit: kg" under the field.
    A number past the range says its bound ("Max 9 mm") and is set to it on Enter; what is no number outlines the
    field in the destructive's colour, says "Enter a number, 3–9 mm", and goes back on Enter or blur. The hint is a
    tooltip under the field's right end, 11/16. While a valid number is typed, the slider follows it.
  - **The label scrubs**: dragging it sideways (an east-west cursor over it) moves the value a step a pixel, Shift
    ten, on the slider's steps and within its range, written as a slider drag is; a press that does not move is a
    click. A finger's press on a phone scrolls the panel instead.
- **The slider** is shadcn's shape (`primitives/slider.jsx`): a 6px rounded track, its range (from
  `origin` where there is one, a tick at the origin), a 12px round thumb. **Its colours are quiet**, as
  Figma's sliders are, the same rule in light and dark, from the `--slider-*` tokens
  (`styles/tokens.css`): a faint neutral track (the foreground at 9% in light, 12% in dark); a fill a
  few steps darker (28%, 32% in dark), never the primary's near-black or near-white bar nor an accent;
  a light thumb (white; a light grey in dark, so it does not glare) held off the panel by a thin
  mid-grey ring (3:1 against the panel in light; black in dark) and a small shadow. **Hover** (the
  pointer anywhere over the slider) strengthens the fill a step (38%, 42%) and darkens the ring; the
  keyboard's **focus** rings the thumb (3px, the theme's ring at 40%); **disabled** (a motion owning a
  joint, a parameter being saved) the whole slider is at half strength and its thumb flat, no shadow.
  No slider draws a colour of its own. On a phone the band is 16px in the panel, 36px of touch reaching
  over the label's foot, and the thumb 16px.

## Settings

Settings are the person's, never a file's, and live in the app menu: one dropdown
(`file-viewer/navigation/AppMenu.jsx`) on the floating surface, 12rem wide, from the
navbar's logo over every file and over the home (FileViewer builds it from the host's `links`, the
`appSettings` `CadViewer` hands it and `environment.platform`, while a model loads and after
it failed to as well). Its rows, a rule between each group, are only
what the host supplies, the person's settings in the order Language, Telemetry,
Theme:

- **Back to home**, where the host has a home
  (`navigation.home`): it shows the home in this view. The home's own menu has none.
- **Language**, where the host hands the person's language (`language`, both apps): one row,
  its name and then the language in force, whose submenu offers **Automatic (<the inferred
  language>)** and then each language under its own name — English, 简体中文, 繁體中文, 日本語,
  한국어 — whatever the menu is reading in; a press changes it without closing the menu. The
  row is a setting row like Theme: its name, then the language in force, muted, right-aligned
  before the chevron, centred on the column Theme's last segment and the checkboxes share. A
  phone has no room beside the menu for a submenu: there a press of the same row opens the
  choices under it, in the menu itself (closed each time the menu opens, the chevron turning
  down while they show: `DropdownMenuInlineSub`, as More's Display and Zoom), and a choice closes them again.
  Automatic is the default: the web infers the language from the browser's languages, the CAD
  app from its host's locale (then the frame's browser languages); Simplified script or
  mainland China and Singapore read 简体中文, Traditional script or Taiwan, Hong Kong and Macau
  繁體中文, any Japanese 日本語, any Korean 한국어, anything else English. A language chosen
  overrides the inference until Automatic clears it. The host resolves the language and hands
  it down as `environment.locale` (`@cad/ui/i18n`'s `useLanguage`); the shared UI holds
  no locale of its own.
- The host's own on/off settings (`appSettings`), a checkbox item each, in the order they
  come, checked at the right; a press turns one without closing the menu. An info icon after
  a setting's name, where the host gives its meaning (`info`), shows it as a hint to the
  menu's right. **Telemetry**, in both apps: anonymous usage data and crash reports, never
  prompts, models or files. It adds nothing to the navbar.
- **Theme**, where the host hands the person's colour scheme (`colorScheme`, both apps): one
  row, its name and then **System**, **Light** and **Dark** as a segmented control of their
  glyphs (each a radio item, named), the one in force lit; a press changes it without closing
  the menu. The web's System follows the OS and is
  the tab's; the CAD app's follows its host's theme, Light or Dark overriding it for as long as
  the view is open. Neither app has a light/dark button of its own: Theme is the one
  control, the same on the home.
- **Send feedback**, where the host has a tracker (`links.issues`): a link to a new issue
  titled "Feedback: " for the person to finish, naming the version and the platform, with
  no label (what is said may be a bug, a request or a question). Then **GitHub** and
  **Discord**.
- Last, in gray, a footer of two rows: "v<version>", a link to its release notes, and under
  it "Made by @<handle>", the handle a link to the host's X account. A build that is not the release's
  own adds its id to the version: `v0.10.0-dev.b80844940`, the commit it was built from.

Nothing of a file is in it: a file's view is
[Display](#display-settings-and-section-primitives)'s. Every setting is the person's, not a
view's or a tab's: the host keeps it where every view of theirs reads it (both apps: their
settings, `settings.json` in text-to-cad's state directory), and a view reads it again whenever
the person comes back to the page.

Every string of the chrome reads through `@cad/ui/i18n` (`useI18n().t`), English
first: `en.js` holds every key, each other locale the same keys (a parity test), and a key a
locale misses reads English. No view spells a word itself: `scripts/test/check-ui-strings.mjs`
refuses English in JSX text, the attributes a person reads and a table's labels across
`packages/ui/src`, `apps/web/src` and `apps/mcp/src` (a table entry says its `key` beside its
English `label`), with an allow-list for what is no language. What a file or the engine says (an alert's own title and message,
a part's name) stays as it was written. The loading and view-update lines are a closed
vocabulary (`kit/status/loadingState.js`), English in the code and said in the view's language
on screen (`kit/status/statusLabels.js`).

## Position and references

**Joints** (the Position section in code) is a tab of the [view's panel](#the-views-panel-and-the-tool-stack), there
under every tool: a STEP's where the file has joints to move, a
robot's where a joint can be driven. Its knobs in the viewport are Select's, while Select's
filter ticks Position, and only while the parts are where the pose puts them: over an explosion
Select draws no knobs (the section's controls stay, and using them takes Explode off). Its
first row is the pose (`KinematicsPoseRow`, `data-pose-row`), a settings row at the panel's 28px: its
label, **Position** (muted, in the settings rows' 4rem column, on the 16px line; the dropdown's name
"Position: Default"), and the pose in hand as a dropdown as wide as its value (6rem at least, the row's rest at
most) at the row's right end on the right 16px line, as a settings row's control is, so it reads as the setting it is; nothing sits above the
row, and a robot's is the same row. The dropdown holds
**Default**, which puts the joints back, then the named poses, and Custom while the joints are
set by hand. Its last row is its actions row (`KinematicsResetRow`, `data-pose-actions`), where Params has
its Reset and Save, in the same place and style (`PanelActions`): **Reset** alone (its name "Reset
joints"), the way back to the default pose, off while the joints are at their default.
Each joint is the [slider control](#the-slider-control): its name and value (degrees read
"90.0°", a robot's slides in millimetres, "12.5 mm", typed in millimetres too; the unit says
whether it turns or slides, so no kind icon), then its slider (no tooltip: the range is the slider's `aria-valuemin` and `aria-valuemax`).
Each joint is 48px, one after another. Long names truncate with a full-name hint and never take the value's room.
A joint's fills from its rest — as built, or the description's
default — to its value, a tick at the rest where it is inside the range (`origin`): a joint's zero
is mostly mid-range, so a bar from the left end would mean nothing, and the fill says at a glance
which joints are moved and how far. Slider thumbs are named after their
joint, and every slider reports its value at its step's precision (never float
noise). Writes pose the model at once.

Position persists across tools, and across an update of the model whose joints and
named poses are unchanged, the named pose chosen included; an update that changed them
starts the pose at the new defaults, never fitting the old values onto other joints.
Default restores the authored
values (an SRDF's home included), stops motion and hands control back to
Position. Using Position takes Explode off, and exploding puts the pose back to its
default ([one motion at a time](#tools-and-lifecycle)); while the model is exploded there are no
knobs. Preview leaves the tools view's pose as it is and never shows it: it opens on the model
at rest, and a pose set there is its own (see [Preview](#camera-animation-and-preview)). Kinematics, named poses and
animation are separate capabilities; the absence of one never leaves empty
controls for another.

What is picked is [Quick Edit](#quick-edit)'s chips, and a chip's card is what a person
reads of it (`kit/tools/quick-edit/ReferenceChips.jsx`, drawn by `kit/inspector/ItemDetail.jsx` from the
view's one description of the pick: [the card](#the-views-panel-and-the-tool-stack)). A component or subassembly is a chip
of its own; faces, edges and solids are a chip for each kind on each part — "base · face 3"
alone, "base · 6 faces" for several, however they were picked — so a large selection stays a
few chips. A chip names its reference: its own label when it has one (a part's or
subassembly's name, a named face), otherwise its part and kind ("base · face 3") — never the
raw id. In a STEP the card's rows are the reference's few key facts, nothing else: a face's part
and area; an edge's part and length (an arc's, a circle's circumference); a part's size, volume and
mass; a subassembly's part count, size, volume and mass; a run on one part, one row each. Its rows are
the UI font at the panel's 12px, numbers in tabular figures — no monospace. A click on a chip copies its references, each naming its file
by absolute path; resting on it lights its picks; its X drops them.

Viewport picks reach individual faces and edges, every one to hand from the start.
Shift-click adds to a selection in the viewport; Shift, Ctrl or Cmd does in a
tree (robots select several links this way). Double-click, or a row's Isolate,
isolates a component or subassembly, and the tree brings its row into view (its owners opened);
double-click on empty space leaves isolation, as do the isolated row's X, the menu's Exit all
isolates and Escape, and leaving it shuts again what isolating opened (a folded row double-clicked,
the owners its reveal opened), so the tree is as it was before; a row open before, or opened or shut
by the person meanwhile, stays as it is. No bar over the tree says what is isolated: its row does. A double-click on a face,
an edge or ink turns the view square to it (CAD's Normal To, `kit/camera/lookAt.js`) and
selects nothing: the selection is as its first click found it.

## Parameters

**Params** (the Parameters section in code) is a tab of the [view's panel](#the-views-panel-and-the-tool-stack), an engine
document's (`xbf/XbfParametersSection.jsx`), after Model and before Joints, there under every tool
while the document records parameters: the named numbers a model's script declares, each with the value
the document was built with (the structure's `parameters`). A part file with parameters has the panel for
them; a phone has the same tab, in its sidebar sheet. It is the one control of the viewer that changes a design (the
[package's one exception](../README.md)), and it changes it only through the engine: a value set here is
a **draft**, the tab's own, until **Save**. While a draft differs the view draws the model at the drafts
(a **preview**), and nothing is written until Save.

- **The actions row**, last, under the list, in the tab's foot: the foot stands at the panel's bottom edge
  while a list too long for the panel scrolls under it (sticky, on the chrome's colour to the panel's edges,
  `kit/inspector/PanelActions.jsx`, Joints' Reset row the same), so Save is never scrolled away from the values it
  saves; under a short list it stands under the last row. The row is 8px above and below its buttons, a status on the 16px line at its left
  (muted, the panel's 12px: why nothing in the tab can work, where that is so (below), which may wrap to a second line
  in a narrow panel, the row growing to hold it, so it is never cut off; else "Saved" once a save is answered
  and nothing differs; nothing otherwise: no count of what is unsaved, Save on is the sign), then **Reset** (a ghost button) and **Save** (the primary one), each 28px of regular
  text, 8px apart, Save ending on the 16px line at the right. Both are off while nothing differs. Reset drops
  the drafts not yet saved, and the view draws the document again at once. Save sends every changed
  value, and only those, in one request (`client.setModelParameters`). The row is there only while some
  parameter can be written from this view, or the document's own reason keeps them all from it (below).
- **Nothing in the tab can work: the foot's status says why**, as text, in place of "Saved", and Save is
  simply off, with no hint of its own: no alert, no banner, no other line. It is one of three lines: a document
  read from a file, "Edit these in the script."; a model no worker holds (after a restart, its script not run
  since, or found by a refused preview or save: `no_worker`), "Run the script again to edit."; the script
  changed by hand since it ran (found by a refused preview or save: `script_changed`), "Script changed. Run it
  again.". The engine never watches the file, so a hand edit is learned from the first refusal, never before,
  and only the script's next run clears it.
- **Save off for another reason says why**, in its hint, and nothing else in the tab does. Its hint (on a
  wrapper that takes the pointer and the keyboard for the disabled button, `TooltipHint`'s `explainsDisabled`)
  is one short line in plain words, about six words at most, saying what is wrong or what to do, never "save"
  where Save is not what fixes it. The engine's own message is never in it: a build's can run to many lines.
  Save is off, so said, while: a host whose client cannot save ("This view can't save."); the model is building
  (`busy`, a save refused: off for two seconds or until the document's next version); the drafts' preview
  does not build ("These values don't build."; the view keeps the last values that did); a save whose build
  failed and was put back; any other refusal. A refusal of the drafts is cleared by the next edit. Nothing to
  save is no reason: Save is simply off, with no hint.
- **Controls that cannot work are off.** Where neither a preview nor a save can run for a reason the document
  says or a worker gone (`no_worker`), every control is off; a refusal that finds the worker gone drops the
  drafts and their preview (the view draws the document), and the tab is editable again at the document's next
  version (the script run again). A script changed by hand (`script_changed`) takes nothing back: no slider
  snaps back and the tab does not lock. The drafts stay where the person put them, every control stays live,
  the view keeps what it drew, and nothing more is previewed or saved until the document's next version, which
  previews the drafts on screen then. (A preview runs the script as it is on disk in the model's warm worker,
  so after a hand edit it could only mix the new code with the last run's positions of the numbers: it is
  refused, never guessed.)
- **By file, where they come from more than one.** A model whose parameters are declared in more than one
  file (an imported module's, `shared`: "Set in another file") lists its own first, with no heading, then
  each other file's under its name as the engine names it (`fastener_standards.py`, `lib/spec.py`), a 28px
  heading in the panel's muted colour on the 16px line, in the order the files are first met
  (`parameterGroups`). Parameters all from one file have no heading at all.
- **A parameter**, in the document's order (within its file's group). One with both ends of a range is the
  [slider control](#the-slider-control): its name and value on the first line, its slider over the
  range under them, filled from its left end as shadcn's (no fill from the document's value, no
  difference shown: the value beside it is the draft), with no tooltip over it: the range is the
  slider's own `aria-valuemin` and `aria-valuemax`, not a visible bubble.
  Any other is a settings row: its name in the row's label column, widened to take the room (a
  parameter's name is an identifier, not a short word), and `FileSheetNumberProperty` in a 5.5rem column
  ending on the 16px line. An integer parameter steps and is typed in whole numbers; a float by its
  declared step, else by a power of ten that crosses its range in a hundred to a thousand steps.
  Values read with their unit ("2.5 mm", "30°"), in tabular figures. Every write crosses one boundary
  (`parameterValue`: the range, a whole number, six decimals), shared by the slider and the field; a
  value typed back to the document's is no draft. A parameter the engine cannot write for a reason of its
  own (declared in another file, set by an expression) is its control, off, and its hint says why in one
  short line ("Set in lib/spec.py.", "Calculated in the code."), on a wrapper that
  takes the pointer and the keyboard, as Save's.
- **The preview.** The drafts ask the engine for the model at them (`client.previewModelParameters`),
  which it builds for this page alone and writes nothing (not the script, not the document). One request
  is out per document at a time, the newest drafts next: values passed over while one builds are never
  built. When they go is the model's **cadence**, set by how long its previews take, request to answer (a
  running estimate per document, the newest answer weighing half; a model not yet previewed counts as
  fast). A **fast** model (its estimate under 250 ms) follows a slider as it moves: the newest drafts go as
  each answer arrives. A **slow** one is sent nothing while a slider moves, only the value the person comes
  to: the pointer let go, a keyboard step, a value typed and committed, or the slider at rest for 300 ms,
  the pointer still down (a build in the kernel cannot be stopped once begun, so none is spent on a value
  already passed). Each answer is drawn in the document's place as it lands (`useXbfScene`'s `preview`):
  only the parts the values changed are fetched, the camera stays where it is, and the view's update line
  says nothing (it is the document's). Every control stays live: no slider locks or snaps back while a
  preview waits or builds, and the view keeps the last values that built.
- **Nothing says a preview is building**: no text in the foot, none on a row. Drafts back at the document's
  values draw the document at once. A model whose script is running or saving now (`busy`) is asked again,
  waiting longer each time, said nothing. A preview refused turns Save off, its hint saying why (above), and
  the view keeps the last preview that built. Measure measures what is drawn; Export, a snapshot and every
  other page show the document, never the preview.
- **Saving.** While a save is out every control and both buttons are off and Save is a spinner and
  "Saving…" (`aria-busy`), and nothing more is previewed. The engine rewrites the numbers in the script
  and builds the model again, and the rebuilt document arrives as any new version does (the view's
  update line says it is updating). Until it holds them the saved values stay on their controls and are
  not sent again, and the preview of them stays drawn; once it does, the view draws the document and the
  preview is let go. A value the engine did not write (the script already held it) goes back to the
  document's.
- **A refusal** of a save keeps every draft (but `no_worker`, above) and turns Save off (the foot saying why for
  `script_changed`, above),
  its hint the tab's sentence for the engine's `code` -- the script ran with no worker left holding it, it
  changed since it ran, the model is building, a value out of range or of the wrong kind, a parameter no
  longer declared or not writable, a build of the new values that failed and was put back -- and nothing
  more; a failure with no code this page knows, "Couldn't save.".
- **Search** finds a parameter by its name, as the panel's search finds every tab's rows.
- **Telling the agent.** Each value saved is remembered by the view (its name, its value before and
  after, its script) for as long as the file is on screen, and the next Quick Edit message, sent,
  queued or copied, says them once, after what the person wrote and before the file, as one plain
  line: "Saved from the viewer since your last edit: wall 2 -> 2.5 (bracket.py); the script holds these
  values and is built at them: read it again before you edit it, and keep them", the script by its
  name, never its path, and what the agent does with them, so the line explains itself; saves of one parameter that follow on from each other read as one change.
  Once that message has gone the list is forgotten; a message that failed keeps it for the next. A
  message sent while another that carries it is still on its way carries none of it, so it is never
  said twice. A message sent while drafts are drawn (a preview) says so every time, after the saved
  line: "Shown in the viewer, not saved: wall 2 -> 3.5 (bracket.py); the script still holds the first
  values; write the new ones only if asked", since what the agent is shown (the views, the picks) is not the script; it is the view's
  state, not a change, so it is never remembered.

## Quick Edit

Quick Edit is always available in an interactive CAD view. It has no enable/disable
control or persisted preference; stale settings cannot suppress it.

Quick Edit is a person's note to their agent about the file on screen, and the
one way the viewer hands it over: a bar at the view's bottom, on the floating surface the
tool strip has (its radius and padding at the strip's V1 proportions), two rows like a chat's
input. It is there only while it has something to carry or a note to keep: nothing stands in
for it otherwise, not even a button. Only a view whose picks and annotations a note can carry
has it (a STEP's, a robot's); a compact host gets none, and Preview puts it away with the
tools. While the view loads it is out of sight, its note and its state kept. It is essential,
so no setting turns it off.

The bar stands 16px off the view's bottom. **The toolbar and the Quick Edit bar are centred on the window, always;
panels never move them; where they meet a panel they sit above it.** Its width is 400px at most, else the window less
16px a side (8px on a phone), measured by the one frame every view mounts (`ViewFrame.jsx`'s `QUICK_EDIT_MAX_PX` and
`QUICK_EDIT_MARGIN_PX`, written to `--cad-quick-edit-left` and `--cad-quick-edit-width`), in the top layer over both
panels and an overlaid one. Why: the bar is where the person writes, and it stays where their eyes left it whatever
opens beside it; a bar that moved or shrank with each panel was a different target every time.

Its first row is the context: what goes with the note, as chips (below), one row of them, the
rest under **+N more**, whose list opens above it; then, at the row's right end, an X. The file always goes and is not named. Its second row is the note ("Describe a
change…") with the buttons at its right. The note is a comfortable line at rest and grows
upward, line by line, as it is written (never on focus), to six lines, then scrolls; the bar's
border is blue while the note has the keyboard. Where the bar is narrow its chips give way to
**+N more** sooner and Copy Prompt drops its words for its icon (only where the window makes the bar narrower than 400px).

On a phone (`docked`) the bar is the same two rows across the view, 8px in, above the safe
area, at a finger's sizes (36px buttons, the note's text a step up). A pick never brings up the
keyboard there: the note is a tap away. A tap on a chip opens its card (above the chip) and
copies nothing: the card's title copies. On a desktop a card opens above its chip too, and a
click on the chip copies it.

The bar follows what it would carry: it opens when something is picked or annotated, and
closes when that goes. **Every geometry reference is ONE chip** (`ReferenceChips.jsx`'s `groupedChips`, the same in
every view): "5 refs" for several, whatever their kinds (parts, faces, edges, a board's pads and nets, a drawing's
entities), and a single pick its own chip by its own name ("output_flange"); the annotation (the drawing) and the
measurements keep chips of their own. **A press on the geometry chip (or a rest of the pointer) opens its list**, the
one place a pick is read in detail: one row a reference, its icon, its whole name (never a chip's cut name) and its kind ("Part", "Face of
output_flange", "6 faces"), its X at the right; and under it **its key facts**, in the muted 11/16 (`text-tiny`), a
label column and the values in tabular figures: a part's size, volume and mass, a face's type and area, an edge's
length or radius, a board part's value, footprint and net, a DXF entity's type, layer and length, a GLB node's size —
the view's own descriptions (each chip's `detail.facts`, the producers the views always had), only what is known (no
Mass row for a part with no material), a
fact that is not text left out and said (`referenceFacts`). With one reference the press shows that one's row and
facts, the same list. A press on a row's name copies its reference ("Copied" in its place). **No second popover or
card from the list.** The chip's X drops them all. A renderer that hands no chips has its references the same chip. What
goes to the agent is unchanged: every reference, however the chips show them. Why one chip: the bar is for the note, and a row of chips per kind crowded it out without saying
more than a count does. Every chip leads with its icon — the Annotation chip's pen, a reference's pick glyph (a part's cube, a face,
an edge, a vertex) — then its words, and the kinds stand in the order each first came. A chip's copy pasted into the note is a pill there,
drawn as the chip is, 20px like the note's lines so it sits in its rows without spacing
them out. A click on a pill selects it whole, highlighted in the selection's colour, so
Backspace, Delete or typing replaces it as it would selected text. Its chips are
**Annotation** (its X clears the ink), then the selection. The Annotation chip does not copy
references or write files. Copy Prompt, Queue and Send
include their data in the snapshot packet; only selection chips copy individual references.
The X dismisses the bar: its note goes, and the bar stays away until what it would carry
changes (another pick, a pick undone, ink drawn or cleared); the selection and the annotations
are kept, and so are measurements, which are not Quick Edit's. A note that has gone (Queue,
Send) clears what it carried, the selection (as a press on the model's background does) and the
annotations, so the bar goes; Copy Prompt keeps it all, since nothing has gone yet.
Escape in an empty bar is the viewer's Escape (clearing the selection, and so the bar);
in a bar with a note it only hands the keyboard back to the model. Coming into sight and being
dismissed are counted (`quick_edit_shown`, `quick_edit_dismissed`), as its buttons are.

The person's picks put the keyboard in the note on a desktop, each one (a pick right after their
primary press in this view), and so does a first annotation stroke once the pen lifts. No
live command selects (every renderer declines `select`), so nothing but a person opens it.

The buttons, left to right, are only those the host can carry out, and the rightmost
is the primary one, which Enter presses (Shift+Enter is a new line). They are the
`Button` primitive in its own shape — 28px squares with its rounded corners, each an
icon with a name and a hint above it — and every one is solid: the primary in the `default`
variant, the others in `secondary`. Where Copy Prompt is the only one (a host that
takes no message, as the web), it is a button in words, "Copy Prompt" with its icon
first — at the bar's full 400px too: its 8px sides and 4px gap, and the note at least 12rem beside it, keep the words
and the icon in the bar — its icon alone only where the window makes the bar narrower than that (`@container`: the
bar's content under 24rem, a window under about 430px, a phone's). Why: the bar at its full width read as icon-only, a
square nobody knew was Copy.
While there is no note they are disabled, dimmed but still drawn:

- **Copy Prompt** (copy icon), always. It copies the note as text: its references
  spelled as copied references are, and its files by the paths they were saved at,
  since text carries no file.
- **Queue** (list-plus icon), where the destination is a composer: the note goes
  into the context of the person's next message.
- **Send** (up arrow), where the host can post a message: the note goes now, as the
  person's message.

Every prompt captures the current view and the recorded views with remaining ink.
If the current view matches a recorded view, its exact current framing replaces
that entry for this export; otherwise a `current view` job is appended. Text and
selection alone also capture the current view. The packet stores shared input,
annotation once, with a `jobs` list of view states.
At Copy, Queue or Send, packets up to 1024 bytes of compact UTF-8 JSON are included
in the prompt as JSON. Larger packets are written to system temporary storage as
one `.snapshot.json` and named by path. Drawing, selecting and typing write nothing.
Captured 3D views preserve projection and lens. No PNG is rendered or attached.
To render inline JSON, the receiving agent saves it to a temporary file first,
then draws a view with `cad <type> snapshot <document> <out.png> --annotation <file>
--camera authored`.


Queue and Send clear the note and what it carries, and so close the box, once the
note has gone. Copy Prompt keeps it all, since nothing has gone yet: its button
shows a tick for a moment. A failure keeps the note and says why in the box. The message is
one format, sent, queued or copied: what the person wrote; then, once, what the view itself has
to tell the agent (the renderer's `promptNotes`: the [Parameters](#parameters) saved since the last
message); then `File: <path>`; then
`References:` and one reference per line; then each file that travels as a file by its
label and path — `Snapshot (cad <type> snapshot --annotation):` — or the compact object under
`Snapshot JSON (cad <type> snapshot --annotation):`. An agent draws each view with
`cad <type> snapshot SRC OUT.png --annotation PACKET --camera authored`.

## Camera, animation and Preview

A drag on the model orbits as a turntable that goes over the top (`kit/camera/turntable.js`):
sideways about the world's vertical, up and down about the view's own level right, with no stop
at straight down or straight up — the view goes on over the pole and comes round upside down,
never rolled. A sideways drag begun upside down turns the other way, so the model's near side
follows the cursor; the drag keeps the sense it began with to its end, so one that crosses a pole
never reverses under the cursor, and the next drag picks again. The arrow keys (held together, one
gesture) and a drag across the cube orbit the same way.

Cube face, edge and corner clicks turn the view and keep pan and zoom, and land upright: the top
and bottom exactly down their axis, +Y up the screen; dragging
the cube orbits. Reloading the page restores the camera the file on screen was left
at, and its Display settings, Explode/Clip, the pose, hidden and isolated parts and
the tree's expansion come back with it. A file left in the page — for another file or the
home — has its view kept by the page until it closes, and shown again it opens as it was
left, as a reload opens the file on screen (the tab's record keeps the file on screen's view
alone, so a reload brings back that one); a file the page has not shown opens fitted, at
the defaults. An update of the model on
screen keeps its Display settings, Explode/Clip, hidden and isolated parts and its
tree, and the pose while its joints are unchanged. The tool, the selection and
measurements never come back — every open starts in the default tool with nothing
selected.

Zoom to Fit recenters and frames the whole original model at the current angle, in the room under
the tool strip and centred in it, as a flat view's fit keeps clear of the strip (every 3D fit does:
the first frame, a board's 3D view);
Zoom to Selection frames the selection and is unavailable without one. A double-click on empty space fits
only while Select is in hand, in every view, 2D or 3D: under Draw or Measure a double-click is
the tool's (the frame says Select is up, `data-cad-selecting`, and `kit/viewport/dom.js`'s
`doubleClickFits` is the one rule the canvases keep). Both are
every view's context-menu items and the zoom's menu's (below); the live `resetCamera` command takes
the same fit path.

**The zoom.** A flat view shows it, as Figma does: its corner's one control (`kit/shell/ZoomControl.jsx`: [The view's
corner](#ownership-and-layout)), the zoom as a percentage in tabular digits at a fixed width with a small chevron, no −
or +, pressed opening its menu — the zoom's commands alone: Zoom in, Zoom out (half again, and back), Zoom to
100%, then Zoom to fit and Zoom to selection, each with its key (no key hints on a touch screen), as Figma's: ⌘+ and ⌘- (Ctrl+= and
Ctrl+- elsewhere; the plain + and - too), ⇧0, F (⇧1 too) and ⇧2. A 3D view shows no percentage, as CAD
tools do not: F, a double-click on empty space under Select and the view's menu frame it, and the
same keys zoom it. The wheel, a pinch, a double-click and the keys zoom a flat view as before. A board in 3D keeps its
zoom, which reads and steps its 3D camera
(`viewportZoom`, the 3D views' own zoom). On a phone there is no zoom control: a pinch zooms, and the View menu's Reset
view fits (outside a navbar, the zoom is More's Zoom row, its choices opening under it). **100% is the
model as authored, framed whole**: a flat view's fit, a 3D view's rest box (`restBounds`; a board's
slab) at the camera's angle — a
fixed ruler nothing shown moves: not Explode, a pose, a routine, Clip, hiding or isolating, which
leave the number where it is while the camera stays. **Zoom to fit frames what is shown now**
(`scene.shownBounds()`: the parts as they stand, exploded or posed, the hidden ones left out, the
isolated ones alone; else `bounds`), so on an exploded assembly it reads whatever that takes, 42%
say. A rebuild whose box changed redefines 100%: an untouched camera fits again and reads 100%, a
camera the person took stays exactly where it is and its number moves. The number is read from the
view live (`zoomPercent()`, `subscribeCamera()`; a flat view's `zoom`), redrawn at most once a frame.

**A rebuild follows the camera's owner** (`kit/camera/cameraTouch.js`). A page opens on the
viewer's fit, and the camera is **untouched** until the person takes it: an orbit, a pan or a
zoom (a drag, the wheel, a pinch, the arrow keys), a view cube face, edge or corner, a drag
across the cube, a double-click's Look at, Zoom to selection, or a camera handed to the view
(the live `setCamera`). While it is untouched, a rebuild of the file on screen whose rest box
changed fits the camera again, the fit F makes, animated as F's is, along the direction the
view looks; a rebuild with the same box changes nothing. The first touch makes the camera the
person's for the page's life, and a rebuild then keeps it exactly, its pose and its zoom, as
desktop CAD does. A fit hands it back: **F**, Zoom to Fit or the live
`resetCamera` leaves the camera untouched again. A resize keeps its own rule (opening's refit
while it settles, the model's apparent size after). The state is the page's: a reload restores
the saved view, and a camera restored is the person's, so it is touched until they fit; a file
opened afresh starts untouched. Preview's view, which keeps no camera, re-fits nothing.

**Preview** (`previewing` in code) is available for every 3D file, animated
or not, and for nothing else: a renderer declares it (`useRendererShell`'s `previewable`: STEP,
GLB, STL/3MF, URDF/SRDF), and a view whose renderer does not (a DXF, 2D) has no Preview
button, not a disabled one, and never enters it, whatever asks. It is the shell's own state;
hosts neither start nor observe it. Its button is lucide's Play, a play triangle ("Preview"), the strip's last
tile, in every host. A press covers the view at once
("Preparing preview…", on the canvas) and enters Preview under the cover,
which lifts once Preview's view has presented its first frame, its published mesh is complete
and the studio frame's picture has converged
(every sample drawn: the viewport's `pictureProgress`) — at least 700ms; at five seconds it stops
waiting for more components and lifts on the picture converged, a second later at the latest — fading from
the finished picture (`kit/shell/previewCover.js`). A view the shell set moving, Orbit
on or a routine playing, has nothing to wait for; a published component that lands starts the
picture again and is waited for, never read as motion. The navbar is gone too, in every host
(the renderer says Preview is up, `onPreviewChange`, and FileViewer hides it until it closes), as are
the tool strip, its sub-toolbar, the tool stack and their resize grips, Quick
Edit, the host's notice and corner, joint handles, cube and context menu (`PreviewChrome`, hidden and
inert); leaving Preview gives the host's chrome back as it was.

In the navbar's place, over the view's top edge, is **Preview's bar**: the navbar's row (40px, a
phone's 48px) on no surface, the model showing through, with the file's or model's name at its
left as plain words, muted as its controls are (no logo, menu, dropdown or glyph), and at its right **Preview settings** (a
sliders icon, pressed while its panel is open, a second press closing it) and the way out, an X
(**Exit preview**), their hints below them; nothing else, in every host (no Full size,
no Quick Edit). **It and the playbar are drawn in the backdrop's ink, never the app's** (`PreviewChrome.jsx`'s
`backdropScheme`: the `.light` or `.dark` token scope by Preview's Background colour, else the viewport's canvas),
as the corner and the cube follow the viewport: dark ink on a light backdrop in the dark app, light on a dark one, the
name's halo the backdrop's too; Preview's settings panel, on a surface of its own, keeps the app's. It and the playbar, where the file has routines, come and go together, as a
video player's controls do (`usePreviewIdle`): up as Preview opens, gone after two seconds with no
pointer movement over the view (counted from the frame that shows them, ending at a frame, so a slow
GPU's long frame is never idle time; each says `data-state="visible"` or `"hidden"`), and at once when the pointer leaves the view or the window
(`pointerleave`/`mouseleave` on the view, `blur` of the window), back on the next movement or a tap, and on keyboard focus of
anything in either; they stay while the pointer is on either, while something in one has the
focus (a menu of theirs open among them) and while the settings are open. Gone, they let presses
through to the model, and hiding never touches the routine. Under the bar's right end, docked at
the view's right edge, the settings panel (`kit/shell/PreviewSettings.jsx`), which slides in and out
from that edge (`SIDEBAR_SLIDE_CLASS`, 200ms, none under reduced motion), closed each time Preview
opens and put away by its button or its own X: **Orbit** — its heading's checkbox turns the camera about the model, off every
time Preview opens, and its **Speed** is a dropdown of speeds — then Render's own settings
page (see [Display settings](#display-settings-and-section-primitives)). Preview has no
panel (hidden, so a tree keeps its state); a file with routines has Preview's own routine in a
playbar under the model (`kit/tools/playbar/PreviewPlaybar.jsx`), which fades with the bar.
Escape leaves Preview too, once an open dropdown has closed. Explode and Clip are the tools
view's alone.

**Preview is drawn in Render**, whatever the file's display mode: it is a view of its own
over the tools view, drawing the file's Render settings, and the file's own mode and its
settings are left as they are. The tools view never draws Render: no file's mode is Render,
a live `setDisplaySettings` refuses it as it refuses any mode it does not know, and a saved view
left in it reads as the defaults. Render settings edited in Preview are the file's Render settings;
leaving returns the tools view to the file's mode.

**Routines** play, in the tools view, from the panel's **Animation** tab (**Motion** for an engine document's motions;
`kit/tools/playbar/AnimationSection.jsx`),
last of its tabs, for a file with routines only (an engine document's motions, a STEP's where it has any, a GLB's
animations; none: no tab), and nothing of them is on the tool strip or under the model: there is no playbar in the
tools view. Its rows are the panel's own (`kit/inspector/panelRows.jsx`, 28px, on the panel's one 16px inset, `--panel-inset`), top to bottom:
- **Clip**: a bordered dropdown as Joints' Position is, the routine's name alone (no duration), every routine in its
  menu (one too); a choice plays it from its start.
- **The transport**: **Play** or **Pause** (the strip's 28px tile, its icon turning in place) at the row's left, the
  scrubber (`AnimationTimeControl`) the rest of it; no time text (the time is the scrubber's value text).
- **Speed** a dropdown ("1×"), **Loop** (Repeat) and **Autoplay** (CirclePlay) switch rows: the file's (its view's
  `playback`), Speed and Loop once chosen what its routines play with, Autoplay whether entering Preview starts it.

**The tab's controls are one set** at rest, playing and paused: nothing comes or goes as the routine plays.
**There is no Stop: the scrubber's start is the rest pose.** Scrubbed to 0 while the routine is not playing (dragged
to the left end, Home, or the arrows down to it), the routine lets the model go (`onRelease`) and the model is at
rest, as built; playing, a scrub to 0 plays on from there. One motion at a time holds (the renderer's `motionExclusion`):
playing puts a pose and Explode at rest, and a joint's edit or Explode puts the routine at rest. **Leaving the tab or
shutting the panel leaves a playing routine playing**: there is no other control for it on screen and no key for it,
and the tab, opened again, shows it playing, its Pause to hand (the tab stays mounted, out of sight, through Preview too).
A record from before the tab that kept a playbar put away (`playback.collapsed`) is read without it.

In **Preview**, which has no strip, Preview's own playbar plays its routine
(`kit/tools/playbar/PreviewPlaybar.jsx`): one transparent row under the model on no surface, fading with
Preview's bar — the routines' list where there are two or more, then **Play** or **Pause**, the scrubber
and **Playback settings** (a cog: Speed, Loop, Autoplay). In the tools view a routine is a motion as a pose is
(see [one motion at a time](#tools-and-lifecycle)): paused, its frame stays on the model. A
routine opens at rest. Each view's routine is its own: entering Preview sets the
tools view's untouched and starts its own at rest, playing only under Autoplay (off by default);
leaving throws Preview's away, and the tools view's is as it was left. A new revision of the
model starts its routine at rest. Speed and Loop are the file's, one set,
chosen in Playback settings and kept in its view once chosen — until then the routine's own
apply. Orbit's speed (1×) and Autoplay are the file's too, remembered between leaving and
re-entering Preview and across a reload of the tab; whether it orbits is not kept. Another
file has its own, which a file the page left has back when it is shown again, and a file the
page has not shown starts at the defaults. Nothing of the
routine — which one, its time, whether it plays — is saved. Orbit is not an animation
setting.

**Preview and the tools view are two states.** Entering Preview leaves the tools view's
state exactly as it is — the tool in hand and its sub-toolbar, the Position pose, the routine,
the selection, hidden and isolated parts, Explode and Clip, Measure's results, the annotations,
the camera — and Preview starts clean, from the model as authored: at its opening pose,
every part shown, nothing isolated, picked, hovered, measured, exploded or clipped, its own
camera fitted at the default angle and still, its routine at rest. Leaving it throws away what
was done there — its camera, its pose, its routine — and the tools view comes back exactly as
it was, in the file's display mode, its camera in the projection and lens the Display settings
now hold. Nothing of the tools view is reset to make room for Preview and nothing of the
Preview's is kept: the next one starts clean again. Preview holds this by being a view of its
own (`kit/shell/PreviewView.jsx`): its own viewport, scene, camera, pose and routine, mounted
over the tools view's while it is up and unmounted as it closes, sharing only the page's GPU
device. The tools view's viewport stays mounted throughout and is never told: it draws nothing
while covered and is uncovered with its own last frame. What is not either state's is the file's settings, shared by
both and kept: its Display settings (an edit in Preview's Render settings is the file's
Render settings), Orbit's speed, Autoplay, Speed and Loop.

**Two views, two ways of drawing.** The tools view is drawn for working on the
model: the scene quality its settings resolve to, and a lower pixel ratio while
the camera moves so a gesture stays responsive. Preview's view is drawn for looking at
it, in Render (`kit/viewport/previewViewScene.js`): one scene-quality tier up (Interactive to
Standard, Standard to High — a higher idle pixel ratio, and at High larger shadow and
environment maps, at the same meshes), its full pixel ratio kept while it orbits, and nothing
of the tools view's (no picking, overlays, cube or tool effects). Neither changes a Display
setting. Render's studio code and environment are prepared a moment after a model is on screen
(`useRendererShell`'s `previewPrepare`), into the GPU device's cache Preview draws from, so
entering Preview has less to do — on a GPU. On a software renderer (SwiftShader, llvmpipe:
the viewport's `softwareRendering`), where that compile would hold the page for seconds unasked,
nothing is prepared ahead: Preview prepares as it is entered, under its cover.

## Keyboard

Escape and Copy belong to one viewer: the one with focus, or the one last
pressed in while focus is on the page. Editable targets keep their own keys. A file
shown takes the keyboard where nothing has it, in a page of its own (never a card in a
chat's frame), so its tool keys work with no press in it first (`file-viewer/takeKeyboard.js`).

- **Escape**, innermost first: an open popup in this viewer (a menu, the app menu
  included, a Select, a color picker, Display, the explorer) closes itself; then Preview closes;
  then the drawing surface's canvas (Draw's) spends its own Escape; then the selected ink; then an unfinished
  measurement; then the tool in hand, any but Select, which goes down and takes Select up, what
  it set kept; then the renderer's own (STEP: the selection, then isolation; robots: the
  selection). The view's panel peeking over the model counts as an open popup: a popup in it, or its search box,
  spends Escape first, then Escape puts the peek away, and nothing else. The pinned panel and the tool stack's panels
  are never Escape's to close.
- **The view's panel's grip** (its right edge), and a resizable panel's (its bottom-right corner),
  is a separator in the tab order: Left/Right nudge its width by 16px (and a resizable panel's
  Up/Down its cap), and Home and End take it to its bounds.
- **Copy** (⌘C or Ctrl+C, and Ctrl+Insert) copies the view with its annotations
  while Draw is up, otherwise the selection's references — unless a text field
  has focus or text is selected.
- **Quick Edit's bar** keeps its own keys: Enter presses the primary button and
  Shift+Enter is a new line. Escape hands the keyboard back to the view and keeps
  a note; in an empty bar it closes the bar and is also the viewer's own Escape
  (it clears the selection). ⌘C or Ctrl+C with none of its text selected is the
  viewer's copy.
- **Ctrl+H** (⌘H) on a KiCad board cycles Display's Others, Shown, Dimmed, Hidden and round, as
  KiCad's high-contrast key does, while the board has the keyboard (as Escape's viewer, above); no
  other view binds it, and a Mac browser that keeps ⌘H for Hide leaves Ctrl+H.
- **3** and **⇧F** on a KiCad board, single keys as a tool's are (no ⌘, Ctrl or Alt, never in a text
  field), while the board has the keyboard: **3** draws it in 3D and flat again (2D/3D), as KiCad's Alt+3
  opens its 3D view; **⇧F** turns it over (Flip: in 2D the side shown, in 3D the camera), EasyEDA's
  Shift+F, since **F** is Zoom to fit everywhere. Each shows after its button's hint. No other view binds
  them, and neither is any other binding's: ⇧1, ⇧2 and ⇧0 are the zoom's, ⇧P and ⇧L the drawing tools'.
- **⌘\\** (Ctrl+\\) shows and hides the panel, in every view that has one (a board, a schematic,
  a drawing with Layers, a STEP, a robot), and **/** opens it on its search with the keyboard in the box, while the
  view has the keyboard; in the box, Escape closes the search. While the panel peeks, ⌘\\ pins it (the toggle's key,
  the one other way to pin it), and / opens its search in the peek, pinning nothing. **\\** alone does nothing.
  On a phone ⌘\\ opens and shuts the panel's sheet; / does nothing there.
- **Arrow keys** orbit the viewer that has focus or the pointer over
  it, never every mounted viewport; they do nothing in Preview or with a
  modifier held.
- **A tree's rows** (the Model tree, the name menu's Files) walk by the keyboard as the WAI-ARIA tree
  pattern has it, one rule for every tree that walks its rows (`primitives/tree-keys.js`): from the row
  with the keyboard, Down and Up the next and the previous row on screen, Home and End the first and the
  last, Right a shut row's opening and an open one's first row, Left an open row's shutting and any other
  row's owner; Enter and Space are the row's own press. With the keyboard in a row, the arrows are the
  tree's, never the viewer's orbit.
- **Undo and Redo** (⌘Z and ⇧⌘Z, Ctrl+Z and Ctrl+Y) walk the view's one history: each piece of
  ink put down, erased, restyled or cleared, and each measurement taken, deleted or cleared. The
  camera, the selection, Display, Explode, Clip, hiding and isolating, and Position's pose are
  not steps: they are how the model is looked at, each with its own way back. There are no
  Undo and Redo buttons.
- **Single keys** (`kit/tools/toolShortcuts.js`), with no ⌘, Ctrl or Alt and never in a text
  field or Preview, take a tool up as a design or CAD tool's do: **V** Select, **M** Measure;
  **P** the Pen, **⇧P** the Highlighter, **E** the Eraser; **R** the Rectangle, **L** the Line,
  **⇧L** the Arrow, **O** the Ellipse, **T** Text, **G** Fill (each taking up Draw with that
  tool in hand); and **F** frames the model (Zoom to fit: and the zoom's menu, the corner's percentage). A tool already in hand stays so.
  The zoom's keys are the design tools' (`pressZoomKey`), held keys repeating: **+** (or **=**) and
  **-** zoom in and out, with ⌘ or Ctrl as well (the view's then, never the page's zoom); **⇧1**
  fits as F does, **⇧2** frames what Select has picked (nothing with nothing picked), and **⇧0** is
  100% (a flat view's fit; a 3D view's authored box at the camera's angle, about its target).
  Each key shows after its name in its button's tooltip ("Measure M", muted), Draw's tooltip names what it draws
  with now ("Rectangle R"), and each tool of its row names its own key.

## Tooltips and feedback

Every hint is a `TooltipHint`: compact text, one surface and arrow, a 400ms
delay. No native `title` anywhere in chrome. Prefer one or two words; show a
full technical name only when it is truncated (`overflowOnly`). Quick Edit's buttons, the
strip's buttons (Preview among them; a tool with a key shows it after its name,
muted), the drawing row's tools (each with its key), the corner's buttons (the zoom's),
the navbar's right-hand controls (an
alert's icon, the host's actions: the CAD app's Full size), Preview's bar (Preview
settings, Exit preview) are hinted by name — the strip's hints above their buttons, the others' below (the
zoom's and View's under them); there is no hint on the navbar's left (the logo,
the file's name and the ⋯ say what they are), on Display's settings button, Playback settings, an X,
the transport (play, pause, the scrubber), the drawing row's settings or labelled text
buttons (Quick Edit's alone say what they do). A disabled, selected or expanded control has none, but for a
control off for a reason the person can act on, whose hint says why and what to do (the [Parameters](#parameters)
tab's Save, a parameter declared elsewhere: `TooltipHint`'s `explainsDisabled`, on a wrapper that takes the
pointer and the keyboard for it); pressing or leaving cancels a
pending one. A hint appears on focus only for keyboard navigation (the focus a Tab moves, that one move alone), never
when code moves focus: a closing menu handing it back, a peek handing it to the panel's toggle as it goes.

Copy, snapshot and prompt actions complete silently, the Copy and Quick Edit
buttons showing a tick for a moment. An export is the one exception, and it works as a
browser's download does: one toast, shadcn's Sonner as it ships (`primitives/sonner.jsx`,
mounted once with the export controls), at the view's top right, 16px under the navbar and
16px from the edge, at every width. It is as small as a menu item: one line of the menu's text
(`text-xs`, 12/16, regular weight), its padding (6px by 10px), a 14px icon, under 32px tall and as
wide as its line (above a 600px window; under it Sonner spans the screen less its 16px insets),
set through the Toaster's `toastOptions` and `offset` in `export/ExportControls.tsx`. It says
what the page does, which is prepare the file, not download it: Sonner's spinner while the
job is queued or running and while a dropped connection is asked again (**Preparing
part.step…**), dismissed the moment the file is handed to the browser's download (whose own
downloads say the rest), with no success toast of its own; or, where the export fails, its
error icon with the engine's one-line reason, kept until its dismiss, the one button a toast
has. No other action earns a toast. Export is the file's ⋯'s last item, a stock shadcn
submenu (`DropdownMenuSub`), never the navbar's right end and never the tool strip. It opens
the formats in the menu's own surface and type, as wide as its
items (shadcn's 8rem least) (`export/ExportControls.tsx`): the formats the file's kind writes, plain items, known
from the kind and the scene the view already holds, so nothing loads before it shows
(`export/formats.ts`: a STEP's, an xbf's and a held model's STEP, STL, 3MF, GLB and XBF, and
DXF where the view draws it flat on z=0, an xbf's XBF its own bytes; a GLB's, an STL's or a
3MF's the other two mesh kinds), and nothing else: no job list, no rule, no note. A view
whose file writes nothing has no Export. A format chosen closes the file menu and starts its export
at once; nothing is asked first, and choosing it again is another export.
A finished file is a plain browser download, started once by itself; where it lands is
the browser's setting (its download bubble, or its Save dialog), and the page never says it
was saved. No source bundle is an export format.
Progress stays in the viewport; a failed action is the
viewport's alert card, whose **Retry** reloads the file and whose **Report Issue**,
where the host has a tracker, opens a new issue titled "Issue: ", labelled `bug`, filled
in from the card. Its **Details** open into a box that scrolls, with a copy icon at the
box's top-right corner, hinted **Copy**: it copies all of the details and shows a tick for a
moment, or, where the clipboard refuses, a line under the box saying so. Errors handed to
the host's `onError` are the host's to show. A card the
model survives (a failed update, a warning beside the model) has an X, **Dismiss**: it puts
the card away for as long as that alert stands, and its icon, first of the navbar's
right-hand controls (before the host's actions), brings it back. The dismissal goes once the alert changes or clears, or
another file opens; with the card back, so does the icon. Preview has no navbar, and so no
icon.

**What's new** is the one dialog the viewer opens by itself (`whats-new/WhatsNewDialog.tsx`): once
after a release with notes is installed, never on a new person's first run, over the home or a
file's view once its renderer is up (never a loading page, nor while the host's own notice covers
the view). It is the stock shadcn Dialog (`primitives/dialog.jsx`, on the `text-ui` scale, no corner
X): the release's title, its items as a list, each a bold title and, in the muted text, a few words on
what the feature is for, then one short example prompt in quotation marks (never a command), and
one primary button, **Got it**, which has the focus. The button, Escape and a press outside each
close it and keep it seen for every view of the person's; nothing else is offered.

## Naming the page

Text a person reads in the viewer and the CAD app says "browser" (**Open in browser**, "open the
model in your browser"); where a sentence means the page
itself it says "the viewer" or "this page". That holds for every button, notice, card, menu and tool
message an agent relays to a person, in every locale. The page has no other name: developer docs
and the skills call it the viewer too, its command is `cad viewer`, and where a reader has no
context (a file read on its own, a package's description) it is "the text-to-cad viewer".

## Verification

Verify state transitions, touch cancellation, keyboard operation, nested popup
dismissal, feature availability, narrow panels and empty or error states.
Camera and kept-tool tests exercise real transitions, not class names. Do not
keep tests for discarded layouts: replace their assertions with coverage of this
contract. `src/designSystem.test.js` holds chrome to the type scale and the one
breakpoint. The core settings semantics are in
[render-mode.md](render-mode.md); update scheduling is in
[view-updates.md](view-updates.md).

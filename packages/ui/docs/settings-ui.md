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
under the file's name: Models and Files, the file explorer). RendererShell owns the scene's chrome: the tool strip and
the view's controls at its end (Projection, Display, Preview), the sub-toolbar of the tool in hand under
it, the view's panel, Quick Edit, the view cube and Preview, with Preview's own bar in the navbar's place. Renderers supply
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
  own bar in its place, in every host (see [Preview](#camera-animation-and-preview)). Left: the text-to-cad logo,
  named Menu, with no chevron: the "C" mark, 16px, in the row's 24px button, the same over the
  home and over a document (no wordmark, and nothing that changes between the two). Its left edge
  is the page's 16px gutter, over the home and over a page alike (the
  row starts 12px in, the button's padding is 4px). The logo opens the
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
  **Copy path**; **Copy link** (the document's page with a fresh link, `<engine origin>/<id>?token=<link>`,
  the address the page itself holds: on every document, model or file of any kind, always enabled,
  its source there or not; copied silently, as Copy path is; `fileActions.perform["copy-link"]`); **Open in**, a submenu of **Browser** (the document's page in the person's
  browser: the CAD app's, where a launch carried the web viewer's page, `fileActions.perform.browser`)
  and the desktop's file manager by its plain name — **Finder** on macOS, **File Explorer** on
  Windows, **File manager** on Linux (`reveal`); then, where the host has this computer's apps
  (`fileActions.apps`), in groups parted by separators: the apps that take the source (a model's
  script: Visual Studio Code, Cursor …; a file's: FreeCAD, Bambu Studio …, by their product names,
  untranslated as Finder is); each file the model's last build wrote that is on disk, its apps as
  **App (file name)** (FreeCAD (bracket.step)); and **Default app**, the OS's own handler for the
  source. A group with no item is left out with its separator, and an export whose file is gone is
  left out. The apps are asked for as the menu opens, never before: what needs no answer is there
  at once, the apps join it when it comes, and a failed or slow answer leaves the menu as without
  them. Choosing one is counted as `file_open_app`, never which app. Then the host's own items, the CAD viewer's
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
  whether it opens now and why not (`openInMenu`). No ⋯ where there is nothing. The home has no file and no ⋯. The name has
  no right-click menu and there are no crumbs. The left's controls sit edge to edge, spaced
  by their own padding alone: the logo's 24px button, Back, Forward and the ⋯ in 20px ones,
  and the name 4px in from its edges, so about 7px separate one glyph from the next. Right,
  kept clean for the update's nudge, only what a host or a file adds, in this order: first, while
  a person has put an alert card away, the card's own icon (a circle
  with an exclamation mark, red for an error and amber for a warning, named and hinted by
  the alert's title), which brings the card back and goes with it — the renderer's one
  navbar action. Then the host's own actions (`actions`): inline, where the host can show the view full size,
  **Full size** (the CAD app's: two diagonal arrows, a ghost icon button) — today the slot's
  only control. Last, outermost, the update — the blue update button (a download icon and
  nothing else, no popover), there only while the host's install is behind, which updates when
  pressed. Export and Open in are the file menu's, never here. A CAD file publishes no
  navbar action but that icon. The person's own settings, the theme among them, are never here: they are the app
  menu's.

  *Design note: the navbar carries nothing the view needs.* What a host or the file adds (the
  update, an alert's icon, the host's actions) is the navbar's right end; what can be done with
  the document (copy its path, open it elsewhere, export it) is its ⋯, beside its name. The view's own
  controls are the strip's, in every host, with or without a navbar: **Projection**, **Display**
  and **Preview** end it; they act on the whole view, whatever tool is in hand, so they are no
  tools, and a new per-file button that is no tool goes with them. In Preview, Preview's own
  controls, **Preview settings** and **Exit preview**, are its bar's. So a host may leave the
  navbar out (`chrome: "bare"`), and Preview hides it.

  A host's home has the same navbar, with only the logo and its app menu (without Back to
  files) and, where the host keeps the view's history, **Back** and **Forward** at the left
  (a desktop's alone) and, at the right end, the host's actions and, last, its update, when there is one — the same
  buttons, sizes and places as over a file. Under it,
  the page, after Figma's Recents, with no hero (no wordmark, tagline or links: GitHub and
  Discord are the app menu's, X its footer's "Made by"; no light/dark button: Theme is the
  menu's). The Home is **one type scale**: every text `text-ui` (13px) — the
  type filter, the search, the names, the table — but the heading, **Recent**, the one larger text
  (17px, weight 600), and a tile's age, `text-tiny` (11px) and
  muted; a tile's and a row's glyph is 16px (`src/designSystem.test.js` holds it). It starts
  with **one control row**, every control 24px tall with 13px text: at the
  left **Recent**, a plain heading on the row's 24px line (no fill or padding box: no tab); at the right,
  8px apart, the **type filter**, a stock DropdownMenu whose ghost `xs` trigger names what it
  shows ("All ▾") and whose radio items are All, Models and Files, there only where models and
  files are both listed; the **search**, a stock Input 24px tall and 200px wide ("Search"); and
  the **grid/list switch**, two `icon-xs` buttons, the chosen one on the `muted` fill; and last,
  where the host's computer has a file chooser (`ModelLibrarySource.pick`), **Open**, a stock
  `xs` button (24px) with the folder icon and "Open", which opens the desktop's own chooser
  (`POST /api/v1/local/pick`) and shows the file picked. Then the
  documents opened or built before, pinned first, then by last activity. The home is the
  library and Open alone: no folder of a launch. It is a **centred column**, 1128px wide at most,
  on 24px gutters of its own (not the navbar's 16px, which the logo keeps), 44px under the navbar,
  its control row 20px over the tiles: a library page's generous spacing. In the grid, a **tile** is transparent on the
  page in both themes, a 1px `border`, a 12px radius and no shadow, the same under the pointer;
  columns at least 280px (three across the full column, two at a narrower window), 24px apart. Its picture sits on the
  `muted` fill at 330:185, contained (its placeholder cube 24px); its caption is compact (8px by 12px): its kind's 16px glyph in a 20px
  column, 8px before its name (`text-ui`, weight 500) over its last activity with its verb
  ("Edited 2m ago" for a change after the last opening, "Viewed 16m ago" for an opening after the
  last change; `lib/age.ts`, `text-tiny`, muted). In the list, a **table**, one type in every cell (`text-ui`, 13px): a
  32px header row of muted labels (Name, Updated, Created) over 40px rows, each its glyph and
  name, then its `updated` and `created` ages with no verb, muted, in two 160px columns (Created dropped under a 560px page), transparent with the
  hover fill. Each has a **pin** toggle and **one ⋯ menu** (a stock DropdownMenu), shown on hover
  or focus, at a tile's picture's top-right (Figma's star) or a row's end; a pinned one keeps its
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
  top-right, first in the column of the host's notice and Quick Edit (`ViewportTopRight`): where
  the host can show the view full size, **Full size**; then, while its install is behind, the
  blue update button, the navbar's own: an icon, no text and no popover, which updates when
  pressed. In Preview it is gone with the rest of the column.
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
  same from the keyboard. A double-click opens it in the explorer's place, as a crumb does —
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
  side (it wraps before it would be): the tools, left to right, in **two sections** parted by one
  thin rule (a tool's `group`: the tools that pick, Select, Pencil, Shapes and Measure; then the
  model's effects, Explode and Clip), and, for a 3D file, **Preview**, directly after the last tool, in
  the same second section with no rule between (a file with only tools that pick has it after a rule,
  as its own second section), in every host, with a navbar or without. The strip is what you do to the
  model; how you look at it is the view's corner (**The view's corner**, below). **What goes on the
  screen is what is changed often**: a tool, Display and Projection, a board's Display (its preset), 2D | 3D and side, the zoom. What is
  changed now and then goes in the view's panel or behind a menu: a board's layers and layer display are
  its Layers tab's, Grid is Display's menu's, Zoom to selection and Zoom to 100% the zoom's menu's. 24px tiles with 14px icons,
  an even 4px apart, a tool's chevron touching its button, in a 34px row (`FloatingToolBar`,
  `data-cad-toolbar`). A file with no tools and no 3D view has no strip. On a phone
  ([mobile](#the-views-panel-and-the-tool-stack)) the tiles are 36px with 18px icons, a chevron
  20px wide, in one row that never wraps. Centre it on the viewport whenever it fits;
  clamp its position to keep 8px from the edges and, on a phone, from the panel's pill at its left.
  Its available width still uses all the room after that pill. What does not fit goes into
  **More tools** (an ellipsis, last): on a phone the view's controls are always its rows, and the
  tools that do not fit join them from the strip's end; a tool there is a row ticked while it is
  in hand, Projection's row switches the projection as its tile does, and Display's row opens its
  choices as a nested submenu (`touchStripFit`).
- **Sub-toolbar** under the strip, 8px below it, centred: the tool in hand's one row of
  controls (`SubToolbar`, `data-cad-sub-toolbar`), there for as long as the tool is up (see
  [Tools and lifecycle](#tools-and-lifecycle)). Select and Measure have none. On a phone its
  buttons are the strip's 36px tiles and its sliders as tall, the slider rows 20rem wide.
- **Tool stack** under the sub-toolbar, in the same centred column: a renderer's own
  `toolPanels`, where it hands any (see
  [The view's panel and the tool stack](#the-views-panel-and-the-tool-stack)). The column
  stops 8px above the cube's line (`VIEWPORT_STACK_BOTTOM`), so it never runs past the
  view.
- **The view's panel**, docked at the left: one search over a tab per section of what there is
  to read of the file — a STEP assembly's Model, a robot's Links, Position, an SDF's
  metadata, a drawing's Layers — whatever tool is in hand; collapsed, a pill at the canvas's top-left; on a phone the
  whole view (see [The view's panel](#the-views-panel-and-the-tool-stack)). A file with no
  section (a mesh) has none.
- **Quick Edit** at top-right, 8px in, a STEP's or a robot's: the box of the note a
  person writes to their agent, there only while something is picked, drawn or measured
  (see [Quick Edit](#quick-edit)), under the host's notice where there is one (the CAD app's
  file handler's corner: Full size and its update). The rest of the right side of the view is clear.
- **View cube** at bottom-right, its drawing (the cube, its axes and their labels) 8px from the right
  and from the bottom, as every corner control stands: its 6rem box is larger than the drawing, so the
  box overhangs the right edge by 6px and sits 2px off the bottom (`VIEWPORT_CUBE_BOTTOM`):
  enlarged face/edge/corner hit areas and neutral hover and XYZ guides. Over it, the view's corner's
  column (**The view's corner**, below). A host whose own
  control floats over that corner lifts it clear with `--cad-viewport-corner-bottom`, the
  room that control takes from the bottom edge. A host can instead anchor it at bottom-left
  with `--cad-viewport-corner-left: 2px` and `--cad-viewport-corner-right: auto`.
  Codex's tab presentation uses this for all its views to avoid the floating composer.
  Preview omits it, and so does a phone.
- **Preview** ends the tool strip, for a 3D file (`data-view-controls`, `FloatingToolBar`'s
  `views`): a play triangle, the way into Preview — a mode of the whole view, not a setting of it, so
  the strip's. It is no tool: pressing it leaves the tool in hand as it is.
- **The view's corner** (`kit/shell/ViewCorner.jsx`) is how you look at the model, at the bottom-right,
  as Blender keeps its navigation buttons with its gizmo. A **3D view's** is a column over the cube,
  flush with the cube's right face and standing on its box's top (the cube turns with the camera and
  may reach almost that high, so only the box keeps the gap under the column clear at every angle):
  **Display** (the active mode's sphere: see [Display settings](#display-settings-and-section-primitives);
  its menu opens to the left), **Projection** (the projection on screen; a click switches to the
  other, Orthographic to Perspective and back, no menu, its tooltip naming the one it switches to:
  `ProjectionToggle.jsx`), then **Home** nearest the cube (a house: the view it opened with — the
  opening direction, what is shown framed whole — as Fusion's and Maya's cubes' Home is). A **flat
  view's** has its zoom pill where the cube would stand, 8px from the right and the bottom, and its own
  view controls on the corner's **bottom row**, left of the pill (below). The corner's design
  language is its own, for navigation only, never a tool: **round** — 28px discs with 14px icons on one
  surface (`ViewCorner.jsx`'s `VIEW_CORNER_SURFACE_CLASS`): the canvas at 85% under a 4px blur, a wash
  of the foreground over it (9%, 16% under the pointer, while a menu is open and while a state is on),
  no border and no shadow. Over an empty canvas it is the canvas and the wash; over the picture or the
  model its glyphs keep their contrast and what passes under it is a faint hint. 6px apart, tooltips
  and menus to the left; the pill is the
  same disc drawn out into a capsule, the same height and fill, − and + discs either end of the
  percentage, and a board's switches the same capsule beside it, their halves side by side, the
  chosen one raised on the stronger fill. A state shows on the control itself (Projection's icon, a
  board's side). The strip's
  square tiles on the floating surface stay the tools'. A phone has no corner: its view's controls are
  rows of the strip's More (Projection, Display, the zoom's submenu, Preview; a board's View from the
  back, ticked while it is). A view drawn as a picture, or one that is loading or failed to load, has none of them. In Preview the strip is gone and Preview's own controls are its bar's (see
  [Preview](#camera-animation-and-preview)).
- **The corner's bottom row** (`ViewCorner.jsx`'s `ViewCornerRow`, `VIEWPORT_CORNER_ROW_POSITION`): a
  view's own controls for how it is looked at, side by side on the pill's line, right-aligned 6px left of
  the pill (118px from the right edge), each of a fixed width, lifted by `--cad-viewport-corner-bottom`
  as the pill is. The cube's box ends 90px from the right edge, so the row clears it by 28px: when a flat
  view shows its picture in 3D and the pill becomes the cube, not one of the row's controls moves. A
  board's row is `[Display] [2D | 3D] [Front | Back]`: Display the round button (28px), its menu opening
  up and away from the corner; the two switches capsules on the corner's surface
  (`ViewCornerSwitch`, `VIEW_CORNER_SURFACE_CLASS`, the one surface the corner's discs, pill and
  switches share), 72px and 104px wide. A host that anchors the cube at the bottom-left
  (`--cad-viewport-corner-left`) moves neither the pill nor the row today.
- **A file's routines are a playbar at the bottom centre**, in the tools view (on a phone over
  Quick Edit's peek) as in Preview, one transparent row on no surface, the same row in both;
  the tools view's Reset is an item of its Playback settings (see
  [Preview](#camera-animation-and-preview)). Nothing else sits there.
- **Model update status** sits under the strip and its sub-toolbar, centred, and where
  there is no strip (Preview, a compact view, a load) at the top centre, in the strip's
  34px row, in every host. It is renderer chrome: the navbar carries no status. On mobile
  it is a tappable progress icon whose popover names what is loading.

## Tools and lifecycle

| File | Tool strip, left to right |
| --- | --- |
| STEP | Select, Pencil, Shapes, Measure; Explode (two or more parts), Clip, Projection, Display and Preview |
| URDF / SRDF / SDF | Select, Pencil, Shapes, Measure; Clip, Projection, Display and Preview |
| GLB | Select, Pencil, Shapes, Measure; Explode (several rigid nodes that draw), Clip, Projection, Display and Preview |
| 3MF | Select, Pencil, Shapes, Measure; Clip, Projection, Display and Preview |
| STL | Select (in hand, the view's navigation: an STL picks nothing), Pencil, Shapes; Clip, Projection, Display and Preview |
| DXF | Select (in hand, and the view's hand: a drag pans, a tap picks an entity), Pencil, Shapes, Measure; no view controls: a drawing is 2D |
| KiCad board | Select (in hand, as KiCad's: a click picks what its filter ticks, on a layer the Display draws, a click on nothing clearing; a drag draws a box, the area on the view's working layer; the rest are the 3D views' drags: a right or middle drag, or a drag with Ctrl, Cmd or Shift, pans, as a trackpad's two-finger scroll does, a mouse's wheel and a pinch zoom, a double-click fits: the board whole, 6% of the pane’s smaller side clear round it (16px at least) and clear of the strip, as it opens and as its snapshot frames it), Pencil, Shapes, Measure; the corner’s Display, 2D \| 3D and Front \| Back |
| KiCad schematic | Select (in hand, as a board's: a click picks what its filter ticks, a click on nothing clearing; a drag picks what lies wholly inside the box, KiCad's window selection; a double-click on a sheet symbol enters its sheet, anywhere else fits: the page whole, with a board's margin and clear of the strip), Pencil, Shapes, Measure; no view controls (no layers, and its colours are the theme's). |

There is no activity dot. A thin rule parts the tools from the view's controls, which
are no tools (see [Ownership and layout](#ownership-and-layout)). Position is no tool:
its knobs are Select's, while Select's filter picks Position, and its controls are a
tab of the [view's panel](#the-views-panel-and-the-tool-stack); the file's routines play from the
playbar under the model (see [Preview](#camera-animation-and-preview)). A file with no tools
and no 3D view has no strip at all.

**A tool the file cannot offer is not on the strip**: never shown disabled.
Renderers leave it out of the `tools` they hand over; `FloatingToolBar` draws
what it is given. Until a file has loaded, what it offers is not known: a tool
that depends on it (Explode) is shown idle meanwhile, a robot's filter offers
Position meanwhile, and the whole strip is disabled while loading. Unavailable and
idle are different states.

One tool owns pointer input, and it alone is lit on the strip. **A press on the tool in hand
does nothing**: a tool is put down by taking up another (Select, most often), or by Escape, which
takes Select up. **Explode and Clip are no tools**: like Projection and Display, each is a
popover from its tile, its row under its button — opened by a press, closed by a press away
from it (a press on the model is a pick as well), by Escape or by its button again — and its
button has no pressed state, whatever is in hand. What it sets stays on the model once the
popover closes, until its Reset, as a Display setting does: an explosion, a cut, like a pose,
has nothing on screen for it but the model and the dot in its tile's corner (`ChangedDot`).
Opened again, it is as it was. Preview's tile alone is a mode.

| Tool | Pressing it | Its sub-toolbar | Leaving it |
| --- | --- | --- | --- |
| Select | The default tool of every 3D file but an STL; picks what its filter ticks, or a GLB's nodes, a 3MF's objects (Shift adds; Delete deletes annotations and measurements); what is picked is Quick Edit's chips | None: its filter is the chevron after its button | The selection stays, lit and in Quick Edit, under any tool |
| Pencil / Shapes | Draws on the view: Pencil with the pen, the highlighter or the eraser, Shapes with the rectangle, line, arrow, ellipse or text; each button is the tool last chosen in it | One row for both: the tools of the one that is up, then Color, Stroke width, Placement and Clear annotations (Undo and Redo are ⌘Z, ⇧⌘Z) | The annotations stay in the model, their chip in Quick Edit; each tool keeps what it draws with, the strip showing its icon |
| Measure | Arms picking two entities and reading what the pair makes (an engine document's — an `.xbf`'s or a STEP's — exact vertices, edges and faces, what its filter ticks; on a mesh, two points on its surface, approximately, in its file's unit; a drawing's ends, centres and lines, in the unit it declares, else "units"); each result a chip in its colour | Its measurements, as chips, then Clear measurements; none while nothing is measured | Unfinished picks are cancelled; completed measurements stay, drawn on the model, their row back with the tool |
| Explode / Clip | No tool: opens its popover, the tool in hand kept; an edit applies the effect (Explode's, as a motion: see below) | None: its popover is the row it was (the slider, its amount beside it, Reset; Clip's axis first, whose dropdown holds its settings) | Closing the popover leaves the effect on the model |

**One motion at a time.** Every tool's state stands beside every other's — the selection,
measurements, the annotations, Clip — except the two that move the parts: **Explode** and
the **Position** pose. They replace each other: exploding puts the pose back at its
default, and using Position (a knob dragged, a value set or a named pose chosen) takes
Explode off, with nothing set aside to come back. While the model is exploded there are no
knobs. Its popover closed, the explosion stays under every tool until Position is used. A
routine played from the playbar is the third motion: playing it puts Explode and the
pose back at rest, and using either puts the routine back at rest; paused, its frame stays on the
model as a pose does. Preview's routine is its own and moves nothing of the tools view's.
Another file has the motions its tools have, under the same rule, decided by value
(`kit/tools/model-effects/motionExclusion.js` for a GLB and an engine document; the robot
renderer's own rule, `RobotRenderer.jsx`, for a robot): a GLB's Explode, routine and Clip; a robot's
Position and Clip; an engine document's Explode, Position and its motions (its **Motion**
section, where Position shows a motion's frame read-only while it owns the pose).

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
context menu, and the playbar's routine and Playback settings (`PlaybackMenu.jsx`, on
`ToolPopover`). Preview's settings are a panel, not a dropdown (see [Preview](#camera-animation-and-preview)).

**Select's menu** (`kit/tools/select/SelectFilterMenu.jsx`) is a CAD tool's selection
priority (Fusion's Select > Face Priority, Blender's vertex, edge and face modes), not a
checklist: the chevron's dropdown, headed "Pick", lists ONE choice of what a click on the model
takes, each with its glyph — **All** first, the default, then each kind alone. Choosing
one puts the menu away and takes Select up. An `.xbf`'s and a STEP's (`XbfSelectionModes.jsx`'s `xbfSelectModes`):
**All** (the pointer: a face or an edge where a part's are loaded, the part elsewhere,
Position's knobs, the annotations and the measurements), **Parts** (a whole cube; an assembly's
only — in a part file a press that reaches no face or edge picks the whole part), **Faces** (a
faint cube, its top face filled), **Edges** (a faint cube, one edge heavy) and **Position**
(where the file has joints to move: its knobs alone, the model picking nothing). A robot's:
**All**, **Links** and **Position** (where a joint can be driven; a robot with nothing to
drive has no menu). The annotations and measurements are no choice of their own: they are drawn
over the model, so a click on one is never taken for the face under it, and a kind alone (Faces)
picks that kind only. All is chosen when a file opens; the choice holds while the file is
open, across updates of it, and another file starts on All. The chevron's name says what
is chosen ("Selection filter: everything", "Selection filter: Faces"), and Select's button wears
it as a badge on the pointer (`modeGlyphs.jsx`'s `ToolModeIcon`; none for All), so what a
click takes is on the strip, not only in the menu. After a rule, an `.xbf`'s menu ends in how a face
or edge pick grows, each with its glyph and independent of each other: **Group edges** (the
connected edges with a picked edge), shown while edges are picked, and **Group faces** (the
smoothly joined faces with a picked face), shown while faces are; a hidden one keeps its choice
for when it shows again.

**A board's filter is KiCad's Selection Filter** (`board/BoardSelectFilter.jsx`), the one
Select filter that is a checklist, because KiCad's is: the chevron's dropdown, headed "Pick",
holds a grid of stock checkbox items in KiCad's two columns, row by row — **All items** and
**Locked items**, **Footprints** and **Text**, **Tracks** and **Vias**, **Pads** and **Graphics**,
**Zones** and **Rule Areas**, then **Dimensions** — each its name alone, with no glyph (KiCad's
boxes have none), and its check at the row's right end. Ticking a box leaves the menu up (a press on the board puts it away) and takes
Select up. All items ticks or unticks every kind, and shows a dash while some are ticked; Locked
items is no kind: ticked, a click takes what KiCad saved locked as well (a pad is taken whatever
its part, as KiCad's single click), and it is unticked as a board opens, as KiCad's. Every kind is
ticked as a board opens; the filter holds while the file is open. A click takes the most specific
thing the boxes tick (`board/boardPick.js`): with Footprints ticked a footprint's graphics are its
part's; with the zones alone a zone is taken anywhere inside it. KiCad's Grid Items, Points and
Other items have no box: the board's index holds none of them. A whole net is picked from the panel's
Nets, not by the filter. The chevron's name says what is ticked ("Selection filter:
everything", "Selection filter: Pads, Vias"). Select on a board has no modes: a click picks and a
drag draws a box, the area it names (KiCad's window selection, a translucent rectangle as it is
dragged); every other drag is the 3D views' (`useViewerRuntime.js`'s OrbitControls, the left
button's orbit being the box): the right button's drag pans (a Mac trackpad's two-finger click and
drag), as does the middle button's and a left drag with Ctrl, Cmd or Shift held (a Shift click still
adds), and so does a trackpad's two-finger scroll, as Figma's does; a mouse's wheel, a wheel with
Cmd or Ctrl and a pinch zoom (`kit/viewport/wheelGesture.js`); the browser's menu is kept off
the board, as off a 3D view.

**A schematic's filter is KiCad's too** (`schematic/SchematicSelectFilter.jsx`, over the kit's checklist the
`kit/tools/select/SelectFilterChecklist.jsx`, a board's too): **All items**, then **Symbols** and **Pins**, **Wires** and
**Labels**, **Sheets** and **Other items** (junctions, no-connects), each its name alone. A click takes
the nearest ink, and of what is about as near the most specific — a pin, a junction or a no-connect, a
label (a sheet pin, its net), a wire, a field (its symbol) — then the symbol body or sheet symbol it is
inside. A whole net is picked from the panel's Nets.

The geometry chosen is picked as one mode (`xbf/xbfSelectionFilter.js`'s
`selectGeometryMode`): All, a press takes the face or edge it lands on where the part's
topology can be picked, and the part elsewhere; Parts, the part; Faces or Edges, that topology
alone. The mode sets the model tree's shape: under All, or Position (no geometry at all),
it is the person's own (put back as it
was when they left it, with the owners of what is still selected kept open); Parts alone
opens every assembly and shuts every part; Faces or Edges open every assembly. A
part is a leaf in every shape: nothing opens under it, and a face or edge picked in the
viewport is revealed at its part's row. Outside the person's own shape the disclosure is
locked (chevrons shown, not pressable) and Expand/Collapse leave the row menus. Every face and
edge is to hand from the start: nothing waits on a part's topology.

**Sub-toolbars** (`kit/tools/SubToolbar.jsx`): the tool in hand's controls, one row hung
under the strip, centred, 8px below it, on the strip's surface, its buttons the strip's
24px tiles, its groups — what the tool does, then how it looks and what clears it — parted by a
thin rule. It stays up for as long as its tool does, and has no heading: the tool's lit
button above names it. Explode's and Clip's rows are the same component in a popover under their
own tile (`model-effects/ModelTools.jsx`'s `EffectPopover`, shadcn's Popover as it ships, the row
bringing its own surface), never under the strip: one shape — the
[slider control](#the-slider-control) on one line (what leads it, its slider, its value), the
tool's actions (neither has any), then Reset, last, at the same spot in both, with no rules — and
one width (`SLIDER_SUB_TOOLBAR_CLASS`, 202px; a phone's 320px). The slider takes the rest of the
row. A tool's options never sit in the row as checkboxes, labels or
buttons of their own, which would squeeze the slider: they are the dropdown of what leads it
(Clip's axis).

**Pencil and Shapes.** Drawing is two plain strip tools, a button each, with no chevron and no menu:
**Pencil**, drawing with the **Pen** (the freehand ink, tapering with pressure or
speed), the **Highlighter** or the **Eraser**; and **Shapes**, with the **Rectangle** (what it opens on), **Line**, **Arrow**,
**Ellipse** or **Text** (a mark put down in place). The tool's button shows the icon of what it draws with
now, and a press takes up the one last chosen. Pencil and Shapes share the annotation and its history, whichever is up, but not the style: the colour, stroke width
and placement are kept **per drawing kind** — the Pen, the Highlighter (which opens in neon yellow) and Shapes (all five
shapes share one) — and the row shows and sets the tool in hand's own — and **one sub-toolbar**,
"Annotation controls" (`annotation/toolbar.jsx`'s `AnnotationToolbar`), a single row, never a
second, from the left: the **tools of the one that is up**, a button each, the one in hand pressed (with Pencil up, Pen,
Highlighter, Eraser; with Shapes up, Rectangle, Line, Arrow, Ellipse, Text: choosing one is how the strip tool changes what it
draws with); a thin rule; then what is drawn next, each a dropdown whose button shows its value, no
chevron: **Colour** (no heading, a grid of swatches, unnamed but for assistive technology: the neons and
one neutral that reads against the viewer, white in dark mode and near-black in light, then
the colour wheel, which opens the system's colour picker for any other colour, kept once the
picker closes), **Stroke width** (no heading, four weights, 1, 2, 4 and 6px, the pen drawn to look the
same weight; on the button and as each row, a straight line drawn at that weight, unnamed but for assistive
technology, the current one checked) and **Placement** (laid out as the strip's menus are: headed with its name, a
row per choice, the check on the right: **On surface**, the default, its glyph a sphere: each point of the next mark on the visible
surface under it; **On plane**, its glyph a sheet: the whole mark on the plane of the surface it
starts on; a flat view, a DXF, has none); then **Clear annotations** (the trash), disabled while there is
nothing to clear. Under the **Eraser**, which draws nothing, Color, Stroke width and Placement are disabled (greyed out, still
on the row so it does not jump). Undo and Redo have no buttons: they are ⌘Z and ⇧⌘Z (Ctrl+Z, Ctrl+Y). The row is the same row for both tools at every width; on a phone its
buttons are 36px tiles and, where the row is wider than the view, it wraps rather than scrolls (there is no second menu on
the strip for it). The **Highlighter** draws a freehand stroke like the pen's, but broad and translucent: five times
the chosen stroke width, 35% opaque, round at its ends, with no pressure taper; it is an ordinary stroke, picked,
erased and recoloured as any (its Stroke width in the selection's bar is the same setting). The tools have no Select or Pan of their own (Select picks
annotations, a right drag or Space orbits). Never a restyle of ink already down: the
annotations Select picks have their own bar, a small floating toolbar on the tool strip's
surface just above them — Color and Stroke width dropdowns, Fill for a closed
shape, a rule, Delete. An update of the model forgets the annotations too, their history with
them (Undo has nothing to bring back), and leaves the tool in hand, with its tool, colour,
weight and placement. The pen and the shapes share one default stroke
width. The annotations have no panel: while there are any they are Quick Edit's
**Annotation** chip (its X clears them), and while Pencil or Shapes is up the copy shortcut writes
the view with its annotations to the clipboard as a PNG. A first stroke opens
[Quick Edit](#quick-edit), whose header says **annotation** while there is ink. The drawing tools
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

**Explode and Clip** have no enabled checkbox, and their rows are drawn alike, each in its popover.
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
choosing in it, or Escape closing it, leaves the popover open. They are settings of the
file's view (`clip.axis`, `clip.partColors`, `clip.invert`, stored and restored with its
display), kept as the popover closes and by Reset clip. Explode opens at 0%, Clip at no
cut; an edit applies the effect, and the slider back at zero removes it. An axis alone is not
an effect. The view settings own both effects, so a mode reset preserves them and a restored
effect reappears on the model. Clip's slider, left to right, cuts deeper through the original
bounding box; pose, animation and Explode never redefine the range. It shows the share cut
away, while the view stores where the plane stands (`clip.at`, in millimetres), so a model
edit leaves the plane where it was and the slider reads 0% or 100% if the plane ends up
outside the new box. Explode is offered only where there are parts to separate: a STEP
assembly and a GLB of several rigid nodes. A STEP part file has no Explode tile, as it has no
Model (`STEP_PART_VIEW_FEATURES`).

## The view's panel and the tool stack

**The view's panel** (`kit/shell/FlatPanel.jsx`; a board's and a schematic's `FlatViewFrame.jsx`, a
3D view's `RendererShell.jsx`, a drawing's `DxfRenderer.jsx`, one state, `useFlatPanelState`) holds what there is to read of the
file, whatever tool is in hand, after KiCad's Appearance panel: docked at the view's left edge, the
full height of the view, on the chrome's colour (the navbar's, `bg-sidebar`: a step off the canvas,
`bg-canvas`, the content area behind every view, 2D and 3D, which sits darker than the chrome in
both themes, as Figma's, VS Code's and Linear's canvas does)
with a rule at its right, and the canvas the narrower for it: open, at any width, it takes its
width out of the canvas, and the picture is drawn in what it leaves, nothing of it under the panel
(a phone's whole-view page aside). The strip stays at the view's centre,
panel open or not, and stands over the panel where a narrow view makes them meet, as Figma's toolbar
stands over its layers; its reach is written before the frame is painted, so opening or shutting the
panel never moves it, `kit/shell/useStageReach.js`. Its tabs: a board's Parts, Nets and Layers, a schematic's Parts, Nets and Hierarchy,
a drawing's Layers (handed in); a 3D view's its renderer's sections in their order (`ToolPanel`s, each a tab by its
name: a STEP assembly's **Model** — a part file, whose tree would be its one row, has none —
then **Position**, where the file has joints to move; a robot's **Links**, an `.sdf`'s **SDF**, then
**Position**), Position's Reset on its pose row and the Model's Show all on a line over its rows,
and the trees searched by the panel's search box. A file's routines are no tab:
they play from the playbar under the model. A mesh, with no section, has no panel, and nor has a
drawing with nothing for its Layers to say (fewer than four layers drawn on and no block
reference: a flat pattern's CUT and BEND). The strip is for using tools, the panel for reading the
file.

- **Its head.** The search box filling the row (`TreeFilterInput`, dense, in a 1px border), its
  placeholder "Search" in every file, its accessible name what it searches ("Search the board",
  "Search the schematic", "Search the drawing", "Search the model"); then **Hide panel** at its
  right (lucide's PanelLeftClose, its tooltip naming ⌘\ or Ctrl+\). Its inside is a row's: the
  search icon a row's 12px glyph in the rows' glyph box (16px in, 8px inside the box), its text on
  the rows' labels' line (32px), the clear button a row action whose glyph ends 8px inside the
  box's right edge; a phone's 16px glyphs keep the same anatomy.
- **One tab is no tabs.** A panel with a single tab (an assembly's Model with nothing to Position, a
  drawing's Layers, a board read without its index) draws no row of tabs and no name over its search
  hits, and no rule: the rule goes with the tab row, so its list starts 6px under the search box. The
  list is labelled by the tab's name for assistive technology.
- **Its tabs**, under the head, buttons as Figma's: 24px, the open one on the accent in medium
  weight, the others muted, each as wide as its name in medium weight, so choosing one moves nothing; a board's **Parts**, **Nets** then **Layers**, a schematic's **Parts**, **Nets** then, for more than one
  sheet, **Hierarchy**. Arrow keys move between them. The tab shown is the person's, by the kind of
  file (`toolStack.tabs`), the first at first. Every tab stays mounted, and each keeps its own scroll.
- **Two lines, the same on both sides** (Figma's). Every box in the head and the lists — the search
  field, the collapse button, a tab's button, a row's background, a full-width control (Position's
  pose dropdown, the Model's status lines) — stands 8px from each edge. What is read in them stands
  16px in: the search icon, a tab's name, a row's first glyph, a heading, a layer group's name, a
  status line ("12 matches"), a settings label; a settings control (a Select, a value, a checkbox)
  ends on the 16px line at the right, as a row's last action's glyph and a right-aligned value do. A
  labelled setting's control stays in its column. The panel owns both lines: its head, body and
  detail pad 8px, and it sets the rows' `--tree-row-pad` (8px) and `--tree-row-actions-pad` (6px),
  which the one row reads (`FlatPanel.jsx`, `primitives/tree-row.jsx`); no tab, list or section
  pads itself. Every rule runs the panel's width. A settings row's label column is 4rem (its labels
  are short words) and its control fills the rest (`FileSheetSettingRow`).
  The navbar's logo stands on the same 16px line: its drawn mark, not its image's edge.
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
  double-clicked (on a phone, whose page gives the view back, a press frames it). A row's chevron
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
- **Selected** (`kit/inspector/CircuitDetail.jsx`, `FlatPanel`'s `detail`; `boardTree.js`'s
  `boardSelected`, `schematicTree.js`'s `schematicSelected`), as a CAD tool's Properties panel: under the
  lists, whatever tab is open, at a height of its own whatever it shows (320px at first, or half the
  panel where that is less: room for a pick's facts and half a dozen of what it is connected to, whatever
  the window's height; its top edge is the grip that sizes it, kept across files as
  `toolStack.panels.flatDetail`, never under 96px, the lists keeping 160px over it), scrolling on its
  own. First **what it is** — its
  glyph and name (`C17.1`, `VBUS · track`), a line in words for a pad or a pin ("Pad of C17 · 100nF"),
  and its facts (its net, layer, width, drill, value, footprint, position: a Quick Edit chip card's) —
  then **what it is connected to**: a part's own pads or pins, each its net ("Pads of C17"); a net's pads
  or pins, each its part ("Pads on net VBUS"); a pad's, a pin's, a track's, a via's, a pour's or a
  wire's net's pads or pins ("Connected to VBUS"), itself lit there. Several picked: how many, and each
  of them. A text, a graphic or an area has its facts alone. A row selects as a press on the picture
  does and a double-click frames it; the head's name selects it again. Nothing picked: none.
- **A hover tip** (`kit/shell/HoverTip.jsx`): under Select, the name of what the pointer rests on — a
  pad's or a pin's with its net, a part's with its value — in a small tip beside it, once the pointer has
  rested on it a moment (450ms), gone the moment it leaves; it takes no pointer.
- **The Layers** (`board/LayersSection.jsx`), a list as Altium's Layers panel is: the layers, grouped
  Front, Inner, Back, Other, each its colour, name, count and eye, a press on a board layer's row
  making it the active layer (a filled dot after its name), drawn on top. How the board is drawn is
  the strip's (below), not the panel's.
- **A drawing's Layers** (`dxf/LayersSection.jsx`): each layer drawn on, in the drawing's order, its
  pen, name, entity count and eye (hidden: not drawn, picked or snapped to), and under a layer the
  block references placed on it, open, a press on one picking it as a tap on the drawing does
  (Shift adds). Every layer row is two glyphs, so none starts on a gap: its slot holds its chevron
  where blocks hang under it, else a layer's icon (lucide's Layers, as light as every kind icon),
  and the box after it its pen; its name 48px in (16, the slot's 12, 4, the pen's 12, 4), always,
  whether or not any layer has blocks. A block reference's row stands in line with its layer's: its
  slot only the layer's guide, down the chevron's middle; its box its block's glyph, under the pen;
  its name and handle under the layer's name and count. Searching, the layers whose names match,
  and the blocks whose names do under their layer.
- **A board's view controls on the screen** (`board/BoardDisplay.jsx`'s `boardViewControls`), changed
  often, so on the corner's bottom row, left of the zoom pill or the cube, the same in 2D and 3D:
  **Display**, the round corner button every 3D view has for it (`kit/shell/DisplayPopover.jsx`, its
  menu the presets as one radio group — Board, Copper, Assembly, Placement — the one on screen ticked,
  and Custom, ticked and not a choice, while the Layers tab's eyes have left the preset's set);
  **2D | 3D** (below, [A board in 3D](#a-board-in-3d)); and the **side** (KiCad's View ▸ Flip Board View):
  **Front** and **Back** side by side, in KiCad's words, the side the board is seen from raised, a press
  on the other flipping it; from the back the board is mirrored, its back layers on top. The rest of how a
  board is drawn is changed now and then, so it is the Layers tab's, as KiCad's Appearance panel has it,
  in the settings form's rows: under the layers, **Layer display**: **Others** (KiCad's high-contrast
  modes, a Select: every layer but the active one **Shown**, **Dimmed** or **Hidden**; the outline, and
  with a copper layer active every drill and via through it, stay at full strength; **Ctrl+H** (⌘H)
  cycles them while the board has the keyboard), **Pours** (a checkbox, while copper is drawn), and
  the **Zones**' (60%) and **Tracks**' (100%) opacities, each the [slider control](#the-slider-control). On a phone the three are rows of the strip's More: Display a submenu of the presets, 3D view and View from the back ticked while they are on. All of it is the board's Display (`plot2d/boardDisplay.js`), which `cad kicad_pcb
  snapshot --display` draws too. A schematic has none: its colours are the theme's.

- **The Hierarchy** (`schematic/SheetsSection.jsx`), KiCad's Hierarchy Navigator: the root (by its
  file's name) and the sheets each places, in page order, each row its page number, every sheet open,
  the sheet shown lit; a press on a row shows that sheet, the way back up from one entered.
- **Search is the panel's.** What is typed searches every tab: the tabs step aside and the body lists
  each tab's hits under its name — the layers or sheets whose names match first, then the Parts' and
  the Nets' ranked hits (the arrows and Enter walk and pick the open tab's, else the first list's) —
  a tab with none left out, and one line when
  nothing matches. Escape or the box's X clears it and the tabs come back.
- **Collapsed, it goes whole.** **Hide panel** takes it away and leaves **Show panel** (lucide's
  PanelLeftOpen) alone on a pill at the canvas's top-left, 8px in, on the strip's surface. No rail, no
  hover reveal, and a pick on the picture never opens it.
  ⌘\ (Ctrl+\) shows and hides it, and / opens it with the keyboard in its search, while the view has
  the keyboard. Docked, open or collapsed is the person's (`toolStack.collapsed.flat`), and so is its
  width (`toolStack.panels.flat`: 216px at first, 200px to half the view, from a grip on its right
  edge, Left/Right by 16px).
- **Open, it is always docked**: the canvas is the narrower for it, at any width; it never covers
  the picture. Showing or hiding it is a resize of the canvas, as a 3D viewport's: a view still at
  its fit refits to the room it has now, and a view the person has moved keeps its zoom against
  the fit and the point of the picture at its centre at the centre of the room left
  (`kit/viewport/useFlatCanvasView.js`, a drawing's `dxf/useDrawingView.js`). Zoom to fit and 100%
  measure the room beside the panel. Under 1024px of
  view it starts collapsed (not kept); opened, it docks as it does on a wide view. **On a phone**
  (under 600px) the pill is a touch tile at the left of the strip's line, and the panel opens as the
  whole view, **Back to the view** before its search; a row pressed closes it, the pick made, and
  Quick Edit's sheet keeps the bottom. There its text is one size (13px, the Display menu's), its
  search a 36px field and its tabs 32px, its tree rows 36px with 16px glyphs, its dropdowns and
  value fields 32px and a joint's row 44px (`globals.css`, `[data-flat-panel="page"]`).

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
- **One grip, on a resizable panel only**: its bottom-right corner, Quick Edit's grip, moving
  its width and cap at once, a separator in the tab order named after its panel (Left/Right
  nudge the width and Up/Down the cap by 16px, Home and End take both to their bounds). A folded panel has no grip: there is no height to set.
- **Never past the viewer.** The column stops 8px above the cube's line
  (`VIEWPORT_STACK_BOTTOM`, `calc(6rem + 16px)`). When the panels need more, a `"tree"` panel
  gives way first, down to 128px or its content, then the `"details"` panels together, each in
  proportion to its height, down to 96px or its content; a `"fixed"` panel keeps its height.
  If what cannot give way still does not fit, the column itself scrolls — a panel is never cut.
- **Headings.** A panel's heading row reads as Display's section headings do (11px, regular,
  `TOOL_PANEL_HEADING_TEXT_CLASS`), 28px tall, 8px in: a title, a summary where there is one,
  then at its right end its own actions, the chevron where it folds (up while open, down while
  folded) and an X where it has something to remove. Every small button in a heading is 20px,
  2px apart and 4px from the edge.

- **Surfaces.** Three, defined once (`lib/floatingSurface.js`), each the popover's colour (a step
  off the app's background, lighter in the dark theme) with one border, nearly opaque, so chrome
  reads over any canvas — a flat view's, which is the app's own background, and a 3D scene's alike:
  the tool strip, its sub-toolbars, the stack's panels and a collapsed panel's pill share
  `FLOATING_CHROME_SURFACE_CLASS` (90%, a small blur, a medium shadow); Preview's settings panel,
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

**The one row.** Every list of the view's panel — the Parts, the Nets, Selected's, the Hierarchy, a
board's and a drawing's Layers, the Model, the Links, every search hit — is ONE row,
`TreeRowSurface` (`primitives/tree-row.jsx`), and the row alone sets its horizontal geometry, so a
fix to it lands in every list. In the panel's numbers (216px wide, its body padded 8px):

- **The box**: 24px (36px on a phone), the background 8px from each edge, its radius and its hover,
  selected and cursor fills; 11px text (`dense`).
- **The slot**: its first child, always (`TreeRowGlyph`): 12px wide (a phone's 16px glyphs widen
  it), its glyph centred, its left edge on the search icon's, 16px in, and 10px further a level
  (the row's padding: `--tree-row-pad` plus 10px a level, from its `depth`). It holds a branch's
  chevron, the button that opens or shuts it (`TreeRowToggle`: a block's, whose name is that
  button, the pointer's alone; a locked one a mark at half strength), or the row's own glyph — its
  kind's light icon, a layer's colour, the robot's anchor — or only a guide, or nothing: a leaf
  keeps its slot, so every name in a list stands on one line. A list that needs a colour as well
  (a drawing's Layers) draws a second 12px box 4px after the slot.
- **The name**: 4px after the slot (or the box), the label 11px and first to truncate, its detail
  10px and muted 4px after it, ending 8px before the row's end (`TREE_ROW_NAME_CLASS`). A row's
  first name stands 32px in (48px in a drawing's Layers).
- **The guides**: a faint line under each owner's slot, drawn by the row from its `depth`, its full
  height, so the rows under an open branch draw its line unbroken.
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
text, and iOS Safari zooming into any field under 16px): type 12, 13, 14 and 15px for `text-micro`,
`text-tiny`, `text-xs` and `text-ui`; text entry at the panel's own size (the page's viewport,
not a 16px font, stops a phone zooming in on a field); menu, select and tree rows 36-40px; the
navbar, and Preview's bar in its place, a 48px row of 36px controls; the strip and the sub-toolbars 36px tiles (the strip one row,
**More tools** holding what does not fit; the drawing tools' row the same single row, wrapping where it must — Shapes' does
at 375px, its style group under its tools, and a row that wrapped draws no rule between its groups, the line
break parting them, `SubToolbar`'s `data-wrapped`). An SDF's counts are two tiles a row in a phone's panel (three on a desktop), so
their labels read whole.
The scale is set once, in `globals.css`, for the whole page while a phone's view is on it, so a
portalled menu, select or hint is the same size as the chrome it opened from. There is no view
cube; the view's panel is a pill at the strip's left, opening as the whole view; and
Quick Edit is a bottom sheet (see
[Quick Edit](#quick-edit)). The explorer is the same popover, never wider than the window less
1rem. The shortcut hint is hidden.
Touch works for every tool: one finger orbits, two pan and
zoom, a tap picks; a pinch, a cancelled pointer or a camera drag is never a
pick.

### A board in 3D

**2D | 3D** shows the same view of a board in 3D (`board/Board3dView.jsx`, a lazy chunk): the board as a
slab cut to its outline, its two faces the 2D drawer's own pictures of the two sides, in the Layers
tab's Display and the view's theme, on the 2D canvas's colour. It is the view's other canvas in the same
frame (`FlatViewFrame.jsx`), never another view: the strip, the panel and its tabs, Quick Edit, the
selection, the ink and the measurements are the same mounted components, with the same names, in both;
the one change is the corner, whose zoom pill becomes the 3D views' cube with their Projection and Home
over it (`ViewCubeColumn`, every 3D view's). The key **3** switches, as KiCad's Alt+3 opens its 3D view.

| Control | In 3D |
| --- | --- |
| Select: a click, Shift, a click on nothing | the same pick where the pointer's ray meets the face it enters, from that side, with the same filter and the layers that side draws |
| Select: a drag | turns the view, as in every 3D view; naming an area is the 2D view's, and an area named stays selected and drawn |
| Pencil, Shapes | the same ink, laid on the face the camera sees; ink drawn in either mode shows in the other |
| Measure | the same snaps and measurements, on the board's plane, drawn through the camera |
| Hover tip, the context menu, double-click | the same; the menu's groups are every view's; a double-click on nothing fits |
| Display, the Layers tab | the same Display: both faces redraw |
| Front \| Back | turns the camera over about the board's upright axis, eased; follows the camera when it is turned over by hand |
| Zoom pill | replaced by the cube; the zoom's keys (F, + and −, ⇧1, ⇧2, ⇧0) are the 3D views' |
| Projection, Home | the 3D views' own |
| A panel shown or hidden | the canvas takes what the panel leaves, the camera centred in it; the strip stays at the view's centre |

Entering 3D opens head on, on the window the 2D view shows, from the side it shows, and eases to Home
(or to the camera the file was left at in 3D); leaving frames the 2D view on what the camera was centred
on, from its side. Which is up, the 3D camera and its projection are the file's view (`board3d`). The
library card's picture is the flat board in either mode. On a phone, **3D view** is a ticked row of More.

## Display settings and section primitives

Display is not a tool. Its tile ends the strip after the strip's rule, between Projection and
Preview, and shows the current mode's sphere icon. It opens a stock shadcn dropdown menu
(`DisplayPopover.jsx`): a muted **Display** label, the modes as a `DropdownMenuRadioGroup`,
a separator, then **Grid**, a `DropdownMenuCheckboxItem`. On a phone the strip's **More**
menu has a Display row whose nested submenu is the same list (`DisplayMenuItems`), with no
label. Checks sit at the row's right end. Choosing a mode closes the menu; ticking Grid
toggles it and leaves the menu open (`onSelect` prevents the close). Clicking outside or
pressing Escape closes it. Opening it leaves the active tool and its controls in place. A
DXF view has no Display or Preview control. A native KiCad board has none on the strip: its view
settings are its corner's side and its Layers tab's preset and layer display (see [A flat view's panel](#the-views-panel-and-the-tool-stack)),
and it has no 3D Projection or Preview. It follows the theme as every view does: the app's own canvas
(white, or the neutral dark grey) and a palette for it (`plot2d/theme.js`: KiCad's default colours
on the dark one, the same hues darkened to 3:1 on white on the light one), its highlight, hover and
net dim with it (`board2d/boardOverlay.js`), and its layer swatches; a switch of theme draws it
again in the browser, from the payload it holds.

A 3D view's Display is a choice of mode and the Grid switch, and nothing else: a mode has no settings
of its own, and there is no settings page. The modes, in order, are **Solid** (shaded with
the model's CAD edges, the default), **Shaded** (no edges), **Parts** (Solid with each part
its own colour), **X-ray**, **Hidden line** and **Wireframe**, filtered by the view's
injected capabilities (`viewFeaturesForKind`, `@cad/core/common/viewSettings.js`; the
rows and icons `DisplayModeOptions.js`): a STEP assembly
offers all six, a STEP part file all but Parts, and a file without CAD edges (STL, 3MF, GLB,
a robot) Solid, with Parts when it has several parts, objects or links. **Grid** draws the
measuring grid in every mode, off by default. Each row has its icon, the sphere drawn as the
mode draws a model (and a tile of floor grid for Grid). Render is no display mode: Preview
draws the model in Render whatever the file's mode, with its own settings (see
[Preview](#camera-animation-and-preview)). Per-file storage keeps the mode and the grid;
old-shaped stored display settings are dropped setting by setting, never migrated.
Projection is a menu of its own, shared, orthographic by default; Preview's Render resolves
to perspective while preserving the shared choice.

Preview's settings panel (`PreviewSettings.jsx`, its body `PreviewRenderSettings.jsx`) is
the one settings form: Orbit, then Render's Part colours, Lighting, Background and Floor.
It shows all groups under static section headings and dividers, with no collapsible
sections or cascading settings menus. A heading is 24px of regular `text-tiny` in the
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

Type comes from the token scale only (`text-micro` 10px, `text-tiny` 11px,
`text-xs` 12px, `text-ui` 13px, a phone's a step up: see [mobile](#the-views-panel-and-the-tool-stack));
no pixel font sizes. Settings controls and the
menu labels use `text-tiny`, regular weight;
panel headings use `text-tiny` (11px) too. Sections use 8px gutters and bottom insets
and 4px row and column gaps. `FileSheetFieldGrid` owns horizontal spacing; its
children never pad again. Menu, select and context-menu typography comes from
the primitives, portals included. Selected values show their icon where it
means something.

Use the slider control for a useful bounded range, `FileSheetNumberProperty` for other scalars,
`FileSheetColorProperty` for color with opacity, and ordinary Select controls for choices. Drafts
stay local until Enter or blur; Escape cancels. Clamp at the owner's write boundary, which sliders
and number inputs share. Omit a visible label only where the value or icon is unambiguous, and
always keep the accessible name.

### The slider control

A number a slider sets is ONE control everywhere (`kit/inspector/SliderField.jsx`), shadcn's
labelled slider: no site brings its own slider and number (`src/designSystem.test.js`; the
playbar's scrubber, a timeline, is the one other slider).

- **In a panel**, two lines. The first (16px): the label at the left, in the foreground, and the
  value at the right. The second: the slider (a 12px band) the control's full width, from the
  label's left edge to the value's right edge. No icon before the label, no indent. The label
  line's text stands 5px over the track; 4px above and below the control keep 16px between a
  track and the next label, so each label reads with the slider under it. In the view's panel it
  stands on the panel's lines: the label and the track from 16px in, the value's text and the
  track ending 16px from the right.
- **In a toolbar row** (Explode's, Clip's), one line: the tool's button or name as its label,
  the slider, the value.
- **The value** is the editable number it is (typed, Enter or blur commits, Escape cancels, its
  unit kept), with no border, outline or ring in any state: plain right-aligned text in tabular
  figures, as wide as its text and one figure more; under the pointer and the keyboard the view's
  corner wash (the foreground at 9%) with the caret and the selection.
- **The slider** is shadcn's (`primitives/slider.jsx`) as the control draws it: a 6px track a shade
  darker than muted, the primary range (from `origin` where there is one), a 12px white thumb with
  a primary border and a ring on hover and focus. On a phone the band is 16px in the panel, 36px
  of touch reaching over the label's foot, and the thumb 16px.

## Settings

Settings are the person's, never a file's, and live in the app menu: one dropdown
(`file-viewer/navigation/AppMenu.jsx`) on the floating surface, 12rem wide, from the
navbar's logo over every file and over the home (FileViewer builds it from the host's `links`, the
`appSettings` `CadViewer` hands it and `environment.platform`, while a model loads and after
it failed to as well). Its rows, a rule between each group, are only
what the host supplies, the person's settings in the order Language, Telemetry, Automatic updates,
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
  down while they show), and a choice closes them again.
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
  prompts, models or files. **Automatic updates**, in both apps, after it: whether the server
  installs a newer patch release by itself and restarts on it once nothing runs (a minor or major
  release waits for the update button) (the server's
  `cad_server/auto_updates.py`, the same setting `cad update auto` changes), on by default; one
  the environment turned off (`CAD_UPDATE_CHECK=0`, CI) shows unchecked and fixed, saying so in
  its label, as Telemetry does. Neither adds anything to the navbar: an automatic update shows
  as the update button's own restart, and only once it switches.
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

**Position** is a tab of the [view's panel](#the-views-panel-and-the-tool-stack), there
under every tool: a STEP's where the file has joints to move, a
robot's where a joint can be driven. Its knobs in the viewport are Select's, while Select's
filter ticks Position, and only while the parts are where the pose puts them: over an explosion
Select draws no knobs (the section's controls stay, and using them takes Explode off). Its
first row is the pose (`KinematicsPoseRow`, `data-pose-row`), laid out as the panel's head is: a
dropdown, a full-width box from the panel's 8px line (its text on the 16px one), then, 6px after it
in the head's collapse button's column, **Reset position**, a 20px icon button whose glyph ends on
the right 16px line, idle while the joints are at their default; nothing sits above the row. The
dropdown holds
**Default**, which puts the joints back, then the named poses, and Custom while the joints are
set by hand. No divider under the pose row and no Reset footer.
Each joint is the [slider control](#the-slider-control): its name and value (degrees read
"90.0°", a robot's slides in millimetres, "12.5 mm", typed in millimetres too; the unit says
whether it turns or slides, so no kind icon), then its slider, its range in the slider's hint.
Joints are 4px apart. Long names truncate with a full-name hint and never take the value's room.
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
reads of it (`kit/tools/quick-edit/ReferenceChips.jsx`). A component or subassembly is a chip
of its own; faces, edges and solids are a chip for each kind on each part — "base · face 3"
alone, "base · 6 faces" for several, however they were picked — so a large selection stays a
few chips. A chip names its reference: its own label when it has one (a part's or
subassembly's name, a named face), otherwise its part and kind ("base · face 3") — never the
raw id, which its card shows under the name. In a STEP the card's rows are the reference's key
measurements, nothing else: a face's area, and a round face's diameter and radius (a torus's
two radii); an edge's length, or a round one's diameter, radius and circumference or arc
length, with an arc's sweep; a part's size and volume; a subassembly's part count, size and
volume; a run on one part, one row each. Its rows are the UI font at `text-tiny`, numbers in
tabular figures — no monospace. A click on a chip copies its references, each naming its file
by absolute path; resting on it lights its picks; its X drops them.

Viewport picks reach individual faces and edges, every one to hand from the start.
Shift-click adds to a selection in the viewport; Shift, Ctrl or Cmd does in a
tree (robots select several links this way). Double-click, or a row's Isolate,
isolates a component or subassembly, and the tree brings its row into view (its owners opened);
double-click on empty space leaves isolation, as do the isolated row's X and the menu's Exit all
isolates. No bar over the tree says what is isolated: its row does. A double-click on a face,
an edge or ink turns the view square to it (CAD's Normal To, `kit/camera/lookAt.js`) and
selects nothing: the selection is as its first click found it.

## Quick Edit

Quick Edit is always available in an interactive CAD view. It has no enable/disable
control or persisted preference; stale settings cannot suppress it.

Quick Edit is a person's note to their agent about the file on screen, and the
one way the viewer hands it over: a box at the viewport's top-right, 8px in, on the
floating surface. It is there only while it has something to carry or a note to keep:
nothing stands in for it otherwise, not even a button. Only a view whose picks and
annotations a note can carry has it (a STEP's, a robot's); a compact host gets none, and
Preview puts it away with the tools. While the view loads it is out of sight, its note
and its state kept. It is essential, so no setting turns it off.

Quick Edit keeps its corner, 8px in, and never reaches under the tool strip or its tool's row:
the top-right column starts past the strip's right edge (`--cad-top-right-left`), measured by
the frame (`RendererShell.jsx`, `FlatViewFrame.jsx`, `DxfRenderer.jsx`), so the strip is never
covered. The view's panel is docked beside the canvas, never over it.

On a phone Quick Edit is a bottom sheet, shadcn's drawer as it ships (`primitives/drawer.jsx`,
vaul): full width, non-modal, never swiped away (its X clears it). It opens at a peek of its
handle, header (its title, what goes with the note, the X) and chips, and a pick never brings up
the keyboard. A swipe up, or a tap on its way in (below), takes it to its open stop,
62% of the screen, its note filling what the header and buttons leave, the keyboard in it; a
swipe down takes it back to the peek, what is written kept. Peeking, under its chips is its way
in, a field-like button reading "Describe your changes…" with a pen, which opens it so; its title
is the sheet's heading, a step up the scale. A tap on a chip opens its card (above the chip,
inside the screen) and copies nothing: the card's title copies. Beside the box, on a desktop, a
card opens to the box's left and a click on the chip copies it. It has no grip there.

The box opens 15rem wide, capped to its column, its note growing with what is written up to 10rem. Its
bottom-left corner — the grip every resizable box over the viewport has
(`kit/tools/ResizeGrip.jsx`) — drags it wider to the left and its note taller, for as long as the
box is open: once it closes, however it closes, the next box opens at 15rem again, and
so does another file's. A drag keeps the box at the corner, a frame at a time and
never eased, and renders nothing: the size is written to the box itself, so nothing
else in the viewer redraws under the pointer. Its header is the title, one step up
the type scale ("Quick Edit"); then what goes with the note, in muted text: **N
ref(s)**, the selection counted one by one (a reference naming several picks counts
each; hovering lists their ids, one a line), and **annotation** while there are annotations;
then an X. The file always goes and is not named. Under the header, the note
("Describe your changes"), its border blue while it has the keyboard, and the
buttons at its bottom-right.

While the note is empty the box follows what it would carry: it opens when something
is picked or annotated, and closes when that goes. Every chip leads with its
icon — the Annotation chip's pen, a reference's pick glyph
(a part's cube, a face, an edge, a vertex) — then its words, and they stand in the order
they came, whatever their kind. A chip's copy pasted into the note is a pill there,
drawn as the chip is, 20px like the note's lines so it sits in its rows without spacing
them out. A click on a pill selects it whole, highlighted in the selection's colour, so
Backspace, Delete or typing replaces it as it would selected text. Its chips are
**Annotation** (its X clears the ink), then the selection. The Annotation chip does not copy
references or write files. Copy Prompt, Queue and Send
include their data in the snapshot packet; only selection chips copy individual references. A written note keeps it open whatever
is picked, even with nothing picked or annotated, until the X. The X clears everything:
the note, the selection (as a press on the model's background does) and the annotations, so the
box goes; measurements are not Quick Edit's, and stay. A note that has gone (Copy Prompt, Queue, Send) clears the same way.
Escape in an empty box is the viewer's Escape (clearing the selection, and so the box);
in a box with a note it only hands the keyboard back to the model.

The person's picks put the keyboard in the note, each one (a pick right after their
primary press in this view), and so does a first annotation stroke once the pen lifts. No
live command selects (every renderer declines `select`), so nothing but a person opens it.

The buttons, left to right, are only those the host can carry out, and the rightmost
is the primary one, which Enter presses (Shift+Enter is a new line). They are the
`Button` primitive in its own shape — 28px squares with its rounded corners, each an
icon with a name and a hint — and every one is solid: the primary in the `default`
variant, the others in `secondary`. Where Copy Prompt is the only one (a host that
takes no message, as the web), it is a button in words, "Copy Prompt" with its icon
first. While there is no note they are disabled, dimmed but still drawn:

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
one format, sent, queued or copied: what the person wrote; then `File: <path>`; then
`References:` and one reference per line; then each file that travels as a file by its
label and path — `Snapshot (cad <type> snapshot --annotation):` — or the compact object under
`Snapshot JSON (cad <type> snapshot --annotation):`. An agent draws each view with
`cad <type> snapshot SRC OUT.png --annotation PACKET --camera authored`.

## Camera, animation and Preview

Cube face, edge and corner clicks turn the view and keep pan and zoom; dragging
the cube orbits. Reloading the page restores the camera the file on screen was left
at, and its Display settings, Explode/Clip, the pose, hidden and isolated parts and
the tree's expansion come back with it. Only the model on screen keeps that view:
leaving it — for another file or the home — drops it, so opening a file,
for the first time or again, fits it at the defaults. An update of the model on
screen keeps its Display settings, Explode/Clip, hidden and isolated parts and its
tree, and the pose while its joints are unchanged. The tool, the selection and
measurements never come back — every open starts in the default tool with nothing
selected.

Zoom to Fit recenters and frames the whole original model at the current angle;
Zoom to Selection frames the selection and is unavailable without one. Both are
every view's context-menu items and the zoom's menu's (below); the live `resetCamera` command takes
the same fit path.

**The zoom.** A flat view shows it, as canvas tools do (tldraw's, Excalidraw's, Miro's): its corner's
pill (`kit/shell/ZoomControl.jsx`), − and + either side of the zoom as a percentage in tabular digits at
a fixed width, and the percentage, pressed, its menu — Zoom in, Zoom out (half again, and back), Zoom to
100%, then Zoom to fit and Zoom to selection, each with its key, as Figma's: ⌘+ and ⌘- (Ctrl+= and
Ctrl+- elsewhere; the plain + and - too), ⇧0, F (⇧1 too) and ⇧2. A 3D view shows no percentage, as CAD
tools do not: its corner's Home, F, a double-click on empty space and the view's menu frame it, and the
same keys zoom it. On a phone the zoom is More's Zoom submenu. **100% is the model as authored,
framed whole**: a flat view's fit, a 3D view's rest box (`restBounds`) at the camera's angle — a
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
GLB, STL/3MF, URDF/SRDF/SDF), and a view whose renderer does not (a DXF, 2D) has no Preview
button, not a disabled one, and never enters it, whatever asks. It is the shell's own state;
hosts neither start nor observe it. Its button is a play triangle ("Preview"), the strip's last
tile after Display, in every host. A press covers the view at once
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

In the navbar's place, over the view's top edge, is **Preview's bar**: the navbar's row (36px, a
phone's 48px) on no surface, the model showing through, with the file's or model's name at its
left as plain words, muted as its controls are (no logo, menu, dropdown or glyph), and at its right **Preview settings** (a
sliders icon, pressed while its panel is open, a second press closing it) and the way out, an X
(**Exit preview**), their hints below them; nothing else, in every host (no Full size, no update,
no Quick Edit). It and the playbar, where the file has routines, come and go together, as a
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

**Routines** play from the playbar under the model (`kit/tools/playbar/PreviewPlaybar.jsx`), one
transparent row on no surface, the same in both views (in the tools view on a phone, over Quick
Edit's peek): the routines' list where there are two or more, then **Play** or
**Pause**, the scrubber (`AnimationTimeControl`) and **Playback settings** (a cog: the routine's
Speed, a submenu, then Loop and Autoplay; in the tools view, last after a rule, **Reset
animation**, which stops the routine and puts the model at rest, disabled while it is). Reset is
used seldom, so it is behind the cog, not on the row. The model is at rest while the routine
neither plays nor owns the pose: a routine scrubbed back to its start, or just chosen, still owns
it at its first frame, so the scrubber's start is not Reset; only Reset lets go. Each routine in the dropdown says its duration at its
right, muted, in tabular figures. In the tools view a routine is a motion as a pose is
(see [one motion at a time](#tools-and-lifecycle)): paused, its frame stays on the model. A
routine opens at rest. Each view's routine is its own: entering Preview sets the
tools view's untouched and starts its own at rest, playing only under Autoplay (off by default);
leaving throws Preview's away, and the tools view's is as it was left. A new revision of the
model starts its routine at rest. Speed and Loop are the file's, one set,
chosen in Playback settings and kept in its view once chosen — until then the routine's own
apply. Orbit's speed (1×) and Autoplay are the file's too, remembered between leaving and
re-entering Preview and across a reload of the tab; whether it orbits is not kept. Another
file has its own, and a file the tab left starts at the defaults again. Nothing of the
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
  then the drawing surface's canvas (Pencil's or Shapes') spends its own Escape; then the selected ink; then an unfinished
  measurement; then the tool in hand, any but Select, which goes down and takes Select up, what
  it set kept; then the renderer's own (STEP: the selection, then isolation; robots: the
  selection). The view's panel and the tool stack's panels are
  never Escape's to close.
- **The view's panel's grip** (its right edge), and a resizable panel's (its bottom-right corner),
  is a separator in the tab order: Left/Right nudge its width by 16px (and a resizable panel's
  Up/Down its cap), and Home and End take it to its bounds.
- **Copy** (⌘C or Ctrl+C, and Ctrl+Insert) copies the view with its annotations
  while Pencil or Shapes is up, otherwise the selection's references — unless a text field
  has focus or text is selected.
- **Quick Edit's box** keeps its own keys: Enter presses the primary button and
  Shift+Enter is a new line. Escape hands the keyboard back to the view and keeps
  a note; in an empty box it closes the box and is also the viewer's own Escape
  (it clears the selection). ⌘C or Ctrl+C with none of its text selected is the
  viewer's copy.
- **Ctrl+H** (⌘H) on a KiCad board cycles Display's Others, Shown, Dimmed, Hidden and round, as
  KiCad's high-contrast key does, while the board has the keyboard (as Escape's viewer, above); no
  other view binds it, and a Mac browser that keeps ⌘H for Hide leaves Ctrl+H.
- **⌘\\** (Ctrl+\\) on a KiCad board or schematic shows and hides its panel, and **/** opens it with
  the keyboard in its search, while the view has the keyboard; in the search box, Escape clears what is
  typed, then (on a phone) closes the panel.
- **Arrow keys** orbit the viewer that has focus or the pointer over
  it, never every mounted viewport; they do nothing in Preview or with a
  modifier held.
- **Undo and Redo** (⌘Z and ⇧⌘Z, Ctrl+Z and Ctrl+Y) walk the view's one history: each piece of
  ink put down, erased, restyled or cleared, and each measurement taken, deleted or cleared. The
  camera, the selection, Display, Explode, Clip, hiding and isolating, and Position's pose are
  not steps: they are how the model is looked at, each with its own way back. There are no
  Undo and Redo buttons.
- **Single keys** (`kit/tools/toolShortcuts.js`), with no ⌘, Ctrl or Alt and never in a text
  field or Preview, take a tool up as a design or CAD tool's do: **V** Select, **M** Measure;
  **P** the Pen, **⇧P** the Highlighter, **E** the Eraser; **R** the Rectangle, **L** the Line,
  **⇧L** the Arrow, **O** the Ellipse, **T** Text (each taking up Pencil or Shapes with that
  tool in hand); and **F** frames the model (Zoom to fit: and the zoom's menu, the strip's percentage). A tool already in hand stays so.
  The zoom's keys are the design tools' (`pressZoomKey`), held keys repeating: **+** (or **=**) and
  **-** zoom in and out, with ⌘ or Ctrl as well (the view's then, never the page's zoom); **⇧1**
  fits as F does, **⇧2** frames what Select has picked (nothing with nothing picked), and **⇧0** is
  100% (a flat view's fit; a 3D view's authored box at the camera's angle, about its target).
  Each key shows after its name in its button's tooltip ("Measure M", muted), and Pencil's and
  Shapes' tooltips name what they draw with now ("Rectangle R").

## Tooltips and feedback

Every hint is a `TooltipHint`: compact text, one surface and arrow, a 400ms
delay. No native `title` anywhere in chrome. Prefer one or two words; show a
full technical name only when it is truncated (`overflowOnly`). Quick Edit's buttons, the
strip's buttons (Display and Preview among them; a tool with a key shows it after its name,
muted), the drawing row's tools (each with its key), the navbar's right-hand controls (the
update, an alert's icon, the host's actions: the CAD app's Full size), Preview's bar (Preview
settings, Exit preview) are hinted by name — the strip's hints above their buttons, the
others' below; there is no hint on the navbar's left (the logo,
the file's name and the ⋯ say what they are), on Display's settings button, Playback settings, an X,
the transport (play, pause, the scrubber), the drawing row's settings or labelled text
buttons (Quick Edit's alone say what they do). A disabled, selected or expanded control has none; pressing or leaving cancels a
pending one. A hint appears on focus only for keyboard navigation (a Tab), never
when a closing menu hands focus back.

Copy, snapshot and prompt actions complete silently, the Copy and Quick Edit
buttons showing a tick for a moment. An export is the one exception, and it works as a
browser's download does: one toast, shadcn's Sonner as it ships (`primitives/sonner.jsx`,
mounted once with the export controls), at the view's top right, 16px under the navbar and
16px from the edge, at every width. It is as small as a menu item: one line of the menu's text
(`text-tiny`, regular weight), its padding (6px by 10px), a 14px icon, under 32px tall and as
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
right-hand controls (before the host's actions and the update button), brings it back. The dismissal goes once the alert changes or clears, or
another file opens; with the card back, so does the icon. Preview has no navbar, and so no
icon.

**What's new** is the one dialog the viewer opens by itself (`whats-new/WhatsNewDialog.tsx`): once
after an update to a release with notes, never on a new person's first run, over the home or a
file's view once its renderer is up (never a loading page, nor while the host's own notice covers
the view). It is the stock shadcn Dialog (`primitives/dialog.jsx`, on the `text-ui` scale, no corner
X): the release's title, its items as a list, each a bold title and a sentence or two in the
muted text, and one primary button, **Got it**, which has the focus. The button, Escape and a press
outside each close it and keep it seen for every view of the person's; nothing else is offered.

## Verification

Verify state transitions, touch cancellation, keyboard operation, nested popup
dismissal, feature availability, narrow panels and empty or error states.
Camera and kept-tool tests exercise real transitions, not class names. Do not
keep tests for discarded layouts: replace their assertions with coverage of this
contract. `src/designSystem.test.js` holds chrome to the type scale and the one
breakpoint. The core settings semantics are in
[render-mode.md](render-mode.md); update scheduling is in
[view-updates.md](view-updates.md).

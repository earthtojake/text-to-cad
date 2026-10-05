# Viewer interaction and settings design system

This is the binding contract for the viewer's tools, its tool stack and its
settings, in both apps. Build from the shared pieces — the
[toolbar button](../src/primitives/toolbar-button.jsx),
[FloatingToolBar](../src/renderers/kit/tools/FloatingToolBar.js),
[ToolPopover](../src/renderers/kit/tools/ToolPopover.jsx),
[ToolStack](../src/renderers/kit/tools/ToolStack.jsx),
[ToolPanel](../src/renderers/kit/tools/ToolPanel.jsx),
[the floating surface](../src/lib/floatingSurface.js) and the
[FileSheet primitives](../src/renderers/kit/inspector/FileSheet.js) — and extend
them rather than recreating their layout in a renderer. Environmental effects
belong to apps through the [host contract](viewer-host.md).

## Ownership and layout

FileViewer owns the navbar — the logo's app menu ([Settings](#settings)) included, built from
the host's `links` and the `appSettings` `CadViewer` hands it — and the file explorer (a
popover under the file's name). RendererShell owns the scene's chrome: the toolbar, the tool
stack under it, Quick Edit, the view cube with the view's controls (Display, Preview) on top
of it, the playbar and preview mode. Renderers supply their tools, their document state and
their tool panels; the shell never inspects a format's parts, joints or topology. No pick or
tool opens or closes the explorer.

| The host (web, desktop) supplies | The shared UI decides |
| --- | --- |
| Where the tab record lives (`TabRecordStorage`: the web's sessionStorage, the CAD app's memory) | The record: its settings (the tool stack's layout, the appearance, the home's layout) and the view of the file on screen (its camera, Display settings, Playback settings and renderer slices), what is written when, and what is never stored (`@text-to-cad/ui/tab-store`, `kit/shell/fileView.js`) |
| `navigation.home`, `links` (its version, GitHub, Discord, where a new issue opens, how a link opens), `appSettings` (the person's own settings) and `displayActions` (an appearance control) | The navbar's order and look, the app menu (one menu in the viewer and on the home) and what a new issue says |
| `host.files`, `fileActions`, `navigation`, `clipboard`, `promptContext`, `attachments` | When a copy, capture or open happens and what it carries |
| `host.environment`: color scheme, keyboard `platform`, `reducedMotion` | How the chrome honours them |
| `onError`, for errors the viewer hands up | Preview, tooltips, keyboard scope, the tool stack, the camera |

Hosts pass no preview, chrome-visibility or notification props; there are
none.

- **Navbar.** One row, the same in every app, over every file. Left: the text-to-cad "C"
  logo, named Menu, the size of the row's icon buttons, with no chevron, which opens the
  **app menu** (see [Settings](#settings)) — a host with no home has it too — then the open
  file's name and its ⋯. Each of the three that is a control (`NAV_ITEM_CLASS`) is
  transparent at rest, takes the same accent background while the pointer is on it and
  while its menu is open, has a pointer cursor and no tooltip: it says what it is. The name
  is that control where it opens the explorer (below), where the host's files can be
  browsed; where they cannot it is plain text. The ⋯
  is the file menu: Copy path, and Reveal in Finder / Show in Explorer / Show in file
  manager, each only where the host can do it, and no ⋯ where it can do none. The name has
  no right-click menu and there are no crumbs. It sits the row's 4px gap after the item
  before it, with no margin of its own. Right, only what a host or a file adds, so usually
  nothing: first, the update — a blue download button, there only when the host
  found a newer release, whose menu says the step to it, how this host updates and what
  is new. Then, while a person has put an alert card away: the card's own icon (a circle
  with an exclamation mark, red for an error and amber for a warning, named and hinted by
  the alert's title), which brings the card back and goes with it — the renderer's one
  navbar action. And last, where the host shows the view small (inline in a conversation,
  where the view is the whole viewer), its **Full size**. A CAD file publishes no navbar
  action but that icon. The navbar holds no settings and no view controls: the person's
  settings are the app menu's, and Display and Preview sit on top of the view cube. A
  host's home has no navbar: under its TEXTTOCAD wordmark and byline, its update, when there is
  one, is a row of its own (the blue button, labeled **Update**, its card centred under it), then
  GitHub (its mark, a link to the project: it is open source), Discord and X, as icon links, and,
  where the host shows the view small, **Full size**, above its Recent Files: the models opened before,
  pinned first, as cards or rows, with Open where the host has a file chooser.
  The update shows only for a release
  later than the version the page names, whatever the host says. A file that will not open
  shows a page under the navbar: "File does not exist" and the file's path, or "Could not
  open that file" and the reason, each with **Go home** where the host has a home. A view
  drawn as a picture (`compact`, the home's thumbnails) has no navbar either, and draws the
  model alone: no tools, view actions, cube or Quick Edit.
- **File explorer** is a popover under the file's name (`FolderExplorer.jsx`), aligned to
  the name's left edge, 18rem wide and never resized, as tall as its rows up to 28rem or
  the room below it: past that its list scrolls. It floats over the view and the tool
  stack, so opening it resizes and moves nothing. It starts in the open file's folder and
  lists one folder at a time — its subfolders, then its CAD files — under a breadcrumb of
  the last three folders, whose "…" lists the folders above to jump to; there is no up
  arrow, and the open file is highlighted. "Filter files..." under the breadcrumb searches
  every file nested under the folder (the server's bounded search, debounced 150ms, each
  keystroke cancelling the search before it); a search that stopped early says "Stopped
  early. Keep typing to narrow the search." Up and Down move between the filter and the
  rows. A pick opens the file and closes it, as do Escape and a press anywhere outside it.
- **Toolbar** at top-left, 8px in — the gap between it and the stack under it.
- **Tool stack** beneath the toolbar: the panels of the tool in hand and of the
  effects a person keeps (see [The tool stack](#the-tool-stack)). The column is
  exactly the height the stack may take: it stops 8px above the view's controls on top
  of the cube, so it never runs under them or the cube, and while the panels fit only a
  panel's inner body scrolls.
- **Quick Edit** at top-right, 8px in, a STEP file's: the box of the note a person
  writes to their agent, there only while something is picked or drawn (see
  [Quick Edit](#quick-edit)). The rest of the right side of the view is clear.
- **View cube** at bottom-left, 2px from the left and 8px off the bottom so the
  axes drawn in its lower corner never touch the edge, in a 6rem area: enlarged
  face/edge/corner hit areas and neutral hover and XYZ guides. Preview omits it.
- **Display and Preview** on top of the view cube, in the bottom-left corner: for a 3D
  file, the view's own controls — **Display** (the perspective box: see
  [Display settings](#display-settings-and-section-primitives)) and **Preview** (a
  fullscreen icon, two diagonal arrows). They are 24px icon buttons with 14px icons, 2px
  apart, in a 24px row as wide as the cube, directly on top of it
  (`data-viewport-actions`, `VIEWPORT_ACTION_HEIGHT_PX`), with hints above them. Display's
  dropdown opens up from its button, start-aligned, and never taller than the viewer below
  the tool strip. A view that is not 3D has neither, and neither does a view drawn as a
  picture, one that is loading or failed to load, or preview, which has the page to itself.
- **Playbar** (preview's, a file with routines only) sits at bottom-centre, on a
  line 1.75rem up (a host whose control floats over the view's bottom moves it
  with `--cad-viewport-bottom-center`), and nothing else does; a static file has
  nothing at the bottom.
- **Model update status** sits at top-centre of the viewport, vertically centred
  in the same 34px row as the top-left toolbar in every host.
  It is renderer chrome: the navbar carries no status.
  On mobile it is a tappable progress icon whose popover names what is loading.

## Tools and lifecycle

| File | Toolbar, left to right |
| --- | --- |
| STEP | Select, Position (movable joints only), Draw, Measure, Explode (two or more parts), Clip |
| URDF / SRDF / SDF | Select, Position (posable joints only) |
| GLB / STL / 3MF | none |
| DXF | none: a 2D canvas |

There is no separator or activity dot. There is no Animate tool: routines play in
[preview](#camera-animation-and-preview). Display is not a tool: every 3D view has
its **Display** button on top of the view cube, before Preview (see
[Display settings](#display-settings-and-section-primitives)). A file
with no tools has no strip at all.

**A tool the file cannot offer is not on the strip**: never shown disabled.
Renderers leave it out of the `tools` they hand over; `FloatingToolBar` draws
what it is given. Until a file has loaded, what it offers is not known: a tool
that depends on it (Explode, a robot's Position) is shown idle meanwhile, and
the whole strip is disabled while loading. Unavailable and idle are different
states.

One tool owns pointer input. A kept effect (an Explode, Clip or Measure panel)
stays highlighted beside it; a highlighted kept effect is not a second pointer
owner.

| Tool | Pressing it | Leaving it |
| --- | --- | --- |
| Select | The default tool of STEP and robots; shows Features (Links) and, with a selection, the Reference panel; a STEP's Select panel above them sets the mode. A press while it is up opens its tree again where a person closed it | The selection is dropped; its panels leave the stack |
| Draw | Draws on the view; its tools, color and history are the Drawing panel; a second press puts it down | The sketch is gone |
| Measure | Arms picking and shows the Measure panel: its snapping modes, then its results; a press while it is up clears the results and puts it down | Unfinished picks are cancelled; completed measurements and their panel stay |
| Explode / Clip | Opens a neutral panel; an edit applies the effect | A neutral panel goes; an applied effect and its panel stay |
| Position | Shows joint handles and the Position panel; its icon carries a small dot while the pose is not the default | Handles and panel hide; joint values stay |

A tree is Select's panel, so it is used under Select; a tree row's menu action
returns to Select before it acts.

**Every tool's panel but Select's has an X, and no fold chevron.** The X puts
the tool down and returns to Select, the default tool, which cannot itself be put
down. Select's tree has an X too, which closes the tree alone and leaves Select
the tool; a press on Select while it is up opens it again (see
[Closing the tree](#the-tool-stack)). SDF folds instead.

**No tool has a menu on the strip.** A press on a tool is its only action:
it takes the tool up, and — for a tool that toggles (Draw, Measure, Explode,
Clip) — a press while it is up puts it down. Whatever a tool can be
set to is its panel in the stack, up while the tool is: Select's modes, Measure's
snapping, Draw's tools, Position's joints. A tool's exclusive
modes are never a panel or a row of their own: they are ONE small button in its
panel's header row, just before the fold chevron or the X — a sliders icon, the
size of those buttons (the strip's button shows the mode in hand) — whose
dropdown lists the modes — each its glyph and its name — then any options that
go with them (`kit/tools/ToolModeMenu.jsx`). Select's sits in the Features
filter row, Measure's in the Measure heading. A dropdown is ordinary — under
its own button, free to overlap the stack — and closes with no exit animation,
so a quick second tap (touch included) always reaches its trigger. Choosing a
value closes it; ticking an option leaves it open. Menu checks sit on the
right. The other dropdowns over the viewport are its context menu and
preview's Playback settings (`ToolPopover`, `PlaybackMenu`).

**Select** (STEP) has four exclusive modes, each with its own glyph: **All**
(the pointer), **Parts** (a cube), **Faces** (a cube, its top face filled) and
**Edges** (a faint cube, one edge heavy). They are the mode menu in the
Features filter row, beside its X; each menu row shows its mode's glyph
at full size. The strip's Select button shows the mode in hand as ONE composite:
the pointer, with the mode's glyph shrunk to a badge in its top-right corner
(cut out of the pointer so the two never touch at the strip's 14px), and the
bare pointer for All (`data-select-mode`). One drawing of each glyph serves
both sizes (`SelectionModes.jsx`). Parts is offered only in an assembly. The mode in
hand is kept while the file is open, across updates of it (an update that leaves no
assembly puts Parts back to All); another file opens in All. Under the modes,
checkboxes — **Group edges** and **Group faces** — change how a pick grows,
independently of the mode and of each other: Group faces applies under All
and Faces, Group edges under All and Edges. Only the options that apply under the
mode in hand are shown (both under All, none under Parts); a hidden one keeps
its choice for when it applies again. Nothing under the strip names the mode. The mode sets the Features tree's shape: under **All** it
is the person's own (put back as it was when they left All, with the owners of
what is still selected kept open); **Parts** opens every assembly and shuts
every part; **Faces** and **Edges** open everything down to the features whose
faces and edges are picked. Outside All the disclosure is locked (chevrons
shown, not pressable) and Expand/Collapse leave the row menus. Under Faces or Edges
a part's topology is asked for as its row comes on screen in the tree, never for
a whole large assembly at once; a viewport press on a part not yet loaded loads
that part and picks, and the Features filter row says "Loading…" meanwhile. A large
assembly (more than 300 rows of assemblies and parts, `LARGE_TREE_ROWS`) opens
under Faces or Edges with its assemblies open and locked but its parts closed, each
with a disclosure of its own and, at its right in muted text, its face or edge
count ("412 faces", "96 edges") once that is known. A part opens by its
disclosure, by a pick inside it (which scrolls to the picked row) or by the
row menu's Expand and Expand all; Collapse and Collapse all close parts. A
closed part's topology is not asked for when its row shows: opening it asks, and
so does the pointer resting on the part in the viewport (150ms) or pressing it.

**Draw.** Its **Drawing** panel leads the stack while Draw is up, with no heading
and no X: choosing another tool, or pressing Draw again, puts it down. It holds
the tools, then a rule across the panel, then a row of Color, Stroke width (Thin,
Medium, Bold — a shape's 1, 2 or 4px, the pen drawn to look the same weight),
Undo, Redo and Clear; both are grids of 24px columns spread across the panel's
width, their columns lined up, with no menu and no inset beyond the panel's own.
Leaving Draw forgets the sketch, but not the tool, colour and weight in hand,
which the next time opens with. An update of the model forgets it too, its history
with it (Undo has nothing to bring back), and leaves Draw the tool, on the tool,
colour and weight in hand. Choosing a drawing tool changes the toolbar
icon. Undo and Redo are disabled when their history is empty. The select tool uses lucide's
SquareMousePointer. The pencil and the shapes share one default stroke width.
Once there is ink, the Drawing panel ends in a full-row **Copy Drawing**, which
writes the view with its ink to the clipboard as a PNG and then says **Copied**, a
tick where the shortcut was; the copy shortcut does the same. A sketch begun opens
[Quick Edit](#quick-edit), whose header says **drawing** while the ink is there. Draw disables the cube without hiding it.

**Measure.** Its **Measure** panel is up as soon as it is the tool, empty: a
heading whose mode menu, beside its X, holds the four snapping
modes — **All**, **Points**, **Edges**, **Faces**, plain rows with no title and
no descriptions, each the mode's glyph at full size (All: the ruler; Points: a
dot in a ring; Edges and Faces: Select's glyphs) — and, before the first
measurement, one hint row the height of a measurement row ("Pick two points to
measure"). The strip's Measure button shows the mode in hand
as Select's does: the ruler badged with the mode's glyph (`data-measure-mode`).
Completed measurements are the panel's body, and keep the panel in the
stack when another tool is taken up; choosing a mode there takes Measure up
again, results and all. A press on Measure while it is up — results or none —
or the panel's X clears them all and puts it down. Removing the last result
leaves Measure picking, its panel empty. There is no Clear All footer.

**Measure, Explode and Clip** do not fold: their X is how a person is done
with one (it clears the results or removes the effect, and puts the tool down).

**Explode and Clip** are toggles with no enabled checkbox, drawn alike: the
amount in the heading beside the title, one row for a body — Explode's a
slider, Clip's its axis (a compact X / Y / Z dropdown) and then its slider. Explode opens at 0%,
Clip at no cut; an edit applies the effect and the panel is then kept. A panel
still at its neutral value goes when another tool is chosen, or when the pointer
is released after a drag that ended at neutral — never mid-drag. Pressing the
tool again while its panel shows is the same as its X: the effect is removed and,
if the tool held the pointer, Select returns. An axis alone is not an effect. The view settings
own both effects, so a Display Reset removes their panels and a restored effect
reappears with its panel without another press. Clip's slider, left to right,
cuts deeper through the original bounding box; pose, animation and Explode never
redefine the range. There is no Flip. With fewer than two parts Explode is not
on the strip.

## The tool stack

Under the toolbar, in one column: the shell's tool's panel (**Drawing**) while
Draw is up; Select's **Features** (STEP; a
robot's **Links**) and, whenever something is selected, its **Reference** (then
a `.sdf`'s **SDF**); Position's **Position**; then the panels
of the effects a person keeps (**Measurements**, **Explode**, **Clip**). A panel
whose tool is not up is `hidden`, not unmounted: a tree keeps its expansion,
filter and scroll across a trip to another tool. Preview hides the whole
stack.

- **Two kinds of panel.** The tree (Features, Links), the **Reference** and
  **Position** are *resizable*: the person's to size, each on its own. The
  Reference sits under the tree as a box of its own, sized apart from it:
  sizing either changes nothing about the other. Every other panel — Drawing,
  Measurements, Explode, Clip, SDF — is *fixed*: one width, its content's
  height, and no grip. A renderer opts a panel in with `resizable`; nothing
  else about it changes.
- **One width.** Every panel opens at `TOOL_PANEL_WIDTH`: 164px, a strip of
  six tools (six 24px buttons, 2px gaps, 4px padding and a 1px border),
  whatever tools the file's own strip has — a file with three tools has the
  same panels as one with seven. A fixed panel is exactly that wide. A
  resizable panel is only ever made wider, up to half the viewer; widening one
  changes nothing about any other panel. The panels hang left-aligned
  under the strip, each at its own width. Content truncates to fit; it never
  widens a panel.
- **Heights.** A panel is exactly its content's height — never padded to a
  minimum: a tree of two rows is its filter row and two rows. A resizable panel
  has a *cap* the content grows up to and then scrolls inside: the tree and
  Position open capped at half the stack's own height (the area under the
  strip, not the viewer) on desktop, and at the whole column on a phone. The
  Reference opens shorter, capped at 144px on both (`TOOL_PANEL_REFERENCE_HEIGHT`:
  its heading, its Copy and four compact rows between them — a reference's key
  measurements, an arc's four the most; a longer one, a robot link's facts,
  scrolls, or a drag of its corner shows it).
  A cap is never a floor. Setting one panel's cap changes no other's.
- **One grip, on a resizable panel only.** A resizable panel is sized from its
  bottom-right corner alone, by the grip Quick Edit's box has
  (`kit/tools/ResizeGrip.jsx`, mirrored into this corner): two short diagonal
  strokes drawn inside the panel's border, muted until the pointer is over them,
  in a 14px hit area with a resize cursor and, for the keyboard, a focus ring. No
  edge of a panel resizes it. A drag moves only that panel, its width (from the
  one width to half the viewer) and its cap (from 64px to the stack's height)
  at once. The grip is a separator in the tab order, named after its panel
  ("Resize features", "Resize reference details"): Left/Right nudge the width
  and Up/Down the cap by 16px, and Home and End take both to their bounds. One
  write, when the pointer lets go (or per key), never per pointer move. A
  folded panel has no grip: there is no height to set.
- **Never past the viewer.** The column is the viewer's height less the 8px
  inset above the strip, the strip, and at its foot the cube with the view's
  controls on top of it and an 8px gap above them (`VIEWPORT_STACK_BOTTOM`,
  `calc(6rem + 40px)`: the cube's 6rem, its 8px off the bottom, the controls' 24px and
  the gap): it never runs under the cube or its controls. When the panels need more, the tree gives way first and
  scrolls inside itself, down to 128px or its content, whichever is less; then a
  details panel (Reference, Position, Measurements)
  gives way, down to 96px or its content; a small panel (Explode, Clip, Drawing)
  keeps its height. If what cannot give way still does not fit, the column
  itself scrolls — a panel is never cut. On mobile the tree starts closed and,
  opened, may take the whole column, giving way as other panels join it.
- **Closing the tree.** Select's tree (Features, Links) does not fold: the X at
  its filter row's end ("Close features") closes it, `hidden` and kept mounted
  with its expansion, filter, selection and scroll, and Select stays the tool —
  a selection still shows its Reference, a panel of its own. While the tree is
  closed, Select's button carries the flyout corner: a small filled triangle in
  its bottom-right corner (the mode badge has the top-right), out of the
  accessibility tree, with the button described as "Features closed". A press
  on Select while it is the tool opens the tree again as it was, and the mark
  goes; from another tool a press only takes Select up, the tree still closed.
  Until a person closes or opens it, the tree starts as the file does: closed
  for a single part, open for an assembly (and for a robot's Links), and closed
  on a phone whatever the file — the mark showing whenever it starts closed.
  Once the person has closed or opened it, that choice holds in every file of
  the tab, over how each starts. A renderer opts in with `closable` on the
  tree's panel (`ToolPanelClose` is its X) and `panel: { id, label, startsClosed }`
  on the tool it belongs to (STEP: `startsClosed` for a single part); the frame
  draws the mark, routes the press and starts the panel (`RendererShell.jsx`).
- **Folding.** Only Select's SDF panel and a robot's Reference fold: every tool
  panel and a STEP's Reference has an X alone. A folding panel folds to its first row and unfolds again,
  by a chevron at that row's trailing end: up while open (fold), down while
  folded (open), with `aria-expanded` and the panel's name ("Collapse sdf").
  Folded content stays mounted.
- **First rows.** Features and Links have no heading: the filter is their top
  row ("Filter…"), stays put while the tree scrolls, and carries the mode menu
  (Select's) and the X at its end — both step aside while the box has
  focus, so the whole row is the box. Every other panel
  has a heading row, and every heading reads alike: the Display section
  headings' text (11px, regular, `TOOL_PANEL_HEADING_TEXT_CLASS`), 28px tall,
  8px in — a title; a summary where there is one (Explode's and Clip's amount);
  then, at its right
  end, its own actions (a mode or settings menu — Measure's — or Position's
  Reset), the chevron where it folds, and an X when there is something to remove.
  Every small button in a heading or a filter row is 20px, 2px apart and 4px from
  the edge, so the icons line up down the stack. The Reference's heading is the
  reference itself, then an X that clears the selection; a kept panel's X removes
  the effect.
- **Footers.** A panel can end in one full-row button under its body, which
  never scrolls (`footer`, `ToolPanelFooterButton`): the Reference's **Copy** —
  **Copy All** with several references, every one selected — and, once there is
  ink, Drawing's **Copy Drawing**. The button shows the copy shortcut in the
  platform's form (a phone shows none); after a copy it says **Copied** for a
  moment, a tick where the shortcut was.
- **The layout is the person's.** The sizes, the folded panels and the closed
  tree are one of the tab's settings, across its files (`CadPreferences.toolStack`:
  `{ panels: { [panel id]: { width?, height? } }, collapsed: { [panel id]: boolean }, closed: { [panel id]: boolean } }`,
  kept beside the appearance). `panels` holds only what a person set, by
  resizable panel — the tree, the Reference and Position each under its own
  id; `collapsed` only what differs from a panel's start (the SDF panel starts
  folded); `closed` the person's own choice, once they have closed (`true`) or
  opened (`false`) the tree, which then holds in every file over how each
  starts (a part closed, an assembly open, a phone closed). A new tab (a cleared
  record) puts every panel back at the one width and its default cap, and the
  tree as each file starts it. Every size is written back once, when the pointer
  lets go (or per key), never per pointer move.
- **Surfaces.** Two, defined once (`lib/floatingSurface.js`), with one border: the
  toolbar and the stack's panels, which stay up beside the model, share
  `FLOATING_CHROME_SURFACE_CLASS` — the background at 45.5% and barely blurred
  (2px), so the model behind them is easy to make out; every menu and popover
  over the viewport, the app menu and Display included, share
  `FLOATING_SURFACE_CLASS` (the background at 75%, blurred), so their text never
  competes with the model.
- **Scrolling.** Every scroll region in the viewer's chrome — a panel's body,
  the stack's column, the explorer, a menu, the alert card — is the
  `ScrollArea` primitive (`primitives/scroll-area.jsx`, shadcn's): thin overlay
  bars in the theme's colours, shown while the pointer is over the region. No
  native `overflow-auto` scroller in chrome; `src/designSystem.test.js` holds it.
  The home (the model library) is a page, not chrome: it scrolls as a page does,
  with the platform's scrollbar, and only when there is more of it than fits.
- **Nothing opens elsewhere.** A pick shows its Reference in the stack; the
  Position tool shows its panel by being chosen. No pick or tool opens or closes
  the explorer, on desktop or mobile.

Tree rows inset their backgrounds 4px from the panel edges, and the filter row
shares that inset. A tree in the stack (Features, Links) is dense (`TreeRowSurface`'s
`dense`): 24px rows in the panels' 11px text, 12px kind icons, a 16px disclosure
column with a small chevron, and 12px of indent per level; its filter row is a
heading's 28px, the box 20px tall and close to the row's walls. An assembly row's
actions, shown on hover and kept while they are on, are **Isolate** then the **Hide/Reveal** eye; a part file has no
Isolate. They float over the row's right end rather than taking width from it:
the name runs the row's full width and, while an action shows, fades out half a
rem before them (a mask, `ROW_NAME_UNDER_ACTIONS`), so nothing is drawn behind the
buttons and the row keeps its own colour.
Model, link and explorer filters share `TreeFilterInput`; the explorer's rows are not
dense: 28px, in 12px text.

**Mobile** is below 720px of FileViewer width — the one viewer breakpoint
(`useViewerMobile`); chrome never uses window breakpoints. The tool stack is
the same stack, but Select's tree (Features, Links) starts closed in every
file, Select marked, so the model has the screen until the person presses Select. The
explorer is the same popover, never wider than the window less 1rem. The navbar is the
same row; the shortcut hint is hidden.
Touch works for every tool: one finger orbits, two pan and
zoom, a tap picks; a pinch, a cancelled pointer or a camera drag is never a
pick.

## Display settings and section primitives

Display is not a tool. It is a 3D view's dropdown (`kit/shell/DisplayPopover.jsx`) from its
button on top of the view cube, before Preview: the perspective box
(`PerspectiveProjectionIcon`), hinted "Display", pressed while the dropdown is open. A view
that is not 3D (a DXF) has no Display button, not a disabled one. It opens an ordinary
popover up from the button, start-aligned, 304px wide — the width its settings are laid
out for, two a row, with Projection's "Orthographic" in full beside the host's appearance
control — and never taller than the viewer below the tool strip: its sections scroll
inside it. Opening it leaves the tool in hand as
it is: a selection, a Draw session or Position stay. It goes with Escape, a press outside
it (on the model, say), its button again, or the X at the end of its first heading
("Display", its Reset, then its X); setting changes leave it up. It is idle while the file
is, as the tools are. Another file opens with it closed; preview, which has the page to
itself, puts it away.

One scroller (the dropdown's body), shared section primitives, no sticky headings
and no nested cards. Nested dropdowns and color pickers own their dismissal:
Escape closes the innermost popup first, the dropdown only on a later press.

| Section | Contents |
| --- | --- |
| Display | Full-width render Mode; Appearance (when the host gives one) and Projection beneath; a small gray Reset icon at top-right |
| Surfaces | Style and part-color mode; color or palette and opacity below |
| Edges | Visibility and color, where the format has topology |
| Grid / Axes | Two color/opacity controls, left and right in title order, no visible labels |
| Lighting | Quality, exposure, rotation, softbox size and fill |
| Background | Color and opacity |
| Floor | Color/opacity; position and finish side by side |

Display holds the file's view alone: the person's settings are the [app menu](#settings)'s.
Display and Surfaces are always open. Every other section is a feature gate
with plus/minus: expanded means enabled, collapsed means disabled. Grid / Axes
gates both groups; their settings stay separate in the core/CLI contract. Never
add an "Enabled" checkbox inside a gated section. Enabling starts at defaults;
disabling removes overrides. A heading click reveals enabled content without
disabling it; only minus disables. Hover, focus and rendering never write
settings.

Mode presets are shortcuts over the same controls; manual overrides show
Custom, which is not selectable. Reset keeps the chosen Mode and clears
everything else, Explode and Clip included; it never reframes, and it leaves the
pose, the app's appearance and orbit preferences alone. Appearance is the
host's (the web app's Light/Dark/System): with System stored, its trigger shows
the resolved Light or Dark, and the menu still marks System. The Projection
value carries its icon and truncates with an ellipsis.

Every section but the first has a top border. A press on an open gate's title
scrolls it into view within the natural range, never adding blank space to
force it to the top; ordinary edits do not scroll.

Type comes from the token scale only (`text-micro` 10px, `text-tiny` 11px,
`text-xs` 12px, `text-ui` 13px); no pixel font sizes. Settings controls and the
Display's headings use `text-tiny`, regular weight, with shared 28px controls;
panel headings use 12px. Sections use 8px gutters and bottom insets
and 4px row and column gaps. `FileSheetFieldGrid` owns horizontal spacing; its
children never pad again. Menu, select and context-menu typography comes from
the primitives, portals included. Selected values show their icon where it
means something.

Use `FileSheetSliderField` for a useful bounded range with a committed number
input, `FileSheetNumberProperty` for other scalars, `FileSheetColorProperty` for
color with opacity, and ordinary Select controls for choices. Drafts stay local
until Enter or blur; Escape cancels. Clamp at the owner's write boundary, which
sliders and number inputs share. Omit a visible label only where the value or
icon is unambiguous, and always keep the accessible name.

## Settings

Settings are the person's, never a file's, and live in the app menu: one dropdown
(`file-viewer/navigation/AppMenu.jsx`) on the floating surface, 15rem wide, from the
navbar's logo over every file (FileViewer builds it from the host's `links`, the
`appSettings` `CadViewer` hands it and `environment.platform`, while a model loads and after
it failed to as well); the home has no menu. Its rows, a rule between each group, are only
what the host supplies:

- **Back to files**, where the host has a home
  (`navigation.home`): it shows the home in this view. The home's own menu has none.
- The host's own on/off settings (`appSettings`), a checkbox item each, in the order they
  come, checked at the right; a press turns one without closing the menu. **Share
  anonymous usage data** and **Quick edit** — on until the person turns it off
  ([Quick Edit](#quick-edit)) — in both apps.
- **Send feedback**, where the host has a tracker (`links.issues`): a link to a new issue
  titled "Feedback: " for the person to finish, naming the version and the platform, with
  no label (what is said may be a bug, a request or a question). Then **GitHub** and
  **Discord**.
- Last, in gray, a footer: "v<version> · Made by @<handle>" — the version a link to its
  release notes, the handle one to the host's X account.

Nothing of a file is in it: a file's view is
[Display](#display-settings-and-section-primitives)'s. Every setting is the person's, not a
view's or a tab's: the host keeps it where every view of theirs reads it (both apps: their
settings, `settings.json` in cadgen's state directory), and a view reads it again whenever
the person comes back to the page.

## Position and references

The **Position** panel is headed "Position", with a small Reset icon and its
X in its heading, and is sized like the tree: its content's height, capped at
half the stack, with its corner grip. Its first row is "Pose" — a label
beside its dropdown (`KinematicsPoseRow`) — only when there is a named pose to
choose; the dropdown includes Default, and manual edits show Custom. No divider
under the pose row and no Reset footer. Each joint's label sits tight above its
slider in the flexible left column, with a compact value field (24px tall, about
five characters wide, tabular figures; degrees read "90.0°") in the right column
of the same row; joint rows are 4px apart. Long labels truncate with a full-name
hint and never take the slider's width. Slider thumbs are named after their
joint, and every slider reports its value at its step's precision (never float
noise). Writes pose the model at once.

Position persists across tools, and across an update of the model whose joints and
named poses are unchanged, the named pose chosen included; an update that changed them
starts the pose at the new defaults, never fitting the old values onto other joints.
Reset restores the authored
values (an SRDF's home included), stops motion and hands control back to
Position. A routine playing in preview sets the Position values aside and gives
them back on leaving it. A Position edit, Reset included, stops and rewinds a
routine but keeps its Routine, Speed and Loop for the next play. Kinematics, named poses and
animation are separate capabilities; the absence of one never leaves empty
controls for another.

The Reference panel is read-only, and a resizable panel of its own under the
tree: it opens at the one width, capped at 144px, and its corner grip sizes it
apart from the tree. Its rows are compact (2px above and below) and
in the panel's one face: labels and values alike are the UI font at `text-tiny`,
numbers in tabular figures — no monospace. A value too long for its cell wraps
between words, or (a row of numbers, such as a link's inertia) truncates with
its whole as a hint; a number never wraps inside itself. Its heading, flush with
the rows' labels, names the reference: its own label when it has one (a part's or subassembly's
name, a named face), otherwise its part and kind ("base · face 3") — never the
raw id, which is no row either. In a STEP its rows are the reference's key
measurements, nothing else: a face's area, and a round face's diameter and
radius (a torus's two radii); an edge's length, or a round one's diameter,
radius and circumference or arc length, with an arc's sweep; a part's size and
volume; a subassembly's part count, size and volume. What it is (its kind and
part) is the heading's to say, what a person copies for an agent (the reference,
with its file) the Copy's, and where it sits and points the view's: there is no
Type, ID, Center, Normal, Component or Material row. With several references the heading is a
picker over them with a muted "i/N" beside the name — quiet on hover in either
theme (no fill; only its chevron comes up), and nothing about it moves; that picker is all a
multi-selection adds, and the rows are always the browsed reference's alone (no
totals, no count line). An X at the heading's end clears the selection; the
heading has no Copy of its own. Copy stays in row menus and the copy shortcut, and
the panel ends in a full-row **Copy** (**Copy All** with several references) that
shows the shortcut. What goes to an agent goes through [Quick Edit](#quick-edit), which a
pick opens and which carries the selected references with the file. Every copied
reference names its file by absolute path.

Viewport picks reach individual faces and edges even where the tree groups them
into a feature. In an assembly, faces and edges load per part, when first
needed: under a face or edge filter, a press on a part whose faces are not
loaded loads that part alone and then picks what is under the pointer — one
press, with "Loading…" in the Features filter row meanwhile. Until
then, hovering such a part lights the whole part.
Shift-click adds to a selection in the viewport; Shift, Ctrl or Cmd does in a
tree (robots select several links this way). Double-click, or a row's Isolate,
isolates a component or subassembly; double-click on empty space leaves
isolation, as do the isolation bar's Exit and the lit Isolate. Only topology that
cannot be isolated copies on double-click, and it stays selected.
Clearing the selection or leaving isolation never leaves a stale Copy Reference.

## Quick Edit

Quick Edit is a person's note to their agent about the STEP file on screen, and the
one way the viewer hands it over: a box at the viewport's top-right, 8px in, on the
floating surface. It is there only while it has something to carry or a note to keep:
nothing stands in for it otherwise, not even a button. It is a STEP file's alone,
since only a STEP has picks and sketches to carry; a compact host gets none, and
preview puts it away with the tools. While the view loads it is out of sight, its note
and its state kept. A person can turn it off in the [app menu](#settings) (**Quick
edit**, on until they do; `view.features.quickEdit`): it is then not there at all, in any
of their views — no box, so nothing a pick or a sketch opens and no keyboard it takes —
until they turn it on again.

The box opens 15rem wide, its note growing with what is written up to 10rem. Its
bottom-left corner — the grip every resizable box over the viewport has
(`kit/tools/ResizeGrip.jsx`) — drags it wider to the left and its note taller, for as long as the
box is open: once it closes, however it closes, the next box opens at 15rem again, and
so does another file's. A drag keeps the box at the corner, a frame at a time and
never eased, and renders nothing: the size is written to the box itself, so nothing
else in the viewer redraws under the pointer. Its header is the title, one step up
the type scale ("Quick Edit"); then what goes with the note, in muted text: **N
ref(s)**, the selection counted one by one (a reference naming several picks counts
each; hovering lists their ids, one a line), and **drawing** while Draw has ink;
then an X. The file always goes and is not named. Under the header, the note
("Describe your changes"), its border blue while it has the keyboard, and the
buttons at its bottom-right.

While the note is empty the box follows what it would carry: it opens when something
is picked or sketched, and closes when that goes. A written note keeps it open whatever
is picked, even with nothing picked or sketched, until the X. The X clears everything:
the note, the selection (as a press on the model's background does) and the sketch, so
the box goes. A note that has gone (Copy Prompt, Queue, Send) clears the same way.
Escape in an empty box is the viewer's Escape (clearing the selection, and so the box);
in a box with a note it only hands the keyboard back to the model.

The person's picks put the keyboard in the note, each one (a pick right after their
primary press in this view), and so does a sketch's first stroke once the pen lifts. A
selection an agent or host makes through the live controller (`select`) opens it without
taking the keyboard.

The buttons, left to right, are only those the host can carry out, and the rightmost
is the primary one, which Enter presses (Shift+Enter is a new line). They are the
`Button` primitive in its own shape — 28px squares with its rounded corners, each an
icon with a name and a hint — and every one is solid: the primary in the `default`
variant, the others in `secondary`. Where Copy Prompt is the only one (a host that
takes no message, as the web), it is a button in words, "Copy Prompt" with its icon
first. While there is no note they are disabled, dimmed but still drawn:

- **Copy Prompt** (copy icon), always. It copies the note as text: its references
  spelled as copied references are, and a sketch by the path it was saved at, since
  text cannot carry a picture.
- **Queue** (list-plus icon), where the destination is a composer: the note goes
  into the context of the person's next message.
- **Send** (up arrow), where the host can post a message: the note goes now, as the
  person's message.

Queue and Send clear the note and what it carries, and so close the box, once the
note has gone. Copy Prompt keeps it all, since nothing has gone yet: its button
shows a tick for a moment. A failure keeps the note and says why in the box. The message is
one format, sent, queued or copied: what the person wrote; then `File: <path>`; then
`References:` and one reference per line; then `Sketch: <path>` when the picture
travels as a file (a picture sent beside the text is not named).

## Camera, animation and preview

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
STEP context-menu items; the live `resetCamera` command takes the same fit path.

**Preview** is available for every 3D file, animated or not, and for nothing
else: a renderer declares it (`useRendererShell`'s `previewable`: STEP, GLB, STL/3MF,
URDF/SRDF/SDF), and a view whose renderer does not (a DXF, 2D) has no Preview button,
not a disabled one, and never enters it, whatever asks. It is the shell's
own state (`previewing`); hosts neither start nor observe it, beyond giving the
page over to it. Its button is the fullscreen icon, after Display on top of the view cube
("Preview"). It is fullscreen: the renderer says so
(`onFullscreenChange`), and the navbar (its menu and the explorer with it) and any declared
panel step aside while it lasts, Display and Preview with them; the toolbar, the tool stack
and its resize grips, Quick Edit, joint handles, cube and context menu are gone. Its
way out is the view's own: an X ("Exit preview") in the corner box over the cube's corner
(the cube itself is hidden), the very box Display and Preview sit in outside preview
(`PreviewChrome`'s `cornerStyle`), so each lands exactly where its counterpart was: the X
where Preview was. It is transparent over the model and fades with the playbar; Escape
leaves it too. It
starts orbiting, unless the file's Playback settings turned its orbit off. **Playback
settings** (a cog; `PlaybackMenu`) sits in that corner before the X, where Display
sits outside preview, and opens up. It holds, for a file with routines, **Animation** — the Routine (with more than one), Speed, Loop and
Autoplay — then **Orbit**: on or off, and its speed. Under the model, an
animated file shows its playbar (play/pause and the scrubber); a static one shows
nothing there. These controls and the corner share one one-second idle deadline and a
150ms fade: movement wakes them, and hovering their area or an open menu holds them.

Routines play in preview alone: there is no Animate tool. Entering preview
starts the routine when Autoplay is on (off by default); leaving it stops the
routine and puts the model back at rest, keeping the Routine for the next time
while the file is open. An update of the model that leaves its routines as they were
neither stops nor rewinds one that is playing; a changed routine starts at rest.
Everything in Playback settings is the file's own and is remembered between leaving
and re-entering preview and across a reload of the tab: Orbit on or off (on by
default) and its speed (1×), Autoplay, and a Speed or Loop once chosen — until one
is chosen, the routine's own apply. Another file has its own, and a file the tab
left starts at the defaults again. Nothing of the routine — which one, its time,
whether it plays — is saved. Orbit is not an animation setting.

Previewing turns off picks, hover, selection highlights, recognition, Draw,
Measure, joint handles and Position as tools, and Explode and Clip, without
discarding any of their values. The two modes keep separate cameras: entering
saves the tools view's camera and fits a preview camera at the default angle;
dragging in preview moves only that camera; leaving restores the tools view's
exact pose (in the projection and lens the Display settings now hold) and every
suspended tool with its panels. Preview's pose is never kept: the next preview
fits afresh. The viewport stays mounted throughout.

**Render profiles.** One viewport draws the same Display settings two ways
(`kit/viewport/renderProfile.js`). The tools view is drawn for working on the
model: the scene quality its settings resolve to, and a lower pixel ratio while
the camera moves so a gesture stays responsive. Preview is drawn for looking at
it: one scene-quality tier up (Interactive to Standard, Standard to High —
finer STEP tessellation, a higher idle pixel ratio, and at High larger shadow
and environment maps), its full pixel ratio kept while it orbits, and nothing
of the tools view's (no picking, overlays, cube or tool effects). The profile
never changes a Display setting.

## Keyboard

Escape and Copy belong to one viewer: the one with focus, or the one last
pressed in while focus is on the page. Editable targets keep their own keys.

- **Escape**, innermost first: an open popup in this viewer (a menu, the app menu
  included, a Select, a color picker, Display, the explorer) closes itself; then preview exits;
  then Draw's canvas spends its own Escape; then the renderer's (STEP: an
  unfinished measurement, then the Measure tool, then the selection, then
  isolation; robots: the selection). The tool stack's panels are never Escape's to
  close (a phone's sheet is dismissed like any sheet).
- **A panel's grip** (its bottom-right corner) is a separator in the tab
  order: Left/Right nudge its width and Up/Down its cap by 16px, and Home and
  End take both to their bounds.
- **Copy** (⌘C or Ctrl+C, and Ctrl+Insert) copies the drawing while Draw has
  ink, otherwise the selection's references — unless a text field has focus or
  text is selected. The Reference's and Drawing's Copy buttons show the shortcut
  in the platform's form (`⌘C` on macOS, `Ctrl+C` elsewhere).
- **Quick Edit's box** keeps its own keys: Enter presses the primary button and
  Shift+Enter is a new line. Escape hands the keyboard back to the view and keeps
  a note; in an empty box it closes the box and is also the viewer's own Escape
  (it clears the selection). ⌘C or Ctrl+C with none of its text selected is the
  viewer's copy.
- **Arrow keys and WASD** orbit the viewer that has focus or the pointer over
  it, never every mounted viewport; they do nothing in preview or with a
  modifier held.

## Tooltips and feedback

Every hint is a `TooltipHint`: compact text, one surface and arrow, a 400ms
delay. No native `title` anywhere in chrome. Prefer one or two words; show a
full technical name only when it is truncated (`overflowOnly`). Quick Edit's buttons, the
strip's buttons, the navbar's right-hand controls (the update, an alert's icon, a panel's
toggle, Full size) and the view's controls on top of the cube (Display, Preview, and
preview's Exit preview) are hinted by name — the strip's and the view's controls' hints
above their buttons, the others' below; there is no hint on the navbar's left (the logo,
the file's name and the ⋯ say what they are), on Playback settings, X,
the transport, drawing tools or labelled text buttons (Quick Edit's alone say what
they do). A disabled, selected or expanded control has none; pressing or leaving cancels a
pending one. A hint appears on focus only for keyboard navigation (a Tab), never
when a closing menu hands focus back.

The viewer shows no toasts or notifications: copy, snapshot and prompt actions
complete silently, the Copy and Quick Edit buttons showing a tick for a moment.
Progress stays in the viewport; a failed action is the
viewport's alert card, whose **Retry** reloads the file and whose **Report Issue**,
where the host has a tracker, opens a new issue titled "Issue: ", labelled `bug`, filled
in from the card; errors handed to the host's `onError` are the host's to show. A card the
model survives (a failed update, a warning beside the model) has an X, **Dismiss**: it puts
the card away for as long as that alert stands, and its icon, first of the navbar's
right-hand controls after the update button, brings it back. The dismissal goes once the alert changes or clears, or
another file opens; with the card back, so does the icon. Preview has no navbar, and so no
icon.

## Verification

Verify state transitions, touch cancellation, keyboard operation, nested popup
dismissal, feature availability, narrow panels and empty or error states.
Camera and kept-tool tests exercise real transitions, not class names. Do not
keep tests for discarded layouts: replace their assertions with coverage of this
contract. `src/designSystem.test.js` holds chrome to the type scale and the one
breakpoint. The core settings semantics are in
[render-mode.md](render-mode.md); update scheduling is in
[view-updates.md](view-updates.md).

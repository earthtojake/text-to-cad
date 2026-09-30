# Viewer interaction and settings design system

This is the binding contract for the viewer's tools, its tool stack and its
settings, in both apps. Build from the shared pieces — the
[toolbar button](../src/primitives/toolbar-button.jsx),
[FloatingToolBar](../src/renderers/kit/tools/FloatingToolBar.js),
[ToolPopover](../src/renderers/kit/tools/ToolPopover.jsx),
[ToolStack](../src/renderers/kit/tools/ToolStack.jsx),
[ToolPanel](../src/renderers/kit/tools/ToolPanel.jsx),
[the floating surface](../src/renderers/kit/tools/floatingSurface.js) and the
[FileSheet primitives](../src/renderers/kit/inspector/FileSheet.js) — and extend
them rather than recreating their layout in a renderer. Environmental effects
belong to apps through the [host contract](viewer-host.md).

## Ownership and layout

FileViewer owns the nav row, the breadcrumbs, the panel column (the file tree)
and which panel is open. RendererShell owns the scene's chrome: the toolbar, the
tool stack under it, the view cube, the bottom action, the playbar and
preview mode. Renderers supply their tools, their document state and their tool
panels; the shell never inspects a format's parts, joints or topology. A CAD
file's controls are never a panel of the host's column: no pick or tool opens,
closes or turns it.

| The host (web, desktop) supplies | The shared UI decides |
| --- | --- |
| Where the tab record lives (`TabRecordStorage`: the web's sessionStorage, the desktop's per-tab store) | The record: its settings (the tree, the tool stack's layout, the appearance) and each file's view (its camera, Display settings, Playback settings and renderer slices), what is written when, and what is never stored (`@text-to-cad/ui/tab-store`, `kit/shell/fileView.js`) |
| `leading`, `navigationActions` and `displayActions` (an appearance control) | The nav row's order, the snapshot action and the panel toggles |
| `host.files`, `fileActions`, `navigation`, `clipboard`, `promptContext` | When a copy, capture or open happens and what it carries |
| `host.environment`: color scheme, keyboard `platform`, `reducedMotion` | How the chrome honours them |
| `onError`, for errors the viewer hands up | Preview, tooltips, keyboard scope, the tool stack, the camera |

Hosts pass no preview, chrome-visibility or notification props; there are
none.

- **Nav row.** Leading content, breadcrumbs and the loading status, then host
  actions, the renderer's actions (the snapshot camera) and one toggle per
  declared panel, **Show files** last. A CAD file declares none: its toggle
  row is the file tree's alone.
- **Toolbar** at top-left, 8px in — the gap between it and the stack under it.
  At top-right, 2px in, the view cube sits above a centred bar of 20px
  transparent buttons with 12px icons: **Display settings** (cog),
  **Reset view**, then **Preview** (a play icon). Mobile uses the same cube and bar layout. In preview the same bar, in the same place, keeps Display and Reset, then an
  X where Preview was; **Playback settings** is the cog at the playbar's right
  end, and its menu opens upward.
- **Tool stack** beneath the toolbar: the panels of the tool in hand and of the
  effects a person keeps (see [The tool stack](#the-tool-stack)).
- **View cube** at top-right, 2px in, with a 2px gap before the 24px action bar below
  its 6rem area: enlarged face/edge/corner hit areas and neutral hover and XYZ
  guides. Preview omits it.
- **Bottom action** and **playbar** sit near bottom-centre, independent of the
  cube. For a composer destination, one white **Add To Prompt** button captures the current view and adds
  the file, selected references when present, and the screenshot through the
  host's prompt destination. It stays visible across tools and without a
  selection. Clipboard destinations retain the tool's **Copy Reference(s)**
  action for a selection and **Copy Drawing** while Draw has ink, with the
  normal primary styling and copy shortcut. With neither there is no bottom
  action; their snapshot action remains in file navigation. Preview hides
  bottom actions completely. The destination capability decides this behavior.
- **Model update status** sits at top-centre of the viewport, vertically centred
  in the same 34px row as the top-left toolbar in every host.
  It is renderer chrome, independent of the host's navigation status slot.
  On mobile it is a tappable progress icon whose popover names what is loading.

**Reset view** restores the opening orientation and fits the complete model,
returns Position to its default pose, clears selection, measurements and ink,
disables Clip and Explode, restores hidden parts, and returns to Select. It
keeps appearance preferences. This is distinct from Zoom to fit, which retains
the camera orientation. Renderer-specific tool state is reset through a callback
to the shared shell; no host or file-format branch belongs in the button.

## Tools and lifecycle

| File | Toolbar, left to right |
| --- | --- |
| STEP | Select, Position (movable joints only), Draw, Measure, Explode (two or more parts), Clip |
| URDF / SRDF / SDF | Select, Position (posable joints only) |
| GLB / STL / 3MF | none |
| DXF | none: a 2D canvas; composer Add To Prompt or clipboard navigation snapshot |

There is no separator or activity dot. There is no Animate tool: routines play in
[preview](#camera-animation-and-preview). Display is not a tool: every 3D
renderer has its **Display settings** button in the viewport's top-right bar,
beside Preview (see
[Display settings](#display-settings-and-section-primitives)). A file with no
tools has no strip at all.

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
| Select | The default tool of STEP and robots; shows Features (Links) and, with a selection, the Reference panel; a STEP's Select panel above them sets the mode | The selection is dropped; its panels leave the stack |
| Draw | Draws on the view; its tools, color and history are the Drawing panel; a second press puts it down | The sketch is gone |
| Measure | Arms picking and shows the Measure panel: its snapping modes, then its results; a press while it is up clears the results and puts it down | Unfinished picks are cancelled; completed measurements and their panel stay |
| Explode / Clip | Opens a neutral panel; an edit applies the effect | A neutral panel goes; an applied effect and its panel stay |
| Position | Shows joint handles and the Position panel; its icon carries a small dot while the pose is not the default | Handles and panel hide; joint values stay |

A tree is Select's panel, so it is used under Select; a tree row's menu action
returns to Select before it acts.

**Every tool's panel but Select's has an X, and no fold chevron.** The X puts
the tool down and returns to Select, the default tool, which cannot itself be put
down — its panels (Features or Links, Issues, SDF) fold instead.

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
Features filter row, beside its chevron; each menu row shows its mode's glyph
at full size. The strip's Select button shows the mode in hand as ONE composite:
the pointer, with the mode's glyph shrunk to a badge in its top-right corner
(cut out of the pointer so the two never touch at the strip's 14px), and the
bare pointer for All (`data-select-mode`). One drawing of each glyph serves
both sizes (`SelectionModes.jsx`). Parts is offered only in an assembly. Under the modes,
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
which the next time opens with. Choosing a drawing tool changes the toolbar
icon. Undo and Redo are disabled when their history is empty. The select tool uses lucide's
SquareMousePointer. The pencil and the shapes share one default stroke width.
While Draw has ink, a clipboard destination shows Copy Drawing; a composer
destination keeps Add To Prompt and captures the ink with the view. The copy
shortcut copies that drawing as a PNG. Draw disables the cube without hiding it.

**Measure.** Its **Measure** panel is up as soon as it is the tool, empty: a
heading whose mode menu, beside the chevron and the X, holds the four snapping
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
STEP's **Issues**, a `.sdf`'s **SDF**); Position's **Position**; then the panels
of the effects a person keeps (**Measurements**, **Explode**, **Clip**). A panel
whose tool is not up is `hidden`, not unmounted: a tree keeps its expansion,
filter and scroll across a trip to another tool. Preview hides the whole
stack.

- **Two kinds of panel.** The tree (Features, Links) and **Position** are
  *resizable*: the person's to size, each on its own. Every other panel —
  Drawing, Measurements, Explode, Clip, the Reference, Issues, SDF — is *fixed*:
  one width, its content's height, and no handle. The Reference is the one
  exception to the width: it sits under the tree and takes the tree's width
  (`widthFrom="tree"`), following a drag live, while its height stays fixed. A
  renderer opts a panel in with `resizable`; nothing else about it changes.
- **One width.** Every panel opens at `TOOL_PANEL_WIDTH`: 164px, a strip of
  six tools (six 24px buttons, 2px gaps, 4px padding and a 1px border),
  whatever tools the file's own strip has — a file with three tools has the
  same panels as one with seven. A fixed panel is exactly that wide. A
  resizable panel is only ever made wider, up to half the viewer; widening the
  tree changes nothing about any other panel. The panels hang left-aligned
  under the strip, each at its own width. Content truncates to fit; it never
  widens a panel.
- **Heights.** A panel is exactly its content's height — never padded to a
  minimum: a tree of two rows is its filter row and two rows. A resizable panel
  has a *cap* the content grows up to and then scrolls inside: the tree and
  Position open capped at half the stack's own height (the area under the
  strip, not the viewer) on desktop, and at the whole column on a phone. The
  Reference has a cap that is not the person's (288px, `maxHeight`: its heading
  and a dozen compact rows, so a part's or a face's facts and material fit
  without scrolling). A cap is never a floor. Setting one panel's cap changes
  no other's.
- **Handles, on a resizable panel only.** Three, each moving only that panel:
  one ON its right edge (width), one ON its bottom edge (height) and one on the
  bottom-right corner between them (both) — each centred on the edge, an 8px
  hit area (12px for the corner), nothing drawn: a resize cursor, and a focus
  ring for the keyboard. Named "Resize features width", "Resize features
  height" and "Resize features". By pointer, or by keyboard: arrows by 16px
  (Left/Right on the width's, Up/Down on the height's, all four on the corner),
  Home and End to an edge's bounds (the one width or half the viewer; 64px or
  the stack's height). One write, when the pointer lets go (or per key), never
  per pointer move. A folded panel keeps its width handle and has no height
  handle or corner: there is no height to set.
- **Never past the viewer.** The column is the viewer's height less the 8px
  insets and the strip. When the panels need more, the tree gives way first and
  scrolls inside itself, down to 128px or its content, whichever is less; then a
  details panel (Reference, Position, Measurements, Issues)
  gives way, down to 96px or its content; a small panel (Explode, Clip, Drawing)
  keeps its height. If what cannot give way still does not fit, the column
  itself scrolls — a panel is never cut. On mobile the tree starts folded and,
  opened, may take the whole column, giving way as other panels join it.
- **Folding.** Only Select's panels fold (Features or Links, Issues, SDF): every tool panel and the Reference has an X instead. A folding panel folds to its first row and unfolds again,
  by a chevron at that row's trailing end: up while open (fold), down while
  folded (open), with `aria-expanded` and the panel's name ("Collapse
  features"). Folded content stays mounted, so a tree keeps its expansion,
  selection and scroll. Typing into a
  folded tree's filter opens it, since what the filter finds is in its body; a
  folded filter row draws no rule under it.
- **First rows.** Features and Links have no heading: the filter is their top
  row ("Filter…"), stays put while the tree scrolls, and carries the mode menu
  (Select's) and the chevron at its end — both step aside while the box has
  focus, so the whole row is the box. Every other panel
  has a heading row, and every heading reads alike: the Display section
  headings' text (11px, regular, `TOOL_PANEL_HEADING_TEXT_CLASS`), 28px tall,
  8px in — a title; a summary where there is one (Explode's and Clip's amount);
  then, at its right
  end, its own actions (a mode or settings menu — Measure's —
  Position's Reset, the Reference's Copy), the chevron where it folds, and an X
  when there is something to remove. Every small button in a heading or a filter
  row is 20px, 2px apart and 4px from the edge, so the icons line up down the
  stack. The Reference's heading is the reference itself, then **Copy** (the
  reference on show — the one browsed to, with several selected — as Copy
  Reference copies it) and an X that clears the selection; a kept panel's X
  removes the effect.
- **The layout is the person's.** The sizes and the folded panels are one of the
  tab's settings, across its files (`CadPreferences.toolStack`:
  `{ panels: { [panel id]: { width?, height? } }, collapsed: { [panel id]: boolean } }`,
  kept beside the appearance). `panels` holds only what a person set, by
  resizable panel; `collapsed` only what differs from a panel's start (the SDF
  panel starts folded). A new tab (a cleared record) puts every
  panel back at the one width and its default cap. Every size is written back
  once, when the pointer lets go (or per key), never per pointer move.
- **Surfaces.** Two, defined once (`floatingSurface.js`), with one border: the
  toolbar and the stack's panels, which stay up beside the model, share
  `FLOATING_CHROME_SURFACE_CLASS` — the background at 35% and barely blurred
  (2px), so the model behind them is easy to make out; every menu and popover
  over the viewport shares `FLOATING_SURFACE_CLASS` (the background at 75%,
  blurred), so its text never competes with the model.
- **Scrolling.** Every scroll region in the viewer's chrome — a panel's body,
  the stack's column, the file tree, a menu, the alert card — is the
  `ScrollArea` primitive (`primitives/scroll-area.jsx`, shadcn's): thin overlay
  bars in the theme's colours, shown while the pointer is over the region. No
  native `overflow-auto` scroller in chrome; `src/designSystem.test.js` holds it.
- **Nothing opens elsewhere.** A pick shows its Reference in the stack; the
  Position tool shows its panel by being chosen. No pick or tool opens, closes
  or turns the host's panel column, on desktop or mobile.

Tree rows inset their backgrounds 4px from the panel edges, and the filter row
shares that inset. A tree in the stack (Features, Links) is dense (`TreeRowSurface`'s
`dense`): 24px rows in the panels' 11px text, 12px kind icons, a 16px disclosure
column with a small chevron, and 12px of indent per level; its filter row is a
heading's 28px, the box 20px tall and close to the row's walls. The host's file
tree keeps 28px rows. An assembly row's actions, shown on hover and kept while they
are on, are **Isolate** then the **Hide/Reveal** eye; a part file has no
Isolate. They float over the row's right end rather than taking width from it:
the name runs the row's full width and, while an action shows, fades out half a
rem before them (a mask, `ROW_NAME_UNDER_ACTIONS`), so nothing is drawn behind the
buttons and the row keeps its own colour.
Model and link filters share `TreeFilterInput`.

**Mobile** is below 720px of FileViewer width — the one viewer breakpoint
(`useViewerMobile`); chrome never uses window breakpoints. The tool stack is
the same stack, but Select's tree (Features, Links) starts folded, so the model
has the screen until the person opens it. The host's panels (the file tree) become non-modal floating
sheets over the viewer (280px, inset 8px) that never resize or move the scene
or shift the page; a sheet has a compact X, outside dismissal and Escape.
Breadcrumbs collapse to the current file's crumb; the cube and the shortcut
hint are hidden. Touch works for every tool: one finger orbits, two pan and
zoom, a tap picks; a pinch, a cancelled pointer or a camera drag is never a
pick.

**The file tree's column** (the host's) is 220px by default, 140px at least and
480px at most. A drag past the minimum stops at it; only a drag below half the
minimum closes the column, and the keyboard never does. The next open starts at
220px.

## Display settings and section primitives

Display is not a tool. Its button — the cog icon, "Display settings" — sits in the viewport's
top-right bar beside Preview, in the same place in the tools view and in
preview, and opens an ordinary popover end-aligned under it (`kit/shell/DisplayPopover.jsx`), 256px wide and
never taller than the viewer. Opening it leaves the tool in hand as it is: a
selection, a Draw session or Position stay. It goes with Escape, its button, or
a press anywhere but the model; a press on the model (to orbit and judge a
setting) and setting changes leave it up. It is the same popover, the same
settings, in preview: a change made in one mode is there in the other. Open in
preview, it holds preview's controls up.

One scroller (the popover's body), shared section primitives, no sticky headings
and no nested cards. Nested dropdowns and color pickers own their dismissal:
Escape closes the innermost popup first, the popover only on a later press.

| Section | Contents |
| --- | --- |
| Display | Full-width render Mode; Appearance (when the host gives one) and Projection beneath; a small gray Reset icon at top-right |
| Surfaces | Style and part-color mode; color or palette and opacity below |
| Edges | Visibility and color, where the format has topology |
| Grid / Axes | Two color/opacity controls, left and right in title order, no visible labels |
| Lighting | Quality, exposure, rotation, softbox size and fill |
| Background | Color and opacity |
| Floor | Color/opacity and placement |

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

## Position and references

The **Position** panel is headed "Position", with a small Reset icon and the
fold chevron in its heading, and is sized like the tree: its content's height,
capped at half the stack, with a height handle. Its first row is "Pose" — a label
beside its dropdown (`KinematicsPoseRow`) — only when there is a named pose to
choose; the dropdown includes Default, and manual edits show Custom. No divider
under the pose row and no Reset footer. Each joint's label sits tight above its
slider in the flexible left column, with a compact value field (24px tall, about
five characters wide, tabular figures; degrees read "90.0°") in the right column
of the same row; joint rows are 4px apart. Long labels truncate with a full-name
hint and never take the slider's width. Slider thumbs are named after their
joint, and every slider reports its value at its step's precision (never float
noise). Writes pose the model at once.

Position persists across tools. Reset restores the authored
values (an SRDF's home included), stops motion and hands control back to
Position. A routine playing in preview sets the Position values aside and gives
them back on leaving it. A Position edit, Reset included, stops and rewinds a
routine but keeps its Routine, Speed and Loop for the next play. Kinematics, named poses and
animation are separate capabilities; the absence of one never leaves empty
controls for another.

The Reference panel is read-only. Its rows are compact (2px above and below) and
in the panel's one face: labels and values alike are the UI font at `text-tiny`,
numbers in tabular figures — no monospace. A value too long for its cell wraps
between words, or (a row of numbers, such as a link's inertia) truncates with
its whole as a hint; a number never wraps inside itself. Its heading, flush with
the rows' labels, names the reference: its own label when it has one (a part's or subassembly's
name, a named face), otherwise its part and kind ("base · face 3") — never the
raw id, which is the **ID** row. With several references the heading is a
picker over them with a muted "i/N" beside the name — quiet on hover in either
theme (no fill; only its chevron comes up), and nothing about it moves; that picker is all a
multi-selection adds, and the rows are always the browsed reference's alone (no
totals, no count line). An X at the heading's end clears the selection. Copy
stays in row menus, the Reference heading and the copy shortcut. Clipboard
destinations also show Copy Reference or Copy References below the viewport;
composer destinations show Add To Prompt, which includes the selected
references with the screenshot. Every copied reference
carries its file prefix.

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

## Camera, animation and preview

Cube face, edge and corner clicks turn the view and keep pan and zoom; dragging
the cube orbits. Opening a file, or reloading the page, restores the camera the
file was left at in the tab, and fits it only when there is none. Display settings,
Explode/Clip, the pose, hidden and isolated parts and the tree's expansion come back
with it; the tool, the selection and measurements never do — every open starts in
the default tool with nothing selected.

Zoom to Fit recenters and frames the whole original model at the current angle;
Zoom to Selection frames the selection and is unavailable without one. Both are
STEP context-menu items; the live `resetCamera` command takes the same fit path.

**Preview** is available for every 3D file, animated or not, and is the shell's
own state (`previewing`); hosts neither start nor observe it. Its button is the
play icon in the top-right bar ("Preview"). It fills the viewer below the
host's nav row, which stays, and beside the host's column, which stays as it was
and can still be opened and shut; the toolbar, the tool stack and its resize
handles, joint handles, cube, bottom action and context menu are gone. It starts
orbiting, unless the file's Playback settings turned its orbit off. Its top-right bar is the tools view's bar in the same place:
**Display settings**, **Reset view** and an X ("Exit preview") where Preview was. **Playback
settings** (a cog; `PlaybackMenu`) ends the playbar under the model and opens
upward. It holds, for a file with routines, **Animation** — the Routine (with more than one), Speed, Loop and
Autoplay — then **Orbit**: on or off, and its speed. Under the model, an
animated file shows its playbar (play/pause, the scrubber, then the cog); a
static one an orbit play/pause and the cog. These controls share one one-second idle deadline and a 150ms
fade: movement wakes them, and hovering their area, an open menu or the Display
popover holds them.

Routines play in preview alone: there is no Animate tool. Entering preview
starts the routine when Autoplay is on (off by default); leaving it stops the
routine and puts the model back at rest, keeping the Routine for the next time
while the file is open. Everything in Playback settings is the file's own and is
remembered between leaving and re-entering preview and across a reload of the tab:
Orbit on or off (on by default) and its speed (1×), Autoplay, and a Speed or Loop
once chosen — until one is chosen, the routine's own apply. Another file has its
own. Nothing of the routine — which one, its time, whether it plays — is saved.
Orbit is not an animation setting.

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

- **Escape**, innermost first: an open popup in this viewer (a menu, a Select,
  a color picker, the Display popover) closes itself; then preview exits;
  then Draw's canvas spends its own Escape; then the renderer's (STEP: an
  unfinished measurement, then the Measure tool, then the selection, then
  isolation; robots: the selection). The tool stack's panels and the host's
  column are never Escape's to close.
- **Resize handles** (the stack's width, a panel's cap) are separators in the
  tab order: arrows nudge by 16px, Home and End go to the bounds, and a folded
  panel's handle opens it on ArrowDown or End.
- **Copy** (⌘C or Ctrl+C, and Ctrl+Insert) copies the drawing while Draw has
  ink, otherwise the bottom action's references — unless a text field has focus
  or text is selected. The bottom action shows the shortcut in the platform's
  form (`⌘C` on macOS, `Ctrl+C` elsewhere).
- **Arrow keys and WASD** orbit the viewer that has focus or the pointer over
  it, never every mounted viewport; they do nothing in preview or with a
  modifier held.

## Tooltips and feedback

Every hint is a `TooltipHint`: compact text, one surface and arrow, a 400ms
delay. No native `title` anywhere in chrome. Prefer one or two words; show a
full technical name only when it is truncated (`overflowOnly`). The top-right
bar's buttons are hinted by name (Reset view, Display settings, Preview, Playback settings);
there is no hint on Exit, X, the transport, drawing tools or labelled text buttons. A
disabled, selected or expanded control has none; pressing or leaving cancels a
pending one. A hint appears on focus only for keyboard navigation (a Tab), never
when a closing menu hands focus back.

The viewer shows no toasts or notifications: copy, snapshot and prompt actions
complete silently. Progress stays in the nav row; a failed action is the
viewport's alert card; errors handed to the host's `onError` are the host's to
show.

## Verification

Verify state transitions, touch cancellation, keyboard operation, nested popup
dismissal, feature availability, narrow panels and empty or error states.
Camera and kept-tool tests exercise real transitions, not class names. Do not
keep tests for discarded layouts: replace their assertions with coverage of this
contract. `src/designSystem.test.js` holds chrome to the type scale and the one
breakpoint. The core settings semantics are in
[render-mode.md](render-mode.md); update scheduling is in
[view-updates.md](view-updates.md).

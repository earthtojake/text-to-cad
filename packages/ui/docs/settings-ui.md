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
fullscreen. Renderers supply their tools, their document state and their tool
panels; the shell never inspects a format's parts, joints or topology. A CAD
file's controls are never a panel of the host's column: no pick or tool opens,
closes or turns it.

| The host (web, desktop) supplies | The shared UI decides |
| --- | --- |
| Storage of `FileViewerState`: open panel, width, expanded directories, renderer records | What a record holds, when it is written, what is never stored |
| Storage of the viewer preferences: orbit speed and the tool stack's width | Their format and bounds (`createStoredCadPreferences`) |
| `leading`, `navigationActions` and `displayActions` (an appearance control) | The nav row's order, the snapshot action and the panel toggles |
| `host.files`, `fileActions`, `navigation`, `clipboard`, `promptContext` | When a copy, capture or open happens and what it carries |
| `host.environment`: color scheme, keyboard `platform`, `reducedMotion` | How the chrome honours them |
| `onError`, for errors the viewer hands up | Fullscreen, tooltips, keyboard scope, the tool stack, the camera |

Hosts pass no fullscreen, chrome-visibility or notification props; there are
none.

- **Nav row.** Leading content, breadcrumbs and the loading status, then host
  actions, the renderer's actions (the snapshot camera) and one toggle per
  declared panel, **Show files** last. A CAD file declares none: its toggle
  row is the file tree's alone.
- **Toolbar** at top-left, 14px in. **Fullscreen** is a small transparent
  two-diagonal-arrows icon button at top-right, aligned with the toolbar.
- **Tool stack** beneath the toolbar: the panels of the tool in hand and of the
  effects a person keeps (see [The tool stack](#the-tool-stack)).
- **View cube** at bottom-right: enlarged face/edge/corner hit areas, neutral
  hover and XYZ guides, and nothing around it (no arrows, Home or Reset). Mobile
  and fullscreen omit it.
- **Bottom action** and **playbar** sit near bottom-centre, independent of the
  cube. The action is a content-sized button with the platform's copy shortcut
  beside its label; mobile omits the shortcut.
- **Loading status** sits after the filename in the nav row; on mobile it is a
  tappable progress icon whose popover names what is loading.

## Tools and lifecycle

| File | Toolbar, left to right |
| --- | --- |
| STEP | Select, Draw, Measure, Explode (two or more parts), Clip, Position (movable joints only), Animate (routines only), Display |
| URDF / SRDF / SDF | Select, Position (posable joints only), Display |
| GLB | Animate (clips only), Display |
| STL / 3MF | Display |
| DXF | none: a 2D canvas with the snapshot action only |

There is no separator or activity dot. Animate is always the last tool before
Display, and Display is last in every 3D renderer.

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
| Select | The default tool of STEP and robots; shows Features (Links) and, with a selection, the Reference panel; the STEP corner menu sets the mode | The selection is dropped; its panels leave the stack |
| Draw | Draws on the view; its tools, color and history are the Drawing panel; a second press puts it down | The sketch is gone |
| Measure | Arms picking; the corner menu chooses snapping | Unfinished picks are cancelled; completed measurements stay |
| Explode / Clip | Opens a neutral panel; an edit applies the effect | A neutral panel goes; an applied effect and its panel stay |
| Position | Shows joint handles and the Position panel | Handles and panel hide; joint values stay |
| Animate | Starts playback; the corner menu holds Routine, Speed and Loop | Playback stops and the model returns to rest; Routine, Speed and Loop stay |
| Display | Shows the Display panel at the top of the stack; a second press or Escape puts it down | The panel goes and the default tool returns; settings stay |

A tree is Select's panel, so it is used under Select; a tree row's menu action
returns to Select before it acts.

**Corner menus.** A corner triangle marks a tool whose options are a temporary
menu. The first press takes up the tool, wherever it lands; a press while the
tool is active opens the menu, and pressing again closes it. Enter, Space and
ArrowDown select an inactive tool before they open anything. Menus are
`ToolPopover`s (keyboard access, outside dismissal, Escape). **A corner menu is
an ordinary dropdown under its own button, start-aligned, and may overlap the
tool stack while it is open; only persistent panels live in the stack.** A
closed menu unmounts at once, with no exit animation, so a quick second tap
(touch included) always reaches the trigger. Choosing a value closes an
ordinary option menu. Menu checks sit on the right.

**Select** (STEP) has four exclusive modes, each with its own icon, and the
strip's Select button shows the mode in hand: **All** (the pointer), **Parts**
(a cube), **Faces** (a cube, its top face filled) and **Edges** (a faint cube,
one edge heavy). Parts is offered only in an assembly. Below a rule, two
checkboxes — **Edge chain** and **Tangent faces** — change how a pick grows,
independently of the mode and of each other: Tangent faces applies under All
and Faces, Edge chain under All and Edges; elsewhere it stays in the menu,
disabled, its choice kept. Ticking one leaves the menu open. Nothing under the
strip names the mode. The mode sets the Features tree's shape: under **All** it
is the person's own (put back as it was when they left All, with the owners of
what is still selected kept open); **Parts** opens every assembly and shuts
every part; **Faces** and **Edges** open everything down to the features whose
faces and edges are picked. Outside All the disclosure is locked (chevrons
shown, not pressable) and Expand/Collapse leave the menus. Under Faces or Edges
a part's topology is asked for as its row comes on screen in the tree, never for
a whole large assembly at once; a viewport press on a part not yet loaded loads
that part and picks, and the Features filter row says "Loading…" meanwhile.

**Draw.** Its **Drawing** panel leads the stack while Draw is up: a tools grid
and a settings row (Color, Undo, Redo, Clear) separated by a rule, without
headings and without a corner menu. Choosing a drawing tool changes the toolbar
icon. Undo and Redo are disabled when their history is empty. The select tool uses lucide's
SquareMousePointer. The pencil and the shapes share one default stroke width.
While Draw has ink, the bottom action is **Copy Drawing** (the view with its
ink, as a PNG to the clipboard). Draw disables the cube without hiding it.

**Measure.** A measurement makes a results panel only once it is complete: no
empty panel and no "pick two points" prompt. With results, pressing Measure or
the panel's X clears them all, and the corner resumes picking and opens
snapping. Removing the last result returns Measure to ordinary picking. There is
no Clear All footer.

**Explode and Clip** are toggles with no enabled checkbox. Explode opens at 0%,
Clip at no cut; an edit applies the effect and the panel is then kept. A panel
still at its neutral value goes when another tool is chosen, or when the pointer
is released after a drag that ended at neutral — never mid-drag. Pressing the
tool again while its panel shows is the same as its X: the effect is removed and,
if the tool held the pointer, Select returns. Axis or Flip alone is not an effect. The view settings
own both effects, so a Display Reset removes their panels and a restored effect
reappears with its panel without another press. Clip has one axis/Flip row and
one slider row: left to right cuts deeper through the original bounding box;
Flip keeps the other half at the same plane; pose, animation and Explode never
redefine the range. With fewer than two parts Explode is not on the strip.

**Display** is a tool whose panel is its settings. It takes the pointer from any
tool, Draw included, and kept panels stay highlighted beside it. See
[Display panel and section primitives](#display-panel-and-section-primitives).

## The tool stack

Under the toolbar, in one column: the shell's tools' panels (**Display**,
**Drawing**) while their tool is up; Select's **Features** (STEP; a robot's
**Links**) and, whenever something is selected, its **Reference** (then STEP's
**Issues**, a `.sdf`'s **SDF**); Position's **Position**; then the panels of the
effects a person keeps (**Measurements**, **Explode**, **Clip**). A panel whose
tool is not up is `hidden`, not unmounted: a tree keeps its expansion, filter
and scroll across a trip to another tool. Fullscreen hides the whole stack.

- **One width.** Every panel is the stack's width. The default is the strip of
  the base STEP toolset plus one tool — seven 24px buttons, 2px gaps, 4px
  padding and a 1px border: 190px. A handle in a 4px gutter right of the stack
  widens or narrows every panel together, from 160px up to half the viewer, by
  pointer or keyboard (Arrows, Home, End). The width is a viewer preference the
  host keeps across files (`CadPreferences.toolStackWidth`, stored beside the
  orbit speed). Content truncates to fit; it never widens the stack.
- **Height.** Panels take their natural height; the column is the viewer's
  height less the 14px insets, never more. When the panels need more, the tree
  panel gives way first and scrolls inside itself down to a 128px floor; then a
  details panel (Reference, Position, Measurements, Display) gives way down to
  96px; a small panel (Explode, Clip, Drawing) keeps its height. The Reference
  panel is never taller than its heading and eight 24px rows. On mobile the
  tree takes at most 40% of the column.
- **Headings.** A panel has a heading row only when it has something to do
  there. Features and Links have none: the filter is their top row and stays
  put while the tree scrolls. Position has none (its Pose row leads it), nor
  has Display or Drawing. The Reference's heading is the reference itself and
  an X that clears the selection. A kept panel has a title, a summary, a
  collapse chevron (a view only) and an X that removes the effect.
- **Surface.** The toolbar, every stack panel and every menu or popover over
  the viewport share one surface (`FLOATING_SURFACE_CLASS`): the background at
  75% under a medium backdrop blur, with the border token. With a full stack
  over the planetary gear assembly and `juno.step`, orbiting measured the same
  frame time with the blur as without it.
- **Nothing opens elsewhere.** A pick shows its Reference in the stack; the
  Position tool shows its panel by being chosen. No pick or tool opens, closes
  or turns the host's panel column, on desktop or mobile.

Tree rows inset their backgrounds 4px from the panel edges, and the filter row
shares that inset. Rows are 28px, with a 20px disclosure column and 12px of
indent per level. An assembly row's actions, shown on hover and kept while they
are on, are **Isolate** then the **Hide/Reveal** eye; a part file has no
Isolate. Model and link filters share `TreeFilterInput`.

**Mobile** is below 720px of FileViewer width — the one viewer breakpoint
(`useViewerMobile`); chrome never uses window breakpoints. The tool stack is
the same stack. The host's panels (the file tree) become non-modal floating
sheets over the viewer (280px, inset 8px) that never resize or move the scene
or shift the page; a sheet has a compact X, outside dismissal and Escape.
Breadcrumbs collapse to the current file's crumb; the cube and the shortcut
hint are hidden. Touch works for every tool: one finger orbits, two pan and
zoom, a tap picks; a pinch, a cancelled pointer or a camera drag is never a
pick.

**The file tree's column** (the host's) is 280px by default, 200px at least and
480px at most. A drag past the minimum stops at it; only a drag below half the
minimum closes the column, and the keyboard never does. The next open starts at
280px.

## Display panel and section primitives

Display uses the render-sphere icon. While it is the tool, its settings are the
first panel of the stack, the stack's width, left-aligned under the toolbar.
Setting changes, and presses on the model, never close it; the button again or Escape puts Display down
and returns the default tool.

One scroller (the panel's body), shared section primitives, no sticky headings
and no nested cards. Nested dropdowns and color pickers own their dismissal:
Escape closes the innermost popup first, Display only on a later press.

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

"Pose" is a label above a full-width dropdown, with a small Reset icon opposite
the label (`KinematicsPoseRow`). The dropdown includes Default; manual edits
show Custom. Without named poses the row is "Position" and Reset alone. No
divider under the pose row and no Reset footer. Each joint's label sits tight
above its slider in the flexible left column, with a standard value input in
the right column of the same row; joint rows are 8px apart under an 8px top
inset. Long labels truncate with a full-name hint and never take the slider's
width. Slider thumbs are named after their joint. Writes pose the model at once.

Position persists across tools. Reset restores the authored
values (an SRDF's home included), stops motion and hands control back to
Position. Animate sets the Position values aside and gives them back when it
lets go. A Position edit, Reset included, stops and rewinds a routine but keeps
Animate's Routine, Speed and Loop for the next play. Kinematics, named poses and
animation are separate capabilities; the absence of one never leaves empty
controls for another.

The Reference panel is read-only. Its heading, flush with the rows' labels,
names the reference: its own label when it has one (a part's or subassembly's
name, a named face), otherwise its part and kind ("base · face 3") — never the
raw id, which is the **ID** row. With several references the heading is a
picker over them with a muted "i/N" beside the name; that picker is all a
multi-selection adds, and the rows are always the browsed reference's alone (no
totals, no count line). An X at the heading's end clears the selection. Copy
lives in the bottom action — **Copy Reference** or **Copy References**, never
the ids — shown only for an actual, usable selection. Every copied reference
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

## Camera, animation and fullscreen

Cube face, edge and corner clicks turn the view and keep pan and zoom; dragging
the cube orbits. Opening a file, or reloading the page, fits the model: the
camera is never persisted. Display settings, the tool, the pose and Explode/Clip
are, per file.

Zoom to Fit recenters and frames the whole original model at the current angle;
Zoom to Selection frames the selection and is unavailable without one. Both are
STEP context-menu items; the live `resetCamera` command takes the same fit path.

Animate starts playback when pressed. Its corner menu holds Routine (with more
than one), Speed and Loop. The playbar under the model owns pause, scrub and
restart and has no settings of its own. Orbit is not an Animate setting.

**Fullscreen** is available for every 3D file, animated or not, and is the
shell's own state (`presenting`); hosts neither start nor observe it. It fills
the viewer below the host's nav row, which stays; the host's column is hidden
and its toggles disabled; the toolbar, the tool stack, cube, bottom action and
context menu are gone. It starts orbiting. Its top-right controls are an Animation menu
(Play icon, the same Routine/Speed/Loop menu as Animate) for animated files, an
Orbit menu (Orbit on/off and Speed) and Exit (X). An animated file shows its
playbar; a static one shows an orbit play/pause. These controls share one
one-second idle deadline and a 150ms fade: movement wakes them, and hovering
their area or an open menu holds them.

Presenting turns off picks, hover, selection highlights, recognition, Draw,
Measure, joint handles, Animate and Position as tools, and Explode and Clip,
without discarding any of their values. Entering saves the camera and fits a
presentation camera; leaving restores the exact camera, the host's column as it
was and every suspended tool with its panels. The viewport stays mounted throughout.

## Keyboard

Escape and Copy belong to one viewer: the one with focus, or the one last
pressed in while focus is on the page. Editable targets keep their own keys.

- **Escape**, innermost first: an open popup in this viewer (a menu, a Select,
  a color picker) closes itself; then fullscreen exits; then Display is put
  down; then Draw's canvas spends its own Escape; then the renderer's (STEP: an
  unfinished measurement, then the Measure tool, then the selection, then
  isolation; robots: the selection). The tool stack's panels and the host's
  column are never Escape's to close.
- **Copy** (⌘C or Ctrl+C, and Ctrl+Insert) copies the drawing while Draw has
  ink, otherwise the bottom action's references — unless a text field has focus
  or text is selected. The bottom action shows the shortcut in the platform's
  form (`⌘C` on macOS, `Ctrl+C` elsewhere).
- **Arrow keys and WASD** orbit the viewer that has focus or the pointer over
  it, never every mounted viewport; they do nothing in fullscreen or with a
  modifier held.

## Tooltips and feedback

Every hint is a `TooltipHint`: compact text, one surface and arrow, a 400ms
delay. No native `title` anywhere in chrome. Prefer one or two words; show a
full technical name only when it is truncated (`overflowOnly`). No hint on
Fullscreen, Exit, X, the transport, drawing tools or labelled text buttons. A
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

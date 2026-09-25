# Viewer interaction and settings design system

This is the binding contract for the viewer's tools, sidebars and settings, in
both apps. Build from the shared pieces — the
[toolbar button](../src/primitives/toolbar-button.jsx),
[FloatingToolBar](../src/renderers/kit/tools/FloatingToolBar.js),
[ToolPopover](../src/renderers/kit/tools/ToolPopover.jsx),
[ToolPanel](../src/renderers/kit/tools/ToolPanel.jsx),
[FileSheet primitives](../src/renderers/kit/inspector/FileSheet.js),
[FilePanelSections](../src/renderers/kit/inspector/FilePanelSections.jsx) and
[FilePanelTabs](../src/renderers/kit/inspector/FilePanelTabs.jsx) — and extend
them rather than recreating their layout in a renderer. Environmental effects
belong to apps through the [host contract](viewer-host.md).

## Ownership and layout

FileViewer owns the nav row, the breadcrumbs, the panel column and which panel
is open. RendererShell owns the scene's chrome: the toolbar, the Display
popover, kept tool panels, the view cube, the bottom action, the playbar and
fullscreen. Renderers supply their tools, their document state and their
Settings panel's sections; the shell never inspects a format's parts, joints or
topology.

| The host (web, desktop) supplies | The shared UI decides |
| --- | --- |
| Storage of `FileViewerState`: open panel, width, expanded directories, renderer records | What a record holds, when it is written, what is never stored |
| `leading`, `navigationActions` and `displayActions` (an appearance control) | The nav row's order, the snapshot action and the panel toggles |
| `host.files`, `fileActions`, `navigation`, `clipboard`, `promptContext` | When a copy, capture or open happens and what it carries |
| `host.environment`: color scheme, keyboard `platform`, `reducedMotion` | How the chrome honours them |
| `onError`, for errors the viewer hands up | Fullscreen, tooltips, keyboard scope, panel reveal, the camera |

Hosts pass no fullscreen, chrome-visibility or notification props; there are
none.

- **Nav row.** Leading content, breadcrumbs and the loading status, then host
  actions, the renderer's actions (the snapshot camera) and one toggle per
  panel: the file's **Settings** (sliders icon) when it has one, then
  **Show files** last.
- **Toolbar** at top-left, 14px in. **Fullscreen** is a small transparent
  two-diagonal-arrows icon button at top-right, aligned with the toolbar.
- **Kept tool panels** stack beneath the toolbar: 160px wide, 8px apart, in one
  scroller bounded by the viewport. Each is a `ToolPanel` with a collapse
  chevron (visibility only) and an X (removes and resets the effect).
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
| STEP | Select, Draw, Measure, Explode, Clip, Position (movable joints only), Animate (routines only), Display |
| URDF / SRDF / SDF | Select, Position (posable joints only), Display |
| GLB | Animate (clips only), Display |
| STL / 3MF | Display |
| DXF | none: a 2D canvas with the snapshot action only |

There is no separator or activity dot. Animate is always the last tool before
Display, and Display is last in every 3D renderer.

One tool owns pointer input. A kept effect (an Explode, Clip or Measure panel)
stays highlighted beside it; a highlighted kept effect is not a second pointer
owner.

| Tool | Pressing it | Leaving it |
| --- | --- | --- |
| Select | The default tool of STEP and robots; the STEP corner menu sets the selection filter | The selection is dropped |
| Draw | Draws on the view; the corner menu holds drawing tools, color and history | The sketch is gone |
| Measure | Arms picking; the corner menu chooses snapping | Unfinished picks are cancelled; completed measurements stay |
| Explode / Clip | Opens a neutral panel; an edit applies the effect | A neutral panel goes; an applied effect and its panel stay |
| Position | Shows joint handles and reveals the Position tab (desktop) | Handles hide; joint values stay |
| Animate | Starts playback; the corner menu holds Routine, Speed and Loop | Playback stops and the model returns to rest; Routine, Speed and Loop stay |
| Display | Selects Display and opens its popover | The popover closes and the default tool returns; settings stay |

Choosing something in a tree under another tool returns to Select first.

**Corner menus.** A corner triangle marks a tool whose options are a temporary
menu. The first press takes up the tool, wherever it lands; a press while the
tool is active opens the menu, and pressing again closes it. Enter, Space and
ArrowDown select an inactive tool before they open anything. Menus are
`ToolPopover`s (keyboard access, outside dismissal, Escape) and open beside kept
tool panels, never over them. Choosing a value closes an ordinary option menu.
Menu checks sit on the right.

**Draw.** Its menu has a tools row and a settings row separated by a rule,
without headings. Choosing a drawing tool changes the toolbar icon and closes
the menu; Color, Undo and Redo keep it open; Clear closes it. Undo and Redo are
disabled when their history is empty. The select tool uses lucide's
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
redefine the range. Explode is unavailable with fewer than two parts.

**Display** is a popover tool, not a sidebar tab. It takes the pointer from any
tool, Draw included, and kept panels stay highlighted beside it. See
[Display popover and section primitives](#display-popover-and-section-primitives).

## Sidebars and mobile

A file type has at most one **Settings** panel, under the sliders icon. It is
never named for the file (no Part, Assembly or Robot titles), and camera or
snapshot actions never become panels. Neither the file tree nor Settings has a
visible title bar; each keeps an accessible name.

| File | Settings |
| --- | --- |
| STEP | **Features** (the model tree, then Issues when there are any) and **Position** when the file has movable joints |
| Robot | **Links** (then SDF metadata for an `.sdf`) and **Position** when it has posable joints |
| GLB, mesh, DXF | none |

Sections declare `role: "model"` or `role: "position"`; `FilePanelTabs` shows
two tabs only when both exist, and one column of sections otherwise. Inactive
tabs stay mounted (their content is told `active=false`). The selected tab is
shell state, so it survives the panel remounting across the breakpoint.

**Defaults on open.** A file opened directly opens with its Settings, or with
nothing when it has none; the file tree opens by default only when no file is
open. A file picked in the tree keeps the tree up while a person walks it.

**Reveal on pick.** Any open sidebar — the file tree included — turns to the
file's Settings on a pick (Features or Links) and on the
Position tool (Position, including a repeated press). A pick never opens a
closed sidebar; the Position tool does. Draw, Measure, Explode, Clip, Animate
and Display never choose a tab. On mobile, no tool or pick opens a sheet or
turns a tab.

**Width.** One panel column for every panel: 280px by default, 256px minimum,
480px maximum. Dragging below the minimum collapses it, and the next open starts
at 280px. The handle also resizes from the keyboard.

**Mobile** is below 720px of FileViewer width — the one viewer breakpoint
(`useViewerMobile`); chrome never uses window breakpoints. Panels become
non-modal floating sheets over the viewer (280px, inset 8px) that never resize
or move the scene or shift the page. A file opens with no sheet over it (an
empty tab still opens on its tree); a sheet has a compact X, outside dismissal
and Escape. The desktop panel choice and width are kept for
when the viewer widens again. Breadcrumbs collapse to the current file's crumb;
the cube and the shortcut hint are hidden.

Model and link filters share `TreeFilterInput`. Trees and Position scroll in
their own tab's single scroller; the pinned Reference is a sibling pane below,
not a nested scroller. Touch works for every tool: one finger orbits, two pan
and zoom, a tap picks; a pinch, a cancelled pointer or a camera drag is never a
pick.

## Display popover and section primitives

Display uses the render-sphere icon and a 256px popover capped at 520px or the
available height, anchored under its button or beside kept tool panels. Setting
changes never close it. Closing it — the button again, an outside press or
Escape — returns to the default tool.

One scroller, shared section primitives, no sticky headings and no nested cards.
Nested dropdowns and color pickers own their dismissal: Escape or an outside
press closes the innermost popup first, the popover only on a later gesture.

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

Sidebar sections outside the popover may use sticky headings: earlier headings
stack at the top of the single scroller, later ones at the bottom. Every section
but the first has a top border. Revealing a section unfolds it if folded and
scrolls within the natural range, never adding blank space to force it to the
top; ordinary edits do not scroll. A heading hidden by its tab needs no header
offset.

Type comes from the token scale only (`text-micro` 10px, `text-tiny` 11px,
`text-xs` 12px, `text-ui` 13px); no pixel font sizes. Settings controls and the
popover's headings use `text-tiny`, regular weight, with shared 28px controls;
sidebar section headings use 12px. Sections use 8px gutters and bottom insets
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

Position persists across tools and sidebar changes. Reset restores the authored
values (an SRDF's home included), stops motion and hands control back to
Position. Animate sets the Position values aside and gives them back when it
lets go. A Position edit, Reset included, stops and rewinds a routine but keeps
Animate's Routine, Speed and Loop for the next play. Kinematics, named poses and
animation are separate capabilities; the absence of one never leaves empty
controls for another.

The Reference pane is read-only, with a static heading and an X to clear. Copy
lives in the bottom action — **Copy Reference** or **Copy References**, never
the ids — shown only for an actual, usable selection. Every copied reference
carries its file prefix.

Viewport picks reach individual faces and edges even where the tree groups them
into a feature. In an assembly, faces and edges load per part, when first
needed: under a face or edge filter, a press on a part whose faces are not
loaded loads that part alone and then picks what is under the pointer — one
press, with "Loading selectable geometry…" under the toolbar meanwhile. Until
then, hovering such a part lights the whole part.
Shift-click adds to a selection in the viewport; Shift, Ctrl or Cmd does in a
tree (robots select several links this way). Double-click isolates a component
or subassembly; double-click on empty space leaves isolation, as does the
isolation bar's Exit. Only topology that cannot be isolated copies on
double-click, and it stays selected. A tree row's one action is Hide, on hover.
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
the viewer below the host's nav row, which stays; the sidebar is hidden and its
toggles disabled; the toolbar, kept panels, cube, bottom action and context
menu are gone. It starts orbiting. Its top-right controls are an Animation menu
(Play icon, the same Routine/Speed/Loop menu as Animate) for animated files, an
Orbit menu (Orbit on/off and Speed) and Exit (X). An animated file shows its
playbar; a static one shows an orbit play/pause. These controls share one
one-second idle deadline and a 150ms fade: movement wakes them, and hovering
their area or an open menu holds them.

Presenting turns off picks, hover, selection highlights, recognition, Draw,
Measure, joint handles, Animate and Position as tools, and Explode and Clip,
without discarding any of their values. Entering saves the camera and fits a
presentation camera; leaving restores the exact camera, the sidebar as it was
and every suspended tool. The viewport stays mounted throughout.

## Keyboard

Escape and Copy belong to one viewer: the one with focus, or the one last
pressed in while focus is on the page. Editable targets keep their own keys.

- **Escape**, innermost first: an open popup in this viewer (a menu, a Select,
  the Display popover) closes itself; then fullscreen exits; then Draw's
  canvas spends its own Escape; then the renderer's (STEP: an unfinished
  measurement, then the Measure tool, then the selection, then isolation;
  robots: the selection); then the open Settings panel closes.
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

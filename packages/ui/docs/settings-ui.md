# Viewer interaction and settings design system

This is the binding contract for shared viewer tools, sidebars and settings.
Use [FileSheet primitives](../src/renderers/kit/inspector/FileSheet.js),
[FilePanelSections](../src/renderers/kit/inspector/FilePanelSections.jsx) and
[toolbar primitives](../src/renderers/kit/tools/ToolbarButton.js). Extend these
shared components rather than recreating their layout in individual renderers.
Environmental effects belong to apps through the [host contract](viewer-host.md).

## Ownership and layout

The host-owned FileViewer owns the navbar, breadcrumbs, panel
frame and panel visibility. RendererShell owns the scene's toolbar, display
popover, persistent tool panels, view cube, bottom actions and presentation.
Renderers supply capabilities, tool definitions, document state and panel content;
the shell must not inspect a format's parts, joints or topology.

- The toolbar sits at top-left. Fullscreen is a separate small transparent
  diagonal-arrows button at top-right, aligned with the toolbar.
- STEP orders its available tools Select, Draw, Measure, Explode, Clip, Position,
  Animate, Display. There is no separator or activity dot. Display is available
  in every 3D renderer; Animate appears only with animation clips.
- Persistent tool panels stack beneath the toolbar, 160px wide with 8px gaps and
  a viewport-constrained scroller. They use `ToolPanel`, including its collapse
  and X actions. Collapse changes visibility; X removes and resets the tool.
- The draggable view cube is bottom-right on desktop, with enlarged face/edge/
  corner hit areas, neutral hover feedback and XYZ guides. No surrounding arrow,
  Home or Reset buttons. Mobile omits the cube.
- Bottom actions and the playbar sit near bottom-center, independently of the
  cube's dimensions. Copy CTAs use content-sized buttons and platform-appropriate
  keyboard hints; mobile omits the shortcut hint.
- Loading status sits after the filename/menu in the navbar. Notifications are
  compact and right-aligned below the navbar, unaffected by sidebar width. Name
  the completed action, such as “Reference copied,” rather than transport details.

## Tools and lifecycle

One tool owns pointer input. Retained effects may remain highlighted alongside
it; a highlighted retained effect is not another pointer owner.

| Tool | Activation and options | Leaving the tool |
| --- | --- | --- |
| Select | Default for STEP and robots; corner menu narrows selection where supported | Clear selected parts/topology/links |
| Draw | Select drawing mode; corner menu offers drawing tools and history/color actions | Clear the sketch |
| Measure | Arm picking; corner menu chooses snapping | Cancel unfinished picks; retain completed measurements |
| Explode / Clip | Open a neutral panel; edits apply the effect | Remove a neutral panel; retain a nonzero effect |
| Position | Enable joint handles; reveal Position on desktop | Hide handles; retain joint values |
| Animate | Start playback; corner menu contains Routine, Speed and Loop | Stop playback and restore the renderer's base motion state |
| Display | Select the tool and open its properties sheet | Close the sheet and return to Select; retain settings |

Corner triangles indicate temporary menus only. First activation selects the
tool, including a press on its corner; a subsequent press opens options. Use
`ToolPopover`, with keyboard access, outside dismissal and Escape. Choosing a
value closes ordinary option menus. A selected tool has no tooltip.

Draw's menu has tools and settings rows separated by a rule, without headings.
Selecting a drawing tool changes the main icon and closes the menu. Color, Undo
and Redo keep it open; Clear closes it. Undo/Redo reflect their actual history
stacks. Draw selection uses SquareMousePointer. Pencil and geometric marks use
the same default stroke thickness.

A measurement creates a retained results panel only when completed. No empty
panel or “pick two points” prompt. With results, the main Measure button and X
clear all results; its corner resumes picking and opens snapping options. Removing
the last result returns Measure to ordinary picking behavior. No Clear All footer.

Explode and Clip have no enabled checkbox. Explode opens at 0%; Clip at 0% cut.
Clicking a retained tool again is equivalent to X. Returning its value to neutral
makes the panel temporary again; changing axis or Flip alone is not an effect.
Canonical settings own these effects. External Reset must update panels too;
restored nonzero effects get panels without requiring another toolbar click.

Clip uses one axis/Flip row and one slider/value row. Left-to-right increases cut
percentage through the original model bounding box. Flip reverses the retained
half, preserving an active plane's coordinate. Pose, animation and Explode do
not silently redefine the slider's range. At 0% there is no clipping. Explode
is unavailable with fewer than two parts.

## Sidebars and mobile

Each renderer may register at most one optional **Settings** navbar entry, with
the sliders icon. Camera/snapshot actions are actions, not extra settings tabs.
The file explorer and settings sheets have no redundant visible title bars;
retain accessible dialog names.

A STEP's settings contain Features and, when available, Position. Robots use
Links and Position; Links is the established robot-description term. Show an
internal tab strip only when both exist. Keep inactive contents mounted, passing
`active=false` to expensive content. Issues belong with Features; SDF metadata
belongs with Links. Display is a toolbar popover, never a sidebar tab.

Desktop sidebar navigation is intentional:

- Position explicitly opens its tab, including a repeated activation.
- Selecting Select alone does not switch tabs. A selection can show Features or
  Links when Settings is already open; it does not reopen a closed sidebar.
- Draw, Measure, model effects, Animate and Display do not choose sidebar tabs.
- Fullscreen temporarily hides/disables panels and restores the previous panel,
  width and internal tab on exit.

Use one breakpoint at 720px of the entire FileViewer. Desktop panels resize with
one shared frame (256px minimum; reopening a collapsed panel starts at 280px).
Mobile panels are nonmodal floating sheets over the viewer; they never resize
or translate the scene or lock/shift the surrounding page. They start closed,
with a compact X, outside dismissal and Escape. Preserve the desktop selection
and width across the breakpoint. Tool-driven panel opening **and tab switching**
are disabled on mobile. Breadcrumbs show the current filename and menu only;
status becomes a tappable progress icon.

Model and link filters share `TreeFilterInput` sizing and insets, including the
reduced top inset beneath a heading. Trees and Position scroll in their own
active tab's single scroller. A pinned Reference inspector is a sibling pane,
not a nested tree scroller. One-finger orbit, two-finger pan/zoom and tool taps
must work on touch. A pinch, pointer cancellation or camera drag is not a pick.

## Settings sheet and primitives

Display uses the render sphere icon and a 256px popover capped at 520px or the
available viewport height. It is a tool: it remains usable during Draw and
activating it leaves the previous tool. Closing its sheet returns to Select. Settings changes never dismiss the sheet.

Use one scroller, shared section primitives, non-sticky headings and no nested
cards. Nested dropdowns/color pickers own their dismissal: Escape or an outside
click dismisses the innermost popup first, then the sheet on a later gesture.

| Section | Contents |
| --- | --- |
| Display | Full-width render Mode; Appearance and Projection beneath it; small gray Reset at top-right |
| Surfaces | Style and part-color mode; color/palette and opacity below |
| Edges | Visibility and color, where the format supports topology |
| Grid / Axes | Two color/opacity controls, left/right in title order; no redundant visible labels |
| Lighting | Quality, exposure, rotation, softbox size and fill |
| Background | Color and opacity |
| Floor | Color/opacity and placement |

Display and Surfaces stay open. Other sections use a plus/minus feature gate:
expanded means enabled, collapsed means disabled. Grid / Axes gates both groups;
their settings remain separate in the core/CLI contract. Never add a second
“Enabled” checkbox inside a gated section. Enabling starts at defaults; disabling
removes overrides. A heading click reveals enabled content without disabling it;
only minus disables. Hover, focus and rendering completion never write settings.

Mode presets are shortcuts over the same controls. Manual overrides show Custom,
which is not a selectable preset. Reset restores the chosen preset and clears
Clip/Explode; it does not reset pose, camera, app appearance or orbit preferences.
Appearance is host-owned Light/Dark/System. When System is stored, its trigger
shows the resolved Light or Dark icon/value; the menu still marks System.

Sections outside the short Display popover may use sticky headers: earlier
headers stack at the top and later headers at the bottom of the single scroller.
Use a top border except on the first section. Revealing a section expands it if
folded and scrolls within the natural range; never add blank space to force it
to the top. Ordinary edits do not scroll. Hidden tab headings need no artificial
header offset.

Settings controls and Display headings use `text-tiny` (11px), regular weight
and shared 28px control sizing. Sidebar section headings use 12px. Use 8px section gutters/bottom insets and 4px row/column gaps.
`FileSheetFieldGrid` owns horizontal spacing; its children must not double-pad.
Menu/select/context-menu typography comes from the primitives, including portals.
Checkmarks sit on the right. Icons appear in selected values where meaningful.

Use `FileSheetSliderField` for a useful bounded range and committed number input,
`FileSheetNumberProperty` for other scalars, `FileSheetColorProperty` for combined
color/opacity, and ordinary Select controls for choices. Keep drafts local until
Enter/blur; Escape cancels. Clamp at the owner's write boundary. Sliders and
number inputs share that boundary. Omit visible labels only where the value/icon
is unambiguous, and always retain accessible names.

## Position and references

Pose sits above a full-width dropdown, with a small Reset icon opposite its
label (`KinematicsPoseRow`). Include Default; manual edits show Custom. Without
named poses, show Position and Reset only. There is no divider beneath Pose or
Reset footer. Each joint label sits tightly above its slider in the flexible left
column; a standard value input occupies the right column on the same row. Keep
8px between joint rows and 8px top inset. Long labels truncate with a full-name
hint; they must not consume the slider's width. Writes update pose immediately.

Position persists across tools and sidebar changes. Reset restores authored
values (including SRDF home), stops motion if necessary and hands control back
to Position. Kinematics, named poses and animation availability are separate
capabilities; absence of one must not create empty controls for another.

Reference information is read-only, with a static heading and X to clear. Keep
copy/prompt actions in the bottom CTA. Show that CTA only for an actual, usable
selection. Use Copy Reference/Copy References, not IDs. The platform copy shortcut
copies the active drawing or references unless a text field owns input.

Viewport picks target individual faces and edges even when the tree groups them
into a semantic feature. Double-click isolates a component/subassembly; double-
click away leaves isolation. Only topology that cannot be isolated copies on
double-click. Clearing/collapsing selected topology or leaving isolation must not
leave a stale Copy Reference action.

## Camera, animation and fullscreen

Cube face/edge/corner clicks change direction and preserve pan/zoom; dragging
orbits. Draw disables cube interaction without hiding it. Fresh file mounts and
refreshes fit the model; camera transforms are not persisted in per-file storage.
Display settings and authored pose are separate persisted state.

Zoom to Fit recenters and frames the whole original model at the current angle.
It has little effect when already fitted. Zoom to Selection frames the selected
geometry and is unavailable without a selection. Both live in STEP context
menus; live `resetCamera` uses the same fit path. Display Reset never reframes.

Animate starts playback when selected. Its temporary menu contains Routine
(when multiple exist), Speed and Loop. The bottom transport owns pause, scrub and
restart; it has no second settings menu. No orbit settings appear in Animate.

Fullscreen is available for every 3D file, independently of animation support.
It fills the viewer **below the parent navbar**, hides/disables sidebars and editor
controls, and starts orbit by default. Animation settings use the Play icon and
the same runtime/menu as Animate; a separate Orbit menu controls orbit and speed.
A static model gets an orbit play/pause transport. Exit, menus and transport use
one one-second idle deadline and 150ms fade; movement wakes them, while hovering
their generous interaction area or opening a menu holds them visible. The cube
is always hidden. Escape closes menus before leaving fullscreen.

Presentation suspends picking, drawing, measurements, handles and model effects
without discarding their values. It saves the regular camera, fits a presentation
camera and restores the exact regular camera on exit. Presentation movement never
writes the saved file state. The sidebar selection/width is restored, not reopened
unconditionally. Keep the viewport mounted throughout.

## Tooltips and verification

All hints use `TooltipHint`: compact text, one shared surface/arrow and a 400ms
delay. No native `title` hints. Prefer one or two words; show full technical names
only when truncated. Omit redundant hints on Fullscreen, X, transport and labeled
text buttons. Disabled or selected tools have no tooltip; pressing, leaving or
changing tool cancels pending hints. Menu focus restoration must not reopen one.

Verify state transitions, touch cancellation, keyboard operation, nested popup
dismissal, feature availability, narrow panels and empty/error states. Camera
and persistent-tool tests must exercise actual transitions, not only class names.
Do not preserve tests for discarded layouts: replace their old assertions with
coverage of the current contract. The core settings semantics remain documented
in [render-mode.md](render-mode.md); update scheduling is in
[view-updates.md](view-updates.md).

## Feedback

Viewer actions complete without toast notifications. Do not add success messages,
notification queues or dismissal timers for copy, snapshot or prompt actions.
Loading progress stays in the navbar; failures use the existing error presentation.

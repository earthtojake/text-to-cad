# File-viewer settings design system

This is the binding contract for settings in shared file-viewer panels, including
Display and a file's Position section. Use the primitives in
[`FileSheet.js`](../src/renderers/kit/inspector/FileSheet.js), and stack both Display and file-specific
panels with [`FilePanelSections.jsx`](../src/renderers/kit/inspector/FilePanelSections.jsx).
The nav row opens the file panel or file tree. Inside the file panel,
`FilePanelTabs` separates Features/Links and Position when both exist.
Extend a shared primitive when a new control shape is needed. Do not recreate
rows or section behavior inside each renderer. Environmental effects belong to
the host, per [viewer-host.md](viewer-host.md); these controls work in either app.

## Sections express behavior

Both panels use the same `FilePanelSections` stack and `FileSheetSettingsSection`
primitive: sticky headers with thin top borders, except on the first section. Do not nest disclosures or
put the display groups inside another “Display settings” accordion.

| Kind | Primitive | Behavior | Examples |
| --- | --- | --- | --- |
| Always available | `FileSheetSettingsSection` (`collapsible: false` in the stack) | Always open; no disclosure, hover treatment, or enable switch | Display |
| Foldable | `FileSheetSettingsSection` (Expand/Collapse) | The gates' plus/minus as a view only: folding changes nothing the section does, and a folded section stays mounted | Secondary information outside primary tabs |
| Optional feature | `FileSheetSettingsSection` (`enabled` / `onEnabledChange` in the stack) | Expanded means enabled; collapsed means disabled | Edges, Grid / Axes, Lighting, Background, Floor |

A section is gated only when its entire feature has a meaningful disabled state.
The surface controls stay open in their own Surfaces section below Display because they configure the model's
basic presentation. Their style picker mirrors the CLI (Shaded, Flat, Hidden, Off),
constrained by the renderer's capabilities. Mode presets are shortcuts over these
same settings; they do not hide controls. Position holds controls over
authored motion in the file sidebar. Switching its tab changes only visibility;
leaving the Position tool preserves the pose.

For an optional feature:

- The disabled header has muted text and a small plus on the right. The title and
  plus enable it on click or keyboard activation. Hover provides a gray
  background only.
- The enabled title uses primary text and scrolls to its section on click, without
  changing settings. Only the trailing minus disables it; the icon button uses
  the standard hover/focus treatment.
- Enabling initializes the group's defaults. Disabling removes its overrides
  and applies its neutral behavior. Reopening never restores old edits.
- Do not add an enable checkbox inside the section, and do not infer whether it
  is open from the numerical value of a control.
- Hover, focus, scrolling, layout movement, or renderer completion must never
  write settings or open/close a section.

Feature state comes from the canonical per-file settings store. There is no
second accordion-open state to synchronize with it.

## Toolbar option menus

Tools with second-press option menus show a small filled triangle in their lower
right corner. The icon activates the tool; pressing it while active opens its
options. Pressing the triangle follows the same rule: the first click selects
the tool, and only a subsequent click opens its options. Keep the indicator inside the existing button footprint; tools without
options have no triangle. A selected tool never shows a tooltip; keep the trigger
DOM stable when selection changes so a corner pointer-down can finish its click.
Keyboard activation retains the same menu access.
All viewer hints use the shared `TooltipHint` primitive: compact 11px text, the
same popover surface/arrow, and a 400ms hover delay. Do not use native HTML
`title` attributes for interface hints. Keep copy to one or two words where
possible; use longer text only for clipped names or necessary technical context.
Omit hints on obvious Fullscreen/exit/close/playback controls and text buttons
that already state their action. Tree and field names get hints only when clipped.
Preserve accessible labels even where a visible hint is unnecessary.

Toolbar tooltips use that same delay, dismiss on pointer leave or
press, and never retain a pending/open tooltip across selection or disablement.
Menu focus restoration must not open a tooltip; keyboard focus still can.
Preview chrome hides its portalled toolbar tooltips at the same time as its controls.

Every corner menu is an ephemeral `ToolPopover` dropdown; Select, Draw, Measure and multi-routine Animate use this shared component. They dismiss on outside click,
Escape, or another trigger press; choosing an option closes them except for Draw's
settings actions described below. Menus fit the viewport and scroll if needed.
Persistent tools instead use `ToolPanel` in the right-hand stack, described below.
Position has no corner menu: its tool enables joint handles and reveals its sidebar
Position tab. Repeated presses reveal it again without
resetting the pose or toggling the tool off.

Draw uses an ephemeral corner dropdown with separate tools and settings rows,
divided by a separator. Picking a drawing tool updates the toolbar icon and closes
the dropdown. Color, Undo and Redo keep it open; Clear drawing closes it. Outside
click or Escape dismisses it. Undo and Redo are disabled when their respective SDK history stacks are empty, independent of whether the canvas has ink. Draw selection uses the SquareMousePointer icon. Leaving Draw clears its sketch. Select remains an
ordinary interaction tool with an ephemeral filter menu.

## Persistent tools

The top-left toolbar orders tools as Select, Draw, Measure, Explode, Clip,
Position and Play, with no separator. Home and Display sit in a separate
transparent row at the bottom corners of the top-right view cube widget.
Opening Explode or Clip immediately makes it the active tool, including at zero. Its neutral panel is retained while that tool is active and removed when another tool is chosen.
Persistent buttons stay selected while their panels exist, independently of the
current pointer tool. They have no corner menu or active dot. Clicking one again
resets and removes its panel, exactly like X.

Persistent panels share `ToolPanel` and stack directly under the left-aligned toolbar in insertion
order, 160px wide with an 8px gap. Applied effects survive changing tools. A neutral
Explode or Clip panel is temporary: choosing another tool removes it, including
when its slider was changed and returned to zero. Opening the other model effect
also removes an unused panel. Editing axis or Flip alone does not count as a cut. Their disclosure folds controls without changing values.
The stack scrolls within viewport height and hides in fullscreen. Restored applied
effects get panels on load. The canonical store owns rendering and CLI state.

Explode opens at 0% with no effect; editing its slider applies separation. Clip
opens neutral with Flip off: X/Y/Z selection and Flip share a row, and one slider
plus percentage input share the next. The slider runs from 0% cut at the left to
100% at the right. Without Flip this advances from maximum to minimum coordinate;
Flip reverses the direction. Its input and rendered plane use the same original
model bounds, independent of pose and Explode. Flip preserves an active plane's
coordinate while reversing the retained half. At 0% there is no clipping.
X removes and resets the feature. Display Reset clears both effects; presets preserve
them. Explode is unavailable with fewer than two parts.

Measure starts as an exclusive picking tool with a temporary corner dropdown for
snap options. Repeated activation before any result keeps it armed. The first
completed measurement creates a retained results panel in the toolbar stack.
Changing tools cancels only an unfinished pick: completed rulers and their panel
remain, and Measure stays highlighted. Its main button now clears all results
and releases Measure if it owns pointer input; its corner reactivates picking and
opens snap options without clearing results. X clears and removes the retained
tool. Deleting the last result returns it to ordinary picking-tool behavior.

Tool cleanup is explicit, never a blanket reset on deselection:

| Leaving | Cleanup |
| --- | --- |
| Select | Clear selected topology/parts |
| Draw | Clear drawings |
| Measure | Cancel unfinished picks; retain completed measurements until cleared |
| Animate | Stop animation and restore the base position |
| Position | Keep joint values; hide manipulation handles |
| Explode / Clip | Remove zero-value panels; keep applied effects until their tool is removed |

## Read-only inspection

Reference information uses a static heading with an X to clear selection, not a
gated settings section. Its body may scroll independently and its divider may
resize it; fields never hide behind nested disclosures. Use compact label/value
rows with the same 8px gutters and 11px text as settings. A dropdown may browse
multiple selected items without altering the selection. Keep copy, prompt and
geometry-manipulation actions out of this read-only panel.

## Density and spacing

Use 8px horizontal gutters throughout. There is no tab strip inside a panel.
The shared panel column has a 256px minimum width to preserve tree and setting
rows without horizontal scrolling. Dragging narrower
collapses the panel; reopening starts at 320px. Every panel (the file tree, a
file's own panel, Display) uses the same resize frame and rule.
At less than 720px of total file-view width, sidebars become nonmodal floating
sheets over the scene with an explicit close button, outside dismissal and Escape.
They have no extra title bar: the filter, tabs or first section is the top row.
Accessible dialog names remain available to screen readers. Opening a panel
never translates content beyond the viewer or scrolls the surrounding page.
They start closed, never resize the scene, and preserve the desktop panel and width
when returning to desktop. Automatic tool reveals neither open mobile sheets nor switch their tabs.
Mobile bottom action buttons fit their contents and omit desktop keyboard hints.
The view cube is omitted on mobile; one-finger orbit and two-finger pan/zoom
remain available. Pinch and cancelled touches must never be interpreted as
selection or measurement taps.
This same breakpoint collapses breadcrumbs to the filename and its menu and
replaces navbar status text with a tappable progress icon. Desktop has no extra
breakpoint based on the remaining scene width. Collapsing never resets file, pose, or display state.

Display and the file sidebar each have one scroll container for all section bodies, including trees
and Position; do not give either a height cap or nested scrollbar. Section headers
stay visible in section order: preceding headers stack at the top, and later
headers stack at the bottom while a long section scrolls between them. Use an opaque panel background. The existing pinned
Reference inspector remains a separate sibling pane, not a nested tree scroller.
Clicking a section title expands it if needed and scrolls its content below
the pinned header stack; clicking an already open title only scrolls. Only the trailing minus collapses or
disables it. A Position-tool reveal selects the Position tab. Other section reveals use this scroll behavior. Reveal scrolls toward the top only within the natural content range. A short
section near the end stops at the scroll limit; never add spacers or viewport
padding to force it to the top. Ordinary
edits and rerenders never scroll the panel.

Section headers are at least 28px high with regular 12px text. Controls follow
the header directly, without extra top padding; expanded headers have no hover
background to separate from the controls. Keep 4px between rows and 8px bottom padding per section, matching the horizontal inset. Trees have 4px
top padding before the first row; their bottom gutter comes from the shared
section, so the two ends match without doubling padding. Controls are generally 28px high. Use muted smaller labels for secondary
information; do not enlarge every label to the default body size. Avoid bold.

Related controls share rows through `FileSheetFieldGrid` (two or three equal
columns), which owns the gutter. Children use `className="px-0"` when their
primitive normally adds its own gutter. Never double-pad a grid cell.

| Control | Pattern |
| --- | --- |
| Related choices | Two or three compact dropdowns on one row; equal widths |
| Scalar with a useful range | `FileSheetSliderField compact`: short label, slider, committed value on one row |
| Scalar where the range is less useful | `FileSheetNumberProperty` with recognizable icon/unit and a tooltip |
| Boolean option within a feature | `FileSheetCheckboxRow`, label directly beside the checkbox |
| Color and opacity | `FileSheetColorProperty`; swatch, hex value, and percentage together |
| Actions | `FileSheetButtonRow`; compact buttons, verb labels, icons where useful |

Omit a visible label only when the selected value, icon, unit, or swatch makes
its meaning clear. Always provide an accessible name and a tooltip for omitted
labels. Keep labels on ambiguous controls such as authored joint values.
Long labels truncate while reserving at least 48px for sliders and keeping
numeric inputs visible, without pushing controls outside the panel;
the full name remains available in a tooltip/accessibility label. Never use an
unlabelled switch whose neighboring labels could refer to it.

Menu items default to 11px text with a 16px line height in the shared dropdown,
select and context-menu primitives, including submenus and checkbox/radio rows.
Do not override this at each settings control: popup portals must retain the
same compact size independently of the trigger's or host body's typography.
Menu shortcut hints use the 10px metadata size.

Dropdowns show useful icons in both the selected value and menu options. Use
specific projection icons and complementary Solid/Render icons. Color opacity
uses the checkerboard preview; 0% is transparent and 100% is opaque. Do not add a
separate transparency toggle or duplicate opacity slider.

## Display

Keep this order in every preset; enabling a feature never moves it:

| Section | Contents |
| --- | --- |
| Display | Full-width Mode, then Appearance and Projection side by side, with selected icons. Always expanded |
| Surfaces | Surface style and part-color mode together; color/palette and opacity underneath. Always expanded |
| Edges | Visibility and color together (`edges`) |
| Grid | Grid color and opacity (`grid`) |
| Axes | Axis color and opacity (`axes`); matches the grid's default color |
| Lighting | Quality, then paired exposure/rotation and softbox-size/fill controls (`lighting`) |
| Background | Background color and opacity (`background`) |
| Floor | Floor color/opacity and placement, using model origin by default (`floor`) |

Each optional section controls exactly one CLI settings group. Its plus enables that
feature at default values, and its minus disables only that feature. Do not combine
Grid with Axes or Lighting with Background and Floor behind a shared gate. Keep
related controls compact inside each section, without nested disclosures.

Explode, Cross-section and Edges are for CAD models (STEP). A mesh, a robot or a drawing has
no parts to separate, no solid to section and no topology to draw edges from: those
three sections are not rendered for it, they resolve disabled whatever was saved,
and the presets made of edges (X-ray, Hidden line, Wireframe) are not offered
(the `features` lists of `resolveViewSettings`: a STEP view passes `ALL_VIEW_FEATURES`,
every other `EDGELESS_VIEW_FEATURES`). The snapshot CLI applies the same rule.

Solid's basic display groups precede the effects disabled by default in Solid.
Presets are batches of settings; controls do not branch on the mode name. An
edit makes the selected value read muted **Custom**, which is not a menu option.
**Reset** restores the currently selected preset's display defaults and disables
Cross-section and Explode. It leaves the model's pose and the camera unchanged. See
[render-mode.md](render-mode.md) for the grouped settings/CLI contract.

The desired settings update immediately. Expensive changes can take longer to
appear in the viewport, but rendering cannot rewrite controls. The small status
indicator, cancellation, and presentation policy live in
[view-updates.md](view-updates.md).

## Framing

The top-right view cube has a transparent Home / Display row beneath it, at the widget’s left and right corners.
Face, edge and corner clicks change orientation while preserving zoom and pan.
Home restores default isometric orientation, centers original model bounds and
restores 100% zoom. Dragging only rotates the view.
XYZ guides follow its edges. Draw leaves the cube and its buttons visible but disables them (including tooltips);
Preview hides the cube throughout the presentation. Mode and Projection live
in the Display toolbar menu.

There is no zoom percentage control. Camera framing always uses original model
bounds, never bounds changed by explode, clipping or motion. Do not advertise unimplemented keyboard shortcuts.

| Action | Where | Scope |
| --- | --- | --- |
| Zoom to fit | STEP's viewport context menu — over a part, over the backdrop, and on every Features tree row | Frame the whole model again, without turning the camera. What the live `resetCamera` command does |
| Zoom to selection | The same menu, disabled without a selection | Frame what is selected now |
| Camera direction | Cube faces, edges and corners | Change direction while preserving zoom and pan |
| Home | Bottom-left corner of the cube widget | Default isometric direction, original model center and 100% zoom |
| Display → Reset | The Display panel | Restore selected preset defaults and disable Cross-section/Explode; keep the model's pose and the camera |

Restoring the model itself belongs to whoever owns it: the Position section's
Reset for a pose, the Display panel's Reset for settings.

## Position

A STEP uses **Features** and **Position** tabs; a robot uses **Links** and **Position**.
Only show tabs when both views exist. Their contents are permanently expanded with
no repeated collapse headings. Keep Issues with Features and SDF metadata with Links.
Keep inactive tabs mounted to preserve tree and scroll state, but pass `active=false`.
The Position tool reveals its tab.
Position controls live in the sidebar in both. Include the tool
only when there is something to drive: a STEP whose sidecar declares
kinematics, a robot with a joint a person can move. Detect the named poses and
the joint values independently from their respective sidecar blocks (or the
SRDF's group states), not from the file extension or the existence of the other
block. Loading/error status for a requested block can be shown; absence of a
block does not create empty controls. Animation has no section here: it is the
Animate tool's own playbar, entirely outside this panel (see
[Fullscreen presentation controls](#fullscreen-presentation-controls) for its
transport, which the tool also shows at the bottom of the regular viewport).

Position begins with a standard labeled field: Pose above a full-width dropdown,
with a small muted Reset icon opposite the label (`KinematicsPoseRow`). Include Default; show
Custom after manual edits. Without named poses, show Position and Reset only.
Joint controls use the shared slider field: a label directly above its slider
in the flexible left column, with the standard numeric input alongside. Use
the shared muted field-label typography and control dimensions, without
per-renderer size overrides. Long labels truncate. Every pose write lands in the same frame, without
easing. Do not include a Copy button.

Position persists across pointer-tool changes, tab switching and panel closure.
The tool controls joint handles only. Reset restores the authored base pose
(including a robot's SRDF `home`). Animate keeps its existing ownership and
reset-on-exit behavior; starting playback still replaces the manually set pose.

Place one **Reset** beside the Pose/Position label at the top. It restores authored joint
values and, if a routine owns the pose, also stops playback and hands the pose
back to Position, so animation and a modified pose never disagree about
which one is in control after a reset. Display settings and camera remain
unchanged.

## Animation and fullscreen

Animate is conditional on authored animation clips (STEP or GLB). It is the
rightmost interaction tool and starts playback when selected. A second click or
its corner opens a temporary menu with Routine (when multiple exist), Speed, and
Loop. Pausing belongs to the bottom playbar. No orbit controls appear in that menu.
Every 3D file has a toolbar with Display; static GLB files have only that control.

Fullscreen is a separate transparent diagonal-arrows icon button at the viewport's top-right.
It preserves the presentation layout below the parent-owned navbar, suspends
and hides the sidebar and editor controls, and starts camera orbit by default.
Animations remain available through the playbar and animation settings when the
file has clips, even if Animate was not selected before entering. Static files
have a simple orbit play/pause control. A separate Orbit menu controls camera motion and speed, independently of the animation menu. Animation settings use the same Play icon as Animate.
Settings, Exit and transport share the existing one-second idle deadline and
150ms fade; movement wakes them, and hovering controls or opening settings holds
them visible. Escape dismisses a menu first, then exits fullscreen. Leaving restores
the previous sidebar visibility, width and tab. Clip, Explode, selection, drawing,
and position handles remain suspended during presentation. The cube is hidden.

The cube sits at bottom-right. It has no surrounding Reset or arrow buttons; Display is the last item in the main toolbar. Both link and model filters use TreeFilterInput's
shared height and padding, including the reduced top inset below a heading.


## State, input, and verification

Use controlled values from the owning store/runtime. Input drafts stay local
until Enter or blur commits them; Escape cancels. Normalize/clamp at the write
boundary. Do not mirror props into effects that write them back to the owner.
Native sliders and editable number fields must share one update path.

New behavior must work with mouse and keyboard. Verify disabled/enabled
semantics, preset stability, independently available kinematics blocks, empty and
error states, and narrow panels. Test state transitions rather than exact class
strings. The Display and Position components are the reference consumers;
legacy subsection primitives elsewhere are not the pattern for new settings.

## Display popover

`DisplaySettingsPopover` uses a render sphere trigger and one 256px properties
popover, capped at 520px or the available viewer height. It selects the Display tool, leaving Draw, Select, Measure, Position or Animate.
Dismissing the popover keeps Display selected; choosing another tool closes it.
It remains available during Draw and does not replace the file sidebar. Reuse `FilePanelSections` and
`FileSheetSettingsSection`, with ordinary non-sticky headers in this short sheet
and one scroll container. Display section headings use the same `text-tiny` size as their dropdowns. Use equal 4px row/column gaps, 8px horizontal and bottom section insets, thin separators and no nested cards.

Display is permanent: a full-width Mode selector comes first, followed by the
host-owned Light / Dark / System dropdown and Projection side by side. Both show
the selected option’s icon. Surfaces is a separate permanent section below it.
A muted Reset icon sits at the top-right of Display. Individual optional sections
follow in the order above. Their plus enables default values and reveals controls;
the minus disables the whole feature and discards its overrides. There is no
additional Enabled checkbox or submenu between the heading and its controls.

Use ordinary Select controls and the shared color picker for individual values.
Edits and option choices keep the sheet open. Escape closes the innermost picker
first, then the sheet. A pointer click that dismisses an inner dropdown closes only
that dropdown; a subsequent outside click dismisses the sheet without resetting settings. Open settings hold Preview chrome visible. Menu visibility
is not persisted. Appearance controls application theme, Orbit controls viewing
behavior, and Display controls rendering; Reset affects only display settings
and the model effects, never theme or Orbit.

When Appearance follows System, its trigger shows the resolved Light/Dark label
and icon; the dropdown still marks System as the saved preference.

Grid and Axes share a `Grid / Axes` gate. Two unlabeled color controls are ordered
left to right to match the title, with separate accessible names and opacity
controls. The gate enables/disables both groups while CLI values remain separate.
The tab strip has no bottom padding; the feature filter supplies its own vertical spacing. Position uses an 8px top inset and 8px between joint rows, with a small positive gap between each label and slider.

The Pose header has no divider or bottom Reset. Default restores the coordinated base motion state; manually adjusted values show Custom. Each joint label sits directly above its slider, with the standard value input alongside the pair.


## Sidebar navigation and viewport spacing

Position explicitly opens its tab. Selecting the Select tool alone never switches tabs.
A part or topology selection reveals Features (Links for robots) only when the sidebar
is already open. Geometry picks never reopen a closed sidebar. Other tools leave its
selected tab unchanged. Tabs remain mounted to preserve tree expansion, input and scroll state.

The cube uses a 112px canvas with enlarged edge and corner targets, no arrow buttons,
and no Reset button. Reloading fits the camera at its default perspective and zoom;
older stored camera framing is ignored. Face, edge, corner and drag interactions
remain available, with neutral hover fills and colored XYZ guides. The top-right
Fullscreen button keeps its 24px hit area. Contextual tool actions and playback use a fixed center 3.5rem above the scene bottom (`kit/shell/viewportLayout.js`), independent of the cube. Status updates use transparent, unboxed text and icons beside the filename in the navbar.
On very narrow viewports, playback may move above the cube to prevent overlap.


Copy actions use 44px-high buttons labeled Copy Reference, Copy References or Copy
Drawing, with the host platform's ⌘C / Ctrl+C hint. They always copy to the clipboard;
adding context to a prompt remains a separate action. Double-clicking a model reference
or a selected tree row copies it. Viewport copy shortcuts prioritize an active drawing,
otherwise the selected references, and never override editable fields or selected text.
Copy notifications name the action, fit their message width, and sit 12px from the full viewer’s right edge below its navbar. Sidebar width never moves the notification anchor.

A robot opens with Select active and Links visible. Select uses the same pointer icon
as the STEP viewer and precedes Position in the toolbar. A single-action toolbar
uses 2px outer padding; multi-action strips retain 4px. A tree filter directly below
a section heading uses a smaller top inset than a filter below tabs.

# File-viewer settings design system

This is the binding contract for settings in shared file-viewer panels, including
Display and a file's Position section. Use the primitives in
[`FileSheet.js`](../src/renderers/kit/inspector/FileSheet.js), and stack a file's
own panel with [`FilePanelSections.jsx`](../src/renderers/kit/inspector/FilePanelSections.jsx).
A panel has no tabs: the nav row's toggles are the tab strip (the file's own
panel, Display, the file tree), and a panel is one column of sections.
Extend a shared primitive when a new control shape is needed. Do not recreate
rows or section behavior inside each renderer. Environmental effects belong to
the host, per [viewer-host.md](viewer-host.md); these controls work in either app.

## Sections express behavior

Sections are a flat stack separated by thin borders. Do not nest disclosures or
put the display groups inside another “Display settings” accordion.

| Kind | Primitive | Behavior | Examples |
| --- | --- | --- | --- |
| Always available | `FileSheetStaticSection` | Always open; no chevron, hover treatment, or enable switch | Display |
| Foldable | `FilePanelSections` in a file's own panel, beside another section (`FileSheetToggleHeading`, Expand/Collapse) | The gates' chevron as a view only: folding changes nothing the section does, and a folded section stays mounted | Features, Position, Issues, Links, SDF |
| Optional feature | `FileSheetGatedSection` | Expanded means enabled; collapsed means disabled | Edges, Grid & axes, Environment |

A section is gated only when its entire feature has a meaningful disabled state.
The surface controls stay open, inside Display, because they configure the model's
basic presentation. Their style picker offers only Shaded and Flat: Hidden and Off
are what Hidden line and Wireframe are made of, so the Mode owns them, and while the
Mode draws no shaded surface the surface rows step aside. Position holds controls over
authored motion, not an optional display effect, so it is never gated; folding it
away beside Features changes the view and nothing else.

For an optional feature:

- The disabled header has muted text and a chevron pointing right. The title and
  chevron enable it on click or keyboard activation. Hover provides a gray
  background only.
- The enabled header is static primary text with a chevron pointing down. Only the
  chevron is an interactive icon button, with the standard button hover/focus
  treatment.
- Enabling initializes the group's defaults. Disabling removes its overrides
  and applies its neutral behavior. Reopening never restores old edits.
- Do not add an enable checkbox inside the section, and do not infer whether it
  is open from the numerical value of a control.
- Hover, focus, scrolling, layout movement, or renderer completion must never
  write settings or open/close a section.

Feature state comes from the canonical per-file settings store. There is no
second accordion-open state to synchronize with it.

## Explode and Cross-section

These are how a person examines a design, so they are not Display sections: they are
toggle buttons in a STEP's tool strip, after Measure. They are not tools. Tools are
one at a time; a person selects or measures while exploded or cut, so a toggle
leaves the active tool alone. A press turns one on and puts its controls in a
panel under the strip (`ViewToolPanel`, the Measure panel's surface); a press
while on turns it off. The panel has no close button. The controls
(`ExplodeControls`, `CrossSectionControls`) write the same `exploded` and `clip`
settings Display's Reset clears.

Cross-section (the `clip` setting) opens with an X center cut and Flip off,
exposing the section toward the default camera. Flip reverses the kept half
without moving the plane; orbiting does not change the cut. Explode opens at 50%
and stays on at 0%, and its button is disabled with fewer than two parts. Both stay
outside presets.

## Read-only inspection

Reference information uses a static heading with an X to clear selection, not a
gated settings section. Its body may scroll independently and its divider may
resize it; fields never hide behind nested disclosures. Use compact label/value
rows with the same 8px gutters and 11px text as settings. A dropdown may browse
multiple selected items without altering the selection. Keep copy, prompt and
geometry-manipulation actions out of this read-only panel.

## Density and spacing

Use 8px horizontal gutters throughout. There is no tab strip inside a panel.
The shared panel column has a 256px minimum width, so a Position section's joint
sliders and their typed values fit without scrolling sideways. Dragging narrower
collapses the panel; reopening starts at 320px. Every panel (the file tree, a
file's own panel, Display) uses the same resize frame and rule.
If the containing file view itself becomes narrower than the minimum, collapse
the column as well. Collapsing never resets file, pose, or display state.

Section headers are at least 28px high with regular 12px text. Controls follow
the header directly, without extra top padding; expanded headers have no hover
background to separate from the controls. Keep 4px between rows and 8px after
the last row. Controls are generally 28px high. Use muted smaller labels for secondary
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
| Display | The Mode dropdown; then, while the Mode draws surfaces, Style (Shaded/Flat) and part-color mode together and compact color/opacity controls. Projection is not here: it is the view cube's toggle |
| Edges | Visibility and color together |
| Grid & axes | One gate over both groups; Grid and Axis color/opacity side by side (the axes match the grid's default color) |
| Environment | One gate over lighting, background and floor, the groups Render turns on together. A **Lighting** group (quality, then paired numeric properties for exposure/rotation and size/fill), then **Background & floor** (the two colors side by side, then floor placement, using model origin by default) |

A section that gates several groups (`groupSection`) is open while any of them is on, and
its gate turns all of them on or off together. Inside it, `FileSheetItemGroup` labels each
group; that is a label, never a nested disclosure.

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

There is NO zoom control. No panel carries one, there is no percentage readout,
no menu behind one, and no zoom toolbar over the viewport. Do not add one, and do not advertise keyboard shortcuts the viewer does
not implement. Zooming is the pointer's: wheel or pinch to zoom, drag to pan, and
on a DXF double-click to fit.

Two affordances frame the model, and between them every renderer has a way back
from a view that has been driven off it.

| Action | Where | Scope |
| --- | --- | --- |
| Zoom to fit | STEP's viewport context menu — over a part, over the backdrop, and on every Features tree row | Frame the whole model again, without turning the camera. What the live `resetCamera` command does |
| Zoom to selection | The same menu, disabled without a selection | Frame what is selected now |
| Reset to default isometric view | The house beside the view cube, in every 3D renderer | Frame the model AND return to the default direction — the only way back on a robot, a GLB or a mesh |
| Display → Reset | The Display panel | Restore selected preset defaults and disable Cross-section/Explode; keep the model's pose and the camera |

Framing the whole model is ONE act, so it is offered once and under one name.
Restoring the model itself belongs to whoever owns it: the Position section's
Reset for a pose, the Display panel's Reset for settings.

## Position

A STEP's own panel stacks **Features**, then **Position**, then **Issues**; a
robot's stacks **Position**, then **Links**, then **SDF** for an `.sdf`. Include
Position only when there is something to drive: a STEP whose sidecar declares
kinematics, a robot with a joint a person can move. Detect the named poses and
the joint values independently from their respective sidecar blocks (or the
SRDF's group states), not from the file extension or the existence of the other
block. Loading/error status for a requested block can be shown; absence of a
block does not create empty controls. Animation has no section here: it is the
Animate tool's own playbar, entirely outside this panel (see
[Fullscreen presentation controls](#fullscreen-presentation-controls) for its
transport, which the tool also shows at the bottom of the regular viewport).

Position is ONE section of rows, with no sections of its own inside it. First a
**Pose** row, the label on the left and the named-pose dropdown right-aligned
beside it (`KinematicsPoseRow`), present only if named poses exist (a STEP
sidecar's poses, an SRDF's group states); then a row per joint value, present
only if joint values exist. Keep each DOF's label and unit: these are not
self-explanatory icons. Numeric DOFs use compact slider/value rows with 4px
gaps and a label column capped at 96px; longer labels truncate to preserve
slider space. Do not include a Copy button. Every pose write lands in the same
frame — a named pose, a slider drag, a typed number, a Position-tool knob and
Reset — and none of them ease; motion over time is the Animate tool's, never
this section's.

Place one **Reset** at the bottom of Position. It restores authored joint
values and, if a routine owns the pose, also stops playback and hands the pose
back to Position, so animation and a modified pose never disagree about
which one is in control after a reset. Display settings and camera remain
unchanged.

## Fullscreen presentation controls

Fullscreen is entered from the `Fullscreen` tool (`Maximize2`), the last item of
a STEP's tool strip, which exists only where the host offers fullscreen (the web
app does; the desktop app does not). The kit's `FullscreenToolbar`
(`kit/tools/fullscreen/`) places the Animate tool's playbar (`ViewportAnimationBar`,
the same transparent bar the regular viewport shows at bottom center while a
routine plays) at the bottom center, with an Orbit-settings button and X at
the top-right. Use shared 24px buttons and 12px icons without a toolbar
background, border or shadow. Play/Pause never opens a picker. Without
animation, omit the bottom bar entirely.

The corner button, unlike the neighboring Exit button, carries no tooltip; it
opens a floating, content-height panel aligned to the top-right. Clamp its
width and height to the viewport and scroll its contents when needed. It holds
one permanent `FileSheetStaticSection`, **Orbit**: a compact speed slider,
also untooltipped, plus numeric input (0–5×, slider steps of 0.05; 0 stops
rotation). Persist this global preference through `CadPreferences`. Settings
never opens or switches a file's panel, and closing it does not disable
animation.

Both control areas fade together after two seconds without pointer/wheel/keyboard
activity. An open settings panel, a scrub gesture or keyboard focus keeps them
visible. The animation clock's ticks do not reset the idle timer. Hidden controls are
inert and do not intercept viewport input. Escape closes a nested picker, then
the settings panel, then fullscreen. Fullscreen and the regular viewport's playbar use
the same callbacks and the renderer's one clock; do not duplicate animation state.

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

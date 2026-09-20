# File-viewer settings design system

This is the binding contract for settings in shared file-viewer tabs, including
Display and Kinematics. Use the primitives in
[`FileSheet.js`](../src/renderers/kit/inspector/FileSheet.js), and the
fixed strip in [`FileSheetTabbedSurface.js`](../src/renderers/kit/inspector/FileSheetTabbedSurface.js).
Extend a shared primitive when a new control shape is needed. Do not recreate
rows or section behavior inside each renderer. Environmental effects belong to
the host, per [viewer-host.md](viewer-host.md); these controls work in either app.

## Sections express behavior

Sections are a flat stack separated by thin borders. Do not nest disclosures or
put the display groups inside another “Display settings” accordion.

| Kind | Primitive | Behavior | Examples |
| --- | --- | --- | --- |
| Always available | `FileSheetStaticSection` | Always open; no plus/minus, hover treatment, or enable switch | Mode, Surfaces, Pose, Joints |
| Optional feature | `FileSheetGatedSection` | Expanded means enabled; collapsed means disabled | Explode, Clip, Edges, Grid, Axes, Lighting, Background, Floor |

A section is gated only when its entire feature has a meaningful disabled state.
Surfaces stays open because the group configures the model's basic presentation;
its style picker can still explicitly select Off. Pose and Joints are
controls over authored motion, not optional display effects: neither collapses.

For an optional feature:

- The disabled header has muted text and a plus. The title and plus enable it
  on click or keyboard activation. Hover provides a gray background only.
- The enabled header is static primary text. Only the separate minus is an
  interactive icon button, with the standard button hover/focus treatment.
- Enabling initializes the group's defaults. Disabling removes its overrides
  and applies its neutral behavior. Reopening never restores old edits.
- Do not add an enable checkbox inside the section, and do not infer whether it
  is open from the numerical value of a control. Explode stays open at 0%.
- Hover, focus, scrolling, layout movement, or renderer completion must never
  write settings or open/close a section.

Feature state comes from the canonical per-file settings store. There is no
second accordion-open state to synchronize with it. Clip opens with an X center
cut and Flip off, exposing the section toward the default camera. Flip reverses
the kept half without moving the plane; orbiting does not change the cut.
Explode opens at 50%. These two tools stay outside presets.

## Read-only inspection

Reference information uses a static heading with an X to clear selection, not a
gated settings section. Its body may scroll independently and its divider may
resize it; fields never hide behind nested disclosures. Use compact label/value
rows with the same 8px gutters and 11px text as settings. A dropdown may browse
multiple selected items without altering the selection. Keep copy, prompt and
geometry-manipulation actions out of this read-only panel.

## Density and spacing

Use 8px horizontal gutters throughout. The tab strip also has 8px of top inset;
its container is 28px high with 2px internal padding and 24px triggers. Tabs use
the standard 13px text size, regular weight, and remain in a fixed order.
The shared inspector/file-explorer column has a 256px minimum width so the full
tab strip and zoom value fit without scrolling. Dragging narrower collapses the
panel; reopening starts at 320px. Both panels use the same resize frame and rule.
If the containing file view itself becomes narrower than the minimum, collapse
the column as well. Collapsing never resets file, kinematics, or display state.

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
| Mode | Equal-width Mode and Projection dropdowns |
| Surfaces | Style and part-color mode together; compact color/opacity controls |
| Explode | Amount slider/value |
| Clip | X/Y/Z slider/value rows, then Flip checkbox |
| Edges | Visibility and color together |
| Grid | Color/opacity |
| Axes | Color/opacity, matching Grid's default color |
| Lighting | Quality, then paired numeric properties for exposure/rotation and size/fill |
| Background | Color/opacity |
| Floor | Placement and color/opacity, using model origin by default |

Explode, Clip and Edges are for CAD models (STEP). A mesh, a robot or a drawing has
no parts to separate, no solid to section and no topology to draw edges from: those
three sections are not rendered for it, they resolve disabled whatever was saved,
and the presets made of edges (X-ray, Hidden line, Wireframe) are not offered
(the `features` lists of `resolveViewSettings`: a STEP view passes `ALL_VIEW_FEATURES`,
every other `EDGELESS_VIEW_FEATURES`). The snapshot CLI applies the same rule.

Solid's basic display groups precede the effects disabled by default in Solid.
Presets are batches of settings; controls do not branch on the mode name. An
edit makes the selected value read muted **Custom**, which is not a menu option.
**Reset** restores the currently selected preset's display defaults and disables
Clip and Explode. It leaves Kinematics and camera pose unchanged. See
[render-mode.md](render-mode.md) for the grouped settings/CLI contract.

The desired settings update immediately. Expensive changes can take longer to
appear in the viewport, but rendering cannot rewrite controls. The small status
indicator, cancellation, and presentation policy live in
[view-updates.md](view-updates.md).

## Zoom and reset menu

Place the muted 10px zoom percentage at the far right of the inspector header,
beside the fixed tabs, using `FileSheetTabbedSurface.headerActions`. It remains
outside the tablist and does not scroll with a tab's content. The percentage is
read-only; clicking it opens the shared `ZoomControl` menu. There is no duplicate
zoom toolbar over the viewport. The menu contains Zoom in/out, Zoom to 100%,
Zoom to fit, Zoom to selection (disabled without a selection), and two resets.
Do not advertise keyboard shortcuts that the viewer does not implement.

| Action | Scope |
| --- | --- |
| Reset camera | Original authored bounds and default camera pose; current projection remains |
| Reset model | Stop/reset animation and pose, disable Clip/Explode, reveal hidden/isolated geometry, restore original camera framing; keep the exact display settings, including Custom and projection |
| Display → Reset | Restore selected preset defaults and disable Clip/Explode; keep Kinematics and camera pose |

A model reset must stop clocks before writing authored pose values,
so a queued frame cannot undo it. Embedded GLB returns to its authored rest
transforms, not the possibly displaced first frame of an animation clip. Robot
joints and drawing fold/orientation controls follow the same spatial reset rule.

## Kinematics

The standard STEP strip is **Features | Kinematics | Display**. Include
Kinematics only when the sidecar declares it. Detect Pose and Joints
independently from their respective sidecar blocks (or the SRDF's group
states), not from the file extension or the existence of the other block.
Loading/error status for a requested block can be shown; absence of a block
does not create empty controls. Animation has no section here: it is the
Animate tool's own playbar, entirely outside this tab (see
[Fullscreen presentation controls](#fullscreen-presentation-controls) for its
transport, which the tool also shows at the bottom of the regular viewport).

**Pose** is a permanent section containing only the named-pose dropdown,
present only if named poses exist (a STEP sidecar's poses, an SRDF's group
states). **Joints** is a separate permanent section below it, present only if
joint values exist. Keep each DOF's label and unit: these are not
self-explanatory icons. Numeric DOFs use compact slider/value rows with 4px
gaps and a label column capped at 96px; longer labels truncate to preserve
slider space. Do not include a Copy button. Every pose write lands in the same
frame — a named pose, a slider drag, a typed number, a Pose-tool knob and
Reset — and none of them ease; motion over time is the Animate tool's, never
this tab's.

Place one **Reset** at the bottom of Kinematics. It restores authored joint
values and, if a routine owns the pose, also stops playback and hands the pose
back to Kinematics, so animation and a modified pose never disagree about
which one is in control after a reset. Display settings and camera remain
unchanged.

## Fullscreen presentation controls

`FullscreenToolbar` places the Animate tool's playbar (`ViewportAnimationBar`,
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
never changes the inspector's tab or opens its panel, and closing it does not
disable animation.

Both control areas fade together after two seconds without pointer/wheel/keyboard
activity. An open settings panel, a scrub gesture or keyboard focus keeps them
visible. The animation clock's ticks do not reset the idle timer. Hidden controls are
inert and do not intercept viewport input. Escape closes a nested picker, then
the settings panel, then fullscreen. Fullscreen and the regular viewport's playbar use
the same callbacks and renderer-scoped STEP/GLB clocks; do not duplicate animation state.

## State, input, and verification

Use controlled values from the owning store/runtime. Input drafts stay local
until Enter or blur commits them; Escape cancels. Normalize/clamp at the write
boundary. Do not mirror props into effects that write them back to the owner.
Native sliders and editable number fields must share one update path.

New behavior must work with mouse and keyboard. Verify disabled/enabled
semantics, preset stability, independently available kinematics blocks, empty and
error states, and narrow panels. Test state transitions rather than exact class
strings. The Display/Pose/Joints components are the reference consumers;
legacy subsection primitives elsewhere are not the pattern for new settings.

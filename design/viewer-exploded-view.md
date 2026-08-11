# Viewer: exploded view redesign

Recorded 2026-07-06. Research + design proposal: how professional CAD tools
model exploded views, why the current viewer implementation feels wonky
against that bar, and a step-based redesign that fits this repo's
cadjs/viewer/snapshot architecture. No code changes yet; this document is the
deliverable of the research task.

## 1. Current implementation

### Data model

Exploded view is a **global display setting**, one flat object shared by the
viewer UI, per-file display state, and agent snapshot JSON jobs
(`DISPLAY_OPTION_KEYS` in `skills/cad/scripts/snapshot/__main__.py:77`):

```js
// packages/cadjs/src/common/displaySettings.js:75
exploded: {
  enabled: false,
  axis: "z",            // "x" | "y" | "z" | "radial"
  direction: "positive",
  spacing: 1.45,         // 0.25–4 multiplier on heuristic gaps
  depth: 1,              // 1–8 occurrence-tree grouping depth
  keepBaseGrounded: true,
  mergeCoplanar: false,
  autoFrame: true
}
```

There is no per-component or per-step state anywhere. Everything a user can
express about an explode is those eight globals.

### Solver

`packages/cadjs/src/lib/viewer/explodedView.js` is a pure-function solver:
`createExplodedViewRecordStates(THREE, records, bounds, settings)` returns
per-record `{direction, distance, translation, matrix}` states, and
`applyExplodedViewProgress` writes a translation-only
`record.explodedViewMatrix` that `displayRecordTransform.js` composes into
the render — no scene rebuild, cheap per-frame updates.

- **Grouping**: display records are grouped by occurrence-path prefix
  (`o1.2.3`) at `depth` levels below the common prefix, so sub-assemblies
  move as rigid groups at depth 1 and shatter progressively as depth grows.
- **Axis mode (x/y/z)**: groups are sorted by center along the chosen axis
  and serialized into a stack of "layers", re-spaced with gap heuristics
  (`minimumGap`, thickness fractions, `spacing` multiplier). Coplanar groups
  become **separate layers unless `mergeCoplanar` is on** — and it is off by
  default. The first layer can stay grounded.
- **Radial mode**: groups are pushed outward in the world-XY plane away from
  the model center, height preserved; groups sitting on the model's vertical
  axis have no radial direction, so they are fanned by golden-angle
  (`radialFanDirection`). A ground-lift pass keeps parts above the base.
- **Animation**: toggling runs a 1 s cubic-ease transition in
  `viewer/src/client/components/CadViewer.js`, interpolating from current
  translations when settings change mid-flight.

### UI

The controls live in their own **"Exploded"** file-sheet tab
(`ExplodedSettingsSection` / `buildExplodedSettingsTab` in
`viewer/src/client/components/workbench/ThemeSettingsPopover.js`, registered as
`FILE_SHEET_SECTION_IDS.THEME_EXPLODED` and appended to the STEP section list in
`viewer/src/client/workbench/fileSheetSections.js`). The tab is **auto-first**
and deliberately terse. On/off is expressed purely through **Amount** (0 =
assembled): a compact **Enable / Disable** button at the top just toggles Amount
to/from zero (syncing the viewer's `enabled` flag and restoring the last
non-zero amount), so **every control stays visible whether or not the view is
exploded**. Below it a flat stack of minimally-labelled controls — Amount, a
top **Layout: Automatic / Custom** switch (kept above the controls it swaps), a
**Direction dropdown** (`Auto/X/Y/Z/Radial`), Reverse, Spread, Detail, Order,
Explode lines, Reset — with detail carried in hover tooltips rather than inline
text. Choosing **Custom** materializes the automatic layout into an editable
per-part step list (numeric distance/angle edit, reorder, delete); **Automatic**
discards it. Earlier this was a terse subsection of the Display tab. The skill
docs describe the feature as "an independent Explode toggle for animated
vertical STEP disassembly" (`skills/cad-viewer/references/viewer-features.md:22`).

### What it gets right

Worth preserving in any redesign:

- Pure solver in `packages/cadjs` (non-React), applied as a per-record
  matrix — no geometry duplication, works with the package/instancing work.
- Occurrence-group rigidity and the depth concept (sub-assemblies first).
- Animated transitions that interpolate from the current state.
- Keep-base-grounded and auto-frame as explicit toggles.
- A declarative JSON surface that agents can drive headlessly through
  snapshot jobs.

## 2. Why it feels wonky

The root cause is architectural, not tuning: **the explode is a single
global heuristic layout, while every professional tool models an exploded
view as an editable, ordered list of per-component moves.** Concretely:

1. **No per-component control.** You cannot say "these two turbopumps go
   out ±X, the nozzle goes down −Z, the gimbal goes up +Z". The only knobs
   are one axis for *everything* or a radial bloom for *everything*. The
   repo itself documents the workaround:
   `models/spacex/raptor2/raptor2_exploded.step.py` hand-authors a
   per-group offset table (`OFFSETS = {nozzle_bell_group: (0,0,-650),
   ox_turbopump_group: (380,0,120), …}`) plus
   translucent guide rods — i.e. contributors rebuilt explode *steps* and
   *explode lines* as separate STEP models because the viewer cannot
   express them. Same pattern in `starship_exploded.step.py`,
   `merlin1d_exploded.step.py`, `falcon_heavy_exploded.step.py`.
2. **Default axis mode serializes coplanar parts.** With `mergeCoplanar:
   false` (the default), four bolts at the same height become four separate
   layers stacked apart vertically. Side-by-side geometry (gripper jaws,
   boosters) gets sheared into a column. The fix toggle exists but is
   buried and off.
3. **Non-physical directions.** Axis mode moves everything along one world
   axis regardless of the assembly's own structure. Radial mode scatters
   coaxial parts sideways by golden-angle — a gearbox explodes axially in
   any catalog drawing, never as a sideways scatter. Directions never come
   from the part's own placement, contacts, or symmetry axis.
4. **Slider semantics.** `spacing` re-solves the layout with different gap
   multipliers; it is not the "explode amount" scrub every viewer-style
   tool offers. There is no way to scrub assembled ↔ exploded; only the
   on/off animation. `depth` (1–8) is an occurrence-path concept with no
   visual affordance for what each notch will do.
5. **Magic-number layout.** Distances are products of tuned constants
   (0.85, 0.28, 0.6, 0.22, 0.35 …) of bounding radii — not editable, not
   in model units, not stable across models. Users cannot type "move this
   650 mm".
6. **Nothing persists as an artifact.** No named exploded views, no explode
   lines/trails, no step sequencing for assembly-order animation, nothing a
   drawing/snapshot can reference besides the eight globals.
7. **Discoverability.** A core assembly-review feature is a subsection of
   the *theme* settings popover, siblings with backdrop color and edge
   thickness.

## 3. How professional tools model exploded views

Survey of SolidWorks, Onshape, Fusion 360, Inventor, FreeCAD 1.x, and
viewer-class tools (eDrawings, Autodesk/APS Viewer, Babylon/three.js).
Sources in §6. Two sharply distinct designs exist:

### 3.1 Authoring tools: an exploded view is a document of ordered steps

Every authoring CAD tool converges on the same model:

- **Persistent named views.** SolidWorks stores `ExplView` features per
  configuration (multiple per configuration, copyable between them);
  Onshape keeps named exploded views in an assembly panel, spanning all
  configurations, with step distances linkable to configuration variables;
  Inventor uses a separate presentation (`.ipn`) file with snapshot views +
  storyboards; FreeCAD 1.x keeps `Exploded_View` objects holding `Move`
  objects. Fusion is the outlier in *location* (exploded views live in the
  Animation workspace as storyboard timelines) but not in *shape* — still
  an ordered list of recorded per-component actions.
- **Steps.** Each step = one movement of one-or-more components:
  translate along a direction, rotate about an axis (SolidWorks 2019+
  regular steps carry both), or a **radial step** (SolidWorks) that pushes
  a bolt circle outward about an axis in one step. Steps are named,
  reordered by dragging, deleted, and edited numerically (exact distance /
  angle typed in).
- **Authoring gesture.** Universally: select components → a **triad/gizmo
  appears** → drag an arm to displace → a step is recorded → refine the
  number. Direction defaults to the assembly axes but can be taken from
  geometry (SolidWorks: drag the triad ball onto a face to align with its
  normal; FreeCAD: align dragger to part origin or selected geometry;
  legacy Inventor auto-explode took directions from **mate constraints** —
  bolts "unscrew" along their insert axis).
- **Sub-assemblies move as units by default**, with explicit opt-in to
  reach inside; SolidWorks additionally supports **"Reuse Subassembly
  Explode"** — importing the sub-assembly's own exploded view as steps of
  the parent's.
- **Explode lines are part of the artifact.** SolidWorks: a 3D "explode
  line sketch" with route/jog lines plus auto "Smart Explode Lines"
  (2021+); Onshape: auto per-step lines, centroid-anchored, **on by
  default**; Inventor: first-class editable "trails"; Fusion: trail-line
  visibility toggle on explode actions.
- **Animation is derived from the steps.** Animate explode/collapse plays
  the step list (optionally reversed); Fusion's manual explode
  distinguishes **one-step** (simultaneous) vs **sequential** explosions.
  Drawings reference a named exploded view/snapshot rather than a live
  slider state.
- **No authoring tool has a global "explode amount" slider.** The closest
  are per-step spacing sliders (SolidWorks auto-space) and Fusion's
  auto-explode "explosion scale" parameter. Scrubbing is step-sequence
  playback (Onshape's rollback bar, eDrawings' step slider).

### 3.2 Viewers: a scalar slider over a centroid heuristic

Viewer-class tools have no authored data, so they synthesize the explode
from one scalar: Autodesk/APS Viewer's explode slider displaces each
fragment along the (model-center → fragment-center) ray scaled by the
slider; Babylon.js ships this verbatim as `MeshExploder`; three.js
tutorials all reimplement it. Its documented failure modes are exactly the
class of complaints against our implementation:

1. non-physical directions (a screw exits sideways, not along its axis);
2. concentric/coaxial parts get zero or arbitrary direction;
3. mid-explode interpenetration (no blocking/contact awareness);
4. sub-assembly internals scatter when the tree is ignored — hence APS's
   hierarchy-aware `explodeStrategy` and commercial tools' level-wise
   explode (children move with parents, displacement damped by depth);
5. radial-from-center is useless for elongated models — hence APS blog
   customizations for "vertical explode" / "explode along levels".

Our axis mode is essentially a hand-rolled "vertical explode"
customization and our radial mode a hierarchy-grouped `MeshExploder`; the
wonkiness is inherent to this algorithm class, not a tuning problem.

### 3.3 Auto-explode, where it exists

Production auto-explode is assistive, not the primary model: SolidWorks
auto-spaces components equally along a dragged axis (ordering by bounding
box) and offers the one-step radial explode; Fusion's Auto Explode
(one level / all levels) respects hierarchy levels with a scale slider and
an undocumented outward-direction heuristic; Inventor's legacy
constraint-driven auto-explode (directions from mates, cumulative distance
per depth) was **removed** in 2017 in favor of manual tweaks. The research
literature (Li et al., SIGGRAPH 2008 "Automated Generation of Interactive
3D Exploded View Diagrams") computes an **explosion graph** from part
contacts and blocking constraints, giving physically-plausible directions,
ordering, and interlocking handling — the north star if we later want
contact-aware auto-explode.

### 3.4 Cross-tool summary

| Aspect | SolidWorks | Onshape | Fusion 360 | Inventor | Viewers (APS etc.) |
|---|---|---|---|---|---|
| Persistence | `ExplView` per configuration | Named views, cross-configuration | Animation storyboards | `.ipn` snapshot views + storyboards | none (slider state) |
| Step model | Ordered steps; translate+rotate; radial | Ordered steps; translate/rotate | Timeline actions | Tweaks on a timeline | single scalar |
| Direction source | Triad; face normal; radial axis | Triad; reselectable axis | Axis arrows; auto heuristic | Triad; (legacy) mate axes | center-to-part ray |
| Auto explode | Auto-space, radial step | none | One/all levels + scale | removed 2017 | the whole mechanism |
| Explode lines | Sketch + Smart Explode Lines | Auto per step, default on | Trail toggle | First-class trails | none |
| Global slider | no | no (step rollback) | only as auto-explode param | no | yes — primary UX |

## 4. Proposed design

Three layers, replacing the current single-heuristic pipeline. The guiding
move is the one every professional tool made: **promote the exploded view
from a display setting to a document — an ordered list of explode steps —
and demote the current heuristic to a generator that seeds that document.**
This serves both viewer users (who get editing) and agents (who get a
declarative per-group format they already invent by hand in the
`*_exploded.step.py` fixtures).

### 4.1 Layer 1 — explode-step data model (cadjs)

A serializable `explodedView` document, per file, versioned:

```js
{
  version: 1,
  name: "default",             // named views later; one view first
  steps: [
    {
      id: "s1",
      type: "translate",        // "translate" | "rotate" | "radial"
      targets: ["o1.3", "o1.4"],  // occurrence paths; groups move rigidly
      axis: [0, 0, 1],            // unit vector in model space
      distance: 650,              // model units (mm), not multipliers
      // rotate steps: axis + origin + angleDeg
      // radial steps: center + per-target outward directions resolved at solve time
    },
    ...
  ],
  order: "simultaneous" | "sequential",  // animation scheduling
  trails: true                            // explode lines, auto-routed
}
```

This is the SolidWorks/Onshape step model with viewer-grade evaluation on
top. `order` mirrors Fusion's one-step vs sequential explosions; `trails`
follows Onshape's default-on auto explode lines (per-step override can come
later).

Semantics:

- **Progress scrubbing is first-class.** The evaluator is
  `translationAtProgress(step, t)` for global `t ∈ [0,1]`; `simultaneous`
  scales all steps by `t`, `sequential` maps step *k* of *N* to the
  `[k/N, (k+1)/N)` slice (collapse animations replay assembly order in
  reverse, like SolidWorks/Fusion animate collapse). Output stays what it is
  today: a per-record `explodedViewMatrix` (now possibly rotation too), so
  the render path, package instancing, and snapshot runtime are untouched.
- **Distances are absolute.** Steps store model units so users can type
  "650" and agents can compute offsets from part sizes; the raptor2
  `OFFSETS` table maps 1:1 onto translate steps.
- **Targets are occurrence paths**, same ids the STEP tree and selection
  already use; a target that names a sub-assembly moves the whole subtree
  rigidly (today's depth-grouping behavior, but explicit and per-step).
- **Chained frames**: later steps see earlier steps' displaced positions
  when `sequential` (matches pro-tool step chaining); `simultaneous` is
  what the current implementation effectively does.

New module `packages/cadjs/src/lib/viewer/explodedViewSteps.js` (evaluator +
validation + (de)serialization), keeping `explodedView.js`'s
progress/animation helpers. cadjs stays non-React per repo rules.

### 4.2 Layer 2 — auto-explode becomes a step generator

The current solver's job survives, reframed: `generateExplodedViewSteps(
records, bounds, hints)` returns a step list instead of directly returning
record states. Same inputs (bounds + occurrence tree; we have no mates), but
with the heuristics upgraded where they are wonky today:

1. **Principal-axis detection instead of a hardcoded axis.** Pick the
   explode axis per scope from the occurrence-center distribution (dominant
   PCA axis of group centers, tie-broken toward model Z). The `axis`
   setting becomes an optional hint, not the only input.
2. **Coplanar groups never serialize.** Groups whose extents overlap along
   the explode axis stay one layer and separate *laterally* (outward from
   the axis, snapped to the nearest principal direction) — i.e. the current
   `mergeCoplanar` behavior becomes always-on, and lateral separation
   replaces golden-angle fanning. Bolt circles and side-by-side jaws
   explode outward or stay with their layer instead of stacking.
3. **Coaxial stacks explode axially.** Detect groups whose XY centers
   coincide with the stack axis (the planetary-gear / gearbox case) and
   keep them on-axis with axial gaps; never scatter them sideways.
4. **Sub-assembly recursion.** Depth *n* explodes: move depth-1 groups
   apart with large gaps, then recursively explode inside each group with
   smaller gaps along that group's own principal axis. Today depth just
   regroups at a finer level and re-solves globally, which loses the
   sub-assembly structure it worked out at depth 1.
5. **Non-overlap by construction along each explode direction** (sweep and
   re-space, as axis mode does today; radial/lateral moves get the same
   sweep along their own direction).

The generated steps are ordinary steps: the user can then delete, retarget,
re-axis, or renumber them. Auto-explode is a seeding action ("Auto
explode"), re-runnable, not a live mode that fights manual edits. Recursion
into sub-assemblies plays the role of SolidWorks' "Reuse Subassembly
Explode": inner explodes become ordinary nested steps of the outer view.

Bounds + occurrence tree is deliberately the whole input for now. The
contact/blocking-constraint approach (Li et al., SIGGRAPH 2008; legacy
Inventor's mate-driven directions) produces the best directions but needs
interference analysis we don't compute at view time; it slots in later as a
better generator behind the same step interface, likely as a cadgen-side
precomputation stored with package topology artifacts.

### 4.3 Layer 3 — viewer UX

Move explode out of the theme popover into a first-class **Explode mode**
(floating-toolbar entry, like Select/Draw):

- **Explode amount slider, 0–100%**, always visible in the mode — the
  universally-understood viewer control (Autodesk Viewer's explode slider,
  eDrawings' step scrub), driving evaluator progress. With
  `order: "sequential"` the same slider walks the step sequence, which is
  exactly eDrawings' behavior over authored SolidWorks steps. Replaces
  "spacing" as the primary slider; a small "gap scale" stays in advanced
  settings and simply scales generated step distances.
- **Auto explode button** with the axis/radial presets (hints to the
  generator), plus Reset/Collapse.
- **Step list panel** (in the file sheet next to the STEP tree): ordered
  steps with target names from occurrence `displayName`s, editable numeric
  distance, reorder, delete; selecting a step highlights its parts.
- **Direct manipulation**: with parts selected (existing
  `useCadWorkspaceSelection` + picking), show a translation gizmo (three.js
  `TransformControls`-style arrows snapped to model axes + the group's
  inferred axis); dragging creates or updates a step; typed distance in the
  step list for precision. This is the SolidWorks/Onshape/Fusion authoring
  gesture, feasible because targets/ids/selection already exist.
- **Explode trails**: optional faded lines from assembled to exploded
  position per moved group (the guide rods raptor2 fakes today), rendered
  through the existing line/edge runtime.
- **Persistence**: the explode document rides the existing per-file display
  state channel, and snapshot jobs accept `exploded: {steps: [...]}` (or
  `exploded: {auto: {...hints}}` for generated ones) through the same
  `DISPLAY_OPTION_KEYS` slot. Old-format settings normalize into an
  auto-explode hint object, so existing URLs/jobs keep working.

### 4.4 Compatibility and phasing

`normalizeExplodedViewSettings` keeps accepting the current shape and maps
it to `{auto: {axis, direction, gapScale, depth, keepBaseGrounded}}`;
`enabled: true` with no steps means "generate on demand". Suggested order:

1. **Phase 1 — model + evaluator + slider.** `explodedViewSteps.js`,
   generator returns steps, CadViewer evaluates steps, explode-amount
   slider in the current popover. Fixes scrubbing and slider semantics with
   no UI relocation. Old settings normalize forward.
2. **Phase 2 — generator quality.** Principal-axis detection, lateral
   separation for coplanar layers, coaxial handling, recursion
   (§4.2.1–5). Snapshot fixtures re-baselined once.
3. **Phase 3 — step list + persistence + snapshot steps.** File-sheet step
   panel, per-file persistence, `exploded.steps` in snapshot jobs; retire
   the hand-authored `*_exploded.step.py` pattern for new models (author an
   explode document next to the base model instead).
4. **Phase 4 — direct manipulation + trails.** Gizmo editing and explode
   lines.

Each phase is independently shippable; Phase 1+2 alone remove the main
"wonky" complaints (serialized coplanar parts, sideways gear scatter,
unscrubable explode, opaque spacing).

## 4.5 Implementation status

Shipped (backwards compatibility intentionally dropped — the old
axis/spacing/depth/mergeCoplanar setting shape is gone):

- **Layer 1 (model + evaluator).** `packages/cadjs/src/lib/viewer/
  explodedViewSteps.js` — step document, compiler, progress evaluator
  (`translate`/`rotate`/`radial`; simultaneous + sequential scheduling),
  derived auto-frame bounds and trail segments. Unit-tested.
- **Layer 2 (generator).** `packages/cadjs/src/lib/viewer/explodedView.js`
  rewritten to emit an editable step document: principal-axis detection,
  coplanar lateral separation, coaxial axial handling, occurrence-depth
  grouping, outward sweep with real gaps. Unit-tested.
- **Settings + snapshot.** `displaySettings.js` carries the step document
  (deterministic for equality/persistence); `renderMeshScene.js` offline
  path resolves authored-or-generated steps and honours the scrub amount;
  snapshot job schema documented; runtime bundle regenerated.
- **Layer 3 (viewer).** `CadViewer.js` compiles + evaluates the document
  (toggle animates, amount scrubs and edits snap) and renders explode-line
  trails. A dedicated, auto-first **"Exploded" tab** (`ExplodedSettingsSection`)
  leads with an Enable/Disable button that toggles Amount to/from zero (controls
  stay visible either way), then a terse flat stack — Amount, a top Automatic/
  Custom switch, a Direction dropdown, Reverse, Spread, Detail, Order, Explode
  lines, Reset — where Custom materializes an editable per-step list (numeric
  distance/angle edit, reorder, delete). Labels are minimal; detail lives in
  hover tooltips. Per-file persistence rides the existing display-settings slice.

Deferred (single follow-up): the **drag gizmo** for direct manipulation
(§4.3). Numeric per-step editing already provides precise authoring; the
`TransformControls` drag affordance needs live-canvas integration
(`useViewerRuntime` init, pick-list exclusion, pointer arbitration) that
cannot be verified headlessly, so it is left as a contained next step — the
integration points are recorded in the exploded-view integration map.

## 5. What this buys, concretely

- The raptor2/starship/merlin1d/falcon_heavy `*_exploded.step.py` pattern
  (a duplicated model per exploded presentation) becomes a small explode
  document next to the base model — reviewable, diffable, animatable, and
  usable by snapshot jobs without geometry duplication.
- Agents get a format they can author reliably: named targets + axis +
  millimeters, instead of reverse-engineering what `spacing: 1.45` will do
  to a given assembly.
- The default un-authored experience improves immediately (Phase 2): no
  more serialized bolt circles or sideways gear scatter.
- Humans reviewing a model get the two controls that actually matter:
  a scrub slider and per-part drag.

## 6. Sources

Compiled 2026-07-06 from vendor documentation and tutorials
(search-indexed content; key claims cross-checked across at least two
sources where possible).

- SolidWorks exploded views, steps, configurations:
  https://help.solidworks.com/2024/English/solidworks/sldworks/c_Exploded_Views_in_Assemblies.htm
- SolidWorks reuse of sub-assembly explode:
  https://help.solidworks.com/2024/English/solidworks/sldworks/t_using_subassembly_exploded_view.htm
- SolidWorks auto-space components:
  https://help.solidworks.com/2022/english/Solidworks/sldworks/t_Auto-Spacing_Components.htm
- SolidWorks radial explode:
  https://www.goengineer.com/blog/create-radial-explode-solidworks
- SolidWorks explode line sketch / smart explode lines:
  https://help.solidworks.com/2021/english/SolidWorks/sldworks/t_adding_explode_lines.htm,
  https://www.goengineer.com/blog/smart-explode-lines-in-solidworks-explained
- eDrawings exploded-view playback slider:
  https://help.solidworks.com/2023/English/eDrawings/t_Exploded_Views.htm
- Onshape exploded views (steps, rollback bar, auto explode lines,
  configuration-linked distances):
  https://cad.onshape.com/help/Content/Assembly/exploded_views.htm
- Fusion 360 exploded views in the Animation workspace:
  https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-create-an-exploded-view-drawing-in-Fusion-360.html
- Fusion Auto Explode one/all levels:
  https://help.autodesk.com/view/fusion360/ENU/?guid=ANI-EXPLODE-ONE-LEVEL,
  https://help.autodesk.com/view/fusion360/ENU/?guid=ANI-EXPLODE-ALL-LEVELS
- Fusion manual explode (one-step vs sequential):
  https://help.autodesk.com/cloudhelp/ENU/Fusion-Animate/files/ANI-EXPLODE-MANUAL.htm
- Inventor presentations (tweaks, trails, snapshot views, storyboards):
  https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-Help/files/GUID-2A480981-2E53-4408-BFA9-290C14F03C95.htm
- Inventor legacy constraint-driven Auto Explode (removed 2017):
  https://help.autodesk.com/cloudhelp/2016/ENU/Inventor-Help/files/GUID-873A362E-843F-44A0-AA6F-5882C24CC632.htm,
  https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Auto-Explode-Removed-from-inventor-2017-Presentations.html
- FreeCAD 1.x Assembly exploded views:
  https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Assembly_CreateView.html
- Autodesk/APS Viewer explode slider + extension + customizations:
  https://aps.autodesk.com/en/docs/viewer/v6/reference/Extensions/ExplodeExtension,
  https://aps.autodesk.com/blog/selective-explode-viewer,
  https://aps.autodesk.com/blog/view-each-floor-using-vertical-explode,
  https://aps.autodesk.com/blog/explode-along-levels
- Babylon.js MeshExploder (canonical scalar radial explode):
  https://doc.babylonjs.com/features/featuresDeepDive/mesh/meshExploder/
- Li, Agrawala, Curless, Salesin — "Automated Generation of Interactive 3D
  Exploded View Diagrams", SIGGRAPH 2008:
  https://grail.cs.washington.edu/projects/exview3D/
- Constraint/interference-based disassembly + exploded view generation:
  https://ieeexplore.ieee.org/document/8374185/

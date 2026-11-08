# The manufacturing checks

`cad.<type>.dfm(source, process=...)` and `cad <type> dfm SRC --process cnc|sheet|molding|printing`:
whether a part can be made by a process, and what to change where it cannot. This is the mechanism; the
library README's **Manufacturing checks** says what the check is for and how it is called.

## Two layers

**Facts.** An integration measures the part and answers a report of plain data: millimetres, degrees,
square millimetres, cubic millimetres and ratios. Exact geometry -- a STEP, an xbf, a document the engine
holds (its id or a model's handle), a live build123d shape -- is measured on its B-rep by the build123d
integration (`cad/build123d/_dfm_<process>.py` over the shared core, `_dfm_brep.py`); a mesh -- an STL, a 3MF,
a GLB -- by the trimesh integration (`cad/trimesh/_molding.py`, `_printing.py`); a DXF, a sheet's cut file,
with ezdxf, build123d's own DXF library (`cad/build123d/_dfm_dxf.py`). CNC machining and sheet metal are
measured on exact geometry alone: a mesh holds no radius, axis or thickness to read, so a mesh type's `dfm`
takes `molding` and `printing` alone, and a DXF's `sheet` alone (`manufacturing.processes_for`).
Geometry both paths share is numpy alone (`cad/_internal/meshops_<process>.py`): numpy is the library's one
required dependency, so neither integration imports the other's.

**Where exact geometry is measured.** In the engine, where the document is held: the caller resolves the
options (`manufacturing.options`) and asks the engine (`cad.engine.api.check`, an `export` carrying a
`check`), which measures it in the kernel process that holds it (`cad.engine.worker._check`,
`_dfm_check.held`) -- a model's document in its script's warm worker, a STEP's or an xbf's file in the
documents worker, read once by the engine's loader and held while the file stays as it was -- and answers the
report, which the caller finishes into its result (`manufacturing.finish`). Nothing is exported, written or
read again, and no process or kernel import is paid. Each part is measured on a copy that shares nothing with
the held document (`_dfm_brep.of_source`: a check's meshing never touches it), its result equal to the same
document's read from its file. The engine keeps each result by the version it measured -- a model's
generation, a file's bytes' digest -- with the check's type, process, options and library release
(`cad_server/engine/checks.py`, 128 results and 64 MB at most, in the daemon's memory), so the same check of an
unchanged document measures nothing; a document holds one version's results. A build of a model's script
cancels a check running in its worker, which answers that it was cancelled; a worker killed in a check says
so, and is not asked again. A file is measured in the calling process only where no engine can be reached
(none installed, a sandbox that cannot start one), as before; a mesh and a DXF are measured in the calling
process (or the integration's environment) always.

**Verdicts.** The type side (this folder, the standard library alone, so the command resolves every option
before it starts an environment) holds each process's options, its rules, the findings its facts call for
and its summary line (`cnc.py`, `sheet.py`, `molding.py`, `printing.py`). Each process has **one table of
rules** (`RULES`, a `rules.RuleSet`: versioned, each rule a limit on one measured field with its source,
`rules.py`), and the checks are **general**: a rule states general practice, and the published design guide
it cites is the evidence for it, never a target -- no rule is a shop's capability (its gauges, its tooled
radii, its machines' sizes, its press). Every verdict says so (`general practice; source: ...`), and every
result says the verdicts are no shop's limits (`rules_general`, info). A shop's own limits are compared with
the measurements, which every result carries (a skill for a named fabrication service does that, reading
the measurements against the service's own published specs); what a person knows of their own shop is a plain
option -- `--tools`, `--axes`, `--stock`, `--thickness`, `--bend-radius`, `--k-factor`, `--kerf`,
`--sheet-size`, `--cavities`, `--build-volume`, `--layer-height`, `--nozzle`, `--material` -- never a rule
set. A rule's id (`cnc.internal_corner_radius`) is its finding's code; its severity is `error` where the
source's number is a feasibility limit (the part cannot be made as drawn under that rule) and `warning`
where it is a recommendation ("should", "recommend"), a cost or a risk, and its note quotes the source's
sentence.

## The process and the options

`--process` names the check, one of the type's: `cnc`, `sheet`, `molding` or `printing` for a model, an xbf
and a STEP; `molding` or `printing` for an STL, a 3MF and a GLB; `sheet` for a DXF, its default, so `cad dxf
dfm cut.dxf` alone checks the cut file. Each type's signature (`manufacturing.dfm_for`) holds its processes'
options alone: the command's choices and flags are the type's, and a mesh's help offers no `--axes`. Given
none, an xbf or a model is checked for the process its parts declare (a STEP keeps no process: its parts'
materials are not written to it, so one given none is refused before anything is read): a part's
`bd_materials` material carries how it is made (`part.material =
metals.aluminum(process=machined())`, its `.process` an `AppliedProcess`), and `processes.declared` maps the
route: `machined` is cnc, `molded` molding, `fdm`, `sls`, `mjf`, `slm` and `vat` printing with `--technology`
fdm, sls, mjf, pbf and sla, an FDM wall's `pitch_mm` its `--layer-height`. A technology or layer height given
wins over the declared one (a technology given takes its own layer height; parts whose layer heights differ
take the technology's, and `process_declared` says so). Cast and wrought stock have no check, and no route
is sheet's: those, parts that declare no process and parts that declare different ones are refused with the
fix (`give --process cnc, sheet, molding or printing`), the command line's mistake (exit 2); a mesh always
needs `--process`.

Every option has a kind (`manufacturing.KINDS`): a count is an `int` (never a `bool` or a float: `axes=3.7`
is refused, not taken as 3), a flag a `bool` (`turning="no"` is refused, not truthy), a length or an angle a
finite number, a list or a size text. A library call of another kind is refused by name
(`_common.require_*`), as the command's parser refuses one, before the process's own `validate` judges the
range.

The options resolve in two steps when the process comes from the parts. `manufacturing.options(type, None,
...)`, the type side, refuses what holds for every process before anything is read -- each option's kind, a
units, a material, a pull beside `--candidates` -- and answers None; the command
then starts the integration's environment, which reads the document (`_dfm_brep.read`), takes the declared
process (`manufacturing.declared`) and resolves the options for it, refusing there an option of another
process (`--pull` on a machined part) with the declared route named. A refusal there comes back to the
command with its reason (`cad._internal.operation`'s answer carries `reason`: `invalid_argument` for an
argument refused by name, `not_found` for a document the engine does not hold), so it exits 2 as the same
refusal does in the command's own process. Given `--process`, every option is resolved and refused before
the read.

## The result

A `cad.results.CheckResult`: `ok` (no error), `findings` (each a severity, a code, a message, a location and,
for a verdict, a `hint` saying what to change), `summary` and `measurements`, the report:

```
{"process": "cnc", "source": {"type": "step", "measured_as": "brep", "document": "plate"},
 "document": {...}, "bodies": [{"name", "owner", "material", "material_table", "process", "bbox_mm", "volume_mm3", ...}],
 "<family>": {"items": [{<fields>, "location": "plate/face 7", "xyz": [x, y, z], "faces": [...]}, ...],
              "count": 12, <scalars>},
 "partial": false, "partial_sections": [],
 "rules": {"title", "version", "note", "context", "evaluated", "failed": [ids], "none_found": [ids],
           "outcomes": [{"rule", "family", "field", "op", "limit", "unit", "severity", "source", "status",
                         "evaluated", "unmeasured", "failures": [{"value", "location", "xyz"}], "reason",
                         "variants"}],
           "sources": [{"id", "publisher", "title", "url", "accessed"}]}}
```

- **Locations.** On exact geometry an item's `location` is a ref in `cad xbf inspect`'s grammar -- the
  part's canonical owner and the face's ordinal (`plate/face 7`, `kit/pin.2/face 3`) -- read with the
  engine's own loader, so `cad step inspect FILE REF` and `cad xbf inspect DOC REF` resolve it to the very
  face; a feature of several faces lists them in `faces`. On a mesh it is `x, y, z` in millimetres. Each
  part of an assembly is measured once, placed where its first occurrence stands.
- **A family that failed** is `{"error": "..."}`, named in `partial_sections`, and an error finding
  (`measurement_failed`); the other families are still reported.
- **Every rule id has one outcome**: `passed` (each item within the limit; with none to judge -- no hole, no
  wall under the family's threshold -- `passed` with `evaluated` 0, reason `none found`, listed in
  `rules.none_found`; with some items lacking the figure, reason `N item(s) not measured`), `failed` (each
  failing item's value, place and the limit), `not_evaluated` (the rules
  give no limit for this material or technology, or the family or the figure was not measured: unverified)
  or `not_applicable` (the rule is for another context -- turning, a sheet given, a cut file -- or reads a
  figure this source's items do not carry, which another rule judges). Rules that come in variants by one
  key (`RuleSet.selector`, printing's `technology`) with no variant of a rule id for the part's value leave
  that rule `not_evaluated`, not `not_applicable`: a technology the rules have no figure for is unverified,
  and a check that evaluated nothing says so (`rules_none_evaluated`, a warning) instead of reading as a
  pass. A figure that was not
  measured is never a pass. A rule id that comes in variants -- by the context (a tool given or not), by
  its items (acute or square corners), a minimum and a maximum of one figure -- answers once
  (`rules._one_per_rule`): the variants that judged are its outcome, merged where several did (`failed` if
  any failed, each item counted once, each failure with its own `op`, `limit` and `severity` where they
  differ, listed in `variants`), a variant that applied but had no limit said in `reason`; where none judged,
  the one not evaluated, else one `not_applicable` (or `not_evaluated` for a selector value the rules lack).
  The record holds every failure; the findings are fewer, what a reader acts on:
  failures of one rule at one ref are one finding (`and N more at this ref`), a warning on a figure of an
  item that already fails an error (the recommendation beside the feasibility limit it exceeds: `draft`
  beside `draft_min`) is left to the record, at most eight refs of one rule are findings and the rest are
  counted in one more, at `measurements.rules` with the rule's fix. Findings come in this order: what puts
  every other figure in doubt first, whatever its severity (`not_watertight`, `not_sound`,
  `measurement_failed`, `units_suspect`: `manufacturing._FIRST`), then errors, then warnings, then the facts
  and assumptions (info).
- **The summary** of a failed check is `<process> <what was measured>; failed: <code> xN, ...`: each rule
  that failed with its count of error failures (the record's, not the findings shown), then every other
  error by its code (`cnc.no_turning_axis`, `sheet.not_sheet`, `measurement_failed`). A check that passed
  says `OK <source>: <process> <what was measured>`, and `(N warning(s))` at its end where it warned.
- **Items** are sorted worst first and capped (a few hundred), with the family's `count`. Every figure is
  finite: the result is JSON (`allow_nan=False`), and a report that is not is `not_finite`.
- **The material** is `--material`'s, else the one the parts declare (`part.material = metals.aluminum()`, a
  `bd_materials` material the document keeps: its family or its name's stem, `materials.declared`), when every
  part that declares one names the same material of the table (`material_declared`, info; a `--material`
  given beside another declared one is said there too); parts that disagree are judged as with none
  (`material_mixed`, info), as is a material the table has no name for.
- **The process** is `--process`'s, else the one the parts declare (above): `process_declared` (info) says
  what was read and from which material (`process cnc, read from the part's declared material
  (Alu_G6061_T6, machined): give --process to check another`), with the technology and layer height taken;
  each body's `process` is its declared route. Parts that declare different routes are not measured: the
  call is refused (`ArgumentRefused`, exit 2), naming each route and its parts, as one that declares none is.
- The source unreadable is `document_unreadable` or `mesh_unreadable`, a missing file `invalid_target` (the
  command refuses one first, `not_found`), a document id the engine does not hold its `NotHeld` (the
  command's `not_found`, exit 2), a
  document with no part that has a face `document_empty`; a part with no face beside others (an empty
  label an exporter left) is skipped and said, `empty_parts` (info).

The Python functions: `cad.<type>.dfm(path_or_id, process=..., ...)`; on a live shape
`cad.build123d.cnc(shape)`, `sheet_metal`, `molding`, `printing` (the same `CheckResult`, refs as the
engine would name its document) and `cad.build123d.unfold(shape, k_factor=)`; on a mesh a program holds
`cad.trimesh.molding(mesh)`, `pulls`, `printing`, `orientations` (the report as data).

## CNC machining

Exact geometry only (STEP, xbf, a document the engine holds, a live build123d shape); a mesh is refused.
Options: `--axes 3|4|5` (default 3), `--turning`, `--tools 3,6,10` (end mill diameters, mm), `--stock 100x60x25`
(mm; default the part's box), plus `--material`.

Every family is `{"items": [...], "count": N, <scalars>}`, items sorted worst first and capped at 200; every
item has `location` (a face ref, `plate/face 7`) and `xyz`; several-face features list `faces`. Each part
of an assembly is measured on its own B-rep; its items carry its refs. A family that raised is
`{"error": "..."}` and is named in `partial_sections`. `machine` echoes axes, turning, tools, stock.

### Families (what each measures, and how)

- **holes** — a connected set of coaxial concave cylinders and cones (plus the planes square to the axis whose
  every neighbour is one of them: a counterbore step, a flat floor); sets on one axis whose cylinders of one
  radius overlap along it are one hole (a hole a slot splits); one radius's cylinders sweep >= 300 degrees
  together. `diameter_mm` (narrowest full cylinder), `depth_mm` (the cylinders' extent along the axis),
  `depth_to_diameter`, `through` / `bottom` (`through`, `drill_point`, `flat`, `closed`, `other`: an exact
  ray along the axis from inside the hole meets the hole's own floor or not), `point_angle_deg` (a drill
  point's included angle), `counterbores` [{diameter_mm, depth_mm}], `countersinks` [{diameter_mm,
  angle_deg}], `axis`, `aligned` (along a world axis), `reachable` (along a direction the machine has),
  `inclination_deg` (to the nearest world axis), `opening`, `drilled` (<= 1 3/4 in), `standard_drill`
  (`"6.8 mm"`, `"1/4 in (6.350 mm)"`, `"#7 (5.105 mm)"`, `"letter F (6.528 mm)"`: within 0.005 mm),
  `drill_deviation_mm`, `tap_candidate` (`"M8x1.25"` where the diameter is an ISO 262 coarse tap drill: a
  fact, not a verdict), `tap_drill`, `tap_nominal_mm` (that thread's nominal); with `--turning`, `relation`
  (axial; radial: square to the axis and meeting it; perpendicular: square to it, beside it; off_axis). Drill table: Wikipedia
  "Drill bit sizes" (ASME B94.11M): metric 0.2-25 mm in its steps, fractional 1/64 in to 1 3/4 in, #80-#1,
  A-Z.
- **threads** — modelled threads: non-analytic faces (no surface of revolution) whose edge points sweep >= 350
  degrees about a cylinder's axis in a radial band under a third of the radius, with a flank edge winding half
  a turn or more (a pitch), with their end caps. `internal`, `major_diameter_mm`,
  `minor_diameter_mm`, `pitch_mm` (axial advance per unwrapped turn of a flank edge), `length_mm`,
  `length_to_diameter`, `modelled` (1). Thread faces are excluded from access, walls, gaps and sharp edges.
- **pockets** — a planar face meeting, by a concave edge (or a concave root fillet), faces lying along its
  normal, and seen end-on (a ray along its normal from it escapes), is a floor; its walls grow along
  concave/tangent edges parallel to the normal. `kind` (`closed`; `slot`: open with opposite walls; `open`),
  `depth_mm` (floor to the walls' rim), `depth_from_top_mm` (floor to the part's top along the normal: tool
  reach), `width_mm` (narrowest exact ray between opposite walls of the pocket), `depth_to_width`,
  `open_boundary_fraction`, `floor_radius_mm` (root fillet), `axis`, `aligned`, `reachable` (along a direction
  the machine has, or none of its edges left unmade: a chamfer mill's V reads as a pocket on one flank),
  `inclination_deg`, `wall_count`, `floor` (its
  floor's ref), `width_faces` (the two walls the width is between; `location` is the first of them, else the
  floor). An open step that reads both ways (floor+wall or wall+floor seen from the side) keeps the shallower
  reading. **Through** cavities (`kind` `through`: windows, through slots, cut-outs, through T-slots and
  dovetails, no floor) are faces along a world axis joined by concave or tangent edges along it, none a floor
  pocket's, none meeting a plane square to the axis by a concave edge, closed around the axis (their normals
  seen along it in no one half-plane: an open valley is no window), with a corner -- a concave cylinder along
  it that is no floor's root fillet (no tangent plane neighbour seen end-on), or a sharp concave edge along
  it; `depth_mm` is the walls' extent along the axis, `depth_from_top_mm` the shallower side's reach,
  `width_mm` / `depth_to_width` as for a pocket, `floor` null.
- **internal_corners** — a pocket's in-plane corners: concave cylinders along the pocket's axis (`radius_mm`)
  and sharp concave edges along it that no tool makes from another side (`radius_mm` 0, `sharp` true,
  `edge`). `height_mm` (the corner's own extent: the cavity depth there), `depth_mm` (from the part's top),
  `radius_to_depth`, `tool_mm` (largest `--tools` tool <= 2r, else 2r), `reach_ratio` (depth / tool_mm),
  `pocket` (its floor's ref; a through cavity's `location`), `folded_edges` (the sharp edges its run makes
  through small edge rounds at its ends -- an edge sharing a vertex and a face with it that runs along its
  axis, or is a face of such a round and under twice its radius long; never a floor-to-wall edge -- folded in
  rather than listed under sharp_edges). A through cavity's concave cylinders and unmade sharp edges along it
  are its corners the same way. `radius_mm` is read to 0.01 mm (`RADIUS_TOLERANCE`: 1.4999
  is 1.5). Floor-to-wall roots are never corners (a flat end mill makes them sharp).
- **sharp_edges** — every other sharp concave edge no rotating tool makes (each with `void_angle_deg`,
  `length_mm`, `edge`, `faces`, `makeable` 0, `radius_mm` 0, `acute`: void under 90 degrees, and `reason`,
  the first that holds: `other_axes` -- a tool along a direction the machine lacks would make it;
  `vertical_corner` -- both faces lie along a machine direction the edge runs along, a corner where the
  tool's side leaves its radius; `acute`; `blocked` -- a face is a plane square to a machine direction, the
  way along it blocked; `no_square_face`). A crease a ball end mill makes is an item too: `made_by`
  `ball_mill`, `makeable` 1, `radius_mm` the ball's (half the smallest `--tools`, else 1.25), `deviation_mm`
  = R (1 / sin(void / 2) - 1), the round's departure from the drawn edge. Made by: an
  end mill where one face is a plane square to an approach direction (a floor or a ceiling), the void angle
  >= 90 and a ray from that face along the direction escapes; a T-slot cutter where a face of the cavity
  the edge bounds is seen along that direction; a 45/60 degree dovetail cutter likewise (its face a plane);
  a 60/90/120 degree chamfer mill along the bisector, and its shoulder (a 150/135/120 degree void: one face
  along the mill's axis, the other looking along it); a ball end mill where the void angle is >= 150 degrees
  (`BALL_VOID_DEG`, the owner's to confirm: the ball's round departs from the drawn crease by
  R (1 / sin(void / 2) - 1), 0.035 R at 150) along a direction both faces look along whose ray from the crease
  escapes; a drill or tap for a hole's own edges. `by_tool` counts every concave edge by the tool. Evaluated at
  each edge's midpoint. An edge sharing a vertex with a reported corner and a face with it (or with a round
  tangent to its faces) is folded into that corner.
- **knife_edges** — convex edges whose material angle is under 45 degrees (`KNIFE_DEG`, printing's): the
  material thins to nothing there. `angle_deg`, `length_mm`, `thickness_mm` 0, `edge`, `faces`. The two faces
  of a knife edge are no wall to each other.
- **walls** — under each sampled point of each face, an exact ray into the material to the first face across
  that faces back (normals within ~45 degrees of opposite; not across a knife edge); the thinnest per face
  under 5 mm: `thickness_mm`, `opposite`, `height_mm` (a plane's extent across its longest concave root edge),
  `height_to_thickness`, `surface`. The 200 listed items are refined to the exact least distance between the
  face and `opposite` (`BRepExtrema_DistShapeShape`; faces sharing an edge or a vertex are not), kept where the
  segment leaves the face within ~45 degrees of its inward normal and its middle is in the material or on the
  boundary: `refined` true, `xyz` the thinnest point. A face and its `opposite` are one item (the thinner
  reading): one web is one finding; gaps likewise.
- **gaps** — the same ray outward across the void (holes and threads excluded); the narrowest per face under
  10 mm: `width_mm`, `opposite`, `surface`; refined the same way, through the void.
- **access** — faces (stock faces on the part's box excluded when no `--stock`) whose sampled points no
  straight line from the machine's directions reaches (exact rays must escape the part; back-facing points
  never count): `unreached_fraction`, `unreached_any_direction_fraction` (200 directions over the sphere),
  `kind` (`undercut`: five axes would reach it; `no_line_of_sight`: nothing straight would), `hole` and
  `hole_axis` (a hole's face, and its axis). Items of `kind` `special_cutter` are the edges only a T-slot or
  dovetail cutter makes, joined by the faces they share, whatever line of sight says: `cutter`,
  `edge_count`, `edges` (their fractions 0). Directions: 3
  axes the six world axes; 4 axes those plus every 15 degrees about the rotary axis (X, Y or Z, the one
  that reaches most); 5 axes those plus every 15 degrees about each world axis, then the part's own and 200
  over the sphere (so five reach at least what four do).
- **setups** — one item per part: the greedy set cover of the sampled area by direction (`directions`
  [{direction, area_fraction, faces}]), `orientation_count`, `setup_count` (clampings: each orientation on 3
  axes; directions square to the rotary axis are one on 4; directions within a half-space above one
  clamping face are one on 5), `unreached_area_fraction`, `rotary_axis`, `sampled_points`,
  `inclined_directions` (each inclined hole's or pocket's own direction: one more orientation and clamping).
- **voids** — closed cavities (inner shells): `volume_mm3`, `face_count`.
- **stock** — per part: `size_mm`, `stock_mm`, `stock_given`, `fits_stock`, `length_mm` >= `width_mm` >=
  `height_mm`, `volume_mm3`, `stock_volume_mm3`, `removal_ratio` (null where the part does not fit).
- **small_features** — faces narrower than 0.5 mm (2 x area / perimeter); scalars `smallest_edge_mm`,
  `smallest_face_mm2`, `fine_faces` (under 1 mm).
- With `--turning` (pockets and internal_corners are then absent): **turning** (per part: `axis` — the line
  whose coaxial cylinders, cones and tori have the most area —, `axis_origin`, `axisymmetric_fraction` (area on
  faces of revolution about it and on planes square to it whose every edge is a circle about it),
  `max_diameter_mm`, `length_mm`,
  `length_to_diameter`, `bar_removal_ratio`, `off_axis_faces`, `sharp_profile_corners`), **turned_diameters**
  (convex coaxial cylinders not groove floors: `diameter_mm`, `length_mm`), **bores** (on-axis holes),
  **grooves** (a coaxial cylinder with both ends meeting square planes by concave edges: `internal`,
  `width_mm`, `depth_mm`, `diameter_mm`), **live_tooling** (off-axis face groups: `cross_hole`, `flat`,
  `slot`, `feature`, with the hole's `relation`).

### Rule ids (finding code = rule id)

Severity e = error (not made as drawn under the source's limit), w = warning (its recommendation). "tools" =
the limit follows the smallest `--tools` tool when given. Every number is Protolabs Network (Hubs)'s "How to
design parts for CNC machining", cited as general practice.

| id | family.field | limit |
|---|---|---|
| cnc.internal_corner_sharp | internal_corners.radius_mm min, sharp corners: the radius to give | 1.25 (e, a 2.5 mm tool's); tools: 0.5 x min tool |
| cnc.internal_corner_radius | internal_corners.radius_mm | 0.025 mm (e, micro tools 0.05 mm); tools: 0.5 x min tool (e) |
| cnc.internal_corner_small | internal_corners.radius_mm min 1.25 (w) | features under 2.5 mm are micro-machining |
| cnc.corner_radius_to_depth | internal_corners.radius_to_depth min 0.3333 (w) | a third of the cavity's depth |
| cnc.corner_reach / _limit | internal_corners.reach_ratio max 4 (w) / 30 (e) | 3-4 D cutting length / 30:1 specialised |
| cnc.sharp_internal_edge | sharp_edges.radius_mm min, message and fix by `reason` (e; `other_axes` w: an angled setup or more axes) | 1.25; tools: 0.5 x min tool |
| cnc.knife_edge | knife_edges.thickness_mm min (w) | metal 0.5 / plastic 1.0 (the feasible wall) |
| cnc.pocket_depth_to_width | pockets.depth_to_width max | 4 (w) |
| cnc.wall_thickness | walls.thickness_mm min | metal 0.5 / plastic 1.0 (e, feasible) |
| cnc.wall_thickness_recommended | walls.thickness_mm min | metal 0.8 / plastic 1.5 (w) |
| cnc.inclined_feature | pockets / holes.inclination_deg max 0 where `reachable` is false (w); 3 and 4 axes (5: n/a) | align features to the six principal directions, else 5 axes |
| cnc.hole_diameter | holes.diameter_mm min | 1.0 (e: "Feasible: any diameter larger than 1 mm") |
| cnc.hole_depth / _limit | holes.depth_to_diameter max | 4 (w) / 40 (e) |
| cnc.drill_size | holes.drill_deviation_mm max 0.005 (w), drilled holes | standard drill sizes |
| cnc.thread_size | threads.major_diameter_mm min 6 (w) | M6 or larger recommended |
| cnc.thread_length / _minimum | threads.length_to_diameter max 3 / min 1.5 (w) | 3 D adds no strength / 1.5 D minimum |
| cnc.gap_width | gaps.width_mm min | 0.05 (e); tools: min tool (e) |
| cnc.gap_width_small | gaps.width_mm min 2.5 (w) | features under 2.5 mm are micro-machining |
| cnc.undercut | access.unreached_fraction max 0.02, kind undercut (w; a hole's face: its fix names the axis) | special cutters |
| cnc.special_cutter | access.edge_count max 0, kind special_cutter (w) | undercuts are machined with special tools, 3 to 40 mm wide |
| cnc.no_line_of_sight | access.unreached_any_direction_fraction max 0.02 (w) | special cutters |
| cnc.enclosed_void | voids.volume_mm3 max 0 (e) | a tool reaches only what it can enter |
| cnc.setups | setups.setup_count max 5 (w) | rotated "up to three or four times" (five clampings) |

No rule judges a machine's size, a lathe's capacity or a shop's own feature limits (its narrowest engraved
line, its smallest part, its turned diameters, grooves and cross holes): those are a shop's, and the
measurements (`stock`, `turning`, `turned_diameters`, `grooves`, `holes.relation`, `pockets.depth_from_top_mm`)
are compared with them. `--stock` given is checked (`cnc.stock_too_small`).

Each finding's message ends with what its item says of itself (`Rule.detail`): `internal_corner_sharp` its
edge, height and depth below the top; `sharp_internal_edge` its edge, the two faces, the void angle and xyz
(its fix names the angle); every `walls` and `gaps` rule the face across (`opposite`) and the thinnest point.

Fact findings (not rules): `cnc.stock_too_small` (e: the part does not fit `--stock`), `cnc.no_turning_axis`
(e, `--turning` on a part with no surface of revolution), `cnc.mostly_not_turned` (w, under half the area
turns), `cnc.live_tooling` (i), `cnc.rotary_axis` (i), `cnc.fine_detail` (i, >= 20 faces under 1 mm),
`cnc.material_assumed` (i: no `--material`, walls judged by metal's limits), `cnc.ball_creases` (i: the
creases a ball end mill rounds, the worst one's departure from the drawn edge).
The summary says a part's setups (an assembly: the most any part takes), never a sum.

Context the rules read: `material_class`, `wall_class` (the class, else `metal`), `tools_given`,
`min_tool_mm`, `axes`, `turning`.

Source (accessed 2026-11-06; the rules' version 2026-11-08): Protolabs Network (Hubs), "How to design parts
for CNC machining".

### What it cannot measure

Tool holder and spindle collisions (access is a line of sight, a tool of zero diameter; width and corner
radius cover the diameter separately); a T-slot or dovetail cutter's actual entry path (its edges are said,
not its clearance); an angled fixture's reach (an inclined feature is counted as one more setup); fixturing and
workholding; tolerances, surface finish, cycle time or cost; thread callouts on a drawing (only modelled
threads and tap-drill diameters); hole axes other than a cylinder's (a slot milled as a hole); pockets whose
floor is not planar (a 3D-contoured cavity is reported through access and walls, not as a pocket); sharp
edges are judged at their midpoint; text and engraving are recognised only as many fine faces and as
narrow gaps; a crease a ball end mill makes is accepted at `BALL_VOID_DEG` whatever the part's tolerance
(its departure is recorded, not judged); turning: ID groove depth beyond the bore, parting/chucking
allowances, and a cone point's angle on the turned profile itself (only a hole's drill point is read).

### Budgets

A part is meshed once and sampled about 400 x sqrt(faces) points by area, at most 6000, each face 1 to 16 (rays grow
with the face count's square root, not the triangulation). Rays along one direction look up a grid of the faces' box
shadows square to it. A point no machine direction reaches is probed on two points a face, at most 32 directions
each (the part's own normals and axes first, then every 15 degrees about each world axis, then 200 over the
sphere); a point that fails all 32 reads as having no line of sight -- a stated cap, so a rare direction can be
missed. A face's unreached share is read on at most 16 points.

## Sheet metal

A STEP, an xbf or a live shape (`cad.build123d.sheet_metal(shape)`) is measured on its exact B-rep
(`cad.build123d._dfm_sheet`); a DXF cut file (`cad dxf dfm FILE --process sheet`) with ezdxf
(`cad.build123d._dfm_dxf`). A mesh is refused (a sheet's radii and thickness are not on a mesh). Options:
`--thickness` (the stock's, compared with the measured; a mismatch is `sheet.thickness_mismatch`),
`--k-factor` (the shop's, from its bend table; default Hubs's air-bending chart by material hardness and
r/t), `--bend-radius` (the shop's; a bend modelled otherwise is `sheet.bend_radius_differs`), `--kerf` (a
hole, web or gap narrower is `sheet.under_kerf`), `--sheet-size` (the shop's largest sheet; else a standard
5 x 10 ft sheet, 3048 x 1524, assumed). A shop's gauges, its tooled radius per gauge, its dies and its
smallest and largest parts are no rule: give the ones it publishes, or compare the measurements with them.

### How it measures (3D)

- **Thickness.** Each face is sampled by area; an exact ray from each sample, square to the face, crosses
  the material to the next face. A planar face whose rays mostly reach an antiparallel planar face is a
  skin; the area-weighted modal distance is the thickness `t`. A coaxial concave/convex cylinder pair `t`
  apart is a bend; a face touching both faces of a pair is a cut edge; a cone between a skin and a coaxial
  hole wall is a countersink. A chamfer or a round of a skin's edge (a slanted plane, a convex cylinder of at
  most `t` along it, a cone, torus or sphere about its normal, within the sheet) is an `edge_break`, and a
  face square to the skin that reaches it and its opposite skin through breaks is a cut edge: its rays run
  across the plate and measure its width, never its thickness. A cone, torus, sphere or freeform face whose
  rays cross `t` is `formed` (a cone between flanges is not a bend). A face square between two opposite planes that face away from each other,
  nearer each other than its own rays run, is the cut edge of a stretch off the thickness (a 3 mm wall's end
  cap): the stretch is judged on its skins, not on rays that run along it. Everything else, and any stretch
  of a skin whose rays cross another distance, is `not_sheet` at its ref; a face standing square on a skin
  (a boss's, patch's or pocket's side) is thicker or thinner by its height off that skin.
- **Bends.** The skins and bend cylinders joined by tangent edges are the sheet's two sides; the side with
  the largest skin is unfolded, its coplanar skins the flanges. A bend's angle is its cylinder's angular
  span (checked against the flanges' normals), its length the extent along the axis, its tangent lines
  where the cylinders meet the flanges. A corner joined without a bend is a `sharp_bends` item: two skins at
  an angle meeting at an edge (`Box + Box`, a shelled box), a round on one side of a corner with no
  concentric round a thickness across (`inside_only`, `outside_only`), or skins no bend joins to the unfolded
  side (`unjoined`); their flanges are not in the flat pattern.
- **Unfold.** Breadth-first from the largest flange: each flange is moved flat (one rigid transform, exact:
  arcs and holes stay arcs and holes) about its bend and out by `BA = angle * (r + K t)`; each bend is its
  cylinder's outline unrolled into a strip `BA` wide (exact for straight ends, sampled where an end is
  curved). A bend about the same axis, radius and angle as the bend that placed its flange (a bend line a
  cut interrupts) is laid along the same line with its own strip, no loop. Fused, this is the flat pattern;
  a hole of the fused flat no face's inner wire gave (one crossing a bend's tangent line, part of both
  faces' outer wires) is read back from it, `in_bend` where it reaches a bend's strip. Where a chamfer or a
  round breaks the cut edge the skin stops short of the cut, so each flange's breaks are laid into its plane
  and fused on: the flat is the cut outline (an 80 x 40 x 3 plate chamfered 0.5 mm unfolds 80 x 40, not 79 x
  39), and a hole with a broken rim is read back from it at its cut size.
  `cad.build123d.unfold(shape, thickness=, k_factor=, material=, bend_lines=False)` returns it
  (`bend_lines=True`: a Compound of `CUT` and `BEND` children, one DXF layer each), and raises `ValueError`
  for a part with a corner modelled without a bend or a flat that does not hold all of its material. Holes, notches, tabs, webs, gaps, flange lengths, reliefs and every distance are measured on
  the flat pattern in the plane (`cad._internal.meshops_sheet`, numpy), each place mapped back onto the
  part for its ref. At K = 0.5 the flat area equals volume / t exactly (`neutral_area_ratio`); the flat's area
  with each strip widened to K = 0.5, over volume / t, is `flat_material_fraction`: 1 where the flat holds
  all of the part's material.

### Families (each `{"items": [...], "count": n}`, items sorted worst first, capped at 300)

| family | per item | notes |
|---|---|---|
| `parts` | `thickness_mm`, `is_sheet`, `why`, `sheet_area_fraction`, `bend_count`, `sharp_bend_count`, `flat_length_mm`, `flat_width_mm` (smallest rectangle), `flat_area_mm2`, `flat_overlap_mm2`, `neutral_area_ratio`, `flat_material_fraction`, `box_short_mm`, `unfold_note`, `flat_bend_lines` | one per part |
| `not_sheet` | `kind` (thicker, thinner, unpaired; `edge_break`: a chamfer or round of a cut edge, its depth `break_mm`; `formed`: a cone, torus or freeform face a thickness across), `surface`, `local_thickness_mm`, `sheet_thickness_mm`, `deviation_mm`, `area_mm2`, `judged` (None on a part that is not sheet, or a round a `sharp_bends` item names: no thickness verdict) | a boss, pocket, round, freeform face |
| `sharp_bends` | `kind` (sharp, inside_only, outside_only, unjoined), `angle_deg`, `inside_radius_mm`, `outside_radius_mm`, `thickness_mm`, `edge_count`, `faces` | a corner joined without a bend: its flange is not in the flat |
| `bends` | `kind` (bend, hem, curl), `inside_radius_mm`, `outside_radius_mm`, `radius_to_thickness`, `angle_deg` (bent from flat), `included_angle_deg`, `flanges_angle_deg`, `length_mm`, `axis`, `axis_origin`, `tangent_lines`, `k_factor`, `k_factor_source`, `bend_allowance_mm`, `bend_deduction_mm` (None for a hem or curl: its mold lines meet nowhere); `faces` [inside, outside] | location: the inside cylinder |
| `flanges` | per bend side: `length_tangent_mm` (least along the bend), `length_tangent_half_mm` (reached by half the bend), `length_inside_mm`/`_half`, `length_outside_mm`/`_half` (mold lines: + r·tan(θ/2), + (r+t)·tan(θ/2)), `length_outside_minus_radius_mm` | the length runs to the free edge or the next bend's tangent line |
| `channels` | `base_length_mm`, `flange_length_mm` (outside), `base_to_flange_ratio` | a flange between two parallel bends turning the same way |
| `reliefs` | per bend end and side where the flange runs on past the bend's end: `kind` (corner where the end meets another bend's end, relieved or not; else bend), `needed`, `present`, `width_mm`, `depth_tangent_mm`, `depth_centerline_mm`, `depth_centerline_minus_radius_mm`, `detail` | a missing relief has width and depth 0, its detail "no relief" |
| `hems` | `inside_diameter_mm`, `gap_mm`, `return_length_mm` | bends of 175 to 185 degrees |
| `curls` | `inside_radius_mm`, `outside_radius_mm`, `angle_deg` | over 185 degrees |
| `holes` | `kind` (round, slot, cutout), `size_mm` (diameter, or least width), `length_mm` (largest extent), `edge_distance_mm` (edge to edge), `in_bend`, `countersunk`, `countersink_diameter_mm`; `faces` | location: the hole's wall; a hole read back from the flat (across a tangent line): the face it lies on |
| `hole_spacing` | `distance_mm` edge to edge, `other` | each hole and its nearest |
| `hole_to_bend` | `distance_tangent_mm`, `distance_centerline_mm` (+ BA/2), `distance_inside_mm`, `distance_outside_mm`, `distance_outside_minus_radius_mm`, `bend` | the nearest bend |
| `notches` | `width_mm` (mouth), `length_mm` (depth), `length_to_width` | pockets of the outline off its hull |
| `tabs` | `width_mm`, `length_mm`, `length_to_width` | facing straight sides, a tip, an inside corner at both sides of the base (proud of the body on three sides: an L plate's leg is no tab) |
| `webs` | `width_mm` | the narrowest material within an outline (a neck, a bridge) |
| `gaps` | `width_mm`, `between` | the narrowest void (slots, holes, gaps between parts) |

DXF adds `cut_file` (`insunits`, `unit`, `mm_per_unit`, `extents_mm`, `layers` with intents, `cut_layers`,
`cut_layer_count`, `contour_count`, `is_drawing`), `scale` (`units_unknown`: every length rule withheld;
`units_suspect` where the declared unit makes the part implausible -- in mm a part under 25.4 mm, every hole
under the given thickness; in inches larger than the sheet (`--sheet-size`, else the standard one) -- its
note giving the part read the other way: a warning, the rules still run in the declared unit), and
defect families, each item `location` = `layer L, TYPE #handle`, `xyz` in mm: `open_geometry` (dangling ends
and branch points, less those an overlap explains: a copy of a curve laid on another meets it at three ends
or leaves its own ends on it), `overlaps` (collinear lines or concentric equal arcs overlapping over a
length, any entity types; an exact copy of another entity's curve is left out when the contours are
chained, so the outline it doubles is still the part's), `self_intersections`, `contour_crossings`, `zero_area_loops`, `annotations` (text,
dimensions, hatches, inserts, points on cut layers), `floating_interiors` (an island inside a hole),
`short_line_runs` (8+ short lines turning a little each way, a curve as chords). The drawing checks every
export runs (`validate_drawing_document`: `units_not_set`, `duplicate_entity`, `zero_length_entity`,
`empty_drawing`, `drawing_document`) are kept as findings. A `BEND` layer's lines give `hole_to_bend`'s
`distance_centerline_mm`.

### Findings of fact (`cad._internal.dfm.sheet.findings`)

`sheet.not_sheet` (error: no constant-thickness sheet, a freeform shell, or a thickness over a quarter of
the part's width), `sheet.sharp_bend` (error: each `sharp_bends` item, one finding per place; the message
says which radius is missing, the hint "model an inside radius r >= t and an outside radius r + t at the
corner"), `sheet.flat_incomplete` (error: `flat_material_fraction` off 1 by more than 3%, the flat is not the
part's blank, where no `sheet.sharp_bend` or judged `not_sheet` face already says why; context
`sharp_bends_found`), `sheet.thickness_mismatch` (error), `sheet.flat_overlap` (error), `sheet.not_unfolded`
(warning: a loop of bends, a flange no bend reaches), `sheet.formed_surface` (error, one per part: its
`formed` faces; a cone or a torus is rolled, spun or stamped, not brake-bent), `sheet.edge_break` (warning,
one per part: its chamfered or rounded cut edges, a second operation after cutting), `sheet.bend_radius_differs`
(warning: vs `--bend-radius`, one a bend), `sheet.bend_radii_mixed`
(info: bends, not hems or curls), `sheet.under_kerf` (error), `sheet.hole_in_bend` (warning),
`sheet.k_factor_assumed` (info); DXF: `sheet.thickness_unknown` (warning: no `--thickness`, naming the rules
that scale with it and were not evaluated; the OK line says so too), `sheet.open_contour`,
`sheet.overlapping_curves`, `sheet.self_intersecting`, `sheet.crossing_contours`, `sheet.zero_area_loop`
(errors), `sheet.annotation_on_cut_layer`, `sheet.floating_interior`, `sheet.short_line_run` (warnings).
A cut file's layers holding cut geometry are counted (`cut_file.cut_layer_count`), never judged: a shop's
file rules are its own.

### Rules (id: family.field op limit, severity; source)

Every length rule is withheld where the units are unknown. `t` = thickness (`scale_by`).

Hubs's numbers unless noted, each citing its page as the evidence for general practice:
`sheet.uniform_thickness` (Protolabs guidelines: uniform throughout) on `not_sheet` items with `judged`: a
thicker stretch's `local_thickness_mm` max the sheet's thickness, a thinner's min it, where the document's
sheet parts share one thickness (`one_thickness`; the message gives both: "local thickness (the sheet's is
the maximum) 3 mm is over the 2 mm maximum"), else `deviation_mm` max 0 per direction; an unpaired face's
`deviation_mm` max 0;
`sheet.thickness_max` parts.thickness_mm max 6 bent / 10 flat, `sheet.thickness_min` min 0.5 (warnings, "We
recommend a sheet metal thickness range"; parts with `is_sheet` alone); `sheet.bend_radius` bends.inside_radius_mm min 1 t (warning; bends, not hems,
which `sheet.hem_diameter` judges);
`sheet.flange_length` flanges.length_outside_minus_radius_mm min 2 t (Hubs min bend height 2t + r; read from
the outside mold line, the page does not say); `sheet.bend_relief_width` reliefs.width_mm min 1 t (bend
reliefs, not corner); `sheet.hole_to_bend` hole_to_bend.distance_tangent_mm min 2 t ("from the start of the
bend radius"); `sheet.hole_diameter` holes.size_mm min 1 t (warning); `sheet.hole_to_edge` min 1 t (warning:
"Holes should be at least the sheet's thickness from the edge");
`sheet.hole_spacing` min 2 t; `sheet.web_width` webs.width_mm min 1 t (warning; Hubs's hole-to-edge applied
to any web); `sheet.notch_width` min max(t, 1.016), `sheet.notch_length` length_to_width max 5,
`sheet.tab_width` min max(2t, 3.2), `sheet.tab_length` max 5 (warnings: notches and tabs "should" be),
`sheet.hem_diameter` min 1 t,
`sheet.hem_return` min 6 t (warning) (Protolabs guidelines); `sheet.flat_length`/`sheet.flat_width` max the
sheet: an error against `--sheet-size` (the shop's sheet, context `sheet_given`), a warning against the
standard 5 x 10 ft blank assumed without it (3048 x 1524; Xometry's page for the largest standard blank).

No rule judges a shop's tooling or capabilities: its gauges and tooled radius per gauge, its die widths and
the distances they set, its largest tooled radius, its brake's angles and bend lengths, its smallest and
largest parts, its relief depths, countersink sizes, channel proportions and file rules. The measurements
carry each of them (`parts.thickness_mm`, `bends.inside_radius_mm` and `angle_deg`, `flanges.length_*`,
`hole_to_bend.distance_*`, `reliefs.depth_*`, `holes.countersink_diameter_mm`, `channels`,
`cut_file.cut_layer_count`) for a shop's own limits to be read against.

Sources, accessed 2026-11-03 (the rules' version 2026-11-08): hubs.com/guides/sheet-metal-fabrication;
protolabs.com sheet metal design guidelines; xometry.com/capabilities/sheet-metal-fabrication.

### What it does not measure

Bend order, tooling access and collisions while bending; grain direction; hardware (PEMs) and their
distances; window and joggle bends; box flange maxima and the corner flange gap;
bump-formed or conical bends (a cone between flanges is not a bend: `sheet.formed_surface`); freeform formed
shells (reported not sheet); closed hems
(modelled as a double thickness: not sheet); a hole crossing a bend is unrolled from samples; a non-straight
bend end is unrolled from samples; notches are hull pockets (a pocket's mouth, not its narrowest width);
tabs need two parallel straight sides. Corner reliefs are reported, not judged (no published number
verified). Hubs's hole-to-bend is stated ("from the start of the bend radius") and read at the tangent line;
only Hubs's flange height is unstated, read from the outside mold line (the rule's note says so).

## Injection molding

`cad <type> dfm SRC --process molding [--pull z|-y|x,y,z] [--wall-limit 45] [--zero-tol 0.05]
[--cavities N] [--material abs|pc|...] [--candidates]`

A STEP, an xbf or a model's document is measured on its B-rep (`cad.build123d._dfm_molding`); every item
is at a face ref (`plate/face 7`) plus `xyz`. An STL, 3MF or GLB is measured as triangles
(`cad.trimesh._molding`), every item at `xyz`. Both share one schema and one algorithm for everything but
draft and feature recognition (`cad._internal.meshops_molding`, numpy only). A mesh report also carries
`notes`: what a mesh cannot say.

On the B-rep a face's surface is its kernel type, and a B-spline or Bezier face that IS a plane, cylinder,
cone, sphere or torus (within a millionth of its size, 1e-4 mm at most: `_dfm_brep.surface`) is read as that
surface. `extrude(taper=)` flaring outward, a loft between similar sections and many STEP exporters write
analytic walls and their fillets as splines; read as splines, their draft would be sampled, not exact, and
their fillets, ribs and bosses unrecognised.

### Families (`measurements.<family>`)

| family | what | how | items (fields the rules read in **bold**) |
|---|---|---|---|
| `draft` | each wall face's draft along the pull and the way it opens | B-rep: plane exact, cylinder/cone with axis along the pull exact (0 / half-angle), other faces the least over points sampled ON the surface; mesh: per region (triangles joined under 20 deg), flat exact, curved 5th percentile of its facets (`spread_deg`), tangent bands excluded | `location`, **`draft_deg`**, `area_mm2`, **`opens`** (`+pull`, `-pull`, `none` = zero draft, `split` = the parting line crosses it), `surface`, `exact`, `depth_mm`, `xyz` |
| `undercuts` | trapped features and what releases them | points on every face shot along the way their face opens (zero-draft: both ways); blocked = trapped; touching trapped faces = one group, split where its trapped points lie apart (three sample spacings; on a mesh, 1.5 probe edges): two snaps under one lid are two features. Release: rays along 8 slide directions in the parting plane + the feature's mean lateral normal + each tilted 45 deg (angled slide); fewest slides covering it (each point assigned to its shortest stroke); else a lifter (short lateral move then a pull, stroke <= 1/4 part size); else a collapsible core (each point freed radially, no common direction); else `none` | `location` (the mostly-trapped face), `faces`, **`trapped_area_mm2`**, `kind` (external/internal), **`release`** (side_action/lifter/collapsible_core/none), `side_actions` (`+x`, ...), `side_action_count`, `angled`, **`stroke_mm`**, **`height_mm`** (along pull), **`width_mm`**, `blocked_by`; scalars: `candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `collapsible_core_count`, `unreleasable_count`, ... |
| `thickness` | the wall: nominal, thin, thick, transitions | rolling ball: at each sampled point the diameter of the largest ball tangent there that no surface triangle cuts into (exact per triangle: corners, edges, insides), capped by the exact ray straight through. Points whose ball is held by a face across a convex edge read low and are left out of medians; a narrow face (rib top, plate end) takes its broad neighbours' wall | `location`, **`thickness_mm`** (area median), `min_mm` (p10), `max_mm`, **`ratio_to_nominal`** (max / nominal), `thin_ratio`, **`feature`** (`wall`, or `rib`/`snap`/`boss`: a feature's face, judged by its own rules, not the wall's range), `xyz` (the thickest point); scalars `nominal_mm` (area median of the faces' walls), `min_mm`, `max_mm`, `ratio_max_nominal`, `thick_sections` (> 1.5 x nominal) |
| `transitions` | abrupt changes of wall | read on the stepped side (`meshops_molding.steps`): two flat faces (mesh: flat regions) facing the same way at two offsets, joined by a chain of at most three faces none parallel to them (a pad's side, a chamfer, a fillet), whose walls differ by a quarter of the nominal or more and by about their offset (one face behind both: not a rib's top, not a wall's rim); its run is the chain's reach across, square to the faces, from one seam to the other. On a mesh a ramp gentler than the regions' 20 deg join merges with its levels and is no abrupt step (3:1 is 18.4 deg). A free-form face no step takes in: the rolling ball's steepest pair of points within four sample spacings whose walls differ by half the nominal (`basis` `ball`) | `location` (the chain's first face), **`transition_ratio`** (run over the change: a vertical step 0, a chamfer its run over its rise), `min_mm` and `max_mm` (the two walls), `change_mm`, `length_mm` (the run), `basis` (`step` or `ball`), `xyz`, `at_xyz` (a point on each seam) |
| `ribs` | thin slabs standing on a wall | two opposite planar faces (within 12 deg) whose inward rays come out of each other, both meeting one base plane at a concave edge or a concave fillet, height >= thickness, length >= 1.5 x thickness; base = the plane it is shortest from. Its ends (faces joining both sides, no wider than the rib) are its roots too: their fillets are the rib's, not corners, and `base_fillet_mm` is the least of sides' and ends'. A rib a trapped face touches (one of its own, or one beside them no larger than its side, not its base) is a snap arm, the face its barb (B-rep only). On a mesh the base is the plane of the base region's triangles along the root (a floor filleted to its walls elsewhere is one curved region) | **`kind`** (`rib`, `snap`), `barb`, **`thickness_ratio`** (root / base wall), **`height_ratio`** (height / wall), **`height_to_thickness`**, **`base_fillet_ratio`** (fillet / rib), **`base_fillet_wall_ratio`**, **`gap_to_thickness`**, **`gap_to_wall`** (gap = median ray to the next face), **`draft_deg`**, `thickness_mm`, `height_mm`, `length_mm`, `base_fillet_mm` |
| `bosses` | cylindrical stands, cored or solid | a convex cylinder, or a cone drafted 5 deg or less, standing on a plane square to its axis (concave edge or fillet), with the largest coaxial concave cylinder or cone inside it reaching half its height; radii at the base | `od_mm`, `id_mm`, `boss_wall_mm` (R - r, or 2R solid), **`wall_ratio`** (boss wall / base wall), `od_to_id`, `height_mm`, `height_to_od`, **`base_fillet_mm`** (its root's: 0 sharp; a mesh finds sharp-rooted bosses only), `hole_floor_above_base_mm` |
| `corners` | internal corners | every concave edge with no fillet (radius 0, `edge` ref) and every concave fillet with two tangent joins: a cylinder's or torus's radius, a free-form blend's from its curvature at its middle (concave where its sampled normals turn toward each other); rib (sides and ends) and boss roots excluded | `radius_mm`, `sharp`, **`ratio_to_wall`** (radius / thinner wall meeting there), `wall_mm`, `edge`, `angle_deg` |
| `projection` | area along the pull | the part triangulated (each triangle naming its face), projected, cells covered on a raster 2000 across the part | per part: **`projected_area_mm2`**, `area_error_mm2` (half the outline's cells), `raster_resolution_mm`, `depth_along_pull_mm`, `span_major_mm`, `span_minor_mm`, `volume_mm3` |
| `envelope` | size against a mold | from the projection and the parting | per part: **`span_major_mm`**, **`span_minor_mm`**, **`depth_along_pull_mm`**, **`depth_from_parting_mm`**, `volume_mm3` |
| `parting` | flat parting plane? | outline pieces within 3 cells of the projection's OUTER outline (a hole through the part along the pull is a shut-off: its rim is no parting line): edges where a +pull face meets a -pull face, zero-draft walls (the line may run anywhere up them), curved faces turning through the pull (sphere centre, horizontal cylinder axis, ...); undercut faces left out (a slide forms them). Flat when every edge/turn is level at one height every wall spans | scalars `flat_parting_possible`, `parting_plane_height_mm`, `parting_plane_range_mm`, `depth_above_mm`, `depth_below_mm`, `depth_from_parting_mm`, `off_plane_count`; items: `kind`, `low_mm`, `high_mm`, `on_plane` |
| `clamp` | clamp force estimate (added by the type side) | area (in2) x factor (tons/in2, Moldminds by resin; unknown: 2-5, estimated at 3) x cavities x 1.15 | per part `tons`, `tons_low`, `tons_high`, `kN`, `tonnes`; `factor_source` |
| `pulls` (`--candidates`) | x, y, z and the principal axes ranked (`molding.ranked`: fewest unreleasable, least undercut area, fewest side actions, least zero-draft area -- areas within a hundredth of the largest wall tie -- then the most draft at its least, a flat parting first); `pull_check` holds the same where the pull looks wrong (below), for the hint | the families above per axis (fewer samples) | `undercut_candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `unreleasable_count`, `zero_draft_wall_area_mm2`, `min_wall_draft_deg`, `flat_parting`, `projected_area_mm2`, `depth_from_parting_mm` |

Kept from today's report: `draft` scalars (`wall_area_mm2`, `zero_draft_wall_area_mm2`, `largest_zero_draft_faces`,
`min_wall_draft`, `wall_draft_histogram_mm2`, `wall_area_by_opening_mm2`, ...), `undercuts` scalars
(`candidate_area_mm2`, `largest_candidate_faces`, `probe_resolution_note` on a mesh; `unintersected_rays` and
its note where the kernel failed to intersect a ray with a face -- that crossing is not found, the family is
measured all the same), `projection`, `scale`, `mesh` (meshes). Fact findings: `zero_draft_walls`,
`undercut_candidates` (now with feature counts), `coarse_curved_face` (info), `probe_resolution`,
`rays_unintersected` (warning: the undercut figures are a lower bound there), `several_bodies` (also for a multi-part document, and a
warning for a part of several solids: they shadow each other), `zero_draft_walls` and `undercut_candidates`
(their hints: when half the wall area or more reads zero draft, or a quarter of the surface or more is
trapped -- an engineering trigger, no source's -- the pull may be the wrong one; on one part of one solid the
pulls are then ranked, `pull_check` (the cost of a `--candidates` run), and the hint names the one it ranks first),
`stepped_parting` (new, warning), `resin_unknown` (info), `clamp_estimate` (info), `thickness_unmeasured`.

### Rules (each rule's id is the finding's code)

Sources, each cited as the evidence for general practice: Hubs `https://www.hubs.com/guides/injection-molding/`;
Protolabs design guidelines
`https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/`;
Protolabs uniform-wall tip `https://www.protolabs.com/resources/design-tips/improving-part-design-with-uniform-wall-thickness/`;
Xometry ribs `https://www.xometry.com/resources/injection-molding/plastic-ribs-for-injection-molding-design/`;
Moldminds clamp calculator `https://moldminds.com/clamp-force-calculator/` (all accessed 2026-11-03; the
rules' version 2026-11-08).

| rule id | field | limit (severity; source) |
|---|---|---|
| `molding.draft_min` | draft_deg min | 0.5 error (Protolabs) |
| `molding.draft` | draft_deg min | 2 warning (Hubs "A minimum draft angle of 2° is recommended."; Protolabs "Most situations: 2°"; Hubs' 1-2 deg is a textured face's extra) |
| `molding.undercut` | trapped area, release side_action/lifter/core | warning (Hubs) |
| `molding.undercut_unreleasable` | trapped area, release none | error |
| `molding.wall_min` / `wall_max` | thickness_mm (the face's wall, `feature` wall: a junction's thickest point is thick_section's) by `--material` | the wall table by resin (Protolabs), warning |
| `molding.thick_section` | ratio_to_nominal max 1/0.6 | warning (Protolabs 40-60%) |
| `molding.wall_transition` | `transitions`.transition_ratio min 3 | warning (Hubs) |
| `molding.rib_thickness` | thickness_ratio max 0.6 | warning (Xometry) |
| `molding.rib_height` | `kind` rib: height_ratio max 3 | warning (Hubs "max. height equal to 3x the wall thickness"; it also says "Define a height smaller than 3 × rib thickness") |
| `molding.rib_base_fillet` | base_fillet_ratio min 0.25 | warning (Hubs) |
| `molding.rib_gap` | `kind` rib: gap_to_wall min 2.5 | warning (Xometry) |
| `molding.rib_draft` | draft_deg min 0.5 | warning (Xometry) |
| `molding.snap_thickness` | `kind` snap: thickness_ratio min 0.5 | warning (Hubs "Design snap-fits with thickness greater than 0.5x the wall thickness") |
| `molding.boss_root_fillet` | base_fillet_mm min 0.01, any rounding | warning (Hubs "the base of vertical features (like ribs, bosses, snap-fits) must also always be rounded"; no source gives a radius) |
| `molding.boss_wall` | wall_ratio max 0.6 | warning (Protolabs) |
| `molding.inside_corner_radius` | ratio_to_wall min 0.5 | warning (Hubs) |

No rule judges a press or a mold: its projected area, its largest part, its depth from the parting line,
its shot volume and its side actions' travel are a shop's, read against the measurements (`projection`,
`envelope`, `undercuts`' strokes) and the clamp estimate.

The wall table by resin (Protolabs', in inches, converted to mm): ABS 0.045-0.140, acetal 0.030-0.120, acrylic 0.025-0.500,
LCP 0.030-0.120, nylon 0.030-0.115, PC 0.040-0.150, polyester (PBT, PETG) 0.025-0.125, PE 0.030-0.200,
PP 0.035-0.150, PS 0.035-0.150 PPS 0.020-0.180, polyurethane 0.080-0.750, long-fiber reinforced 0.075-1.000 (HDPE and LDPE read polyethylene's row).

### What it cannot measure

- Exact draft of a mesh's curved face (chords read low by up to `spread_deg`); fillet radii on a mesh
  (filleted corners and rib roots merge into one region: corners lists sharp ones, ribs only sharp-rooted
  ones); bosses on a mesh only with their axis along the pull. A free-form fillet's radius is read at its
  middle (a variable one reads one figure).
- Texture draft (no texture option), tall-feature extra draft (Hubs +1 deg / 25 mm over 50 mm), shut-off
  draft (3 deg), stripping undercuts (lead angle, 5% of diameter), a snap's barb and a mesh's snap arm (read
  as a rib), living-hinge proportions,
  threads, boss OD against a screw (no screw size), gating, weld lines, filling, cooling, warpage, shrinkage.
- The undercut test samples points (2400 per part, at least 12 a face): a feature smaller than the point
  spacing can be missed; the lifter stroke is capped at a quarter of the part; an undercut freed only by a
  slide in a direction other than the 25 tried reads `none`.
- A side action's travel is to where the pull clears, not including the slide's own clearance.
- A component model whose contacts are fused into one solid with its housing (a KiCad connector) reads its
  pins as walls and ribs and its contact slots as undercuts: check the housing alone. Contacts kept as their
  own solids are said (`several_bodies`).
- Clamp force is the part's projected area alone (no runner), a molder's factor table, not a resin's cavity
  pressure.

### Budgets

Each face's points are chosen by area before they are mapped to the surface, about 6000 a part; wall thickness is
read at a fixed number of points whatever the face count (a small face of a part of thousands takes its broad
neighbours' wall); rays along one direction look up a grid of the faces' box shadows. The undercut release search
spends at most 200000 rays a part, largest features first; a feature left over reads release `unknown`, is counted
in `unsearched_count` and is still judged by `molding.undercut`. Between world-axis slides freeing about as many
points (within a fiftieth), the first in the candidates' order is taken, +x before +y.

## 3D printing

### The check

`cad <type> dfm --process printing` (`cad.step.dfm(..., process="printing")`,
`cad.build123d.printing(shape, ...)`) measures a part as it stands on the plate (its lowest point, Z up) for one
technology: `--technology fdm|sls|sla|mjf|pbf` (default `fdm`; `pbf` is metal powder bed fusion, DMLS/SLM).
Options: `--build-volume XxYxZ` (mm, the printer's; default a typical machine of the technology's, assumed), `--angle-limit` (deg from
horizontal; default the technology's: FDM 45, SLA 19, metal 45, SLS/MJF 0), `--layer-height` (mm; default FDM 0.2,
SLA 0.1, SLS 0.1, MJF 0.08, metal 0.03), `--nozzle` (FDM's only), `--samples` (rays, default 2000), `--material`,
`--candidates`.

A STEP, an xbf or a document id is measured on its exact geometry (B-rep), every item at a face ref
(`bracket/face 7`, resolved by `cad xbf inspect`); an STL, a 3MF or a GLB as triangles, every item at `x, y, z`.
The powder processes (SLS, MJF) need no support: their overhangs are facts, never verdicts, and trapped powder is.

### Families (`measurements.<family>`)

Every family with features is `{"items": [{..., "location": ref, "xyz": [x, y, z]}], "count": n, <scalars>}`,
items worst first, at most 300. A family that fails is `{"error": "..."}` and is named in `partial_sections`.

| family | exact geometry (B-rep) | mesh |
| --- | --- | --- |
| `solid` / `mesh` | per part: `solids`, `shells`, `closed`, `inner_shells`, `sound` (the kernel's boolean-argument check, `issues` its BRepCheck codes), `volume_mm3`; scalars `body_count`, `volume_mm3`, `watertight`, `sound` | `mesh`: `watertight`, `body_count`, `volume_mm3`, ... (unchanged) |
| `overhangs` | per down-facing face off the plate: `angle_deg` (a plane's exactly, a curved face's least over its samples), `area_mm2`, `area_below_limit_mm2`, `height_mm`, `kind`: `slope`, `bridge`/`cantilever`/`ceiling` (a flat face, see `bridges`), `hole` (a hole's arch), `plate_edge` (a round or chamfer on the plate's edge whose under-limit part is within 1 mm / 5 layers of it); `reach_mm` (a flat face's, from `bridges`); `counted`: false for a face too small to need support -- under `OVERHANG_AREA_MM2` (1 mm2) below the limit, or a cantilever reaching less than the nozzle's width (`--nozzle`, else `OVERHANG_REACH_MM`, 0.4 mm) -- which no rule judges (both floors text-to-cad's own: no guide states them, and the family's `method` says so); an angle within 1e-6 deg of the limit is at it (`ANGLE_EPS`: a kernel's 45 deg chamfer reads 44.999999999999936); scalars `down_facing_area_below_limit_mm2` (the counted faces, holes, bridges and plate edges aside), `area_floor_mm2`, `reach_floor_mm` | connected regions of the counted triangles, same fields and floors |
| `bridges` | flat (< 5 deg) down-facing planes: `kind` `bridge` (the farthest point lies within the convex hull of its supports: `length_mm` = twice the farthest distance to a supporting edge = the span between the walls), `cantilever` (beyond one support: `length_mm` = its reach), `ceiling` (none); supporting edges are the concave edges whose other face descends. A horizontal hole's arch is no bridge (each layer stands on the one below but the crown's): `printing.horizontal_hole` judges its diameter | the flat regions and any region carried on both sides (a hole's crown among them: a mesh has no axes) |
| `wall_thickness` | per face, the thinnest exact ray into the material from its samples, `sampled: true` (a face's thinnest sample, which can read above the exact least thickness between samples: a keycap's 0.6129 against 0.5493). A ray counts where the face it lands on looks back along it, its normal there within 45 deg of the ray (`KNIFE_DEG`), whether or not that face shares an edge with the ray's own: past it the ray measured a corner (a rim whose sides meet at 50 deg reads alike on both paths, and a sharp 50 deg tip as the same tip blunted by 0.0001 mm). One landing on a face that shares an edge with its own within `SEAM_HIT_MM` (0.05 mm) met the seam and is dropped; a ray inside a knife edge's `thin_depth_mm` that starts or lands on one of the knife's two faces (its flanks) is that knife's sliver -- from a flank, or from a face meeting them at the knife's end across to one -- reported by `knife_edges` alone, while a ray near it between two other faces (a fin beside the knife, across itself) measures its own wall; pins are the pins' rules'. `thickness_mm`, `opposite`, `supported` (joined to the part on 2+ sides: the face's or its opposite's concave edges, smooth joins into a concave round, or a closed ring), `joined_sides`; scalars `min_mm`, `p05_mm`, `p25_mm`, `median_mm`, `max_mm` | per body, `--samples` rays from points at random over the surface, and on a mesh of at most `COVER_MAX_TRIANGLES` (5000) triangles one more from every triangle's centre (`cover: true`; on 60 real meshes the pass cost 26 times the family's time and found 3 thin places against 9 that are not there, while under 5000 triangles it found a knob's 0.27 mm web 2000 random rays miss, with no false one); a ray counts where it lands on a face turned toward it (within 45 deg) and is no knife's sliver: inside a knife's thin depth, starting or landing on one of its flanks (the triangle's normal within 20 deg of a flank's, `FLANK_DEG`). Items the thinnest per cube of diag/40 (>= 2 mm), `supported: null`; `min_mm` .. `max_mm`, `samples_valid` and `thinnest_samples` are of the same rays as the items, per body too; `method` says which rays ran |
| `gaps` | per face, the narrowest exact ray out of the material to another face of the same part (not a neighbour, not the same hole), up to 3 mm, each pair once | one ray out of every triangle to a facing wall of the same body (a hole reads as a gap); under `GAP_DEFECT_MM` (0.05 mm) faces lie on faces -- doubled or overlapping triangles, the mesh's defect -- reported once as `overlap` (`mesh_overlap`), never an item |
| `holes` | concave cylinders round one axis covering >= 250 deg: `diameter_mm`, `depth_mm`, `orientation` (vertical < 10 deg, horizontal > 80 deg, else inclined), `through`, `teardrop` (horizontal and no material within 15 deg of the top), `channel` (depth >= 5 d), `coverage_deg` | not measured (no axes) |
| `pins` | convex cylinders the same way: `diameter_mm`, `height_mm`, `aspect_ratio` | not measured |
| `details` | a planar side face between a parallel top (its convex edge) and bottom (its concave edge) at most 2 mm apart, narrower than `DETAIL_ACROSS_MM` (3 mm: text, a logo, a mark; a wider step -- a groove, a land, a ledge -- is the part's geometry): `emboss` where it is narrower through the material (the side's rays in) than across the air (its rays out), else `engrave`; `height_mm` (the step), `width_mm` (that narrower extent) | not measured |
| `clearances` | each pair of parts within 5 mm: exact `distance_mm` (BRepExtrema), `kind` `gap`/`contact`/`overlap` (`overlap_mm3` by boolean), `parts` | each pair of bodies (inside-out void shells and slivers dropped): closest points of vertices and triangle centres |
| `trapped_volumes` | cavities: every solid's inner shells exactly (`exact: true`, volume from the shell), and from a voxel field (<= 1.5 M voxels) the air a ball of r = clamp(0.2 x smallest side, 3 voxels, 6 mm) cannot reach from outside (open hollows) and sealed pockets; `sealed` (a voxel pocket under 8 voxels, `POCKET_MIN_CELLS`, is the voxelisation's and dropped), `escape_holes` (each run of an exact hole along its axis with one end in the cavity and the other outside -- one cut through two opposite walls is two holes -- plus voxel openings no hole explains), `escape_hole_diameters_mm`, `min_escape_hole_mm`, `min_wall_mm` (the wall samples whose outside lies in the cavity), `volume_mm3` | the voxel field alone; opening widths estimated ((2 depth + 3) voxels) |
| `knife_edges` | convex edges whose material angle (at the middle) is under 45 deg (`knife_below_deg`): `location` the edge ref (`lip/edge 14`), `faces`, `angle_deg`, `length_mm`, `thickness_mm` 0, `thin_depth_mm` = min wall / (2 tan(angle / 2)) (how far in the material stays under the rules' unsupported-wall minimum, `min_wall_mm`; at most `THIN_DEPTH_CAP_MM`, 10 mm, past which the sliver is a fin the walls read; none under `FOLD_DEG`, 2 deg), `thin_area_mm2`. Why 45: that depth is half a wall at a 90 deg corner (one bead), 1.2 walls at 45, 1.9 at 30; 45 deg is also the guides' self-supporting chamfer. The sliver is the knife's alone: the walls drop the rays inside `thin_depth_mm` that start or land on its two faces | convex creases between triangles of material under 60 deg (`CREASE_DEG`) and at least `FOLD_DEG` (2 deg: a sharper crease is a fold of the tessellation, two triangles doubled back, whose depth would reach anywhere -- a 0.227 deg one on a watertight shin wiped every wall ray within 201 mm), chained by shared corners; a chain is a knife where its angle, its creases' median by length (as the exact path reads an edge at its middle: a curved 41 deg edge meshes as creases of 4 to 58 deg), is under 45 deg and it is at least as long as its thin depth (a shorter one is a sliver triangle's crease); same fields at `xyz` |
| `build_volume` | the document's box in the volume in the best of the six axis orientations: `fill_ratio` (largest side over the volume's: <= 1 fits), `fits`, `best_axes`, `as_placed_fill_ratio`, `max_dimension_mm`, `volume_mm`, `volume_origin` | same |
| `bed` | planar faces facing -Z on the plate: `contact_area_mm2`, `contact_length_mm`, `footprint_mm`, `contact_ratio`, `sharp_bottom_edges_mm`, `holes_on_plate` | contact triangles; `holes_on_plate: null` |
| `stair_stepping` | per face, the area between 0.5 and 20 deg from horizontal: `angle_deg`, `cusp_mm` (layer cos angle), `step_width_mm` (layer / tan angle), `facing`; `area_by_angle_mm2` | regions of such triangles |
| `support_volume` | column fill under every down-facing surface under the angle limit, down to the part or the plate, from a raster (<= 90 000 columns) of the triangulation along Z: `estimated_support_volume_mm3`, `support_contact_mm2`, `support_contact_cosmetic_mm2` (faces of 5% of the part's area or more, holes aside), items per face touched | same raster |
| `sections` | the largest ball each part's material holds (voxels, up to 12 mm: `at_least`), `max_cross_section_mm2`, `max_cross_section_z_mm`, `largest_section_change_mm2` | same |
| `scale` | `bbox_diagonal_mm`, `units_suspect` | unchanged |
| `orientations` (`--candidates`) | the six axis orientations plus up to four of the largest flat faces laid down: `support_volume_mm3`, `support_contact_mm2`, `support_contact_cosmetic_mm2`, `build_height_mm`, `bed_contact_mm2`, `overhang_area_mm2`, `stair_step_area_mm2`, `fill_ratio`, `fits`, `score`, `rank`, `rotation` (3x3) and `rotate` (the same as build123d makes it, pasteable: `bd.Rot(-90, 0, 0)`; turn the part in its model); `weights` | the six axis orientations |

**Ranking** (`orientations.weights`): each figure over the largest any candidate has, weighted, summed, lowest
first. Support processes (FDM, SLA, metal): support volume 0.30, support contact 0.15, contact on cosmetic faces 0.10,
build height 0.15, overhang area 0.10, stair-step area 0.10, lack of bed contact 0.10. Powder (SLS, MJF): build height
0.50, stair-step area 0.30, overhang area 0.20.

### Findings that are facts

`not_watertight` (every figure of an open surface is suspect), `not_sound`, `several_bodies`, `overhangs` (info
for powder; with a hint, and on an assembly the sentence that the parts are measured as printed together, in place,
and a part printed on its own is checked by its own id), `plate_edge_round` (info: rounds on the plate's edge facing
down under the limit; a 45 deg chamfer is not one), `walls_not_measured`, `internal_void` (FDM: a sealed void prints
as infill; never on an open mesh, whose voxel "voids" are its holes), `no_bed_contact`,
`warping_risk` (FDM in abs, nylon, nylon_gf, pc, pc_abs, pp, peek, pei, pom, pbt with a flat bottom on the plate),
`elephant_foot` (FDM: holes open on the plate), `mesh_overlap` (a mesh's faces lying on faces under 0.05 mm: its
defect, said once at its place, no gap).

### Rules (every limit keyed by `technology`)

The rules take, per technology, the first published design guide's figure: Hubs's where Hubs gives one, else
Protolabs's, else Xometry's (and apply Hubs's SLS escape-hole figure to the other powder beds, saying so), each
cited as the evidence for general practice, not as a printer's or a shop's limit. The build volume is the
printer's given (`--build-volume`), else a typical machine of the technology's (Hubs's: a desktop printer for FDM
and SLA, `BUILD_VOLUMES`), assumed and said. The `selector` is `technology`: a rule id with no figure for the
technology is one `not_evaluated` outcome ("the rules give no limit for technology fdm"), never a pass, and a
check that judged nothing says so (`rules_none_evaluated`).
The rules' version is 2026-11-08. A rule no fetched guide states cites `text-to-cad-own` ("text-to-cad's own
figure; no fetched guide states one") and its findings say so: `printing.knife_edge`, `printing.horizontal_hole`.
Severity follows the source: a feasibility limit is an error, a recommendation or an unsourced figure a warning.
Sources (accessed 2026-11-03): hubs-thin-walls, hubs-geometry, hubs-fdm, hubs-sla, hubs-sls, hubs-mjf, hubs-metal,
protolabs-toolkit, protolabs-metal, protolabs-7mistakes, xometry-fdm, xometry-sla (Xometry Pro SLA quick reference),
xometry-3dp, xometry-guide (Xometry Pro design guide) -- URLs in `cad._internal.dfm.printing.SOURCES`.

| rule id | family.field | op | limit (fdm / sla / sls / mjf / pbf; source) | severity |
| --- | --- | --- | --- | --- |
| printing.wall_supported | wall_thickness.thickness_mm (supported) | min | 0.8 / 0.5 / 0.8 / 0.7 / 0.4 (hubs-thin-walls) | error |
| printing.wall_unsupported | wall_thickness.thickness_mm (not) | min | 0.8 / 1.0 / 1.0 / 1.0 / 0.8 (hubs-thin-walls) | error |
| printing.wall | wall_thickness (mesh, supported unknown) | min | as supported | error |
| printing.hole_diameter | holes.diameter_mm | min | 1.0 (xometry-fdm, warning: "to retain a circular shape") / 0.8 warning ("may close off") and 0.5 error (its table's minimum) (hubs-sla) / 1.5 (hubs-sls) / - / 1.5 (hubs-metal) | error* |
| printing.pin_diameter | pins.diameter_mm | min | - (Hubs FDM: pins under 5 mm "can be made up of only perimeter prints", no minimum) / 0.5 (xometry-sla) / 0.8 (hubs-sls, warning: "recommended") / 0.5 (hubs-mjf, warning) / 0.6 (hubs-metal) | error* |
| printing.pin_aspect | pins.aspect_ratio | max | pbf 8 (hubs-metal) | warning |
| printing.overhang_angle | overhangs.angle_deg (slope, ceiling, cantilever; metal also bridge; `counted` only) | min | fdm 45 (hubs-fdm), sla 19 (hubs-sla), pbf 45 (protolabs-metal: Hubs metal lists 50 deg, its reference axis unstated, so the rules keep Protolabs's 45) | warning |
| printing.bridge_length | bridges.length_mm (bridge) | max | fdm 5 (hubs-fdm), sla 21 (hubs-sla) | warning |
| printing.cantilever_length | bridges.length_mm (cantilever) | max | sla 1.0 (hubs-sla), pbf 0.5 (hubs-metal) | warning |
| printing.horizontal_hole_diameter | holes.diameter_mm (horizontal, no teardrop) | max | pbf 8 (protolabs-metal) | warning |
| printing.horizontal_hole | holes.diameter_mm (horizontal, no teardrop) | max | fdm 10 (`HORIZONTAL_HOLE_MM`, text-to-cad-own: Hubs FDM gives no diameter) | warning |
| printing.clearance | clearances.distance_mm | min | fdm 0.762 (xometry-3dp), sla 0.5, sls 0.3, mjf 0.9 (hubs), pbf 0.635 (protolabs) | warning |
| printing.gap | gaps.gap_mm | min | fdm 0.762 (xometry-3dp, warning: its general "clearance between features" line, no FDM limit), sla 0.635, sls 0.762, mjf 0.508, pbf 0.635 (protolabs-toolkit) | error* |
| printing.escape_holes | trapped_volumes.escape_holes | min | 1: sla (hubs-sla); sls, mjf, pbf (hubs-sls, applied) | error |
| printing.escape_hole_diameter | trapped_volumes.min_escape_hole_mm | min | 3.5: sla (hubs-sla), sls (hubs-sls), mjf, pbf (hubs-sls, applied) | warning |
| printing.hollow_wall | trapped_volumes.min_wall_mm | min | sla 2.0 (hubs-sla) | warning |
| printing.build_volume | build_volume.fill_ratio | max | 1.0 against the machine given (`--build-volume`: error), else against a typical machine assumed (a warning naming it: "against an assumed typical fdm machine, 200 x 200 x 200 mm: give --build-volume"; fdm 200 x 200 x 200, sla 145 x 145 x 175, sls 300 x 300 x 300, mjf 380 x 285 x 380, pbf 250 x 150 x 150, hubs-geometry) | error / warning |
| printing.emboss_height | details.height_mm (emboss) | min | fdm 1.0 (xometry-fdm), sla 0.1, sls 1.0, mjf 0.3048 (protolabs), pbf 0.4 (hubs-metal detail) | warning |
| printing.engrave_depth | details.height_mm (engrave) | min | sla 0.4, sls 1.0 (hubs) | warning |
| printing.engrave_width | details.width_mm (engrave) | min | sla 0.4 (hubs-sla), pbf 0.4 (hubs-metal) | warning |
| printing.warp_length | build_volume.max_dimension_mm | max | sls, mjf 177.8 (protolabs-7mistakes) | warning |
| printing.knife_edge | knife_edges.thickness_mm (0 at the edge) | min | the unsupported-wall rows' figures: 0.8 / 1.0 / 1.0 / 1.0 / 0.8 (text-to-cad-own: no guide defines a knife edge; the tip prints rounded, Hubs SLS: "A radius of less than 0.4mm on a design is printed as 0.4mm") | warning |
| printing.section_thickness | sections.thickness_mm | max | pbf 10 (hubs-metal) | warning |

\* severity per row: SLS and MJF pins, Xometry's FDM walls and holes, Hubs's SLA 0.8 mm hole and FDM gaps are
warnings (a recommendation, a risk or a general line), the rest errors. There is no FDM pin row.

### What it cannot measure

- On a mesh: holes, pins, embossed and engraved details (no axes or faces): their rules read "holes was not
  measured", never a pass; a mesh's hole reads as a gap. Whether a mesh's wall is supported (judged against the
  supported minimum, `printing.wall`).
- Escape-hole sizes on a mesh, and openings that are not round holes on a B-rep, are estimated from the voxels (to
  about a voxel). Cavities smaller than the probing ball are found only when sealed.
- Support is a column fill (vertical supports, no tree supports, no support angle or density); its contact on
  "cosmetic" faces is a size rule (5% of the part's area), not the designer's intent.
- Supported vs unsupported walls are read from the face's concave edges; a wall joined along one long edge split
  into several reads as joined more times.
- Lattices, minimum feature by local curvature, text legibility, tolerance stack-ups, residual stress beyond the
  largest cross-section and thick sections. FDM's horizontal holes are judged by diameter against text-to-cad's
  own 10 mm (no fetched source gives one).
- An assembly is measured as printed together, in place: its contacts are clearances of 0 and its parts' undersides
  in the assembled pose are overhangs. A part printed on its own is checked by its own id.

### Budgets (exact geometry; each stated in the report it limits)

- Samples: `--samples` (2000) by area, each face at least 4 -- fewer when the floor alone would pass 6000 (a part of
  thousands of faces gets one each) -- at most 400; a face of many triangles keeps its count, spread over them.
  The wall and gap rays of a part are cast together (one slab test per chunk of 64 rays against every face box).
- Clearances: each side of a pair thinned to 1500 points; the 3 nearest face pairs measured exactly
  (BRepExtrema) where the triangulations come within 1.5 mm plus their margin, at most 90 exact queries a document,
  nearest pairs first; the rest keep the triangulations' distance (`exact: false`, `uncertainty_mm`); at most 4
  overlap booleans.
- Soundness: the kernel's boolean check on parts while their faces add up to 200; the rest BRepCheck topology alone
  (`solid.items[].check`).
- Flat ceilings: the 40 largest refined to the exact farthest point; the rest read on their samples (`refined`).

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
measured on exact geometry alone: a mesh holds no radius, axis or thickness to read, and is refused by name.
Geometry both paths share is numpy alone (`cad/_internal/meshops_<process>.py`): numpy is the library's one
required dependency, so neither integration imports the other's.

**Verdicts.** The type side (this folder, the standard library alone, so the command resolves every option
before it starts an environment) holds each process's options, its rule sets, the findings its facts call
for and its summary line (`cnc.py`, `sheet.py`, `molding.py`, `printing.py`). A **rule set** is a named,
versioned table of rules for one process, each rule a limit on one measured field with its source
(`rules.py`). `--rules` picks one: `generic` (the default), a shop's -- `protolabs`, `hubs` (Protolabs
Network), `xometry`, `sendcutsend`, those the process has -- or `none`, facts alone. `generic` is
text-to-cad's own starting point: every rule in it still cites the published page its number comes from,
and every verdict says it is no shop's limit (`rules_generic`). A rule's id (`cnc.internal_corner_radius`)
is its finding's code; its severity is `error` where the source's number is a feasibility limit (the part
cannot be made as drawn under that rule) and `warning` where it is a recommendation, a cost or a risk.

## The result

A `cad.results.CheckResult`: `ok` (no error), `findings` (each a severity, a code, a message, a location and,
for a verdict, a `hint` saying what to change), `summary` and `measurements`, the report:

```
{"process": "cnc", "source": {"type": "step", "measured_as": "brep", "document": "plate"},
 "document": {...}, "bodies": [{"name", "owner", "bbox_mm", "volume_mm3", "face_count", ...}],
 "<family>": {"items": [{<fields>, "location": "plate/face 7", "xyz": [x, y, z], "faces": [...]}, ...],
              "count": 12, <scalars>},
 "partial": false, "partial_sections": [],
 "rules": {"set", "title", "version", "generic", "note", "context", "evaluated", "failed": [ids],
           "outcomes": [{"rule", "family", "field", "op", "limit", "unit", "severity", "source", "status",
                         "evaluated", "unmeasured", "failures": [{"value", "location", "xyz"}], "reason"}],
           "sources": [{"id", "publisher", "title", "url", "accessed"}]}}
```

- **Locations.** On exact geometry an item's `location` is a ref in `cad xbf inspect`'s grammar -- the
  part's canonical owner and the face's ordinal (`plate/face 7`, `kit/pin.2/face 3`) -- read with the
  engine's own loader, so `cad step inspect FILE REF` and `cad xbf inspect DOC REF` resolve it to the very
  face; a feature of several faces lists them in `faces`. On a mesh it is `x, y, z` in millimetres. Each
  part of an assembly is measured once, placed where its first occurrence stands.
- **A family that failed** is `{"error": "..."}`, named in `partial_sections`, and an error finding
  (`measurement_failed`); the other families are still reported.
- **Every rule has an outcome**: `passed`, `failed` (each failing item's value, place and the limit),
  `not_evaluated` (the set gives no limit for this material or technology, or nothing was measured to judge)
  or `not_applicable` (the rule is for another context: turning, a gauge, a technology). A figure that was
  not measured is never a pass. At most eight failures of one rule are findings; the rest are counted in one
  more, and `rules.outcomes` lists every one.
- **Items** are sorted worst first and capped (a few hundred), with the family's `count`. Every figure is
  finite: the result is JSON (`allow_nan=False`), and a report that is not is `not_finite`.
- The source unreadable is `document_unreadable` or `mesh_unreadable`, a missing file `invalid_target`.

The Python functions: `cad.<type>.dfm(path_or_id, process=..., ...)`; on a live shape
`cad.build123d.cnc(shape)`, `sheet_metal`, `molding`, `printing` (the same `CheckResult`, refs as the
engine would name its document) and `cad.build123d.unfold(shape, k_factor=)`; on a mesh a program holds
`cad.trimesh.molding(mesh)`, `pulls`, `printing`, `orientations` (the report as data).

## CNC machining

Exact geometry only (STEP, xbf, a document the engine holds, a live build123d shape); a mesh is refused.
Options: `--axes 3|4|5` (default 3), `--turning`, `--tools 3,6,10` (end mill diameters, mm), `--stock 100x60x25`
(mm; default the part's box), plus `--rules generic|hubs|protolabs|xometry|none`, `--material`.

Every family is `{"items": [...], "count": N, <scalars>}`, items sorted worst first and capped at 200; every
item has `location` (a face ref, `plate/face 7`) and `xyz`; several-face features list `faces`. Each part
of an assembly is measured on its own B-rep; its items carry its refs. A family that raised is
`{"error": "..."}` and is named in `partial_sections`. `machine` echoes axes, turning, tools, stock.

### Families (what each measures, and how)

- **holes** — a connected set of coaxial concave cylinders and cones (plus the planes square to the axis whose
  every neighbour is one of them: a counterbore step, a flat floor), with one cylinder sweeping >= 300
  degrees. `diameter_mm` (narrowest full cylinder), `depth_mm` (the cylinders' extent along the axis),
  `depth_to_diameter`, `through` / `bottom` (`through`, `drill_point`, `flat`, `closed`, `other`: an exact
  ray along the axis from inside the hole meets the hole's own floor or not), `point_angle_deg` (a drill
  point's included angle), `counterbores` [{diameter_mm, depth_mm}], `countersinks` [{diameter_mm,
  angle_deg}], `axis`, `aligned` (along a world axis), `opening`, `drilled` (<= 1 3/4 in), `standard_drill`
  (`"6.8 mm"`, `"1/4 in (6.350 mm)"`, `"#7 (5.105 mm)"`, `"letter F (6.528 mm)"`: within 0.005 mm),
  `drill_deviation_mm`, `tap_candidate` (`"M8x1.25"` where the diameter is an ISO 262 coarse tap drill: a
  fact, not a verdict); with `--turning`, `relation` (axial / radial / off_axis). Drill table: Wikipedia
  "Drill bit sizes" (ASME B94.11M): metric 0.2-25 mm in its steps, fractional 1/64 in to 1 3/4 in, #80-#1,
  A-Z.
- **threads** — modelled threads: non-analytic faces whose edge points sweep >= 350 degrees about a cylinder's
  axis in a radial band under a third of the radius, with their end caps. `internal`, `major_diameter_mm`,
  `minor_diameter_mm`, `pitch_mm` (axial advance per unwrapped turn of a flank edge), `length_mm`,
  `length_to_diameter`, `modelled` (1). Thread faces are excluded from access, walls, gaps and sharp edges.
- **pockets** — a planar face meeting, by a concave edge (or a concave root fillet), faces lying along its
  normal, and seen end-on (a ray along its normal from it escapes), is a floor; its walls grow along
  concave/tangent edges parallel to the normal. `kind` (`closed`; `slot`: open with opposite walls; `open`),
  `depth_mm` (floor to the walls' rim), `depth_from_top_mm` (floor to the part's top along the normal: tool
  reach), `width_mm` (narrowest exact ray between opposite walls of the pocket), `depth_to_width`,
  `open_boundary_fraction`, `floor_radius_mm` (root fillet), `axis`, `aligned`, `wall_count`. An open step
  that reads both ways (floor+wall or wall+floor seen from the side) keeps the shallower reading.
- **internal_corners** — a pocket's in-plane corners: concave cylinders along the pocket's axis (`radius_mm`)
  and sharp concave edges along it that no tool makes from another side (`radius_mm` 0, `sharp` true,
  `edge`). `height_mm` (the corner's own extent: the cavity depth there), `depth_mm` (from the part's top),
  `radius_to_depth`, `tool_mm` (largest `--tools` tool <= 2r, else 2r), `reach_ratio` (depth / tool_mm),
  `pocket` (its floor's ref). Floor-to-wall roots are never corners (a flat end mill makes them sharp).
- **sharp_edges** — every other sharp concave edge no rotating tool makes (each with `void_angle_deg`,
  `length_mm`, `edge`, `faces`, `makeable` 0). Made by: an end mill where one face is a floor square to an
  approach direction, the void angle >= 90 and a ray from that face along the direction escapes; a T-slot
  cutter where a face of the cavity the edge bounds is seen along that direction; a 45/60 degree dovetail
  cutter likewise; a 60/90/120 degree chamfer mill along the bisector; a drill or tap for a hole's own
  edges. `by_tool` counts every concave edge by the tool. Evaluated at each edge's midpoint.
- **walls** — under each sampled point of each face, an exact ray into the material to the first face across
  that faces back (normals within ~45 degrees of opposite); the thinnest per face under 5 mm:
  `thickness_mm`, `opposite`, `height_mm` (a plane's extent across its longest concave root edge),
  `height_to_thickness`, `surface`.
- **gaps** — the same ray outward across the void (holes and threads excluded); the narrowest per face under
  10 mm: `width_mm`, `opposite`, `surface`.
- **access** — faces (stock faces on the part's box excluded when no `--stock`) whose sampled points no
  straight line from the machine's directions reaches (exact rays must escape the part; back-facing points
  never count): `unreached_fraction`, `unreached_any_direction_fraction` (200 directions over the sphere),
  `kind` (`undercut`: five axes would reach it; `no_line_of_sight`: nothing straight would). Directions: 3
  axes the six world axes; 4 axes those plus every 15 degrees about the rotary axis (X, Y or Z, the one
  that reaches most); 5 axes those plus 200 over the sphere.
- **setups** — one item per part: the greedy set cover of the sampled area by direction (`directions`
  [{direction, area_fraction, faces}]), `orientation_count`, `setup_count` (clampings: each orientation on 3
  axes; directions square to the rotary axis are one on 4; directions within a half-space above one
  clamping face are one on 5), `unreached_area_fraction`, `rotary_axis`, `sampled_points`.
- **voids** — closed cavities (inner shells): `volume_mm3`, `face_count`.
- **stock** — per part: `size_mm`, `stock_mm`, `stock_given`, `fits_stock`, `length_mm` >= `width_mm` >=
  `height_mm`, `volume_mm3`, `stock_volume_mm3`, `removal_ratio`.
- **small_features** — faces narrower than 0.5 mm (2 x area / perimeter); scalars `smallest_edge_mm`,
  `smallest_face_mm2`, `fine_faces` (under 1 mm).
- With `--turning` (pockets and internal_corners are then absent): **turning** (per part: `axis` — the line
  whose coaxial cylinders, cones and tori have the most area —, `axis_origin`, `axisymmetric_fraction` (area on
  faces of revolution about it and planes square to it), `max_diameter_mm`, `length_mm`,
  `length_to_diameter`, `bar_removal_ratio`, `off_axis_faces`, `sharp_profile_corners`), **turned_diameters**
  (convex coaxial cylinders not groove floors: `diameter_mm`, `length_mm`), **bores** (on-axis holes),
  **grooves** (a coaxial cylinder with both ends meeting square planes by concave edges: `internal`,
  `width_mm`, `depth_mm`, `diameter_mm`), **live_tooling** (off-axis face groups: `cross_hole`, `flat`,
  `slot`, `feature`, with the hole's `relation`).

### Rule ids (finding code = rule id)

Severity e = error (not made as drawn under that source), w = warning. "tools" = the limit follows the
smallest `--tools` tool when given.

| id | family.field | generic / hubs | protolabs | xometry |
|---|---|---|---|---|
| cnc.internal_corner_sharp | internal_corners.radius_mm min 0.001 (e) | Hubs: a tool always leaves a radius | Protolabs milling | Xometry tips |
| cnc.internal_corner_radius | internal_corners.radius_mm | 0.025 mm (e, Hubs micro tools 0.05 mm); tools: 0.5 x min tool (e) | tools: 0.5 x min tool (e) | 1.625 mm (w, 130% of a 2.5 mm tool's radius); tools: 0.65 x min tool (w) |
| cnc.internal_corner_small | internal_corners.radius_mm min 1.25 (w) | Hubs 2.5 mm small features | - | - |
| cnc.corner_radius_to_depth | internal_corners.radius_to_depth min 0.3333 (w) | Hubs | - | - |
| cnc.corner_reach / _limit | internal_corners.reach_ratio max 4 (w) / 30 (e) | Hubs 3-4 D cutting length / 30:1 specialised | - | - |
| cnc.sharp_internal_edge | sharp_edges.makeable min 1 (e) | Hubs | Protolabs | Xometry |
| cnc.pocket_depth_to_width | pockets.depth_to_width max | 4 (w, Hubs) | - | 3 (w, lower end of 3-5) |
| cnc.milled_depth | pockets.depth_from_top_mm max | - | 50.8 (e) | - |
| cnc.wall_thickness | walls.thickness_mm min | metal 0.5 / plastic 1.0 (e, Hubs feasible) | 0.51 (w) | 0.5 (e, min feature) |
| cnc.wall_thickness_recommended | walls.thickness_mm min | metal 0.8 / plastic 1.5 (w) | - | metal 0.794 / plastic 1.5 (w) |
| cnc.hole_diameter / _limit | holes.diameter_mm min | 1.0 (w) / 0.05 (e) | - | - |
| cnc.hole_depth / _limit | holes.depth_to_diameter max | 4 (w) / 40 (e) | - | 4 (w) / 10 (e) |
| cnc.drill_size | holes.drill_deviation_mm max 0.005 (w), drilled holes | Hubs: standard drill sizes | - | - |
| cnc.thread_size | threads.major_diameter_mm min 6 (w) | Hubs | - | - |
| cnc.thread_length / _minimum | threads.length_to_diameter max 3 / min 1.5 (w) | Hubs | - | - |
| cnc.modelled_thread | threads.modelled max 0, internal (w) | - | Protolabs: don't model internal threads | - |
| cnc.gap_width | gaps.width_mm min | 0.05 (e); tools: min tool (e) | soft 0.457 / hard 0.838 (e, narrowest engraved line); tools: min tool | tools: min tool (e) |
| cnc.gap_width_small | gaps.width_mm min 2.5 (w) | Hubs | - | Xometry min tool 2.5 |
| cnc.undercut | access.unreached_fraction max 0.02, kind undercut (w) | Hubs (special cutters) | - | - |
| cnc.no_line_of_sight | access.unreached_any_direction_fraction max 0.02 (w) | Hubs | - | - |
| cnc.enclosed_void | voids.volume_mm3 max 0 (e) | Hubs | - | - |
| cnc.setups | setups.setup_count max 4 (w) | Hubs (3-4 acceptable) | - | - |
| cnc.part_thickness | stock.height_mm min 1.02 (e) | - | Protolabs | - |
| cnc.envelope_length/width/height | stock.*_mm max | 2032/1219/610 (w, Xometry's, generic only) | per material x axes (e): plastic/3 559x356x19.1, aluminum/3 559x356x95.3, aluminum/5 254x178x95.3, hard/5 254x178x44.45, ss304/5 107.95x82.55x95.25 | 2032/1219/610 (e) |
| cnc.turned_diameter / _length | turning.max_diameter_mm / length_mm max | 813 / 1575 (w, Xometry's, generic) | 100.33 / 228.6 (e) | 813 / 1575 (e) |
| cnc.turned_feature_diameter / _small | turned_diameters.diameter_mm min | - | 0.76 (e) / 4.07 (w) | - |
| cnc.turned_feature_length | turned_diameters.length_mm min | - | 1.27 (e) | - |
| cnc.turned_wall | walls.thickness_mm min (turning) | - | 0.51 (e) | - |
| cnc.axial_hole_diameter / radial_hole_diameter | holes.diameter_mm min | - | 1.0 / 2.0 (1.0 Al, brass) (e) | - |
| cnc.off_axis_hole | holes.diameter_mm max 0, off-axis, not Al/brass (e) | - | Protolabs | - |
| cnc.groove_width / groove_depth | grooves (OD) | - | width min 1.2 (0.5 Al, brass) / depth max 24.1 (e) | - |
| cnc.internal_groove | grooves (ID) width max 0 (e) | - | ID grooves not offered | - |

Fact findings (not rules): `cnc.stock_too_small` (e: the part does not fit `--stock`), `cnc.no_turning_axis`
(e, `--turning` on a part with no surface of revolution), `cnc.mostly_not_turned` (w, under half the area
turns), `cnc.live_tooling` (i), `cnc.rotary_axis` (i), `cnc.fine_detail` (i, >= 20 faces under 1 mm),
`cnc.material_assumed` (i: no `--material`, walls judged by metal's limits).

Context the rules read: `material_class`, `wall_class` (the class, else `metal`), `hardness` (soft: plastics,
aluminium, brass, copper; hard: steels, stainless, titanium), `envelope` (`<group>/<axes>`), `lathe_material`
(`al_brass` | `other`), `tools_given`, `min_tool_mm`, `axes`, `turning`.

Sources (accessed 2026-11-03): Hubs "How to design parts for CNC machining"; Protolabs "CNC milling design
guidelines" and "CNC turning design guidelines"; Xometry "10 tips to improve your CAD designs for CNC
machining" and "CNC machining service" capabilities (Xometry's own CNC design guide URL is still a 404).

### What it cannot measure

Tool holder and spindle collisions (access is a line of sight, a tool of zero diameter; width and corner
radius cover the diameter separately); a T-slot or dovetail cutter's actual entry path; fixturing and
workholding; tolerances, surface finish, cycle time or cost; thread callouts on a drawing (only modelled
threads and tap-drill diameters); hole axes other than a cylinder's (a slot milled as a hole); pockets whose
floor is not planar (a 3D-contoured cavity is reported through access and walls, not as a pocket); sharp
edges are judged at their midpoint; text and engraving are recognised only as many fine faces and as
narrow gaps; turning: ID groove depth beyond the bore, parting/chucking allowances, and cone point angle.

## Sheet metal

A STEP, an xbf or a live shape (`cad.build123d.sheet_metal(shape)`) is measured on its exact B-rep
(`cad.build123d._dfm_sheet`); a DXF cut file (`cad dxf dfm FILE --process sheet`) with ezdxf
(`cad.build123d._dfm_dxf`). A mesh is refused (a sheet's radii and thickness are not on a mesh). Options:
`--thickness` (the stock's, compared with the measured; a mismatch is `sheet.thickness_mismatch`),
`--k-factor` (default: SendCutSend's calculator K for its own gauges with `--rules sendcutsend`, else Hubs's
air-bending chart by material hardness and r/t), `--bend-radius` (the shop's; a bend modelled otherwise is
`sheet.bend_radius_differs`), `--kerf` (a hole, web or gap narrower is `sheet.under_kerf`), `--sheet-size`
(else the rule set's sheet).

### How it measures (3D)

- **Thickness.** Each face is sampled by area; an exact ray from each sample, square to the face, crosses
  the material to the next face. A planar face whose rays mostly reach an antiparallel planar face is a
  skin; the area-weighted modal distance is the thickness `t`. A coaxial concave/convex cylinder pair `t`
  apart is a bend; a face touching both faces of a pair is a cut edge; a cone between a skin and a coaxial
  hole wall is a countersink. Everything else, and any stretch of a skin whose rays cross another distance,
  is `not_sheet` at its ref.
- **Bends.** The skins and bend cylinders joined by tangent edges are the sheet's two sides; the side with
  the largest skin is unfolded, its coplanar skins the flanges. A bend's angle is its cylinder's angular
  span (checked against the flanges' normals), its length the extent along the axis, its tangent lines
  where the cylinders meet the flanges.
- **Unfold.** Breadth-first from the largest flange: each flange is moved flat (one rigid transform, exact:
  arcs and holes stay arcs and holes) about its bend and out by `BA = angle * (r + K t)`; each bend is its
  cylinder's outline unrolled into a strip `BA` wide (exact for straight ends, sampled where an end is
  curved). Fused, this is the flat pattern; `cad.build123d.unfold(shape, thickness=, k_factor=, material=,
  rules=, bend_lines=False)` returns it (`bend_lines=True`: a Compound of `CUT` and `BEND` children, one DXF
  layer each). Holes, notches, tabs, webs, gaps, flange lengths, reliefs and every distance are measured on
  the flat pattern in the plane (`cad._internal.meshops_sheet`, numpy), each place mapped back onto the
  part for its ref. At K = 0.5 the flat area equals volume / t exactly (`neutral_area_ratio`).

### Families (each `{"items": [...], "count": n}`, items sorted worst first, capped at 300)

| family | per item | notes |
|---|---|---|
| `parts` | `thickness_mm`, `is_sheet`, `why`, `sheet_area_fraction`, `bend_count`, `flat_length_mm`, `flat_width_mm` (smallest rectangle), `flat_area_mm2`, `flat_overlap_mm2`, `neutral_area_ratio`, `box_short_mm`, `unfold_note`, `flat_bend_lines` | one per part |
| `not_sheet` | `kind` (thicker, thinner, unpaired), `surface`, `local_thickness_mm`, `deviation_mm`, `area_mm2` | a boss, pocket, round, freeform face |
| `bends` | `kind` (bend, hem, curl), `inside_radius_mm`, `outside_radius_mm`, `radius_to_thickness`, `angle_deg` (bent from flat), `included_angle_deg`, `flanges_angle_deg`, `length_mm`, `axis`, `axis_origin`, `tangent_lines`, `k_factor`, `k_factor_source`, `bend_allowance_mm`, `bend_deduction_mm`; `faces` [inside, outside] | location: the inside cylinder |
| `flanges` | per bend side: `length_tangent_mm` (least along the bend), `length_tangent_half_mm` (reached by half the bend), `length_inside_mm`/`_half`, `length_outside_mm`/`_half` (mold lines: + r·tan(θ/2), + (r+t)·tan(θ/2)), `length_outside_minus_radius_mm` | the length runs to the free edge or the next bend's tangent line |
| `channels` | `base_length_mm`, `flange_length_mm` (outside), `base_to_flange_ratio` | a flange between two parallel bends turning the same way |
| `reliefs` | per bend end and side where the flange runs on past the bend's end: `kind` (bend, corner), `needed`, `present`, `width_mm`, `depth_tangent_mm`, `depth_centerline_mm`, `depth_centerline_minus_radius_mm` | a missing relief has width 0 |
| `hems` | `inside_diameter_mm`, `gap_mm`, `return_length_mm` | bends of 175 to 185 degrees |
| `curls` | `inside_radius_mm`, `outside_radius_mm`, `angle_deg` | over 185 degrees |
| `holes` | `kind` (round, slot, cutout), `size_mm` (diameter, or least width), `length_mm`, `edge_distance_mm` (edge to edge), `in_bend`, `countersunk`, `countersink_diameter_mm`; `faces` | location: the hole's wall |
| `hole_spacing` | `distance_mm` edge to edge, `other` | each hole and its nearest |
| `hole_to_bend` | `distance_tangent_mm`, `distance_centerline_mm` (+ BA/2), `distance_inside_mm`, `distance_outside_mm`, `distance_outside_minus_radius_mm`, `bend` | the nearest bend |
| `notches` | `width_mm` (mouth), `length_mm` (depth), `length_to_width` | pockets of the outline off its hull |
| `tabs` | `width_mm`, `length_mm`, `length_to_width` | facing straight sides, a tip, an inside corner at the base |
| `webs` | `width_mm` | the narrowest material within an outline (a neck, a bridge) |
| `gaps` | `width_mm`, `between` | the narrowest void (slots, holes, gaps between parts) |

DXF adds `cut_file` (`insunits`, `unit`, `mm_per_unit`, `extents_mm`, `layers` with intents, `cut_layers`,
`cut_layer_count`, `contour_count`, `is_drawing`), `scale` (`units_unknown`: every length rule withheld), and
defect families, each item `location` = `layer L, TYPE #handle`, `xyz` in mm: `open_geometry` (dangling ends
and branch points), `overlaps` (collinear lines or concentric equal arcs overlapping over a length, any
entity types), `self_intersections`, `contour_crossings`, `zero_area_loops`, `annotations` (text,
dimensions, hatches, inserts, points on cut layers), `floating_interiors` (an island inside a hole),
`short_line_runs` (8+ short lines turning a little each way, a curve as chords). The drawing checks every
export runs (`validate_drawing_document`: `units_not_set`, `duplicate_entity`, `zero_length_entity`,
`empty_drawing`, `drawing_document`) are kept as findings. A `BEND` layer's lines give `hole_to_bend`'s
`distance_centerline_mm`.

### Findings of fact (`cad._internal.dfm.sheet.findings`)

`sheet.not_sheet` (error: no constant-thickness sheet, a freeform shell, or a thickness over a quarter of
the part's width), `sheet.thickness_mismatch` (error), `sheet.flat_overlap` (error), `sheet.not_unfolded`
(warning: a loop of bends, a flange no bend reaches), `sheet.bend_radius_differs` (warning: vs
`--bend-radius`, or SendCutSend's radius for the gauge), `sheet.bend_radii_mixed` (info), `sheet.under_kerf`
(error), `sheet.hole_in_bend` (warning), `sheet.k_factor_assumed` (info); DXF: `sheet.open_contour`,
`sheet.overlapping_curves`, `sheet.self_intersecting`, `sheet.crossing_contours`, `sheet.zero_area_loop`
(errors), `sheet.annotation_on_cut_layer`, `sheet.floating_interior`, `sheet.short_line_run` (warnings),
`sheet.units` (SendCutSend: inches or mm only).

### Rules (id: family.field op limit, severity; source)

Every length rule is withheld where the units are unknown. `t` = thickness (`scale_by`).

**generic** (Hubs's numbers unless noted, each citing its page):
`sheet.uniform_thickness` not_sheet.deviation_mm max 0 (Protolabs guidelines: uniform throughout);
`sheet.thickness_max` parts.thickness_mm max 6 bent / 10 flat (Hubs: bending 0.5-6, laser 0.5-10);
`sheet.thickness_min` min 0.5; `sheet.bend_radius` bends.inside_radius_mm min 1 t (warning);
`sheet.flange_length` flanges.length_outside_minus_radius_mm min 2 t (Hubs min bend height 2t + r; read from
the outside mold line, the page does not say); `sheet.bend_relief_width` reliefs.width_mm min 1 t (bend
reliefs, not corner); `sheet.hole_to_bend` hole_to_bend.distance_tangent_mm min 2 t ("from the start of the
bend radius"); `sheet.hole_diameter` holes.size_mm min 1 t (warning); `sheet.hole_to_edge` min 1 t;
`sheet.hole_spacing` min 2 t; `sheet.web_width` webs.width_mm min 1 t (warning; Hubs's hole-to-edge applied
to any web); `sheet.notch_width` min max(t, 1.016), `sheet.notch_length` length_to_width max 5,
`sheet.tab_width` min max(2t, 3.2), `sheet.tab_length` max 5, `sheet.hem_diameter` min 1 t,
`sheet.hem_return` min 6 t (warning) (Protolabs guidelines); `sheet.flat_length`/`sheet.flat_width` max the
sheet (Xometry's largest blank 3050 x 1520 unless `--sheet-size`).

**hubs**: uniform thickness, the Hubs rules above, flat size against Xometry's blank.

**protolabs**: uniform; thickness 0.609-6.35; `sheet.bend_radius` 0.254 min / `sheet.bend_radius_max` 25.4
(warning) (toolkit tooling radii); `sheet.flange_length` length_outside_minus_radius_mm min (toolkit
multiplier by material group and thickness band) x t, or with no toolkit row length_outside_mm min 4 t
(guidelines); `sheet.hole_to_bend` distance_outside_minus_radius_mm min the toolkit multiplier x t (toolkit:
"same multipliers"; reference unstated, read from the outside mold line), or distance_tangent_mm min 4 t
(warning; guidelines "within 4x"); hole diameter min 1 t; `sheet.hole_to_edge` min 1.574 mm (t <= 0.914) or
3.175 mm; notch, tab, hem rules; `sheet.countersink_diameter` 2.286-12.7; flat size max 1193.8 x 990.6;
`sheet.flat_min` 6.35 flat, `sheet.formed_min` box_short_mm 12.7 formed; `sheet.bend_length` max 1193.8.

**sendcutsend** (give `--material`; a thickness is a calculator gauge within 0.005 in, so 2 mm is 0.074 in
steel and 3 mm is no 5052 gauge): uniform; `sheet.hole_diameter` min 0.5 t (cutting guide), 1 t for 5052
(material page); `sheet.hole_to_edge` 2 t and `sheet.bend_radius` 1 t (warning), both by material, 5052
alone (other materials `not_evaluated`); `sheet.bend_radius_shop` the part's inside radius within the larger
of 5% and 0.001 in of the calculator's effective radius for the gauge (no custom radii); `sheet.bend_angle`
max 130, `sheet.bend_angle_min` min 5 (bending page; no hems); `sheet.flange_length` length_outside_half_mm
min the calculator's minimum formed flange for the gauge (from the bend's apex, over half the bend);
`sheet.hole_to_bend` distance_centerline_mm min half the gauge's die width (deformation guide: from the bend
line, where the die centres). For a thickness that is no gauge, the gauge rules are `not_evaluated` (the
error `sheet.gauge_unmatched` names the nearest gauge; with no `--material`, a warning) and the gauge-free
minimums judge instead: a flange of at least 0.286 in (the calculator's least) and a feature at least
0.236 in from the bend line (half the narrowest die, 0.472 in). `sheet.bend_relief_depth`
depth_centerline_minus_radius_mm min 0.508 to 0.187 in (thicker: `not_evaluated`); `sheet.channel_base`
min 2; `sheet.bend_length` max 1117.6; flat size: bending 1117.6 x 762 (min 38.1 x 9.525), laser 1727.2 x
1117.6 (min 9.525 x 6.35); `sheet.cut_layers` max 1 (warning). generic also takes `sheet.channel_base`
(warning, SendCutSend's 2:1).

**What each set does not judge** is its `note` (`cad._internal.dfm.sheet.NOT_JUDGED`, a test holds it
complete): generic and hubs leave the shop-tooling rules (largest radius, a shop's radius, countersinks,
smallest parts, bend length and angle, relief depth, cut layers) to the shops' sets; hubs has no notch,
tab, hem or channel numbers; protolabs no relief, hole-to-hole, web, angle, channel or layer rule;
sendcutsend no relief width, hole-to-hole, web, notch, tab or countersink number, no hems (its 130 degree
limit refuses them) and judges thickness by its gauges.

Sources, accessed 2026-11-03: hubs.com/guides/sheet-metal-fabrication; protolabs.com sheet metal design
guidelines and its sheet metal toolkit; xometry.com/capabilities/sheet-metal-fabrication; sendcutsend.com
guidelines/sheet-cutting, services/cnc-bending, guidelines/bend-deformation, bending-calculator,
materials/5052-aluminum, materials/min-max.

### What it does not measure

Bend order, tooling access and collisions while bending; grain direction; hardware (PEMs) and their
distances; window bends; box flange maxima (SendCutSend's 3/5 in); bump-formed or conical bends (a cone
between flanges is not a bend: not sheet); freeform formed shells (reported not sheet); closed hems
(modelled as a double thickness: not sheet); a hole crossing a bend is unrolled from samples; a non-straight
bend end is unrolled from samples; notches are hull pockets (a pocket's mouth, not its narrowest width);
tabs need two parallel straight sides. Corner reliefs are reported, not judged (no published number
verified). The Protolabs and Hubs flange and feature-to-bend conventions are not stated by the sources and
are read from the outside mold line (stated in each rule's note).

## Injection molding

`cad <type> dfm SRC --process molding [--pull z|-y|x,y,z] [--wall-limit 45] [--zero-tol 0.05]
[--cavities N] [--material abs|pc|...] [--rules generic|protolabs|hubs|xometry|none] [--candidates]`

A STEP, an xbf or a model's document is measured on its B-rep (`cad.build123d._dfm_molding`); every item
is at a face ref (`plate/face 7`) plus `xyz`. An STL, 3MF or GLB is measured as triangles
(`cad.trimesh._molding`), every item at `xyz`. Both share one schema and one algorithm for everything but
draft and feature recognition (`cad._internal.meshops_molding`, numpy only). A mesh report also carries
`notes`: what a mesh cannot say.

### Families (`measurements.<family>`)

| family | what | how | items (fields the rules read in **bold**) |
|---|---|---|---|
| `draft` | each wall face's draft along the pull and the way it opens | B-rep: plane exact, cylinder/cone with axis along the pull exact (0 / half-angle), other faces the least over points sampled ON the surface; mesh: per region (triangles joined under 20 deg), flat exact, curved 5th percentile of its facets (`spread_deg`), tangent bands excluded | `location`, **`draft_deg`**, `area_mm2`, **`opens`** (`+pull`, `-pull`, `none` = zero draft, `split` = the parting line crosses it), `surface`, `exact`, `depth_mm`, `xyz` |
| `undercuts` | trapped features and what releases them | points on every face shot along the way their face opens (zero-draft: both ways); blocked = trapped; touching trapped faces = one feature. Release: rays along 8 slide directions in the parting plane + the feature's mean lateral normal + each tilted 45 deg (angled slide); fewest slides covering it (each point assigned to its shortest stroke); else a lifter (short lateral move then a pull, stroke <= 1/4 part size); else a collapsible core (each point freed radially, no common direction); else `none` | `location` (the mostly-trapped face), `faces`, **`trapped_area_mm2`**, `kind` (external/internal), **`release`** (side_action/lifter/collapsible_core/none), `side_actions` (`+x`, ...), `side_action_count`, `angled`, **`stroke_mm`**, **`height_mm`** (along pull), **`width_mm`**, `blocked_by`; scalars: `candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `collapsible_core_count`, `unreleasable_count`, ... |
| `thickness` | the wall: nominal, thin, thick, transitions | rolling ball: at each sampled point the diameter of the largest ball tangent there that no surface triangle cuts into (exact per triangle: corners, edges, insides), capped by the exact ray straight through. Points whose ball is held by a face across a convex edge read low and are left out of medians; a narrow face (rib top, plate end) takes its broad neighbours' wall | `location`, **`thickness_mm`** (area median), `min_mm` (p10), **`max_mm`**, **`ratio_to_nominal`** (max / nominal), `thin_ratio`, **`transition_ratio`** (distance per unit of thickness change, steepest pair on the face), `xyz`; scalars `nominal_mm` (area median of the faces' walls), `min_mm`, `max_mm`, `ratio_max_nominal`, `thick_sections` (> 1.5 x nominal) |
| `ribs` | thin slabs standing on a wall | two opposite planar faces (within 12 deg) whose inward rays come out of each other, both meeting one base plane at a concave edge or a concave fillet, height >= thickness, length >= 1.5 x thickness; base = the plane it is shortest from | **`thickness_ratio`** (root / base wall), **`height_ratio`** (height / wall), **`height_to_thickness`**, **`base_fillet_ratio`** (fillet / rib), **`base_fillet_wall_ratio`**, **`gap_to_thickness`**, **`gap_to_wall`** (gap = median ray to the next face), **`draft_deg`**, `thickness_mm`, `height_mm`, `length_mm`, `base_fillet_mm` |
| `bosses` | cylindrical stands, cored or solid | a convex cylinder standing on a plane square to its axis (concave edge or fillet), with the largest coaxial concave cylinder inside it reaching half its height | `od_mm`, `id_mm`, `boss_wall_mm` (R - r, or 2R solid), **`wall_ratio`** (boss wall / base wall), `od_to_id`, `height_mm`, `height_to_od`, `base_fillet_mm`, `hole_floor_above_base_mm` |
| `corners` | internal corners | every concave edge with no fillet (radius 0, `edge` ref) and every concave cylinder/torus fillet (two tangent joins), rib and boss roots excluded | `radius_mm`, `sharp`, **`ratio_to_wall`** (radius / thinner wall meeting there), `wall_mm`, `edge`, `angle_deg` |
| `projection` | area along the pull | the part triangulated (each triangle naming its face), projected, cells covered on a raster 2000 across the part | per part: **`projected_area_mm2`**, `area_error_mm2` (half the outline's cells), `raster_resolution_mm`, `depth_along_pull_mm`, `span_major_mm`, `span_minor_mm`, `volume_mm3` |
| `envelope` | size against a mold | from the projection and the parting | per part: **`span_major_mm`**, **`span_minor_mm`**, **`depth_along_pull_mm`**, **`depth_from_parting_mm`**, `volume_mm3` |
| `parting` | flat parting plane? | outline pieces within 3 cells of the projected outline: edges where a +pull face meets a -pull face, zero-draft walls (the line may run anywhere up them), curved faces turning through the pull (sphere centre, horizontal cylinder axis, ...); undercut faces left out (a slide forms them). Flat when every edge/turn is level at one height every wall spans | scalars `flat_parting_possible`, `parting_plane_height_mm`, `parting_plane_range_mm`, `depth_above_mm`, `depth_below_mm`, `depth_from_parting_mm`, `off_plane_count`; items: `kind`, `low_mm`, `high_mm`, `on_plane` |
| `clamp` | clamp force estimate (added by the type side) | area (in2) x factor (tons/in2, Moldminds by resin; unknown: 2-5, estimated at 3) x cavities x 1.15 | per part `tons`, `tons_low`, `tons_high`, `kN`, `tonnes`; `factor_source` |
| `pulls` (`--candidates`) | x, y, z and the principal axes ranked | the families above per axis (fewer samples) | `undercut_candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `unreleasable_count`, `zero_draft_wall_area_mm2`, `min_wall_draft_deg`, `flat_parting`, `projected_area_mm2`, `depth_from_parting_mm` |

Kept from today's report: `draft` scalars (`wall_area_mm2`, `zero_draft_wall_area_mm2`, `largest_zero_draft_faces`,
`min_wall_draft`, `wall_draft_histogram_mm2`, `wall_area_by_opening_mm2`, ...), `undercuts` scalars
(`candidate_area_mm2`, `largest_candidate_faces`, `probe_resolution_note` on a mesh), `projection`, `scale`,
`mesh` (meshes). Fact findings: `zero_draft_walls`, `undercut_candidates` (now with feature counts),
`coarse_curved_face`, `probe_resolution`, `several_bodies` (also for a multi-part document),
`stepped_parting` (new, warning), `resin_unknown` (info), `clamp_estimate` (info), `thickness_unmeasured`.

### Rule sets (each rule's id is the finding's code)

Sources: Hubs `https://www.hubs.com/guides/injection-molding/`; Protolabs design guidelines
`https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/`;
Protolabs uniform-wall tip `https://www.protolabs.com/resources/design-tips/improving-part-design-with-uniform-wall-thickness/`;
Xometry service page `https://www.xometry.com/capabilities/injection-molding-service/`; Xometry ribs
`https://www.xometry.com/resources/injection-molding/plastic-ribs-for-injection-molding-design/`;
Moldminds clamp calculator `https://moldminds.com/clamp-force-calculator/` (all accessed 2026-11-03).

| rule id | field | generic | protolabs | hubs | xometry |
|---|---|---|---|---|---|
| `molding.draft_min` | draft_deg min | 0.5 error (Protolabs) | 0.5 error | - | 0.5 error |
| `molding.draft` | draft_deg min | 2 warning (Hubs) | 2 warning | 2 warning | - |
| `molding.undercut` | trapped area, release side_action/lifter/core | warning (Hubs) | warning | warning | warning |
| `molding.undercut_unreleasable` | trapped area, release none | error | error | error | error |
| `molding.wall_min` / `wall_max` | thickness_mm / max_mm by `--material` | Protolabs resin table, warning | same | - | - |
| `molding.thick_section` | ratio_to_nominal max 1/0.6 | warning (Protolabs 40-60%) | same | - | - |
| `molding.wall_transition` | transition_ratio min 3 | warning (Hubs) | - | warning | - |
| `molding.rib_thickness` | thickness_ratio max | 0.6 (Xometry) | - | 0.5 | 0.6 |
| `molding.rib_height` | height_ratio max 3 (Hubs "3x wall") / height_to_thickness max 3 (Xometry) | height_ratio 3 | - | height_ratio 3 | height_to_thickness 3 |
| `molding.rib_base_fillet` | base_fillet_ratio min 0.25 (Hubs) / base_fillet_wall_ratio min 0.5 (Xometry) | Hubs | - | Hubs | Xometry |
| `molding.rib_gap` | gap_to_wall min 2.5 (Xometry) / gap_to_thickness min 4 (Hubs) | Xometry | - | Hubs | Xometry |
| `molding.rib_draft` | draft_deg min 0.5 | warning (Xometry) | - | - | warning |
| `molding.boss_wall` | wall_ratio max 0.6 | warning (Protolabs) | same | - | - |
| `molding.inside_corner_radius` | ratio_to_wall min 0.5 | warning (Hubs) | - | warning | - |
| `molding.side_action_stroke` / `_height` / `_width` | stroke 73.66, height 60.38, width 213.84 mm max | - | errors | - | - |
| `molding.projected_area` | projected_area_mm2 max 112903 (175 in2) | - | error | - | - |
| `molding.part_length` / `part_width` / `part_depth` | 751.84 / 480.06 / 203.2 mm | - | errors | - | - |
| `molding.depth_from_parting` | depth_from_parting_mm max 101.6 (4 in) | - | error | - | - |

Protolabs wall table (in, converted to mm): ABS 0.045-0.140, acetal 0.030-0.120, acrylic 0.025-0.500,
LCP 0.030-0.120, nylon 0.030-0.115, PC 0.040-0.150, polyester (PBT, PETG) 0.025-0.125, PE 0.030-0.200,
PP 0.035-0.150, PS 0.035-0.150 PPS 0.020-0.180, polyurethane 0.080-0.750, long-fiber reinforced 0.075-1.000 (HDPE and LDPE read polyethylene's row).

### What it cannot measure

- Exact draft of a mesh's curved face (chords read low by up to `spread_deg`); fillet radii on a mesh
  (filleted corners and rib roots merge into one region: corners lists sharp ones, ribs only sharp-rooted
  ones); bosses on a mesh only with their axis along the pull.
- Texture draft (no texture option), tall-feature extra draft (Hubs +1 deg / 25 mm over 50 mm), shut-off
  draft (3 deg), stripping undercuts (lead angle, 5% of diameter), snap-fit and living-hinge proportions,
  threads, boss OD against a screw (no screw size), gating, weld lines, filling, cooling, warpage, shrinkage.
- The undercut test samples points (2400 per part, at least 12 a face): a feature smaller than the point
  spacing can be missed; the lifter stroke is capped at a quarter of the part; an undercut freed only by a
  slide in a direction other than the 25 tried reads `none`.
- A side action's travel is to where the pull clears, not including the slide's own clearance.
- Clamp force is the part's projected area alone (no runner), a molder's factor table, not a resin's cavity
  pressure.

## 3D printing

### The check

`cad <type> dfm --process printing` (`cad.step.dfm(..., process="printing")`,
`cad.build123d.printing(shape, ...)`) measures a part as it stands on the plate (its lowest point, Z up) for one
technology: `--technology fdm|sls|sla|mjf|pbf` (default `fdm`; `pbf` is metal powder bed fusion, DMLS/SLM).
Options: `--build-volume XxYxZ` (mm; default the rule set's machine for the technology), `--angle-limit` (deg from
horizontal; default the technology's: FDM 45, SLA 19, metal 45, SLS/MJF 0), `--layer-height` (mm; default FDM 0.2,
SLA 0.1, SLS 0.1, MJF 0.08, metal 0.03), `--nozzle` (FDM's only), `--samples` (rays, default 2000), `--material`,
`--rules generic|hubs|protolabs|xometry|none`, `--candidates`.

A STEP, an xbf or a document id is measured on its exact geometry (B-rep), every item at a face ref
(`bracket/face 7`, resolved by `cad xbf inspect`); an STL, a 3MF or a GLB as triangles, every item at `x, y, z`.
The powder processes (SLS, MJF) need no support: their overhangs are facts, never verdicts, and trapped powder is.

### Families (`measurements.<family>`)

Every family with features is `{"items": [{..., "location": ref, "xyz": [x, y, z]}], "count": n, <scalars>}`,
items worst first, at most 300. A family that fails is `{"error": "..."}` and is named in `partial_sections`.

| family | exact geometry (B-rep) | mesh |
| --- | --- | --- |
| `solid` / `mesh` | per part: `solids`, `shells`, `closed`, `inner_shells`, `sound` (the kernel's boolean-argument check, `issues` its BRepCheck codes), `volume_mm3`; scalars `body_count`, `volume_mm3`, `watertight`, `sound` | `mesh`: `watertight`, `body_count`, `volume_mm3`, ... (unchanged) |
| `overhangs` | per down-facing face off the plate: `angle_deg` (a plane's exactly, a curved face's least over its samples), `area_mm2`, `area_below_limit_mm2`, `height_mm`, `kind`: `slope`, `bridge`/`cantilever`/`ceiling` (a flat face, see `bridges`), `hole` (a hole's arch), `plate_edge` (a round or chamfer on the plate's edge whose under-limit part is within 1 mm / 5 layers of it); scalars as before (`down_facing_area_below_limit_mm2` excludes holes, bridges, plate edges) | connected regions of the counted triangles, same fields |
| `bridges` | flat (< 5 deg) down-facing planes: `kind` `bridge` (the farthest point lies within the convex hull of its supports: `length_mm` = twice the farthest distance to a supporting edge = the span between the walls), `cantilever` (beyond one support: `length_mm` = its reach), `ceiling` (none); supporting edges are the concave edges whose other face descends; plus, for FDM and SLA, each horizontal non-teardrop hole's arch (`arch: true`, `length_mm` = d sin(angle limit)) | the flat regions and any region carried on both sides |
| `wall_thickness` | per face, the thinnest exact ray into the material from its samples (a ray landing on a face that meets its own at a sharp convex edge measures the edge and is dropped; pins are the pins' rules'), `thickness_mm`, `opposite`, `supported` (joined to the part on 2+ sides: the face's or its opposite's concave edges, smooth joins into a concave round, or a closed ring), `joined_sides`; scalars `min_mm`, `p05_mm`, `p25_mm`, `median_mm`, `max_mm` | the existing per-body ray field, plus one ray from every triangle (to 20 000) for the items: the thinnest per cube of diag/40 (>= 2 mm), `supported: null`; a ray must land on a face looking away from the start (within 60 deg) |
| `gaps` | per face, the narrowest exact ray out of the material to another face of the same part (not a neighbour, not the same hole), up to 3 mm, each pair once | one ray out of every triangle to a facing wall of the same body (a hole reads as a gap) |
| `holes` | concave cylinders round one axis covering >= 250 deg: `diameter_mm`, `depth_mm`, `orientation` (vertical < 10 deg, horizontal > 80 deg, else inclined), `through`, `teardrop` (horizontal and no material within 15 deg of the top), `channel` (depth >= 5 d), `coverage_deg` | not measured (no axes) |
| `pins` | convex cylinders the same way: `diameter_mm`, `height_mm`, `aspect_ratio` | not measured |
| `details` | a planar side face between a parallel top (its convex edge) and bottom (its concave edge) at most 2 mm apart: `emboss` (the top smaller) or `engrave`; `height_mm` (the step), `width_mm` (the raised stroke's thickness, or the groove's gap) | not measured |
| `clearances` | each pair of parts within 5 mm: exact `distance_mm` (BRepExtrema), `kind` `gap`/`contact`/`overlap` (`overlap_mm3` by boolean), `parts` | each pair of bodies (inside-out void shells and slivers dropped): closest points of vertices and triangle centres |
| `trapped_volumes` | cavities: every solid's inner shells exactly (`exact: true`, volume from the shell), and from a voxel field (<= 1.5 M voxels) the air a ball of r = clamp(0.2 x smallest side, 3 voxels, 6 mm) cannot reach from outside (open hollows) and sealed pockets; `sealed`, `escape_holes` (the exact holes with one end in the cavity and the other outside, plus voxel openings no hole explains), `escape_hole_diameters_mm`, `min_escape_hole_mm`, `min_wall_mm` (the wall samples whose outside lies in the cavity), `volume_mm3` | the voxel field alone; opening widths estimated ((2 depth + 3) voxels) |
| `build_volume` | the document's box in the volume in the best of the six axis orientations: `fill_ratio` (largest side over the volume's: <= 1 fits), `fits`, `best_axes`, `as_placed_fill_ratio`, `max_dimension_mm`, `volume_mm`, `volume_origin` | same |
| `bed` | planar faces facing -Z on the plate: `contact_area_mm2`, `contact_length_mm`, `footprint_mm`, `contact_ratio`, `sharp_bottom_edges_mm`, `holes_on_plate` | contact triangles; `holes_on_plate: null` |
| `stair_stepping` | per face, the area between 0.5 and 20 deg from horizontal: `angle_deg`, `cusp_mm` (layer cos angle), `step_width_mm` (layer / tan angle), `facing`; `area_by_angle_mm2` | regions of such triangles |
| `support_volume` | column fill under every down-facing surface under the angle limit, down to the part or the plate, from a raster (<= 90 000 columns) of the triangulation along Z: `estimated_support_volume_mm3`, `support_contact_mm2`, `support_contact_cosmetic_mm2` (faces of 5% of the part's area or more, holes aside), items per face touched | same raster |
| `sections` | the largest ball each part's material holds (voxels, up to 12 mm: `at_least`), `max_cross_section_mm2`, `max_cross_section_z_mm`, `largest_section_change_mm2` | same |
| `scale` | `bbox_diagonal_mm`, `units_suspect` | unchanged |
| `orientations` (`--candidates`) | the six axis orientations plus up to four of the largest flat faces laid down: `support_volume_mm3`, `support_contact_mm2`, `support_contact_cosmetic_mm2`, `build_height_mm`, `bed_contact_mm2`, `overhang_area_mm2`, `stair_step_area_mm2`, `fill_ratio`, `fits`, `score`, `rank`; `weights` | the six axis orientations |

**Ranking** (`orientations.weights`): each figure over the largest any candidate has, weighted, summed, lowest
first. Support processes (FDM, SLA, metal): support volume 0.30, support contact 0.15, contact on cosmetic faces 0.10,
build height 0.15, overhang area 0.10, stair-step area 0.10, lack of bed contact 0.10. Powder (SLS, MJF): build height
0.50, stair-step area 0.30, overhang area 0.20.

### Findings that are facts

`not_watertight`, `not_sound`, `several_bodies`, `overhangs` (info for powder), `plate_edge_round` (info: chamfer
edges on the plate), `walls_not_measured`, `internal_void` (FDM: a sealed void prints as infill), `no_bed_contact`,
`warping_risk` (FDM in abs, nylon, nylon_gf, pc, pc_abs, pp, peek, pei, pom, pbt with a flat bottom on the plate),
`elephant_foot` (FDM: holes open on the plate).

### Rules (`--rules`; every limit keyed by `technology`)

`generic` takes, per technology, Hubs's figure where Hubs gives one, else Protolabs's, else Xometry's (and applies
Hubs's SLS escape-hole figure to the other powder beds, saying so); its build volume is Hubs's typical machine.
A technology a set has no figure for is `not_evaluated` ("the rule set gives no limit here"), never a pass.
Sources (accessed 2026-11-03): hubs-thin-walls, hubs-geometry, hubs-fdm, hubs-sla, hubs-sls, hubs-mjf, hubs-metal,
protolabs-toolkit, protolabs-metal, protolabs-7mistakes, xometry-fdm, xometry-sla (Xometry Pro SLA quick reference),
xometry-3dp, xometry-guide (Xometry Pro design guide) -- URLs in `cad._internal.dfm.printing.SOURCES`.

| rule id | family.field | op | generic (fdm / sla / sls / mjf / pbf) | severity | hubs | protolabs | xometry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| printing.wall_supported | wall_thickness.thickness_mm (supported) | min | 0.8 / 0.5 / 0.8 / 0.7 / 0.4 (hubs-thin-walls) | error | same | - / 0.305 / 0.762 / 0.508 / 0.381 | 1.2 / 0.4 / 0.508 / 0.508 / 0.508 |
| printing.wall_unsupported | wall_thickness.thickness_mm (not) | min | 0.8 / 1.0 / 1.0 / 1.0 / 0.8 (hubs-thin-walls) | error | same | as supported | 1.2 / 0.6 / 0.508 x3 |
| printing.wall | wall_thickness (mesh, supported unknown) | min | as supported | error | | | |
| printing.hole_diameter | holes.diameter_mm | min | 1.0 (xometry-fdm) / 0.8 (hubs-sla text) / 1.5 (hubs-sls) / - / 1.5 (hubs-metal) | error | - / 0.8 / 1.5 / - / 1.5 | - / 0.508 / - / - / 0.635 | 1.0 / 0.75 |
| printing.pin_diameter | pins.diameter_mm | min | 5 (hubs-fdm, warning) / 0.5 (xometry-sla) / 0.8 (hubs-sls) / 0.5 (hubs-mjf, warning) / 0.6 (hubs-metal) | error* | | | sla 0.5 |
| printing.pin_aspect | pins.aspect_ratio | max | pbf 8 (hubs-metal) | warning | same | | |
| printing.overhang_angle | overhangs.angle_deg (slope, ceiling, cantilever; metal also bridge) | min | fdm 45 (hubs-fdm), sla 19 (hubs-sla), pbf 45 (protolabs-metal) | warning | fdm 45, sla 19 | pbf 45 | |
| printing.bridge_length | bridges.length_mm (bridge) | max | fdm 5 (hubs-fdm), sla 21 (hubs-sla) | warning | same | | sla 20 |
| printing.cantilever_length | bridges.length_mm (cantilever) | max | sla 1.0 (hubs-sla), pbf 0.5 (hubs-metal) | warning | same | pbf 0.5 | sla 1.0 |
| printing.horizontal_hole_diameter | holes.diameter_mm (horizontal, no teardrop) | max | pbf 8 (protolabs-metal) | warning | | pbf 8 | |
| printing.clearance | clearances.distance_mm | min | fdm 0.762 (xometry-3dp), sla 0.5, sls 0.3, mjf 0.9 (hubs), pbf 0.635 (protolabs) | warning | sla/sls/mjf | pbf | 0.762 x4, sla 0.5 |
| printing.gap | gaps.gap_mm | min | fdm 0.762 (xometry-3dp), sla 0.635, sls 0.762, mjf 0.508, pbf 0.635 (protolabs-toolkit) | error | | same | sla 0.5, others 0.762 |
| printing.escape_holes | trapped_volumes.escape_holes | min | 1: sla (hubs-sla); sls, mjf, pbf (hubs-sls, applied) | error | sla | | |
| printing.escape_hole_diameter | trapped_volumes.min_escape_hole_mm | min | 3.5: sla (hubs-sla), sls (hubs-sls), mjf, pbf (hubs-sls, applied) | warning | sla, sls | | |
| printing.hollow_wall | trapped_volumes.min_wall_mm | min | sla 2.0 (hubs-sla) | warning | same | | |
| printing.build_volume | build_volume.fill_ratio | max | 1.0 against the set's machine | error | 900x600x900, 1500x750x500, 750x550x550, 380x285x380, 500x280x360 | -, 736x635x533, 482.6x482.6x431.8, 281x378x378, 245x245x330 | 914.4x609.6x914.4, 736x635x533, 700x380x580, 380x284x380 |
| printing.emboss_height | details.height_mm (emboss) | min | fdm 1.0 (xometry-fdm), sla 0.1, sls 1.0, mjf 0.3048 (protolabs), pbf 0.4 (hubs-metal detail) | warning | | 0.3048 (not fdm) | fdm 1.0, sla 0.3 |
| printing.engrave_depth | details.height_mm (engrave) | min | sla 0.4, sls 1.0 (hubs) | warning | same | | sla 0.5 |
| printing.engrave_width | details.width_mm (engrave) | min | sla 0.4 (hubs-sla), pbf 0.4 (hubs-metal) | warning | same | | |
| printing.warp_length | build_volume.max_dimension_mm | max | sls, mjf 177.8 (protolabs-7mistakes) | warning | | same | |
| printing.section_thickness | sections.thickness_mm | max | pbf 10 (hubs-metal) | warning | same | | |

\* severity per row: FDM pins and MJF pins are warnings ("recommended"), the rest errors.

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
  largest cross-section and thick sections, and FDM horizontal holes (no fetched source gives a teardrop diameter;
  FDM's arch is judged as a bridge instead).

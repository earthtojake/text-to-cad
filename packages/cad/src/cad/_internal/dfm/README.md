# The manufacturing checks

`cad.<type>.dfm(source, process=...)` and `cad <type> dfm SRC --process cnc|sheet|molding|printing`:
whether a part can be made by a process, and what to change where it cannot. This is the mechanism; the
library README's **Manufacturing checks** says what the check is for and how it is called.

## Two layers

**Facts.** An integration measures the part and answers a report of plain data: millimetres, degrees,
square millimetres, cubic millimetres and ratios. Exact geometry -- a STEP, an xbf, a document the engine
holds (its id or a model's handle), a live build123d shape -- is measured on its B-rep by the build123d
integration (`cad/build123d/_dfm_<process>.py` over the shared core, `_dfm_brep.py`); a mesh -- an STL, a 3MF,
a GLB -- by the trimesh integration (`cad/trimesh/_printing.py`), for 3D printing alone; a DXF, a sheet's cut
file, with ezdxf, build123d's own DXF library (`cad/build123d/_dfm_dxf.py`). CNC machining, sheet metal and
injection molding are judged on exact geometry alone: a mesh holds no radius, axis or thickness to read, and its
chords misread a molded part's draft, undercuts and walls. So a mesh type's `dfm` takes `printing` alone (its
default), and a DXF's `sheet` alone (`manufacturing.processes_for`); a mesh asked for another process is
refused with the reason and the check to run instead, the STEP's or the model's (`manufacturing._MESH_REFUSED`,
exit 2). Geometry both paths share is numpy alone (`cad/_internal/meshops_<process>.py`): numpy is the
library's one required dependency, so neither integration imports the other's.

**Where exact geometry is measured.** In the engine's checks processes: the caller resolves the options
(`manufacturing.options`) and asks the engine (`cad.engine.api.check`, an `export` carrying a `check` and the
caller's release), which answers the report, which the caller finishes into its result (`manufacturing.finish`).

- One of the engine's checks processes measures it when the server's library is the caller's (its release, code
  and libraries): a STEP's or an xbf's file, read once while its bytes stay as they were (by their digest, four
  files at most), or a document the engine holds, a model's, from its bytes, read once per version. They are a
  small pool of warm kernels of their own, never a model's worker, so checks of different documents run at once,
  a build or an inspection of a model waits for no check of it, and a long check or its crash costs no document
  anything.
- Otherwise it is another library's check, answered at once with no report. A file is then measured in the calling
  process, a model's document exported by the engine and read back there; a command whose environment holds no
  kernel sends either to the base's environment. So is a file where no engine can be reached. One line on stderr
  says so: nothing keeps such a check, so it is measured again each time.

Each part is measured on a copy that shares nothing with the document read (`_dfm_brep.of_source`), its result
equal to the same document's read from its file. The engine keeps each clean result by the version it measured -- a model's generation, a file's bytes'
digest -- with the check's type, process, options and the measuring library's release (128 results and 64 MB at
most in the engine's memory, and written beside its cache, under a model's revision, so a restarted engine finds
them), so the same check of an unchanged document measures nothing; a document holds one version's results. A
document that did not read, a refused check or a family not measured is not kept.

A check outlives its caller, as a build does: a shell's time limit cutting its caller off leaves it running, its
result kept, so the same check asked again finds it; asked while it still runs, it waits for that check and
answers with its result, measuring nothing. A check waiting for a busy process says what it waits for. A check
that does not complete is never a result: the engine's answer is a failure with one word for why (`reason`) --
`stopped` (the engine stopped), `cancelled` (its callers all gone, its process given to a check someone waits
for), `over_time` and `over_memory` (past a check's limits, `CAD_ENGINE_CHECK_SECONDS`, half an hour by default,
and `CAD_ENGINE_CHECK_RSS_MB`, by default the engine's memory cap), `process_lost` (its process exited under it),
`no_kernel`, `superseded` (its model was built again, or its file rewritten, while it was measured) and `error`
(the measuring raised). A run of a model's script that changes nothing disturbs no check of it.

A mesh and a DXF are measured in the calling process (or the integration's environment) always. A mesh is read
and cleaned (`cad/trimesh/_mesh.py`): corners at one place welded into one
vertex, a triangle two of whose corners became one dropped (it opens nothing), a sliver (under 1e-8 of the
diagonal squared) on an edge more than two triangles use dropped where its edges stay used once each way or
not at all (an exporter's collapsed chord left doubled or fanned over an edge; never one that closes the
shell), a connected piece of no area dropped, and a boundary loop within 0.2% of the diagonal of one straight
line -- a tessellation's crack -- filled, wound as its neighbours; a wider hole is the part's opening and stays
open. Watertightness is judged per body (`open_bodies`: an edge used an odd number of times), the volume the
closed bodies'; two bodies sharing a face are each closed. Printing splits the bodies with no repair: a piece
with no boundary has the faces another body shares filled in, a piece with one stays open.

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
and a STEP; `printing` for an STL, a 3MF and a GLB, its default (the others are offered and refused with the
reason and the fix: check the STEP or the model); `sheet` for a DXF, its default, so `cad dxf dfm cut.dxf`
alone checks the cut file. Each type's signature (`manufacturing.dfm_for`) holds its processes'
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
fix (`give --process cnc, sheet, molding or printing`), the command line's mistake (exit 2).

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
  part of an assembly is measured once, placed where its first occurrence stands. A part that is another's
  geometry moved -- an exporter's copies, a pattern written out part by part -- is found by its geometry
  (`_dfm_brep.copies`: its counts and faces' kinds alike, its volume and area the first's to 1e-6, and every
  vertex, each edge at its middle and quarters and each face at the middles and quarters of its parameters where
  the first's lie moved, ordinal for ordinal, 1e-7 of its size -- probes in one plane, which a mirror fits as well
  as a turn, are no copy; never by bytes, which a copy does not keep) and, in CNC and sheet metal (each part read in
  its own frame, so where it stands changes nothing), measured once: the first's items said again at the copy's
  refs, its places and directions moved onto it, its counts counted again (`_dfm_brep.moved`), the faces the
  kernel failed on said at the copy's own too. CNC reuses a measurement only where the copy's own machine frame
  (`machine.frames`, its own) is the measured part's turned with it: a copy turned by a right angle reads square
  to the world again, a frame of its own, and is measured anew (a mirrored copy too). A row of 46 copies among 107
  parts costs 61 parts' measurement, its report the same. Molding and printing read a part against the world's
  pull and plate, so they measure every part.
- **Exact rays** (`_dfm_brep.Rays`, each process's casts) cost what a crossing costs. On a heavy face -- free-form
  and of 48 edges or more, or a B-spline of 4000 control points or more (`heavy`) -- the kernel's intersector (`IntCurvesFace_Intersector`) classifies a line's
  crossing of the surface beyond the face's trim against every edge again, with a classifier made anew each call:
  6 ms a ray on a 526-edge face, against microseconds on any other. So a heavy face's candidates are screened by its
  triangulation (`Screen`: chunks of 16 triangles, each box widened by three deflections and the reach below -- a
  ray that meets none cannot cross the face, nor the full intersector accept a crossing of it beyond its trim),
  and cast with the intersector that does not
  re-classify; on the stretches of the line within reach of the face's edges (`Intersector`: the edges walked to
  2e-5 of the part, the reach twice the edges' largest tolerance, the face's, and the (u, v) tolerance the
  kernel's classifier accepts at the boundary in millimetres along the surface's finer direction, plus three
  walks' deflections) the full one is cast too, and its crossings the fast one lacks are added. The full
  intersector answers differently on different stretches of one line, so neither's crossings are dropped for the
  other's. What this keeps: every crossing on the face that the kernel's own intersector finds on the whole line
  (rays grazing a free-form face's edges: none lost); within the boundary's tolerance band, beyond the trim, a
  crossing is accepted as the kernel accepts it on that stretch, which may differ from its answer on the whole
  line by its tolerance. A face is read once; one whose triangulation cannot be read is not screened, and the
  full intersector answers for its whole line. A ray the kernel cannot intersect with a face (`Standard_Failure`
  on a degenerate patch), or a stretch of it near the boundary it does not finish, loses that crossing alone --
  the fast intersector's on the rest of the line are kept -- never the family: it is counted against the face
  and said (`rays_unintersected`, a warning naming the faces), and every family whose rays it cost names those
  faces (`unmeasured_faces`), so its rules say what was not measured there (below).
- **A family that failed** is `{"error": "..."}`, named in `partial_sections`, and an error finding
  (`measurement_failed`); the other families are still reported.
- **Every rule id has one outcome**: `passed` (each item within the limit; with none to judge -- no hole, no
  wall under the family's threshold -- `passed` with `evaluated` 0, reason `none found`, listed in
  `rules.none_found`; with some items lacking the figure, reason `N item(s) not measured`; with faces the family's
  rays could not be intersected with -- its `unmeasured_faces` -- each counted in `unmeasured`, named in the
  outcome's `unmeasured_faces` and its reason, `not_evaluated` where nothing else was judged), `failed` (each
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
  failures of one rule at one ref are one finding (`and N more at this ref`), a failure on a figure of an
  item that already fails a rule of higher severity, or of the same severity with a limit further off (the
  recommendation beside the feasibility limit it exceeds; `draft`'s 2 deg beside `draft_min`'s 0.5) is left
  to the record, a feature another finding names as its cause is judged there alone (a process says which:
  a special cutter's recess, an undercut's trapped faces), at most eight refs of one rule are findings and the rest are
  counted in one more, at `measurements.rules` with the rule's fix. Findings come in this order: what puts
  every other figure in doubt first, whatever its severity (`not_watertight`, `not_sound`,
  `measurement_failed`, `units_suspect`: `manufacturing._FIRST`), then errors, then warnings, then the facts
  and assumptions (info).
- **Figures are judged as measured.** Every figure a rule reads is kept to 1e-9 in the report and compared
  unrounded; only a message rounds it (four figures, more where value and limit would read alike). A limit is
  its source's number exactly (`molding.thick_section`'s 1 / 0.6, not 1.6667), and the comparison's slack is
  noise alone -- a billionth of the limit, an angle's a millionth of a degree (`rules.ANGLE_TOLERANCE_DEG`: a 2
  deg wall against a pull typed to nine digits reads 1.99999999) -- so a value exactly at its limit passes.
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
- **Not a solid.** Exact geometry is a part of material: a part holding no closed solid of any volume -- an
  open shell, a face, a solid of zero volume -- is refused before anything is measured, `not_solid` (an error,
  as `document_empty`, its message naming each such part and what to fix), in every process. A part whose
  solid has an open shell or that holds faces beside its solids is `not_watertight`, and one that fails the
  kernel's topology check (BRepCheck) `not_sound`: errors in every process, said first (printing's `solid`
  family judges its own solids' shells and soundness, with the boolean check). A mesh's open body is
  `not_watertight` too, an error.
- **Units.** One test for every process, exact geometry and mesh alike (`_common.units_doubt`): a document
  under 1 mm across, or over 10 m (the largest standard sheet is 3048 x 1524, 3.4 m across; gantry mills and
  large-format printers reach a few metres; none of the four processes makes a 10 m part in one piece), is
  `units_suspect` (a warning, said first), its note offering only the readings that make it a plausible size
  (metres, inches, centimetres for a small one; micrometres or millimetres read as metres, inches or
  centimetres for a large one). build123d has no unit and a model's is the millimetre, so a part modelled in
  metres reads a thousand times small; a STEP declares its unit, and one out of range is said all the same; a
  mesh is said as read with `--units`. A DXF's declared `$INSUNITS` is judged against the sheet on its own
  terms (below).
- **Sampling.** A face's samples are laid on a mesh whose tolerance is a fiftieth of the face's own size (its
  oriented box's longest side, `_dfm_brep.face_size`), so a part turned in its model is sampled alike; a
  process whose verdict must not depend on the pose measures the part in its own frame (CNC's machine frame,
  molding's frame about the pull) and turns every place back.

The Python functions: `cad.<type>.dfm(path_or_id, process=..., ...)`; on a live shape
`cad.build123d.cnc(shape)`, `sheet_metal`, `molding`, `printing` (the same `CheckResult`, refs as the
engine would name its document) and `cad.build123d.unfold(shape, k_factor=)`; on a mesh a program holds
`cad.trimesh.printing(mesh)`, `orientations` (the report as data).

## CNC machining

Exact geometry only (STEP, xbf, a document the engine holds, a live build123d shape); a mesh is refused.
Options: `--axes 3|4|5` (default 3), `--turning`, `--tools 3,6,10` (end mill diameters, mm), `--stock 100x60x25`
(mm; default the part's box), plus `--material`.

Every family is `{"items": [...], "count": N, <scalars>}`, items sorted worst first and capped at 200; every
item has `location` (a face ref, `plate/face 7`) and `xyz`; several-face features list `faces`. Each part
of an assembly is measured on its own B-rep; its items carry its refs. A family that raised is
`{"error": "..."}` and is named in `partial_sections`. `machine` echoes axes, turning, tools, stock.

**A part is one solid.** A part that holds several separate solids (a compound exported as one product) is
judged solid by solid (`_dfm_cnc._solids`): each its own stock, frame, setups and tool access -- another solid
of the part is no obstacle to its tools and no wall of its gaps --, its refs the whole part's, its `part` name
`<part> (solid 2 of 3)`; `cnc.solids_judged_apart` (info) says so, and the summary counts the parts judged. A
part of more than 20000 faces (`FACE_BUDGET`, text-to-cad's own bound) is not measured: `model` is
`{"error": ...}`, the report `partial`, never a pass.

Each part is machined in its own frame, never the world's: the rotation whose axes the most of its area lies
along (each plane's normal, each cylinder's, cone's or torus's axis, by its face's area). Two tolerances, two
meanings: directions within 0.81 degrees (`SAME`) are one cluster, its direction their mean by area; a face is
aligned with a frame by how near its direction is to an axis -- all of it on the axis, none 0.81 degrees off,
by the angle's square --, so the world's frame aligns less of a part tilted a twentieth of a degree than the
part's own does, and a tilt of 0.05, 0.4 or 0.8 degrees is machined in its own frame as one of 37 is.
Candidates: the world's frame and, about each of the six heaviest clusters, one whose second axis is the
heaviest cluster square to it (within a cluster's width, then squared exactly); the world's wins a tie (1e-9 of
the area), and of a frame's 24 rotations the one nearest the world's is taken. The part is
measured turned into it and every `xyz`, axis and direction turned back, so a part turned in its model reads as
drawn; `machine.frames` lists each part's (`axes`: the machine's X, Y, Z in the part's coordinates, `turned`,
`aligned_area_fraction`). An assembly's parts each take their own. Below, "world axis" is the frame's axis.

### Families (what each measures, and how)

- **holes** — a connected set of coaxial concave cylinders and cones (plus the planes square to the axis whose
  every neighbour is one of them: a counterbore step, a flat floor); sets on one axis whose cylinders of one
  radius overlap along it are one hole (a hole a slot splits); one radius's cylinders sweep >= 300 degrees
  together; a wider cylinder with a narrower one of the hole beyond it toward the opening (either way along a
  through hole) is an internal groove, no counterbore: it and the planes beside it leave the hole, a keyseat
  cutter's recess (`sharp_edges`, `access`), `grooves` [{diameter_mm, width_mm, location}] saying it.
  `diameter_mm` (narrowest full cylinder), `depth_mm` (the drilled length: that cylinder's axis between its two
  ends, each at its middle along the axis -- 25 / cos 30 deg for a 30 degree hole through 25 mm, where its
  longest side is longer --, below any counterbore), `overall_depth_mm` (every cylinder's extent),
  `depth_to_diameter`, `through` / `bottom` (`through`, `drill_point`, `flat`, `closed`, `other`: an exact
  ray along the axis from inside the hole meets the hole's own floor or not), `point_angle_deg` (a drill
  point's included angle), `counterbores` [{diameter_mm, depth_mm, depth_to_diameter}] (each its own feature:
  its depth is not the hole's; the **counterbores** family lists each, a stepped bore's larger step too, with
  its face as `location` and its `hole`, judged by the hole-depth rules as a hole of its own), `countersinks` [{diameter_mm, angle_deg}] (included angles, as drawn), `axis`, `aligned` (along an axis of the part's machine frame), `reachable` (along a direction the machine has),
  `inclination_deg` (to the frame's nearest axis), `opening`, `drilled` (<= 1 3/4 in, and not flat-bottomed: a
  drill leaves its point), `floor_tool` (a flat floor's: an end mill or a flat-bottom drill), `standard_drill`
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
  the machine has; or none of its edges left unmade, an edge only a setup of its own makes counted unmade: a
  chamfer mill's V reads as a pocket on one flank; or every face of it along a machine direction square to its
  axis: a profile cut along that direction, a plate's notch turned in the plane, never inclined),
  `inclination_deg`, `wall_count`, `floor` (its
  floor's ref), `width_faces` (the two walls the width is between; `location` is the first of them, else the
  floor), `micro_tool` (under 1 mm wide: only a micro tool fits). An open step that reads both ways (floor+wall or wall+floor seen from the side) keeps the shallower
  reading. **Through** cavities (`kind` `through`: windows, through slots, cut-outs, no floor) are faces along
  a world axis joined by concave or tangent edges along it, none a floor pocket's, none meeting a plane square
  to the axis by a concave edge, closed around the axis -- no ray across the axis from inside the cavity
  (from each face along its normal, then from the middle of that ray every 10 degrees and toward the middle
  of each pair of the edges leading out of it) leaves the part: an open valley, a quilted pad's grooves, a
  T-slot or a dovetail open at its neck is no window, whatever way its faces look; a keyway open only into
  its bore is closed --, with a corner -- a concave cylinder along
  it that is no floor's root fillet (no tangent plane neighbour seen end-on), or a sharp concave edge along
  it; `depth_mm` is the walls' extent along the axis, `depth_from_top_mm` the shallower side's reach,
  `width_mm` / `depth_to_width` as for a pocket, `floor` null.
- **internal_corners** — a pocket's in-plane corners: concave cylinders along the pocket's axis (`radius_mm`)
  and sharp concave edges along it that no tool makes from another side (`radius_mm` 0, `sharp` true,
  `edge`). A corner's `location` is its cavity's ref (`pocket`), which the cavity's corners share, so one
  cavity is one finding a rule (`and 3 more at this ref`; the record holds each); `corner` is its own face. `height_mm` (the corner's own extent: the cavity depth there), `depth_mm` (from the part's top),
  `radius_to_depth`, `tool_mm` (largest `--tools` tool <= 2r, else 2r), `reach_ratio` (depth / tool_mm),
  `micro_tool` (that tool under 1 mm),
  `pocket` (its floor's ref; a through cavity's `location`), `folded_edges` (the sharp edges its run makes
  through small edge rounds at its ends -- an edge sharing a vertex and a face with it that runs along its
  axis, or is a face of such a round and under twice its radius long; never a floor-to-wall edge -- folded in
  rather than listed under sharp_edges). A through cavity's concave cylinders and unmade sharp edges along it
  are its corners the same way. `radius_mm` is read to 0.01 mm (`RADIUS_TOLERANCE`: 1.4999
  is 1.5). Floor-to-wall roots are never corners (a flat end mill makes them sharp). `third_of_depth_mm`: a
  third of its height, the radius the hint gives in millimetres; `opening_mm` its cavity's width, `fits_mm`
  half of it and `radius_fits` whether that third fits -- where it does not (a 6 mm keyway 22 deep) the hint
  says so and names how such a corner is made instead (`instead`: a keyway, a through slot off a bore along it
  (`keyway`), broached or slotted; any other by EDM).
- **sharp_edges** — every other sharp concave edge no rotating tool makes (each with `void_angle_deg`,
  `length_mm`, `edge`, `faces`, `makeable` 0, `radius_mm` 0, `acute`: void under 90 degrees, and `reason`,
  the first that holds: `other_axes` -- a tool along a direction the machine lacks would make it (a tool tilted
  square to one face whose other face is no flank along it: an angled setup or more axes); `vertical_corner` --
  both faces lie along a machine direction the edge runs along, a corner of a profile or a cavity cut along
  it where the tool's side leaves its radius (a gear's curved tooth root, a closed pocket's corner); `acute`;
  `blocked` -- a face is a plane square to a machine direction, the way along it blocked, or some way reaches
  part of the edge (here or with more axes) and an obstacle the rest; `no_square_face`; and before them
  `no_way_in`, an error -- a disc cutter reaches every station but no disc gets there, see below). Two more
  reasons are warnings on edges that are made: `narrow_opening` (a slot cutter's opening narrower than its
  recess is tall, `opening_mm` and `recess_mm`: a text-to-cad figure, not a passage) and `obtuse_root` (an
  obtuse root between two planes seen end-on along a machine direction -- a profile's, a valley's: a tool
  side-milling it, or a ball, leaves its radius; it is sharp only facing each side from its own direction,
  two more setups the count leaves out, one where a face is square to a setup it counts (`more_setups`), none
  said where both are; the same at every turn). A V of a standard angle (`V_MILLS`) is a chamfer mill's along
  its bisector, its cone the V as drawn, and no root of a chamfer mill's V or shoulder is `obtuse_root`. The
  rule is the part's, whatever its turn: a notch in a plate turned 30 degrees reads as one along the plate's
  axes. A crease a ball end mill makes is an item too: `made_by`
  `ball_mill`, `makeable` 1, `radius_mm` the ball's (half the smallest `--tools`, else 1.25), `deviation_mm`
  = R (1 / sin(void / 2) - 1), the round's departure from the drawn edge. A corner of `BALL_VOID_DEG` (150
  degrees) or more along a machine direction -- a 12- or 24-sided pocket's, a faceted arc's -- is made by the
  end mill's flank and is an item the same way (`made_by` `end_mill_flank`, `radius_mm`, `deviation_mm` the
  residue the radius leaves in the corner): `cnc.flank_corners` says it, and `cnc.flank_corner_residue` warns
  past `FLANK_RESIDUE_MM` (0.05 mm, text-to-cad's own figure); a corner under 150 degrees keeps the corner
  rules. An edge of a closed void is the void's (`by_tool` `enclosed_void`): no tool
  enters it, and `voids` is its one defect. Each way is tried at stations
  along the edge (its ends 0.05 mm inside, and between), 9 at least and at most the smallest tool's radius
  apart (`--tools`, else 1.25 mm; 129 at most) so an obstacle a tool could not pass between two is never
  missed, and makes it only where it reaches every one: a 0.5 mm window at a corner's mid-height, or a front
  wall cut down to a 2 mm lip, side-mills no 10 mm corner; a disc cutter's costlier walk is tried at the 9
  first. Where some way reaches part of an edge, the stretch none reaches is unmade: between a reached station
  and an unreached one the boundary is found by bisection (every way tried there) to 0.1 mm (1% of an edge
  under 10 mm); the item (or the corner) sits at the middle of the longest such stretch, `unreached_mm` their
  length (a 5 mm bridge over a 100 mm channel's edges reads 5.0, wherever it stands), and its message says so.
  An edge shorter than 0.025 mm (or a hundred-thousandth of the part) is a sliver of the model's own and not
  judged (`by_tool` `sliver`). Made by: an
  end mill where one face is a plane square to an approach direction (a floor or a ceiling), the void angle
  >= 90 and a ray from that face along the direction escapes; a square end mill along any direction a setup
  presents (the part clamped to present it, 3 axes' re-fixturing) where one face is a plane square to it (the
  end), the other lies along it (the flank) and a ray from the end along it escapes -- a profile's corner
  side-milled, that direction one setup (`setups`); an end mill is tried from both faces before any cutter;
  a keyseat cutter where the recess has a floor and a ceiling square to that direction and its way in is a
  bore it meets by a convex edge seen along it (a groove inside a bore), else a T-slot cutter, where beside
  every station the cutter's shank (0.5 mm about its axis) leaves the part along the direction from some
  place across the void and the disc that reaches the station from there touches no material short of the
  edge's own ends, slid back along the edge where it passes them (the shank travels along the edge: an 8 mm
  port in a wall is no way to a 25 mm corner; an edge shorter than the disc is no run for one); a dovetail
  cutter of any acute angle likewise, its floor a plane square to one of the part's axes (45 and 60 degrees
  are standard; another, Parker's 66, is a cutter ground to it, the special cutter's finding naming the
  angle). The disc must get there, by geometry alone (the least disc that reaches the station from the
  opening, its shank of no breadth): a keyseat cutter's no wider than the bore it comes down, so every
  station within twice the bore's radius of its axis (a 20 mm chamber behind a 4 mm bore: none); a slot or
  dovetail cutter's plunged through an opening as wide as the disc somewhere along the edge (its sides found by
  bisection), or fed in at its own level from a side the recess opens to (a T-slot from its open end; a round
  chamber under a 5 mm port: neither). Else the edge is unmade, `no_way_in`. A slot cutter's opening is read at
  every station: narrower than the recess is tall, `narrow_opening` (a warning). A
  60/90/120 degree chamfer mill along a V's bisector where the bisector keeps to one axis along the edge
  (five axes tilt it along a curved one); a V of another angle under 90.5 degrees is a V cutter's ground to it
  along its bisector (a special cutter, its angle named), or on five axes a 60 degree mill tilted to each
  flank in turn, its cone's side on the flank (each flank an orientation); and a chamfer mill's shoulder (a 150/135/120 degree void: one face
  along the mill's axis, the other the cone's, its normal's cosine to the axis the half angle's sine within
  0.01 -- a face along the axis, 1e-16 off square in a turned part, is none), or its pointed tip along a floor's
  root under a face its cone lies on (a floor under a 45 degree chamfer, the 90 degree mill's); an end mill's
  corner, tried before any disc cutter, where one face lies along the tool's axis and the other looks along it
  (a wall's root over a chamfer or a slope falling away below the tool's end: side-milling the wall down to the
  root leaves it sharp, made in its faces' setups, nothing said); a ball end mill where the void
  angle is >= 150 degrees
  (`BALL_VOID_DEG`, the owner's to confirm: the ball's round departs from the drawn crease by
  R (1 / sin(void / 2) - 1), 0.035 R at 150) along a direction both faces look along whose ray from the crease
  escapes (each face's normal more than half a degree's sine along it); a drill or tap for a hole's own edges.
  Last, along directions a setup presents: a chamfer mill along the bisector of a V between two planes,
  whatever the turn (a 60 or 90 degree V's bisector a setup of its own, even along a machine axis), and an
  obtuse edge (void over 90) between two planes each seen from outside along its own normal, each side faced
  from its own direction (the tool's corner forms the edge, the other face leaning away: a 140 degree
  valley's, a 100 or 120 degree profile root's). An obtuse edge (void over 90.5, `OBTUSE_DEG`) adds no setup of
  its own, however it is made: it is made in the setups that make its two faces, which the cover counts (a
  root reads one count at any turn; a hex socket's pyramid floor adds none). On five axes (simultaneous) a chamfer
  mill's direction leans along the edge as it goes (an end mill's axis stays its plane face's normal: leaned,
  it would gouge it), up to 40 deg toward its way, by at
  most 20 deg station to station (`LEANS_DEG`, own figures): a continuous path, not one direction for all 9
  stations (on 3 and 3+2 axes, one direction an edge). A gear's curved roots and a closed pocket's corners
  stay unmade. `by_tool` counts every concave edge by the tool. A recess a special cutter makes takes in the
  faces across its edges no tool makes (its square ends, which the disc leaves round): what no straight line
  reaches there is the recess's; and its own faces ask the setup cover no direction (the cutter's axis, either
  way, is its edges' need): an O-ring groove round a boss reads one setup, not three. An edge sharing a vertex with a reported corner and a face with it (or with a round
  tangent to its faces) is folded into that corner.
- **knife_edges** — convex edges whose material angle, read along the edge (a curved one at 17 points: an
  edge where a cone meets a sphere runs from 63 to 42 degrees), falls under 45 degrees (`KNIFE_DEG`,
  printing's): the material thins to nothing there. `angle_deg` (the least, found between the samples about it
  by golden-section search, as printing's: a rod cut 30 deg off its axis reads 30.0), `length_mm` (the stretch under
  the limit), `edge_length_mm`, `thickness_mm` 0, `edge`, `faces`. The two faces of a knife edge are no wall to
  each other.
- **walls** — under each sampled point of each face, an exact ray into the material to the first face across
  that faces back (normals within ~45 degrees of opposite; not across a knife edge); the thinnest per face
  under 5 mm: `thickness_mm`, `opposite`, `height_mm` (a plane's extent across its longest concave root edge),
  `height_to_thickness`, `surface`, `standing` -- a thin feature that stands: a plane rising from a concave
  root edge (or a root fillet) at one end with no concave edge across its other (a fin, a rib, a wall beside a
  pocket; never a floor, held all round, nor a plate's face), or a convex cylinder with a root at one end
  alone (a pin, a boss), the material of one thickness (two planes facing apart within ten degrees, a pin's own
  face: a dovetail's lip is a wedge, and none); `height_mm` is then what it stands to. The 200 listed items
  are refined to the exact least distance between the
  face and `opposite` (`BRepExtrema_DistShapeShape`; faces sharing an edge or a vertex are not), kept where the
  segment leaves the face within ~45 degrees of its inward normal and its middle is in the material or on the
  boundary: `refined` true, `xyz` the thinnest point. A face and its `opposite` are one item (the thinner
  reading): one web is one finding; gaps likewise.
- **gaps** — the same ray outward across the void (holes and threads excluded, and a face sharing an edge with
  the ray's own: the two close to nothing at that edge -- a dovetail's flank over its floor, a V groove's
  flanks --, the void's angle, `sharp_edges`' to judge); the narrowest per face under
  10 mm: `width_mm`, `opposite`, `surface`, `made_by` (`end_mill`; `slot_cutter` where the two faces are the
  floor and ceiling of a recess a special cutter makes -- planes facing each other square to one direction --,
  `cutter_recess` its ref: the cutter's thickness cuts that height, not an end mill's diameter); refined the same
  way, through the void. One pocket's or cavity's gaps are one item, its narrowest (`pocket`, the others'
  refs in `also_at`): one slot is one finding.
- **access** — faces (the stock's own excluded: the planes on the part's box, where the blank is as long as
  the part along that axis -- no `--stock`, or one whose side there is the part's, its sides matched to the
  part's longest first) whose sampled points no
  straight line from the machine's directions reaches (exact rays must escape the part; back-facing points
  never count): `unreached_fraction`, `unreached_any_direction_fraction` (a face of revolution's own axis
  either way, then the probes: 200 directions over the sphere),
  `kind` (`undercut`: five axes would reach it; `no_line_of_sight`: nothing straight would), `hole` and
  `hole_axis` (a hole's face, and its axis). A `no_line_of_sight` face is then tried for a disc cutter on a
  straight shank -- a keyseat cutter down a bore, a T-slot cutter through an opening, a lollipop
  (`_disc_gets_to`, on 4 of its points, along the part's six axes and six more of its own directions): across
  the void from the point, square to the shank, an opening is found where lines along the shank leave the part
  (offsets doubling from 0.02 mm: any opening wide enough for the disc holds one); the least disc that reaches
  the point has its shank at the opening's side nearest it; and it gets in where the opening holds that disc
  (lines along the shank from its rim, centred in the opening, leave the part; at its limit to the sides' own
  0.005 mm it does) and the disc, at the point, touches no material. `disc_reach` (every point probed: a
  12 mm groove behind a 10 mm bore; a 24 mm chamber behind one is not) and `no_tool_fraction` (the share of
  the face neither a line nor such a cutter reaches). The faces of one recess that share an edge are one
  item, judged at its worst face: `faces`, `face_count`. Items of `kind` `special_cutter` are the edges only a T-slot,
  dovetail or keyseat cutter makes, joined by the faces they share, whatever line of sight says: `cutter`,
  `edge_count`, `edges` (their fractions 0), `advice` (the hint's ask: a recess whose dovetails are all within
  `SQUARABLE_DEG`, 10 degrees, of square is a wall drafted back, asked squared so an end mill makes it; any
  other kept to a standard cutter). Directions: 3
  axes the six world axes; 4 axes those plus every 15 degrees about the rotary axis (X, Y or Z, the one
  that reaches most); 5 axes those plus every 15 degrees about each world axis, then the part's own and 200
  over the sphere (so five reach at least what four do).
  One cause, one judged item: an `undercut` or `no_line_of_sight` face of a special cutter's recess is that
  recess's (`part_of` its ref; the `special_cutter` item lists them in `unreached_faces` and its message names
  them, saying which no straight line reaches at all), and on 3 and 4 axes an inclined hole's unreached faces
  are the hole's (`part_of`; `cnc.inclined_feature` judges it). Neither is judged by `cnc.undercut` or
  `cnc.no_line_of_sight` again.
- **setups** — one item per part: the greedy set cover of the sampled area and of the sharp edges an end mill
  makes, each from one of its directions (the area first, the edges a direction makes breaking a tie; a
  direction the machine lacks reaches what a straight line along it does; a hole's faces only along its axis,
  from the end that reaches all of it -- a hole is drilled whole, and its wall glimpsed from another side asks
  no setup --, an inclined hole's its own setup), by direction (`directions`
  [{direction, area_fraction, faces, sharp_edges}]: `sharp_edges` the edges it is the first to make -- a
  notch side-milled), `orientation_count`, `setup_count` (clampings: each orientation on 3
  axes; directions square to the rotary axis are one on 4; directions within a half-space above one
  clamping face are one on 5), `unreached_area_fraction`, `rotary_axis`, `sampled_points`,
  `inclined_directions` (each inclined hole's or pocket's own direction: one more orientation and clamping).
  A part with no face but the stock's own takes none (`setup_count` 0).
- **voids** — closed cavities (inner shells): `volume_mm3`, `face_count`.
- **stock** — per part: `size_mm`, `stock_mm`, `stock_given`, `fits_stock`, `length_mm` >= `width_mm` >=
  `height_mm`, `volume_mm3`, `stock_volume_mm3`, `removal_ratio` (null where the part does not fit).
- **small_features** — faces narrower than 0.5 mm (2 x area / perimeter); scalars `smallest_edge_mm`,
  `smallest_face_mm2`, `fine_faces` (under 1 mm).
- With `--turning` (pockets and internal_corners are then the live tooling's features alone -- its face groups
  and the planes they meet at a concave edge, a keyway's square ends --, measured and judged as a mill's):
  **turning** (per part: `axis` — the line
  whose coaxial cylinders, cones and tori have the most area —, `axis_origin`, `axisymmetric_fraction` (area on
  faces of revolution about it and on planes square to it whose every edge is a circle about it),
  `max_diameter_mm`, `length_mm`,
  `length_to_diameter`, `bar_removal_ratio`, `off_axis_faces`, `sharp_profile_corners`), **turned_diameters**
  (convex coaxial cylinders not groove floors: `diameter_mm`, `length_mm`), **bores** (on-axis holes),
  **grooves** (a coaxial cylinder with both ends meeting square planes by concave edges: `internal`,
  `width_mm`, `depth_mm`, `depth_to_width`, `diameter_mm`, and internal: `entry_diameter_mm` -- the wider of
  the two bores beside it, its tool's best way in -- and `depth_to_entry`), **live_tooling** (off-axis face groups: `cross_hole`, `flat`,
  `slot`, `feature`, with the hole's `relation`).

### Rule ids (finding code = rule id)

Severity e = error (no general shop makes the part as drawn), w = warning (a recommendation, a cost or a
risk: it is made). "tools" = the limit follows the smallest `--tools` tool when given. A number a published
guide states cites it: Protolabs Network (Hubs)'s "How to design parts for CNC machining" (`hubs-cnc`) and its
CNC machining service page's maximum part sizes (`hubs-cnc-service`). A floor no guide states is text-to-cad's
own (**own** below; the rule's source is `text-to-cad`, so its message reads `source: text-to-cad`, never the
publisher's name, and its note gives the reason). One tool floor holds for holes, slots and corners: the
0.05 mm the guide's small-features table calls a feasible hole (`TOOL_FLOOR_MM`); a tool under 1 mm is a micro
tool (`MICRO_TOOL_MM`), which reaches ten of its diameters (`MICRO_REACH`, own).

| id | family.field | limit |
|---|---|---|
| cnc.internal_corner_sharp | internal_corners.radius_mm min, sharp corners | sharp: no round tool makes it (e: Hubs "the internal corners of a CNC part always have a radius"); the limit 0.025 mm (own: the smallest feasible tool's radius, Hubs' "Feasible: 0.05 mm" hole); tools: 0.5 x min tool (e); the hint gives 1.25 mm or more recommended (a 2.5 mm end mill's) and a third of the depth in mm |
| cnc.internal_corner_radius | internal_corners.radius_mm | 0.025 mm (e, own: half the tool floor); tools: 0.5 x min tool (e) |
| cnc.internal_corner_small | internal_corners.radius_mm min 1.25 (w) | features under 2.5 mm are micro-machining |
| cnc.corner_radius_to_depth | internal_corners.radius_to_depth min 1/3 (w) | Hubs "Recommended: ⅓ times cavity depth (or larger)"; the hint gives the radius in mm |
| cnc.corner_reach / _limit | internal_corners.reach_ratio max 4 (w) / 30 (e); 10 (e, own) where `micro_tool` | 3-4 D cutting length / 30:1 specialised; a tool under 1 mm is catalogued to about ten diameters (a 0.1 mm corner 6 mm deep is no tool's) |
| cnc.sharp_internal_edge | sharp_edges.radius_mm min, message and fix by `reason` (e; `other_axes` w: an angled setup or more axes) | 0.025 (own, as internal_corner_sharp; the fix gives 1.25 mm or more recommended); tools: 0.5 x min tool |
| cnc.knife_edge | knife_edges.thickness_mm min (w) | metal 0.5 / plastic 1.0 (the feasible wall) |
| cnc.pocket_depth_to_width | pockets.depth_to_width max | 4 (w) |
| cnc.pocket_depth_limit | pockets.depth_to_width max 30 (e); 10 (e, own) where `micro_tool` | Hubs "A tool diameter-to-cavity depth ratio of up to 30:1 is possible using specialized tooling", read for a width: a cavity takes no tool wider than itself |
| cnc.tall_feature | walls.height_to_thickness max 4, `standing` (w, own) | a rule of thumb: a thin wall, rib or pin over four times its thickness chatters; no hard limit, never an error |
| cnc.wall_thickness | walls.thickness_mm min | metal 0.5 / plastic 1.0 (e, feasible) |
| cnc.wall_thickness_recommended | walls.thickness_mm min | metal 0.8 / plastic 1.5 (w) |
| cnc.inclined_feature | pockets / holes.inclination_deg max 0 where `reachable` is false (w); 3 and 4 axes (5: n/a); a profile cut along a machine direction is reachable | align features to the six principal directions of the part's own frame (`machine.frames`), else 5 axes |
| cnc.hole_diameter | holes.diameter_mm min | 0.05 (e: minimum hole diameter "Feasible: 0.05 mm (0.005 inches)") |
| cnc.hole_diameter_small | holes.diameter_mm min 1.0 (w) | holes, diameter: "Feasible: any diameter larger than 1 mm"; under it, micro-drilling |
| cnc.hole_depth / _limit | holes.depth_to_diameter, counterbores.depth_to_diameter max | 4 (w) / 40 (e) |
| cnc.drill_size | holes.drill_deviation_mm max 0.005 (w), drilled holes | standard drill sizes |
| cnc.thread_size | threads.major_diameter_mm min 6 (w) | M6 or larger recommended |
| cnc.thread_length / _minimum | threads.length_to_diameter max 3 / min 1.5 (w) | 3 D adds no strength / 1.5 D minimum |
| cnc.gap_width | gaps.width_mm min | 0.05 (e, own: the tool floor, a gap takes no tool wider than itself); tools: min tool (e) for `made_by` end_mill, 0.05 for a slot cutter's recess height |
| cnc.gap_width_small | gaps.width_mm min 2.5 (w) | features under 2.5 mm are micro-machining |
| cnc.undercut | access.unreached_fraction max 0.02, kind undercut, not `part_of` another cause (w; a hole's face: its fix names the axis); access.unreached_any_direction_fraction, kind no_line_of_sight where `disc_reach` (w: only a keyseat or lollipop cutter through its opening makes it) | special cutters |
| cnc.special_cutter | access.edge_count max 0, kind special_cutter (w; its message names the recess's unreached faces) | "The width of an undercut can vary between 3mm and 40mm." |
| cnc.no_line_of_sight | access.no_tool_fraction max 0.02, kind no_line_of_sight, not `part_of` another cause (e, own; milling and turning) | by geometry: a tool is straight, and a disc on a shank reaches no further past an opening than the disc the opening lets in |
| cnc.enclosed_void | voids.volume_mm3 max 0 (e) | a tool reaches only what it can enter |
| cnc.setups | setups.setup_count max 5 (w) | rotated "up to three or four times" (five clampings) |
| cnc.part_size | stock.length_mm max 2000 (w, milling); turning.max_diameter_mm max 431, turning.length_mm max 990 (w, turning) | the service's maximum part sizes: "3-axis CNC milling (soft metals) 2000 x 1500 x 200 mm", "CNC turning (lathe) Ø431 x 990 mm" |
| cnc.part_size_limit | stock.length_mm max 4000 (e, own, milling); turning.max_diameter_mm max 1000, turning.length_mm max 4000 (e, own, turning) | twice (a lathe's length: four times) what the cited network's machines take: past any general machine |
| cnc.turned_slenderness | turning.length_to_diameter max 10 (w, own, turning) | past about ten diameters a steady rest or a sliding-head lathe: made, never an error |
| cnc.groove_depth_limit | grooves.depth_to_entry max 0.5, internal (e, own, turning) | by geometry: a tool that passes the bore reaches past its wall by less than its own width |
| cnc.groove_depth | grooves.depth_to_width max 5 (w, own, turning) | a grooving insert's reach, a rule of thumb |

The pocket and corner rows apply under `--turning` too, to the live tooling's pockets. Under `--turning` the
milling rows -- `sharp_internal_edge`, `gap_width*`, `inclined_feature`, `special_cutter`, `undercut`,
`setups` -- are `not_applicable`, and `cnc.turning_not_judged` (info) says what turning does not judge.

No rule judges a shop's own feature limits (its narrowest engraved line, its smallest part, its turned
diameters and cross holes) or its own machine: those are a shop's, and the measurements (`stock`, `turning`,
`turned_diameters`, `grooves`, `holes.relation`, `pockets.depth_from_top_mm`) are compared with them. The
part's size is judged against a general machine's alone (`cnc.part_size`). `--stock` given is checked
(`cnc.stock_too_small`).

Each finding's message ends with what its item says of itself (`Rule.detail`): `internal_corner_sharp` its
edge, height and depth below the top; a round corner's rules its own face (`corner`) and height; `sharp_internal_edge` its edge, the two faces, the void angle and xyz
(its fix names the angle); every `walls` and `gaps` rule the face across (`opposite`) and the thinnest point.

Fact findings (not rules): `cnc.stock_too_small` (e: the part does not fit `--stock`), `cnc.no_turning_axis`
(e, `--turning` on a part with no surface of revolution), `cnc.mostly_not_turned` (w, under half the area
turns), `cnc.live_tooling` (i), `cnc.turned_corner_sharp` (i: the sharp internal corners of the turned
profile, each left with an insert's nose radius), `cnc.turning_not_judged` (i), `cnc.solids_judged_apart`
(i), `cnc.rotary_axis` (i), `cnc.fine_detail` (i, >= 20 faces under 1 mm),
`cnc.material_assumed` (i: no `--material`, walls judged by metal's limits), `cnc.ball_creases` (i: the
creases a ball end mill rounds, the worst one's departure from the drawn edge).
The summary says a part's setups (an assembly: the most any part takes), never a sum.

Context the rules read: `material_class`, `wall_class` (the class, else `metal`), `tools_given`,
`min_tool_mm`, `axes`, `turning`.

Sources (the rules' version 2026-11-09): Protolabs Network (Hubs), "How to design parts for CNC machining"
(accessed 2026-11-06) and its "CNC machining service" page's maximum part sizes (accessed 2026-11-09);
`text-to-cad` for its own floors.

### What it cannot measure

Tool holder and spindle collisions (access is a line of sight, a tool of zero diameter; width and corner
radius cover the diameter separately); a disc cutter's path from where it gets in to each station (its way in -- a bore, an
opening as wide as the disc, an open side -- and its shank's way out and clearance at each station are judged,
the travel between them not); a rounded recess fed from an open side that no straight line reaches into (a
face no line reaches is tried for a disc plunged along its shank alone); a disc cutter's shank (taken of no
breadth: the floor is geometry's, a real cutter reaches less); an angled fixture's reach (an inclined feature is counted as one more setup); fixturing and
workholding; tolerances, surface finish, cycle time or cost; thread callouts on a drawing (only modelled
threads and tap-drill diameters); hole axes other than a cylinder's (a slot milled as a hole); pockets whose
floor is not planar (a 3D-contoured cavity is reported through access and walls, not as a pocket); sharp
edges are judged at their midpoint; text and engraving are recognised only as many fine faces and as
narrow gaps; a crease a ball end mill makes is accepted at `BALL_VOID_DEG` whatever the part's tolerance
(its departure is recorded, not judged); a tall feature thicker than 5 mm (walls are listed under that);
turning: parting/chucking allowances, a boring bar's reach (a bore is judged as a drilled hole), a thin
section's slenderness (the part's is its length over its largest diameter), and a cone point's angle on the
turned profile itself (only a hole's drill point is read).

### Budgets

A part is meshed once and sampled about 400 x sqrt(faces) points by area, at most 6000, each face 1 to 16 (rays grow
with the face count's square root, not the triangulation). Rays along one direction look up a grid of the faces' box
shadows square to it. A point no machine direction reaches is probed on two points a face, at most 32 directions
each (the part's own normals and axes first, then every 15 degrees about each world axis, then 200 over the
sphere); a point that fails all 32 reads as having no line of sight -- a stated cap, so a rare direction can be
missed (a face of revolution's own axis is tried first: a deep bore's wall sees out along it alone). A face's
unreached share is read on at most 16 points, its disc cutter's reach on 4. A part of more than 20000 faces is
not measured (`FACE_BUDGET`); rays' boxes are tested together a batch of at most a million ray-face pairs
(`BATCH_PAIRS`), so memory a batch does not grow with the part's faces. Time is not bounded otherwise: a ray
costs with the edges of the face it crosses (a plate of 576 holes takes most of a minute).

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
  cut interrupts) is laid along the same line with its own strip, no loop. Two bends meeting tangent with no
  flat between them meet at a joint, a flange of no faces at their shared tangent line: the unfold runs on
  through it, the second strip laid where the first ends (no flange there for the flange rules). Two that
  turn opposite ways (their axes either side of the sheet there: an S-jog) are a joggle (`parts.joggles`);
  two the same way round are a compound bend, unrolled and no more. A flange between two parallel bends that
  turn opposite ways is an offset's web (`flanges.web_of`, its two bends); the type side lists one under the
  flange minimum (`sheet.flange_length`'s 2 t, from the outside of the bend) among the joggles too, its items
  `joggle_web` (which flange_length leaves alone). Fused, this is the flat pattern;
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
| `parts` | `thickness_mm`, `is_sheet`, `why`, `sheet_area_fraction`, `bend_count`, `sharp_bend_count`, `flat_length_mm`, `flat_width_mm` (smallest rectangle), `flat_area_mm2`, `flat_overlap_mm2`, `neutral_area_ratio`, `flat_material_fraction`, `box_short_mm`, `unfold_note`, `not_in_flat` (the flanges no bend reached, each its largest face, and the bends not laid out), `joggles` [{bends, location, xyz}] (two bends meeting tangent with no flat between), `flat_bend_lines` | one per part |
| `not_sheet` | `kind` (thicker, thinner, unpaired; `edge_break`: a chamfer or round of a cut edge, its depth `break_mm`; `formed`: a cone, torus or freeform face a thickness across), `surface`, `local_thickness_mm`, `sheet_thickness_mm`, `deviation_mm`, `area_mm2`, `judged` (None on a part that is not sheet, or a round a `sharp_bends` item names: no thickness verdict) | a boss, pocket, round, freeform face |
| `sharp_bends` | `kind` (sharp, inside_only, outside_only, unjoined), `angle_deg`, `inside_radius_mm`, `outside_radius_mm`, `thickness_mm`, `edge_count`, `faces` | a corner joined without a bend: its flange is not in the flat |
| `bends` | `kind` (bend, hem, curl), `inside_radius_mm`, `outside_radius_mm`, `radius_to_thickness`, `angle_deg` (bent from flat), `included_angle_deg`, `flanges_angle_deg`, `length_mm`, `axis`, `axis_origin`, `tangent_lines`, `k_factor`, `k_factor_source`, `bend_allowance_mm`, `bend_deduction_mm` (None for a hem or curl: its mold lines meet nowhere); `faces` [inside, outside] | location: the inside cylinder |
| `flanges` | per bend side: `length_tangent_mm` (least along the bend), `length_tangent_half_mm` (reached by half the bend), `length_inside_mm`/`_half`, `length_outside_mm`/`_half` (mold lines: + r·tan(θ/2), + (r+t)·tan(θ/2)), `length_outside_minus_radius_mm`, `stations`, `stations_off_flange` | the length runs to the free edge or the next bend's tangent line, read at 11 stations along the bend; a station whose start is off the flat (the bend runs on past its flange there) has length 0, judged by `sheet.flange_length` as a short flange is, the item then at the bend (`location` its ref, `xyz` that stretch) |
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
the part's width; named as its ref names the part), `sheet.sharp_bend` (error: each `sharp_bends` item, one
finding per place; the message says which radius is missing, the hint "model an inside radius r >= t and an
outside radius r + t at the corner"), `sheet.flat_incomplete` (error: `flat_material_fraction` off 1 by more
than 3%, the flat is not the part's blank, where no `sheet.sharp_bend` or judged `not_sheet` face already says
why: it names what did not unfold, `not_in_flat`, at the first of them, or says that every flange and bend
did; context `sharp_bends_found`), `sheet.thickness_mismatch` (error), `sheet.flat_overlap` (error),
`sheet.not_unfolded` (warning: a loop of bends, a flange no bend reaches), `sheet.joggle` (warning, one per
joggle: two bends that turn opposite ways with no web or one under a flange's minimum between them, unrolled;
it needs an offset/joggle die, not measured; a web at or over the minimum is two ordinary bends, and the
joggle's bends keep their own `bend_radius`), `sheet.formed_surface`
(warning, one per part: its `formed` faces, not measured -- a cone, a torus or a free-form face is rolled,
spun or stamped, an emboss, a louver or a bead, not brake-bent, and no source gives a stamped form's
feasibility limit: quote it as a formed feature), `sheet.edge_break` (warning, one per part: its chamfered or
rounded cut edges, a second operation after cutting), `sheet.bend_radius_differs`
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
`sheet.hole_spacing` min 2 t (warning: a laser-cutting best practice, its risk the forming's -- "Holes that are
too close to each other can lead to deformation or breakage during forming or bending."); `sheet.web_width` webs.width_mm min 1 t (warning; Hubs's hole-to-edge applied
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
distances; window bends; a joggle's own limits (its offset against the thickness, a joggle die's: its two
bends are unrolled, `sheet.joggle`); stamped forms -- embosses, louvers, beads -- beyond saying them
(`sheet.formed_surface`); box flange maxima and the corner flange gap;
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

A STEP, an xbf or a model's document is measured on its B-rep (`cad.build123d._dfm_molding`, its geometry's
numpy in `cad._internal.meshops_molding`); every item is at a face ref (`plate/face 7`) plus `xyz`. A mesh is
refused: its chords misread draft (a 2 deg cone's read 1.998), its regions merge a fillet with the faces it
joins, and its tessellation folds and slivers read as undercuts -- check the STEP or the model. A part of one
solid is measured in its own frame about the pull (its long direction in the parting plane along the plane's
first axis; `frame` says the turn), and every place and side action is reported in the world: a part turned
about the pull in its model reads the same figures.

On the B-rep a face's surface is its kernel type, and a B-spline or Bezier face that IS a plane, cylinder,
cone, sphere or torus (within a millionth of its size, 1e-4 mm at most: `_dfm_brep.surface`) is read as that
surface. `extrude(taper=)` flaring outward, a loft between similar sections and many STEP exporters write
analytic walls and their fillets as splines; read as splines, their draft would be sampled, not exact, and
their fillets, ribs and bosses unrecognised.

### Families (`measurements.<family>`)

| family | what | how | items (fields the rules read in **bold**) |
|---|---|---|---|
| `draft` | each wall face's draft along the pull and the way it opens | B-rep: plane exact, cylinder/cone with axis along the pull exact (0 / half-angle), other faces the least over points sampled ON the surface and along its edges (a round tangent to a wall square to the pull reaches 0 on that edge, which no sample inside it lands on) | `location`, **`draft_deg`**, `area_mm2`, **`opens`** (`+pull`, `-pull`, `none` = zero draft, `split` = the parting line crosses it), `surface`, `exact`, `depth_mm`, `xyz`, `feature` (`wall`; `rib`/`snap`: a rib's side, judged by `molding.rib_draft`; `undercut`: a face an undercut traps, formed by its release, judged by the undercut rules) |
| `undercuts` | trapped features and what releases them | points on every face shot along the way their face opens (zero-draft: both ways); blocked = trapped; a point on another solid of the same part (two solids touching, not fused) is no surface and never trapped; touching trapped faces = one group, split where its trapped points lie apart (three sample spacings): two snaps under one lid are two features. Release: rays along 8 slide directions in the parting plane + the feature's mean lateral normal + each tilted 45 deg (angled slide); fewest slides covering it (each point assigned to its shortest stroke); else a lifter (short lateral move then a pull, stroke <= 1/4 part size); else a collapsible core (each point freed radially, no common direction); else `none`. Depth (`meshops_molding.interference`; against the pull at 48 of the feature's tested points, against a slide at all of them, searched up to 0.2 mm -- past it, "more than"; a pull only ranked, not chosen, has no depth against it): per point the least offset square to a way out (its normal's part square to it, or 8 round it) from which a ray along the way leaves the part, the material between bent past; `depth_mm` against the straight pull for every feature (`depth_limited` where 1/4 part size frees none), `slide_depth_mm` against the best slide for one nothing releases. A feature `depth_mm` at most `BUMP_OFF_MM` (0.1 mm, text-to-cad's own figure: Protolabs gives none) deep, or one nothing releases whose lip against a slide is, is `bump_off` (`bump_off_over` the pull or a slide, `interference_mm`) | `location` (the mostly-trapped face), `faces`, **`trapped_area_mm2`**, `kind` (external/internal), **`release`** (side_action/lifter/collapsible_core/bump_off/none), `leaning` (its faces), **`depth_mm`**, `slide_depth_mm`, `interference_mm`, `side_actions` (`+x`, ...), `side_action_count`, `angled`, **`stroke_mm`**, **`height_mm`** (along pull), **`width_mm`**, `blocked_by`; scalars: `candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `collapsible_core_count`, `bump_off_count`, `unreleasable_count`, ..., `trapped_faces` (the faces it mostly traps) |
| `touching` | solids of one part that touch without being fused | each sampled point stepped off its face classified in the part's other solids (in or on: a contact); parts of 2 to 24 solids | `location`, `part`, `solids` [i, j], `faces`, `contact_area_mm2`, `xyz` (present only where some touch) |
| `thickness` | the wall: nominal, thin, thick, transitions | rolling ball: at each sampled point the diameter of the largest ball tangent there that no surface triangle cuts into (exact per triangle: corners, edges, insides; a needle's inside -- a triangle narrower than a thousandth of its longest side, a tall corner strip's tessellation, whose plane is its corners' rounding -- left to its edges: one held a 0.015 mm ball under a 2 mm wall), capped by the exact ray straight through. Points whose ball is held by a face across a convex edge read low and are left out of medians; a narrow face -- most of its balls so held (rib top, plate end) -- takes its broad neighbours' wall, a face merely narrow reads its own. The 32 thinnest faces are then refined to the exact least distance to a face across (`BRepExtrema_DistShapeShape`; the faces whose box comes nearer than the face's least sampled wall, not its neighbours or a face sharing a corner), where the segment leaves the face within 45 deg of its inward normal, the face across looks on along it and a ray along it meets that face first: a 0.6 mm wall between two samples (a cut grazing a drafted corner) reads 0.6, never its neighbours' 2. The faces whose thickest sampled ball reaches 1.2 x nominal and is under the thick-section limit -- where the verdict could turn -- (32 at most) have that thickest refined over the face: a pattern search over its own (u, v) from its two thickest samples, their trials solved together against the face's neighbourhood, a step halved where none gains 1% of nominal, settled at a hundredth of the face's span or once a ball reaches the limit, trials strictly inside the face and no ball held across a convex edge of it, solved as the samples are -- four alike blind-hole floors read their true 4.0 in every placement (sampled: 2.6 to 3.1, the thick-section count 2 to 5) | `location`, **`thickness_mm`** (area median, or the refined least where thinner), `min_mm` (p10, or the refined least), `refined`, `max_mm`, **`ratio_to_nominal`** (max / nominal), `thin_ratio`, **`feature`** (`wall`, or `rib`/`snap`/`boss`: a feature's face, judged by its own rules, not the wall's range), `xyz` (the thickest point); scalars `nominal_mm` (area median of the faces' walls), `min_mm`, `max_mm`, `ratio_max_nominal`, `thick_sections` (> 1.5 x nominal) |
| `transitions` | abrupt changes of wall | read on the stepped side (`meshops_molding.steps`): two flat faces facing the same way at two offsets, joined by a chain of at most three faces none parallel to them (a pad's side, a chamfer, a fillet), whose walls differ by a quarter of the nominal or more and by about their offset (one face behind both: not a rib's top, not a wall's rim); its run is the chain's reach across, square to the faces, from one seam to the other. A free-form face no step takes in: the rolling ball's steepest pair of points within four sample spacings whose walls differ by half the nominal (`basis` `ball`) | `location` (the chain's first face), **`transition_ratio`** (run over the change: a vertical step 0, a chamfer its run over its rise), `min_mm` and `max_mm` (the two walls), `change_mm`, `length_mm` (the run), `basis` (`step` or `ball`), `xyz`, `at_xyz` (a point on each seam) |
| `ribs` | thin slabs standing on a wall | two opposite planar faces (within 12 deg) whose inward rays come out of each other, both meeting one base plane at a concave edge or a concave fillet, height >= thickness, length >= 1.5 x thickness; base = the plane it is shortest from. Its ends (faces joining both sides, no wider than the rib) are its roots too: their fillets are the rib's, not corners, and `base_fillet_mm` is the least of sides' and ends'. A rib a trapped face touches (one of its own, or one beside them no larger than its side, not its base) is a snap arm, the face its barb. | **`kind`** (`rib`, `snap`), `barb`, **`thickness_ratio`** (root / base wall), **`height_ratio`** (height / wall), **`height_to_thickness`**, **`base_fillet_ratio`** (fillet / rib), **`base_fillet_wall_ratio`**, **`gap_to_thickness`**, **`gap_to_wall`** (gap = median ray to the next face), **`draft_deg`**, `thickness_mm`, `height_mm`, `length_mm`, `base_fillet_mm` |
| `bosses` | cylindrical stands, cored or solid | a convex cylinder, or a cone drafted 5 deg or less, standing on a plane square to its axis (concave edge or fillet), with the largest coaxial concave cylinder or cone inside it reaching half its height; radii at the base | `od_mm`, `id_mm`, `boss_wall_mm` (R - r, or 2R solid), **`wall_ratio`** (boss wall / base wall), `od_to_id`, `height_mm`, `height_to_od`, **`base_fillet_mm`** (its root's: 0 sharp), `hole_floor_above_base_mm` |
| `corners` | internal corners | every concave edge with no fillet (radius 0, `edge` ref) and every concave fillet with two tangent joins: a cylinder's or torus's radius, a free-form blend's from its curvature at its middle (concave where its sampled normals turn toward each other); rib (sides and ends) and boss roots excluded | `radius_mm`, `sharp`, **`ratio_to_wall`** (radius / thinner wall meeting there), `wall_mm`, `edge`, `angle_deg` |
| `projection` | area along the pull | the part triangulated (each triangle naming its face), projected, cells covered on a raster 2000 across the part | per part: **`projected_area_mm2`**, `area_error_mm2` (half the outline's cells), `raster_resolution_mm`, `depth_along_pull_mm`, `span_major_mm`, `span_minor_mm`, `volume_mm3` |
| `envelope` | size against a mold | from the projection and the parting | per part: **`span_major_mm`**, **`span_minor_mm`**, **`depth_along_pull_mm`**, **`depth_from_parting_mm`**, `volume_mm3` |
| `parting` | flat parting plane? | outline pieces within 3 cells of the projection's OUTER outline (a hole through the part along the pull is a shut-off: its rim is no parting line): edges where a +pull face meets a -pull face, zero-draft walls (the line may run anywhere up them), curved faces turning through the pull (sphere centre, horizontal cylinder axis, ...); undercut faces left out (a slide forms them). Flat when every edge/turn is level at one height every wall spans | scalars `flat_parting_possible`, `parting_plane_height_mm`, `parting_plane_range_mm`, `depth_above_mm`, `depth_below_mm`, `depth_from_parting_mm`, `off_plane_count`; items: `kind`, `low_mm`, `high_mm`, `on_plane` |
| `clamp` | clamp force estimate (added by the type side) | area (in2) x factor (tons/in2, Moldminds by resin; unknown: 2-5, estimated at 3) x cavities x 1.15 | per part `tons`, `tons_low`, `tons_high`, `kN`, `tonnes`; `factor_source` |
| `pulls` (`--candidates`) | x, y, z and the principal axes ranked (`molding.ranked`: fewest unreleasable, least undercut area, fewest side actions, least zero-draft area -- areas within a hundredth of the largest wall tie -- then the most draft at its least, a flat parting first); `pull_check` holds the same where the pull looks wrong (below), for the hint | the families above per axis (fewer samples) | `undercut_candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `unreleasable_count`, `zero_draft_wall_area_mm2`, `min_wall_draft_deg`, `flat_parting`, `projected_area_mm2`, `depth_from_parting_mm` |

Kept from today's report: `draft` scalars (`wall_area_mm2`, `zero_draft_wall_area_mm2`, `largest_zero_draft_faces`,
`min_wall_draft`, `wall_draft_histogram_mm2`, `wall_area_by_opening_mm2`, ...), `undercuts` scalars
(`candidate_area_mm2`, `largest_candidate_faces`; `unintersected_rays` and
its note where the kernel failed to intersect a ray with a face -- that crossing is not found, the family is
measured all the same), `projection`, `scale`. Fact findings: `zero_draft_walls`,
`undercut_candidates` (now with feature counts; both **info** sums of what the rules judge per face and per
feature, each naming the rule that judges it -- warnings only where they say the pull may be the wrong one),
`solids_touching` (warning: names the part's solids that touch and says to fuse them; their contact is
left out of draft and undercuts, and the part's `several_bodies` is then not said),
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
| `molding.draft_min` | draft_deg min, a wall's face (a rib's sides are `rib_draft`'s, a face an undercut traps its release's) | 0.5 warning (Protolabs' table: "VERTICAL FACES 0.5°", "MOST SITUATIONS 2°"; only its shut-off and texture rows are labelled MINIMUM, so it is a recommendation) |
| `molding.draft` | draft_deg min, a wall's face, as draft_min | 2 warning (Hubs "A minimum draft angle of 2° is recommended."; Protolabs "Most situations: 2°"; Hubs' 1-2 deg is a textured face's extra) |
| `molding.undercut` | trapped area, release side_action/lifter/core; says its leaning faces and depth against the pull | warning (Hubs) |
| `molding.undercut_bump_off` | trapped area, release bump_off; says the lip's depth | warning (Protolabs' bumpoff tip: a flexible resin, TPE, unfilled PE or PP, over a ramped or rounded leading edge; the 0.1 mm depth is text-to-cad's own figure) |
| `molding.undercut_unreleasable` | trapped area, release none; says its depth against the pull and its best slide, over 0.1 mm | error |
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
| `molding.inside_corner_radius` | ratio_to_wall min 0.5 | warning (Hubs); the hint gives the radius in mm (half the wall) |

No rule judges a press or a mold: its projected area, its largest part, its depth from the parting line,
its shot volume and its side actions' travel are a shop's, read against the measurements (`projection`,
`envelope`, `undercuts`' strokes) and the clamp estimate.

The wall table by resin (Protolabs', in inches, converted to mm): ABS 0.045-0.140, acetal 0.030-0.120, acrylic 0.025-0.500,
LCP 0.030-0.120, nylon 0.030-0.115, PC 0.040-0.150, polyester (PBT, PETG) 0.025-0.125, PE 0.030-0.200,
PP 0.035-0.150, PS 0.035-0.150 PPS 0.020-0.180, polyurethane 0.080-0.750, long-fiber reinforced 0.075-1.000 (HDPE and LDPE read polyethylene's row).

### What it cannot measure

- A mesh at all (STL, 3MF, GLB): refused, check its STEP or model. A free-form fillet's radius is read at its
  middle (a variable one reads one figure).
- Texture draft (no texture option), tall-feature extra draft (Hubs +1 deg / 25 mm over 50 mm), shut-off
  draft (3 deg), stripping undercuts (lead angle, 5% of diameter), a snap's barb, living-hinge proportions,
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
points (within a fiftieth), the first in the candidates' order is taken, +x before +y. Each part's projection
raster is read for its parting line as soon as it is made and dropped: an assembly's rasters held together were
half of a 107-part check's 1.9 GB.

## 3D printing

### The check

`cad <type> dfm --process printing` (`cad.step.dfm(..., process="printing")`,
`cad.build123d.printing(shape, ...)`) measures a part as it stands on the plate (its lowest point, Z up) for one
technology: `--technology fdm|sls|sla|mjf|pbf` (default `fdm`; `pbf` is metal powder bed fusion, DMLS/SLM).
Options: `--build-volume XxYxZ` (mm, the printer's; default a typical machine of the technology's, assumed), `--angle-limit` (deg from
horizontal; default the technology's: FDM 45, SLA 19, metal 45, SLS/MJF 0), `--layer-height` (mm; default FDM 0.2,
SLA 0.1, SLS 0.1, MJF 0.08, metal 0.03), `--nozzle` (FDM's only), `--samples` (rays, default 2000), `--material`,
`--candidates`. A material of the other class from the technology's is refused, the command line's mistake (exit 2):
metal powder bed fusion (`pbf`) prints a metal, the others a plastic (`--material aluminum` with `fdm`, `pla` with
`pbf`), as molding refuses a metal.

A STEP, an xbf or a document id is measured on its exact geometry (B-rep), every item at a face ref
(`bracket/face 7`, resolved by `cad xbf inspect`); an STL, a 3MF or a GLB as triangles, every item at `x, y, z`.
The powder processes (SLS, MJF) need no support: their overhangs are facts, never verdicts, and trapped powder is.

### Families (`measurements.<family>`)

Every family with features is `{"items": [{..., "location": ref, "xyz": [x, y, z]}], "count": n, <scalars>}`,
items worst first, at most 300. A family that fails is `{"error": "..."}` and is named in `partial_sections`.

| family | exact geometry (B-rep) | mesh |
| --- | --- | --- |
| `solid` / `mesh` | per part: `solids`, `shells`, `closed`, `inner_shells`, `sound` (the kernel's boolean-argument check, `issues` its BRepCheck codes and `BOPAlgo_CheckStatus` names -- `BOPAlgo_SelfIntersect` --, `faulty_faces` every face it names, a faulty edge's or vertex's faces too; the finding says them all), `volume_mm3`; scalars `body_count`, `volume_mm3`, `watertight`, `sound` | `mesh`: read and cleaned (`cad.trimesh._mesh`: welded, collapsed triangles, doubled slivers and zero-area debris dropped, folds laid flat -- two triangles side by side in one plane wound against each other, an exporter's fan folded back over a concave boundary, the planar region triangulated again from its boundary, `folds_laid_flat`; a mesh with none is not changed --, a tessellation's cracks closed), its bodies split with no repair; `watertight` judged per body (`open_body_count`, `open_bodies` with each one's `xyz` and `boundary_edges`), `volume_mm3` the closed bodies', `body_count`, ... |
| `overhangs` | per down-facing face off the plate: `angle_deg` (a plane's exactly, a curved face's least over its samples), `area_mm2`, `area_below_limit_mm2`, `height_mm`, `kind`: `slope`, `bridge`/`cantilever`/`ceiling` (a flat face, see `bridges`), `hole` (a hole's arch), `plate_edge` (a round or chamfer on the plate's edge whose under-limit part is within 1 mm / 5 layers of it); `reach_mm` (a flat face's, from `bridges`); `counted`: false for a face too small to need support -- under `OVERHANG_AREA_MM2` (1 mm2) below the limit, or a cantilever reaching less than the nozzle's width (`--nozzle`, else `OVERHANG_REACH_MM`, 0.4 mm) -- which no rule judges (both floors text-to-cad's own: no guide states them, and the family's `method` says so); an angle within 1e-6 deg of the limit is at it (`ANGLE_EPS`: a kernel's 45 deg chamfer reads 44.999999999999936); scalars `down_facing_area_below_limit_mm2` (the counted faces, holes, bridges and plate edges aside), `area_floor_mm2`, `reach_floor_mm` | connected regions of the counted triangles, same fields and floors; a region that reaches the plate, or runs on into down-facing triangles that do (a round's lowest row), and stays within the plate band is `plate_edge`; `down_facing_area_below_limit_mm2` counts the counted regions, bridges and plate edges aside, as the exact path does |
| `bridges` | flat (< 5 deg) down-facing planes: `kind` `bridge` (the farthest point lies within the convex hull of its supports: `length_mm` = twice the farthest distance to a supporting edge = the span between the walls), `cantilever` (beyond one support: `length_mm` = its reach), `ceiling` (none); supporting edges are the concave edges whose other face descends. A horizontal hole's arch is no bridge (each layer stands on the one below but the crown's): `printing.horizontal_hole` judges its diameter | the flat regions and any region carried on both sides (a hole's crown among them: a mesh has no axes) |
| `wall_thickness` | per face, the thinnest exact ray into the material from its samples, `sampled: true` (a face's thinnest sample, which can read above the exact least thickness between samples: a keycap's 0.6129 against 0.5493). A ray counts where the face it lands on looks back along it, its normal there within 45 deg of the ray (`KNIFE_DEG`), whether or not that face shares an edge with the ray's own: past it the ray measured a corner (a rim whose sides meet at 50 deg reads alike on both paths, and a sharp 50 deg tip as the same tip blunted by 0.0001 mm). One landing on a face that shares an edge with its own within `SEAM_HIT_MM` (0.05 mm) met the seam and is dropped; a ray inside a knife edge's `thin_depth_mm` that starts or lands on one of the knife's two faces (its flanks) is that knife's sliver -- from a flank, or from a face meeting them at the knife's end across to one -- reported by `knife_edges` alone, while a ray near it between two other faces (a fin beside the knife, across itself) measures its own wall; pins are the pins' rules'. The listed items under 5 mm are refined to the exact least distance to the face across (`BRepExtrema_DistShapeShape`, `brep.least_segments`, as CNC's are) where it leaves the face within 45 deg of its normal, the face across looks back along it within 45 deg and an exact ray along it meets that face first: `refined` true, `xyz` the thinnest point (faces sharing an edge or a corner, parallel planes and faces of over 16 edges keep their sampled figure); `min_mm` is the thinner of the field's and a refined item's. A face turned exactly 45 deg from a ray is at the limit, not past it (`ANGLE_EPS`), as is a knife edge's 45 deg: a 45 degree gusset reads the same in every placement. `thickness_mm`, `opposite`, `supported` (joined to the part on 2+ sides: the face's or its opposite's concave edges, smooth joins into a concave round, or a closed ring), `joined_sides`; scalars `min_mm`, `p05_mm`, `p25_mm`, `median_mm`, `max_mm` | per body, `--samples` rays from points at random over the surface, and on a mesh of at most `COVER_MAX_TRIANGLES` (5000) triangles one more from every triangle's centre (`cover: true`; on 60 real meshes the pass cost 26 times the family's time and found 3 thin places against 9 that are not there, while under 5000 triangles it found a knob's 0.27 mm web 2000 random rays miss, with no false one), each measured from the surface (its origin's `NUDGE`, 1e-4 mm off its triangle, added back: a 2 mm wall reads 2, as the gaps' rays do); a ray counts where it lands on a face turned toward it (within 45 deg) and is no knife's sliver: inside a knife's thin depth, starting or landing on one of its flanks (the triangle's normal within 20 deg of a flank's, `FLANK_DEG`). Items one per face of the part (triangles joined by edges whose normals turn under `FACE_DEG`, 30 deg) and the face its thinnest ray lands on -- one fin is one item, read from its two sides, as on exact geometry --, `supported: null`, `chord_mm` (how far its thinnest ray's length may be off the wall the mesh stands for: at each end of the ray the surface's offset from its chord, the point's Phong projection onto its triangle's corners' tangent planes halved -- exact to second order at a chord's middle -- each corner's normal its surface's, the faces about it turning under 30 deg; the two ends' offsets summed with their signs, so a tube's concentric rows of chords, one convex and one concave, cancel where they lie alike; 0 on planes), `at_limit` (the type side's: under `printing.wall`'s limit by no more than `chord_mm`); `min_mm` .. `max_mm`, `samples_valid` and `thinnest_samples` are of the same rays as the items, per body too; `method` says which rays ran |
| `gaps` | per face, the narrowest exact ray out of the material to another face of the same part (not a neighbour, not the same hole), up to 3 mm, each pair once, refined to the exact least distance as the walls are | one ray out of every triangle to a facing wall of the same body (a hole reads as a gap), none landing on a triangle sharing a corner with its own or on a face (`FACE_DEG`) sharing an edge with its own: an acute crease inside a letter closes to nothing there, no slot, as on exact geometry; under `GAP_DEFECT_MM` (0.05 mm) faces lie on faces -- doubled or overlapping triangles, the mesh's defect -- reported once as `overlap` (`mesh_overlap`), never an item |
| `holes` | concave cylinders round one axis covering >= 250 deg: `diameter_mm`, `depth_mm`, `orientation` (vertical < 10 deg, horizontal > 80 deg, else inclined), `through`, `teardrop` (horizontal and no material within 15 deg of the top), `channel` (depth >= 5 d), `coverage_deg` | not measured (no axes) |
| `pins` | convex cylinders the same way: `diameter_mm`, `height_mm`, `aspect_ratio` | not measured |
| `details` | a side face of any surface (a plane, a round corner's cylinder, a dot's, a letter's spline) whose normals lie square to a parallel top (its convex edge) and bottom (its concave edge) at most 2 mm apart, narrower than `DETAIL_ACROSS_MM` (3 mm: text, a logo, a mark; a wider step -- a groove, a land, a ledge -- is the part's geometry), whose steps bound its raised top or its sunk floor all round (an island or a pocket; a step that runs on across a face from edge to edge -- a hinge knuckle's shoulder, a ledge -- is the part's geometry, which the walls and gaps judge): `emboss` where it is narrower through the material (the side's rays in) than across the air (its rays out), else `engrave`; `height_mm` (the step), `width_mm` (that narrower extent) | not measured |
| `clearances` | each pair of parts within 5 mm: exact `distance_mm` (BRepExtrema), `kind` `gap`/`contact`/`overlap` (`overlap_mm3` by boolean), `parts` | each pair of bodies (inside-out void shells and slivers dropped): closest points of vertices and triangle centres |
| `trapped_volumes` | cavities: every solid's inner shells exactly (`exact: true`, volume from the shell), and from a voxel field (<= 1.5 M voxels) the air a ball of r = clamp(0.2 x smallest side, 3 voxels, 6 mm) cannot reach from outside (open hollows) and sealed pockets; `sealed` (a voxel pocket under 8 voxels, `POCKET_MIN_CELLS`, is the voxelisation's and dropped), `escape_holes` (each run of an exact hole along its axis with one end in the cavity and the other outside -- one cut through two opposite walls is two holes -- plus voxel openings no hole explains), `escape_hole_diameters_mm`, `min_escape_hole_mm`, `min_wall_mm` (the wall samples whose outside lies in the cavity), `volume_mm3` | the voxel field alone; opening widths estimated ((2 depth + 3) voxels); on a mesh with an open body a cavity's openings may be the mesh's own holes, so `sealed`, `escape_holes` and their sizes are not measured (None, `openings_not_measured`) and the escape-hole rules read so, never a count of 0 or a 0.53 mm "hole" |
| `knife_edges` | convex edges whose material angle, read along the edge (`brep.edge_angles`: a curved edge at 17 points, its least then found between the samples either side by golden-section search -- a rod cut 25 deg off its axis reads 25.0 on every technology --, then every quarter of its thin depth; an edge where a cone meets a sphere runs from 63 to 42 deg), falls under 45 deg (`knife_below_deg`): `location` the edge ref (`lip/edge 14`), `faces`, `angle_deg` (the least), `length_mm` (the stretch under 45), `edge_length_mm`, `thickness_mm` 0, `thin_depth_mm` = min wall / (2 tan(angle / 2)) (how far in the material stays under the rules' unsupported-wall minimum, `min_wall_mm`; at most `THIN_DEPTH_CAP_MM`, 10 mm, past which the sliver is a fin the walls read; none under `FOLD_DEG`, 2 deg), `thin_area_mm2`. Why 45: that depth is half a wall at a 90 deg corner (one bead), 1.2 walls at 45, 1.9 at 30; 45 deg is also the guides' self-supporting chamfer. The sliver is the knife's alone: the walls drop the rays inside each stretch's `thin_depth_mm` that start or land on its two faces. A tip at the limit (45 deg within `ANGLE_EPS`) is such a zone too, though no knife, so 44 deg is a knife and 45 and 46 nothing, never a thin wall; and a curved edge's stretch over the limit up to `ZONE_DEG` (90) drops the rays from one of its faces onto the other within its thin depth (its faces curve, so such a ray can look back: a tip's own sliver is never a wall, as a 46 deg wedge of two planes reads none) | convex creases between triangles of material under 60 deg (`CREASE_DEG`) and at least `FOLD_DEG` (2 deg: a sharper crease is a fold of the tessellation, two triangles doubled back, whose depth would reach anywhere -- a 0.227 deg one on a watertight shin wiped every wall ray within 201 mm), chained by shared corners; a chain is a knife where its angle, its creases' median by length (as the exact path reads an edge at its middle: a curved 41 deg edge meshes as creases of 4 to 58 deg), is under 45 deg and it is at least as long as its thin depth (a shorter one is a sliver triangle's crease); same fields at `xyz`; a chain at the limit is the walls' zone, no knife. The walls leave each crease's own sliver to it: every crease its thin depth at the angle of the creases within the chain's depth of it (their median by length), so a curved knife running from 25 to 60 deg is as deep at its tip as its 25 deg says |
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

`not_watertight` (an error, mesh and B-rep: an open surface has no inside to print, and every figure of it is
suspect; on a mesh it names the open bodies), `not_sound` (an error: the kernel's validity check fails),
`several_bodies`, `overhangs` (the sum of the down-facing area: info where `printing.overhang_angle` judges each face
-- FDM, SLA, metal, at the angle limit used -- and for powder, a warning only where no rule judges them; with a hint, and on an assembly the sentence that the parts are measured as printed together, in place,
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
Every figure a rule judges is kept to 1e-9 (`meshops_printing.JUDGED`), never rounded before the comparison: a
0.79996 mm wall is under 0.8 mm.
Sources (accessed 2026-11-03): hubs-thin-walls, hubs-geometry, hubs-fdm, hubs-sla, hubs-sls, hubs-mjf, hubs-metal,
protolabs-toolkit, protolabs-metal, protolabs-7mistakes, xometry-fdm, xometry-sla (Xometry Pro SLA quick reference),
xometry-3dp, xometry-guide (Xometry Pro design guide) -- URLs in `cad._internal.dfm.printing.SOURCES`.

| rule id | family.field | op | limit (fdm / sla / sls / mjf / pbf; source) | severity |
| --- | --- | --- | --- | --- |
| printing.wall_supported | wall_thickness.thickness_mm (supported) | min | 0.8 / 0.5 / 0.8 / 0.7 / 0.4 (hubs-thin-walls) | error |
| printing.wall_unsupported | wall_thickness.thickness_mm (not) | min | 0.8 / 1.0 / 1.0 / 1.0 / 0.8 (hubs-thin-walls) | error |
| printing.wall | wall_thickness (mesh, supported unknown) | min | as supported | error; a warning where the wall is under the limit by no more than the mesh's chords may depart from the surface there (`chord_mm`, `at_limit`: at the limit within the mesh's accuracy) |
| printing.hole_diameter | holes.diameter_mm | min | 1.0 (xometry-fdm, warning: "to retain a circular shape") / 0.8 warning ("may close off") and 0.5 error (its table's minimum) (hubs-sla) / 1.5 (hubs-sls) / - / 1.5 (hubs-metal) | error* |
| printing.pin_diameter | pins.diameter_mm | min | 1.0 (xometry-fdm-tips, warning: "Pins should be at least 1 mm in diameter and kept as short as possible."; Hubs FDM gives none) / 0.5 (xometry-sla) / 0.8 (hubs-sls, warning: "recommended") / 0.5 (hubs-mjf, warning) / 0.6 (hubs-metal) | error* |
| printing.pin_aspect | pins.aspect_ratio | max | pbf 8 (hubs-metal) | warning |
| printing.overhang_angle | overhangs.angle_deg (slope, ceiling, cantilever; metal also bridge; `counted` only) | min | `--angle-limit` where given (the printer's own self-supporting angle, as `--tools` is a shop's cutters); else fdm 45 (hubs-fdm), sla 19 (hubs-sla), pbf 45 (protolabs-metal: Hubs metal lists 50 deg, its reference axis unstated, so the rules keep Protolabs's 45) | warning |
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
warnings (a recommendation, a risk or a general line), the rest errors. FDM's pin row is Xometry's FDM design
tips' (accessed 2026-11-08), a "should": a warning.

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
  (`solid.items[].check`). A part with a free-form face of more than 2000 control points (`SOUND_POLES`; a surface
  swept or offset from a B-spline counts its basis's: a revolved curve's poles by nine, an extruded curve's by two)
  is checked edges against faces, not faces against faces (`check: "boolean_edges"`): the kernel's face/face search
  between a large B-spline and a face meeting it tangentially ran for over three hours on a 3-face part, and no
  kernel call can be stopped. A self-intersection that crosses an edge is still found; two faces crossing inside
  both, on such a part, are not. A part read sound by either bounded check is said (`soundness_bounded`, a warning
  naming the parts and the stage not run), never a plain pass.
- Voxel fields: each part's field dropped once its trapped volumes and sections are read (an assembly's fields
  held together were most of a 1.8 GB check), and every flood of it reaches a checkpoint each sweep.
- A flat ceiling the kernel lays no sample on is said not measured (`bridges.items[].unmeasured`), its rules'
  figure missing, never a crash of the family.
- Flat ceilings: the 40 largest refined to the exact farthest point; the rest read on their samples (`refined`).
- A mesh: each overhang region spread over about 3000 points (`meshops_printing.spread_points`: rows from a
  facet's sharpest corner, as wide as each row needs, so a strut's sliver is sampled along its length) and its
  span read by matrix products in blocks (`_least_distances`); every ray cast 1000 at a time (`RAY_BLOCK`).
  A 100k-triangle open lattice (FDM) took 137 s and 7.3 GB, now 14.5 s and 1 GB, its findings the same.

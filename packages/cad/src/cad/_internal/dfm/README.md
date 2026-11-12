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
exit 2). The geometry both integrations share is numpy alone (`cad/_internal/meshops_printing.py`, a triangle
mesh's measures): numpy is the library's one required dependency, so neither integration imports the other's.
Molding's and a sheet's plane geometry are numpy alone too (`cad/_internal/molding_geometry.py`,
`cad/_internal/sheet_plane.py`), measured with by the build123d integration alone.

**Where exact geometry is measured.** In the engine's checks processes: the caller resolves the options
(`manufacturing.options`) and asks the engine (`cad.engine.api.check`, an `export` carrying a `check` and the
caller's release), which answers the report, which the caller finishes into its result (`manufacturing.finish`).

- One of the engine's checks processes measures it when the server's library is the caller's (its release, code
  and libraries): a STEP's or an xbf's file, read once while its bytes stay as they were (by their digest, four
  files at most), or a document the engine holds, a model's, from its bytes, read once per version. They are a
  small pool of warm kernels of their own, never a model's worker, so checks of different documents run at once,
  a build or an inspection of a model waits for no check of it, and a long check or its crash costs no document
  anything.
- Otherwise it is another library's check, answered at once with no report. A file is then measured by its
  caller (in a process of its own, held to a check's limits: below), a model's document exported by the engine
  and read back there; a command whose environment holds no kernel sends either to the base's environment. So is
  a file where no engine can be reached. One line on stderr says so: nothing keeps such a check, so it is
  measured again each time.

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
`no_kernel`, `superseded` and `error` (the measuring raised). A model built again while a check of it runs
stops that check as the build registers -- its process killed, so it holds neither a slot nor its caller for a
result of a version that is gone -- and the check is asked again of the model as it is now for the callers still
waiting, who get that result; `superseded` is the answer only where the model is built again under each of three
tries (or a file is rewritten each time it is read), or no caller is left to ask it for. A run of a model's
script that changes nothing, or a build of another model, disturbs no check.

A mesh and a DXF are measured by their caller (or in the integration's environment) always, and so is a file
where no engine can be reached: in a process of its own that the caller starts and holds to the same limits from
outside (`manufacturing._watched`: `CAD_ENGINE_CHECK_SECONDS` and `CAD_ENGINE_CHECK_RSS_MB`, the same defaults,
read each second), since a kernel call that never returns can be stopped from nowhere else; the process ends
with its caller, so one a shell's time limit killed leaves nothing measuring. Past a limit the check is
`not_checked` with the engine's reason for the same (`over_time`, `over_memory`); a process that exits with no
answer is `process_lost`, and a measuring that raised is `error`, in one line. A mesh is read
and cleaned (`cad/trimesh/_mesh.py`): corners at one place welded into one
vertex, a triangle two of whose corners became one dropped (it opens nothing), a sliver (under 1e-8 of the
diagonal squared) on an edge more than two triangles use dropped where its edges stay used once each way or
not at all (an exporter's collapsed chord left doubled or fanned over an edge; never one that closes the
shell), a connected piece of no area dropped, and a boundary loop within 0.2% of the diagonal of one straight
line -- a tessellation's crack -- filled, wound as its neighbours; a wider hole is the part's opening and stays
open. Watertightness is judged per body (`open_bodies`: an edge used an odd number of times), the volume the
closed bodies'; two bodies sharing a face are each closed. Printing splits the bodies with no repair: a piece
with no boundary has the faces another body shares filled in, a piece with one stays open.

A check measures the inside of a surface, so one gate stands ahead of every family (`_mesh.readable`,
`_mesh.sound`) and a mesh with no inside is refused there, one finding, never a family's exception: no triangles,
or none with an area (`mesh_empty`); a corner that is not a number (`mesh_unreadable`); more than
`MAX_TRIANGLES` (2 000 000: `mesh_too_large`, see the budgets); triangles no winding makes consistent, a
one-sided surface (`inconsistent_normals`); a closed surface that encloses no volume, a sheet doubled back
(`mesh_no_volume`). What is unambiguous is repaired and said (`mesh_repaired`, a warning: a slicer reads the file
as it is): a triangle doubled in place and wound the same way dropped, triangles wound against their neighbours
turned to agree across every edge two triangles share, and a closed shell wound inside out turned -- unless it
lies inside another shell's material: a sealed void's shell faces inward, and stays.

**Verdicts.** The type side (this folder, the standard library alone, so the command resolves every option
before it starts an environment) holds each process's options, its rules, the findings its facts call for
and its summary line (`cnc.py`, `sheet.py`, `molding.py`, `printing.py`). Each process has **one table of
rules** (`RULES`, a `rules.RuleSet`: versioned, each rule a limit on one measured field with its source,
`rules.py`), and the checks are **general**: a rule states general practice, and the published design guide
it cites is the evidence for it, never a target; where no guide states a limit and one physically exists, the
rule is text-to-cad's own floor, labelled as its own (its source `text-to-cad`, its reason in the rule's
note), never put in a publisher's name -- no rule is a shop's capability (its gauges, its tooled
radii, its machines' sizes, its press). Every verdict names where its limit comes from (its `source`: the
guide's publisher and title, or text-to-cad's own where no guide states one), and every
result says the verdicts are no shop's limits (`rules_general`, info). A shop's own limits are compared with
the measurements, which every result carries (a skill for a named fabrication service does that, reading
the measurements against the service's own published specs); what a person knows of their own shop is a plain
option -- `--tools`, `--axes`, `--stock`, `--thickness`, `--bend-radius`, `--k-factor`, `--kerf`,
`--sheet-size`, `--cavities`, `--build-volume`, `--layer-height`, `--nozzle`, `--material` -- never a rule
set. A rule's id (`cnc.internal_corner_radius`) is its finding's code; its severity is `error` where the
source's number is a feasibility limit (the part cannot be made as drawn under that rule) and `warning`
where it is a recommendation ("should", "recommend"), a cost or a risk, and its note quotes the source's
sentence.

**The tables are the code's, not this page's.** A rule's id, the family and field it reads, its comparison,
its limit, its severity, its source and the source's sentence are `cad._internal.dfm.<process>.RULES` and
nowhere else: a copy here would drift from it. Every result carries the table as it judged
(`measurements.rules`: each rule's outcome, its limit in this part's context, and the sources with their
URLs), and it prints as written:

```
python -c "from cad._internal.dfm import cnc
for r in cnc.RULES.rules: print(r.id, r.severity, f'{r.family}.{r.field}', r.op, r.limit, r.source, dict(r.when), dict(r.item_when))"
```

What follows for each process is what its table does not say of itself: how its figures are measured, what
its limits follow, what no rule judges, and its findings of fact.

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
range. What the command line writes out as text a Python caller may give as numbers
(`manufacturing._spelled`: `tools=[3, 6]` or `tools=6`, `stock=(100, 60, 25)`, `build_volume`, `sheet_size`,
`pull=(0, 0, 1)`), and a material is taken by its name as a person writes it (`_material`: the table's name
or an alias, else the longest run of its words that is one -- `Aluminium 6061` is aluminum, `stainless steel
304` stainless). A value in range that no machine has is refused too (`_plausible`): an end mill over 100
mm across, an FDM layer taller than its nozzle (0.4 mm unless `--nozzle` says), a powder or resin layer over
0.5 mm -- text-to-cad's own bounds, there because such a value would judge the part against nothing. `units`
is an STL's, and a DXF's (one that declares none is not checked without it): a type that always declares its
units takes no such option. A refusal names the command line's
flag (`--tools is ...`), and to a Python caller the parameter (`tools is ...`: `manufacturing.parameters`;
the command calls the same function with `_command=True`, a keyword of its own in no signature).

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

A `cad.results.CheckResult`: `status` and `ok`, `reason`, `findings`, `summary` and `measurements`, the
report.

**Three states** (`status`; `manufacturing.finish`), each the command's exit status:

| `status` | exit | when |
| --- | --- | --- |
| `ok` | 0 | every part and family was measured and no finding is an error. Warnings are recommendations: the part is made, at a cost or a risk |
| `failed` | 1 | a finding is an error -- a rule's feasibility limit broken, a process's own error (`cnc.no_turning_axis`, `sheet.not_sheet`), `not_watertight`, `not_sound` -- or, with `--strict` (`strict=True`), a warning |
| `not_checked` | 3 | the check did not judge what it was asked to: no verdict, never a pass. `reason` is the code of the finding that says so |

`ok` is true for `ok` alone. What makes a check `not_checked` is one of two things:

- **the whole check**, which measured nothing (`dfm.Unmeasured`, the result's one finding): the source does
  not read (`document_unreadable`, `mesh_unreadable`), is not there (`invalid_target`; the command refuses
  one first, exit 2), holds no part with a face (`document_empty`) or no closed solid (`not_solid`), needs
  exact geometry it has not (`needs_exact_geometry`), or its report holds a figure that is no finite number
  (`not_finite`);
- **a part of it** (`manufacturing.NOT_CHECKED`, whatever the finding's severity): a family that could not
  be measured (`measurement_failed`: the family is `{"error": "..."}` and named in `partial_sections`, or the
  report lacks it where a rule that applies reads it), faces the kernel failed to intersect rays with
  (`rays_unintersected`: a family's `unmeasured_faces`, so its rules are `partial` or `not_evaluated` there),
  a rule whose items carry no figure that should have been measured (`rule_partly_judged`: its `refs` are
  those features, said once for the features several rules leave unjudged), or rules that judged nothing at all
  (`rules_none_evaluated`).

So a process's module marks what it did not measure through the report alone: raise `Unmeasured(code,
message)` for the whole source, answer `{"error": ...}` for a family and name it in `partial_sections`,
list a family's `unmeasured_faces`, or leave an item's figure `None`.

**Does not apply is not "not measured".** A `None` is never both. A figure that cannot exist of an item is
named in the item's `not_applicable`, a list of its fields (`_common.not_applicable`, set where the type side
annotates its items before the rules read them: `cnc._mark`, `sheet._mark`, `molding._hint_fields`,
`printing._at_limit`), and a rule that reads it asks nothing of the item: an open step or shoulder has no
opposite wall, so no width to be deep against; a sharp corner, or one no tool given fits, has no tool whose
reach to judge; a part with no axis of revolution has no turned diameter; a lone rib has no gap to a
neighbour; a hem's flange has no outside mold line; a sealed cavity has no escape hole to size; a cut file
given no `--thickness` has none. Where an item's own field tells them apart the rule leaves them out by
`item_when` (a part that is no sheet has no flat pattern). A family a source does not hold by its nature is
the report's `not_measured`, `{family: why}` -- a mesh's `holes`, `pins` and `details`, a cut file's `bends`,
`reliefs`, `hems` and `not_sheet` -- its rules `not_evaluated` with that reason, and the result says so once,
as a fact (`families_not_measured`, info, listing the rules that judge nothing): the check stays what the
rest makes it. An error found wins over what was not checked -- `failed`, exit 1, its
line saying `; not checked: <code> xN` too: the part fails whatever else was not judged. The command also
exits 3 for a check that did not run to its end -- the engine stopped it (its document changed under it, it
went past its time or its memory), lost its process or stopped itself, the integration's environment gave no
answer, the check crashed -- never 1, which
says the part fails: under `--json` the failure's document, `{"ok": false, "error": ..., "status":
"not_checked", "reason": ...}`, the reason the engine's own where its error carries one (`error.reason`),
else `engine_stopped`, `engine_failed`, `engine_unavailable` or `failed`; without, its words on stderr and
`NOT CHECKED <source>: <reason>` on stdout. A library call raises those as it did. Exit 2 stays the command
line's mistake.

**A finding** is a severity, a code, a message, a location and a `hint` saying what to change. A rule's
verdict is one finding for each feature that fails the rule, and carries the verdict as data, so nothing is
read out of its message:

```
{"severity": "error", "code": "cnc.internal_corner_sharp", "rule": "cnc.internal_corner_sharp",
 "message": "sharp vertical corner (no round tool makes it): radius 0 mm is under the 1.5 mm minimum (plate/edge 17, 10 mm tall, 10 mm below the top)",
 "location": "plate/edge 17", "refs": ["plate/edge 17", "plate/face 7", "plate/face 8", "plate/face 11"],
 "value": 0.0, "limit": 1.5, "unit": "mm", "op": "min",
 "source": "Protolabs Network (Hubs), How to design parts for CNC machining",
 "hint": "Give it a radius of at least 1.5 mm ...", "items": []}
```

`rule` is the rule's id (None, with `value`, `limit`, `unit`, `op` and `source`, for a finding no rule
made); `op` is `min` (the figure is at least the limit) or `max`; `location` is the feature's most specific
ref -- an item's `edge` (or `vertex`) before its `location`, so a corner is its edge and two corners of one
face are two findings -- and `refs` every ref the item names, `location` first, then the rest (`rules._refs`:
any field that holds a ref or a list of them). A ref is one element, as `cad step inspect DOC REF` takes it:
words that name several (`plate/face 3 and plate/face 4`, a figure written out for the message) are none, nor
is an element named without its part (`face 6`) beside one named with it. Failures of one rule at one feature are one finding, the
worst (`and N more at this ref`, each in `items`: `value`, `xyz`). Past eight features of one rule, one more
finding counts the rest (`value` None, `location` `measurements.rules`, `items` each remaining feature's
`location`, `value` and `refs`).

**The report** (`measurements`):

```
{"process": "cnc", "source": {"type": "step", "measured_as": "brep", "document": "plate"},
 "document": {"name", "part_count", "occurrence_count", "solid_count", "volume_mm3", "units", "empty_parts"},
 "bodies": [{"name", "owner", "occurrences", "paths", "placements_mm", "material", "material_table", "process",
             "bbox_mm", "volume_mm3", ...}],
 "<family>": {"items": [{<fields>, "location": "plate/face 7", "xyz": [x, y, z], "faces": [...]}, ...],
              "count": 12, <scalars>},
 "partial": false, "partial_sections": [],
 "rules": {"title", "version", "note", "context", "evaluated", "failed": [ids], "partial": [ids],
           "none_found": [ids], "failing": {"error": {id: n}, "warning": {id: n}},
           "not_measured": {family: [ids]}, "absent": {family: [ids]},
           "outcomes": [{"rule", "family", "field", "op", "limit", "unit", "severity", "source", "status",
                         "evaluated", "unmeasured", "unmeasured_faces",
                         "failures": [{"value", "location", "xyz", "refs", "item", "limit"}], "reason",
                         "variants"}],
           "sources": [{"id", "publisher", "title", "url", "accessed"}]}}
```

A failure's `location` is its item's own, its `refs` every ref the item names, the feature's first (the
finding's `location`: a corner's edge, where the item's `location` is one of its faces), its `item` the index
of its item in its family's `items`, and its `limit` is there where it is the item's own (below). `rules.failing` counts the features that fail each rule, by severity, as the
findings count them -- those past the eight shown too, a failure another finding implies left out: the one
count a summary says.

- **Locations.** On exact geometry an item's `location` is a ref in `cad xbf inspect`'s grammar -- the
  part's canonical owner and the face's ordinal (`plate/face 7`, `kit/pin.2/face 3`) -- read with the
  engine's own loader, so `cad step inspect FILE REF` and `cad xbf inspect DOC REF` resolve it to the very
  face; a feature of several faces lists them in `faces`. On a mesh it is `x, y, z` in millimetres.
- **Every part, every way it stands.** An assembly's every part is measured, and a part used several times
  -- one geometry, several occurrences: a document's instances of one prototype, a live shape's leaves that
  share a shape (`Pos(...) * part`) and a material -- is one part for each way it stands
  (`_dfm_brep._Standing`, in `read`, `of_source` and `parts_of` alike): the occurrences turned alike (their
  rotations equal to 1e-9, entry for entry: moved apart, never turned against each other) are measured once,
  where the first of them stands, and counted, named and placed on that part (`bodies[i].occurrences`,
  `paths`, `placements_mm`: how far each lies from the first); an occurrence turned another way -- a
  twentieth of a degree is another -- is a part of its own, at its own refs, measured as it stands. So what
  depends on how a part stands (a print's overhangs against the plate, a molding's draft against the pull) is
  judged for every occurrence, and nothing is judged for the first alone. `document` totals every occurrence
  (`occurrence_count`, `solid_count`, `volume_mm3`), and so does every process: a total counts a part once for
  each time it occurs (`_common.occurrences`: molding's draft, undercut and projected areas, its clamp force
  and its candidates' rows; the parts and the volume of CNC's and sheet's last lines), where a family's items
  are the features measured, each once -- but for CNC, which says every occurrence's features at the
  occurrence's own refs (below), so its items, its counts and its findings count every occurrence already. A print is the exception that needs none: its parts stand together on
  one plate, so the occurrences turned alike share neither their height above it nor what stands beside them,
  and it measures every occurrence where it stands (`_dfm_brep.every_occurrence`: each a part at its own path,
  its clearances to its copies among them). A part that is another's
  geometry moved -- an exporter's copies, a pattern written out part by part -- is found by its geometry
  (`_dfm_brep.copies`: its counts and faces' kinds alike, its volume and area the first's to 1e-6, and every
  vertex, each edge at its middle and quarters and each face at the middles and quarters of its parameters where
  the first's lie moved, ordinal for ordinal, 1e-7 of its size, by a turn and a shift -- a mirror image is no
  copy (a left and a right bracket are two parts, each measured on its own), nor are probes in one plane, which a
  mirror fits as well as a turn; never by bytes, which a copy does not keep) and, in CNC and sheet metal (each part read in
  its own frame, so where it stands changes nothing), measured once: the first's items said again at the copy's
  refs, its places and directions moved onto it, its counts counted again (`_dfm_brep.moved`), the faces the
  kernel failed on said at the copy's own too. CNC takes every occurrence as a part
  (`_dfm_brep.every_occurrence`) and measures each geometry once, however its instances are turned: a copy is
  read in the measured part's machine frame moved with it (`machine.frames`: its `axes` that frame, `copy_of`
  the part measured), so fifty instances turned alike and fifty turned fifty ways say the same features, the
  same counts and the same findings, each at its own occurrence's refs (a mirrored copy is measured anew; a
  solid of a part that holds several is a copy only of the same solid of another instance of that part). Molding reads a part against the world's pull, so it
  measures every part that stands another way; printing every occurrence.
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
  other's; one crossing both find (up to 1e-5 mm apart along the line on a torus, `SAME_CROSSING`) is taken once,
  so a count of crossings counts it once, on the face's boundary where either puts it there. Each crossing says
  whether the kernel put it on the boundary (within its tolerance of an edge or a vertex). What this keeps: every
  crossing on the face that the kernel's own intersector finds on the whole line
  (rays grazing a free-form face's edges: none lost); within the boundary's tolerance band, beyond the trim, a
  crossing is accepted as the kernel accepts it on that stretch, which may differ from its answer on the whole
  line by its tolerance. A face is read once; one whose triangulation cannot be read is not screened, and the
  full intersector answers for its whole line. A ray the kernel cannot intersect with a face (`Standard_Failure`
  on a degenerate patch), or a stretch of it near the boundary it does not finish (or the whole line, where the
  fast intersector failed on it and the full one does not finish), loses that crossing alone -- the fast
  intersector's on the rest of the line are kept -- never the family: it is counted against the face and said
  (`rays_unintersected`, a warning naming the faces: one a part, whatever casts lost it -- CNC's walls' and gaps'
  exact distances, measured after its families, and molding's pull check included), and every family whose rays
  it cost names those faces (`unmeasured_faces`), so its rules say what was not measured there (below).
  `Rays.intervals`, the stretches of a line in the material, tells each crossing by which way the line passes
  the face there (the direction against the face's outward normal at the crossing): into the material, out of
  it, or along it -- a tangent touch, within 1e-6 of the surface's plane, which is no crossing (a line along a
  torus's top passes no material; one that grazes its inner equator from inside stays inside). Crossings at
  one place (an edge's two faces, a vertex's three) are one entry or one exit where the faces agree and
  nothing where they disagree (the line touches the edge and stays on its side), and where the places do not
  alternate entry and exit the answer is None, counted (`Rays.unpaired`): unknown, never a guess. A line that
  lies in a face's own surface is read by the faces it crosses.
- **A family that failed** is `{"error": "..."}`, named in `partial_sections`, and said
  (`measurement_failed`): the check is `not_checked`; the other families are still reported.
- **Every rule id has one outcome**: `passed` (each item within the limit; with none to judge -- no hole, no
  wall under the family's threshold -- `passed` with `evaluated` 0, reason `none found`, listed in
  `rules.none_found`; an item whose `not_applicable` names the figure is no item of the rule's), `partial` (it
  judged some of its items and not the rest, which is no pass: items that carry no figure for it, reason `N
  item(s) not measured` and one `rule_partly_judged` finding naming them; or faces the family's rays could
  not be intersected with -- its `unmeasured_faces` -- each counted in `unmeasured`, named in the outcome's
  `unmeasured_faces` and its reason; either makes the check `not_checked`; listed in `rules.partial`),
  `failed` (each failing item's value, place, refs and item; items it could not judge are said all the
  same), `not_evaluated` (the rules give no limit for this material or technology; or the figure was not
  measured of any item, which `rule_partly_judged` says too; or the family was not measured: by the
  source's nature, its reason the report's `not_measured`; because it failed; or because the report lacks
  it, which is `measurement_failed` -- `rules.not_measured` and `rules.absent` name each such family with the
  rules that read it: unverified)
  or `not_applicable` (the rule is for another context -- turning, a sheet given, a cut file -- or reads a
  figure this source's items do not carry, which another rule judges). Rules that come in variants by one
  key (`RuleSet.selector`, printing's `technology`) with no variant of a rule id for the part's value leave
  that rule `not_evaluated`, not `not_applicable`: a technology the rules have no figure for is unverified,
  and a check that evaluated nothing says so (`rules_none_evaluated`) and is `not_checked`, never a
  pass. A figure that was not
  measured is never a pass. A rule's limit is the context's, times the figure it scales by (`scale_by`): the
  item's own figure of that name where it carries one (a part's own thickness, among parts of several), else
  the context's; a failure held to its item's own limit says it (`limit`). A rule id that comes in variants -- by the context (a tool given or not), by
  its items (acute or square corners), a minimum and a maximum of one figure -- answers once
  (`rules._one_per_rule`): the variants that judged are its outcome, merged where several did (`failed` if
  any failed, each item counted once, each failure with its own `op`, `limit` and `severity` where they
  differ, listed in `variants`), a variant that applied but had no limit said in `reason`; where none judged,
  the one not evaluated, else one `not_applicable` (or `not_evaluated` for a selector value the rules lack).
  The record holds every failure; the findings are fewer, what a reader acts on:
  failures of one rule at one feature are one finding (`and N more at this ref`), a failure on a figure of an
  item that already fails a rule of higher severity, or of the same severity with a limit further off (the
  recommendation beside the feasibility limit it exceeds; `draft`'s 2 deg beside `draft_min`'s 0.5) is left
  to the record, a feature another finding names as its cause is judged there alone (a process says which:
  a special cutter's recess, an undercut's trapped faces), at most eight features of one rule are findings and the rest are
  counted in one more, at `measurements.rules` with the rule's fix. Findings come in this order: what puts
  every other figure in doubt first, whatever its severity (what was not checked, `not_watertight`,
  `not_sound`, `units_suspect`: `manufacturing._FIRST`), then errors, then warnings, then the facts
  and assumptions (info).
- **Figures are judged as measured.** Every figure a rule reads is kept to 1e-9 in the report and compared
  unrounded; only a message rounds it (four figures, more where value and limit would read alike). A limit is
  its source's number exactly (`molding.thick_section`'s 1 / 0.6, not 1.6667), and the comparison's slack is
  noise alone -- a billionth of the limit, an angle's a millionth of a degree (`rules.ANGLE_TOLERANCE_DEG`: a 2
  deg wall against a pull typed to nine digits reads 1.99999999) -- so a value exactly at its limit passes.
- **The summary** is the check's last line, and leads with its state and its counts, which are the
  findings' (a rule's failing features, `rules.failing`, and every other finding once): `OK <source>:
  [N warning(s); ]<process> <what was measured>`; `FAILED <source>: E error(s)[, W warning(s)]; <process>
  <what was measured>; failed: <code> xN, ...[; not checked: <code> xN]` -- each rule that failed with its
  count, then every other error by its code (`cnc.no_turning_axis`, `sheet.not_sheet`); with `--strict` and
  no error, `0 error(s), W warning(s) (--strict: a warning fails)` and the warnings' digest; `NOT CHECKED
  <source>: <code> xN[, W warning(s)]; <process> <what was measured>`, or `NOT CHECKED <source>: <code>`
  where nothing was measured.
- **What the command prints** (`CheckResult.human_lines`): the findings, then the summary. A rule's verdicts
  are said together where the first stands -- `error: <rule>, N place(s). Hint: <what to change>. Source:
  <guide>.`, the hint and the source once, then `  <ref>: <message>` a place and, past eight, `  and N more`
  -- so a part with twelve sharp corners reads as one rule and twelve short lines; a lone verdict and every
  other finding is one line, `<severity>: <code> at <location>: <message> Hint: ...`.
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
  command refuses one first, `not_found`, exit 2), a document with no part that has a face
  `document_empty`: each `not_checked`. A document id the engine does not hold is its `NotHeld` (the
  command's `not_found`, exit 2). A part with no face beside others (an empty
  label an exporter left) is skipped and said, `empty_parts` (info).
- **Not a solid.** Exact geometry is a part of material: a part holding no closed solid of any volume -- an
  open shell, a face, a solid of zero volume -- is refused before anything is measured, `not_solid`
  (`not_checked`, as `document_empty`, its message naming each such part and what to fix), in every process.
  A part whose solid has an open shell or that holds faces beside its solids is `not_watertight`, and one
  that fails the kernel's topology check (BRepCheck) `not_sound`: errors in every process, said first
  (printing's `solid` family judges its own solids' shells and soundness, with the boolean check). A mesh's
  open body is `not_watertight` too, an error.
- **Several solids in one part** are said alike in every process, once (`_dfm_check._several`):
  `several_solids`, a warning -- a process makes a part of one solid, and the finding says how this process
  read them (molding: together, their contacts left out of draft and undercuts and listed in `touching`) --
  where `several_bodies` is several parts, every occurrence counted (molding's warning: an assembly; printing's
  info; a mesh's bodies). Where two of a part's solids share volume (their common over
  1e-6 of the smaller's) it is `not_sound`, an error naming the pairs and the volume: interpenetrating solids are
  no part, their material counted twice. Pairs are compared where their boxes meet, 256 at most
  (`solids_not_compared`, a warning, where more remain or the kernel cannot finish one); printing's own
  boolean check finds shared volume, so it is not looked for twice there.
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
  process whose verdict must not depend on the pose measures the part in its own frame (CNC's machine frame)
  and turns every place back, or rests its verdicts on what no sample turns (molding's floors: a broad wall's
  own thickness, a wall's draft against its depth).

The Python functions: `cad.<type>.dfm(path_or_id, process=..., ...)`; on a live shape
`cad.build123d.dfm(shape, process=..., ...)` -- the same options, the same `CheckResult`, refs as the engine
would name its document, with no process the one its parts declare (`cnc`, `sheet_metal`, `molding` and
`printing` are its four processes by name) -- and `cad.build123d.unfold(shape, k_factor=)`; on a mesh a program holds
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
`<part> (solid 2 of 3)`; the part's `several_solids` (the warning every process gives) says so, and the
summary counts the parts judged. A
part of more than 4000 faces (`FACE_BUDGET`, text-to-cad's own bound) is not measured: `model` is
`{"error": ...}`, the report `partial`, never a pass. The bound keeps a check of a large part inside a check's
time limit (`CAD_ENGINE_CHECK_SECONDS`, past which the check is stopped, not checked): a check's time grows about as its
part's faces to the power 1.4 -- a plate of 144 holes takes 9 seconds, one of 576 a minute -- so a part at the
bound takes about a quarter of an hour, and one of 20000 faces would take over two.

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
  together (the turn less the widest gap between the face's points about the axis: a fillet on a leaning edge
  is a quarter-round whatever its parameters' box says); nothing stands inside its narrowest cylinder (`_cored`:
  from just inside the wall, four ways about the axis at five places along it, a ray toward the axis meets no
  face before it gets there) -- a cylinder that goes round a boss, a hub or a core is an annular cavity's outer
  wall, an O-ring's face groove or a round pocket about a boss, which is a pocket's and no hole; a wider cylinder with a narrower one of the hole beyond it toward the opening (either way along a
  through hole) is an internal groove, no counterbore: it and the planes beside it leave the hole, a keyseat
  cutter's recess (`sharp_edges`, `access`), `grooves` [{diameter_mm, width_mm, location}] saying it.
  `diameter_mm` (narrowest full cylinder), `depth_mm` (the drilled length: that cylinder's axis between its two
  ends, each at its middle along the axis -- 25 / cos 30 deg for a 30 degree hole through 25 mm, where its
  longest side is longer --, below any counterbore), `overall_depth_mm` (every cylinder's extent),
  `depth_to_diameter`, `micro_tool` (under 1 mm) and `reach_limit` (the diameters a drill that size reaches:
  40 at 1 mm and over, 25 at 0.5 mm and under, evenly between), `through` / `bottom` (`through`, `drill_point`, `flat`, `closed`, `other`: an exact
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
- **pockets** — one cavity model. A planar face meeting, by a concave edge (or a concave root fillet), faces
  that rise from it, and seen end-on (a ray along its normal from it escapes), is a **floor**. A face **rises**
  (`Model.rises`) where it lies along the floor's normal or leans back from it by a draft of 25 degrees at most
  (`DRAFT_MAX_DEG`, text-to-cad's own: tapered end mills are catalogued to about 20 degrees a side, and a face
  30 degrees off the axis is a 60-degree chamfer mill's V), everywhere on it (its samples' normals and those at
  12 of its mesh's nodes); a face leaning over the floor is an undercut, never a wall. The **walls** grow from
  those along concave/tangent edges that run up the cavity (within 45 degrees of the normal). So a drafted, a
  lofted or a tapered pocket, a cone's, and one with some walls drafted and some square are the pocket their
  straight twin is, with its depth, width and corners. `kind` (`closed`; `slot`: open with a width; `open`),
  `depth_mm` (floor to the walls' rim), `depth_from_top_mm` (floor to the part's top along the normal: tool
  reach), `width_mm` -- the narrowest gap across the void **at the floor** (`_floor_width`: from 17 stations
  along each wall's foot, a ray across the axis along the wall's normal, 0.02 mm above the foot, to the first
  face: where that face looks back within 45 degrees and shares no edge with the wall, its length is a gap --
  a slot's width, a drafted pocket's at its floor, an annular groove's radial gap, a round pocket's diameter;
  where no two walls face each other, a triangle's, the largest tool that touches a wall and clears the wall
  its ray meets, the inscribed circle), or the narrowest sampled gap between two of its walls above the floor
  where that is less (a T-slot's neck) --, `depth_to_width`, `draft_deg` (its walls' greatest),
  `reach_limit` (the widths a tool that fits reaches: 30, a micro tool's 25 to 30), `saw` (a straight slit a
  slitting saw runs through: two plane walls square to the floor, the floor running out of the part at both
  ends), `engraved` and `engraved_corners` (a cavity at most 1 mm deep, no deeper than twice its width and
  under 2.5 mm wide: lettering, an engraving tool's -- its corners are counted on it and leave
  `internal_corners`, and `cnc.engraving` says them all once; its width is still a gap under 2.5 mm,
  micro-machining),
  `open_boundary_fraction`, `floor_radius_mm` (root fillet), `axis`, `aligned`, `reachable` (along a direction
  the machine has; or none of its edges left unmade, an edge only a setup of its own makes counted unmade: a
  chamfer mill's V reads as a pocket on one flank; or every face of it along a machine direction square to its
  axis: a profile cut along that direction, a plate's notch turned in the plane, never inclined),
  `inclination_deg`, `wall_count`, `floor` (its
  floor's ref), `width_faces` (the two walls the width is between; `location` is the first of them, else the
  floor), `micro_tool` (under 1 mm wide: only a micro tool fits). A face that reads both ways -- an open step's
  floor and wall, a drafted wall whose top a tool sees end-on with the floor beside it -- is one cavity: the
  closed reading, else the one cut along a machine direction, else the shallower.
  **Through** cavities (`kind` `through`: windows, through slots, cut-outs, no floor) are faces that rise
  along a world axis, either way (a tapered window's from its wide side), joined by concave or tangent edges
  that run up it, none a floor pocket's, none meeting a plane square
  to the axis by a concave edge, closed around the axis -- no ray across the axis from inside the cavity
  (from each face along its normal, then from the middle of that ray every 10 degrees and toward the middle
  of each pair of the edges leading out of it) leaves the part: an open valley, a quilted pad's grooves, a
  T-slot or a dovetail open at its neck is no window, whatever way its faces look; a keyway open only into
  its bore is closed --, with a corner -- a concave cylinder along
  it that is no floor's root fillet (no tangent plane neighbour seen end-on), a drafted corner, or a sharp
  concave edge that runs up it; `depth_mm` is the walls' extent along the axis, `depth_from_top_mm` the
  shallower side's reach (a drafted one's from its wide side), `width_mm` the narrowest sampled gap between
  two of its walls (a drafted one's at its narrow end, as a pocket's at its floor), `floor` null.
- **internal_corners** — a pocket's in-plane corners: each wall that goes round the void -- a concave cylinder
  along the pocket's axis (its `radius_mm`), else any other wall by the radius its foot turns by at the floor
  (`_plan_radius`: the circle through the foot's ends and middle, seen along the axis; a drafted corner's cone
  or a lofted one's ruled face is tightest there, a leaning fillet's cylinder reads its own radius) -- and
  each sharp concave edge between two walls that runs up the cavity and no tool makes from another side
  (`radius_mm` 0, `sharp` true, `edge`). One corner is one feature: a round one's `location` is its own face
  (`corner`), the face to edit, a sharp one's finding is at its `edge`; `pocket` is its cavity's ref (the
  floor), which its other corners share. `height_mm` (the corner's own extent: the cavity depth there),
  `depth_mm` (from the part's top), `radius_to_depth`, `tool_mm` (largest `--tools` tool <= 2r, else 2r; a
  wall that goes all round -- a round pocket's, an annular groove's outer one -- takes no tool wider than the
  cavity), `reach_ratio` (depth / tool_mm), `micro_tool` (that tool under 1 mm), `reach_limit` (the diameters
  a tool that size reaches),
  `pocket` (its floor's ref; a through cavity's `location`), `folded_edges` (the sharp edges its run makes
  through small edge rounds at its ends -- an edge sharing a vertex and a face with it that runs along its
  axis, or is a face of such a round and under twice its radius long; never a floor-to-wall edge -- folded in
  rather than listed under sharp_edges). A through cavity's round walls and unmade sharp edges along it
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
  edge's own ends (each point of its rim told in or out by the first face an oblique ray from it meets, a ray
  met on an edge or edge-on told along another, the kernel's solid classifier where all three are in doubt; a
  point on a face is not in the material), slid back along the edge where it passes them (the shank travels
  along the edge: an 8 mm port in a wall is no way to a 25 mm corner; an edge shorter than the disc is no run for one); a dovetail
  cutter of any acute angle likewise, its floor a plane square to one of the part's axes (45 and 60 degrees
  are standard; another, Parker's 66, is a cutter ground to it, the special cutter's finding naming the
  angle). The disc must get there, by geometry alone (the least disc that reaches the station from the
  opening, its shank of no breadth): a keyseat cutter's no wider than the bore it comes down, so every
  station within twice the bore's radius of its axis (a 20 mm chamber behind a 4 mm bore: none); a slot or
  dovetail cutter's plunged through an opening as wide as the disc somewhere along the edge (its sides found by
  bisection), or fed in at its own level from a side the recess opens to (a T-slot from its open end; a round
  chamber under a 5 mm port: neither). A recess's way in is the whole recess's: an edge its disc reaches
  with no way in beside it is made where an edge on the same floor or ceiling is made by such a cutter (a
  closed T-slot with an entry hole at one end: the cutter drops in there and travels the slot, its far end's
  edges made). Else the edge is unmade, `no_way_in`. A slot cutter's opening is read at
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
  under 5 mm, and thicker where it is a feature that stands over four times its thickness tall (a 6 mm pin
  40 mm tall): `thickness_mm`, `opposite`, `height_mm` (a plane's extent across its longest concave root edge),
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
  either way, then the probes: the part's own directions, then every 15 degrees about each world axis and
  the 218 directions through a cube's surface cut in three a half side -- a set a cube's symmetries leave as
  it is, each tried by every point it faces, so what is found does not turn with the part's frame),
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
  item, judged at its worst face (`faces`, `face_count`), and it takes in a face beside it that a line at an
  angle reaches part of (a chamber's floor behind its neck): one recess, one finding, whichever of its faces
  a sample's ray clears. A freeform face (a sweep, a loft, a spline: one may be a whole part, a coil spring's
  wire) is sampled at up to 128 points, where a plane or a cylinder takes 16. Items of `kind` `special_cutter` are the edges only a T-slot,
  dovetail or keyseat cutter makes, joined by the faces they share, whatever line of sight says: `cutter`,
  `edge_count`, `edges` (their fractions 0), `advice` (the hint's ask: a recess whose dovetails are all within
  `SQUARABLE_DEG`, 10 degrees, of square is a wall drafted back, asked squared so an end mill makes it; any
  other kept to a standard cutter). Directions: 3
  axes the six world axes; 4 axes those plus every 15 degrees about the rotary axis (X, Y or Z, the one
  that reaches most); 5 axes those plus every 15 degrees about each world axis, then the part's own and the
  spread ones (so five reach at least what four do).
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
  (convex coaxial cylinders not groove floors: `diameter_mm`, `length_mm`, and each section's slender run --
  thinnest first, a section and the sections beside it no more than 1.25 of its diameter across bend as one
  length: `run_mm` and `run_to_diameter` on the thinnest, a section a thinner one's run takes in naming it,
  `run_of`; a 6 x 240 stem on a 60 mm flange is 40 diameters), **bores** (on-axis holes),
  **grooves** (a coaxial cylinder with both ends meeting square planes by concave edges: `internal`,
  `width_mm`, `depth_mm`, `depth_to_width`, `diameter_mm`, and internal: `entry_diameter_mm` -- the wider of
  the two bores beside it, its tool's best way in -- and `depth_to_entry`), **live_tooling** (off-axis face groups: `cross_hole`, `flat`,
  `slot`, `feature`, with the hole's `relation`).

### Rules

`cad._internal.dfm.cnc.RULES` (above: the table is not copied here). An error is a part no general shop
makes as drawn; a warning a recommendation, a cost or a risk: it is made.

A number a published guide states cites it: Protolabs Network (Hubs)'s "How to design parts for CNC
machining" (`hubs-cnc`) and its CNC machining service page's maximum part sizes (`hubs-cnc-service`). A floor
no guide states is text-to-cad's own (`rules.OWN`: its finding's `source` reads `text-to-cad, ...`, never the
publisher's name, and the rule's note gives the reason). A limit that follows the tools is the smallest
`--tools` tool's where one is given. With none, one tool floor holds for holes, slots and corners: the 0.05 mm
the guide's small-features table calls a feasible hole (`TOOL_FLOOR_MM`; a corner's radius half of it, a
gap's width all of it); a tool under 1 mm is a micro tool (`MICRO_TOOL_MM`), whose reach is one continuous
limit (`reach_limit`, own, no guide's or catalogue's figure: 25 diameters at 0.5 mm and under, `MICRO_REACH`,
on a long neck made for it, rising evenly to the guide's 30 at 1 mm; no step at 1 mm), a micro drill's the
same to the guide's 40. A straight slit open at both ends, deeper than an end mill of its width reaches, is a
slitting saw's (`cnc.slitting_saw`, a warning that names it), and no saw's past 60 of its widths (`SAW_REACH`,
own: a saw taken as about 200 times its thickness across, cutting under a third of its diameter deep).

What is text-to-cad's own and why (each rule's note says it again): the tool floor for slots and corners; the
micro reach and the saw's; `cnc.setups`' five (the guide says a part rotated three or four times: four rotations
are five clampings); `cnc.drill_size`'s 0.005 mm (the guide recommends a standard drill and states no
tolerance); `cnc.tall_feature`'s four; the draft a wall may have (25 degrees) and an engraving's depth (1 mm);
`cnc.part_size_limit` (twice the cited network's sizes: a specialist's machine); turning's slenderness (ten
diameters a section), groove depth (a quarter of the bore a warning, half of it the geometric limit, an error)
and width (five). The part's size alone fails no part: long-bed mills and vertical lathes exist, so both size
rules are warnings, and only a `--stock` given that the part does not fit is an error.

The pocket and corner rules apply under `--turning` too, to the live tooling's pockets. Under `--turning` the
milling rules -- `sharp_internal_edge`, `gap_width*`, `inclined_feature`, `special_cutter`, `undercut`,
`setups` -- are `not_applicable`, and `cnc.turning_not_judged` (info) says what turning does not judge.

No rule judges a shop's own feature limits (its narrowest engraved line, its smallest part, its turned
diameters and cross holes) or its own machine: those are a shop's, and the measurements (`stock`, `turning`,
`turned_diameters`, `grooves`, `holes.relation`, `pockets.depth_from_top_mm`) are compared with them. The
part's size is judged against a general machine's alone (`cnc.part_size`). `--stock` given is checked
(`cnc.stock_too_small`).

Each finding's message ends with what its item says of itself (`Rule.detail`): `internal_corner_sharp` its
edge, height and depth below the top; a round corner's rules its height and its cavity (`pocket`; the finding
is at the corner's own face); `sharp_internal_edge` its edge, the two faces (in words, `between`: every ref an
item carries is one ref), the void angle and xyz
(its fix names the angle); every `walls` and `gaps` rule the face across (`opposite`) and the thinnest point.

Fact findings (not rules): `cnc.stock_too_small` (e: the part does not fit `--stock`), `cnc.no_turning_axis`
(e, `--turning` on a part with no surface of revolution), `cnc.mostly_not_turned` (w, under half the area
turns), `cnc.live_tooling` (i), `cnc.turned_corner_sharp` (i: the sharp internal corners of the turned
profile, each left with an insert's nose radius), `cnc.turning_not_judged` (i),
`cnc.rotary_axis` (i), `cnc.fine_detail` (i, >= 20 faces under 1 mm), `cnc.engraving` (i: the shallow, narrow
cavities an engraving tool cuts, and their corners, said once),
`cnc.material_assumed` (i: no `--material`, walls judged by metal's limits), `cnc.ball_creases` (i: the
creases a ball end mill rounds, the worst one's departure from the drawn edge).
The summary says a part's setups (an assembly: the most any part takes), never a sum; its parts, holes and
pockets count every occurrence and every solid, as the findings do.

Context the rules read: `material_class`, `wall_class` (the class, else `metal`), `tools_given`,
`min_tool_mm`, `axes`, `turning`.

Sources and when each was read: `cnc.RULES.sources` (and every result's `measurements.rules.sources`).

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
unreached share is read on at most 16 points, its disc cutter's reach on 4. A part of more than 4000 faces is
not measured (`FACE_BUDGET`); rays' boxes are tested together a batch of at most a million ray-face pairs
(`BATCH_PAIRS`), so memory a batch does not grow with the part's faces. Time is not bounded otherwise: a ray
costs with the edges of the face it crosses (a plate of 576 holes takes most of a minute).

## Sheet metal

A STEP, an xbf or a live shape (`cad.build123d.sheet_metal(shape)`) is measured on its exact B-rep
(`cad.build123d._dfm_sheet`); a DXF cut file (`cad dxf dfm FILE --process sheet`) with ezdxf
(`cad.build123d._dfm_dxf`). A mesh is refused (a sheet's radii and thickness are not on a mesh). Options:
`--thickness` (the stock's, compared with the measured; a mismatch is `sheet.thickness_mismatch`; without it
each part's rules scale by its own measured thickness),
`--k-factor` (the shop's, from its bend table; default Hubs's air-bending chart by material hardness and
r/t), `--bend-radius` (the shop's; a bend modelled otherwise is `sheet.bend_radius_differs`), `--kerf` (a
hole, web or gap narrower is `sheet.under_kerf`), `--sheet-size` (the shop's largest sheet; else a standard
5 x 10 ft sheet, 3048 x 1524, assumed, a warning past it, and the largest plate stocked, an error past it),
and for a DXF `--units` (the units it was drawn in, where it declares none or the wrong ones). A shop's gauges, its tooled radius per gauge, its dies and its
smallest and largest parts are no rule: give the ones it publishes, or compare the measurements with them.

### How it measures (3D)

- **Thickness.** Each face is sampled by area; an exact ray from each sample, square to the face, crosses
  the material to the next face. The thickness `t` is voted by the skins alone: the rays between a face and
  the face opposite it (an antiparallel plane, a coaxial cylinder) where the face is at least 2.5 times as wide
  as the two are apart (`SKIN_WIDTHS`: a plane's outline's smallest rectangle's short side, a cylinder's
  length along its axis -- each face in its own frame, so the same wherever the part stands; text-to-cad's
  own line), the area-weighted modal distance. Where no face is that wide, one twice as wide and ten times
  as long as the part is thick there votes (`STRIP_WIDTHS`, `STRIP_LENGTHS`, its own lines too: a 100 x 4 x 2
  mm strip is cut from sheet, and has no wider face to outvote; a 40 x 30 x 15 mm block is no strip). A tube's
  two ends, a grille's webs, a bar's sides and a block's faces are opposite too and are no skins: a part with
  none is not sheet (`why`: "no face is 2 times as wide and 10 times as long as it is from the face opposite
  it ... a bar or a block"). Nothing reads the part's axis-aligned box. A planar face
  at least half of whose rays reach an antiparallel planar face `t` away is a skin, its rays counted (its samples
  share its area equally: summed, a face exactly half across read under half or not by the last bits of its
  area, which a move changes). A coaxial concave/convex cylinder
  pair `t` apart is a bend; a part of such pairs with no flat skin is a closed section, a tube (not sheet,
  named at its real wall), or, where a face along the axis joins inside to outside (a slit), a sheet rolled
  with no flat flange: sheet (`parts.rolled`), which this check does not unroll, so its `bends` are not
  measured and the check is `NOT CHECKED`, never an error of the part's. A face touching both faces of a pair
  is a cut edge; a cone between a skin and a coaxial
  hole wall is a countersink. A chamfer or a round of a skin's edge (a slanted plane, a convex cylinder of at
  most `t` along it, a cone, torus or sphere about its normal, within the sheet) is an `edge_break`, and a
  face square to the skin that reaches it and its opposite skin through breaks is a cut edge: its rays run
  across the plate and measure its width, never its thickness. A cone, torus, sphere or freeform face whose
  rays cross `t` is `formed` (a cone between flanges is not a bend). A face square between two opposite planes that face away from each other,
  nearer each other than its own rays run, is the cut edge of a stretch off the thickness (a 3 mm wall's end
  cap): the stretch is judged on its skins, not on rays that run along it. Everything else, and any stretch
  of a skin whose rays cross another distance, is `not_sheet` at its ref; a face standing square on a skin
  (a boss's, patch's or pocket's side) is thicker or thinner by its height off that skin. Faces off the
  thickness that touch are one feature: they share the ref of the one furthest off it (`location`; each
  keeps its own in `face`), so a pocket's floor and walls are one finding.
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
  `joggle_web` (which flange_length leaves alone). A cutout across both of a bend's tangent lines past the
  bend's end (a window through the bend, which the unfold reads as two bends in line) ends the bend: it is
  no hole beside that bend (`hole_to_bend` leaves it out) and its width there is a relief's (`reliefs`).
  A bend that stops at a hole in the bend line while its flanges run on is the hole's finding
  (`sheet.hole_to_bend`, `sheet.hole_in_bend`), no relief missing. Fused, this is the flat pattern, and
  the area its pieces share -- each two intersected, never their areas less the fused pattern's, which a
  STEP written as NURBS loses a little of -- is its overlap (`flat_overlap_mm2`);
  a hole of the fused flat no face's inner wire gave (one crossing a bend's tangent line, part of both
  faces' outer wires) is read back from it, `in_bend` where it reaches a bend's strip. Where a chamfer or a
  round breaks the cut edge the skin stops short of the cut, so each flange's breaks are laid into its plane
  and fused on: the flat is the cut outline (an 80 x 40 x 3 plate chamfered 0.5 mm unfolds 80 x 40, not 79 x
  39), and a hole with a broken rim is read back from it at its cut size. A break's edge that is no line and
  no arc (its end where it meets the next break at a corner of the outline: an ellipse's arc between two
  rounds, a conic between a chamfer along a line and one along an arc) is laid as chords within `CHORD_MM`
  of it, as an arc's are, so none is shorter than the tolerance the breaks are fused with.
  `cad.build123d.unfold(shape, thickness=, k_factor=, material=, bend_lines=False)` returns it
  (`bend_lines=True`: a Compound of `CUT` and `BEND` children, one DXF layer each, `BEND` empty for a flat
  plate), and raises `ValueError`
  for a part with a corner modelled without a bend or a flat that does not hold all of its material. Holes, notches, tabs, webs, gaps, flange lengths, reliefs and every distance are measured on
  the flat pattern in the plane (`cad._internal.sheet_plane`, numpy), each place mapped back onto the
  part for its ref. At K = 0.5 the flat area equals volume / t exactly (`neutral_area_ratio`); the flat's area
  with each strip widened to K = 0.5, over volume / t, is `flat_material_fraction`: 1 where the flat holds
  all of the part's material.

### Families (each `{"items": [...], "count": n}`, items sorted worst first, capped at 300)

Every item of a part's families carries its part's `thickness_mm`: what its rules scale by.

| family | per item | notes |
|---|---|---|
| `parts` | `thickness_mm`, `is_sheet`, `why`, `sheet_area_fraction`, `bend_count`, `sharp_bend_count`, `flat_length_mm`, `flat_width_mm` (smallest rectangle), `flat_area_mm2`, `flat_overlap_mm2`, `neutral_area_ratio`, `flat_material_fraction`, `bent` (it has a bend: which thickness limit is its), `rolled` (a sheet rolled with no flat flange: not unrolled), `unfold_note`, `not_in_flat` (the flanges no bend reached, each its largest face, and the bends not laid out), `joggles` [{bends, location, xyz}] (two bends meeting tangent with no flat between), `flat_bend_lines` | one per part |
| `not_sheet` | `kind` (thicker, thinner, unpaired; `edge_break`: a chamfer or round of a cut edge, its depth `break_mm`; `formed`: a cone, torus or freeform face a thickness across), `surface`, `local_thickness_mm`, `sheet_thickness_mm`, `deviation_mm`, `area_mm2`, `judged` (None on a part that is not sheet, or a round a `sharp_bends` item names: no thickness verdict), `face` (its own ref; `location` is its feature's) | a boss, pocket, round, freeform face |
| `sharp_bends` | `kind` (sharp, inside_only, outside_only, unjoined), `angle_deg`, `inside_radius_mm`, `outside_radius_mm`, `thickness_mm`, `edge_count`, `faces` | a corner joined without a bend: its flange is not in the flat |
| `bends` | `kind` (bend; hem: 175 to 185 degrees with an inside diameter of at most 4 t, `HEM_DIAMETER_T`, text-to-cad's own line -- wider is a U-bend, a bend; curl: over 185), `inside_radius_mm`, `outside_radius_mm`, `radius_to_thickness`, `angle_deg` (bent from flat), `included_angle_deg`, `flanges_angle_deg`, `length_mm`, `axis`, `axis_origin`, `tangent_lines`, `k_factor`, `k_factor_source`, `bend_allowance_mm`, `bend_deduction_mm` (None for a fold of 175 degrees or more -- a hem, a U-bend, a curl: its mold lines meet nowhere, and its flanges have no height from one); `faces` [inside, outside] | location: the inside cylinder |
| `flanges` | per bend side: `length_tangent_mm` (least along the bend), `length_tangent_half_mm` (reached by half the bend), `length_inside_mm`/`_half`, `length_outside_mm`/`_half` (mold lines: + r·tan(θ/2), + (r+t)·tan(θ/2)), `length_outside_minus_radius_mm`, `stations`, `stations_off_flange` | the length runs to the free edge or the next bend's tangent line, read at 11 stations along the bend; a station whose start is off the flat (the bend runs on past its flange there) has length 0, judged by `sheet.flange_length` as a short flange is, the item then at the bend (`location` its ref, `xyz` that stretch) |
| `channels` | `base_length_mm`, `flange_length_mm` (outside), `base_to_flange_ratio` | a flange between two parallel bends turning the same way |
| `reliefs` | per bend end and side where the flange runs on past the bend's end: `kind` (corner where the end meets another bend's end, relieved or not; else bend), `needed`, `present`, `width_mm`, `depth_tangent_mm`, `depth_centerline_mm`, `depth_centerline_minus_radius_mm`, `detail` | a missing relief has width and depth 0, its detail "no relief" |
| `hems` | `inside_diameter_mm`, `gap_mm`, `return_length_mm` | the bends of kind hem |
| `curls` | `inside_radius_mm`, `outside_radius_mm`, `angle_deg` | over 185 degrees |
| `holes` | `kind` (round, slot, cutout), `size_mm` (diameter, or least width), `length_mm` (largest extent), `edge_distance_mm` (edge to edge), `in_bend`, `countersunk`, `countersink_diameter_mm`; `faces` | location: the hole's wall; a hole read back from the flat (across a tangent line): the face it lies on |
| `hole_spacing` | `distance_mm` edge to edge, `other` | each hole and its nearest, one of them round (the bar between two cutouts is a web) |
| `hole_to_bend` | `distance_tangent_mm`, `distance_centerline_mm` (+ BA/2), `distance_inside_mm`, `distance_outside_mm`, `distance_outside_minus_radius_mm`, `bend` | the nearest bend, but one the cutout ends (a window across both its tangent lines); a round hole's distances are exact |
| `notches` | `width_mm` (mouth), `length_mm` (depth), `length_to_width` | pockets of the outline off its hull |
| `tabs` | `width_mm`, `length_mm`, `length_to_width` | facing straight sides, a tip, an inside corner at both sides of the base (proud of the body on three sides: an L plate's leg is no tab) |
| `webs` | `width_mm`, `said`, `cutouts` | the narrowest material within an outline (a neck, a bridge), and the bar between a cutout that is no round hole and the cutout nearest it: the bars of one width are one item, `cutouts` how many they lie between (a grille is one feature) |
| `gaps` | `width_mm`, `between` | the narrowest void (notches, gaps between outlines; across a hole only where it necks in under the hole's own `size_mm`) |

DXF adds `cut_file` (`insunits`, `unit` and `unit_from`: `$INSUNITS` or `--units`, `mm_per_unit`,
`extents_mm`, `layers` with intents, `cut_layers`,
`cut_layer_count`, `contour_count`, `bend_line_count`, `unread` and `unread_count`, `is_drawing`: a fact, no
excuse -- a file with dimensions in it is measured as any other), `scale` (`units_suspect` where the unit
makes the drawing implausible -- in mm under 25.4 mm, in inches larger than the sheet (`--sheet-size`, else
the standard one), its note giving the part read the other way; else under 1 mm or over 10 m across, as every
source is held to (`_common.units_doubt`): a warning, the rules still run in the unit the file is read in),
and defect families, each item `location` = `layer L, TYPE #handle` (the modelspace entity's: a block
reference's for a curve of its block), `xyz` in mm: `open_geometry` (dangling ends and branch points, less
those an overlap explains: a curve laid partly on another meets it at three ends or leaves its own ends
on it), `joined_gaps` (ends left dangling within 0.01 mm of each other, `_JOIN`, joined), `overlaps` (`kind`
`duplicate`: an exact copy of another entity's curve of any type -- a line, an arc, a whole circle, a spline,
an ellipse -- one item for the pair of entities, the copy left out when the contours are chained, so the
outline it doubles is still the part's and a hole drawn twice is one hole; `partial`: collinear lines or
concentric equal arcs overlapping over a length), `self_intersections`, `contour_crossings` (`kind`
`crosses`: one contour passes from inside the other to outside it, through a sampled point as anywhere, a
whole circle by its equation; `touches`: they meet within 0.0001 mm without crossing -- a hole tangent to
the edge, two parts corner to corner), `zero_area_loops`, `annotations` (text, dimensions, hatches,
points on cut layers, a block's among them), `floating_interiors` (an island inside a hole),
`short_line_runs` (8+ short lines turning a little each way, a curve as chords: one item a contour, its
`runs` counted). Of the drawing checks every export runs (`validate_drawing_document`),
`zero_length_entity` is kept as a finding; the rest are this check's own, read exactly.

**Units.** A cut file is read in the units it declares (`$INSUNITS`: inches, millimetres and the other
lengths) or the ones given (`--units mm|cm|m|in|ft`, which rule over the file's). One that declares none
-- every R12 file -- is not measured without them (`NOT CHECKED`, `units_not_set`, its message naming
`--units`); read with them it is measured, and `units_not_set` is then a warning (a shop's software has to
be told too), as `units_differ` is where `--units` is not what the file declares.

**How a cut file is read.** Every entity on a cut layer is read, an annotation, or said not read. ezdxf
explodes what holds curves: a block reference (`INSERT`) into its block's entities with its own transform,
a nested one too (16 deep at most; an entity on layer 0 of a block takes the reference's layer), a polyline
(`LWPOLYLINE`, a 2D or 3D `POLYLINE`) into its lines and arcs. What is drawn closed is a contour as drawn,
whatever its sides' lengths: a circle, a closed spline, a full ellipse, a closed polyline. The other pieces
are chained end to end: ends drawn at one point (within 0.0001 mm) are one, and only ends left dangling by
that are joined across a gap of up to 0.01 mm -- so a side, a stub or a fillet shorter than the join is a
side, never an open contour. A layer's intent is its name's (`cad.engine.export.dxf.layer_intent`, by whole
tokens) and its layer table's: a flat pattern export's bend-extent lines (Inventor's `IV_TANGENT`, a
`BEND_EXTENT` layer) and its marks (`IV_ARC_CENTERS`, `IV_TOOL_CENTER`, `IV_FEATURE_PROFILES`) are reference,
neither cut nor a bend's centre line. A line, an arc or a circle is read where it
lies in the world's XY whatever its OCS: one drawn mirrored (extrusion (0, 0, -1), as a mirrored copy is
written) is read mirrored. A curve that leaves the sheet's plane (a 3D polyline that is not flat, an arc
whose extrusion is off Z), a mesh, a block that does not explode and any type this check does not read as
a curve are `cut_file.unread`, and the `cut_entities` family is then not measured (`measurement_failed`,
naming each): what was not read is never passed. A file with no cut curve at all -- empty, or annotation
alone -- is not measured (`no_cut_geometry`); with no contour closed, `parts` is not measured.

**Bend lines.** A bend layer's lines (one drawn twice is one) are the bends' centre lines; a part's are those
whose middle lies on it (`parts.bent`, `bend_line_count`). `hole_to_bend` gives each hole's
`distance_centerline_mm` to the nearest (exact for a round hole); a line that ends on a cutout's edge and
runs on away from it ends there -- a window across the bend line, a relief -- and that cutout is no hole
beside it, and so does a line drawn straight across a cutout that reaches 2 t to both sides of it
(`WINDOW_T`, text-to-cad's own reading of a drawing with no bend radius: past the tangent lines of a 90
degree bend of inside radius up to 2 t; short of that, or with no `--thickness`, the cutout is a hole in the
bend). `flanges` gives, per bend line and side, `length_centerline_mm`: how far the outline (or the next
bend line) lies from the line, square to it, the least of 11 stations on the material
(`length_centerline_half_mm`: what half of them reach).

**Bounded.** The plane's measures (`cad._internal.sheet_plane`) work through their pairs a million at a
time (`PAIRS`): a whole circle is crossed, contained and measured exactly, never through its chords; a
sampled loop is tried stretch by stretch, each only by the rays that cross its box, and only by the points
in its box; each hole's nearest hole is sought nearest box first (`nearest`); a hole's own width is cast
only where it is no circle; a tab's sides are tried only against the sides within a tip's length of them;
a contour's crossings of itself are sought among the segments whose extents along x overlap (past
`SELF_CROSSING_PAIRS` such pairs, a hundred million, they are not sought, and `self_intersections` is then
not measured). Curves are sampled to within 0.01 mm (`CHORD_MM`), so a distance to a sampled arc or spline
is within that. A panel of 2025 round holes is measured in about 2 s within 150 MB, a traced outline of
25 000 lines in about 5 s.

### Findings of fact (`cad._internal.dfm.sheet.findings`)

Each names its refs and its figure as data (`refs`, the location first; `value`, `limit`, `unit` where it
has one), as a rule's finding does: nothing has to be read out of a message.

`sheet.not_sheet` (error: no constant-thickness sheet, a freeform shell, a bar or a block with no skin, a
tube's closed section; named as its ref names the part),
`sheet.flat_length` / `sheet.flat_width` against `--sheet-size` (errors: the user's own sheet, so a finding of
fact that cites no guide; against the standard sheet assumed they are the rules' warnings), `sheet.sharp_bend` (error: each `sharp_bends` item, one
finding per place; the message says which radius is missing, the hint "model an inside radius r >= t and an
outside radius r + t at the corner"), `sheet.flat_incomplete` (error: `flat_material_fraction` off 1 by more
than 3%, the flat is not the part's blank, where no `sheet.sharp_bend` or judged `not_sheet` face already says
why for that part: it names what did not unfold, `not_in_flat`, at the first of them, or says that every
flange and bend did), `sheet.thickness_mismatch` (error), `sheet.flat_overlap` (error),
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
`sheet.k_factor_assumed` (info), `sheet.measured_not_judged` (info, one a check: what was measured and no
rule judges -- how far the bend reliefs reach past the bend, the corner reliefs, the channels' proportions);
DXF: `sheet.thickness_unknown` (warning: no `--thickness`, naming the rules
that scale with it and were not evaluated; the OK line says so too), `sheet.open_contour`,
`sheet.overlapping_curves`, `sheet.self_intersecting`, `sheet.crossing_contours` (two contours that cross,
or touch), `sheet.zero_area_loop` (errors), `units_not_set` and `units_differ` (warnings: a file read with
`--units`, above), `sheet.annotation_on_cut_layer`, `sheet.floating_interior`, `sheet.short_line_run` (warnings),
`sheet.joined_gap` (warning, one a file: its joints closed across a gap, the widest),
`sheet.bend_lines_read` (info: what the bend lines were held to). A flat drawing holds no bend, relief, hem or
thickness to read (the report's `not_measured`): every cut file's result says their rules judge nothing
(`families_not_measured`, info: the bent part's check judges them). A cut file's summary names its closed
contours and its open places while any contour stands open (a hole's loop then reads as an outline, so no
part or size is named).
A cut file's layers holding cut geometry are counted (`cut_file.cut_layer_count`), never judged: a shop's
file rules are its own.

### Rules

`cad._internal.dfm.sheet.RULES` (above: the table is not copied here): Hubs's bending and laser-cutting
numbers, Protolabs' uniform-thickness, notch, tab and hem guidance, and a standard 5 x 10 ft blank (Xometry's
page for the largest), each citing its page as the evidence for general practice; four are text-to-cad's own
(`rules.OWN`): plate over `PLATE_MM` (an inch) is no sheet shop's work (an error), a flat pattern longer or
wider than `LARGEST_PLATE` (a 10 x 40 ft plate, the largest stocked) is cut from no one plate
(`sheet.flat_length_limit`, `sheet.flat_width_limit`: errors, where no `--sheet-size` names the shop's), and
a bend radius over `BRAKE_RADIUS_T` thicknesses is bump-formed or rolled, not bent in one hit (a warning).

`t` is the thickness a rule scales by
(`scale_by` `rule_thickness_mm`): each item's own, which `sheet._scales` writes on it -- the stock's where
`--thickness` names it, else its own part's measured `thickness_mm` -- so a document of a 1 mm and a 3 mm
part judges each by its own, whichever comes first (the context's, the first part's, is read only by a
family with no item). A failure whose limit is its item's own carries it (`failures[].limit`).

Where a source's convention is not the obvious one the rule's note says which it reads: a flange's height
from the outside mold line less the inside radius (Hubs's "minimum bend height 2 t + r"; the page does not
say where it is measured), a hole's distance to a bend from the bend's tangent line ("from the start of the
bend radius"). A cut file has its own two (`when` `cut_file`): its bend line is the bend's centre line, with
no radius or angle, so a flange and a hole are held to the least the same rules ask of the flat at any radius
(1 t and 2 t from the line), and `sheet.bend_lines_read` says the bend lines were held to those floors, not
the full rules. The flat pattern is judged against the standard blank assumed (warnings) and the largest
plate stocked (errors) where no `--sheet-size` is given; against the sheet given it is a finding of fact,
above.

No rule judges a shop's tooling or capabilities: its gauges and tooled radius per gauge, its die widths and
the distances they set, its largest tooled radius, its brake's angles and bend lengths, its smallest and
largest parts, its relief depths, countersink sizes, channel proportions and file rules (a relief that
stops short of the bend's tangent line is no relief, width 0; how far past it one must reach no fetched
guide says). The measurements
carry each of them (`parts.thickness_mm`, `bends.inside_radius_mm` and `angle_deg`, `flanges.length_*`,
`hole_to_bend.distance_*`, `reliefs.depth_*`, `holes.countersink_diameter_mm`, `channels`,
`cut_file.cut_layer_count`) for a shop's own limits to be read against.

Sources and when each was read: `sheet.RULES.sources`. text-to-cad's own figures, each said as its own:
`SKIN_WIDTHS`, `STRIP_WIDTHS` and `STRIP_LENGTHS`, `PLATE_MM`, `LARGEST_PLATE`, `BRAKE_RADIUS_T`, `HEM_DIAMETER_T`, and a
cut file's `WINDOW_T`.

### What it does not measure

Bend order, tooling access and collisions while bending; grain direction; hardware (PEMs) and their
distances; a rolled part (a sheet rolled with no flat flange is said, not unrolled: `NOT CHECKED`); a
contour that crosses itself through one of its own points (a pinch: a crossing between points is found); a
joggle's own limits (its offset against the thickness, a joggle die's: its two
bends are unrolled, `sheet.joggle`); stamped forms -- embosses, louvers, beads -- beyond saying them
(`sheet.formed_surface`); box flange maxima and the corner flange gap;
bump-formed or conical bends (a cone between flanges is not a bend: `sheet.formed_surface`); freeform formed
shells (reported not sheet); closed hems
(modelled as a double thickness: not sheet); a hole crossing a bend is unrolled from samples; a non-straight
bend end is unrolled from samples; notches are hull pockets (a pocket's mouth, not its narrowest width);
tabs need two parallel straight sides. Corner reliefs, a bend relief's depth and a channel's proportions are
reported, not judged (no published number verified; `sheet.measured_not_judged`). A cut file's bend lines
are judged at the least any bend needs, not by the bent part's rules, and its reliefs not at all. Hubs's hole-to-bend is stated ("from the start of the bend radius") and read at the tangent line;
only Hubs's flange height is unstated, read from the outside mold line (the rule's note says so).

## Injection molding

`cad <type> dfm SRC --process molding [--pull z|-y|x,y,z] [--wall-limit 45] [--zero-tol 0.05]
[--cavities N] [--material abs|pc|...] [--candidates]`

A STEP, an xbf or a model's document is measured on its B-rep (`cad.build123d._dfm_molding`, its geometry's
numpy in `cad._internal.molding_geometry`); every item is at a face ref (`plate/face 7`) plus `xyz`. A mesh is
refused: its chords misread draft (a 2 deg cone's read 1.998), its regions merge a fillet with the faces it
joins, and its tessellation folds and slivers read as undercuts -- check the STEP or the model. The part is
measured as it stands, no frame of its own put under it: moved, or turned any way with its pull, it is the same
part and reads the same verdict, because what a verdict rests on does not turn with a sample (below).

**The pull.** `--pull` not given is `z`, and the result says so (`pull_given` false; the summary's "the default
pull"). The part is measured along the pull as given, never along one the check prefers: a part that stands
tilted against the pull is measured tilted. But every check of one part of one solid asks whether another pull
does better (`pull_check`, below), and warns, naming it (`pull_better`). An **assembly**'s parts lie as they are
assembled, not as each is molded, so each is judged along its own pull: the one given, unless one of the part's
own directions does better for it (`pulls` says which, `part_pull` warns of each part judged along its own). One
part lying differently does not fail the assembly.

**The verdict.** A warning is a recommendation of a published guide broken, or a cost: the part is made. An
error is what a general molder sends back, measured as the quantity the rule names and the same however the
part is placed. A false error on an ordinary part is worse than a missed warning -- it teaches the designer to
ignore the check -- so the errors are few:

- a feature nothing releases (`molding.undercut_unreleasable`): geometry, no opinion;
- a **broad shell wall with too little draft for its depth** (`molding.draft_zero`): the wall may run
  `DRAFT_FLOOR_DEPTH_MM` (10 mm) along the pull in one mold half with no draft at all, and needs
  `DRAFT_FLOOR_DEG_PER_MM` (0.01 deg) for every millimetre past that, `DRAFT_FLOOR_MOST_DEG` (0.25 deg, half
  the least a guide recommends) at most: 0.1 deg at 20 mm, 0.2 deg at 30 mm. One criterion of draft against
  depth, with no step at `--zero-tol`: a wall leaning 0.07 deg over 30 mm is as stuck as one leaning 0. Depth is
  a mold half's (`half_depth_mm`): a wall on the outline is split where the parting plane stands, a core's wall
  runs whole. Broad is `BROAD_WALLS` (10) nominal walls across the pull, and clearly so (2% over, a
  rolling-ball thickness's own error: a wall at the limit is no broad wall): a boss, a bore, a pin, a standoff,
  a gear's teeth, a snap arm, a rib and a window's sides are not, and a face a slide forms is the undercut's --
  the draft recommendations warn of those;
- a **broad wall too thin to fill** (`molding.wall_too_thin`): under `WALL_FLOOR_SHARE` (half) of the resin's
  recommended minimum (with no resin of the table named, under every resin's), read as the wall's own
  thickness (`broad_wall_mm`: the area median of the face's own rolling balls, never a neighbour's figure and
  never one refined point) on a face that, with the face across it, is at least `BROAD_WALLS` of that wall
  wide. A feature's width is not a wall's thickness: a text stroke, a ridge's crest, a gear's top land, a snap's
  barb, a living hinge's web read thin where they are thin (`molding.wall_min`, a warning) and fail nothing;
- a **part past any press built** (`molding.clamp_beyond_press`): its projected area takes over
  `CLAMP_LARGEST_TONS` (10 000 US tons; the largest injection presses built clamp some 8 000 to 9 000 tonnes)
  even at `CLAMP_LEAST_FACTOR`, a ton per square inch with no margin (`clamp`'s `tons_least`) -- half of the
  lowest tonnage factor published, so the error does not turn on the estimate: over 6.45 m2 a cavity. Where
  the estimate itself (`tons`) passes `CLAMP_LARGE_TONS` (1 000) it is a warning
  (`molding.clamp_large_press`): a press few general molders run.

The last three are **text-to-cad's own floors**: the guides recommend (0.5 to 2 deg of draft, a wall range by
resin) and state no limit, so each floor cites `text-to-cad` as its source, never a publisher, and its rule's
note says what it rests on. A wall over `WALL_CEILING_MULTIPLE` (twice) the resin's recommended maximum is a
warning (`molding.wall_too_thick`): it sinks, voids and cools slowly, and is molded all the same (a 12 mm
cutting board, a light guide). A shop's own limits are read against the measurements.

**Not searched, and not checked.** The search for what releases the trapped features is budgeted (rays and
seconds, below). A feature it did not reach is an undercut all the same -- warned as one
(`molding.undercut`) and counted (`undercuts_unsearched`: "N feature(s) not searched", their refs, what to do)
-- and where the line stands is the trapped area: where the features searched hold at least as much of it as
those not, the verdict is of what was searched (OK or FAILED, with that warning); where they hold less, nothing
trustworthy was judged of the part's release, the rule of features nothing releases says it did not judge them
(`rule_partly_judged`) and the check is NOT CHECKED.

On the B-rep a face's surface is its kernel type, and a B-spline or Bezier face that IS a plane, cylinder,
cone, sphere or torus (within a millionth of its size, 1e-4 mm at most: `_dfm_brep.surface`) is read as that
surface. `extrude(taper=)` flaring outward, a loft between similar sections and many STEP exporters write
analytic walls and their fillets as splines; read as splines, their draft would be sampled, not exact, and
their fillets, ribs and bosses unrecognised.

### Families (`measurements.<family>`)

| family | what | how | items (fields the rules read in **bold**) |
|---|---|---|---|
| `draft` | each wall face's draft along the pull and the way it opens | B-rep: plane exact, cylinder/cone with axis along the pull exact (0 / half-angle), other faces the least over points sampled ON the surface and along its edges (a round tangent to a wall square to the pull reaches 0 on that edge, which no sample inside it lands on) | `location`, **`draft_deg`**, `area_mm2`, **`opens`** (`+pull`, `-pull`, `none` = zero draft, `split` = the parting line crosses it), `surface`, `exact`, `depth_mm`, **`half_depth_mm`** (how deep it runs in one mold half with its least draft: a face on the outline, which the parting line may run anywhere up, split where the parting plane stands, any other whole; a face of one draft its stretch, any other the stretch its least-drafted points span, a point with more draft counting for less -- a dome's rim, tangent to the pull along a line, has none, a boss a hair off the pull its height), `width_mm` (its greatest extent square to the pull), **`broad`** (a wall of the part's shell: at least ten nominal walls wide), `xyz`, **`feature`** (`wall`; `turn`: a face the parting line crosses that only turns through the pull -- a round, a sphere: under a quarter of its area has less than 0.5 deg -- no wall along it, so no draft rule's, where a boss a degree off the pull, `split` too, is a wall and is judged; `rib`/`snap`: a rib's side, judged by `molding.rib_draft`; `undercut`: a face an undercut traps, formed by its release, judged by the undercut rules), `pull_axis` (an assembly's part judged along its own pull) |
| `undercuts` | trapped features and what releases them | points on every face shot along the way their face opens (zero-draft: both ways); blocked = trapped -- but a point whose own normal meets another face within three ray offsets (0.03 mm at most) stands in a **crevice** and is never trapped: stepped off its face to cast its rays it lands in the other face's material (a rib's square end run 0.1 mm into a drafted wall read trapped both ways and unreleasable); the crevices are said (`crevices`). A point on another solid of the same part (two solids touching, not fused) is no surface and never trapped; touching trapped faces = one group, split where its trapped points lie apart (three sample spacings): two snaps under one lid are two features. Release (`molding_geometry.classify_undercut`), the first that holds: (1) plain slides -- the feature's **own directions** in the parting plane (a bore's axis, a slot's run where two of its planes meet, a pocket floor's normal: exact, where the grid is not) and eight round the plane -- the fewest covering it, four at most; among slides freeing as many points, the one whose points are nearest their way out of the part's box (a hole through the -x wall is the -x slide's, though a ray along +x leaves through the hole opposite); (2) with an angled slide: one of its own directions up to 45 deg out of the plane (`angled`); (3) a lifter (a short lateral move then a pull, stroke <= 1/4 part size); (4) a collapsible core (each point freed so, no common direction); else `none` -- no slide is guessed at an angle the feature's faces do not give. One read `none` on fewer than 12 trapped points is sampled again four times as densely beside them and classified on those: under two trapped, it was a sample's reading and is dropped, counted (`unconfirmed_count`) and said (`undercuts_unconfirmed`). `kind` is the geometry's, whatever releases it: `external` where a third of its points have a straight line out of the part along a plain slide or one of its own directions, else `internal`. A slide's `stroke_mm` clears its points one way along the pull (a slide stands in one half: the way that asks less) and runs on to the end of each face it serves where that lies within two sample spacings of the face's deepest point. Depth (`molding_geometry.interference`; against the pull at 48 of the feature's tested points, against a slide at all of them, searched up to 0.2 mm -- past it, "more than"; a pull only compared, not chosen, has no depth against it): per point the least offset square to a way out from which a ray along the way leaves the part, the material between bent past; `depth_mm` against the straight pull (`depth_limited` where 1/4 part size frees none), `slide_depth_mm` against the best slide for one nothing releases. A feature `depth_mm` at most `BUMP_OFF_MM` (0.1 mm, text-to-cad's own figure: Protolabs gives none) deep, or one nothing releases whose lip against a slide is, is `bump_off` (`bump_off_over` the pull or a slide, `interference_mm`) | `location` (the mostly-trapped face), `faces`, **`trapped_area_mm2`**, **`unreleasable_area_mm2`** (the area where `release` is none, 0 where it is released, no figure where it was not searched: not measured), `kind` (external/internal), **`release`** (side_action/lifter/collapsible_core/bump_off/none/unknown), `figures_measured` (false where the budget ran out before its stroke or depth), `depth_mm`, `slide_depth_mm`, `interference_mm`, `side_actions` (`+x`, ...), `side_action_count`, `angled`, **`stroke_mm`**, `height_mm` (along pull), `width_mm`, `blocked_by`, `trapped_faces` (the faces it mostly traps), `confirmed_points`; scalars: `candidate_area_mm2`, `undercut_count`, **`side_action_count`** and `side_action_directions` (the part's distinct slide directions, within a degree: three slots along +y are one side action), `lifter_count`, `collapsible_core_count`, `bump_off_count`, `unreleasable_count`, `unsearched_count`, `unconfirmed_count`, `crevice_count`, `crevice_area_mm2`, `crevices` (each `faces` [a, b], `area_mm2`, `gap_under_mm`, `xyz`) |
| `touching` | solids of one part that touch without being fused | each sampled point stepped off its face classified in the part's other solids (in or on: a contact); parts of 2 to 24 solids | `location`, `part`, `solids` [i, j], `faces`, `contact_area_mm2`, `xyz` (present only where some touch) |
| `thickness` | the wall: nominal, thin, thick, transitions | rolling ball: at each sampled point the diameter of the largest ball tangent there that no surface triangle cuts into (exact per triangle: corners, edges, insides; a needle's inside -- a triangle narrower than a thousandth of its longest side, a tall corner strip's tessellation, whose plane is its corners' rounding -- left to its edges: one held a 0.015 mm ball under a 2 mm wall), capped by the exact ray straight through. Points whose ball is held by a face across a convex edge read low and are left out of medians; a narrow face -- most of its balls so held (rib top, plate end) -- takes its broad neighbours' wall, a face merely narrow reads its own. The 32 thinnest faces are then refined to the exact least distance to a face across (`BRepExtrema_DistShapeShape`; the faces whose box comes nearer than the face's least sampled wall, not its neighbours or a face sharing a corner), where the segment leaves the face within 45 deg of its inward normal, the face across looks on along it and a ray along it meets that face first: a 0.6 mm wall between two samples (a cut grazing a drafted corner) reads 0.6, never its neighbours' 2. The faces whose thickest sampled ball reaches 1.2 x nominal and is under the thick-section limit -- where the verdict could turn -- (32 at most) have that thickest refined over the face: a pattern search over its own (u, v) from its two thickest samples, their trials solved together against the face's neighbourhood, a step halved where none gains 1% of nominal, settled at a hundredth of the face's span or once a ball reaches the limit, trials strictly inside the face and no ball held across a convex edge of it, solved as the samples are -- four alike blind-hole floors read their true 4.0 in every placement (sampled: 2.6 to 3.1, the thick-section count 2 to 5) | `location`, **`thickness_mm`** (area median, or the refined least where thinner), `min_mm` (p10, or the refined least), `refined`, `max_mm`, **`ratio_to_nominal`** (max / nominal), `thin_ratio`, **`feature`** (`wall`, or `rib`/`snap`/`boss`: a feature's face, judged by its own rules, not the wall's range), **`broad_wall_mm`** (the face's own wall -- the area median of its own balls, no neighbour's and no refined point -- where it bounds a broad wall; else none, `not_applicable`), `broad`, `width_mm` (the lesser of its second extent and four times its area over its outline), `across` (the face its wall ends on), `xyz` (the thickest point); scalars `nominal_mm` (area median of the faces' walls), `min_mm`, `max_mm`, `ratio_max_nominal`, `thick_sections` (> 1.5 x nominal) |
| `transitions` | abrupt changes of wall | read on the stepped side (`molding_geometry.steps`): two flat faces facing the same way at two offsets, joined by a chain of at most three faces none parallel to them (a pad's side, a chamfer, a fillet), whose walls differ by a quarter of the nominal or more and by about their offset (one face behind both: not a rib's top, not a wall's rim); its run is the chain's reach across, square to the faces, from one seam to the other. A free-form face no step takes in: the rolling ball's steepest pair of points within four sample spacings whose walls differ by half the nominal (`basis` `ball`) | `location` (the chain's first face), **`transition_ratio`** (run over the change: a vertical step 0, a chamfer its run over its rise), `min_mm` and `max_mm` (the two walls), `change_mm`, `length_mm` (the run), `basis` (`step` or `ball`), `xyz`, `at_xyz` (a point on each seam) |
| `ribs` | thin slabs standing on a wall | two opposite planar faces (within 12 deg) whose inward rays come out of each other, both meeting one base plane at a concave edge or a concave fillet, height >= thickness, length >= 1.5 x thickness; base = the plane it is shortest from, but never another slab's side where there is another base: ribs that cross stand on the floor, not on each other (two 4.8 mm apart and 6 tall read the crossing rib's 1.2 mm as their wall). Its ends (faces joining both sides, no wider than the rib) are its roots too: their fillets are the rib's, not corners, `base_fillet_mm` is the least of sides' and ends', `draft_deg` the least of sides' and ends', and in `draft` they are the rib's faces (`feature` rib), judged once with it. A rib a trapped face touches (one of its own, or one beside them no larger than its side, not its base) is a snap arm, the face its barb. | **`kind`** (`rib`, `snap`), `barb`, `ends`, **`thickness_ratio`** (root / base wall), **`height_ratio`** (height / wall), **`height_to_thickness`**, **`base_fillet_ratio`** (fillet / rib), **`base_fillet_wall_ratio`**, **`gap_to_thickness`**, **`gap_to_wall`** (gap = median ray to the next face), **`draft_deg`**, `thickness_mm`, **`height_mm`**, `length_mm`, `base_fillet_mm` |
| `bosses` | cylindrical stands, cored or solid | a convex cylinder, or a cone drafted 5 deg or less, standing on a plane square to its axis (concave edge or fillet), with the largest coaxial concave cylinder or cone inside it reaching half its height; radii at the base | `od_mm`, `id_mm`, `boss_wall_mm` (R - r, or 2R solid), **`wall_ratio`** (boss wall / base wall), `od_to_id`, `height_mm`, `height_to_od`, **`base_fillet_mm`** (its root's: 0 sharp), `hole_floor_above_base_mm` |
| `corners` | internal corners | every concave edge with no fillet (radius 0, `edge` ref) and every concave fillet with two tangent joins: a cylinder's or torus's radius, a free-form blend's from its curvature at its middle (concave where its sampled normals turn toward each other); rib (sides and ends) and boss roots excluded | `radius_mm`, `sharp`, **`ratio_to_wall`** (radius / thinner wall meeting there), `wall_mm`, `edge`, `angle_deg` |
| `projection` | area along the pull | the part triangulated (each triangle naming its face), projected, cells covered on a raster 2000 across the part | per part: **`projected_area_mm2`**, `area_error_mm2` (half the outline's cells), `raster_resolution_mm`, `depth_along_pull_mm`, `span_major_mm`, `span_minor_mm`, `volume_mm3` |
| `envelope` | size against a mold | from the projection and the parting | per part: **`span_major_mm`**, **`span_minor_mm`**, **`depth_along_pull_mm`**, **`depth_from_parting_mm`**, `volume_mm3` |
| `parting` | flat parting plane? | outline pieces within 3 cells of the projection's OUTER outline (a hole through the part along the pull is a shut-off: its rim is no parting line): edges where a +pull face meets a -pull face, zero-draft walls (the line may run anywhere up them), curved faces turning through the pull (sphere centre, horizontal cylinder axis, ...); undercut faces left out (a slide forms them). Flat when every edge/turn is level at one height every wall spans | scalars `flat_parting_possible`, `parting_plane_height_mm`, `parting_plane_range_mm`, `depth_above_mm`, `depth_below_mm`, `depth_from_parting_mm`, `off_plane_count`; items: `kind`, `low_mm`, `high_mm`, `on_plane` |
| `clamp` | clamp force estimate (added by the type side) | area (in2) x factor (tons/in2, Moldminds by resin; unknown: 2-5, estimated at 3) x cavities x 1.15 | per part **`tons`**, `tons_low`, `tons_high`, **`tons_least`** (at a ton per square inch, no margin: the floor's), `kN`, `tonnes`; `factor_source` |
| `pulls` (`--candidates`) | x, y, z and the part's own directions that are none of them (`face0`..: the three directions most of its surface is square to or turns about -- its planes' normals, its cylinders' and cones' axes; `principal0`..: its principal axes of inertia, less one whose moment another shares, which is any direction of their plane -- a cube's three, a round part's two) ranked (`molding.ranked`: fewest unreleasable, fewest actions, least undercut area, least zero-draft area -- areas within a hundredth of the largest wall tie -- a flat parting first, then the most draft at its least) | the families above per axis (fewer samples) | `undercut_candidate_area_mm2`, `undercut_count`, `side_action_count`, `lifter_count`, `unreleasable_count`, `unsearched_count`, `zero_draft_wall_area_mm2`, `min_wall_draft_deg`, `flat_parting`, `projected_area_mm2`, `depth_from_parting_mm` |
| `pull_check` | does another pull do better than the one measured? (one part of one solid; of an assembly, each part's is in `pull_checks`) | `chosen` is the report's own figures for the measured pull -- one reading of it, never a second. The part's own directions (as `pulls`' `face*` and `principal*`: the same whichever way the part lies in its model, each pointing the way its surface lies from its mass, where the world's x, y and z are whatever the model made them) are read on the same sampled points, each only as far as it can still do better (`molding.dominates`: fewer features nothing releases decides, whatever else -- that pull turns a part that cannot be molded into one that can, though it takes a lifter more; with as many, no worse in actions, trapped area, zero-draft wall and a flat parting -- areas within a hundredth of the wall tie -- and better in one): its draft first (no ray), then what it traps, then what releases that, then its parting (`measured`: draft, trapped, released, full). A pull nothing can beat -- nothing trapped, no wall without draft, a flat parting -- reads no other pull at all | `chosen`, `candidates` (each `pull` -- `x` where it runs along the world's, else `face0`, `principal1` --, `axis` in the world, `measured`, the figures read so far), `better` (the name of the first that does better as `ranked` ranks them, or null), `note` |

Beside the families: `projection`, `scale`, `pull_given` (false where no `--pull` was given and the
default, z, was measured) and, of an assembly, `pulls` (each part's `axis` and whether it is its `own`). A ray
the kernel cannot intersect with a face loses that crossing alone, and the faces it cost are the family's
`unmeasured_faces`. Every finding names whole refs (`refs`: each resolves with `cad step inspect`), a fact
finding as a rule's does. Fact findings: `zero_draft_walls` and
`undercut_candidates` (both **info**: sums of what the rules judge per face and per feature, each naming the
rule that judges it; the second counts the part's side actions by direction),
`pull_better` (warning: another pull does better than the one measured, named with its axis and both pulls'
figures, the hint its `--pull`, its refs the faces the measured pull falls by; it says where the measured pull
was the default), `part_pull` (warning: a part of an assembly judged along its own pull, at the part's ref),
`crevices` (warning: where two faces stand closer than steel can stand between them -- no undercut, but the
mold's steel there is a knife edge; the samples that met one say where one is, not every one there is),
`undercuts_unsearched` (warning: the features whose release the budget did not reach, counted, at their refs;
see **Not searched, and not checked**),
`undercuts_unconfirmed` (info: places read trapped on a few points and not again on denser ones, counted),
`rays_unintersected` (the undercut figures are a lower bound there), `several_bodies` (warning: several
parts, every occurrence counted, are an assembly, each part measured on its own along its own pull, at the
parts' refs; a part of several solids is
every process's `several_solids`, which says here that they shadow each other and that their contacts --
`touching`, each pair with its area and faces -- are left out of draft and undercuts),
`stepped_parting` (warning, at the outline's pieces off the plane; a face turning through the pull is read at
its silhouette on the surface -- a cone's or a cylinder's axis square to the pull, a free-form face's where its
normal turns through the pull -- so a part split along its axis parts flat), `resin_unknown` (info),
`clamp_estimate` (info), `thickness_unmeasured`.

### Rules

`cad._internal.dfm.molding.RULES` (above: the table is not copied here). The guides give recommendations:
Hubs's injection molding guide, Protolabs' design guidelines (its wall table by resin and its draft table),
its uniform-wall and bump-off tips, Xometry's rib guide -- warnings. Beside them stand the floors, errors: a
feature nothing releases (the guide's own), and text-to-cad's own (`rules.OWN`: its message never names a
publisher as the source of text-to-cad's number) -- **The verdict**, above, states each and what it rests on.

One face, one rule: a wall's draft rules judge a wall's faces, a rib's sides are `molding.rib_draft`'s, a
face an undercut traps is its release's, and a face the floor fails is not warned of the recommendation too
(`molding.draft_min` beside `molding.draft_zero`, `molding.wall_min` beside `molding.wall_too_thin`). An
undercut is judged by what releases it: a side action, a lifter or a core is a warning (tooling cost), a lip
of at most `BUMP_OFF_MM` stripped as the part ejects a warning of its own, and a feature nothing releases an
error; one whose release was not searched is warned as an undercut and counted. A lone rib has no gap to
judge, and says so (`not_applicable`). The clamp force is an estimate: Moldminds' tonnage factors by resin
(`CLAMP_FACTORS`), else the usual range; the two rules on it are text-to-cad's own.

No rule judges a mold, or a press short of the largest: the part's projected area, its spans, its depth from
the parting line, its shot volume and its side actions' travel are a shop's, read against the measurements
(`projection`, `envelope`, `undercuts`' strokes) and the clamp estimate.

The wall table by resin (Protolabs', in inches, converted to mm): ABS 0.045-0.140, acetal 0.030-0.120, acrylic 0.025-0.500,
LCP 0.030-0.120, nylon 0.030-0.115, PC 0.040-0.150, polyester (PBT, PETG) 0.025-0.125, PE 0.030-0.200,
PP 0.035-0.150, PS 0.035-0.150, PPS 0.020-0.180, polyurethane 0.080-0.750, long-fiber reinforced 0.075-1.000 (HDPE and LDPE read
polyethylene's row; PBT and PETG its "Polyester" row). A resin with no row (PC/ABS, TPU, glass-filled nylon,
PEEK) has no range: `resin_unknown` says its walls are not judged by resin, and only the no-resin floors apply.

A figure at its limit is at it, not past it: a ratio a rule reads (a corner's radius over its wall, a rib's
thickness over the wall it stands on, a section over the nominal wall) is of lengths at the precision they are
measured to, a micron -- a 1 mm fillet on a wall that reads 2.00001 is a ratio of 0.5, Hubs' limit, not 0.499997.

### What it cannot measure

- A mesh at all (STL, 3MF, GLB): refused, check its STEP or model. A free-form fillet's radius is read at its
  middle (a variable one reads one figure).
- Texture draft (no texture option), tall-feature extra draft (Hubs +1 deg / 25 mm over 50 mm), shut-off
  draft (3 deg) -- the rule set's note says they are not judged --, stripping undercuts (lead angle, 5% of
  diameter), a snap's barb, living-hinge proportions,
  threads, boss OD against a screw (no screw size), gating, weld lines, filling, cooling, warpage, shrinkage.
- The pull is the one given: a part tilted against it is measured tilted (a square box half a degree off the
  pull reads its walls drafted a third of a degree, half of them the wrong way: the recommendation's warning
  and an undercut, where the box straight fails the draft floor -- graded, never a clean pass). `pull_better`
  names a pull that does better where one of the part's own directions does; no other is looked for.
- A part that occurs several times in a document is measured each way it stands: the occurrences turned alike
  once (`projection.items[i].occurrences`), and the totals -- the projected area, the volume, the clamp force
  -- count every one of them.
- The undercut test samples points (2400 per part, at least 12 a face): a feature smaller than the point
  spacing can be missed; the lifter stroke is capped at a quarter of the part; a slide is tried along the
  feature's own directions (its cylinders' axes, its planes' normals and the lines they meet along) and eight
  round the parting plane: a free-form pocket that opens along none of them reads `none`. A crevice is found
  where a sample meets one, not everywhere one is (so its warning can come and go with the part's placement;
  no verdict does).
- A side action's travel is to where its points clear the part one way along the pull, not including the
  slide's own clearance.
- A component model whose contacts are fused into one solid with its housing (a KiCad connector) reads its
  pins as walls and ribs and its contact slots as undercuts: check the housing alone. Contacts kept as their
  own solids are said (`several_solids`).
- Clamp force is the part's projected area alone (no runner), a molder's factor table, not a resin's cavity
  pressure.

### Budgets

Each face's points are chosen by area before they are mapped to the surface, about 6000 a part; wall thickness is
read at a fixed number of points whatever the face count (a small face of a part of thousands takes its broad
neighbours' wall); rays along one direction look up a grid of the faces' box shadows. A face of twelve edges
or more is crossed with the kernel's fast classifier alone (`_dfm_molding._Fast`): with its boundary tolerance
the kernel sorts each crossing among every edge anew, a millisecond a ray on a wall of a hundred holes, whose
every hole is a feature to release -- minutes, then hours; a crossing within the kernel's tolerance of such a
face's edge is the neighbouring face's.

The search for what releases the trapped features spends, on one pull over every part, at most 200000 rays
and 45 seconds of searching (`_RELEASE_RAYS`, `_RELEASE_SECONDS`; finding what is trapped is none of them: no
budget cuts it short), largest features first, and spends them on verdicts
before figures: first every feature is asked what releases it (a ray a point along each slide), one nothing
releases read in full at once (it fails the part: no budget cuts it short); then, while the budget lasts, the
released features' strokes and depths (`figures_measured` false where it ran out: the feature keeps its
release, a lip under `BUMP_OFF_MM` then reads as the slide it would take). A feature the budget ran out
before reads release `unknown`, is counted in `unsearched_count` and warned (**Not searched, and not
checked**). Rays bound the search alike on every machine; seconds bound it whatever a ray costs, so a slower
machine may leave figures, or features, a faster one reads. Among slides freeing about as many points
(within a fiftieth) and as near their way out (within a tenth), the first in the order they are tried is taken,
+x before +y. The pull check reads the other pulls on the points already sampled, each only as far as it can
still do better -- nothing for a pull no other can beat, a draft pass (no ray) for one whose candidates leave
more wall without draft -- and its candidates share one budget more: one it ran out on is never named. Each part's projection
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
| `solid` / `mesh` | per part: `solids`, `shells`, `closed`, `inner_shells`, `sound` (the kernel's boolean-argument check, `issues` its BRepCheck codes and `BOPAlgo_CheckStatus` names -- `BOPAlgo_SelfIntersect` --, `faulty_faces` every face it names, a faulty edge's or vertex's faces too; the finding says them all), `volume_mm3`; scalars `body_count`, `volume_mm3`, `watertight`, `sound` | `mesh`: read and cleaned (`cad.trimesh._mesh`: welded, collapsed triangles, doubled slivers and zero-area debris dropped, folds laid flat -- two triangles side by side in one plane wound against each other, an exporter's fan folded back over a concave boundary, the planar region triangulated again from its boundary, `folds_laid_flat`; a mesh with none is not changed --, a tessellation's cracks closed), its bodies split with no repair; `watertight` judged per body (`open_body_count`, `open_bodies` with each one's `xyz` and `boundary_edges`), `volume_mm3` the closed bodies' (a body wholly in another's material counted once: `bodies_inside_another`), `body_count`, what the gate repaired (`duplicate_faces_dropped`, `faces_rewound`, `shells_turned`), and `self_intersecting`: the closed bodies whose surface passes through itself -- of a raster of 120 lines a side up through the body, more than a stray one (2, or one in 500) enters material it is already in (`meshops_printing.doubled`: an extruded pentagram's centre is wound twice), the validity the kernel checks on exact geometry (`not_sound`) |
| `overhangs` | per down-facing face off the plate: `angle_deg` (a plane's exactly, a curved face's least over its samples), `area_mm2`, `area_below_limit_mm2`, `height_mm`, `kind`: `slope`, `bridge`/`cantilever`/`ceiling` (a flat face, see `bridges`), `hole` (a hole's arch), `plate_edge` (a round or chamfer on the plate's edge whose under-limit part is within 1 mm / 5 layers of it); `reach_mm` (a flat face's, from `bridges`); `counted`: false for a face too small to need support -- under `OVERHANG_AREA_MM2` (1 mm2) below the limit, or a cantilever reaching less than the nozzle's width (`--nozzle`, else `OVERHANG_REACH_MM`, 0.4 mm) -- which no rule judges (both floors text-to-cad's own: no guide states them, and the family's `method` says so); an angle within 1e-6 deg of the limit is at it (`ANGLE_EPS`: a kernel's 45 deg chamfer reads 44.999999999999936); scalars `down_facing_area_below_limit_mm2` (the counted faces, holes, bridges and plate edges aside), `area_floor_mm2`, `reach_floor_mm` | connected regions of the triangles under the limit, same fields and floors; a region that reaches the plate, or runs on into down-facing triangles that do (a round's lowest row), and stays within the plate band is `plate_edge`; `down_facing_area_below_limit_mm2` counts the counted regions, bridges and plate edges aside, as the exact path does. A triangle is a chord of its surface, and its angle is the surface's only within the mesh's own turn there (**the mesh's angular tolerance**, `meshops_printing.Smooth`: each triangle's corners carry the surface's normal as the mesh knows it -- the mean, by the angle each takes up at the corner, of the triangles round it that turn from the triangle's own by under `FACE_DEG` --, the same angle is read off them, and `SPREADS`, 2, times the difference, at most `CHORD_CAP_DEG` (3 deg: what a curved surface's chords turn an angle by -- a cone meshed in 8 segments reads its 45 deg 2.3 deg off), is the reading's tolerance, with the coordinates' own noise; measured against exact cones, a sphere and a torus at 0.05 to 0.5 rad of deflection, and tested: every triangle of a 45 deg cone holds 45 within its own. A **flat face's** triangle is no chord and carries its own normal: the triangles of one plane (joined across edges with no turn, `COPLANAR_DEG`) are a chord only where the surface runs on past the plane on two sides -- the faces beside it within `FACE_DEG` turn from it opposite ways, as the chords either side of a chord do; a plane with such a neighbour on one side alone is flat, so a 30 deg face that meets a 55 deg one reads 30, an overhang as on exact geometry, never "at the limit"): a region none of whose triangles is under the limit by more than its tolerance is at the limit, no overhang -- a 45 deg cone's triangles read 44.3 to 45.4 deg --, its area `at_limit_area_mm2` (`at_limit_tolerance_deg`: the largest tolerance of those triangles), said (`mesh_at_limit`); a round, whose rows run on down to 0 deg, is an overhang with its rows just under the limit too. Regions with at most `OVERHANG_JOIN` (3) down-facing triangles of each other are one region (a scan's noise breaks one underside into hundreds of islands: one finding). A span is read only where a verdict turns on it -- a flat region or an arch of at least the area floor --, the largest first, within `SPAN_PAIRS` point-to-support distances (at most `SPAN_SUPPORTS` of a region's supporting edges); a region past it is counted (`spans_not_measured`) and the check is not checked |
| `bridges` | flat (< 5 deg) down-facing planes: `kind` `bridge` (the farthest point lies within the convex hull of its supports: `length_mm` = twice the farthest distance to a supporting edge = the span between the walls), `cantilever` (beyond one support: `length_mm` = its reach), `ceiling` (none); supporting edges are the concave edges whose other face descends. A horizontal hole's arch is no bridge (each layer stands on the one below but the crown's): `printing.horizontal_hole` judges its diameter | the flat regions, and a region carried on both sides that is flat or an arch -- curved one way alone, its normals in one plane: a hole's crown (a mesh has no axes) --; a dome carried all round (curved both ways: a hollow sphere's top) is a slope by its least angle, as the exact path reads a curved face, and so is a plane tilted past flat |
| `wall_thickness` | per face, the thinnest exact ray into the material from its samples, `sampled: true` (a face's thinnest sample, which can read above the exact least thickness between samples: a keycap's 0.6129 against 0.5493). A ray counts where the face it lands on looks back along it, its normal there within 45 deg of the ray (`KNIFE_DEG`), whether or not that face shares an edge with the ray's own: past it the ray measured a corner (a rim whose sides meet at 50 deg reads alike on both paths, and a sharp 50 deg tip as the same tip blunted by 0.0001 mm). One landing on a face that shares an edge with its own within `SEAM_HIT_MM` (0.05 mm) met the seam and is dropped; a ray inside a knife edge's `thin_depth_mm` that starts or lands on one of the knife's two faces (its flanks) is that knife's sliver -- from a flank, or from a face meeting them at the knife's end across to one -- reported by `knife_edges` alone, while a ray near it between two other faces (a fin beside the knife, across itself) measures its own wall; The listed items under 5 mm are refined to the exact least distance to the face across (`BRepExtrema_DistShapeShape`, `brep.least_segments`, as CNC's are) where it leaves the face within 45 deg of its normal, the face across looks back along it within 45 deg and an exact ray along it meets nothing before that face (but a face both meet, which the least runs along: a groove's floor): `refined` true, `xyz` the thinnest point (faces sharing an edge or a corner, parallel planes and faces of over 16 edges keep their sampled figure); `min_mm` is the thinner of the field's and a refined item's. A face turned exactly 45 deg from a ray is at the limit, not past it (`ANGLE_EPS`), as is a knife edge's 45 deg: a 45 degree gusset reads the same in every placement. `thickness_mm`, `opposite`, `supported` and `joined_sides`: a wall under the rules' unsupported minimum -- the only walls a verdict can turn on -- has its support **read off the wall itself**, the same on both paths (`meshops_printing.wall_support`: the wall's **thin region** is laid out from the middle of the wall under its thinnest place -- its refined least on exact geometry --, places a spacing apart (half the thickness; four times that where the region has more than `_WALL_PLACES`, 384, and again), each a step on in the wall's own plane, put back in its middle and turned with it, a curved wall followed, for as long as the material across stays under twice the thickness; the region's **outline** is every step that leaves it: joined where the material across grows past that or the region comes round on itself -- a ring --, free where the wall ends in a face across the way or thins away. Supported is an outline with nothing free (a skin over a cavity, a tray's floor), a ring (a tube's wall), joins along no one straight line (a floor and a side wall round a corner; the land a countersink leaves, joined to the plate round its whole rim, at both holes and on both paths) or joins along one line with the region's middle between them (a web between two posts); joins along one line with the region to one side are one side -- a fin on its base, a pin on its foot --, none is none; `free_fraction` is the share of the outline that is free; a region no spacing holds reads `supported` null). A pin is a wall too, joined on one side, its thickness its diameter, as a mesh reads it: the wall minimum is its floor and the pins' rules their guides' own figures for it. `lying`: the way across the wall, between its two faces' normals (so a land between a countersink's cone and the flat under it is one skin from either face), is within 45 deg of the plate's axis (a floor, a lid, a living hinge: laid layer on layer, which FDM judges by its layers), any other its edges' count (joined on 2+ sides: the face's or its opposite's concave edges, smooth joins into a concave round, or a closed ring: `_connections`); scalars `min_mm`, `p05_mm`, `p25_mm`, `median_mm`, `max_mm` | per body, `--samples` rays from points at random over the surface, and on a mesh of at most `COVER_MAX_TRIANGLES` (5000) triangles one more from every triangle's centre (`cover: true`; on 60 real meshes the pass cost 26 times the family's time and found 3 thin places against 9 that are not there, while under 5000 triangles it found a knob's 0.27 mm web 2000 random rays miss, with no false one), each measured from the surface (its origin's `NUDGE`, 1e-4 mm off its triangle, added back: a 2 mm wall reads 2, as the gaps' rays do); a ray counts where it lands on a face turned toward it (within 45 deg) and is no knife's sliver: inside a knife's thin depth, starting or landing on one of its flanks (the triangle's normal within 20 deg of a flank's, `FLANK_DEG`). a far face at 45 deg is at the limit within the two triangles' own tolerance (the angle read again off the surface's smoothed normals at the ray's two ends). Items one per face of the part (triangles joined by edges whose normals turn under `FACE_DEG`, 30 deg) and the face its thinnest ray lands on -- one fin is one item, read from its two sides, as on exact geometry --; one sampled under twice the unsupported minimum is refined to the least wall about its thinnest sample (`_least_wall`: steps across the surface, halved where none is thinner, out of every knife's sliver; `refined`: the skin over a round cavity, 0.3 mm at one point, read 0.5 from 600 rays; the 200 thinnest of a body, `REFINE_READ`), and one under the minimum has `supported`, `joined_sides` and `free_fraction` read off the wall as the exact path's are (the 24 thinnest of a body; any other `supported: null`), `lying` as on exact geometry, `chord_mm` (how far its thinnest ray's length may be off the wall the mesh stands for: at each end of the ray the surface's offset from its chord, the point's Phong projection onto its triangle's corners' tangent planes halved -- exact to second order at a chord's middle -- each corner's normal its surface's, the faces about it turning under 30 deg; the two ends' offsets summed with their signs, so a tube's concentric rows of chords, one convex and one concave, cancel where they lie alike; 0 on planes), `at_limit` (the type side's: under `printing.wall`'s limit by no more than `chord_mm`); `min_mm` .. `max_mm`, `samples_valid` and `thinnest_samples` are of the same rays as the items, per body too; `method` says which rays ran |
| `gaps` | per face, the narrowest exact ray out of the material to another face of the same solid (not a neighbour, not the same hole; what lies between two solids of one part is their clearance) that looks back across it, its normal within 45 deg of the ray's way back (`KNIFE_DEG`, as a wall's far face is turned: a V groove wider than that -- a thread's 60 deg -- is a notch, no slot), up to 3 mm, each pair once, refined to the exact least distance as the walls are | one ray out of every triangle to a wall of the same body that looks back (within 45 deg, as on exact geometry), none landing on a triangle sharing a corner with its own or on a face (`FACE_DEG`) sharing an edge with its own: an acute crease inside a letter closes to nothing there, no slot, as on exact geometry; one item a slot: the faces its rays join, and the faces beside them that have such rays, are one gap, its narrowest ray refined to the least about it (`_least_wall`, as a wall's: a slot's narrowest is seldom under a triangle's centre; gaps sampled under `REFINE_GAP_MM`, 2 mm); a gap whose rays cross a round hole is a hole (`holes`), no gap; under `GAP_DEFECT_MM` (0.05 mm) faces lie on faces -- doubled or overlapping triangles, the mesh's defect -- reported once as `overlap` (`mesh_overlap`), never an item |
| `holes` | concave cylinders round one axis covering >= 250 deg: `diameter_mm`, `depth_mm`, `orientation` (vertical < 10 deg, horizontal > 80 deg, else inclined), `through`, `teardrop` (horizontal and no material within 15 deg of the top), `channel` (depth >= 5 d), `coverage_deg` | the gaps whose rays cross a round hole (`_round_hole`: all as long within 5 %, from all round one axis -- no arc of 110 deg without one, the exact path's 250 deg --, meeting on it: an annular groove's rays do not): `diameter_mm` (the rays' length with the sag of the hole's chords given back), `axis`, `orientation`, `teardrop` false; holes up to the gaps' reach (`read_below_mm`, 3 mm: past every published minimum hole), so `printing.hole_diameter` judges a mesh's holes as a STEP's; a larger hole is read as what it is to a printer, its crown an overhang or a bridge of its span |
| `pins` | convex cylinders the same way: `diameter_mm`, `height_mm`, `aspect_ratio` (a pin is one of the walls too: joined on one side, the wall minimum its floor) | not measured (no axes); a pin is one of the mesh's walls, as on exact geometry |
| `details` | a side face of any surface (a plane, a round corner's cylinder, a dot's, a letter's spline) whose normals lie square to a parallel top (its convex edge) and bottom (its concave edge) at most 2 mm apart, narrower than `DETAIL_ACROSS_MM` (3 mm: text, a logo, a mark; a wider step -- a groove, a land, a ledge -- is the part's geometry), whose steps bound its raised top or its sunk floor all round (an island or a pocket; a step that runs on across a face from edge to edge -- a hinge knuckle's shoulder, a ledge -- is the part's geometry, which the walls and gaps judge): `emboss` where it is narrower through the material (the side's rays in) than across the air (its rays out), else `engrave`; `height_mm` (the step), `width_mm` (that narrower extent) | not measured |
| `clearances` | each pair of bodies -- parts, and the solids of a part of several (`parts` names them: `pair (solid 1)`) -- within 5 mm: exact `distance_mm` (BRepExtrema), `kind` `gap`/`contact`/`overlap` (`overlap_mm3` by boolean), `parts` | each pair of bodies (a void's shell is its solid's own -- the smallest solid that holds a corner of it, so a captive ball is no overlap and its shell's wall is measured --, slivers dropped). First whether one's corners, read a hair inside their own body, lie in the other's material: `overlap` (bodies that only touch share no inside), with `inside` and `inside_volume_mm3` where every corner does -- a body wholly in another, read before any distance, its volume counted once. Else the least distance, bounded (`_least_between`): each body is points in a tree (every triangle's centre, a grid across the large ones, and its corners as probes), a probe's nearest of the other's points bounds its distance from above and, less what the points leave uncovered, from below; where the bodies may come within `CLEARANCE_EXACT_BELOW` (1.5 mm) the probes that could hold the least are measured against the triangles near them exactly, nearest first, until none left could be nearer or `CLEARANCE_PAIRS` (3 million) distances are spent: then `exact` is false and `uncertainty_mm` says how much less the distance may be, and where a limit lies between the two the type side leaves it unjudged (`distance_mm` null, `distance_at_most_mm`, `clearance_bounded`): not checked |
| `trapped_volumes` | cavities: every solid's inner shells exactly (`exact: true`, volume from the shell, whatever its size), and from a voxel field (<= 1.5 M voxels) **air wider than its way out** (`meshops_printing.cavities`): for every ball radius up to r = clamp(0.2 x smallest side, 3 voxels, 6 mm), a voxel at a time, the air the ball fits in is flooded from outside, and what it fits in and the flood does not reach is a cavity where it holds a ball two voxels larger still -- found at the least radius that encloses it, whatever its shape: 40 x 40 x 6 mm of air behind a 2 mm vent is a cavity as a hollow sphere is; an opening the largest ball leaves by (over 2 r wide) is a pocket's mouth, no cavity. `sealed` (none found, and no inner shell: one the voxels read sealed that is no shell has a way out under a voxel wide -- one opening of at most the pitch, `escape_hole_at_most`, never no opening), `escape_holes` (each run of an exact hole along its axis with one end in the cavity and the other outside -- one cut through two opposite walls is two holes -- plus every other opening, where the cavity's air meets the outside's, its throat measured on the triangulation: stations half a voxel apart along the passage, each a fan of 32 rays square to the walls' own line, the point moved away from its nearest wall half the way to the one across from it, the least the largest ball that goes through -- a slot longer than the rays reach is read across its narrow way, so a 2 x 12 mm vent is 2 mm), `escape_hole_diameters_mm`, `min_escape_hole_mm`, `escape_hole_uncertainty_mm` (a round wall's chords stand inside its circle: under the limit by no more is `escape_at_limit`, at the limit), `min_wall_mm` (the wall samples whose outside lies in the cavity), `volume_mm3` (the surface's own voxels round it half counted), `inscribed_mm` | the same field and throats, measured on the mesh's own triangles (a 2 mm vent reads 1.998, a 4 mm one 3.996); `min_wall_chord_mm`, how far that thinnest ray's length may be off the wall the mesh stands for (under the limit by no more is `wall_at_limit`, at it); every sealed void's own shell exactly (`_bodies`: a closed shell wound inward, in a solid's material), as a solid's inner shells; on a mesh with an open body a cavity's openings may be the mesh's own holes, so `sealed`, `escape_holes` and their sizes are not measured (None, `openings_not_measured`) and the escape-hole rules read so, never a count of 0 or a 0.53 mm "hole" |
| `knife_edges` | convex edges whose material angle, read along the edge (`brep.edge_angles`: a curved edge at 17 points, its least then found between the samples either side by golden-section search -- a rod cut 25 deg off its axis reads 25.0 on every technology --, then every quarter of its thin depth; an edge where a cone meets a sphere runs from 63 to 42 deg), falls under 45 deg (`knife_below_deg`): `location` the edge ref (`lip/edge 14`), `faces`, `angle_deg` (the least), `length_mm` (the stretch under 45), `edge_length_mm`, `thickness_mm` 0, `thin_depth_mm` = min wall / (2 tan(angle / 2)) (how far in the material stays under the rules' unsupported-wall minimum, `min_wall_mm`; at most `THIN_DEPTH_CAP_MM`, 10 mm, past which the sliver is a fin the walls read; none under `FOLD_DEG`, 2 deg), `thin_area_mm2`. Why 45: that depth is half a wall at a 90 deg corner (one bead), 1.2 walls at 45, 1.9 at 30; 45 deg is also the guides' self-supporting chamfer. The sliver is the knife's alone: the walls drop the rays inside each stretch's `thin_depth_mm` that start or land on its two faces. A tip at the limit (45 deg within `ANGLE_EPS`) is such a zone too, though no knife, so 44 deg is a knife and 45 and 46 nothing, never a thin wall; and a curved edge's stretch over the limit up to `ZONE_DEG` (90) drops the rays from one of its faces onto the other within its thin depth (its faces curve, so such a ray can look back: a tip's own sliver is never a wall, as a 46 deg wedge of two planes reads none) | convex creases between triangles of material under 60 deg (`CREASE_DEG`) and at least `FOLD_DEG` (2 deg: a sharper crease is a fold of the tessellation, two triangles doubled back, whose depth would reach anywhere -- a 0.227 deg one on a watertight shin wiped every wall ray within 201 mm), chained by shared corners; a chain is a knife where its angle, its creases' median by length (as the exact path reads an edge at its middle: a curved 41 deg edge meshes as creases of 4 to 58 deg), is under 45 deg by more than its own tolerance (the same angle read off the two faces' smoothed normals at the creases' ends, as an overhang's is: `_crease_slack`), however short: the tip of a 1 mm plate and the corner of a letter engraved 0.6 mm deep are edges as short as that, knives as on exact geometry, and their slivers no wall's; same fields at `xyz`. Every chain is the walls' zone, a knife or not: at the limit or under it, every ray in its depth from or onto a flank; over it, a ray from one flank onto the other alone -- so a 45 deg cone's rim, whose creases read 44.5 to 45.2, is neither a knife nor a hair of a wall; a chain within its tolerance of 45 is counted (`at_limit_count`, `at_limit_length_mm`) and said (`mesh_at_limit`). The walls leave each crease's own sliver to it: every crease its thin depth at the angle of the creases within the chain's depth of it (their median by length), so a curved knife running from 25 to 60 deg is as deep at its tip as its 25 deg says |
| `build_volume` | how the document fits the volume lying the best way (`meshops_printing.lie`, on its hull): stood up along each axis it is drawn on, each of its hull's 12 largest flat sides and its points' principal axes, turned about that upright every quarter degree, at its outline's edge directions and twice more closely about the best -- and, where it fits none of those ways, tilted along 150 uprights spread over the half sphere, so a part said not to fit fits no way found; a bed has no preferred diagonal (a 950 mm rod lies across a 900 x 600 bed's corners) and the fit does not turn with how the part stands: `fill_ratio` (the largest of its sizes over the volume's: <= 1 fits; within 1e-6 of 1 is 1), `fits`, `upright`, `turn_deg`, `volume_upright`, `as_placed_fill_ratio` (its box as drawn), `tight_box_mm` and `max_dimension_mm` (its tightest box so found and that box's longest side: the part's length, however it is turned), `bbox_mm`, `volume_mm`, `volume_origin`; where the volume is the typical machine assumed, the largest the same page lists too: `largest_volume_mm`, `largest_fill_ratio`, `fits_largest` | same |
| `bed` | planar faces facing -Z on the plate: `contact_area_mm2`, `contact_length_mm`, `footprint_mm`, `contact_ratio`, `sharp_bottom_edges_mm`, `holes_on_plate` | contact triangles; `holes_on_plate: null` |
| `stair_stepping` | per face, the area between 0.5 and 20 deg from horizontal: `angle_deg`, `cusp_mm` (layer cos angle), `step_width_mm` (layer / tan angle), `facing`; `area_by_angle_mm2` | regions of such triangles |
| `support_volume` | column fill under every down-facing surface under the angle limit, down to the part or the plate, from a raster (<= 90 000 columns) of the triangulation along Z -- but under the triangles of a face that is nowhere under the limit (exact geometry: read on its samples) or of a region at the limit (a mesh): a 45 deg cone's chords read 44.3 deg and need none --: `estimated_support_volume_mm3`, `support_contact_mm2`, `support_contact_cosmetic_mm2` (faces of 5% of the part's area or more, holes aside), items per face touched | same raster |
| `sections` | the largest ball each part's material holds (voxels, up to 12 mm: `at_least`), `max_cross_section_mm2`, `max_cross_section_z_mm`, `largest_section_change_mm2` | same |
| `scale` | `bbox_diagonal_mm`, `units_suspect` | unchanged |
| `orientations` (`--candidates`) | the six axis orientations plus up to four of the largest flat faces laid down: `support_volume_mm3`, `support_contact_mm2`, `support_contact_cosmetic_mm2`, `build_height_mm`, `bed_contact_mm2`, `overhang_area_mm2`, `stair_step_area_mm2`, `fill_ratio`, `fits`, `score`, `rank`, `rotation` (3x3) and `rotate` (the same as build123d makes it, pasteable: `bd.Rot(-90, 0, 0)`; turn the part in its model); `weights` | the six axis orientations |

**Ranking** (`orientations.weights`): each figure over the largest any candidate has, weighted, summed, lowest
first. Support processes (FDM, SLA, metal): support volume 0.30, support contact 0.15, contact on cosmetic faces 0.10,
build height 0.15, overhang area 0.10, stair-step area 0.10, lack of bed contact 0.10. Powder (SLS, MJF): build height
0.50, stair-step area 0.30, overhang area 0.20.

### Findings that are facts

`not_watertight` (an error, mesh and B-rep: an open surface has no inside to print, and every figure of it is
suspect; on a mesh it names the open bodies), `not_sound` (an error: the kernel's validity check fails; on a mesh,
a closed body whose surface passes through itself), `several_bodies` (info: an assembly's parts), `several_solids`
(a warning: a part of several solids, and a mesh of several bodies, which names no parts), `clearance_bounded`
(info: a clearance the mesh path's budget cut short, with the two figures it lies between), `overhangs` (the sum of the down-facing area: info where `printing.overhang_angle` judges each face
-- FDM, SLA, metal, at the angle limit used -- and for powder, a warning only where no rule judges them; with a hint, and on an assembly the sentence that the parts are measured as printed together, in place,
and a part printed on its own is checked by its own id), `plate_edge_round` (info: rounds on the plate's edge facing
down under the limit; a 45 deg chamfer is not one), `walls_not_measured`, `internal_void` (FDM: a sealed void prints
as infill; never on an open mesh, whose voxel "voids" are its holes), `no_bed_contact`,
`warping_risk` (FDM in abs, nylon, nylon_gf, pc, pc_abs, pp, peek, pei, pom, pbt with a flat bottom on the plate),
`elephant_foot` (FDM: holes open on the plate), `mesh_overlap` (a mesh's faces lying on faces under 0.05 mm: its
defect, said once at its place, no gap), `mesh_repaired` (a warning: what the gate repaired before measuring),
`bodies_intersect` (a warning, both paths: bodies or parts that pass through each other, a finding a pair -- a
slicer may join them or fill the overlap twice, and the volume is their sum; a mesh's body wholly inside another
says so, its volume counted once; `printing.clearance` judges gaps and contacts alone), `mesh_at_limit` (info: the down-facing area and the edges that read within the mesh's own
angular tolerance of a limit -- not judged: the exact model has the angle, a finer mesh narrows the band). A
mesh the gate refuses is one error and no report: `mesh_empty`, `mesh_unreadable`, `mesh_too_large`,
`inconsistent_normals`, `mesh_no_volume`.

### Rules

`cad._internal.dfm.printing.RULES` (above: the table is not copied here), every limit keyed by `technology`.

The rules take, per figure and technology, one published design guide's row: Hubs's where Hubs gives one, else
Protolabs's, else Xometry's (and apply Hubs's SLS escape-hole figure to the other powder beds: every verdict of it
says "Hubs's SLS figure, applied"), each cited as the evidence for general practice, not as a printer's or a
shop's limit; the table holds no row that cannot apply (`_general.add` refuses a second source for a figure).
The build volume is the printer's given (`--build-volume`), else a typical machine of the technology's (Hubs's: a
desktop printer for FDM and SLA, `BUILD_VOLUMES`), assumed and said -- and, with none given, the largest machine
the same page lists (`LARGEST_VOLUMES`): a part that fits it lying no way (`build_volume`) is made by no machine
of the technology, an error. The `selector` is `technology`: a rule id with no figure for the
technology is one `not_evaluated` outcome ("the rules give no limit for technology fdm"), never a pass, and a
check that judged nothing says so (`rules_none_evaluated`).
A rule no guide states is text-to-cad's own (`rules.OWN`, its finding's `source`): a knife edge's thin depth
(`printing.knife_edge`), FDM's horizontal round holes over `HORIZONTAL_HOLE_MM` (`printing.horizontal_hole`),
an FDM wall by the `--nozzle` given (two beads of it, where Hubs's 0.8 mm is two beads of the common 0.4 mm
nozzle), and an FDM skin's layers: the two-bead minimum is a standing wall's, laid bead beside bead, and a wall
lying in the layer plane (`wall_thickness.items[].lying`: a tray's floor, a living hinge) is laid layer on layer
-- under one layer it is not laid at all (`printing.skin_layer`, an error), of one layer alone it has no second to
tie its beads (`printing.skin_layers`, a warning).
Severity follows the source: a feasibility limit is an error, a recommendation or an unsourced figure a warning.
A wall's minimum follows whether it is supported (joined on two or more sides: `printing.wall_supported`,
`printing.wall_unsupported`; `printing.wall` where its support could not be read: judged as supported, and
warned where it lies between the two minima, so would fail unsupported -- one finding a wall), and a mesh's wall
under its limit by no more than its chords may depart from the surface is at the limit: the rule's warning, not
its error; a hollow's wall alike (`trapped_volumes.items[].min_wall_chord_mm`, `wall_at_limit`: a 2 mm bottle
reads 1.999 on its chords, at SLA's 2 mm, not under).
Every figure a rule judges is kept to 1e-9 (`meshops_printing.JUDGED`), never rounded before the comparison: a
0.79996 mm wall is under 0.8 mm.
Sources and when each row was read: `printing.RULES.sources` (their URLs in `printing.SOURCES`). Two Hubs pages
differ: its SLA guide gives walls 0.4 mm supported and 0.6 unsupported, its thin-walls table 0.5 and 1.0, which
the rules cite; its MJF guide asks for walls of 2.5 mm, its table 0.7 and 1.0.

What a warning and an error mean here: a warning is a part that will be made, at a cost or a risk (support, a
sagging bridge, a drain hole too small to empty fast); an error one the process does not make as drawn. So FDM's
overhangs, bridges, holes, pins and gaps are warnings -- a 30 mm bridge prints, on support -- and its errors are a
wall under two beads and a part no machine holds.

### What it cannot measure

- On a mesh: pins' own minima and embossed and engraved details (no axes or faces: the report's `not_measured`).
  Their rules are not evaluated, never a pass, and every mesh's result says which, in its one line ("not judged
  on a mesh: ...") and as a finding (`families_not_measured`, info: check the STEP or the model for them). What
  the mesh does judge of them: a pin is a wall (joined on one side: the wall minimum, an error under it, on both
  paths), a round hole up to 3 mm across is a hole (`holes`: every hole minimum is 1.5 mm or less), and a larger
  hole's crown is an overhang or a bridge of its span (`printing.bridge_length`, where exact geometry judges a
  horizontal hole's diameter, a warning either way). So what a mesh cannot judge costs it recommendations, never
  a failure exact geometry would give: an OK of a mesh is of what its line says. An angle within the mesh's own
  tolerance of a limit (`mesh_at_limit`, 3 deg at most): a cone meshed at 0.4 rad cannot tell 43 deg from 45.
- A cavity under about five voxels across (`trapped_volumes.pitch_mm`) is found only where sealed (its shell);
  an opening under a voxel wide is known only to be that narrow; an opening over twice the ball's radius is a
  mouth, its pocket no cavity. An opening that is no straight passage (a labyrinth) reads its narrowest section
  where the stations reach it.
- A wall's support is read off its thin region's outline at a spacing of half its thickness or coarser: one
  joined along a line that curves a little (a fin on a round base) is one side, a flange round a shaft (joined
  round its whole bore) is supported as a land is, and a region of more places than the coarsest spacing holds
  reads unknown (`supported` null: judged as supported, and said between the two minima).
- A self-intersection of a B-rep past the boolean check's budget of faces (`SOUND_FACES`): said, and the check
  is not checked.
- Support is a column fill (vertical supports, no tree supports, no support angle or density); its contact on
  "cosmetic" faces is a size rule (5% of the part's area), not the designer's intent.
- A wall over the unsupported minimum has its support read from the face's concave edges alone (no verdict
  turns on it): a wall joined along one long edge split into several reads as joined more times.
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
- Soundness: the kernel's boolean check on parts while their faces add up to 1000 (`SOUND_FACES`,
  `solid.sound_budget_faces`; its time grows with the square of the faces: 262 took 0.5 s, 406 took 3.2 s); the
  rest get BRepCheck topology alone (`solid.items[].check`) and no self-intersection is looked for: said
  (`measurement_failed`, naming each part once with its count) and the check is not checked, never OK. A part with a free-form face of more than 2000 control points (`SOUND_POLES`; a surface
  swept or offset from a B-spline counts its basis's: a revolved curve's poles by nine, an extruded curve's by two)
  is checked edges against faces, not faces against faces (`check: "boolean_edges"`): the kernel's face/face search
  between a large B-spline and a face meeting it tangentially ran for over three hours on a 3-face part, and no
  kernel call can be stopped. A self-intersection that crosses an edge is still found; two faces crossing inside
  both, on such a part, are not: said (`soundness_bounded`, a warning naming the parts), never a plain pass.
- Voxel fields: each part's field dropped once its trapped volumes and sections are read (an assembly's fields
  held together were most of a 1.8 GB check).
- A flat ceiling the kernel lays no sample on is said not measured (`bridges.items[].unmeasured`), its rules'
  figure missing, never a crash of the family.
- Flat ceilings: the 40 largest refined to the exact farthest point; the rest read on their samples (`refined`).
- A mesh: each overhang region spread over about 3000 points (`meshops_printing.spread_points`: rows from a
  facet's sharpest corner, as wide as each row needs, so a strut's sliver is sampled along its length) and its
  span read by matrix products in blocks (`_least_distances`). Every ray runs on the library's own bounding
  volumes (`meshops_printing.Caster`: the triangles in Morton order, 16 to a box, 8 boxes to a box, a ray's slab
  test down the levels and its triangles' exact test 400 000 pairs at a time): a ray costs the triangles near its
  line. trimesh's engine without embree tested each ray against every triangle whose box its *box* crossed -- a
  330 000 triangle sphere took 59 s and gigabytes, 1.3 million ran out of memory at 10 GB; now 10 s and 0.5 GB,
  and 35 s and 1.7 GB. Past `MAX_TRIANGLES` (2 000 000) the check refuses (`mesh_too_large`: decimate it).
- A cavity's floods: one a ball radius (at most 13), each from the one before; a wall's support: at most 384
  places a spacing, four spacings, on the walls under the unsupported minimum alone; a throat: at most 256
  stations.
- A mesh's families each have a budget, and one that spends it says so, never passes: the clearances (a body's
  points in a tree; `CLEARANCE_PAIRS` exact distances a pair each way, then `exact: false` with its bound -- a
  ball nested 0.3 mm inside a shell held 767 MB at 61 000 triangles in trimesh's closest-point query and ran out
  of 4 GB at 246 000; now 0.3 GB and 0.9 GB), the overhang regions' spans (`SPAN_PAIRS`: grouped in one pass and
  read only where a verdict turns on them, a 330 000 triangle scan went from 180 s to 7 s and 1.3 million
  triangles measure in 22 s and 1.6 GB), the walls refined to their least and those whose support is read (the
  200 and the 24 thinnest of a body), the gaps' rays (20 000) and refinements (200), a knife chain's creases read
  one by one (4000), the stair-stepping regions listed (300). Past them all the caller's own limits stand: a
  check measured in its caller is held to a check's time and memory from outside and stopped there, not checked.

## Since 0.11.7

The check as this page describes it is 0.11.7's. An earlier release's `dfm` measured a mesh tessellated from
the part and judged nothing: what a caller written for one reads differently now (the states and the exit,
a finding's verdict as data, what is gone) is in the library README's **Manufacturing checks**. What that
leaves to this page:

**The rules whose severity is `error`, as of 0.11.7.** The tables are the code's (above), so a later
release's are read from `RULES`, or from a result's `measurements.rules.outcomes`, each with its `severity`;
never key a script on this list. Every other rule is a `warning`, and a rule marked * is one too in a
variant of its own (another technology, a wall at the limit within a mesh's accuracy, an edge more axes or
a special cutter makes, a machine assumed where none is given).

| Process | Rules |
| --- | --- |
| cnc | `cnc.internal_corner_sharp`, `cnc.sharp_internal_edge`*, `cnc.internal_corner_radius`, `cnc.corner_reach_limit`, `cnc.pocket_depth_limit`, `cnc.wall_thickness`, `cnc.hole_diameter`, `cnc.hole_depth_limit`, `cnc.gap_width`, `cnc.no_line_of_sight`, `cnc.enclosed_void`, `cnc.groove_depth_limit` |
| sheet | `sheet.uniform_thickness`, `sheet.thickness_limit`, `sheet.flange_length`, `sheet.bend_relief_width`, `sheet.hole_to_bend`, `sheet.hem_diameter`, `sheet.flat_length_limit`, `sheet.flat_width_limit` |
| molding | `molding.draft_zero`, `molding.undercut_unreleasable`, `molding.wall_too_thin`, `molding.clamp_beyond_press` |
| printing | `printing.wall_supported`*, `printing.wall_unsupported`*, `printing.wall`*, `printing.skin_layer`, `printing.hole_diameter`*, `printing.pin_diameter`*, `printing.gap`*, `printing.escape_holes`, `printing.build_volume`* |

Beside the rules, an `error` is a process's own, which no rule's limit states (each process's findings of
fact, above: `cnc.no_turning_axis`, `sheet.not_sheet`, a cut file's `sheet.open_contour`), or the part's
soundness: `not_watertight` -- a warning on a mesh before -- and `not_sound`.

**What an earlier release's report held and this one's does not.** A mesh is checked for printing alone, so
molding's mesh findings went with its mesh check (`coarse_curved_face`, `mesh_folds`, `probe_resolution`), and
on exact geometry so did what bounded a tessellation: `draft.min_facet_draft`, and `undercuts`' and
`wall_thickness`' `per_body` and `body_count` (each item's `location` names its part, and `bodies` holds each
part's facts). `sealed_voids`, one finding with a count, is `internal_void`, one for each void with its volume.
`units` is taken by an STL and a DXF alone.

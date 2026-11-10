# Migrating from 0.11 to the next release

Draft: this guide is renamed for its release when it ships. It covers the manufacturing checks,
`cad <type> dfm` and `cad.<type>.dfm`. The next release is a minor release, so it never installs
itself: update with the update button or `cad update` when you are ready.

Each change names its tier of the compatibility law ([law 15](../../packages/cad/README.md#the-design-laws),
"Compatibility, by who pays for a break"), which says what a change of its kind keeps working.

## The manufacturing checks (tier 1)

0.11's `dfm` measured and judged nothing: a part passed when every family measured, and what the
figures showed were warnings ([0.10 to 0.11, "The manufacturing measurements"](migrating-0.10-to-next.md#the-manufacturing-measurements-tier-1)).
Now each process has one table of general rules, each a limit on one measured figure with the published
design guide that states it, and the check says which fail. A STEP, an xbf and a model are measured on
their exact geometry, where 0.11 measured a mesh tessellated from them. A check now has three states,
where 0.11 had two:

| State | `"status"` | Exit | When |
| --- | --- | --- | --- |
| `OK` | `ok` | 0 | every part and family was measured and no finding is an `error`. Warnings may remain |
| `FAILED` | `failed` | 1 | a finding's severity is `error`: the part cannot be made by this process as drawn. With `--strict` (`strict=True`), a `warning` fails too |
| `NOT CHECKED` | `not_checked` | 3 | the check did not judge what it was asked to: no verdict, never a pass. `"reason"` is the code that says why |

`"ok"` is true for `ok` alone. An error found wins over what was not checked: such a part is `FAILED`.
Exit 2 is the command line's mistake, as in 0.11. A script or a prompt that reads a check's exit status,
its `--json` or its findings changes for these:

| 0.11 | Now |
| --- | --- |
| a part whose every family measured passed, exit 0 and `"ok": true`, whatever its figures: zero-draft walls, thin walls and overhangs were warnings | a part that breaks a rule's feasibility limit fails, exit 1 and `"ok": false`: the finding is an `error` coded by the rule's id, with the figure, the limit, its source and what to change. A recommendation broken is a `warning` and does not fail the check (zero draft, `molding.draft_min`; a wall under the resin's recommended minimum, `molding.wall_min`; an overhang, `printing.overhang_angle`): the last line counts them, `OK part.step: 22 warning(s); ...`, and `--strict` fails on them. Which a rule is: its `severity` in `measurements.rules.outcomes`. The measurements are in the result either way |
| exit 1 and `"ok": false` for a family that could not be measured (`measurement_failed`), a source that could not be read (`mesh_unreadable`, `document_unreadable`) or a missing file (`invalid_target`) | exit 3, `"status": "not_checked"`, `"reason"` the code: no rule failed, nothing says the part cannot be made. The same for a part with no closed solid (`not_solid`), a document with no part (`document_empty`), faces the kernel failed to intersect rays with (`rays_unintersected`), rules that judged nothing (`rules_none_evaluated`) and a report that is not finite (`not_finite`) |
| exit 1 and `{"ok": false, "error": ..., "reason": "failed"}` for a check that did not run to its end (its environment gave no answer, it crashed) | exit 3, and the document gains `"status": "not_checked"`. The engine measures a STEP's, an xbf's and a model's check now, so the same holds for a check it did not finish: its `"reason"` is the engine's own where its error carries one (a check cancelled by a build of its script, a worker lost), else `engine_stopped`, `engine_failed`, `engine_unavailable` or `failed` |
| a mesh that is not watertight: `not_watertight`, a warning, exit 0 | an `error`, exit 1: an open mesh has no inside, so its walls, voids and volume are a surface's. A STEP's, an xbf's or a model's part with an open shell or loose faces is `not_watertight` too, and one whose solids share volume or that fails the kernel's validity check `not_sound`: errors in every process |
| `--json`: `ok`, `path`, `findings`, `summary`, `measurements` | also `status` (`ok`, `failed`, `not_checked`) and `reason` (the code, when not checked; else null). Every check's result carries them (`drc`, `erc`, `validate`, `solve`: `ok` or `failed`) |
| a finding: `severity`, `code`, `message`, `location`, `hint`, `items` | also `rule`, `value`, `limit`, `unit`, `op` (`min` or `max`), `source` and `refs`: a rule's verdict as data (null and empty for any other finding). Read those, never the message, which no longer carries the source |
| the last line: the summary, or `FAILED <source>: N blocking finding(s)` | it leads with the state and one count, the findings': `OK <source>: [N warning(s); ]...`, `FAILED <source>: E error(s)[, W warning(s)]; ...; failed: <rule> xM[; not checked: <code> xN]` or `NOT CHECKED <source>: <code> ...` |
| each finding printed on a line of its own | a rule's verdicts printed together: the rule once (`error: <rule>, N place(s). Hint: ... Source: ...`), then a short line for each place; every other finding on a line of its own |
| `cad <type> dfm --process printing --candidates` answered the part's own figures (`mesh`, `overhangs`, `wall_thickness`, `support_volume`) and their findings, with the orientations beside them | the orientations alone (`scale`, `orientations`), as molding's `--candidates` answers the pulls alone: run once without `--candidates` for the part's figures |
| the orientations in a fixed order, `current_plus_z` first | ranked, best first, and `orientations.best` names it; each row keeps `orientation`, `support_area_mm2`, `support_area_pct` and `build_height_mm` |
| a STEP, an xbf or a model: `measurements.mesh` (`volume_mm3`, `watertight`, `body_count`, `triangle_count`, `surface_area_mm2`, `bbox_mm`) | `measurements.document` and `measurements.bodies`, each part's facts (its volume, area, box, material); `measurements.source.measured_as` is `brep`. An STL, a 3MF and a GLB keep `mesh` |
| a STEP, an xbf or a model: `undercuts.per_body`, `undercuts.body_count`, `wall_thickness.per_body`, `wall_thickness.body_count`, `wall_thickness.measured_per_body` | each item's `location` names its part; `bodies` holds each part's facts |
| a STEP, an xbf or a model: `scale.bbox_mm_if_units` | `scale.bbox_mm` (a mesh keeps `bbox_mm_if_units`) |
| a STEP, an xbf or a model: `draft.min_facet_draft`, `undercuts.note`, `undercuts.probe_resolution_note`, and the `probe_resolution` finding | gone: an exact face's draft is read exactly, with no facets and no probe to bound it |
| a finding's `location` on a STEP, an xbf or a model: `x, y, z` | a ref, which `cad xbf inspect DOC REF` resolves: the feature's most specific one, a face's (`plate/face 7`) or, for a corner, its edge's (`plate/edge 17`, its faces after it in the finding's `refs`); a mesh's stays `x, y, z` |
| `sealed_voids`, one info finding with the count | `internal_void`, an info finding for each sealed void, with its volume |
| `cad stl\|threemf\|glb dfm --process molding` measured a mesh for molding (`cad.trimesh.molding`, `pulls`; `coarse_curved_face`, `mesh_folds`, `probe_resolution`) | refused, exit 2 (`invalid_argument`): molding is judged on exact geometry, a mesh's chords misread its draft, undercuts and walls -- check the STEP or the model (`cad step dfm part.step --process molding`); a mesh's `dfm` checks printing, its default |

What to change:

- **Read the exit status as one of three, then the findings.** Exit 0 is `OK`; exit 1 is `FAILED`, a
  finding whose severity is `error`; exit 3 is `NOT CHECKED`, which a script must not take for a pass nor
  for a part that fails: fix what its `reason` names, or run the check again. A script that tested `exit
  != 0` still stops on all of them; one that tested `exit == 1` for "could not be measured" tests `exit ==
  3` (or `status == "not_checked"`) now.
- **What fails a check** is every finding of severity `error`, whatever its code:
  - a rule whose limit is a feasibility limit, coded by the rule's id (`<process>.<rule>`). The rules that
    failed are `measurements.rules.failed`, each rule's outcome and `severity` are in
    `measurements.rules.outcomes`, and `measurements.rules.failing` counts the failing features by
    severity. As this is written the `error` rules are: cnc's `cnc.internal_corner_sharp`,
    `cnc.internal_corner_radius`, `cnc.sharp_internal_edge`, `cnc.corner_reach_limit`,
    `cnc.hole_diameter`, `cnc.hole_depth_limit`, `cnc.wall_thickness`, `cnc.gap_width` and
    `cnc.enclosed_void`; sheet's `sheet.uniform_thickness`, `sheet.flange_length`, `sheet.hole_to_bend`,
    `sheet.bend_relief_width`, `sheet.hem_diameter`, `sheet.flat_length` and `sheet.flat_width`; molding's
    `molding.undercut_unreleasable`; printing's `printing.wall`, `printing.wall_supported`,
    `printing.wall_unsupported`, `printing.gap`, `printing.hole_diameter`, `printing.pin_diameter`,
    `printing.escape_holes` and, with `--build-volume` given, `printing.build_volume`. Every other rule is
    a `warning`;
  - a process's own error, which no rule's limit states: `cnc.no_turning_axis`, `cnc.stock_too_small`,
    `sheet.not_sheet`, `sheet.sharp_bend`, `sheet.thickness_mismatch`, `sheet.under_kerf`,
    `sheet.flat_incomplete`, `sheet.flat_overlap`;
  - the part's own soundness: `not_watertight`, `not_sound`.

  Do not key on a list of codes: key on the exit status or `status`, then read `findings` by severity.
- **What makes a check `NOT CHECKED`**, by its `reason`: the whole source -- `invalid_target` (a file
  that is not there, from the library; the command refuses one first, exit 2), `document_unreadable`,
  `mesh_unreadable`, `document_empty`, `not_solid`, `needs_exact_geometry`, `not_finite` -- where
  `measurements` is empty and `summary` is `NOT CHECKED <source>: <code>`; or a part of it --
  `measurement_failed` (a family, named in `measurements.partial_sections`), `rays_unintersected` (faces,
  named in the finding and in each rule's `unmeasured_faces`), `rules_none_evaluated` -- where the rest of
  `measurements` is reported. A script that took exit 0 to mean "measured" reads `measurements` whenever
  `status` is not `not_checked` for the whole source, that is whenever `measurements.rules` is there.
- **A rule that judged some of its features and not the rest** is `partial` in
  `measurements.rules.outcomes`, never `passed`, listed in `measurements.rules.partial` and said in a
  `rule_partly_judged` warning: a script that counted `passed` rules as verified leaves those out.
- **A shop's limits are not the rules.** The verdicts are general practice, no shop's: compare the
  measurements with a shop's own published limits (the sendcutsend skill does, for its sheet).
- **A printing check that ranked orientations runs twice** when it wants both: `--candidates` for the
  orientations, then the chosen one checked as the part stands.

### The library's checks (tier 2)

`cad.<type>.dfm` takes the same parameters but `units`, which is an STL's alone now: `cad.step.dfm`,
`cad.xbf.dfm`, `cad.model.dfm`, `cad.threemf.dfm`, `cad.glb.dfm` and `cad.dxf.dfm` (and the commands'
`--units`) no longer take it, where 0.11 took it and refused every value but `mm` -- drop the argument.
Its result changes as above: `result.status` and `result.reason` are new, `result.ok` is true for `ok`
alone, and a check the engine did not finish still raises. `strict=True` fails on a warning. Each option
is taken only as its kind: a count is an `int`, so `samples=2000.0`, which 0.11 read as 2000, is refused; a
list or a size is text or numbers (`tools="3,6"` or `tools=[3, 6]`, `stock=(100, 60, 25)`, a pull `"z"`,
`"0,0,1"` or `(0, 0, 1)`), and a refusal names the parameter (`tools is ...`), the command its flag
(`--tools is ...`). A value no machine has is refused: an end mill over 100 mm across, an FDM layer
taller than its nozzle, a powder or resin layer over 0.5 mm. On a live build123d shape,
`cad.build123d.dfm(shape, process=...)` is the one function; `cnc`, `sheet_metal`, `molding` and
`printing` stay. `cad.trimesh.molding` and `pulls` are gone (molding is judged on exact
geometry: `cad.build123d.molding(shape)` or `cad.step.dfm(path, process="molding")`); `printing` and `orientations` keep
their parameters and every key of their reports, which gain families; `orientations` ranks its rows,
best first. `cad.model.dfm`, `cad.step.dfm` and `cad.xbf.dfm` keep their signatures and now go through the
engine, from any Python. Against no engine, an older one (0.11) or another release's, a file is measured in the
calling process as in 0.11 (it needs `cad[build123d]` there), and a model's document is exported by the engine
and read back there. The `cad` command, which holds no kernel, runs that in the CAD kernel's environment.

### Fixes, nothing to change

- `support_volume.estimated_support_volume_mm3` is the column of support under each overhang, down to
  the part or the plate, where 0.11 summed a prism from each face to the plate: 0.11's was a coarse
  upper bound, so the figure is lower now for the same part.
- `cad model dfm <id>` with an id the engine does not hold exits 2, `not_found`, as every command does;
  0.11 exited 1 when the check ran in the integration's environment.

### New, nothing to change

An assembly's every part is judged, and a part used several times is judged each way it stands: the
occurrences turned alike are measured once and counted (`measurements.bodies[i].occurrences`, `paths`,
`placements_mm`), one turned another way is measured as it stands, at its own ref, and
`measurements.document` totals every occurrence (`occurrence_count`, `solid_count`, `volume_mm3`). A part of
several solids says so in every process (`several_solids`, a warning).

A model's, a STEP's and an xbf's check is measured by the engine where it holds the document (the model's
warm worker; a file read once, in one of a small pool of the engine's processes, so checks of different files
run at once: `CAD_ENGINE_CHECKS` of them, by default half the machine's cores, one to four, a setting held to
one to the machine's cores), and the same check of an unchanged document answers the result it kept, beside the
engine's cache, so a check run again is immediate, after a restart too (not after an update: another release
measures again, and so does another build of the library at the same release, or a kernel environment made
again with other versions of the libraries a check measures with). A check outlives its caller, as a build does:
cut off by a shell's time limit it runs on, and the same command again answers with its result, waiting for it if
it still runs -- unless another check is waiting for its process meanwhile, which it then gives way to at once,
keeping nothing. `cad status` lists the checks running, for which document, since when and whether their caller still
waits. A `cad run` of a model's script cancels a check of it still running, which says so: run the check again.
So does any check the engine was measuring when `cad stop` stopped it, and a check of a file when an update did:
an update does not wait for it.

`--process cnc` and `--process sheet` check a STEP, an xbf or a model for CNC machining and sheet
metal; `cad dxf dfm` checks a sheet's cut file. A model or an xbf given no `--process` is checked for
the process its parts declare (`part.material = metals.aluminum(process=machined())`), where 0.11
refused it; a STEP still needs one, and a mesh takes printing, the one process it is checked for. Each process takes options of its own beside 0.11's
(`--material`, `--cavities`, `--technology`, `--build-volume`, `--layer-height`, `--nozzle`), and
`--angle-limit 0` is taken.

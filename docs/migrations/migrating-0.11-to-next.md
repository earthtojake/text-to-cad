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
their exact geometry, where 0.11 measured a mesh tessellated from them. A script or a prompt that reads a
check's exit status, its `--json` or its findings changes for these:

| 0.11 | Now |
| --- | --- |
| a part whose every family measured passed, exit 0 and `"ok": true`, whatever its figures: zero-draft walls, thin walls and overhangs were warnings | a part that breaks a rule's limit fails, exit 1 and `"ok": false`: the finding is an error coded by the rule (`molding.draft_min`, `molding.wall_min`, `printing.overhang_angle`), with the limit, its source and what to change; a recommendation broken is a warning. The measurements are in the result either way |
| `cad <type> dfm --process printing --candidates` answered the part's own figures (`mesh`, `overhangs`, `wall_thickness`, `support_volume`) and their findings, with the orientations beside them | the orientations alone (`scale`, `orientations`), as molding's `--candidates` answers the pulls alone: run once without `--candidates` for the part's figures |
| the orientations in a fixed order, `current_plus_z` first | ranked, best first, and `orientations.best` names it; each row keeps `orientation`, `support_area_mm2`, `support_area_pct` and `build_height_mm` |
| a STEP, an xbf or a model: `measurements.mesh` (`volume_mm3`, `watertight`, `body_count`, `triangle_count`, `surface_area_mm2`, `bbox_mm`) | `measurements.document` and `measurements.bodies`, each part's facts (its volume, area, box, material); `measurements.source.measured_as` is `brep`. An STL, a 3MF and a GLB keep `mesh` |
| a STEP, an xbf or a model: `undercuts.per_body`, `undercuts.body_count`, `wall_thickness.per_body`, `wall_thickness.body_count`, `wall_thickness.measured_per_body` | each item's `location` names its part; `bodies` holds each part's facts |
| a STEP, an xbf or a model: `scale.bbox_mm_if_units` | `scale.bbox_mm` (a mesh keeps `bbox_mm_if_units`) |
| a STEP, an xbf or a model: `draft.min_facet_draft`, `undercuts.note`, `undercuts.probe_resolution_note`, and the `probe_resolution` finding | gone: an exact face's draft is read exactly, with no facets and no probe to bound it |
| a finding's `location` on a STEP, an xbf or a model: `x, y, z` | a face's ref (`plate/face 7`), which `cad xbf inspect DOC REF` resolves; a mesh's stays `x, y, z` |
| `sealed_voids`, one info finding with the count | `internal_void`, an info finding for each sealed void, with its volume |
| `cad stl\|threemf\|glb dfm --process molding` measured a mesh for molding (`cad.trimesh.molding`, `pulls`; `coarse_curved_face`, `mesh_folds`, `probe_resolution`) | refused, exit 2 (`invalid_argument`): molding is judged on exact geometry, a mesh's chords misread its draft, undercuts and walls -- check the STEP or the model (`cad step dfm part.step --process molding`); a mesh's `dfm` checks printing, its default |

What to change:

- **Read the exit status as pass or fail, then the findings.** Exit 1 is a rule failed or a part that
  could not be measured. The rules that failed are `measurements.rules.failed` (each rule's outcome is in
  `measurements.rules.outcomes`), and their findings' codes are the rule's, `<process>.<rule>`; what
  could not be measured is still `measurement_failed`, and a source that could not be read
  `mesh_unreadable` or `document_unreadable`. A script that took exit 0 to mean "measured" reads
  `measurements` whatever the exit status, and fails only on those codes.
- **A shop's limits are not the rules.** The verdicts are general practice, no shop's: compare the
  measurements with a shop's own published limits (the sendcutsend skill does, for its sheet).
- **A printing check that ranked orientations runs twice** when it wants both: `--candidates` for the
  orientations, then the chosen one checked as the part stands.

### The library's checks (tier 2)

`cad.<type>.dfm` takes the same parameters, and its result changes as above. Each option is taken
only as its kind: a count is an `int`, so `samples=2000.0`, which 0.11 read as 2000, is refused, and a
pull is text (`"z"`, `"0,0,1"`). `cad.trimesh.molding` and `pulls` are gone (molding is judged on exact
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

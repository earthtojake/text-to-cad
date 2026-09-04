---
name: cad-project
description: Project structure for multi-part CAD work - src/ for model scripts and shared code, format folders (STEP/, DXF/, STL/) for raw outputs, naming, and commit policy for projects with several @step/@dxf model scripts and imported source files. Use when starting a CAD project with more than a couple of models, when asked how to organize CAD code and artifacts, or when growing a flat folder of models into a project.
---

# CAD project structure

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).

This skill is pure convention: cadgen itself is deliberately unopinionated (a
model script's outputs default to its siblings; `out=` relocates them). Use
this structure for anything bigger than a couple of loose models; skip it for
one-off parts, where a flat folder is fine. Authoring the models themselves is
the `$cad` skill; drawings are `$dxf`.

**Where the project lives**: in a workspace that is more than CAD — a
monorepo, an app with models on the side — put the project inside the
directory that holds the workspace's models (`models/`, for example, or
`cad/`, `hardware/` — whatever the workspace already uses as its home for
CAD; `models/` is only the conventional name), never loose at the root.
In an empty or bare workspace, the CAD project IS the workspace: lay out
`src/` and the format folders at the root.

## The layout: code in `src/`, raw outputs in format folders

Only OUTPUTS are organized by format. Code is not: a model script is not a
"STEP thing" — it is authored Python that happens to emit a STEP.

```
<project>/
  src/                    # AUTHORED code — the only thing you edit
    README.md             #   the model catalog (see below)
    plate.py              #   one model per file: a part …
    plate_drawing.py      #   … a drawing …
    frame.py              #   … a sub-assembly …
    assembly.py           #   … the root assembly
    lib/                  #   shared code (plain modules — never models)
      __init__.py         #     one-line docstring; lib is a regular package
      holes.py            #     helpers
      bracket_shape.py    #     a factory two models build from
  STEP/                   # raw outputs ONLY (+ their sidecars)
    plate.step
    imported/             #   committed source files brought in from outside (see commit policy)
  DXF/  STL/  GLB/  3MF/  # other format folders: same shape, outputs + imported/
  tmp/                    # scratch: snapshots, debug renders (gitignored)
```

Two mechanical rules:

1. **Format folders hold only raw artifacts.** Never code, never notes. Each
   model script declares its own destination — cadgen has no layout knowledge:

   ```python
   from cadgen import build123d as bd
   from cadgen import step

   WIDTH = 10.0


   @step(out="../STEP/plate.step")
   def plate():
       return bd.Box(WIDTH, 10, 10)


   if __name__ == "__main__":
       plate()
   ```

   `out=` resolves relative to the script, so the project relocates as a
   unit.
2. **`src/` holds ONLY runnable model scripts.** Every `.py` directly under
   `src/` is a model — one parameterless decorated function — that ends with
   `if __name__ == "__main__": <model>()`; run it to build it. Everything
   shared goes in `src/lib/`: helpers, factories, and constants several models
   read. So `ls src/*.py` IS the model catalog. `src/lib/` is a regular
   package, not a namespace one: it always contains an `__init__.py`, and a
   one-line docstring naming what the package holds is enough.

Because scripts sit directly in `src/`, imports need no setup: python puts the
script's own directory — `src/` — on `sys.path`, so shared code and sibling
models import directly, from any working directory. A model may share its stem
with the `lib/` module it wraps (`src/body.py` over `lib/body.py`); the two are
different modules (`body` and `lib.body`), so alias the import — `from lib
import body as body_lib` — rather than let the module name shadow the model
function you are about to define:

```python
from lib import fasteners            # a helper module: any edit to it rebuilds this model
from plate import WIDTH              # a constant from another model: tracked by value
from plate import plate              # another model: a child, tracked by its result
```

Those three imports are the three kinds of dependency a model can have —
**models by result, constants by value, functions by file** — and `cadgen
store why src/<model>.py` shows which ones a model has and whether each is
current. Importing a model never builds it; calling it inside your body does.

Build from anywhere: `python src/plate.py`. Build-if-missing and rebuild are
the same command — the freshness gate runs first, so an unchanged model is a
no-op. There is no project-level build command: regenerate a whole project by
running each script.

```bash
for f in src/*.py; do python "$f"; done
```

The CAD Viewer opened at the project root catalogs the format folders'
artifacts (scripts never appear); before anything is built, discovery is
`src/`, not the viewer.

## Assemblies pull their children

A parent (`assembly.py`) imports its part and sub-assembly models and calls
them in its body; each call builds that child if it is stale — in parallel
with its siblings, on its own worker — or loads it from the store, and the
parent's output LINKS to the child's result. So **running the root is the
whole build**: `python src/assembly.py` rebuilds exactly what is stale beneath
it and nothing else. Dependency is pull, not push: rebuilding a part on its
own (`python src/plate.py`) does NOT rebuild the assemblies that use it —
rerun the parent to pick the change up.

**A sub-assembly is a model** with its own file and its own outputs
(`frame.py` → `STEP/frame.step`), composed into the root exactly like a part.
A helper that returns a group of placed parts belongs in a model file, not in
`lib/`: as a model it has a record, builds once, links into every parent and
gives you a STEP to inspect on its own; as a `lib/` function it re-runs inside
every caller and any edit rebuilds them all.

**A mirrored part is its own model.** STEP cannot express a reflection, so a
right-hand part is not a mirrored placement of the left-hand one: put the
shape in a `lib/` factory (`side_bracket(mirrored=False)`) and give each hand
a one-line model file. The template shows the pattern.

**A print-only part is a model too.** `@stl` (or `@glb`/`@threemf`) with no
`@step` declares a model whose outputs are meshes; it composes into
assemblies like any part and writes no STEP.

## Naming

- Model script stem = artifact stem = a Python identifier (`plate.py` →
  `STEP/plate.step`). Industry/exchange names (part numbers, revisions,
  spaces) go on the ARTIFACT via `out=` ("../STEP/PN-10432_revB.step"),
  never into the stem — scripts must stay importable modules.
- A drawing gets its own stem: `plate_drawing.py` → `DXF/plate_drawing.dxf`
  (one model per file).
- A mirrored pair is two stems: `bracket_left.py`, `bracket_right.py`.
- Never distinguish files by case alone (macOS filesystems are usually
  case-insensitive).
- Files brought in from outside — vendor downloads, supplier files, anything
  used as a SOURCE, whether rendered directly or composed into generated
  models downstream — keep their upstream names and live in the format
  folder's `imported/` subfolder (`STEP/imported/`, `DXF/imported/`, ...).

## Renaming or retiring outputs

Changing a model's `out=` (or deleting a model) does not remove what the old
declaration produced: the previous artifact, its `.step.json` sidecar, and
any declared mesh exports stay on disk and will look like real project files
forever. Treat a rename as an edit PLUS a cleanup, done conservatively:

1. BEFORE editing, list exactly what the old declaration names: the `out=`
   target, its `<name>.step.json` sidecar, and each declared export's
   `out=` target (`@stl`/`@glb`/`@threemf`).
2. Make the edit, rebuild, and verify the new artifacts exist.
3. Delete ONLY the files from step 1, by exact path. Never glob
   (`rm STEP/A*`), never touch `imported/` (those are sources, not outputs),
   and when unsure, stop and check `git status` — in a committed project the
   orphans appear as exactly the deletions you expect, and anything
   unexpected means step 1 was wrong.

## Building many models

Running the root assembly already builds its children in parallel. Distinct
roots fan out safely too: builds never wait on or cancel one another, and two
concurrent runs of one script both complete, with the store keeping the result
whose sources match the files as they are now (nothing corrupts).

```bash
ls src/*.py | xargs -n1 -P4 python
```

Running builds are limited to one per core (`CADGEN_JOBS` overrides); the
rest queue, so a wide fan-out costs no wall time over the ideal. Two costs
worth avoiding: parallel snapshot invocations each pay a headless browser —
batch several views into one `--job` packet instead — and concurrent identical
mesh exports of one document waste work (the shared ledger makes them safe,
not free).

Several agents building one assembly at once: give each its own entry — a
small model that composes only its subsystem — verify there, and build the
full assembly once when the subsystems land; the root then links the
subsystems' results and rebuilds only what changed.

## `src/README.md` — the model catalog

Every project ships a short catalog so an agent landing in the project knows
what builds what without reading every script:

```markdown
# <project> models

| Script           | Artifact              | Description                          |
|------------------|-----------------------|--------------------------------------|
| plate.py         | STEP/plate.step       | Mounting plate, `HOLE_D` corner holes|
| plate_drawing.py | DXF/plate_drawing.dxf | Plate flat pattern                   |
| frame.py         | STEP/frame.step       | Plate + two standoffs (sub-assembly) |
| assembly.py      | STEP/assembly.step    | Frame + left/right brackets (root)   |

Build: `python src/assembly.py` builds the root and whatever is stale beneath
it; `python src/<script>` per row for the rest; unchanged models are no-ops.
Imported sources: STEP/imported/servo.step (committed, no script).
```

Keep it a table plus a few lines; update it whenever a model is added or
changed.

## Commit policy (a principle, not a layout)

Derived files are regenerable and typically ignored; authored files and
anything code cannot reproduce are committed:

1. **Authored** (`src/`): always committed.
2. **Generated** (the format folders): NOT committed by default — a fresh
   clone regenerates by running the scripts. Snapshots and other review
   renders are scratch, not artifacts: they go to `tmp/`, always ignored.
3. **Committed exceptions, made deliberately**: imported source files under
   any format folder's `imported/` (no code can regenerate them — a
   code-only checkout must never be missing INPUTS, only derived outputs)
   and pinned fixtures —
   anything asserted against byte-for-byte, since regeneration on a newer
   kernel can legally change bytes for identical geometry. Pin a loose file
   with its own negation line or `git add -f`.

```gitignore
/STEP/*
!/STEP/imported/
/DXF/*
!/DXF/imported/
/STL/*
!/STL/imported/
/GLB/*
!/GLB/imported/
/3MF/*
!/3MF/imported/
/tmp/
__pycache__/
```

Note the `*` forms: ignoring the directory itself (`/STEP/`) would make the
`imported/` negation dead — git never descends into an ignored directory.

## Scaffolding a new project

Copy `references/project-template.md` — the full tree with a working part,
drawing, mesh-only part, mirrored pair, two-level assembly, lib modules,
README, and .gitignore to create verbatim. Then verify the loop end to end:
`python src/assembly.py`, snapshot it, and confirm the format folders gained
the artifacts. The template ends with the finished tree — what the project
looks like after that first build, imported source and sidecar included — so
there is nothing else to go and look at.

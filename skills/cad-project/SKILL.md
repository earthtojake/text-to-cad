---
name: cad-project
description: Project structure for multi-part CAD work - src/ for model scripts and shared code, format folders (STEP/, DXF/, STL/) for raw outputs, naming, and commit policy for projects with several @step/@dxf model scripts and imported source files. Use when starting a CAD project with more than a couple of models, when asked how to organize CAD code and artifacts, or when growing a flat folder of models into a project.
---

# CAD project structure

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).

This skill is pure convention: cadgen itself is deliberately unopinionated (a
model script's artifact defaults to its sibling; `out=` relocates it). Use
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
    plate.py              #   one @step/@dxf model per file
    plate_drawing.py
    lib/                  #   shared code (plain modules — never models)
      __init__.py         #     one-line docstring; lib is a regular package
      holes.py
  STEP/                   # raw outputs ONLY (+ their source sidecars)
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

   @step(out="../STEP/plate.step")
   def plate(width: float = 10.0):
       return bd.Box(width, 10, 10)


   if __name__ == "__main__":
       plate()
   ```

   `out=` resolves relative to the script, so the project relocates as a
   unit.
2. **`src/` holds ONLY runnable model scripts.** Every `.py` directly under
   `src/` is a model that ends with `if __name__ == "__main__": <model>()` —
   run it to build it. Everything shared goes in
   `src/lib/`. So `ls src/*.py` IS the model catalog. `src/lib/` is a regular
   package, not a namespace one: it always contains an `__init__.py`, and a
   one-line docstring naming what the package holds is enough.

Because scripts sit directly in `src/`, imports need no setup: python puts the
script's own directory — `src/` — on `sys.path`, so shared code and sibling
models import directly, from any working directory:

```python
from lib import fasteners
from plate import WIDTH        # constants from another model; importing never builds
```

Build from anywhere: `python src/plate.py`. Build-if-missing and rebuild are
the same command — the freshness gate runs first, so unchanged models no-op.
Regenerate a whole project mechanically:

```bash
for f in src/*.py; do python "$f"; done
```

The CAD Viewer opened at the project root catalogs the format folders'
artifacts (scripts never appear); before anything is built, discovery is
`src/`, not the viewer.

## Naming

- Model script stem = artifact stem = a Python identifier (`plate.py` →
  `STEP/plate.step`). Industry/exchange names (part numbers, revisions,
  spaces) go on the ARTIFACT via `out=` ("../STEP/PN-10432_revB.step"),
  never into the stem — scripts must stay importable modules.
- A drawing gets its own stem: `plate_drawing.py` → `DXF/plate_drawing.dxf`
  (one model per file).
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

Parallelize ACROSS models, never within one. Each build holds a per-model
lock — two concurrent builds of the same script serialize (the loser reports
`contended`, nothing corrupts) — while distinct models fan out safely,
because the warm daemon caps its own worker pool to the machine:

```bash
ls src/*.py | xargs -n1 -P4 python
```

Two costs worth avoiding: parallel snapshot invocations each pay a headless
browser — batch several views into one `--job` packet instead — and
concurrent identical mesh exports of one document waste work (the shared
freshness ledger makes them safe, not free).

The lock is also why several agents building ONE assembly entry at once report
long wall times that are not build cost: each waits for the holder, then
finds the result current or rebuilds only its own scope. Measured on a
sixteen-module engine with six builders, a ten-minute run was eight and a half
minutes of `waiting for another run to finish building`. Give each parallel
builder its own entry instead — a small `@step` script that composes only its
subsystem (with the others' modules stubbed or omitted) — verify there, and
build the full assembly once when the subsystems land. Memo scopes make that
final build pay only for what changed.

## `src/README.md` — the model catalog

Every project ships a short catalog so an agent landing in the project knows
what builds what without reading every script:

```markdown
# <project> models

| Script           | Artifact              | Description                   |
|------------------|-----------------------|-------------------------------|
| plate.py         | STEP/plate.step       | Mounting plate, param `hole_d`|
| plate_drawing.py | DXF/plate_drawing.dxf | Plate flat pattern            |

Build: `python src/<script>` per row; unchanged models are no-ops.
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

Copy `references/project-template.md` — the full tree with a working example
model, drawing, lib module, README, and .gitignore to create verbatim. Then
verify the loop end to end: `python src/<first-model>.py`, snapshot it, and
confirm the format folder gained the artifact. The template ends with the
finished tree — what the project looks like after that first build, imported
source and sidecar included — so there is nothing else to go and look at.

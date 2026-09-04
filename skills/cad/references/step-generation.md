# STEP generation

Read this file when generating or regenerating STEP/STP artifacts from build123d
Python source, or when working with imported STEP/STP files.

## The model script is the tool

Generation has no CLI. A model is a plain Python script whose `__main__` calls
the decorated function; that call builds it:

```python
from cadgen import build123d as bd
from cadgen import step

WIDTH = 10.0


@step()
def bracket():
    return bd.Box(WIDTH, 10, 10)

if __name__ == "__main__":
    bracket()
```

```bash
python bracket.py                 # builds bracket.step + its render package
python bracket.py --force --json  # per-run flags ride the script's argv
```

Every run keeps the model's result in the user-level store (a tree of exact
`.brep` + `.surf` components, plus links to its children's results) current and
ALWAYS writes the `.step` output, assembled from that result rather than
re-generated. Unchanged sources are a fast no-op. The default output is the
sibling `<stem>.step`; relocate it durably with `@step(out="path/to/out.step")`
(relative to the script). There is no per-run output override: a model has one
output, and the store's record of it is keyed by the script.
Do not put output paths in the model's return value. Mesh formats are declared
on the model with `@stl`/`@threemf`/`@glb`, or written by the matching
`cadgen <format> build` door (see `supported-exports.md`).

Rules the decorator enforces:

- **The decorator only declares.** Nothing runs at decoration or import time.
  A model file without `if __name__ == "__main__": <model>()` never builds.
- **A top-level call builds.** Calling the decorated name when no build is in
  progress (`__main__`, a REPL) runs the pipeline and returns `None`; a failed
  build exits with the pipeline's code. It takes no arguments — the declared
  output is the model's default configuration.
- **A call inside a build composes.** From another model's body the same name
  returns the shape: the child is built if it is stale (writing ITS `.step`
  and record), otherwise loaded from the store, and either way its result is
  linked into the parent's. This is what makes composition ordinary Python;
  there is nothing to cache by hand.
- **One model per file.** The file is the model; entry identity, packages, and
  closures key off it.
- **A model takes no parameters.** It is one configuration of one output, so
  there is nothing for an argument to select; the decorator refuses a
  parameter list. Parametric geometry is a plain factory the model calls:

  ```python
  def _bracket(width: float, thickness: float) -> bd.Shape:
      return bd.Box(width, 10, thickness)

  @step()
  def bracket():
      return _bracket(width=40.0, thickness=6.0)
  ```

  A second configuration is a second model (`bracket_wide.py`), with its own
  STEP — the way two part numbers are two parts. Authored values that a model
  shares with its drawing or its assembly live in module constants
  (`WIDTH = 40.0`) that the siblings import.
- Options: `out=`, `kind="part"|"assembly"` (else inferred from the return),
  `mesh_tolerance=`, `mesh_angular_tolerance=`. **The return is a build123d
  `Shape` and nothing else** — a dict return is refused. Mesh exports are
  declared with `@stl`/`@threemf`/`@glb` stacked on the model; tolerances on
  the decorators. Everything a model declares about itself lives in its
  decorators, and a child's declarations never ride up into a parent (see
  "Composition" below).

**Imports:** `from cadgen import build123d as bd` is the canonical import — a
lazy, transparent re-export (same names, same objects on first touch), so a
current model's re-run never pays the ~2.5s kernel import: the freshness gate
and warm-daemon handoff fire before any `bd.` attribute resolves. Raw
`import build123d` still works, just slower on re-runs (the build prints a
one-line hint).

## Generated vs imported STEP

These two terms classify a STEP file by what its source is:

- A **generated STEP file** has a model script as its source. The STEP and its
  render package are *derived*; the script is what you edit and re-run.
- An **imported STEP file** is its own source: authored or downloaded
  elsewhere. There is nothing upstream to regenerate.

A model that DECLARES something beyond geometry — kinematics, animation, or
mesh exports — gets a sidecar BESIDE THE MODEL (`<name>.step.json` —
`part.step` gets `part.step.json`) carrying those sections plus source
hashes. A plain model writes NO sidecar: its provenance and freshness ride a
record in the user-level store, so reruns still no-op and the doors still
refuse a document whose script changed. Imports write none of it.
The written STEP/DXF file itself carries NO cadgen metadata and no link back
to source code, ever — a bare artifact separated from its package is a plain
importable file. Provenance is never inferred from filenames either — so
relocated outputs, renamed scripts, and shared output folders all stay
traceable through the package alone.

When a model builds on another part, wire it in as LINKED or UNLINKED —
see "Composing on other parts" below.

## Composing on other parts: linked vs unlinked

A **model script** is any plain `.py` defining one `@step` (or `@dxf`)
function, and a model that builds on another part wires it in one of two
modes. Choose deliberately:

- **LINKED (the default)** — the child is generated here: compose from its
  SOURCE. A child edit flows into the parent on the next rebuild; there are
  no exported bytes to keep in sync. Never route a generated child through
  its exported `.step`.
- **UNLINKED** — the child is a document, not source: a purchased or
  downloaded part, or a generated part the user has EXPLICITLY asked to
  decouple (export it once, then treat the export like any other document).
  Read it with `cadgen.read_step`, below.

A linked child is just an import: model scripts are real modules, and
`from widget import widget` binds the model with no build side effects.
Calling `widget()` inside the parent's body builds the child when it is stale
(writing the child's own `.step`) or loads its result from the store, and
returns the shape. What comes back is GEOMETRY only — tree, labels, colors,
placements. A child's sidecar content (its mates, kinematics, animation) never
rides up into the parent: declare what the assembly needs on the assembly,
with `cadgen.assembly` on the parent's own compound.

The parent depends on the child by RESULT, not by source: its record pins the
child's result hash, so a child edit that yields identical geometry leaves the
parent current, and an edit that does not reach a child skips that child's
Python and kernel work entirely (this is what makes big-assembly edits cost
seconds instead of minutes). Import only the model function from a model
file (`from widget import widget`); importing anything else from it (a
constant, a helper) makes that file part of the parent's own source closure.
A decorated model function is just its geometry here — its own `out=`/export
declarations fire only when it is the entry being built:

```python
from cadgen import build123d as bd
from cadgen import step
from widget import widget   # importing binds; never builds

@step(kind="assembly")
def rig():
    w = widget()              # built if stale, else loaded; compose into the parent
    w.label = "widget"
    ...
```

**Link or component.** Place a child's shape as it came back — `moved()`,
`Location * child`, relabelled, recolored — and the parent's result LINKS to
the child's (stored once, shared by every parent). Modify it (a boolean, a
mirror, extracting a sub-shape) and the parent owns that geometry as its own
components; the dependency is tracked either way. Prefer `moved()` over
`located()`: `located()` deep-copies the geometry, which also makes it the
parent's own component. Put geometry changes that belong to the child in the
child's file.

**`sys.path` does not survive into the model function.** The pipeline restores
`sys.path` after loading the module, so do imports at module top level and
only *call* the imported code inside the function.

**Unlinked children: reading a STEP file the model does not generate.** Use
`cadgen.read_step`, not `build123d.import_step`. It returns the same shape, served from cache on a warm
run, and — the part that matters — it RECORDS the file's content hash as a build
input. Replacing the vendor STEP then makes the model stale on its own, with no
`--force`; read through build123d and the model stays "current" against a file
that changed underneath it.

```python
from pathlib import Path

from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent

@step(kind="assembly")
def rig():
    motor = read_step(_HERE / "imported" / "vendor_motor.step")   # recorded input
    ...
```

**Never `read_step` your own output.** A model that reads the `.step` it is about
to write is not a loop — it is a model whose input changes every time it runs, so
the freshness gate can never say "current", every build is a full rebuild, and the
geometry depends on what the last run happened to leave on disk. Keep source
documents where the model cannot write them — placement policy belongs to
`$cad-project` (`imported/`). Input path and output path being different files is
the whole rule. If the geometry you want is something the model already builds,
call that function instead of reading the artifact — no file, no staleness
question.

For structuring multi-part projects (folder layout, shared `src/` code, commit
policy), load the `$cad-project` skill.

## Generated assemblies

Kind is inferred from the return value (a labeled `Compound` with children
reads as an assembly) or declared with `@step(kind="assembly")`. Passing a
generated assembly's exported `.step` to a tool treats it as imported native
STEP and loses source-level composition; work with the `.py` source. Prefer
`cadgen.assembly.AssemblyHelper` so native labels, named mate frames, and
source-level relationships are preserved before STEP export (see
`positioning.md`).

## Imported STEP/STP files

An imported STEP/STP file needs no model script and no preparation step. Hand it
straight to `cadgen step inspect`, `cadgen step snapshot`, or a mesh door: each
makes whatever it needs on demand, and its part/assembly kind is inferred from
the STEP product hierarchy.

```bash
cadgen step inspect refs path/to/imported.step --facts
cadgen stl build path/to/imported.step meshes/imported.stl
```

To produce STL/3MF/native GLB files from an imported STEP, pass it to the
matching format door with an explicit OUT (an imported file declares nothing, so
a bare door has no variants to produce); read `supported-exports.md`.

### Re-emitting a foreign STEP as your own

A STEP written by another kernel round-trips through cadgen with
`cadgen step build IN OUT`: OCCT reads it, the package is rebuilt, and the
canonical writer emits it, so OUT's bytes are deterministic and identical on
every run. The same command ANNOTATES a document that has no model script —
`--kinematics` takes the whole space (`{mates, couplings, poses, at}`, the same
vocabulary the decorator takes, as inline JSON or a `.json` path) and
`--animation` copies a `.js` module's text into OUT's sidecar.

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.bore", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

Re-running is a no-op; editing only the kinematics refreshes the sidecar without
re-emitting a byte. Vendor metadata (PMI, GD&T) does not survive the round trip.
**Choose the door by how the model will evolve**: a shape you will keep changing
belongs in a model script (a thin wrapper that imports the foreign STEP), while
a one-shot canonicalization or annotation of a file you do not own is exactly
what `step build` is for.

## Optional-module generators and the artifact cache

A model that imports several part modules and SKIPS the ones that do not exist
yet is a useful pattern for parallel work — the assembly stays renderable while
individual parts are still being written. It has one sharp edge.

The artifact's source-closure hash is computed from the modules the model
ACTUALLY IMPORTED at build time. Modules that did not exist during the first
build were never in the closure, so their later appearance cannot change the
hash. The cache is self-consistent and permanently stale: tools that resolve
artifacts on demand keep serving the old package, with no error and no warning,
long after the new modules land.

Run the model script explicitly after adding a part module, rather than relying
on implicit resolution by `inspect`, `snapshot`, or the Viewer.

## Viewer artifacts

Every model run keeps the model's result in the user-level store (a tree of
exact-geometry components plus links to its children's results, recorded
against the script) current as the build output. It powers CAD Viewer review,
`$cad-viewer` workflows, and `cadgen step inspect` refs, and is not optional in
the STEP workflow. Imported STEP/STP files get the same result on demand, per
the previous section.

## After generation

- Confirm the process succeeded and the STEP file exists and is non-empty.
- Run the baseline inspection and any spec-driven checks per
  `inspection-and-validation.md`:

```bash
cadgen step inspect refs path/to/model.step --facts --planes --positioning
```

## Warm daemon (on by default)

Every model run and `cadgen stl|3mf|glb build` /
`cadgen step inspect` / `cadgen step snapshot` invocation would otherwise pay a multi-second OCP/build123d
import. They are routed through a shared warm daemon **by default** — the
decorator hands a directly-run script to the daemon before any kernel import —
and `CADGEN_DAEMON=0` forces the cold path:

```bash
python path/to/part.py            # warm, no flag needed
CADGEN_DAEMON=0 python part.py      # force a cold in-process run
```

- The daemon is a **supervisor over a pool of warm worker processes**. It never imports
  OCP itself, so a model that crashes the CAD kernel costs one worker rather than the
  daemon. The first call spawns a worker (paying the import once); later calls run in a
  warm one and stream the CLI's stdout/stderr and exit code back unchanged.
- **One worker per model.** A request lands on the worker bound to its model
  script; a busy worker means a second one (an *extra*) runs the job now; a model
  with no worker takes a warm spare (`CADGEN_DAEMON_SPARES`, default 2, refilled in
  the background). Nothing waits on another build and nothing is capped.
- **Children build in parallel.** Inside a body, each child call submits that child
  to the daemon and returns a promise; siblings build on their own workers while the
  body continues, and the parent waits only when it first reads the geometry —
  normally at the closing `Compound(children=[...])`.
- **Same-model builds both run**; the store keeps the result whose sources are
  current. There is no lock, no `contended`, and no `--lock-timeout`.
- **A worker that dies mid-job says so.** When the process running your job is
  killed (out of memory, a kernel crash) the client reports the death and how it
  died, names the job, and prints the exact `CADGEN_DAEMON=0 ...` rerun. Nothing
  is retried silently: a half-hour job re-running unannounced is worse than the
  failure it would hide.
- **No memory ceiling and no worker cap.** Unlimited memory is the operating
  assumption; a build the OS kills is reported as a dead worker with its exit status.
- `cadgen daemon status` reports each worker's model, whether it is busy, its job
  count and whether it is an extra, plus `spares`, `imports` (cold spawns) and
  `concurrent` (extras bound).
- Directly-run model scripts and the `cadgen` commands share the same warm processes.
  (The CAD Viewer runs no Python and never builds; it only reflects CLI builds via their
  progress records.)
- **It runs on Windows too.** The channel is a Unix socket on macOS and Linux and a named
  pipe on Windows, both through `multiprocessing.connection` and ACL'd to their creator.
- The daemon is **per worktree**, keyed by `sha256(cadgen-dir)[:12]`; a `.log` beside the
  socket holds daemon lifecycle and C-level OCP noise. `CADGEN_DAEMON_SOCKET` overrides.
- **Staleness:** the daemon records a version token at startup; when a client's token
  differs — cadgen changed — it exits and the client transparently respawns a fresh one.
- **Idle exit:** bound workers stay warm for the daemon's life; the daemon exits after
  an hour without a request (`CADGEN_DAEMON_IDLE_TIMEOUT` overrides).
- On any daemon spawn or protocol problem the run silently falls back to a cold
  in-process build. Cold and warm builds write identical bytes for both formats —
  drawing determinism is engineered in the DXF emitter rather than bought with a
  pinned hash seed, so a cold `@dxf` run costs one interpreter, not two.

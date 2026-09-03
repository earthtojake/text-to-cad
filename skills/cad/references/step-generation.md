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

Every run keeps the model's render package (the document of record: exact-shape
`.brep` blobs + `.surf` render views + descriptor, in the user-level store keyed by the document's content hash)
current and ALWAYS writes the `.step` output, assembled from that package rather
than re-generated. Unchanged sources are a fast no-op. The default output is the
sibling `<stem>.step`; relocate it durably with `@step(out="path/to/out.step")`
(relative to the script) or per-run with `-o PATH` (relative to the command cwd).
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
  returns the shape; nothing is written for the child. This is what makes
  composition ordinary Python. Cache a child across builds with
  `cadgen.compose.memo(child.child)`; `memo` is for pure functions (a child
  model or an expensive helper), never for anything with side effects.
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
  `mesh_tolerance=`, `mesh_angular_tolerance=`. The return is a build123d
  `Shape` or a `{"shape": ..., "stl": ..., "3mf": ..., "mesh_tolerance": ...,
  "mesh_angular_tolerance": ...}` envelope — those are the only fields.

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
`import widget; widget.widget()` returns the shape with no build side
effects (the import tracer records the child's files into the parent's
closure, so staleness flows). For anything expensive, wrap the imported
function with **`cadgen.compose.memo`** — importing links, `memo` caches.
The wrapped call becomes a SCOPE keyed by the child's own source closure
plus the call arguments, so an edit that does not reach the child's files
skips that child's Python and kernel work entirely (this is what makes
big-assembly edits cost seconds instead of minutes). The contract: a
memoized function is pure given its arguments and source closure, and
returns shapes/compounds (or JSON-able values). A decorated model function
is just its geometry here — its own `out=`/export declarations fire only
when it is the entry being built:

```python
from cadgen import build123d as bd
from cadgen import step
from cadgen.compose import memo
from widget import widget as build_widget   # importing links; never builds

_WIDGET = memo(build_widget)                # memo caches

@step(kind="assembly")
def rig():
    widget = _WIDGET()          # cached scope; compose into the parent
    widget.label = "widget"
    ...
```

The same wrapper serves in-file use: decorate an expensive local function
with `@memo` and it caches under the same contract.

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

Every model run keeps the render package (in the user-level store, keyed by
the document's content hash) current as the build output.
It powers CAD Viewer review, `$cad-viewer` workflows, and `cadgen step inspect`
refs, and is not optional in the STEP workflow. Imported STEP/STP files get the
same package on demand, per the previous section.

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
- **Parallel builds are supported.** A burst spawns workers up to a cap, and a second
  burst reuses the first's workers, so repeated parallel work converges to warm.
- **Same-model builds serialize** on a per-model lock; a caller that declines to
  wait reports `contended` in its result rather than building twice.
- **A worker that dies mid-job says so.** When the process running your job is
  killed (out of memory, a kernel crash) the client reports the death and how it
  died, names the job, and prints the exact `CADGEN_DAEMON=0 ...` rerun. Nothing
  is retried silently: a half-hour job re-running unannounced is worse than the
  failure it would hide.
- **A build has a memory ceiling.** One process's peak resident size is watched
  during the model function and the emit; past the cap the build aborts with one
  line naming the stage it was in, instead of the OS killing whatever it likes.
  Default: half the machine's memory budget (the cgroup limit in a container, else
  physical RAM), never below 4 GB — a 2,500-part engine builds in ~4 GB.
  `CADGEN_MAX_RSS_GB=<gigabytes>` raises it; `0` disables. With `--verbose`, every
  stage line also reports peak RSS, so a report says where memory went.
- **The cap follows the machine**: the smaller of what memory allows (half of RAM, or the
  cgroup limit inside a container, divided by ~300 MB a warm worker holds) and what the
  cores allow (`cores - 2`), never more than 32. `CADGEN_DAEMON_MAX_WORKERS` overrides.
- **At the cap a caller waits briefly**, then runs cold if nothing frees up —
  `CADGEN_DAEMON_WAIT`, default 2s; 0 gives up immediately. Jobs are usually short next
  to an OCP import, so most waits end in a warm worker.
- `cadgen daemon status` reports `waits` and `coldOverflows`. Overflows climbing during
  normal work means the machine is genuinely saturated, not that the cap is too small.
- Directly-run model scripts and the `cadgen` commands share the same warm processes.
  (The CAD Viewer runs no Python and never builds; it only reflects CLI builds via their
  progress records.)
- **It runs on Windows too.** The channel is a Unix socket on macOS and Linux and a named
  pipe on Windows, both through `multiprocessing.connection` and ACL'd to their creator.
- The daemon is **per worktree**, keyed by `sha256(cadgen-dir)[:12]`; a `.log` beside the
  socket holds daemon lifecycle and C-level OCP noise. `CADGEN_DAEMON_SOCKET` overrides.
- **Staleness:** the daemon records a version token at startup; when a client's token
  differs — cadgen changed — it exits and the client transparently respawns a fresh one.
- **Idle exit:** workers reap down to one after 5 minutes idle; the daemon exits after 10
  minutes without a request (`CADGEN_DAEMON_IDLE_TIMEOUT` overrides).
- On any daemon spawn or protocol problem the run silently falls back to a cold
  in-process build. Cold and warm builds write identical bytes for both formats —
  drawing determinism is engineered in the DXF emitter rather than bought with a
  pinned hash seed, so a cold `@dxf` run costs one interpreter, not two.

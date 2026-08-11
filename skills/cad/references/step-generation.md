# STEP generation

Read this file when generating or regenerating STEP/STP artifacts from build123d Python source, or when working with imported STEP/STP files.

## Tools

The launchers live in the CAD skill directory:

```bash
python scripts/gen targets... [flags]     # build render GLB/topology packages from gen_step() sources
python scripts/export target [flags]      # write STL/3MF/GLB mesh files (see supported-exports.md)
```

`scripts/gen` accepts gen_step() Python generator sources only. Use explicit target paths only; target paths resolve from the command cwd unless absolute. Do not rely on directory-wide generation.

Building a generator writes its hidden render package (GLB/topology artifacts) beside the source; it writes no `.step` file by default. Write the `.step` file in the same generation run with `scripts/gen <name>.step.py --write` — bare `--write` writes each target's sibling `<name>.step`; an explicit path requires exactly one target and resolves from the command cwd. This is the only way to write a `.step` file; `scripts/export` writes mesh formats only. Do not put output paths in the `gen_step()` return value; the CLI flags own output paths.

## Generated vs imported STEP

These two terms classify a STEP file by what its source is, and they drive every workflow decision in this skill:

- A **generated STEP file** has a Python generator script as its source — a `.step.py` (a `.py` that defines `gen_step()`). The STEP and its GLB/topology artifacts are *derived* from that script, so the script is what you edit and regenerate; the `.step` is an output.
- An **imported STEP file** is its own source: a STEP/STP authored or downloaded elsewhere, not derived from any generator script. There is nothing upstream to regenerate — the STEP file itself is the source of truth.

When a generated STEP file's `gen_step()` builds on another STEP file, that other file is a **dependency** of the generator (ordinary code-dependency terms apply: the parent depends on the child). How you wire a dependency in depends on whether the child is generated or imported — see "Child dependencies" in `positioning.md`.

## Entry generators are named `<name>.step.py`

A **STEP entry generator** — a Python script that defines `gen_step()` and is meant to be built, inspected, snapshotted, or shown in the viewer on its own — is named `<name>.step.py`. That filename is the marker the viewer catalog and the build tools scan for. Ordinary **helper / library modules** (shared geometry functions, `*_parts/` packages, `*_common.py`, anything imported by other generators but not built on its own) stay `<name>.py` and are NOT treated as entries even if they define `gen_step` — the viewer scans for `.step.py`, not every Python file. So: if a `.py` script is a buildable model on its own, name it `<name>.step.py`; if it only exists to be imported by other generators, leave it `<name>.py`.

- A `<name>.step.py` entry produces the logical STEP `<name>.step` (the filename minus the trailing `.py`); its render package lives at `<dir>/__cadgen__/models/<name>.step.py/`. Build/inspect it by passing the `.step.py` path to the CLI, exactly like any generator source.
- **A `.step.py` file cannot be imported by name.** `import foo` does not find `foo.step.py`, and `import foo.step` makes Python look for a `foo` package (a `foo/` directory) — neither exists. Load an entry generator by PATH (`importlib.util.spec_from_file_location`), which is how the CLI, the viewer, and assembly composition already load generators. If generators must share constants/functions, put the shared code in a plain `<name>.py` helper they both import, or path-load the entry. When a generated assembly composes a generated child (see "Child dependencies" in `positioning.md`), it path-loads the child `.step.py` and calls its `gen_step()` — it never `import`s it by name.

  **`sys.path` does not survive into `gen_step()`.** The CLI restores `sys.path`
  after loading your generator module, so a path inserted at import time is gone
  by the time `gen_step()` runs — an import attempted inside the function fails
  with a bare `No module named ...` that points at the module rather than at the
  path. Import sibling helper modules at module top level and only *call* them
  inside `gen_step()`.

  Minimal path-load (cache it with `functools.lru_cache` if a child is composed many times):

  ```python
  import importlib.util
  from pathlib import Path

  def load_entry(step_py_path):
      path = Path(step_py_path)
      spec = importlib.util.spec_from_file_location(path.stem, path)  # path.stem == "<name>.step"
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      return module

  child = load_entry("path/to/widget.step.py")
  child_shape = child.gen_step()   # compose this into the parent's gen_step()
  ```

## Generated Python source

This is the default path when designing from scratch or modifying a generated model. Generated build123d sources define:

```python
def gen_step():
    ...
    return step_ready_shape_or_labeled_compound
```

Generated Python targets infer their kind from the source metadata and `gen_step()` return value; pass the source path directly:

```bash
python scripts/gen path/to/part.step.py
python scripts/gen path/to/a.step.py path/to/b.step.py
python scripts/gen path/to/assembly.step.py
```

Passing a generated assembly's exported `.step` to a tool treats it as imported native STEP and loses source-level assembly composition; work with the `.py` assembly source. For generated build123d assemblies, prefer `cadgen.assembly.AssemblyHelper` in the Python source so native labels, named mate frames, and source-level relationships are preserved before STEP export (see `positioning.md`).

## Imported STEP/STP files

An imported STEP/STP file (downloaded or authored elsewhere, no generator) needs no build command. Its GLB/topology render artifacts are generated on demand from the STEP file itself by the tools that consume them — `scripts/inspect`, `scripts/snapshot`, and the CAD Viewer — and its part/assembly kind is inferred from embedded metadata or the STEP product hierarchy.

To produce STL/3MF/native GLB files from an imported STEP, pass it directly to `scripts/export`; read `supported-exports.md`.

To debug or pre-run the on-demand render-package build itself, `scripts/artifact` runs exactly one build for an imported STEP/STP file (or a generator source) and prints the result payload:

```bash
python scripts/artifact path/to/imported.step [--kind part|assembly] [--force]
```

## Optional-module generators and the artifact cache

A generator that imports several part modules and SKIPS the ones that do not
exist yet is a useful pattern for parallel work — the assembly stays renderable
while individual parts are still being written. It has one sharp edge.

The artifact's source-closure hash is computed from the modules the generator
ACTUALLY IMPORTED at build time. Modules that did not exist during the first
build were never in the closure, so their later appearance cannot change the
hash. The cache is self-consistent and permanently stale: tools that resolve
artifacts on demand keep serving the old package, with no error and no warning,
long after the new modules land.

Run `scripts/gen` on the entry explicitly after adding a part module, rather than
relying on implicit resolution by `inspect`, `snapshot`, or the Viewer.

## Viewer artifacts

Every `scripts/gen` run writes hidden adjacent GLB/topology artifacts as the build output. They power CAD Viewer review, `$cad-viewer` workflows, and `scripts/inspect` refs, and are not optional in the STEP workflow. Imported STEP/STP files get the same artifacts on demand, per the previous section.

## After generation

- Confirm the process succeeded and the STEP file exists and is non-empty.
- Run the baseline inspection and any spec-driven checks per `inspection-and-validation.md`:

```bash
python scripts/inspect refs path/to/model.step --facts --planes --positioning
```

## Warm daemon (opt-in)

Every `scripts/gen` / `scripts/export` / `scripts/artifact` / `scripts/inspect`
/ `scripts/snapshot` invocation pays a multi-second OCP/build123d import. Set
`CADGEN_WARM=1` to route these CLIs through a shared warm-process daemon
instead:

```bash
CADGEN_WARM=1 python scripts/gen path/to/part.step.py
```

- The first warm call spawns the daemon (paying the import cost once) and each
  later call runs in the warm process, streaming the CLI's stdout/stderr and
  exit code back unchanged. Arguments, cwd resolution, and outputs match the
  cold CLIs; requests are handled sequentially.
- The daemon is **per worktree**: the socket is
  `$TMPDIR/cadgen-daemon-<sha256(worktree-root)[:12]>.sock` (falling back to
  `/tmp`), with a `.log` file beside it for daemon lifecycle and C-level OCP
  noise. `CADGEN_DAEMON_SOCKET` overrides the socket path.
- **Staleness:** the daemon records a version token (max mtime over
  `packages/cadgen/src/cadgen/**/*.py` and `skills/cad/scripts/**/*.py`) at
  startup. When a client's token differs — i.e. cadgen or the skill CLIs
  changed — the daemon exits and the client transparently respawns a fresh one,
  so edits to runtime code always take effect on the next call.
- **Idle exit:** the daemon exits after 10 minutes without a request
  (`CADGEN_DAEMON_IDLE_TIMEOUT` seconds overrides) and cleans up its socket.
- Without `CADGEN_WARM=1` nothing changes; on any daemon spawn or protocol
  problem the CLI silently falls back to the normal cold in-process run.
  Invocations reading a payload from stdin (e.g. `scripts/snapshot --job -`)
  always run cold.

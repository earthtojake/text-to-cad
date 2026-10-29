# Migrating a CAD project from cadgen 0.7 to 0.8

This is a hand-migration playbook. Work through it top to bottom with a 0.7 project open
and you will end with a working 0.8 project. An agent with the CAD skill installed is
pointed here by the skill's short `references/migrations.md` and can do most of this for
you: ask it to follow this guide. A project still on 0.4 first follows
[Migrating 0.4 to 0.5](migrating-0.4-to-0.5.md), which ends here. This guide targets
cadgen 0.8.3 with build123d 0.13.

## Read this first: there is no authoring compatibility layer

0.8 ships no backwards compatibility for authoring and runtime APIs, on purpose:

- No shims, no aliases, no deprecated keyword arguments, and no codemod.
- **No teaching errors.** A retired flag is an unrecognized argument, a retired name an
  `ImportError` or `AttributeError`, a retired decorator argument a `TypeError`. None of
  those errors mentions 0.7, this guide, or what the thing used to be called.

So when something fails during this migration, the error tells you what 0.8 wants, not
what you did. Read it as a spec.

### What a 0.7 project does under 0.8

Nothing migrates on its own, and nothing points here. What happens depends on how the
project runs cadgen:

- **Its scripts run on 0.8** (`cadgen run`, or an environment with cadgen 0.8 installed):
  the first run stops at the first 0.7 import, before any model is built:

  ```text
  ImportError: cannot import name 'build123d' from 'cadgen' (.../site-packages/cadgen/__init__.py)
  ```

  With the imports fixed, the next stop is the first 0.7 decorator argument
  (`TypeError: step() got an unexpected keyword argument 'kinematics'`), and so on down this
  guide's steps.
- **Its docs pin 0.7** (a README or `AGENTS.md` that says
  `uvx ... --from cadgen==0.7.21 python src/model.py`): that command keeps building with 0.7,
  writes its STEP files and sidecars as before, and fails nothing. The project moves only
  when those commands do (Prerequisites, step 1).

### The one-paragraph summary

0.8 replaces 0.7's file pipeline with one engine. A model is still a parameterless
Python function, decorated `@model`, whose run writes no deliverable.
`cadgen run model.py` rebuilds the model in the engine's warm worker, in a Python environment
made for the project (starting the engine when none is running), prints its document's id and
a link to its page, and every page open on it updates.
Think of the page as the open document, the script as its feature tree, and running the
script as the rebuild. Export is the download button at the navbar's right: pick a format,
the engine prepares the file, the browser saves it; `cadgen export <id> part.step` writes
one from the command line, and an `exports.py` writes a project's deliverables. Mates,
couplings, poses and JavaScript clips become build123d joints and STEP AP242's mechanism
vocabulary in the model's body (`cadgen.ap242`), and showcase animations become a GLB's own
channels (`cadgen.gltf`). Colours are sRGB hex. `import build123d as bd` is free until it
is used. The 0.7 store, sidecars, STEP-format commands, staleness checks and `?file=` links
are gone.

## Updating from 0.8.0 or 0.8.1

This section is for a project already on 0.8; it has nothing to port. An engine from
0.8.0 or 0.8.1 never exits on its own, so after an update it still holds port 3245.
Update with the install command, which stops that engine once nothing is using it and
installs the new release in every agent app:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. A plugin
updated through its app does the same as the new release's engine starts. An older
engine still in use stays, and the new release says so: `cadgen server`, the plugin's
MCP startup and a model run stop with

```text
port 3245 is held by cadgen 0.8.1's engine (pid N): run `cadgen stop` to stop it, then start again
```

and `cadgen status` names that engine with the same command. To stop it explicitly,
run:

```bash
~/.local/bin/cadgen +0.8.3 stop
```

It stops the older engine serving the selected port
(`stopped cadgen 0.8.1's engine (pid N) on port 3245`);
`~/.local/bin/cadgen +0.8.1 stop`, the older release's own command, does the same.
Then restart the agent app (or, without the plugin, run `cadgen server`) and run the
model again with `cadgen run model.py`, which makes the project's environment with this
release's cadgen ([Prerequisites](#prerequisites), step 1). A project environment you
installed cadgen 0.8.0 or 0.8.1 into yourself needs
`uv pip install --python <python> cadgen==0.8.3` before its `python model.py` works
again: that cadgen speaks the older engines' protocol. From 0.8.3 on, such an
environment's cadgen may lag the engine's release: the engine serves it and says once
that `uv pip install -U cadgen` updates it.

In Codex the CAD MCP server is required ([the CAD app](../../apps/mcp/README.md)): a
session does not start or resume until CAD initializes, so while the old engine holds
the port, stop it from a terminal, or disable the plugin, before continuing.

## Prerequisites

1. **Install text-to-cad, and run models with `cadgen run`.** Install or update
   text-to-cad with its install command (`curl -fsSL https://texttocad.dev/install.sh | sh`;
   on Windows, in PowerShell, `irm https://www.texttocad.dev/install.ps1 | iex`). Then run
   models with `cadgen run model.py`: it makes the project's Python environment with uv,
   from the dependencies the project declares (`requirements.txt`, `pyproject.toml` or the
   script's inline `# /// script` metadata) and the engine's own cadgen, and never touches
   the project's `.venv`. Declare there what the models import beside cadgen; a `cadgen`
   requirement the project lists goes, since the environment's cadgen is the engine's. Its
   Python is the one the project declares when that is 3.11 to 3.14, the versions OCP and
   build123d publish for, else the engine's. Snapshots use OCCT and download no browser.

   ```bash
   cadgen run src/model.py
   ```

   A project that installs cadgen into an environment of its own (for its tests, a
   notebook or CI) may keep doing so: `uv pip install --python <python> cadgen==0.8.3`,
   then `python src/model.py` there. That cadgen need not be the engine's release, as
   long as the two are compatible (step 2).

   Project/helper Python edits, including the project's own package (which `cadgen run`
   installs editable when its `pyproject.toml` has a `[project]` table), take effect on
   the next model run without reinstalling or restarting the engine. The worker keeps its
   kernel and rebuilds affected work. Installed packages are not watched: a worker reads
   them once, when it starts. After a change to the declared dependencies, the next
   `cadgen run` remakes the environment on its own. After installing, upgrading or
   reinstalling packages in an environment of your own, `cadgen stop` stops the selected
   engine (whoever started it), then `cadgen server` starts it again, or, with the plugin,
   its next CAD tool call does (`python model.py` only attaches). Restart any long-lived
   calling Python process, then run the model again on the same `CADGEN_PORT`.

2. **The engine.** The plugin's MCP bootstrap starts or attaches to it, and so does
   `cadgen run`. To keep one running without either (to view files, or for an
   environment of your own), leave this running in another terminal, outside a
   sandbox that cannot bind its listener:

   ```bash
   uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen server
   ```

   Server, project clients and workers need not share a cadgen release: they must
   speak the same protocol, the engine must read the document format the project's
   cadgen writes, and both must use the same OCP line (major.minor). `cadgen run` keeps
   its environments on the engine's own release; in an environment of your own, an older
   cadgen is served and told once to `uv pip install -U cadgen`, and a newer one to update
   the engine with the install command. Model calls from an environment of your own and
   CLI document operations only attach. A missing server, a denied connection or an
   incompatible engine fails, naming what differs; nothing falls back locally.

3. **Choose a port consistently.** The default is 3245. Set `CADGEN_PORT` in both
   server and client environments for another port; CLI `--port N` takes precedence
   where supported. A port must be 1–65535. Bootstrap reuses a compatible selected
   engine and retires an older cadgen's engine once nothing is using it; any other
   listener fails, and nothing moves to another port.

   A GUI agent app does not inherit an export from your terminal. Merge the port
   into its CAD MCP server entry's `env` configuration, then restart that server:

   ```json
   {
     "env": {
       "CADGEN_PORT": "3246"
     }
   }
   ```

   Select the same port in the project shell, for example
   `CADGEN_PORT=3246 cadgen run src/model.py`. For separate plugin installations or
   releases running independent engines, configure distinct ports in each MCP
   server and its project clients. A cadgen installed in an environment of your own
   must be compatible with its selected server; changing only a shell variable cannot
   configure a GUI server or make incompatible releases compatible.

4. **Use `cadgen` to run source and for CLI verbs.** The registered command
   `~/.local/bin/cadgen +0.8.3 <verb>` selects a CLI installation; its `run` verb runs
   project source in the project's environment. Use its explicit path so an activated
   environment's `cadgen` console script cannot shadow it. On Windows use
   `%USERPROFILE%\.local\bin\cadgen.cmd`; honor `CADGEN_LAUNCHER_DIR` if set.
   If that command is missing, run the install command, or
   `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen doctor`
   once outside the sandbox: doctor registers that release alone, without starting a server.

   | Project action | Current command |
   | --- | --- |
   | Build the models called by a script | `~/.local/bin/cadgen +0.8.3 run src/model.py` |
   | Run a check script | `~/.local/bin/cadgen +0.8.3 run tmp/check_part.py` |
   | Run project tests, in an environment of their own | `uv run --with cadgen==0.8.3 python -m unittest ...` |
   | Add the project's import root | `PYTHONPATH=src ~/.local/bin/cadgen +0.8.3 run src/camera/payload.py` |
   | Export a built document | `~/.local/bin/cadgen +0.8.3 export <id> part.step` |
   | Check the selected engine | `~/.local/bin/cadgen +0.8.3 status` |
   | Diagnose releases and connections | `~/.local/bin/cadgen +0.8.3 doctor --json --python <python>` |

   For diagnostics, `<python>` is the interpreter the model runs in: under `cadgen run`,
   the one in the folder `cadgen run --show-env src/model.py` prints (`bin/python`;
   `Scripts\python.exe` on Windows), else your own environment's. The report inspects
   the project, registered installations, known engines and supported provider
   configuration without changing setup or starting or stopping servers. It states
   what it could discover; unregistered environments and unsupported provider
   configurations may be absent.
   Older engines in the private engine directory are identified through their
   read-only status interface, including their release, installation and serving
   port. They are reported as incompatible with the current connection protocol;
   discovering their identity does not permit builds against them.
   Different providers share the engine whatever their releases, as long as each is
   compatible with it; the install command brings every app to one release. Where one
   is not, update it, or explicitly configure separate ports in their MCP settings and
   project environments. A port change does not upgrade a project.

5. **Free port 3245 from a 0.7 viewer.** A 0.7 viewer still running holds 3245, the
   port the 0.8 engine needs, and no new engine displaces it. Stop it with the
   release that started it, for example
   `uvx --no-config --from cadgen==0.7.26 cadgen viewer stop`, or with Ctrl-C in the
   terminal running it; or give 0.8 another port (step 3). Save or commit project
   changes before deleting the old generated files later in this guide.

## Migration checklist

Do these in order. Later steps assume earlier ones.

- [ ] 1. Rewrite imports
- [ ] 2. Convert each model to `@model`, each variant a model of its own
- [ ] 3. Move files out of the model: exports on request, or `exports.py`
- [ ] 4. Move mates to build123d joints and the mechanism's AP242 functions
- [ ] 5. Move clips to configuration sequences and animations
- [ ] 6. Move materials into the body; make colours hex
- [ ] 7. Learn the one engine: ids, pages, links and commands
- [ ] 8. Replace `read_scene` refs, checks and tools that read 0.7's files
- [ ] 9. Delete 0.7 leftovers
- [ ] 10. Verify

---

### 1. Rewrite imports

```python
# 0.7                                   # 0.8
from cadgen import build123d as bd      import build123d as bd
from cadgen.build123d import Box        from build123d import Box   # loads the kernel here
from cadgen import step, read_step      from cadgen import model, memo, read_step
import cadgen                           from cadgen.ap242 import mechanism_state, gear_pair
                                        from cadgen.gltf import animation
```

**`import build123d as bd` directly.** cadgen installs a lazy importer for `build123d`
and `OCP` in its own environment: the import binds at once and the CAD kernel (about
2.5 s) loads on the first attribute anything reads, inside the engine's worker. A run the
engine finds current never loads it in your process. `from build123d import Box` reads
the name and loads the kernel at that line, as does a module-level `bd.Color(...)` or
`bd.Align.CENTER` default, so write build123d attribute-style. The `cadgen.build123d`
proxy is gone. Module-level work runs in your process on every run too: a 0.7 script that
computed its kinematics at import (`KINEMATICS = kinematics()` for the decorator) pays it on
every no-op; once the mates are in the body (step 4), compute them there. Measured on a
628-part arm: 1.3 s of the calling process's CPU per run at module level, 0.1 s in the body.

**The root holds exactly sixteen names**: `model`, the file decorators `xbf`, `step`,
`glb`, `stl`, `threemf` and `dxf`, `memo`, `paint`,
`read_step`, `read_xbf`, `read_mesh`, the operations `export`, `snapshot` and
`inspect`, and `__version__`. Two namespaces hold the standards' vocabulary:
`cadgen.ap242` (`mechanism_state`, `configuration_sequence`, `gear_pair`,
`rack_and_pinion_pair`, `screw_pair`, `posed`) and `cadgen.gltf` (`animation`).
`cadgen.geometry` and `cadgen.flatten` are unchanged. Everything else 0.7 exported is gone:

| Removed (0.7) | Instead (0.8) |
| --- | --- |
| `cadgen.build123d` | `import build123d as bd` |
| `revolute`, `slider`, `cylindrical`, `fastened`, `MateTarget`, `AssemblyHelper`, `target` | build123d's joints in the body (step 4) |
| `couple` | `cadgen.ap242`'s `gear_pair`, `rack_and_pinion_pair`, `screw_pair` (step 4) |
| `srgb`, `srgb_to_linear`, `linear_to_srgb`, `cadgen.color` | the hex itself: `"#2E3742"` (step 6) |
| `report`, `track` | nothing: delete the calls. Progress is reported per `@memo` call and child model, by its function's name |
| `read_scene`, `StepScene`, `Occurrence`, `Selection` | `cadgen inspect` and the model's own tree (step 8) |
| `compound_from_instances` | `bd.Pos(...) * part`: every placement shares its shape |
| `label_shape`, `label_text` | `shape.label = "name"` |
| `ensure_step_topology_artifact` | nothing: the viewer reads a STEP as it is |
| `cadgen.kinematics`, `cadgen.store.*`, `cadgen._internal.*` | nothing: private modules, gone with the store (step 8) |

**A project that computes its mates as data** -- a list of `revolute(...)` and
`fastened(...)` records that stages edit, re-zero and audit before the model uses them --
keeps that data: define the record yourself (a frozen dataclass with 0.7's fields `name`,
`kind`, `parent`, `child`, `axis` `{origin, dir}` and `limits` `{value}`, so
`dataclasses.asdict` gives the rows your code reads), import `revolute` and `fastened` from
it, and turn the final list into joints in the body (step 4).

### 2. Convert each model to `@model`, each variant a model of its own

```python
# bracket.py (0.7)
from cadgen import build123d as bd
from cadgen import step

WIDTH = 40.0


def _bracket(width):
    body = bd.Box(width, 20, 6)
    return body - bd.Cylinder(4, 6)


@step(out="../STEP/bracket.step")
def bracket():
    part = _bracket(WIDTH)
    part.label = "bracket"
    return part


if __name__ == "__main__":
    bracket()
```

```python
# bracket.py (0.8)
import build123d as bd
from cadgen import model


def bracket_body(width, bore):
    body = bd.Box(width, 20, 6)
    body = body - bd.Cylinder(bore / 2, 6)
    body.label = "bracket"
    return body


@model
def bracket():
    return bracket_body(40, 8)


@model
def bracket_wide():
    return bracket_body(60, 8)


if __name__ == "__main__":
    bracket()
    bracket_wide()
```

Mechanically:

1. **Replace each file decorator with `@model`.** A model still takes no parameters and
   returns a build123d shape: a part, or a `Compound` of labelled children.
2. **Keep parameters on plain helper functions.** A model function takes none; its
   values are the arguments of the helpers it calls, as a 0.7 factory's were. The helpers
   need no marking: the engine keeps every kernel operation, keyed by its inputs, and
   replays what an edit did not reach.
3. **Make each variant a named model.** A configuration (a wide bracket, an M4
   standoff) is a `@model` of its own that calls the helper with its values. Each has
   its own document, id and page.
4. **Keep the `__main__` calls.** Decoration only declares; a call builds. Each call your
   `__main__` makes prints its model's id and page. A 0.7 model with no `__main__` (one only
   other models called) builds only when one of them runs; give it one to build it alone.
5. **A model call returns its document, not its shape.** The call returns a handle:
   `.id`, `.url` (its page), `.name`, `.shape` and `.export(...)`. An assembly's body calls
   its part models and composes their shapes -- `plate().shape` where 0.7 had `plate()`,
   `payload().shape.moved(loc)` where 0.7 had `payload().moved(loc)` -- places them and labels
   the placements. A child builds in the same run and keeps its own document, id and page.
   A check reads `kit().shape`; the shape comes into the calling process when it is first
   read.
6. **One declaration per function.** Bare `@model` is a document with no file; the file
   decorators (`@xbf`, `@step`, ...) are a document with those files. Stacking `@model` on a
   file decorator is refused: drop `@model`.
7. **A stage that was a child model only to be cached is `@memo`.** 0.7 projects often built
   a long derivation chain of cached child models (`stages/a.py` -> `stages/b.py` -> the
   root), each writing a STEP nobody delivered. In 0.8 mark each such stage `@memo` (new in
   0.8) and drop its `__main__` and its file: the engine replays it whole, keyed by its code
   and its arguments, and it has no document of its own. Since every kernel call is replayed
   anyway, a memo hit saves only Python time (0.1 to 0.4 ms per kernel call): mark a whole
   sub-assembly stage of a thousand kernel calls or more (measured at 1.3 to 3 s each, twice
   as fast on an edit), never a part and never a helper called many times. A stage a person
   opens on its own stays a `@model`.
8. **A stage's result is now the live tree, its sub-assemblies' placements kept.** In 0.7 a
   child model's result came back from the store with every sub-assembly at the identity and
   each leaf carrying its whole placement in the child's frame. In 0.8 a `@memo` stage, a plain
   function and a child's `.shape` read inside a body hand over the tree as it was built, each
   compound keeping its own `location`. Code that moves leaves with `.moved()` (or reads a
   leaf's `.location`) expecting the 0.7 shape now works in the sub-assembly's frame: a
   sub-assembly turned 180 degrees moves its leaves the other way, silently, a few millimetres
   at a time. Where a stage's code does that, return the 0.7 shape from the stage before it:

   ```python
   def as_leaves(node, outer=None):                   # every placement pushed into the leaves
       here = (outer or bd.Location()) * node.location
       if not node.children:
           leaf = node.located(here)
           leaf.label, leaf.color = node.label, node.color
           return leaf
       return bd.Compound(children=[as_leaves(c, here) for c in node.children],
                          label=node.label, color=node.color)
   ```

   and compare the migrated model's placements with a 0.7 build of the same code (step 10).

cadgen consumes no script arguments. The project may parse its own `sys.argv`
as any Python program does. Remove 0.7's engine switches (`--force`, `--json`,
`--verbose`, `--profile`, `--mesh-tolerance`, `--no-daemon`) and use the explicit
Python operations or environment settings below:

| 0.7 | 0.8 |
| --- | --- |
| `python model.py` | `cadgen run model.py` |
| `python model.py --force` | `CADGEN_ENGINE_MEMO=0 cadgen run model.py` (no memo hits) |
| `python model.py --json` | `bracket.build()` from Python returns the report as data (`.models[0]`) |
| `python model.py --profile` | `bracket.build(profile=True)` |
| `python model.py --no-daemon`, `CADGEN_DAEMON=0` | `Model.build(daemon=False)` explicitly builds offline, cold in the caller; `export(..., daemon=False)` and `snapshot(..., daemon=False)` are explicit offline operations too. None serves a live document or URL |
| `@stl(mesh_tolerance=...)`, `--mesh-tolerance` | nothing: every mesh is made at one tolerance, 0.25 % of each part's size and 28.5 degrees |
| `cadgen store why src/model.py` (stale or current?) | run it: `took ... nothing ran` means the document is current; otherwise it builds, and its `rebuilt:` line says what changed |

A run reports a line, the delta against the build before, and the page:

```text
built src/tom.py::tom cold in 188.89s: bodies 7 run; 9074 misses, 0 hits; body 139.98s, names 12.69s, document 0.84s
  parts 628 · bounds 483.6 × 83 × 512 mm · joints 7 · sequences 3
  id: 3d76a9c1-543c-514f-b08e-a21acc2a5656
  view: http://127.0.0.1:3245/3d76a9c1-543c-514f-b08e-a21acc2a5656?token=...
```

The first run in a fresh installation also says `loading the CAD kernel for the first time
in this environment, up to a minute`. An unchanged rerun is `took ... its document in memory
holds the model's key, ... nothing ran`, in a fraction of a second.

### 3. Move files out of the model: exports on request, or `exports.py`

In 0.7 a run wrote every file its decorators declared. In 0.8 a run writes nothing: the
engine holds the model's document, and a file is written from it when you ask, with no
rebuild:

```bash
cadgen run src/bracket.py                           # prints id: <uuid> and view: <url>
cadgen export <uuid> STEP/bracket.step STL/bracket.stl GLB/bracket.glb
```

A project whose files are delivered after every change keeps one script that imports
its models and exports each. `export` takes the model function itself, builds it (a
replay when nothing changed) and writes from its document:

```python
# src/exports.py
from pathlib import Path

from cadgen import export

from assembly import assembly
from bracket import bracket, bracket_wide

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    export(bracket, ROOT / "STEP/bracket.step", ROOT / "STL/bracket.stl")
    export(bracket_wide, ROOT / "STEP/bracket_wide.step")
    export(assembly, ROOT / "GLB/assembly.glb")
```

`export()` prints nothing; print what it wrote if you want a record. An export takes a
document and its destinations, and nothing else. A file in another pose is a model of its
own that returns the posed assembly (step 4), and a part on its own is that part's own
model. A tool that reads a delivered file (a URDF pipeline reading `STEP/robot.step`) reads
the export: run `exports.py` before it.

**The file decorators still work.** `@xbf`, `@step`, `@glb`, `@stl`, `@threemf` and
`@dxf`, with `out` as their only argument (relative to the script), still write their
file whenever the model runs. A project can keep them while it migrates; 0.8's guidance
is `@model` and explicit exports. `kinematics=`, `materials=`, `animation=` and the mesh
tolerances are gone from every decorator.

**The xbf is Save As.** `.xbf` is cadgen's own document format: parts and placements,
names, colours, materials, element names and the mechanism, read back losslessly.
Export one only to share a model without its code, or to compose it in another project
with `read_xbf`; an engine restart needs none (step 7). It is not a build stage. A vendor
STEP converts to one once, and `read_xbf` reads it many times faster than `read_step`
parses the STEP:

```bash
cadgen export vendor/motor.step vendor/motor.xbf
```

### 4. Move mates to build123d joints and the mechanism's AP242 functions

0.7's `kinematics=` dict (typed mates, couplings and poses, kept in a
`<name>.step.json` sidecar) is gone. An assembly's mechanism is build123d's joints on
its parts, and the functions that say more are named after the STEP AP242 entities the
document writes:

```python
# 0.7
KINEMATICS = {
    "mates": [cadgen.revolute("elbow", parent="#upper_arm", child="#forearm",
                              origin=(80, 0, 0), direction=(0, 0, 1), limits=(0, 150))],
    "poses": {"bent": {"elbow": 60}},
}

@step(out="../STEP/arm.step", kinematics=KINEMATICS)
def arm():
    ...
    return bd.Compound(children=[upper_arm, forearm], label="arm")
```

```python
# 0.8
from cadgen import model
from cadgen.ap242 import mechanism_state, posed

ELBOW = ((80, 0, 0), (0, 0, 1))                 # numbers at module level; the Axis in the body

@model
def arm():
    ...
    elbow = bd.Axis(*ELBOW)
    bd.RevoluteJoint("elbow", upper_arm, axis=elbow, angular_range=(0, 150))
    bd.RigidJoint("elbow", forearm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    upper_arm.joints["elbow"].connect_to(forearm.joints["elbow"], angle=0)
    assembly = bd.Compound(children=[upper_arm, forearm], label="arm")
    return mechanism_state(assembly, "bent", elbow=60)

@model
def arm_bent():                                  # a posed file is a model of its own
    return posed(arm().shape, "bent")
```

| 0.7 | 0.8 |
| --- | --- |
| `cadgen.revolute(name, parent=, child=, origin=, direction=, limits=)` | `bd.RevoluteJoint` on the parent's part, a `bd.RigidJoint` of the same label on the child's |
| `cadgen.slider` | `bd.LinearJoint` (`linear_range`) |
| `cadgen.cylindrical` (`.turn`, `.travel`) | `bd.CylindricalJoint`, valued `(angle, distance)` |
| `cadgen.fastened` | two `bd.RigidJoint`s of one label, one on each part |
| `"poses": {"bent": {...}}` | `mechanism_state(assembly, "bent", **values)` |
| `cadgen.couple(name, {dof: ratio}, limits=)` | `gear_pair` (revolute joints), `rack_and_pinion_pair` (a revolute joint and prismatic ones) or `screw_pair` (one cylindrical joint's pitch); the range comes from the joints' limits |
| a mate `axis` given as a ref (`"#lever.f2"`) | a `bd.Axis` computed in the body from the live shape |
| `cadgen export ... --pose NAME` (an 0.8 preview), `snapshot --kinematics` | a posed model `posed(arm().shape, NAME)`, exported; `cadgen snapshot <id> out.png --pose NAME` to draw one |

The as-built state is now the value each joint stands at, so a joint whose two frames
coincide as built reads 0 and keeps the parts where they were built. A coupling of one
joint is that joint. The page's Position poses a document live, with a slider per
coupling and per joint no coupling moves, and the mechanism states as presets. A STEP
export is placements only: STEP carries no mechanism.

**A nested assembly pairs its joints by label, not by `connect_to`.** build123d's
`connect_to` composes a part's location within its own compound, so it can place a child
only where it sits in the same compound as its parent, as in the example above. A 0.7 mate
could name any two occurrences of the tree (`#shoulder_yoke` deep in one sub-assembly,
`#servo` in another). For those, build the assembly where it stands, author both joints
there with the mate's name as their label, and call no `connect_to`: the engine pairs a
moving joint with the rigid joint of the same label (the nearest in the tree), and two rigid
joints of one label fasten their parts. Two details decide whether the values read right:

- **Give each joint in its part's enclosing frame.** A joint constructor reads its frame in
  the frame its part's `location` is in -- the compound that holds the part -- not the world.
  Carry a world datum in first: `axis.located(holder.inverse())`, where `holder` is the world
  location of the part's enclosing compound (the product of the locations above it).
- **Put the child's rigid frame at the revolute joint's own frame**, not at a plane made from
  the world axis: `child_holder.inverse() * parent_holder * revolute.location`. A plane of
  your own differs from the joint's by a turn about the axis, so the value as built is that
  turn instead of 0, and every mechanism state and motion is off by it.

```python
def author_joints(arm, mates):                             # mates: step 1's records, at joint zero
    nodes = {}                                             # label -> (part, its holder's world location)
    def walk(node, holder):
        nodes.setdefault(node.label, (node, holder))
        for child in node.children or ():
            walk(child, holder * node.location)
    walk(arm, bd.Location())
    for m in mates:
        (p, p_holder), (c, c_holder) = nodes[m.parent[1:]], nodes[m.child[1:]]
        if m.kind == "revolute":
            axis = bd.Axis(m.axis["origin"], m.axis["dir"]).located(p_holder.inverse())
            joint = bd.RevoluteJoint(m.name, p, axis=axis, angular_range=tuple(m.limits["value"]))
            bd.RigidJoint(m.name, c, c_holder.inverse() * p_holder * joint.location)
        else:                                              # fastened: at the child's own origin
            frame = c_holder * c.location
            bd.RigidJoint(m.name, p, p_holder.inverse() * frame)
            bd.RigidJoint(m.name, c, c_holder.inverse() * frame)
```

`cadgen inspect <id>` lists the joints with each one's range and its value as built (0 for
every joint when the frames are right), and the mechanism states. A 0.7 fastened mate
between occurrences the tree already nests needs no joint: a part below a jointed
sub-assembly moves with it.

### 5. Move clips to configuration sequences and animations

A 0.7 clip was a JavaScript module string on `@step(animation=...)`, its `update(t, m)`
moving occurrences directly. 0.8 has two layers, each true to its format:

- **The mechanism's own motion** (a gait, a door opening, an engine running, a robot's
  choreography) is a configuration sequence over its joints, kept in the document:

  ```python
  from cadgen.ap242 import configuration_sequence

  configuration_sequence(turntable, "spin", sweep={"platter": (0, 360)}, duration=4, ease="linear")
  configuration_sequence(arm, "cycle", [(0, "folded"), (2, "reach"), (5, "folded")])
  configuration_sequence(arm, "showcase", pose_at, duration=23.4)   # pose_at(t) -> {joint: value}
  ```

  A clip whose `update(t, m)` computed its pose from `t` (keys eased by hand, a breathing
  drift on top) takes the last form: port the pose computation to a Python function of `t`
  that returns joint values by joint label, and the engine samples it to within 1e-3 radian.
  A clip that rotated occurrence ids about mate axes, and counter-rotated parts mated
  elsewhere, rotates nothing now: the joints say what each value carries. The page's Motion
  tool plays a sequence, and every GLB exported from the model carries it as a glTF
  animation of its name.

- **A showcase** (an explode, a reveal, a part spinning for show, a cover hidden) is a
  GLB's own animation, never written into the document:

  ```python
  from cadgen.gltf import animation

  show = animation(box, "showcase", duration=4)
  show.explode("feet/*", direction=(0, 0, -1), distance=20, start=0.5, end=2)
  show.rotation("latch", axis=(0, 0, 1), turns=2, start=1, end=3, interpolation="LINEAR")
  show.hide("latch", at=3)
  ```

  It is baked into every GLB exported from the model: `cadgen export <id> box.glb`,
  `export(box, "box.glb")`, or `cadgen export box.xbf box.glb` from an xbf the model
  exported, which records the compiled tracks. The page and a STEP show nothing of it. The
  viewer's Animation section plays a GLB's animations.

Remove helper joints that existed only to slide parts apart for an explode: that is an
animation now. A clip's `loop`, `label` and `description` have no counterpart (a player
repeats a clip, and a sequence is called by its name), nor do `.opacity` and tube
deformation; `.visible(false)` is `.hide`. Snapshots never play motion: 0.7's
`--animation`, `--time` and `--video` are gone.

### 6. Move materials into the body; make colours hex

`materials=` on the decorator is gone. Use `bd_materials`, build123d's native material
library. Set a material in the body after the part's last geometric operation, then
assign any explicit colour:

```python
# 0.7
@step(materials={"definitions": {"cast": {"name": "As-cast steel", "roughness": 0.85, "metalness": 0.2}},
                 "assignments": [{"targets": ["#housing"], "material": "cast"}]})

# 0.8.3, in the body
from bd_materials import metals
from cadgen import paint

cast = metals.mild_steel()
cast.pbr = cast.pbr.override(roughness=0.85, metalness=0.2)
housing.material = cast
housing.color = "#2E3742"  # material assignment sets colour; apply an override after it
```

**Choose the material and its look.** Catalogue factories such as `metals.aluminum()`,
`metals.brass()` and `plastics.abs_()` return a native `FinishedMaterial` (`plastics` is
also imported from `bd_materials`). Its `.material` holds physics; `.pbr` is a native
`threejs_materials.PbrProperties`. Edit the look with `.pbr.override(...)` and assign
that result back before giving the material to the shape. Its controls include
`color`, `metalness`, `roughness`, `ior`, `clearcoat`, `clearcoat_roughness`, `anisotropy`,
`anisotropy_rotation` (radians), `transmission`, `attenuation_color`,
`attenuation_distance` (metres), `emissive`, `emissive_intensity`, and `opacity`.

For custom physics, use a native family factory:

```python
from bd_materials.core import Range

alloy = metals.custom_metal(
    "Project alloy", density=2700,
    modulus_of_elasticity=Range(68, 72), tensile_strength=Range(280, 320))
```

Density is a single value in kg/m³. Mechanical properties are native ranges, with
modulus in GPa and strengths in MPa; a custom factory also accepts a number as an exact
range. `shape.mass()` and the physical material's `mass(volume_mm3)` return grams by
default; `cadgen inspect` reports kilograms.

**Assign materials before colour overrides.** Native material assignment sets the shape's
colour, including an inferred preview alpha for transmission (`transmission=1` gives
alpha `0.3`), even with PBR `opacity=1`. To keep an opaque base colour with physical
transmission, assign an opaque `housing.color` after its material, as above. An assembly
material is inherited by children without one; assign it before reading their materials.
`paint(part, faces, colour_or_material)` gives faces their own colour or native material.

**Colours are sRGB, as you pick them.** Shape colours and plain paints take hex strings
(`"#2E3742"`, `"#38414D6B"` with alpha as a byte), 0–255 integer tuples or build123d
`Color`. Native PBR base-colour floats are sRGB ratios; emission and attenuation floats
are linear. Hex strings avoid that distinction.

| 0.7 | 0.8.3 |
| --- | --- |
| `srgb("#2E3742")` | `"#2E3742"` |
| `srgb("#38414D", 0.42)` | `"#38414D6B"` |
| A linear base colour `(0.2, 0.3, 0.9)` in a material definition | Set the look with `material.pbr = material.pbr.override(color="#7c95f3")` before assigning the material; the sRGB hex preserves the same look |
| `paint(shape, faces, (1, 0, 0))`, `paint(..., "orange")` | `paint(shape, faces, "#ff0000")` or `"#ffa500"`: a hex string, 0–255 integers, a build123d `Color` or a native `FinishedMaterial` |
| `shape.color = bd.Color(0.5, 0.5, 0.5)` meant as linear | read as build123d defines it, sRGB: `#808080`. For the old look, give the hex of the linear value (`"#bcbcbc"` for 0.5) |

XBF keeps native physics and the complete resolved PBR look. The viewer and GLB retain
scalar PBR controls; OCCT snapshots use their documented approximations. Native texture
maps survive XBF, but the viewer, GLB export and snapshots refuse them until UV mapping
is supported.

### 7. Use the selected engine: ids, pages, links and commands

The selected engine owns documents and worker lifetimes. Port 3245 is the
normal choice; `CADGEN_PORT` selects another. Every project's environment, the one
`cadgen run` makes or one of your own, attaches to that same selected engine. Its warm
workers run in that interpreter with its dependencies; client, worker and engine need
not share a cadgen release, only a protocol, a document format the engine reads and the
OCP line. Changing the project interpreter or its import environment starts a fresh
worker; ordinary repeated runs keep its memo.

Saved documents, cached bytes, Recents and thumbnails are shared across ports,
as are preferences, installation records and the user's page token. Changing ports
selects another live engine and its workers while keeping the same saved library.

- Run `cadgen run src/assembly.py`. It executes normal Python control flow;
  importing or decorating a model never builds it.
- A `@model` call returns a document handle, with `.id`, `.url`, `.shape` and export
  operations. The build prints an id and authenticated page URL. A file decorator
  writes its explicitly named outputs too; bare `@model` writes no deliverable.
- Tabs and CAD tools select a document at `/<id>`. `cadgen viewer <id>` and
  `cadgen serve <id>` attach to the selected engine and print a link. They never
  start a server or build source. Keep authenticated links private.
- Documents survive worker retirement and engine restarts through the engine's
  document cache. A restart opens the last built state; it does not inspect code
  for changes. Run the project script explicitly to update it.
- A missing document names its defining script. Run that script (`cadgen run`)
  with the selected `CADGEN_PORT`; the engine never executes it for you.
- `cadgen status` lists the selected engine's documents and workers. `cadgen stop`
  stops only that engine. No engine stops another to claim its port, except that a
  newer release's retires an older one once nothing is using it.
- `cadgen delete <id>` removes the document record and cached bytes, never a file
  belonging to the project. A later explicit build creates the document again.
- `Model.build(daemon=False)` builds offline in the caller. Python `export` and
  `snapshot` accept `daemon=False` too. These explicit modes need no engine and
  expose no live document or viewer URL; connection failures never choose them.

| Action | Command |
| --- | --- |
| Run a project model | `cadgen run src/model.py` |
| Start the server explicitly | `cadgen server` (or the pinned uvx bootstrap above) |
| Inspect a built document | `cadgen inspect <id>` |
| Open its page | `cadgen viewer <id>` |
| Export a deliverable | `cadgen export <id> part.step part.stl` |
| Draw a still | `cadgen snapshot <id> review.png` |
| Check or stop your selected engine | `cadgen status`, `cadgen stop` |
| Clear an unwanted document | `cadgen delete <id>` |

There is no project connection object or named context. Select a port in the
process environment or CLI, never in a decorator. The private IPC directory,
`CADGEN_ENGINE_DIR`, retains its permissions and authentication; it is not a
second public engine selector. No command imports a script to build a document.

### 8. Replace `read_scene` refs, checks and tools that read 0.7's files

**References are the engine's grammar, for models and STEP files alike.** A 0.7 ref,
`/work/STEP/assembly.step#o1.2.f7`, named an occurrence by its position and a face by its
number in one saved revision, and `read_scene(path).resolve(ref)` resolved it; the viewer
had a grammar of its own for STEP pages. Both are gone. A 0.8 ref names the document (a
model's id, or a file's absolute path), `#`, the occurrence by the labels on its way from the
root, then the element by the code that made it, or by its number:

```text
b48e875e-f53d-5535-ada3-a2a300690f6f#kit/hand/finger.2/f:finger.body.3;M:finger.relief
/work/STEP/assembly.step#assembly/bracket/face 7
```

`hand/finger.2` is the second component labelled `finger` in `hand`; a label with spaces is
written as it is. Element names come from the function and the variable that made each
feature, so moving code renames nothing and a dimension edit keeps every name; a STEP that
0.8 exported carries them too. The viewer copies refs in this form (Quick Edit's
`References:`). Resolve one with `cadgen inspect`:

```bash
cadgen inspect <uuid> "hand/finger.2/face 7"
cadgen inspect STEP/assembly.step "assembly/bracket/face 7"
```

It answers what the ref names, with the kernel's facts and `made_by`, the function, file
and line of the code that made the element. An old ref resolves to nothing and is refused
with the nearest names (`has no part or assembly o1.2.f7; nearest: ...`): select again in
the viewer, or take the names `cadgen inspect` prints. Code of your own that addresses
occurrences by tree position (`o1.2.15`) for its own purposes may keep doing so; cadgen no
longer reads them.

**A check calls the model and measures what it returns.** Copy the project helpers
`world_parts` and `find_part` from
[Opening geometry](../../skills/cad/references/inspection-and-validation.md#opening-geometry)
into the check first. They accumulate each parent's placement before measuring and
refuse a missing or ambiguous leaf label:

```python
# 0.7                                         # 0.8
from cadgen import read_scene                 from cadgen.geometry import closest_points
scene = read_scene("STEP/kit.step")
...                                           from kit import kit

                                              tree = kit().shape
                                              plate, post = find_part(tree, "plate"), find_part(tree, "post")
                                              print(closest_points(plate, post).distance)
```

`cadgen.geometry` (`closest_points`, `overlap_volume`, `mass_properties`, the topology
checks) is unchanged. In 0.8 previews, `select(...)` resolved refs in Python; it is gone
too, for `cadgen inspect` and build123d's selectors in the body, and
`snapshot_job(packet, source)` is `cadgen.snapshot(source, job=packet)`.

**A tool that read 0.7's files reads the model.** Project tooling built on 0.7 -- a URDF
exporter, a mass report, a collision checker -- often read the STEP's `<name>.step.json`
sidecar (its `kinematics` block, `childId` occurrence ids) or reached into cadgen's private
modules (`cadgen.store.trees.capture_tree`, `cadgen.store.objects.read_object`,
`cadgen._internal.doors.document_tree`). The sidecar is never written and the modules are
gone. Read instead:

- the geometry from the model, `robot().shape`, or from an exported STEP with `read_step`.
  Both keep a tree of `.children` and parent-relative `.location` values; `.leaves`
  alone does not apply ancestors' placements. Use `world_parts` above for measurements
  in world coordinates;
- the mechanism from your own data (step 1's records), or from `cadgen inspect <id> --json`,
  whose summary lists the joints, their ranges, the states and the sequences.

Three things differ from what 0.7's store handed such a tool. `read_step` gives the STEP's root
assembly wrapped in a compound of the same name: tree-position ids (`o1.2.15`) count from the
assembly inside it. A part's `.color` is the sRGB a person picks (`#A7ACB0` reads 0.655, where
0.7's store gave the linear 0.386), so a glTF writer converts it to linear. And no per-face
colour is read back: a vendor board's painted faces take the part's colour. Equal parts share
one shape (`node.wrapped.TShape()`); a digest of the part's own BRep at its origin keys them.

### 9. Delete 0.7 leftovers

- **Sidecars**: `<name>.step.json` and `.params.js` files beside your STEP files are read
  by nothing. Delete them once each model is ported.
- **Old exports**: STEP, STL, 3MF and GLB files 0.7 runs wrote stay where they were and
  nothing rewrites them, the STEP files of stages that are `@memo` now among them. Export
  them again from the ported models, or delete them.
- **The project's 0.7 notes**: commands and rules in its README or `AGENTS.md` that name
  `uvx ... cadgen==0.7.x`, `--force`, `cadgen store why`, `cadgen step snapshot`,
  `cadgen viewer --detach`, `?file=` links or `from cadgen import build123d`.
- **The 0.7 store.** cadgen 0.7 kept a cache store that can hold gigabytes (`objects/` and
  `index/` in its cache folder), and a few state files of its own (its sidebar views, its
  snapshot browser's lock, its viewer's log, its Recents log). 0.8 keeps its own document cache
  in the same folder, under `documents/`, and never reads or writes 0.7's. Whether a 0.7 is
  still installed cannot be told (0.7 never registered itself), so they retire themselves:
  `cadgen doctor` says they are there, with their size and when they were last written, and
  `cadgen doctor --prune` removes them once nothing has written them for 7 days -- a 0.7 in use
  writes its store at every build:

  ```
  removed cadgen 0.7's store and 2 state files (92.0 MB), last written 2026-10-14
  ```

  Once no 0.7 is left in any agent app (no 0.7 plugin anywhere), `cadgen doctor --prune
  --all-versions` removes them at once, however recently written. 0.8 loses nothing either way.

  | Platform | 0.7's store is in |
  | --- | --- |
  | macOS, Linux | `~/.cache/cadgen`, or `$XDG_CACHE_HOME/cadgen` when `XDG_CACHE_HOME` is set |
  | Windows | `%LOCALAPPDATA%\cadgen` |
  | anywhere | the folder `CADGEN_CACHE_DIR` named, if you set it for 0.7 |

  Your settings, telemetry answer and recent files live in cadgen's state folder and stay.

- **Quick Edit's preference**: Quick Edit is always available; a `features.quickEdit:
  false` left in settings does nothing.

### 10. Verify

1. Run each root script: `cadgen run src/assembly.py` exits 0 and prints an id and a page
   for every model it calls. A second run takes the documents (`took ... nothing ran`).
2. Run `cadgen inspect <id>` on each mechanism: its joints, each at 0 as built, its states
   and its sequences.
3. Open each page and compare it with the 0.7 model: parts, colours, materials and the
   tree. For a mechanism, try Position's sliders and presets, and play each motion.
4. Run your checks and tests: they call the models now.
5. Export what you deliver and compare it with the 0.7 files you kept, by snapshot
   (`cadgen snapshot STEP/old.step a.png` beside `cadgen snapshot <uuid> b.png`) and by
   measurement: `cadgen inspect` on both files gives their part counts and bounds, and
   `cadgen inspect STEP/old.step <part>` beside `cadgen inspect <uuid> <part>` each part's world
   bounds. Equal overall bounds do not prove equal placements: compare the parts of every
   sub-assembly a stage moved (step 2, item 8). Keep the 0.7 STEP until they agree.

## Telemetry

Your answer carries over in the same settings, `cadgen telemetry status|on|off` works as
before, and `DO_NOT_TRACK=1` or `CADGEN_TELEMETRY=0` turns it off for a process. New in
0.8: the viewer also counts which of its tools and settings are used, each as a name from a
fixed list (Select, Measure, Explode, Clip, the display modes, Preview, playback, Export, the
home's search and filters, and the like), with how many times each was used and, for a tool
that stays on, how many whole seconds it was on -- never what you typed, a value you chose
(other than a choice that is itself a name on the list, such as a display mode), or a file's
or a part's name. The CAD app's `cad_telemetry` tool is gone: you answer in the CAD app's
menu, the CAD Viewer's, or with `cadgen telemetry`.

## What lands where

| Thing | 0.7 | 0.8 |
| --- | --- | --- |
| A model | `@step(out=...)` (or a mesh decorator) on a parameterless function | `@model` on a parameterless function; parameters on plain helpers |
| A cached stage | a child model writing its own STEP | `@memo` on the stage function, no file |
| A run | `uvx ... cadgen==0.7.x python model.py`, writing every declared file | `cadgen run model.py` builds in the selected engine, starting it when none is running; bare `@model` writes no deliverable, file decorators write their named outputs |
| A file | written by every run, or by `cadgen <format> build` | explicitly declared by file decorators, or requested by `cadgen export` or `exports.py` |
| The model's document | a STEP plus a `<name>.step.json` sidecar | held by the engine at `/<uuid>`; an `.xbf` when saved as one |
| Kinematics | `kinematics=` mates, couplings, poses, in the sidecar | build123d joints and `cadgen.ap242`, in the document |
| Animation | a JavaScript clip module in the sidecar | `configuration_sequence` (the document) or `animation()` (a GLB) |
| Materials | `materials=` definitions and assignments | `part.material = ...` in the body |
| Colours | linear floats, `srgb(...)` | sRGB hex or 0-255 integers |
| Refs | `#o1.2.f7` | `<id or path>#path/to/part/f:function.feature.n` |
| Stale or current | `cadgen store why` | a run: `took ... nothing ran`, or `rebuilt: <what changed>` |
| The cache | the store in `~/.cache/cadgen` | the warm worker's memory, and each model's document as last built in `~/.cache/cadgen/documents`, kept until deleted, with the engine's bytecode under `pycache/` |
| The viewer | its own process, `?file=` links, page sessions | the engine's one page, `/<uuid>`, on port 3245, links good for a day |

## Troubleshooting a half-migrated project

- **A run prints nothing and exits 0.** The script's `__main__` calls no model, or the
  model is still undecorated. Decoration only declares; add the calls. (A script that only
  calls `export()` prints a line per file it wrote.)
- **The project still writes STEP files and sidecars.** Its commands still run 0.7
  (`uvx ... cadgen==0.7.x`): Prerequisites, step 1.
- **`ModuleNotFoundError` for one of the project's own packages.** `PYTHONPATH` does not
  name the import root (Prerequisites, step 4).
- **`ModuleNotFoundError` for another package under `cadgen run`.** The project does not
  declare it: add it to `requirements.txt`, `pyproject.toml` or the script's inline
  metadata (Prerequisites, step 1).
- **`TypeError` naming `kinematics`, `materials` or `animation`.** A decorator still
  carries a 0.7 argument. Move it into the body (steps 4 to 6).
- **`ImportError: cannot import name 'build123d' from 'cadgen'`.** Step 1:
  `import build123d as bd`.
- **`ImportError` or `AttributeError` for `revolute`, `fastened`, `couple`, `srgb`, `report`,
  `track`, or a `cadgen.store` or `cadgen._internal` module.** Step 1's table; step 8 for
  tools.
- **`AttributeError: 'Document' object has no attribute 'moved'`** (or another shape
  method): a child model's call used as a shape. Compose `child().shape` (step 2).
- **The model builds, but some parts sit a few millimetres from where 0.7 put them**, with the
  same overall bounds. A stage moves leaves inside a sub-assembly that keeps its own placement
  in 0.8: hand it the 0.7 shape (step 2, item 8).
- **A joint's value as built is not 0, or every state looks turned.** The child's rigid
  frame is not the revolute joint's own frame (step 4).
- **A build fails naming a pair the built tree contradicts.** A part moved after its
  `connect_to`, or `connect_to` across compounds: author the joints where the parts stand
  and pair them by label (step 4).
- **Colours look washed out or too dark.** A colour meant as linear floats is now read
  as sRGB: give the hex of what you see (step 6).
- **A link opens the home instead of the model.** It is a 0.7 or pre-release link
  (`?file=`, `/s/...`). Run the model and use the page it prints.
- **A page says it needs its link.** Its link is more than a day old, and this browser has
  not been signed in within 30 days: run the model again, or `cadgen viewer <id>`.
- **A page or `cadgen inspect` says the document is not saved.** Its file in the engine's
  cache is gone (deleted by hand), or was never written (the cache folder could not be
  written). Run the command it prints.
- **The viewer shows an old mechanism or none.** A sidecar is read by nothing: the
  mechanism must be in the model's body (step 4).

## Code written against an 0.8 preview

Projects written against a 0.8 pre-release may use names the release renamed or removed,
and the engine such a project ran holds records and documents made under the pre-release's
identities and build closures.

**`key="x"` is now `name="x"`.** `key=` is an unexpected keyword argument. A name belongs to
the folder of its script: the same name in two folders is two models, and in one folder a
second declaration of it is refused, naming both `file:line`, until the file that held it
is gone or has run again without it (`cadgen run <that file>`). Moving a name to another
file of its folder keeps its document.

**Saved XBF documents and build reuse are separate.** Current cadgen writes `xbf/10`;
the engine reads saved `xbf/8`, `xbf/9` and `xbf/10` documents. Loading an `xbf/8` document
converts material metadata in memory without executing its model. The original bytes,
cache record and revision, build closure and toolchain provenance stay unchanged. A
separate migration record describes the idempotent conversion.

Saved files, cached models and cached handed-over shapes follow the same supported-format
read and migration policy. A different original native version or platform does not by
itself require their source to run again. Strict native compatibility applies to live
clients, servers, workers and shape transfers, separately from saved-document access.

To save an upgraded document, choose a different XBF path:

```bash
cadgen export saved-v8.xbf upgraded.xbf
```

The complete upgraded XCAF document is saved atomically; exporting over the source path is
refused. Exporting a cached document by id to XBF also saves its upgraded form.
The viewer's original-file XBF download returns the original bytes. Ordinary current-format
XBF-to-XBF translation remains refused. Unsupported formats or failed conversions preserve
the original bytes and cache record and report a clear error.

Native materials and their libraries entered the key in `xbf/9`. The current `xbf/10`
adds the worker's startup dependency fingerprint and Python version alongside the format, native
toolchain, code and inputs.
Startup never invents a missing runtime identity or runs the script. The next explicit
`cadgen run model.py` rebuilds a runtime-less model in the project's environment;
viewing a last-built document does not imply build-cache reuse. See the
[persisted-document policy](../../packages/cadgen/README.md#the-design-laws).

The independent startup identity pass gives each record its namespace and name, and a
model's record the fingerprint of its script. A record that `key=` named moves, with its
saved document, to the id its folder and name give. This changes identity, not native
producer or runtime provenance. A record that cannot be read or moved stays as it is,
is never deleted, and is counted by `cadgen status`.

Rename `key=` to `name=` in the scripts. The models keep their ids. The other names the
release renamed or removed:

| Before | Now |
| --- | --- |
| `from cadgen.engine import model, memo, ...` | `from cadgen import model, memo, ...` |
| `configuration(assembly, name, **values)` | `cadgen.ap242.mechanism_state(assembly, name, **values)` |
| `motion(assembly, name, ...)` | `cadgen.ap242.configuration_sequence(assembly, name, ...)`, the same arguments |
| `couple(...)` of revolute joints | `gear_pair(assembly, name, **joints)` |
| `couple(...)` of a revolute joint and prismatic ones | `rack_and_pinion_pair(assembly, name, **joints)` |
| `couple(assembly, name, joint=(turn, travel))` of one cylindrical joint | `screw_pair(assembly, name, joint=360 * travel / turn)`: its pitch; the value is now the turn in degrees |
| `from cadgen import mechanism_state, configuration_sequence, gear_pair, ...` | `from cadgen.ap242 import ...` |
| `from cadgen import animation` | `from cadgen.gltf import animation` |
| `cadgen build SOURCE`, `cadgen.build(code_or_shape, ...)`, `cad_build` | none: a decorated function called from Python, in a `.py` file; a shape made elsewhere is handed over, `model(shape, name=...)` |
| `@xbf` + `@glb` stacked so a GLB bakes its animations | `@model`; `cadgen export <id> model.glb` or `export(x, "model.glb")` bakes them |
| a model call returning its shape (`base = plate()` used as a shape) | the call returns the document's handle: compose `plate().shape` |
| `@model(store="copy")`, `store="pointer"`, `store="memory"` | none: no store argument. A model lives in a `.py` file; a cell's shape is handed over, `model(shape, name="plate")` |
| `@model(id="<uuid>")` | none: an id is derived (the script and the function), or `name="plate"` names one within its script's folder |
| `@model` stacked with `@xbf`, `@step` or another file decorator | one or the other; the stack is refused |
| `Model.export(...)`, `Model.snapshot(...)`, `Model.document` on the decorated function | the handle a call returns: `arm().export(...)`, `arm().snapshot(...)`, or `export(arm(), ...)` |
| `cadgen export DOC OUT --pose NAME`, `export(..., pose=)` | a model returning `posed(assembly, NAME)`, exported |
| `cadgen export DOC OUT --part OWNER`, `export(..., part=)` | the part's own `@model`, exported |
| `cadgen export ... --no-daemon`, `cadgen snapshot ... --no-daemon` | the same command without the flag |
| `select(source, ref, kind=None)` | `cadgen inspect DOC REF` (`cadgen.inspect(DOC, REF)`) |
| `cadgen.engine.api.snapshot_job(packet, source)` | `cadgen.snapshot(source, job=packet)` |
| `cadgen.serve(doc)`, `cadgen.status()`, `cadgen.stop()`, `cadgen.daemon()` | the commands `cadgen serve DOC`, `cadgen status`, `cadgen stop`, `cadgen server` |
| a stale badge, a stale notice on `export`, `snapshot` or `inspect` | none: a document is what its last run made; run it again |
| `GET /__cad/browser` (a card's lookup of a browser page) | none; a card's Open in browser is `POST /__cad/browser/open`, the app's alone |
| a page at `/?doc=...`, `/?file=...`, `/s/<session>/...` | `/<id>`; an old link opens the home |
| `XBF/model.xbf` written by every run as the model's cache | no file: the engine caches the document; export an xbf only as Save As |

## Migration complete when

- [ ] Every model is `@model` on a parameterless function, its values on plain helpers,
      and each variant a named model; cached stages are `@memo`.
- [ ] `import build123d as bd` everywhere; no `from cadgen import build123d`, no private
      cadgen module.
- [ ] The project's own docs run scripts with `cadgen run` (tests in an environment of their own, with cadgen 0.8), declare the project's dependencies, and set `PYTHONPATH` where needed.
- [ ] No `kinematics=`, `materials=` or `animation=` anywhere; mechanisms use build123d
      joints and `cadgen.ap242`, showcases `cadgen.gltf`.
- [ ] Every colour is hex or 0-255 integers.
- [ ] Deliverables come from `cadgen export` or an `exports.py`.
- [ ] No `.step.json` or `.params.js` file remains, and no tool reads one.
- [ ] Every root script runs clean and prints a page for each model; each page has been
      opened and reviewed.
- [ ] `cadgen doctor` names no 0.7 store, or says when `--prune` removes it.

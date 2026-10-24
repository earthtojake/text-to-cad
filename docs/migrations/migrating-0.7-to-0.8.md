# Migrating a CAD project from cadgen 0.7 to 0.8

This is a hand-migration playbook. Work through it top to bottom with a 0.7 project open
and you will end with a working 0.8 project. The agent-facing counterpart, a table of
every old form and its replacement, is
[`skills/cad/references/migrations.md`](../../skills/cad/references/migrations.md); an
agent with the CAD skill installed can do most of this for you.

## Read this first: there is no compatibility layer

0.8 ships no backwards compatibility, on purpose:

- No shims, no aliases, no deprecated keyword arguments, and no codemod.
- **No teaching errors.** A retired flag is an unrecognized argument, a retired name an
  `ImportError` or `AttributeError`, a retired decorator argument a `TypeError`. None of
  those errors mentions 0.7 or what the thing used to be called.

So when something fails during this migration, the error tells you what 0.8 wants, not
what you did. Read it as a spec.

### The one-paragraph summary

0.8 replaces 0.7's file pipeline with one engine. A model is still a parameterless
Python function, but it is decorated `@model` and a run writes nothing: `python
model.py` rebuilds the model in a warm engine, prints its document's id and a link to
its page, and every page open on it updates. Think of the page as the open document, the
script as its feature tree, running the script as the rebuild, and export as File →
Export: `cadgen export <id> part.step` writes a file when you want one. Mates, couplings,
poses and JavaScript clips become build123d joints and STEP AP242's mechanism
vocabulary in the model's body (`cadgen.ap242`), and showcase animations become a GLB's
own channels (`cadgen.gltf`). Colours are sRGB hex. `import build123d as bd` is free
until it is used. The 0.7 store, sidecars and STEP-format commands are gone.

## Prerequisites

1. **Update the plugin, or the pin.** The CAD plugin and its skills run cadgen as
   `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.0 cadgen`; a
   project that pins cadgen itself moves its pin to `cadgen==0.8.0`. The Python floor is
   unchanged (3.11). cadgen no longer depends on Playwright: snapshots are drawn by
   OCCT, so no headless browser is downloaded.

2. **Confirm what you have.**

   ```bash
   cadgen --version          # cadgen 0.8.0
   cadgen doctor             # the installation in use, the CAD kernel, the engine
   ```

3. **Stop 0.7's viewer.** A 0.7 viewer still running is 0.7's own process, on its own
   port: stop it with 0.7's `cadgen viewer stop`, or let it be. 0.8 starts its own
   engine on first use.

4. **Commit your work.** This migration deletes files.

## Migration checklist

Do these in order. Later steps assume earlier ones.

- [ ] 1. Rewrite imports
- [ ] 2. Convert each model to `@model`, each variant a model of its own
- [ ] 3. Move files out of the model: exports on request, or `exports.py`
- [ ] 4. Move mates to build123d joints and the mechanism's AP242 functions
- [ ] 5. Move clips to configuration sequences and animations
- [ ] 6. Move materials into the body; make colours hex
- [ ] 7. Learn the one engine: ids, pages and commands
- [ ] 8. Replace `read_scene` refs and checks
- [ ] 9. Delete 0.7 leftovers
- [ ] 10. Verify

---

### 1. Rewrite imports

```python
# 0.7                                   # 0.8
from cadgen import build123d as bd      import build123d as bd
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
proxy is gone.

**The root holds exactly eighteen names**: `model`, the file decorators `xbf`, `step`,
`glb`, `stl`, `threemf` and `dxf`, `memo`, `Material`, `materials`, `paint`,
`read_step`, `read_xbf`, `read_mesh`, the operations `export`, `snapshot` and
`inspect`, and `__version__`. Two namespaces hold the standards' vocabulary:
`cadgen.ap242` (`mechanism_state`, `configuration_sequence`, `gear_pair`,
`rack_and_pinion_pair`, `screw_pair`, `posed`) and `cadgen.gltf` (`animation`).
Everything else 0.7 exported from the root is gone:

| Removed (0.7) | Instead (0.8) |
| --- | --- |
| `cadgen.build123d` | `import build123d as bd` |
| `revolute`, `slider`, `cylindrical`, `fastened`, `MateTarget`, `AssemblyHelper`, `target` | build123d's joints in the body (step 4) |
| `couple` | `cadgen.ap242`'s `gear_pair`, `rack_and_pinion_pair`, `screw_pair` (step 4) |
| `srgb`, `srgb_to_linear`, `linear_to_srgb` | the hex itself: `"#2E3742"` (step 6) |
| `report`, `track` | nothing: delete the calls. Progress is reported per `@memo` call and child model, by its function's name |
| `read_scene`, `StepScene`, `Occurrence`, `Selection` | `cadgen inspect` and the model's own tree (step 8) |
| `compound_from_instances` | `bd.Pos(...) * part`: every placement shares its shape |
| `label_shape`, `label_text` | `shape.label = "name"` |
| `ensure_step_topology_artifact` | nothing: the viewer reads a STEP as it is |

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
   `__main__` makes prints its model's id and page.
5. **A model call returns its document, not its shape.** The call returns a handle:
   `.id`, `.url` (its page), `.name`, `.shape` and `.export(...)`. An assembly's body calls
   its part models and composes their shapes -- `plate().shape` where 0.7 had `plate()` --
   places them and labels the placements. A child builds in the same run and keeps its own
   document, id and page. A check reads `kit().shape`; the shape comes into the calling
   process when it is first read.
6. **One declaration per function.** Bare `@model` is a document with no file; the file
   decorators (`@xbf`, `@step`, ...) are a document with those files. Stacking `@model` on a
   file decorator is refused: drop `@model`.
7. **Mark only big stages `@memo`.** `@memo` (new in 0.8) marks a function the engine
   may replay whole instead of running, keyed by its code and its arguments. Since every
   kernel call is replayed anyway, a memo hit saves only Python time (0.1 to 0.4 ms per
   kernel call): mark a whole sub-assembly stage of a thousand kernel calls or more
   (measured at 1.3 to 3 s each, twice as fast on an edit), never a part and never a
   helper called many times.

`python model.py` takes no options. 0.7's `--force`, `--json`, `--verbose`, `--profile`,
`--mesh-tolerance` and `--no-daemon` are unrecognized arguments; there is nothing to
pass:

| 0.7 | 0.8 |
| --- | --- |
| `python model.py --force` | `CADGEN_ENGINE_MEMO=0 python model.py` (no memo hits) |
| `python model.py --json` | `bracket.build()` from Python returns the report as data |
| `python model.py --profile` | `bracket.build(profile=True)` |
| `python model.py --no-daemon`, `CADGEN_DAEMON=0` | nothing: every run goes through the engine. `Model.build(daemon=False)` remains as a seam for tests and debugging (cold, in your process, nothing served) |
| `@stl(mesh_tolerance=...)`, `--mesh-tolerance` | nothing: every mesh is made at FreeCAD's default tolerance |

### 3. Move files out of the model: exports on request, or `exports.py`

In 0.7 a run wrote every file its decorators declared. In 0.8 a run writes nothing: the
engine holds the model's document, and a file is written from it when you ask, with no
rebuild:

```bash
python src/bracket.py                                   # prints id: <uuid> and view: <url>
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

An export takes a document and its destinations, and nothing else. A file in another
pose is a model of its own that returns the posed assembly (step 4), and a part on its
own is that part's own model.

**The file decorators still work.** `@xbf`, `@step`, `@glb`, `@stl`, `@threemf` and
`@dxf`, with `out` as their only argument (relative to the script), still write their
file whenever the model runs. A project can keep them while it migrates; 0.8's guidance
is `@model` and explicit exports. `kinematics=`, `materials=`, `animation=` and the mesh
tolerances are gone from every decorator.

**The xbf is Save As.** `.xbf` is cadgen's own document format: parts and placements,
names, colours, materials, element names and the mechanism, read back losslessly.
Export one only to share a model without its code, or to compose it in another project
with `read_xbf`; an engine restart needs none (below). It is not a build stage. A vendor STEP converts to one once, and `read_xbf` reads it many times
faster than `read_step` parses the STEP:

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
| `cadgen.revolute(name, parent=, child=, origin=, direction=, limits=)` | `bd.RevoluteJoint` on the parent's part, a `bd.RigidJoint` of the same label on the child's, connected with `connect_to` |
| `cadgen.slider` | `bd.LinearJoint` (`linear_range`) |
| `cadgen.cylindrical` (`.turn`, `.travel`) | `bd.CylindricalJoint`, valued `(angle, distance)` |
| `cadgen.fastened` | two connected `bd.RigidJoint`s |
| `"poses": {"bent": {...}}` | `mechanism_state(assembly, "bent", **values)` |
| `cadgen.couple(name, {dof: ratio}, limits=)` | `gear_pair` (revolute joints), `rack_and_pinion_pair` (a revolute joint and prismatic ones) or `screw_pair` (one cylindrical joint's pitch); the range comes from the joints' limits |
| a mate `axis` given as a ref (`"#lever.f2"`) | a `bd.Axis` computed in the body from the live shape |
| `cadgen export ... --pose NAME` (an 0.8 preview), `snapshot --kinematics` | a posed model `posed(arm().shape, NAME)`, exported; `cadgen snapshot <id> out.png --pose NAME` to draw one |

The as-built state is now the value each joint is connected at, so connecting at 0 with
both frames on the axis keeps the parts where they were built. A coupling of one joint
is that joint. The page's Position poses a document live, with a slider per coupling and
per joint no coupling moves, and the mechanism states as presets. A STEP export is
placements only: STEP carries no mechanism.

### 5. Move clips to configuration sequences and animations

A 0.7 clip was a JavaScript module string on `@step(animation=...)`, its `update(t, m)`
moving occurrences directly. 0.8 has two layers, each true to its format:

- **The mechanism's own motion** (a gait, a door opening, an engine running) is a
  configuration sequence over its joints, kept in the document:

  ```python
  from cadgen.ap242 import configuration_sequence

  configuration_sequence(turntable, "spin", sweep={"platter": (0, 360)}, duration=4, ease="linear")
  configuration_sequence(arm, "cycle", [(0, "folded"), (2, "reach"), (5, "folded")])
  ```

  The page's Motion tool plays it, and every GLB exported from the model carries it as a
  glTF animation of its name.

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
  exported, which records the compiled tracks. The page and a STEP show nothing of it. The viewer's Animation section plays a GLB's animations.

Remove helper joints that existed only to slide parts apart for an explode: that is an
animation now. A clip's `loop` has no counterpart (a player repeats a clip), nor do
`.opacity` and tube deformation; `.visible(false)` is `.hide`. Snapshots never play
motion: 0.7's `--animation`, `--time` and `--video` are gone.

### 6. Move materials into the body; make colours hex

`materials=` on the decorator is gone. A material is a value on the part, set in the
body after the part's last operation:

```python
# 0.7
@step(materials={"definitions": {"cast": {"name": "As-cast steel", "roughness": 0.85, "metalness": 0.2}},
                 "assignments": [{"targets": ["#housing"], "material": "cast"}]})

# 0.8, in the body
from cadgen import Material, materials, paint

housing.material = materials.steel.but(name="As-cast steel", roughness=0.85, metallic=0.2)
```

`materials` is a catalogue of 44 common engineering materials (`materials.aluminium_6061`,
`materials("6061-T6")`), and `Material(...)` makes a project's own. `metalness` is
`metallic`, `clearcoat` is `coat`. A material set on an assembly is the default of every
part below it that has none. `paint(part, faces, colour_or_material)` gives faces their
own.

**Colours are sRGB, as you pick them.** `shape.color`, `paint` and `Material(color=)`
take a hex string (`"#2E3742"`, `"#38414D6B"` with alpha as a byte) or 0-255 integers;
the engine stores them linear. Floats are refused by `paint` and `Material`.

| 0.7 | 0.8 |
| --- | --- |
| `srgb("#2E3742")` | `"#2E3742"` |
| `srgb("#38414D", 0.42)` | `"#38414D6B"` |
| `Material(color=(0.2, 0.3, 0.9))` (linear floats) | `Material(color="#7c95f3")`, the hex of what you see |
| `shape.color = bd.Color(0.5, 0.5, 0.5)` meant as linear | read as build123d defines it, sRGB: `#808080`. For the old look, give the hex of the linear value (`"#bcbcbc"` for 0.5) |

### 7. Learn the one engine: ids, pages and commands

0.7 had a build daemon, a separate viewer process with page sessions, and a store. 0.8
has one engine per installation: it runs the warm workers that build models, holds
their documents, and serves the CAD Viewer's one page. The first run, command or
`cadgen viewer` starts it.

- **Every document has an id**, a UUID: a model's comes from its script's path and its
  function's name, so it is the same every run (`bracket.id` in Python, and the handle's
  `.id`). `@model(key="bracket")` (or `key=` on a file decorator) gives it an id of the key's
  instead, the same wherever the script moves; two declarations claiming one key are
  refused. Its page is `/<uuid>` on the engine's address, and the run prints it as `view:`
  (the handle's `.url`). An open page follows every later run; share the link once.
- **The commands take an id or a file.** `cadgen export`, `cadgen snapshot` and
  `cadgen inspect` read the document as the engine holds it, and never run a script.
- **The engine never reruns code.** A document it no longer holds (the engine restarted,
  or it dropped the document to free memory) is answered, by its page, by
  `cadgen inspect <id>` and by the CAD app, with the command that brings it back:
  `python <the script>`. A viewer link from before an engine restart opens a page saying
  to open the viewer again.
- **Every document has a record** in cadgen's state folder, beside your settings
  (`documents/<uuid>/document.json`: the script and function that build it, never
  geometry), and the home's Recents lists them, most recent first. 0.7's Recents are not
  read: they start empty after the upgrade.
- **Documents reopen after a restart** from the engine's cache, as last built; the code
  stays the source, and a document whose code changed since says so.
- **A model lives in a `.py` file.** Its record points at the script (`pointer`).
  `@model(store="memory")` keeps a document in its worker's memory alone, unrecorded and
  out of Recents: for throwaway probes.
- **A notebook hands its shape over.** In a notebook cell or a REPL, build the shape and
  call `model(shape, name="bracket")`: the engine holds, caches and serves a document of
  it, exports it like any other, and returns the same handle (`.shape` is your shape).
  Joints, mechanism states and sequences on the shape go with it; a GLB's animations are
  passed as `animations=[...]`. Its id comes from the notebook's working folder and the
  name, or from `key=`. Nothing builds it again: run the cell again.
- **No page sessions.** `/s/<session>/...`, `?file=` and `?doc=` links open the home.
  The home shows Recents and the folder of the most recent `cadgen viewer` launch.
- **The CAD app** shows a model by its id or a file by its path (`cad_show`), and its
  card has an Open in browser button at the right of its navbar.

| 0.7 | 0.8 |
| --- | --- |
| `cadgen daemon status` | `cadgen status`: the engine's workers and the documents it holds |
| `cadgen daemon` | `cadgen server`: runs the engine in this process |
| (none) | `cadgen stop`: stops the engine, and any older one left running |
| `cadgen viewer --detach`, `--new`, `cadgen viewer stop`, `cadgen viewer list` | `cadgen viewer [FILE ...]`: ensures the engine, prints each page, exits |
| `<viewer url>?file=<path>` | `/<uuid>`, printed by the run or by `cadgen viewer FILE` |
| `cadgen step build IN OUT`, `cadgen stl\|3mf\|glb build` | `cadgen export SRC DST [DST ...]`, SRC an id, an `.xbf` or a `.step` |
| `cadgen step compile` | nothing: the viewer and snapshots read a STEP as it is |
| `cadgen step snapshot`, `cadgen stl\|3mf\|glb snapshot` | `cadgen snapshot SRC OUT.png`, for every kind |
| snapshot `--kinematics` | `--pose` |
| snapshot `--focus`, `--hide` | `--display '{"isolated": [...]}'`, `--display '{"hidden": [...]}'` |
| snapshot `--mode list` | the model's tree: `[part.label for part in assembly().shape.leaves]` |
| `cadgen store why\|where\|forget\|gc\|info` | nothing: no store. `cadgen inspect <id>` prints what a document was built from |

`--no-daemon` is gone from every command, and `cadgen build` and `cadgen.build()`, which
0.8 previews had, are gone too: the only way to build is a decorated function called
from Python, in a script. A shape made elsewhere -- a notebook cell, a REPL -- is handed
over with `model(shape, name=...)`.

### 8. Replace `read_scene` refs and checks

A 0.7 ref, `/work/STEP/assembly.step#o1.2.f7`, named an occurrence by its position and
a face by its number in one saved revision, and `read_scene(path).resolve(ref)` resolved
it. A 0.8 ref names the document (a model's id, or a file's path), the occurrence by the
labels on its way from the root, and the element by the code that made it:

```text
b48e875e-f53d-5535-ada3-a2a300690f6f#kit/hand/finger.2/f:finger.body.3;M:finger.relief
```

Element names come from the function and the variable that made each feature, so moving
code renames nothing and a dimension edit keeps every name. The viewer copies refs in
this form. Resolve one with `cadgen inspect`:

```bash
cadgen inspect <uuid> "hand/finger.2/face 7"
```

It answers what the ref names, with the kernel's facts and `made_by`, the function, file
and line of the code that made the element. Old refs resolve to nothing: select again in
the viewer.

A check calls the model and measures what it returns:

```python
# 0.7                                         # 0.8
from cadgen import read_scene                 from cadgen.geometry import closest_points
scene = read_scene("STEP/kit.step")
...                                           from kit import kit

                                              parts = {p.label: p for p in kit().shape.leaves}
                                              print(closest_points(parts["plate"], parts["post"]).distance)
```

`cadgen.geometry` (`closest_points`, `overlap_volume`, `mass_properties`, the topology
checks) is unchanged. In 0.8 previews, `select(...)` resolved refs in Python; it is gone
too, for `cadgen inspect` and build123d's selectors in the body, and
`snapshot_job(packet, source)` is `cadgen.snapshot(source, job=packet)`.

### 9. Delete 0.7 leftovers

- **Sidecars**: `<name>.step.json` and `.params.js` files beside your STEP files are read
  by nothing. Delete them once each model is ported.
- **Old exports**: STEP, STL, 3MF and GLB files 0.7 runs wrote stay where they were and
  nothing rewrites them. Export them again from the ported models, or delete them.
- **The 0.7 store.** cadgen 0.7 kept a cache store that can hold gigabytes. 0.8 keeps its
  own document cache in the same folder, under `documents/` alone, and neither reads,
  writes nor removes 0.7's store beside it. Once no 0.7 install is left on the machine
  (no 0.7 plugin in any agent app), delete the folder by hand (0.8 loses nothing: the
  next run of each script builds its document again):

  | Platform | Folder |
  | --- | --- |
  | macOS, Linux | `~/.cache/cadgen`, or `$XDG_CACHE_HOME/cadgen` when `XDG_CACHE_HOME` is set |
  | Windows | `%LOCALAPPDATA%\cadgen` |
  | anywhere | the folder `CADGEN_CACHE_DIR` named, if you set it for 0.7 |

  Your settings, telemetry answer, recent files and documents' records live elsewhere, in
  cadgen's state folder, and deleting the store does not touch them.

- **Quick Edit's preference**: Quick Edit is always available; a `features.quickEdit:
  false` left in settings does nothing.

### 10. Verify

1. Run each root script: `python src/assembly.py` exits 0 and prints an id and a page
   for every model it calls. A second run replays (`bodies ... replayed`).
2. Open each page and compare it with the 0.7 model: parts, colours, materials and the
   tree. For a mechanism, try Position's sliders and presets, and play each motion.
3. Run your checks: they call the models now.
4. Export what you deliver and compare it with the 0.7 files you kept, by snapshot
   (`cadgen snapshot STEP/old.step a.png` beside `cadgen snapshot <uuid> b.png`) or by
   measurement.

## Telemetry

Unchanged. Your answer carries over in the same settings, `cadgen telemetry
status|on|off` works as before, and `DO_NOT_TRACK=1` or `CADGEN_TELEMETRY=0` turns it
off for a process. The CAD app's `cad_telemetry` tool is gone: an agent reads the status
through `cad_http` (`GET /__cad/analytics`) and can opt you out when you ask; only you can
opt in.

## What lands where

| Thing | 0.7 | 0.8 |
| --- | --- | --- |
| A model | `@step(out=...)` (or a mesh decorator) on a parameterless function | `@model` on a parameterless function; parameters on plain helpers |
| A run | writes every declared file | writes nothing; updates the document and its pages |
| A file | written by every run, or by `cadgen <format> build` | written on request by `cadgen export`, or by `exports.py` |
| The model's document | a STEP plus a `<name>.step.json` sidecar | held by the engine at `/<uuid>`; an `.xbf` when saved as one |
| Kinematics | `kinematics=` mates, couplings, poses, in the sidecar | build123d joints and `cadgen.ap242`, in the document |
| Animation | a JavaScript clip module in the sidecar | `configuration_sequence` (the document) or `animation()` (a GLB) |
| Materials | `materials=` definitions and assignments | `part.material = ...` in the body |
| Colours | linear floats, `srgb(...)` | sRGB hex or 0-255 integers |
| Refs | `#o1.2.f7` | `<id>#path/to/part/f:function.feature.n` |
| The cache | the store in `~/.cache/cadgen` | the warm worker's memory; nothing on disk |
| The viewer | its own process, `?file=` links, page sessions | the engine's one page, `/<uuid>` |

## Troubleshooting a half-migrated project

- **A run prints nothing and exits 0.** The script's `__main__` calls no model, or the
  model is still undecorated. Decoration only declares; add the calls.
- **`TypeError` naming `kinematics`, `materials` or `animation`.** A decorator still
  carries a 0.7 argument. Move it into the body (steps 4 to 6).
- **`ImportError: cannot import name 'build123d' from 'cadgen'`.** Step 1:
  `import build123d as bd`.
- **`AttributeError` for `revolute`, `couple`, `srgb`, `report` or `track`.** Step 1's
  table.
- **Colours look washed out or too dark.** A colour meant as linear floats is now read
  as sRGB: give the hex of what you see (step 6).
- **A link opens the home instead of the model.** It is a 0.7 or pre-release link
  (`?file=`, `/s/...`). Run the model and use the page it prints.
- **A page or `cadgen inspect` says the document is not held.** The engine restarted or
  freed it. Run the command it prints.
- **The viewer shows an old mechanism or none.** A sidecar is read by nothing: the
  mechanism must be in the model's body (step 4).

## Migration complete when

- [ ] Every model is `@model` on a parameterless function, its values on plain helpers,
      and each variant a named model.
- [ ] `import build123d as bd` everywhere; no `from cadgen import build123d`.
- [ ] No `kinematics=`, `materials=` or `animation=` anywhere; mechanisms use build123d
      joints and `cadgen.ap242`, showcases `cadgen.gltf`.
- [ ] Every colour is hex or 0-255 integers.
- [ ] Deliverables come from `cadgen export` or an `exports.py`.
- [ ] No `.step.json` or `.params.js` file remains.
- [ ] Every root script runs clean and prints a page for each model; each page has been
      opened and reviewed.
- [ ] The 0.7 store is deleted, once no 0.7 install remains.

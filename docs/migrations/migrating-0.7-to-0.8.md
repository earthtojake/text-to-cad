# Migrating a CAD project from cadgen 0.7 to 0.8

This is a hand-migration playbook. Work through it top to bottom with a 0.7 project open
and you will end with a working 0.8 project. An agent with the CAD skill installed is
pointed here by the skill's short `references/migrations.md` and can do most of this for
you: ask it to follow this guide. A project still on 0.4 first follows
[Migrating 0.4 to 0.5](migrating-0.4-to-0.5.md), which ends here. This guide targets
cadgen 0.8.1 with build123d 0.13.

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

- **Its scripts run on 0.8** (the CAD plugin's `cadgen` command, or a pin moved to 0.8):
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
  when those commands do (Prerequisites, step 2).

### The one-paragraph summary

0.8 replaces 0.7's file pipeline with one engine. A model is still a parameterless
Python function, but it is decorated `@model` and a run writes nothing: `cadgen run
model.py` (or `python model.py` in an environment with cadgen) rebuilds the model in a warm
engine, prints its document's id and a link to its page, and every page open on it updates.
Think of the page as the open document, the script as its feature tree, and running the
script as the rebuild. Export is the download button at the navbar's right: pick a format,
the engine prepares the file, the browser saves it; `cadgen export <id> part.step` writes
one from the command line, and an `exports.py` writes a project's deliverables. Mates,
couplings, poses and JavaScript clips become build123d joints and STEP AP242's mechanism
vocabulary in the model's body (`cadgen.ap242`), and showcase animations become a GLB's own
channels (`cadgen.gltf`). Colours are sRGB hex. `import build123d as bd` is free until it
is used. The 0.7 store, sidecars, STEP-format commands, staleness checks and `?file=` links
are gone.

## Prerequisites

1. **Update the plugin, or the pin.** The plugin starts its server through
   `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.1 cadgen mcp`,
   which installs and registers cadgen. Skills then run commands as `cadgen +0.8.1 ...`
   and model scripts as `cadgen +0.8.1 run SCRIPT.py`, through that installation's
   launcher. A project that pins cadgen itself moves its pin to `cadgen==0.8.1`.
   The Python floor is unchanged (3.11). cadgen no longer depends on Playwright:
   snapshots are drawn by OCCT, so no headless browser is downloaded.

2. **Run cadgen through the `cadgen` command.** 0.8 installs one, `~/.local/bin/cadgen`,
   written by `cadgen doctor` and by the CAD app's server. It runs a registered
   installation, picked by the first of: a version named (`cadgen +0.8.1 ...`), the
   `CADGEN_VERSION` variable, the engine the shell's agent app holds, a running engine, and the
   newest installation registered. `cadgen run SCRIPT.py` runs a model script with that
   installation's Python, so the scripts, the commands and the CAD app share one engine:

   | 0.7 (in a project's README or `AGENTS.md`) | 0.8 |
   | --- | --- |
   | `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.21 python src/model.py` | `cadgen run src/model.py` |
   | `uvx ... --from cadgen==0.7.21 cadgen <verb>` | `cadgen <verb>` |
   | `uvx ... python -m unittest ...` | `cadgen run -m unittest ...` |
   | a version kept in step with the plugin by hand | nothing (the plugin's), or `cadgen +0.8.1 ...` for an explicit version |

   If `cadgen` is not on your PATH, or says 0.8.1 is not installed, run
   `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.1 cadgen doctor` once.

   A project's old venv may shadow the launcher with its own `cadgen`, even when
   `~/.local/bin` is on PATH. Run `~/.local/bin/cadgen +0.8.1 doctor` to see which
   executable wins, and use the full launcher path until PATH is corrected.

3. **Set `PYTHONPATH` where the project's import root needs it**, as for `python SCRIPT`:
   `PYTHONPATH=src cadgen run src/camera/payload.py`.

4. **Confirm what you have.**

   ```bash
   cadgen --version          # cadgen 0.8.1
   cadgen doctor             # the installation in use, the CAD kernel, the engine
   ```

5. **Stop 0.7's viewer.** A 0.7 viewer still running is 0.7's own process, on its own
   port: stop it with 0.7's `cadgen viewer stop`, or let it be. 0.8 starts its own
   engine on first use.

6. **Commit your work.** This migration deletes files.

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

A run takes no options. 0.7's `--force`, `--json`, `--verbose`, `--profile`,
`--mesh-tolerance` and `--no-daemon` are unrecognized arguments; there is nothing to
pass:

| 0.7 | 0.8 |
| --- | --- |
| `python model.py` | `cadgen run model.py`, or `python model.py` in an environment with cadgen 0.8 |
| `python model.py --force` | `CADGEN_ENGINE_MEMO=0 cadgen run model.py` (no memo hits) |
| `python model.py --json` | `bracket.build()` from Python returns the report as data (`.models[0]`) |
| `python model.py --profile` | `bracket.build(profile=True)` |
| `python model.py --no-daemon`, `CADGEN_DAEMON=0` | nothing: every run goes through the engine. `Model.build(daemon=False)` remains as a seam for tests and debugging (cold, in your process, nothing served) |
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
cadgen run src/bracket.py                               # prints id: <uuid> and view: <url>
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

# 0.8.1, in the body
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

| 0.7 | 0.8.1 |
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

### 7. Learn the one engine: ids, pages, links and commands

0.7 had a build daemon, a separate viewer process with page sessions, and a store. 0.8
has one engine per installation: it runs the warm workers that build models, holds
their documents, and serves the CAD Viewer's one page. The first run, command or
`cadgen viewer` starts it, and no timer stops it.

**Documents and their ids.**

- **Every document has an id**, a UUID: a model's comes from its script's path and its
  function's name, so it is the same every run (`bracket.id` in Python, and the handle's
  `.id`). A model's identity is its namespace, the folder of its script, and its name, the
  function's by default. `@model(name="bracket")` (or `name=` on a file decorator) gives it
  an id of that folder and that name instead, the same whichever file of the folder declares
  it. The same name in two folders is two models; in one folder a second declaration is
  refused, naming both `file:line`, until the file that held the name is gone or has run
  again without it (`cadgen run <that file>`). A script moved or renamed without an edit
  keeps its document: its next run re-attaches the old record (history, pins, picture and
  saved build) to the new place. A function renamed keeps its document when it has a
  `name=`, and is a new document when it has none. A file the viewer opens has an id of its
  path. A document's page is `/<uuid>` on the engine's address, and a run prints it as
  `view:` (the handle's `.url`).
- **The commands take an id or a file.** `cadgen export`, `cadgen snapshot` and
  `cadgen inspect` read the document as the engine holds it, and never run a script: a
  script (`x.py`, `x.py::fn`) is refused as a source.
- **A document is what its last run made.** The engine does not watch your script, never
  compares it with the document, and never says a document is stale: there is no staleness
  badge, notice or check (0.7's `cadgen store why` has no successor). When the code changed,
  run it again; a run that finds nothing changed is `took ... nothing ran`.
- **The engine never reruns code.** A document it holds no file of any more (its file in the
  engine's cache deleted by hand, or never saved) is answered, by its page, by
  `cadgen inspect <id>` and by the CAD app, with the command that brings it back:
  `cadgen run <the script>`. A restart or the engine's memory budget never does this: the
  cache keeps every document.

**The store, the records and the cache.** 0.7's store (content-addressed objects and an
index) is gone, and no decorator takes a store (`@model(store=...)`, which 0.8 previews had,
is an unexpected keyword argument).

- **Every document has a record** in cadgen's state folder, beside your settings
  (`documents/<uuid>/document.json`: the script and function that build it, or the file's
  path; never geometry). The home lists them.
- **Every model's document is cached** as last built (`documents/<uuid>/document.xbf` in the
  cache folder, `~/.cache/cadgen` by 0.7's rule), so documents reopen after a restart, as last
  built, with nothing run. The cache has no size cap and nothing evicts from it; a file opened
  in the viewer is never cached (the file is its copy).
- **`cadgen delete <id>`** (or a model's script, for every document recorded of it, or a
  file's path), or Delete in a card's menu on the home, deletes a document: its record and its
  cached document. Your script and its files stay.
- **A model lives in a `.py` file.** Its record points at the script.
- **A notebook hands its shape over.** In a notebook cell or a REPL, build the shape and
  call `model(shape, name="bracket")`: the engine holds, caches and serves a document of
  it, exports it like any other, and returns the same handle (`.shape` is your shape).
  Joints, mechanism states and sequences on the shape go with it; a GLB's animations are
  passed as `animations=[...]`. Its id comes from the notebook's working folder and the
  name. Nothing builds it again: run the cell again.

**Port 3245 and the day link.**

- **One port, kept.** The engine serves on 3245 (or the port `CADGEN_ENGINE_PORT` or
  `--port` names). When another program holds 3245, the engine takes the next free port,
  says so once (`3245 is held by <name> (pid N); this installation serves on 3246 and keeps
  it`) and keeps that port, so links stay stable; once 3245 is free at a start it moves back
  (`back on the default port 3245: links made on 3246 no longer work`). Another 0.8 release's
  engine that nothing uses is stopped for 3245; one still in use is rolled past. A 0.7 CAD
  Viewer still on 3245 is named in that line too: 0.7's `cadgen viewer stop` frees it. A port
  you name is never moved: held, the engine refuses to start and names the holder.
- **A printed link is good for a day.** Every page URL the engine prints or opens -- a run's
  `view:` line, `cadgen viewer`'s output, the CAD app's Open in browser -- carries
  `?token=<expiry>.<signature>`, valid for 24 hours. A browser that opens it is signed in
  with a cookie good for 30 days from its last use, on any port, across `cadgen stop`, a crash
  and a reboot; an open page that lost its engine reconnects on its own when the engine comes
  back. A link past its day, in a browser that is not signed in, shows "This CAD Viewer page
  needs its link": run the model again, or `cadgen viewer <id>`, and open the fresh link.
  `cadgen server --rotate-token`, run with the engine stopped, retires every link and session
  handed out before it.
- **No page sessions.** `/s/<session>/...`, `?file=` and `?doc=` links open the home.

**The commands.**

| 0.7 | 0.8 |
| --- | --- |
| `python model.py` | `cadgen run model.py`: builds the models its `__main__` calls |
| `cadgen daemon status` | `cadgen status`: the engine's workers, the documents it holds, its port and its cache |
| `cadgen daemon` | `cadgen server`: runs the engine in this process |
| (none) | `cadgen stop`: stops the engine, and any older one left running |
| `cadgen viewer --detach`, `--new`, `cadgen viewer stop`, `cadgen viewer list` | `cadgen viewer [FILE or ID ...]`: ensures the engine, registers each file, prints each page (`--json`: one line with each document's `url`), exits |
| `<viewer url>?file=<path>` | `/<uuid>`, printed by the run or by `cadgen viewer FILE` |
| `cadgen step build IN OUT`, `cadgen stl\|3mf\|glb build` | `cadgen export SRC DST [DST ...]`, SRC an id, an `.xbf`, a `.step`, or a mesh (to the other mesh kinds) |
| `cadgen step compile` | nothing: the viewer and snapshots read a STEP as it is |
| `cadgen step snapshot`, `cadgen stl\|3mf\|glb snapshot` | `cadgen snapshot SRC OUT.png`, for every kind |
| snapshot `--kinematics` | `--pose` |
| snapshot `--focus`, `--hide` | `--display '{"isolated": [...]}'`, `--display '{"hidden": [...]}'` |
| snapshot `--mode list` | the model's tree: `[part.label for part in assembly().shape.leaves]` |
| `cadgen store why\|where\|forget\|gc\|info` | no store to manage: `cadgen inspect <id>` prints what a document holds and what it was built from, `cadgen delete <id>` deletes it, and a run says whether anything changed |
| `cadgen telemetry status\|on\|off` | the same |
| (none) | `cadgen doctor [--prune]`: sets cadgen up, reports it, and clears what nothing needs (0.7's store among it) |

`--no-daemon` is gone from every command, and `cadgen build` and `cadgen.build()`, which
0.8 previews had, are gone too: the only way to build is a decorated function called
from Python, in a script. A shape made elsewhere -- a notebook cell, a REPL -- is handed
over with `model(shape, name=...)`.

**The home and the page.**

- **The home is the library alone.** `/` lists, under Recent, every model built and every
  file opened, as tiles or a table, pinned first, then by last activity, with a type filter
  (All, Models, Files), a search, and Open (the desktop's file chooser). A tile says its last
  activity with a verb: "Edited 2m ago" when the document changed after a page last opened
  it, "Viewed 16m ago" when a page opened it after the change. The table's columns are Name,
  Updated (when it last changed) and Created (when its record was first made: a model's first
  run, a file's first open). No model is shown with the script that built it. A card's menu
  holds Open, a file's Copy path and Reveal, Pin, and Delete, which asks first. 0.7's Recents
  are not read, and a launch's folder is no longer listed: the home starts empty after the
  upgrade and fills as you run models and open files. A model page's Files menu lists the
  folder the explorer was last in, else your home folder, never the script's.
- **Exports are downloads.** The viewer's Export (the download button at the navbar's
  right) is a browser download: pick a format, a "Preparing..." toast shows while the engine
  writes the file, and the browser saves it where it saves downloads. There is no export
  dialog, destination or jobs panel. An exported file, from the viewer, `cadgen export` or a
  file decorator, is a detached copy: its page follows the file on disk, never the model,
  and nothing reruns it.

**The CAD app (MCP)** shows a model by its id or a file by its path (`cad_show`; every CAD
tool names the model in `source`, where `cad_show` and `cad_open` took `path` in 0.7). How it
looks depends on the host:

- **Claude Desktop and other MCP Apps hosts** draw a card per `cad_show`: the whole viewer at
  card size under its navbar (the logo and app menu, Back and Forward, the name menu, then
  Full size where the host offers it and Open in browser last; no Export, as the host has no
  downloads). A newer card retires the older ones.
- **The Codex app** shows CAD in its sidebar (the home) and in a CAD tab beside each thread,
  both under the same navbar, and *Open with CAD* for a model file, which shows that file
  alone, with no navbar.
- **Text hosts** (Claude Code in a terminal, `codex exec`) draw nothing: `cad_show` opens the
  model's page in your browser, from the agent's own environment, and answers with its link
  (or says it is already open there, or that no browser can be opened from there).

An agent writes files with `cad_export`, draws with `cad_snapshot` and asks with
`cad_inspect`, on every host.

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
or a part's name. The CAD app's `cad_telemetry` tool is gone: an agent reads the status
through `cad_http` (`GET /__cad/analytics`) and can opt you out when you ask (`POST` with
the body `{"share":false}`); only you can opt in.

## What lands where

| Thing | 0.7 | 0.8 |
| --- | --- | --- |
| A model | `@step(out=...)` (or a mesh decorator) on a parameterless function | `@model` on a parameterless function; parameters on plain helpers |
| A cached stage | a child model writing its own STEP | `@memo` on the stage function, no file |
| A run | `uvx ... cadgen==0.7.x python model.py`, writing every declared file | `cadgen run model.py`, writing nothing; it updates the document and its pages |
| A file | written by every run, or by `cadgen <format> build` | written on request by `cadgen export`, or by `exports.py` |
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
  (`uvx ... cadgen==0.7.x`): Prerequisites, step 2.
- **`ModuleNotFoundError` for one of the project's own packages.** `PYTHONPATH` does not
  name the import root (Prerequisites, step 3).
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

**Saved XBF documents remain usable.** cadgen 0.8.1 writes `xbf/9` and reads both
`xbf/8` and `xbf/9`. Opening an `xbf/8` file or cached snapshot automatically converts its
material metadata in memory, so viewing, inspection, snapshots, imports and exports need
no model source or execution. Source and cache bytes, the cache record and revision, and
the original build closure and toolchain provenance remain unchanged. A separate migration
record describes the conversion. Reading an upgraded document again is idempotent.

To save the upgraded document, choose a different XBF path:

```bash
cadgen export saved-v8.xbf upgraded-v9.xbf
```

The complete upgraded XCAF document is saved atomically; exporting over the source path is
refused. Exporting a cached document by id to XBF also saves its upgraded form. The viewer's
original-file XBF download still returns the original bytes; use the command above to save
an upgrade. Ordinary current-format XBF-to-XBF translation remains refused. Unsupported
formats or failed conversions preserve the original bytes and cache record and report a
clear error.

When you explicitly run a model's source, its original build key is compared with the
current one and the model builds normally when they differ. Saved-document access does
not imply build-cache reuse. See the
[persisted-document policy](../../packages/cadgen/README.md#the-design-laws).

The independent startup identity pass still gives each JSON record its namespace and
name, and a model's record the fingerprint of its script. A record that a `key=` named
moves, with its saved document, to the id its folder and name give. This changes identity,
not the saved document's format. A record that cannot be read or moved stays as it is,
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
- [ ] The project's own docs run `cadgen run` and `cadgen`, with `PYTHONPATH` where it needs one.
- [ ] No `kinematics=`, `materials=` or `animation=` anywhere; mechanisms use build123d
      joints and `cadgen.ap242`, showcases `cadgen.gltf`.
- [ ] Every colour is hex or 0-255 integers.
- [ ] Deliverables come from `cadgen export` or an `exports.py`.
- [ ] No `.step.json` or `.params.js` file remains, and no tool reads one.
- [ ] Every root script runs clean and prints a page for each model; each page has been
      opened and reviewed.
- [ ] `cadgen doctor` names no 0.7 store, or says when `--prune` removes it.

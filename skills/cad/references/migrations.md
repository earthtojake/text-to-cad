# Migrations

Read this file when code or commands written for an older cadgen fail.
`cadgen doctor <skill-dir>` compares the installed version with the skill's pin.

cadgen cuts interfaces over with no compatibility layer: a retired command, flag,
argument, key or import is gone, and fails the way an unknown one does (an unknown
command, an unrecognized argument, an unknown key, an `ImportError`, an
`AttributeError`) without naming what replaced it. The tables below map old forms to
current ones; read the error as what the current contract wants.

## Contents

- [Signs of an older project](#signs-of-an-older-project)
- [0.7 to 0.8: models](#07-to-08-models)
- [0.7 to 0.8: commands](#07-to-08-commands)
- [0.7 to 0.8: Python names](#07-to-08-python-names)
- [0.7 to 0.8: mates become build123d joints](#07-to-08-mates-become-build123d-joints)
- [0.7 to 0.8: clips become sequences and animations](#07-to-08-clips-become-sequences-and-animations)
- [0.7 to 0.8: materials and colours](#07-to-08-materials-and-colours)
- [0.7 to 0.8: refs](#07-to-08-refs)
- [0.7 to 0.8: files left on disk](#07-to-08-files-left-on-disk)
- [0.8 previews to 0.8](#08-previews-to-08)

## Signs of an older project

- `from cadgen import build123d as bd`, `@step(out=..., kinematics=...)`,
  `cadgen.revolute(...)`, an `animation=` string of JavaScript, `read_scene`: 0.7.
- `<name>.step.json` sidecars or `.params.js` files beside STEP files: 0.7.
- `from cadgen.engine import ...`, `configuration(...)`, `motion(...)`, `couple(...)`,
  `select(...)`, `report(...)`, `track(...)`, `srgb(...)`, `cadgen build`: an 0.8 preview.

A file decorator (`@xbf`, `@step`, `@glb`, `@stl`, `@threemf`, `@dxf`) with `out` alone
still writes its file on every run. When editing such a model, port it to `@model`;
if the person wants those files kept current, list them in an `exports.py`
([exports](exports.md)).

## 0.7 to 0.8: models

```python
# 0.7
from cadgen import build123d as bd
from cadgen import step


@step(out="../STEP/bracket.step")
def bracket():
    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    bracket()
```

```python
# 0.8
import build123d as bd
from cadgen import model


@model
def bracket():
    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    bracket()
```

```bash
python src/bracket.py                     # prints id: and view:
cadgen export "$ID" STEP/bracket.step     # the file, when asked
```

| 0.7 | 0.8 |
| --- | --- |
| `@step(out=...)`, `@stl`, `@glb`, `@threemf` on a model | `@model`; files by `cadgen export <id> FILE` when asked, or an `exports.py` calling `export(x, path)` |
| `@dxf(out=...)` on a drawing | `@model` returning the planar geometry; `cadgen export <id> drawing.dxf` writes it, running the drawing checks (`$dxf`) |
| `@step(out=..., kinematics=..., materials=..., animation=...)` | `@model`; joints, materials and motions in the body (below) |
| `@stl(mesh_tolerance=..., mesh_angular_tolerance=...)`, `--mesh-tolerance` | none: every mesh is made at FreeCAD's default tolerance |
| `python model.py --force`, `--json`, `--verbose` | `python model.py` takes no options. `CADGEN_ENGINE_MEMO=0` runs without memo hits; `bracket.build()` returns the report as data; `bracket.build(verify=True)` checks every replay |
| `python model.py --profile` | `bracket.build(profile=True)` |
| `python model.py --no-daemon`, `CADGEN_DAEMON=0` | none: every run goes through the engine (`Model.build(daemon=False)` is a seam for tests: cold, nothing served) |
| a model's dimensions as module constants and one model | a helper function taking the values; each variant its own `@model` calling it |
| a run that writes `STEP/x.step` beside the script | a run that writes nothing: the page updates |
| `compound_from_instances(...)` | `bd.Pos(...) * part`: every placement shares its shape |
| `label_shape(shape, name, ...)`, `label_text(...)` | `shape.label = "name"` |
| `AssemblyHelper`, `MateTarget`, `target(...)` | build123d joints and `Compound(children=...)` |
| `read_step(path)` | `read_step(path)`, the same; `read_xbf(path)` for an xbf, `read_mesh(path)` for an STL |
| `bd.import_step(...)` in a body | `read_step(...)`: an engine read, tracked by its bytes |

## 0.7 to 0.8: commands

| 0.7 | 0.8 |
| --- | --- |
| `cadgen step build IN.step OUT.step` | `cadgen export IN.step OUT.step`, or `OUT.xbf` to read it in models |
| `cadgen step build ... --kinematics/--materials/--animation` | a model that reads the STEP (`read_step`) and writes them in its body |
| `cadgen step compile` | none: the viewer and snapshots read a STEP as it is |
| `cadgen stl build`, `cadgen 3mf build`, `cadgen glb build` | `cadgen export <id or DOC> OUT.stl` (`.3mf`, `.glb`) |
| `cadgen glb build --animation CLIP` | every GLB exported from a model carries every motion and animation of it |
| `cadgen step snapshot`, `cadgen stl snapshot`, `cadgen 3mf snapshot`, `cadgen glb snapshot` | `cadgen snapshot SRC OUT.png`, one command for every kind; SRC a model's id or a file |
| snapshot `--kinematics` | `--pose` |
| snapshot `--animation`, `--time`, `--video` | none: export a GLB and play it in the viewer |
| snapshot `--mode list` | none: list parts from the model's tree (`[p.label for p in kit().shape.leaves]`) |
| snapshot `--focus`, `--hide` | `--display '{"isolated": ["lid"]}'`, `--display '{"hidden": ["lid"]}'` (part refs) |
| a `--job` file's `kinematics`, a STEP job's `selection`, `animation`, `video`, `quality`, `mode`, `output.viewLabels` | a job's pose is `jointValues`; hidden and isolated parts are its `display.hidden` and `display.isolated` |
| `cadgen store why`, `store where`, `store forget`, `store gc`, `store info` | none: no store. `cadgen inspect <id>` prints what a document was built from, `cadgen inspect <id> REF` what made an element |
| `cadgen daemon status` | `cadgen status` |
| `cadgen daemon` | `cadgen server` (runs the engine in this process; rarely needed) |
| `cadgen viewer --detach`, `--new`, `cadgen viewer stop`, `cadgen viewer list` | `cadgen viewer [FILE ...]`: ensures the one engine, prints each page, exits; `cadgen stop` stops the engine |
| a viewer link `url?file=<path>` | the page `/<id>` the run (or `cadgen viewer FILE`) prints |

## 0.7 to 0.8: Python names

| 0.7 | 0.8 |
| --- | --- |
| `from cadgen import build123d as bd`, `cadgen.build123d` | `import build123d as bd`: lazy, the kernel loading on first attribute; `from build123d import X` loads it at that line |
| `read_scene(path).resolve(ref).shape()`, `StepScene`, `Occurrence`, `Selection` | `cadgen inspect DOC REF` for what a ref names; the model's tree (or `read_xbf`/`read_step`'s), walked by labels, for its shapes; build123d selectors in a body |
| `cadgen.revolute`, `slider`, `cylindrical`, `fastened` | build123d joints in the body ([below](#07-to-08-mates-become-build123d-joints)) |
| `cadgen.couple(name, {dof: ratio}, limits=...)` | `cadgen.ap242`'s `gear_pair`, `rack_and_pinion_pair` or `screw_pair` |
| `report(...)`, `track(...)` | none: delete the calls. The progress bar and the page name each `@memo` call and child model a body runs |
| `srgb("#2E3742")`, `srgb_to_linear`, `linear_to_srgb` | the hex itself: `"#2E3742"` |
| `ensure_step_topology_artifact` | none |

## 0.7 to 0.8: mates become build123d joints

```python
# 0.7
KINEMATICS = {
    "mates": [cadgen.revolute("elbow", parent="#upper_arm", child="#forearm",
                              origin=(80, 0, 0), direction=(0, 0, 1), limits=(0, 150))],
    "couplings": [cadgen.couple("curl", {"elbow": 1}, limits=(0, 90))],
    "poses": {"bent": {"elbow": 60}},
}

@step(out="../STEP/arm.step", kinematics=KINEMATICS)
def arm():
    ...
    return bd.Compound(children=[upper_arm, forearm], label="arm")
```

```python
# 0.8
from cadgen.ap242 import mechanism_state

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
```

- `revolute` is a `RevoluteJoint` on the parent's part with its rigid partner on the
  child's, `slider` a `LinearJoint` (`linear_range`), `cylindrical` a `CylindricalJoint`
  (`(angle, distance)` where `.turn` and `.travel` were two DOFs), and `fastened` two
  connected `RigidJoint`s. Targets were labels (`"#forearm"`); a joint is attached to
  the part itself.
- A rest value of 0 was the artifact as written; now the as-built state is the value
  each joint is connected at, so connecting at 0, with both frames on the axis, keeps the
  parts where they were built.
- `poses` become `mechanism_state(assembly, name, **values)`, drawn with a snapshot's
  `--pose`; a posed file is a model returning `posed(assembly, name)`
  ([kinematics](kinematics.md)).
- A coupling is a constraint among two or more joints, its range their limits (`limits=`
  is gone: give the joints the limits instead), made by the function named after the
  pair its joints make: `gear_pair` (revolute joints), `rack_and_pinion_pair` (a revolute
  joint and prismatic ones) or `screw_pair` (one cylindrical joint's pitch). A coupling
  of one joint is that joint, so `curl` above is dropped and `elbow` poses alone.
- A mate's `axis` given as a ref becomes an `Axis` computed in the body from the live
  shape (`part.faces().sort_by(...)`, the element `cadgen inspect` names).

## 0.7 to 0.8: clips become sequences and animations

A 0.7 clip was a JavaScript module string (`export const clips = {demo: {update(t, m)
{...}}}`) moving occurrences through `m.get("forearm").rotate(...)`. It becomes one of
two things:

- **The mechanism's own motion** (a gait, a door, a running engine) is a
  configuration sequence over its joints: model what moves with joints first, then
  `configuration_sequence(assembly, "demo", sweep={"platter": (0, 360)}, duration=4,
  ease="linear")`, or waypoints, or a function of time over joint values
  ([configuration sequences](kinematics.md#configuration-sequences)).
- **A showcase** (an explode, a reveal, a part spinning for show, a part hidden) is a
  GLB's animation: `animation(assembly, "explode", duration=4)` and its channels
  ([animation](animation.md)). `.opacity` has no form; `.visible(false)` is `.hide`.

Neither has `loop`: a player repeats a clip. Tube deformation has no form.

## 0.7 to 0.8: materials and colours

```python
# 0.7
@step(materials={"definitions": {"cast": {"name": "As-cast steel", "roughness": 0.85, "metalness": 0.2}},
                 "assignments": [{"targets": ["#housing"], "material": "cast"}]})

# 0.8, in the body
housing.material = materials.steel.but(name="As-cast steel", roughness=0.85, metallic=0.2)
```

A definition becomes a `Material` (or a catalogue entry,
[materials](build123d-modeling.md#colour-and-materials)): `metalness` is `metallic`,
`baseColor` the `color` as its hex (`"#RRGGBB"`, sRGB), `clearcoat` and
`clearcoatRoughness` are `coat` and `coat_roughness`, and `opacity` is the colour's
alpha. An assignment to a group is the material set on that assembly, the default of
every part below it that has none.

| 0.7 | 0.8 |
| --- | --- |
| `srgb("#38414D", 0.42)` | `"#38414D6B"` (alpha as a byte), or 0-255 integers |
| `Material(color=(0.2, 0.3, 0.9))`, `transmission_color=`, `emissive=`: linear floats | a hex string or 0-255 integers, sRGB; floats are refused |
| `paint(shape, faces, (1, 0, 0))`, `paint(..., "orange")` | `paint(shape, faces, "#ff0000")`: a hex string, 0-255 integers, a build123d `Color` or a `Material` |
| `shape.color = bd.Color(r, g, b)` meant as linear | read as build123d defines it, sRGB (`bd.Color(0.5, 0.5, 0.5)` is `#808080`); for the old look give the hex of the linear values (`"#bcbcbc"` for 0.5) |

## 0.7 to 0.8: refs

A 0.7 ref was `/work/STEP/assembly.step#o1.2.f7`: an occurrence by its position and a
face by its number in that saved revision. It is now
`<id>#robot/bracket/f:bracket.body.6`: the document (a model's id, or a file's path),
an occurrence by the labels on its way from the root, and an element by the function and
the variable that made it ([references](inspection-and-validation.md#references)). The
old spellings resolve to nothing: take refs again from the viewer, or from what
`cadgen inspect` answers.

## 0.7 to 0.8: files left on disk

- `<name>.step.json` sidecars and `.params.js` files are read by nothing: the document
  carries the mechanism. Delete them once the model is ported.
- STEP, STL, 3MF and GLB files 0.7 runs wrote stay where they were; nothing rewrites
  them. Export them again from the ported model when the person wants them current.
- cadgen 0.7 kept a cache store, which can hold gigabytes; 0.8 keeps its own document
  cache in the same folder, under `documents/` alone, and neither reads, writes nor
  removes 0.7's store beside it. Once no 0.7 install is left on the machine (no 0.7 plugin in
  any agent app), the person may delete it, or ask you to: `~/.cache/cadgen`
  (`$XDG_CACHE_HOME/cadgen` when that is set) on macOS and Linux, `%LOCALAPPDATA%\cadgen`
  on Windows, or the folder `CADGEN_CACHE_DIR` named. Settings, the telemetry answer and
  recent files live elsewhere and are untouched.
- The CAD Viewer's Recents are the records of 0.8's documents; 0.7's list is not read,
  so they start empty after the upgrade.
- The CAD app: Quick Edit has no enable/disable preference (a stale
  `features.quickEdit: false` does nothing). The `cad_telemetry` tool is gone: telemetry
  status is `cad_http` with method `GET` and URL `/__cad/analytics`, and opt-out, when the
  person asks, method `POST` with base64 body `eyJzaGFyZSI6ZmFsc2V9` (`{"share":false}`).
  Agents cannot opt in. Reopen a restored page after updating.

## 0.8 previews to 0.8

Code written against an 0.8 preview may use names the release renamed or removed:

| Before | Now |
| --- | --- |
| `from cadgen.engine import model, memo, ...` | `from cadgen import model, memo, ...` (the root holds exactly `model`, `xbf`, `step`, `glb`, `stl`, `threemf`, `dxf`, `memo`, `Material`, `materials`, `paint`, `read_step`, `read_xbf`, `read_mesh`, `export`, `snapshot`, `inspect`, `__version__`) |
| `configuration(assembly, name, **values)` | `cadgen.ap242.mechanism_state(assembly, name, **values)` |
| `motion(assembly, name, ...)` | `cadgen.ap242.configuration_sequence(assembly, name, ...)`, the same arguments |
| `couple(...)` of revolute joints | `gear_pair(assembly, name, **joints)` |
| `couple(...)` of a revolute joint and prismatic ones | `rack_and_pinion_pair(assembly, name, **joints)` |
| `couple(assembly, name, joint=(turn, travel))` of one cylindrical joint | `screw_pair(assembly, name, joint=360 * travel / turn)`: its pitch; the value is now the turn in degrees |
| `from cadgen import mechanism_state, configuration_sequence, gear_pair, ...` | `from cadgen.ap242 import ...` |
| `from cadgen import animation` | `from cadgen.gltf import animation` |
| `cadgen build SOURCE`, `cadgen.build(code_or_shape, ...)`, `cad_build` | none: a decorated function called from Python, in a `.py` file; a shape made elsewhere (a notebook cell, a REPL) is handed over, `model(shape, name=...)` |
| `@xbf` + `@glb` stacked so a GLB bakes its animations | `@model`; `cadgen export <id> model.glb` or `export(x, "model.glb")` bakes them |
| a model call returning its shape (`base = plate()`, `posed(arm(), ...)`) | the call returns the document's handle: compose `plate().shape`; `.id`, `.url` and `.export(...)` are the document's |
| `@model(store="copy")`, a notebook cell's model kept as a copy | none: no copy mode. A cell's shape is handed over, `model(shape, name="plate")`; a model lives in a `.py` file |
| `@model(id="<uuid>")` | none: an id is derived (the script and the function), or `key="plate"` names one: `@model(key=...)`, `@xbf(..., key=...)`, `model(shape, name=..., key=...)` |
| `@model` stacked with `@xbf`, `@step` or another file decorator | one or the other: `@model` for a document with no file, the file decorators for one with files; the stack is refused, drop `@model` |
| `Model.export(...)`, `Model.snapshot(...)`, `Model.document` on the decorated function | the handle a call returns: `arm().export(...)`, `arm().snapshot(...)`, or `export(arm(), ...)` |
| `cadgen export DOC OUT --pose NAME`, `export(..., pose=)` | a model returning `posed(assembly, NAME)`, exported |
| `cadgen export DOC OUT --part OWNER`, `export(..., part=)` | the part's own `@model`, exported |
| `cadgen export ... --no-daemon`, `cadgen snapshot ... --no-daemon` | the same command without the flag |
| `select(source, ref, kind=None)` | `cadgen inspect DOC REF` (`cadgen.inspect(DOC, REF)`); a body picks an element with build123d's selectors |
| `report(detail)`, `track(items, label=)` | none: delete the calls |
| `cadgen.engine.api.snapshot_job(packet, source)` | `cadgen.snapshot(source, job=packet)` |
| `cadgen.serve(doc)`, `cadgen.status()`, `cadgen.stop()`, `cadgen.daemon()` | the commands `cadgen serve DOC`, `cadgen status`, `cadgen stop`, `cadgen server` |
| `cadgen daemon` | `cadgen server` |
| `srgb(...)`, `cadgen.color` | the hex itself |
| a page at `/?doc=...`, `/?file=...`, `/s/<session>/...` | `/<id>`; an old link opens the home |
| `XBF/model.xbf` written by every run as the model's cache | no file: the engine holds the document; export an xbf only as Save As |

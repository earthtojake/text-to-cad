# Exports

Read this file when the user asks for STEP, STL, 3MF, GLB or xbf files, a robot
description (MJCF, URDF), a model in another pose, a part on its own, a project's standing deliverables, or a vendor STEP
converted for use in a model. A 2D profile's DXF is [2D profiles and DXF](2d-profiles-and-dxf.md).

## Contents

- [A file is an action](#a-file-is-an-action)
- [Model page or file page](#model-page-or-file-page)
- [Standing deliverables: `exports.py`](#standing-deliverables-exportspy)
- [Posed files and parts on their own](#posed-files-and-parts-on-their-own)
- [The xbf is Save As](#the-xbf-is-save-as)
- [Formats](#formats)
- [Mesh tolerance](#mesh-tolerance)
- [Robot descriptions](#robot-descriptions)

## A file is an action

A file is written from the document the server holds, when asked, each destination by its suffix.
No code changes and nothing rebuilds. The person can export the same files from the viewer, as
downloads.

```bash
cad model export "$ID" STEP/bracket.step STL/bracket.stl GLB/bracket.glb 3MF/bracket.3mf
```

A file the server reads as a document (an `.xbf`, a `.step`) is a source by its own type, and a
mesh file (`.stl`, `.glb`, `.3mf`) converts to either of the other two mesh formats, keeping what
the target can hold:

```bash
cad step export vendor/motor.step vendor/motor.xbf   # a vendor STEP as an xbf, which xbf.read loads many times faster
cad xbf export share/arm.xbf GLB/arm.glb
cad stl export scan.stl scan.3mf
```

A mesh never becomes an `.xbf`, `.step` or `.dxf`: it has no B-rep, so model it in build123d, with
`stl.read` for its numbers ([inputs](model-contract.md#inputs)).

- **The options** are a mesh file's `--tolerance` and `--angle` ([mesh tolerance](#mesh-tolerance)),
  a robot description's `--zero` ([robot descriptions](#robot-descriptions)) and `--json`. None
  picks a part or a pose: a different file is a different model
  ([posed files and parts on their own](#posed-files-and-parts-on-their-own)).
- **A refused export writes nothing.** Every destination is checked, a DXF's drawing and its
  checks included, before any is written (exit 2). One that fails only once it writes (a full
  disk, a folder it cannot make) exits 1, keeps the files it wrote before and names them in its
  error (`a.stl: ... (a.step was written before it; a.glb was not)`). Each file is written beside
  its target and moved over it, so a failed export leaves the old file whole.
- **`--json`** prints what was written as one object (`{"ok": true, "source", "files": [{"path",
  "kind", "bytes", "seconds", "written", "robot"?}]}`: `written` false where the file already
  held those bytes, `robot` a robot description's summary), and a failure as one `{"ok": false,
  "error": ..., "reason": ...}` (`reason`: `usage`, `invalid_argument`, `wrong_type`, `not_found`).
- **A written file is a detached copy**, whatever wrote it: it changes only when it is written
  again, and a viewer page of it follows the file's bytes on disk, never the model. Give the
  person its path. A check of it as a mesh is a snapshot of that file
  ([mesh files](snapshot-review.md#mesh-files-robots-and-drawings)).

## Model page or file page

The model's page is the default. A project can instead revolve around its exported files, where
the person asks to iterate on the file or the project already works that way (an `exports.py`, a
consumer reading the files, a 0.7-era layout). Each run then writes the file too, by a file
decorator in place of `@model` (`@step("../STEP/bracket.step")`, relative to the script; `@xbf`,
`@glb`, `@stl`, `@threemf` and `@dxf` alike), by `exports.py` or by `cad <type> export` after the
run; the person looks at the file's page; and checks read the file (`cad <type> snapshot` or
`inspect` with its path, or `step.read` in a check).

| | Model page | File page |
| --- | --- | --- |
| Each run | The page updates; nothing is written. | The file is written too and the page re-reads it, a STEP parsed again. |
| A picked ref | `made_by` names the function, file and line. | No `made_by`, a file names no model: a Quick Edit has no way back into the code. |
| A failed run | The page says so. | The file keeps its last write and the page says nothing. |

## Standing deliverables: `exports.py`

A project whose files are delivered again after each change (a print set, a STEP for a
supplier) keeps one script beside its models that imports them and exports each; a one-off file
is a `cad <type> export`. `model.export(x, path, ...)` takes what a model call returns (the
document's handle, whose own `.export(path, ...)` is the same), a document id, or the model
function itself, called as the script's own call is, so an unchanged model is replayed. A file
exports through its own type (`xbf.export("share/arm.xbf", ...)`).

```python
# src/exports.py
from pathlib import Path

from cad import model

from assembly import assembly
from standoff import standoff_m3, standoff_m4

ROOT = Path(__file__).resolve().parent.parent      # the project's folder

if __name__ == "__main__":
    model.export(assembly(), ROOT / "STEP/assembly.step", ROOT / "GLB/assembly.glb")
    model.export(standoff_m3, ROOT / "STL/standoff_m3.stl", ROOT / "3MF/standoff_m3.3mf")
    model.export(standoff_m4, ROOT / "STL/standoff_m4.stl")
```

```bash
cad run src/exports.py
```

## Posed files and parts on their own

A posed file is a model that returns the assembly at a named mechanism state
([mechanism states](kinematics.md#mechanism-states)), exported by its own id:

```python
# src/arm_poses.py
from cad import model
from cad.build123d import posed

from arm import arm                              # an assembly with a mechanism state "folded"


@model
def arm_folded():
    return posed(arm(), "folded")
```

A part meant to ship on its own (a printable bracket, a robot link's mesh in the link's frame) is a
`@model` returning that part where it should sit, which the assembly calls and places; export that
model.

## The xbf is Save As

The `.xbf` is text-to-cad's own document: the parts and placements, names, colours,
materials, element names and mechanism, read back losslessly, and the compiled tracks of
the model's animations, which only a GLB exported from it reads. Export one only to share a model
without its code, or to compose it in another project, where `xbf.read` reads it as an input. A
server restart needs none: the server keeps each document it built.

## Formats

- **STEP** (AP242): the assembly with its instance and product names, colours per part
  and per painted face, materials' names and densities, and the element names on every
  face, edge and vertex, so a STEP read back keeps them. It drops the rest of a
  material's look and physical fields, a face's material (the face keeps its colour),
  and the mechanism: a STEP is placements only.
- **GLB**: glTF 2.0, Y up, in metres. One mesh per part and the assembly's tree as nodes: a
  node per sub-assembly with its components under it, each named by its path below the root
  (`arm/head/pin_1`) and placed in its parent's frame, so a program that reads it walks the tree
  for a part's place in the world. A PBR material per look, with the glTF extensions for IOR,
  transmission, clear coat, anisotropy and emission where a material has them. Each of the
  model's configuration sequences ([kinematics](kinematics.md#configuration-sequences)) and each
  of its `animation()`s ([animation](animation.md)) is an animation of its name, whose
  `extras.cad` holds its `duration` and its `kind`, `"motion"` or `"animation"`; a sub-assembly
  that moves as one is keyed on its own node. `asset.generator` is `cad`. A GLB exported from the
  model by its id, by `model.export(x, path)` or from an xbf the model exported is byte for byte
  the same file.
- **3MF**: an object per part, a build item per placement, in millimetres, with colours
  and materials through the materials extension.
- **STL**: binary, every placed triangle, in millimetres.
- **xbf**: of a model, or of a STEP (converting a vendor file).
- **DXF**: of a planar document only (a 2D drawing); a solid is refused.

STL and 3MF files are in millimetres and a GLB in metres, so a hand-written URDF or MJCF scales an
STL or 3MF link mesh by `0.001` and takes a GLB as it is. A transmissive material is written to a
GLB opaque with its transmission, and to a 3MF, which draws none, at its preview alpha
([colour and materials](build123d-modeling.md#colour-and-materials)).

Mesh exports and the viewer draw the same meshes, made at one tolerance (a chord deviation of
0.25% of the mean side of each part's bounding box, and 28.5 degrees), unless the export gives its
own. A face the mesher leaves without triangles is left out, so a mesh export has a hole there; a
snapshot names such faces in a warning. Repair the face in the model.

## Mesh tolerance

The viewer's mesh is coarse for a print with tight fits and for a close render: on an 85 mm part
its facets sit up to 0.2 mm inside a curved surface, as much as a typical clearance, and large
cylinders show their facets. `--tolerance MM` and `--angle DEG` mesh an STL, a 3MF or a GLB finer,
either alone:

```bash
cad model export "$ID" STL/hopper.stl 3MF/hopper.3mf --tolerance 0.02
cad model export "$ID" GLB/hero.glb --tolerance 0.05 --angle 5
```

- `--tolerance` is an absolute chord deviation in millimetres, at least 0.001. For a print with
  fits, clearances or large curved faces, give about a tenth of the smallest clearance the part
  is designed around (0.02 for a 0.2 mm fit; 0.01 to 0.05 covers most prints).
- `--angle` is a ceiling in degrees, from 1 to 28.5 (the viewer's): it draws small radii in more
  segments, where a tolerance does not reach them.
- From Python they are `model.export(x, path, tolerance=0.02, angle=5)`, and
  `@stl("hopper.stl", tolerance=0.02)`, `@threemf(...)` or `@glb(...)` on a model.

Each part is meshed again at the finer of the option and its own, for that file alone: a file is
never coarser than the viewer's mesh, and the viewer, snapshots and every other export keep
theirs. The file says what it was meshed to (the STL's header, the 3MF's description, the GLB's
`asset.extras.cad`). A mesh file's triangles are its own, so a conversion takes neither option,
and a STEP has no mesh: send a STEP where the person's slicer or shop takes one.

Finer costs triangles on the large curved parts: a tenth of the tolerance is about three times
the segments round a curve and ten times the triangles of a doubly curved face (a 600-part robot
arm at 0.01 mm was 30% more triangles than the viewer's mesh), so say the file's size when it is
large. If the export names faces left without triangles, try a slightly different tolerance or
repair the face.

## Robot descriptions

A mechanism exports as a robot description for a simulator or ROS, by the destination's suffix:
`.xml` (or `.mjcf`) is a MuJoCo MJCF, `.urdf` a ROS URDF.

```bash
cad model export "$ID" sim/arm.xml description/arm.urdf
cad model export "$ID" sim/arm.xml --zero home
```

Each is one description of the model in SI units at its as-built state, and writes its meshes as
binary STL in metres beside it (`assets/` for the MJCF, `meshes/` for the URDF). `--zero STATE`
(`zero="home"` from Python) takes it at a mechanism state instead: every body stands as the state
poses it, each joint's value there is its zero, and its limits and the other states count from
there; the CAD stays as drawn. A state the model does not have is refused, naming the ones it has.
What the model contributes:

- **the mechanism** ([kinematics](kinematics.md)): each link a body, each joint with its axis and
  its limits around the as-built value (or the zero state's), which is every joint's zero in the
  file; couplings as the follower on its leader; mechanism states as MuJoCo keys (a URDF has no
  named poses);
- **materials**: each link's mass, centre of mass and inertia, exact, from its solids at their
  densities; a part with no material weighs nothing, and the export warns of a link with no mass;
- **what its parts declare** ([declaring for a simulator](kinematics.md#declaring-for-a-simulator)):
  named frames, parts kept bodies of their own, drive limits, weighed masses and point masses,
  a floating base and link names;
- **collision**: each part as its own mesh (MuJoCo collides it as its convex hull; a URDF's
  `<collision>` is the same mesh).

Neither file holds a chosen collision shape, contact friction, joint dynamics or an actuator.
Those are a simulation's choices, made in a MuJoCo function on the exported robot; that,
composing a MuJoCo scene around it, checking and tuning it, and the descriptions no model can
write (an SRDF, a hand-written MJCF) are the `robot-simulation` skill's. Never edit the written
file: change the model and export again.

- After each file's `wrote` line the export says what it holds, on stderr: its links and how its
  base stands, its joints by kind and its mass, then its couplings, loops, frames, keys and zero,
  each warning a line before it. `--json` puts the same in the file's row as `robot`.
- An MJCF export writes `scene.xml` beside the robot when there is none (an `include` of the
  robot, a floor, a light, a skybox), which is the person's to edit and never written over.
  `cad mujoco check sim/arm.xml` compiles the MJCF with MuJoCo and checks it. No `cad` command or
  view draws one: the person opens it in MuJoCo Studio (`cad run mujoco-studio --model sim/scene.xml`).
- A URDF whose root link has a mass, or whose root link's frame is not the world's (its first
  part turned or moved in its placement), is rooted at an empty `base_link` before it, as ROS's
  KDL wants and so it stands where the MJCF stands it.
- A closed loop's last joint is an MJCF equality and is left out of a URDF
  ([loops](kinematics.md#loops)); a ball joint in a URDF is refused by name.
- A STEP has no mechanism: exported this way (`cad step export vendor/arm.step sim/arm.xml`), each
  top-level part or assembly is a body fixed to the world.

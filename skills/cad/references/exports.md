# Exports

Read this file when the user asks for STEP, STL, 3MF, GLB or xbf files, a model in
another pose, a part on its own, a project's standing deliverables, or a vendor STEP
converted for use in a model. 2D DXF belongs to `$dxf`.

## Contents

- [A file is an action](#a-file-is-an-action)
- [Model page or file page](#model-page-or-file-page)
- [Standing deliverables: `exports.py`](#standing-deliverables-exportspy)
- [Posed files and parts on their own](#posed-files-and-parts-on-their-own)
- [The xbf is Save As](#the-xbf-is-save-as)
- [Formats](#formats)
- [Other tools](#other-tools)

## A file is an action

A model's document lives in the engine; a file is written from it when asked. In the
viewer, Export is the download button at the navbar's right: pick a format, the engine
prepares the file, the browser saves it. No code changes, nothing rebuilds, and every
destination is written from the document the engine holds, by its suffix:

```bash
cadgen export "$ID" STEP/bracket.step STL/bracket.stl GLB/bracket.glb 3MF/bracket.3mf
```

`$ID` is the `id:` line the model's run printed. The output folders are generated on
request and gitignored by default ([version control](project-layout.md#version-control)). The source can also be a file the
engine reads as a document, an `.xbf` or a `.step`:

```bash
cadgen export vendor/motor.step vendor/motor.xbf
cadgen export share/arm.xbf GLB/arm.glb
```

A mesh file converts to another mesh format: an `.stl`, `.glb` or `.3mf` exports to
either of the other two, keeping what the target format can hold, with no kernel loaded
(`cadgen export scan.stl scan.3mf`). A mesh never becomes an `.xbf`, `.step` or `.dxf`:
it has no B-rep, so model it in build123d, with `read_mesh` for its numbers
([inputs](model-contract.md#inputs)). Each file is written beside its target and
moved over it, so a failed export leaves the old file whole. `--json` prints what was
written as one object (`{"ok": true, "source", "files": [{"path", "kind", "bytes",
"seconds", "written"}]}`), and a failure as `{"ok": false, "error": ...}` with exit status 1.

An export takes a document and its destinations, and nothing else. What a file shows is
the model's business: a different file is a different model.

A written file is a detached copy, whether `cadgen export`, `exports.py` or a file
decorator (`@step`, `@glb`, ...) wrote it: nothing ties it to the model, nothing reruns
it, and a viewer page of it follows the file's bytes on disk, never the model. It
changes only when it is written again. Give the person its path; open it only when they
ask to see it ([Show the model](../SKILL.md#show-the-model)).

## Model page or file page

The model's page is the default; a file's page is for a project that revolves around its
files ([projects built around exported files](../SKILL.md#projects-built-around-exported-files)):

| | Model page | File page |
| --- | --- | --- |
| When | The default. | The person asks to iterate on the exported file, or the project revolves around its files: an `exports.py`, a consumer reading them (a robot description, a slicer, a drawing pipeline), a 0.7-era layout. |
| Each run | The page updates; nothing is written. | The file is written too (a file decorator, `exports.py` or `cadgen export`) and the page re-reads it, a STEP parsed again. |
| A picked ref | `made_by` names the function, file and line. | `made_by` is null, a file names no model: a Quick Edit has no way back into the code. |
| A failed run | The page says so. | The file keeps its last write and the page says nothing. |

## Standing deliverables: `exports.py`

A project whose files are delivered again after each change (a print set, a STEP for a
supplier) keeps one script beside its models that imports them and exports each. From
Python the one spelling is `export(x, path, ...)`, where `x` is what a model call returns
(the document's handle), a document id, or a file. The model function itself is taken
too: it is called as the script's own call is, so an unchanged model comes from the
engine's cache or is replayed, and the file is written from that call's document.

```python
# src/exports.py
from pathlib import Path

from cadgen import export

from assembly import assembly
from standoff import standoff_m3, standoff_m4

ROOT = Path(__file__).resolve().parent.parent      # the project's folder

if __name__ == "__main__":
    export(assembly(), ROOT / "STEP/assembly.step", ROOT / "GLB/assembly.glb")
    export(standoff_m3(), ROOT / "STL/standoff_m3.stl", ROOT / "3MF/standoff_m3.3mf")
    export(standoff_m4(), ROOT / "STL/standoff_m4.stl")
```

```bash
python src/exports.py
```

Write `exports.py` only when the person wants files kept current; a one-off file is a
`cadgen export`. Nothing else in the project writes files.

## Posed files and parts on their own

A posed file is a model that returns the assembly at a named mechanism state, and a
part's file is the part's own model:

```python
# src/arm_poses.py
from cadgen import model
from cad.ap242 import posed

from arm import arm                              # an assembly with a mechanism state "folded"


@model
def arm_folded():
    return posed(arm(), "folded")
```

```bash
python src/arm_poses.py                          # prints arm_folded's id
cadgen export "$FOLDED_ID" STEP/arm_folded.step
```

`posed(assembly, state)` places the assembly's parts at a state the assembly names
([kinematics](kinematics.md#mechanism-states)). A part meant to ship on its own (a
printable bracket, a robot link's mesh in the link's frame) is a `@model` returning that
part where it should sit, which the assembly calls and places; export that model.

## The xbf is Save As

The `.xbf` is cadgen's own document: the parts and placements, names, colours,
materials, element names and mechanism, read back losslessly, and the compiled tracks of
the model's animations, which only a GLB exported from it reads. Export one only:

- to share a model without its code;
- to compose it in another project, where `read_xbf` reads it as an input.

An engine restart needs none: the engine keeps each model document it built in its own
cache, so after a restart the document's id opens in the viewer, answers `cadgen inspect`,
exports and snapshots without a rebuild. It is the last built state: the engine never
checks the code against it and nothing reruns, so after an edit run the script to build it
again.

A vendor STEP converted once (`cadgen export vendor/motor.step vendor/motor.xbf`) is
read by `read_xbf` many times faster than `read_step` parses the STEP, with the same
geometry, names, colours and materials. Keep the xbf beside the STEP, and read the xbf
([inputs](model-contract.md#inputs)).

## Formats

- **STEP** (AP242): the assembly with its instance and product names, colours per part
  and per painted face, materials' names and densities, and the element names on every
  face, edge and vertex, so a STEP read back keeps them. It drops the rest of a
  material's look and physical fields, a face's material (the face keeps its colour),
  and the mechanism: a STEP is placements only.
- **GLB**: glTF 2.0, Y up, in metres. One mesh per part, a node per placement named by
  its occurrence, a PBR material per look (with the glTF extensions for IOR,
  transmission, clear coat, anisotropy and emission where a material has them), each of
  the model's configuration sequences as an animation of its name
  ([kinematics](kinematics.md#configuration-sequences)), and each of its `animation()`s
  ([animation](animation.md)). A GLB exported from the model, by its id, by
  `export(x, path)` or from an xbf the model exported, carries its sequences and its
  animations, byte for byte the same file.
- **3MF**: an object per part, a build item per placement, in millimetres, with colours
  and materials through the materials extension.
- **STL**: binary, every placed triangle, in millimetres.
- **xbf**: of a model, or of a STEP (converting a vendor file).
- **DXF**: of a planar document only (`$dxf`); a solid is refused.

Mesh exports and the viewer draw the same meshes, made at one tolerance
(a chord deviation of 0.25% of the mean side of each part's bounding box, and
28.5 degrees), configurable nowhere. A face the mesher leaves without triangles is left
out, so a mesh export has a hole there; a snapshot names such faces in a warning, and
they are usually slivers a boolean left. Repair the face in the model.

## Other tools

STL and 3MF files are in millimetres and a GLB in metres, so a URDF or SDF scales an STL
or 3MF link mesh by `0.001` and takes a GLB as it is. A check of an export as a mesh is
a snapshot of that file
([mesh files](snapshot-review.md#mesh-files-robots-and-drawings)).

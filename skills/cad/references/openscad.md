# OpenSCAD programs

Read this file when the person has an OpenSCAD program (a `.scad` file) to view, check, export or
change, or asks for OpenSCAD by name. For anything else, a build123d model is the default: it is the
one kernel the server builds, keeps and measures exactly, with the memo, `made_by` and Quick Edit
back into the code. A `.scad` has none of that: its geometry is a mesh.

## Contents

- [What a program is to the server](#what-a-program-is-to-the-server)
- [Edit, show, check](#edit-show-check)
- [Files](#files)
- [In a model](#in-a-model)
- [What it cannot do](#what-it-cannot-do)

## What a program is to the server

A `.scad` is source, like a KiCad board: a file you edit as text, never a model the server builds.
OpenSCAD's kernel makes triangle meshes and no exact geometry, so what the server holds of a program
is the mesh the person's OpenSCAD renders of it, headless, and every command on a `.scad` renders
first: `cad scad` is the type, one operation per command.

```bash
cad scad inspect part.scad                            # the OpenSCAD that rendered it, its includes, triangles, bounds
cad scad export part.scad STL/part.stl 3MF/part.3mf GLB/part.glb
cad scad snapshot part.scad tmp/review.png --camera top
cad scad dfm part.scad --process printing --angle-limit 45
```

OpenSCAD is the person's own, installed by them (2021.01 or newer; `cad doctor` says where it is).
A computer without it fails every `cad scad` command in one line with the install hint: say so and
stop, never install it from a sandbox. `CAD_OPENSCAD` names a particular executable.

The program's `include` and `use` files are read where OpenSCAD reads them: beside the program, in
the person's library folder (`~/.local/share/OpenSCAD/libraries`, `~/Documents/OpenSCAD/libraries`)
and in `OPENSCADPATH`. The server keeps a rendered mesh by the bytes of the program and of every file
it included, so saving an edit to either renders it again, and nothing is rendered twice.

## Edit, show, check

Edit the `.scad` file; a saved edit is the next view. Show the program's page once
([Show the model](../SKILL.md#show-the-model)): its page is the `url` that `cad viewer --json part.scad`
prints, and it follows the file on disk. The page shows the mesh as it shows an STL: Display, Measure
on triangles, Annotate; no exact selection and no Export menu yet (export with `cad scad export`).

Review with a snapshot, as every model is reviewed ([snapshots](snapshot-review.md)); measure with
`cad scad inspect` (bounds, triangle count) or a check script that reads the mesh ([below](#in-a-model)).
A 2D program (a `square`, a `circle` at the top level) is refused in one line: OpenSCAD renders it to a
DXF or an SVG, which the type does not take; give it a `linear_extrude` to render a mesh.

Parameters live in the program. No command sets a variable (`-D`) or gives a parameter file: a verb's
option is about the picture or the path, never the model. A variant of a program is a program: edit
the value, or write the variant beside it.

## Files

`cad scad export` writes the program's mesh: `.stl` (OpenSCAD's binary STL, byte for byte), `.3mf`
and `.glb` (the server's translations of it). It refuses a `.step`, an `.xbf` or a `.dxf` by name:
there is no exact geometry to write. A program's numbers are millimetres, as a slicer takes them.

`cad scad dfm` measures the mesh for 3D printing or molding, as any mesh is measured
([Can it be made?](../SKILL.md#can-it-be-made)); a program's `--units` is not an option, as a 3MF's is not.

## In a model

A build123d model reads a program as mesh data, as it reads an STL:

```python
from cad import scad

mesh = scad.read("enclosure.scad")      # a Mesh: vertices, triangles, bounding_box()
print(mesh.bounding_box().size)
```

OpenSCAD runs at every build that reaches the read (the render is not memoized), and the program's
bytes and its includes' are in the build's closure. A model measures the mesh or sizes B-rep by it;
it does not become a solid.

## What it cannot do

- No exact geometry: no STEP, no face or edge selection, no `made_by`, no Quick Edit into the code.
- No 2D output: a 2D program's DXF or SVG is OpenSCAD's own export, not the type's.
- No parameters from a command: edit the program.
- No viewer Export menu for a program yet: `cad scad export` writes its files.

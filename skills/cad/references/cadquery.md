# CadQuery

Read this file when the project is already written in CadQuery, or the person asks for CadQuery
by name. For anything new, write build123d ([Models](model-contract.md),
[build123d](build123d-modeling.md)): it shares the server's kernel, so an edit replays only what it
changed, every face and edge has a `made_by` that points back into the code, and a Quick Edit from
the viewer lands in the model. A CadQuery model gets a document, a page and every export, and none
of those three.

## Contents

- [Why it is different](#why-it-is-different)
- [Hand the result over](#hand-the-result-over)
- [Run it](#run-it)
- [Files, snapshots and checks](#files-snapshots-and-checks)
- [What does not work](#what-does-not-work)

## Why it is different

CadQuery runs on an OCP build of its own (7.9) and the server's kernel on another (8.0); both are
the one `OCP` module, so CadQuery code can never run inside the server's worker. `cad run` puts a
CadQuery script in an environment of its own, `cad[cadquery]` (CadQuery and the library's core, no
build123d), and the script hands its result over to the server, which makes the document in its own
kernel. Nothing is lost on the way: every solid, name, colour and placement arrives as exact
geometry, and the document is the same kind the viewer shows for any model.

## Hand the result over

Keep the CadQuery code as it is. Where a build123d model has `@model` on a function returning a
shape, a CadQuery script calls `model(value, name=...)` under its `__main__` with what the script
built: a `Workplane` (the shapes on its stack), a `Shape`, a `Sketch` (its faces) or an `Assembly`
(its tree, names, colours and solved locations):

```python
import cadquery as cq
from cad import model


def plate(width=40, thickness=6, bore=8):
    return cq.Workplane("XY").box(width, 20, thickness).faces(">Z").workplane().hole(bore)


def bracket():
    found = cq.Assembly(name="bracket")
    found.add(plate(), name="plate", color=cq.Color(0.3, 0.5, 0.8))
    found.add(cq.Workplane("XY").cylinder(10, 2), name="peg", loc=cq.Location(cq.Vector(10, 0, 8)))
    return found


if __name__ == "__main__":
    model(plate(), name="plate")
    model(bracket(), name="bracket")
```

Each call prints `<name>: handed over`, then its document's `id:` and its page, `view:`, exactly as a
build123d model's run does; the id comes from the script's path and the name, so it is the same run
after run and the open page follows every run. `name=` is required, and two names in one script
folder must differ. Never put `@model` or a file decorator on a CadQuery function: the server would
run it in a worker, where CadQuery is not installed, and the run says so.

## Run it

```bash
cad run src/bracket.py
```

`cad run` sees `import cadquery` and makes the environment of `cad[cadquery]` once, from uv's cache
where it holds it and the network for what that lacks (CadQuery's OCP is some 300 MB the first
time); the runs after are warm. Do not import `OCP` directly in a CadQuery script: that asks for the
server's kernel beside CadQuery's, and uv refuses the environment in one line. CadQuery's own
exporters (`cq.exporters.export`) are not needed and not run: every file is written from the
document the server holds.

## Files, snapshots and checks

A CadQuery document is a model document to every command, by its id:

```bash
cad model export "$ID" STEP/bracket.step GLB/bracket.glb 3MF/bracket.3mf
cad model snapshot "$ID" tmp/review.png --camera iso
cad model dfm "$ID" --process printing
cad model inspect "$ID"
```

[Exports](exports.md), [snapshots](snapshot-review.md) and the manufacturing checks read it as they
read any model's document. Show the person the page once ([Show the model](../SKILL.md#show-the-model)).

## What does not work

- **No memo, no `made_by`, no Quick Edit into the code.** The server never ran the CadQuery code,
  so `cad model inspect "$ID" '<ref>'` answers the geometry's facts and `made_by: null`; a Quick
  Edit prompt's references name faces and parts, and the edit is yours to find in the script.
- **A restart does not rebuild it.** The server keeps the document in its cache and reopens it;
  with the cache gone, the page names no command, so run the script again yourself.
- **No kinematics or animations.** Joints, mechanism states and `animation()` are build123d's; a
  CadQuery assembly arrives posed as CadQuery solved it.
- **Not a reader.** A CadQuery value cannot be composed into a build123d model's body; export a
  STEP from its document and `step.read` that instead.

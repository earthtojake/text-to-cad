# CadQuery

Read this file when the project is already written in CadQuery, or the person asks for CadQuery
by name. For anything new, write build123d ([Models](model-contract.md),
[build123d](build123d-modeling.md)): it shares the server's kernel, so every face and edge has a
`made_by` that points back into the code, and a Quick Edit from the viewer lands in the model. A
CadQuery model gets a document, a page, a warm worker and every export, and neither of those two.

## Contents

- [Why it is different](#why-it-is-different)
- [Write a model and run it](#write-a-model-and-run-it)
- [Warm and cold](#warm-and-cold)
- [Files, snapshots and checks](#files-snapshots-and-checks)
- [Hand a value over](#hand-a-value-over)
- [What does not work](#what-does-not-work)

## Why it is different

CadQuery runs on an OCP build of its own (7.9) and the server's kernel on another (8.0); both are
the one `OCP` module, so CadQuery code can never run inside the server's kernel worker. `cad run`
puts a CadQuery script in an environment of its own, `cad[cadquery]` (CadQuery and the library's
core, no build123d), and the server builds its models in a CadQuery worker it keeps for the script
in that environment. The worker describes each result exactly -- every solid, name, colour and
placement -- and the server makes the document in its own kernel: the same kind of document the
viewer shows for any model.

## Write a model and run it

A CadQuery model is a `@model` function, as any model is: no parameters, returning what the
script built -- a `Workplane` (the shapes on its stack), a `Shape`, a `Sketch` (its faces) or an
`Assembly` (its tree, names, colours and solved locations). Dimensions are the arguments of a plain
helper; an assembly calls its parts and composes their `.shape`:

```python
import cadquery as cq
from cad import model


def plate_body(width=40, thickness=6, bore=8):
    return cq.Workplane("XY").box(width, 20, thickness).faces(">Z").workplane().hole(bore)


@model
def plate():
    return plate_body()


@model
def bracket():
    found = cq.Assembly(name="bracket")
    found.add(plate().shape, name="plate", color=cq.Color(0.3, 0.5, 0.8))
    found.add(cq.Workplane("XY").cylinder(10, 2), name="peg", loc=cq.Location(cq.Vector(10, 0, 8)))
    return found


if __name__ == "__main__":
    plate()
    bracket()
```

```bash
cad run src/bracket.py
```

Each call prints how its model built, the delta under it, its document's `id:` and its page,
`view:`, exactly as a build123d model's run does; the id comes from the script's path and the
function's name, so it is the same run after run and the open page follows every run. Inside a
body, a child model's call hands back its handle, whose `.shape` is the child's CadQuery value, to
compose; the child is part of the assembly's document, not a document of its own. Keep the calls
under `if __name__ == "__main__":`. `cad run` sees `import cadquery` and makes the environment of
`cad[cadquery]` once (CadQuery's OCP is some 300 MB the first time); do not import `OCP` directly,
which asks for the server's kernel beside CadQuery's and is refused in one line.

## Warm and cold

The worker keeps the script's kernel calls between runs, keyed by their operation, parameters and
the shapes they were given, and the run line says what each run cost:

```text
built src/bracket.py::plate cold in 1.84s: bodies 1 run; 25 misses, 0 hits
built src/bracket.py::plate warm in 0.03s: bodies 1 run; 0 misses, 25 hits
```

A cold run is the worker's first: every call runs. An unchanged rerun is warm: every call hits,
and the body returns the very geometry the first run made. An edit re-runs the calls that read
the changed value and what depends on them, and keeps the rest: a wider plate re-runs its box,
hole and fillet, and the peg's chain hits. The memo lives in the worker's memory alone: a restart
(`cad stop`, a memory retirement) makes the next run cold, and the page reopens from the
server's cache meanwhile.

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

## Hand a value over

A value with no function -- a REPL's, a notebook cell's, a script that is not a model -- is handed
over, as a build123d shape is: `model(value, name="plate")` returns the same kind of handle, its
document made from the same description, and no command builds it again.

## What does not work

- **No `made_by`, no Quick Edit into the code.** The worker keeps no trace of which call made which
  face, so `cad model inspect "$ID" '<ref>'` answers the geometry's facts and `made_by: null`; a
  Quick Edit prompt's references name faces and parts, and the edit is yours to find in the script.
- **No file decorators.** `@step`, `@stl` and the rest on a CadQuery function are refused by name;
  a project's standing deliverables are `cad model export` after the run, or an `exports.py`.
- **No `@memo` bodies and no take-up from the cache.** Every run runs the body, warm; a restart
  runs it cold once.
- **No `.shape` in the calling process.** The handle a call returns has its id and page; the value
  lives in the worker. In a body, a child's `.shape` is its value. Elsewhere, call the function.
- **No kinematics or animations.** Joints, mechanism states and `animation()` are build123d's; a
  CadQuery assembly arrives posed as CadQuery solved it.
- **Not a reader.** A CadQuery value cannot be composed into a build123d model's body; export a
  STEP from its document and `step.read` that instead.

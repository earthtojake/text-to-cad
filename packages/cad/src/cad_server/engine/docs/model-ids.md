# Model ids

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`@model` declares a model and its `.xbf`, `<name>.xbf` beside the script unless given a path
(`@model("….xbf")`); the file decorators (`@step` and the others) declare its other files, alone or
with it (**A file decorator's path is optional**); declared by `@step` alone, a model still writes
`<name>.xbf`. A declaration does no work. Call the
function explicitly to build it:

```python
from cad import model

@model
def bracket():
    import build123d as bd
    return bd.Box(10, 20, 3)

if __name__ == "__main__":
    handle = bracket()
```

The document's id is `bracket.id` (and `handle.id`): uuid5 of the script's canonical path and the
function's name, the same in every process (**Architecture**), or `@model(name="bracket")`'s
folder/name id from that same formula. Different scripts can use the same function name; in one folder
each then gives its file a path or `name=`, as both would write `<name>.xbf`. Running the
script again with changed code updates the same document and open viewers; `python parts.py`
prints each model's `id:` and `view:` lines (`<engine>/<id>`), and `handle.url` is the page. No list
of ids is saved.

`cad serve ID`, `cad model snapshot ID view.png`, `cad model export ID part.step`, and `cad
inspect ID 'face 1'` take the id; `cad <type> inspect 'ID#face 1'` uses the same reference syntax.
Each reads the document the engine holds, as it is: editing the script changes nothing until
Python runs it again, and no verb imports, runs or builds a script. Only the viewer's Save of a model's
parameters, which a person asks for in a page, writes the script and runs its last run again
(**Parameters**). An id the engine no longer
holds (unsaved, detached) is refused with its state and the command that builds it again
(`cad run <the script that defines it>`; **Document lifetime**).
`--query build` returns saved-file metadata/closure or live-build metadata; `--query closure` and
`--query geometry` select the other queries explicitly. In the viewer a model's page is
`/<id>`; it is no file's page, so its ⋯ menu acts on the document and on the script that builds it
(Export among them), and it is in the project its script is in, where a person opened one (`viewer/projects.py`).

A shape with no function -- a REPL's, a notebook cell's -- is handed over instead: `model(shape,
name="bracket")` returns the same kind of handle (**Shapes handed over**).

Ids live in the library's `cad.engine.ids`, document names (a CAD file's path or an id) in
`cad.engine.addresses`; the daemon's transient book of live models, by id, lives in [models.py](../models.py).

# Model ids

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`@model` declares a model and its `.xbf`, `<name>.xbf` beside the script unless given a path
(`@model("….xbf")`); the file decorators (`@step` and the others) declare its other files, alone or
with it (**A file decorator's path is optional**). A function declared by `@step` alone writes its STEP alone: no
`.xbf`, so no model document; its id is its first file's, and its page that file's. A declaration does no work. Call the
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

A model's document is its `.xbf`, and its id is that file's (`ids.file_id` of its canonical path): `bracket.id`
(and `handle.id`), worked out from the script's folder and the declared path, or `<name>.xbf`, the same in every
process without asking the engine (**Architecture**). Different scripts can use the same function name; in one
folder each then gives its file a path or `name=`, as both would write `<name>.xbf` -- two models that write one
file share its id, and the last build wins. Running the script again with changed code updates the same document
and open viewers; `python parts.py` prints each model's `id:` and `view:` lines (`<engine>/<id>`), and `handle.url`
is the page. No list of ids is saved. An id from before ids were the `.xbf`'s (its script and function, or its
folder and `name=`) answers as the model's (**Identity migration**).

`cad serve ID`, `cad model snapshot ID view.png`, `cad model export ID part.step`, and `cad
inspect ID 'face 1'` take the id; `cad <type> inspect 'ID#face 1'` uses the same reference syntax.
Each reads the document as it is -- the live worker's, else its `.xbf` -- and so does the `.xbf`'s path:
editing the script changes nothing until Python runs it again, and no verb imports, runs or builds a script. Only the viewer's Save of a model's
parameters, which a person asks for in a page, writes the script and runs its last run again
(**Parameters**). An id whose `.xbf` is gone
(unsaved, detached) is refused with its state and the command that builds it again
(`cad run <the script that defines it>`; **Document lifetime**).
`--query build` returns saved-file metadata/closure or live-build metadata; `--query closure` and
`--query geometry` select the other queries explicitly. In the viewer a model's page is
`/<id>`, and opening its `.xbf` by path opens that page: the model, live -- its parameters editable, its
provenance asked -- while a worker holds its build, else the file read as any file is. Its ⋯ menu acts on the
document and on the script that builds it (Export among them), and it is in the project its `.xbf` is in, where a
person opened one (`viewer/projects.py`).

A shape with no function -- a REPL's, a notebook cell's -- is handed over instead: `model(shape,
name="bracket")` returns the same kind of handle, its id its `.xbf`'s too (**Shapes handed over**).

Ids live in the library's `cad.engine.ids`, document names (a CAD file's path or an id) in
`cad.engine.addresses`; the daemon's transient book of live models, by id, lives in [models.py](../models.py).

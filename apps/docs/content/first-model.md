---
title: Your first model
description: A walk-through from a fresh install to a part on screen, a change to it, and a STEP or STL file out.
---

This page follows one small part from a prompt to a file. It assumes you have run the [install command](/docs/install) and restarted your agent app.

## Ask for a part

Open your agent in a folder you want the model to live in, and ask for something plain:

```text
Make a 40 by 20 mm mounting bracket, 6 mm thick, with an 8 mm hole through the middle.
```

You do not name a skill. The agent picks the [cad skill](repo:skills/cad/SKILL.md) from the request.

## What the agent writes

The agent writes a Python script. A model is a function with no parameters, marked `@model`, that returns a build123d shape. Units are millimetres, with +Z up. A script such as `src/bracket.py` looks like this:

```python
import build123d as bd
from cad import model


def bracket_body(width, thickness, bore):
    body = bd.Box(width, 20, thickness)
    hole = bd.Cylinder(bore / 2, thickness)
    body = body - hole
    body.label = "bracket"
    body.color = "#4a6fa5"
    return body


@model
def bracket():
    return bracket_body(40, 6, 8)


if __name__ == "__main__":
    bracket()
```

The dimensions are arguments of a plain helper, so a change is one number. The call under `__main__` is what builds the model. Importing the script builds nothing, which lets other scripts, such as an assembly, import the part. [Models](repo:skills/cad/references/model-contract.md) covers the contract, and [project layout](repo:skills/cad/references/project-layout.md) covers where scripts go.

## What running it prints

The agent builds the script with the `cad` command:

```bash
cad run src/bracket.py
```

`cad run` works like `uv run`, so the script's own packages come from its header. It prints how the model built, then two lines that matter to you:

```text
  id: 0dc50a92-a21f-5895-a245-ebdeb5352f3b
  view: http://127.0.0.1:54360/0dc50a92-a21f-5895-a245-ebdeb5352f3b?token=...
```

The `id:` names the model's document. It comes from the script's path and the function's name, so it is the same on every run. The `view:` line is its page in the viewer. Your port and token will differ.

> [!NOTE]
> The first build downloads the CAD kernel, about 240 MB, and a first model waits for it. It is made once, in a cache folder, and every later build reuses it. [Installing by hand](/docs/install#what-a-model-runs-in) says what lives where.

## See it on screen

Your agent shows you the model. In apps with the CAD app, the viewer opens inside the app, as a card in Claude Desktop or a tab in Codex. In the others you get the `view:` link to open in your browser. You can also run `cad viewer` yourself, which opens the viewer's home. See [the viewer](/docs/viewer).

## Ask for a change

Stay in the same conversation:

```text
Make the hole 10 mm and the bracket 60 mm long.
```

The agent edits the numbers and runs `cad run src/bracket.py` again. The page you have open updates on its own. The server keeps a warm worker for the script and replays every step the edit did not reach, so a small edit rebuilds quickly.

## Export a file

A run writes no files. A model is a document the server holds, and files are made when you ask:

```text
Export the bracket as a STEP file and an STL.
```

The agent runs `cad model export` with the model's id:

```bash
cad model export "$ID" STEP/bracket.step STL/bracket.stl
```

`$ID` is the `id:` line from the run. The format comes from the file's suffix, and `GLB` and `3MF` work the same way. You can also use Export in the viewer's file menu, which hands you a browser download. An STL for printing a part with fits takes a tolerance, which [exports](repo:skills/cad/references/exports.md) explains.

## Where to go next

- [cad](/docs/cad): assemblies, configurations and what else a model can do.
- [The viewer](/docs/viewer): what you can do on the page.
- [Supported agents](/docs/agents): what each app shows and how.
- [The cad command](/docs/reference/commands): running and checking things yourself.

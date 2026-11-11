---
title: Parts and assemblies
description: Ask for a part or an assembly and your agent writes it as a build123d Python script, builds it in the CAD Viewer and exports STEP, STL, 3MF or GLB on request.
---

In text-to-cad a part or an assembly is a Python function. Your agent writes it with build123d, a Python library for B-rep CAD (solid models described by their faces and edges), and runs the script. The server builds the model and the CAD Viewer page you have open updates. You end up with a model you can keep editing in plain text, and with STEP, STL, 3MF or GLB files whenever you ask for them.

## What to ask

- "Make a 60 by 40 mm mounting plate, 4 mm thick, with four 4.5 mm holes 6 mm in from the corners."
- "Add two M3 standoffs, 12 mm tall, 30 mm apart on that plate, and put them in an assembly."
- "Make the bracket 20 mm wider and re-check that the bore is still 8 mm."
- "Give me the assembly as a STEP and the standoff as an STL for printing."

## What your agent does

1. **Writes a model script.** A model is a function with no parameters, decorated with `@model`, that returns a build123d shape. Its dimensions are the arguments of a plain helper function, and each configuration is a `@model` of its own with its own id and page. Units are millimetres and +Z is up.

   ```python
   import build123d as bd
   from cad import model


   def bracket_body(width, thickness, bore):
       body = bd.Box(width, 20, thickness)
       body = body - bd.Cylinder(bore / 2, thickness)
       body.label = "bracket"
       body.color = "#4a6fa5"
       return body


   @model
   def bracket():
       return bracket_body(40, 6, 8)


   @model
   def bracket_wide():
       return bracket_body(60, 6, 8)


   if __name__ == "__main__":
       bracket()
       bracket_wide()
   ```

2. **Runs it.** `cad run` works like `uv run`, so the script needs no setup.

   ```bash
   cad run src/bracket.py
   ```

   Each call in `__main__` prints how its model built, its `id:` and its `view:` page. The id comes from the script's path and the function's name, so it is the same on every run, and the open page follows it.

3. **Edits rebuild only what changed.** A warm worker in the server keeps every kernel operation the script ran. A comment re-runs nothing, and a changed dimension re-runs only what reads it. Running the script writes no file.

4. **Builds assemblies by calling the parts.** An assembly's body calls each part model, places it, labels it and returns a `Compound`. Each part keeps its own document and id. Labels name each placement in the viewer's tree, in references and in exports.

   ```python
   @model
   def assembly():   # plate and standoff_m3 are models imported from their scripts
       base = plate().shape
       post = standoff_m3().shape
       left = bd.Pos(-15, 0, 8) * post
       right = bd.Pos(15, 0, 8) * post
       left.label, right.label = "standoff_left", "standoff_right"
       return bd.Compound(children=[base, left, right], label="assembly")
   ```

   Running a child's script alone leaves its assemblies as they were. Run the assembly.

5. **Checks the change.** It takes a snapshot with `cad model snapshot "$ID" tmp/review.png`, puts an `assert` on a dimension you gave inside the model body, and for an assembly runs `cad model interference "$ID"`, which reports parts that share volume. When your prompt carries a face you picked in the viewer, it resolves it with `cad model inspect "$ID" "bracket/face 7"`.

6. **Exports files when you ask.** A file is written from the document the server holds. No code changes and nothing rebuilds.

   ```bash
   cad model export "$ID" STEP/bracket.step STL/bracket.stl GLB/bracket.glb 3MF/bracket.3mf
   ```

   For a print with tight fits, an STL or 3MF takes `--tolerance MM`, about a tenth of the smallest clearance. A project whose files must stay current gets an `exports.py`.

## What you get

- **A live model page** in the [CAD Viewer](/docs/guides/cad-viewer), at the `view:` link the run prints. Your agent shows it to you once. It updates on every run.
- **Source you own**: the scripts, usually under `src/`. The server's cache reopens every built model after a restart, as last built. It never reruns code, so after an edit your agent runs the script again.
- **Files only on request**, in folders such as `STEP/`, `STL/`, `GLB/` and `3MF/`, which a project normally keeps out of git. The formats:
  - STEP (AP242) keeps instance and product names, colours, material names and element names. It drops the mechanism.
  - STL is binary, in millimetres.
  - 3MF has an object per part and a build item per placement.
  - GLB is glTF 2.0, Y up, in metres, with the assembly as a node tree.

## Limits

- A model takes no parameters. A variant is another `@model` calling the same helper.
- A file is a detached copy. It changes only when it is written again, and nothing ties it to the model afterwards.
- A mesh (STL, 3MF, GLB) never becomes a STEP or a model, because it has no B-rep. Your agent reads a scan's numbers with `stl.read` and builds geometry from them.
- A snapshot shows arrangement and appearance. It is not a measurement, so dimensions are checked in code or with `cad model inspect`.

## Go deeper

- [First model](/docs/first-model) walks through a first request end to end.
- [Mechanisms and animation](/docs/guides/mechanisms) adds joints, poses and motion to an assembly.
- [Manufacturing checks](/docs/guides/manufacturing-checks), [DXF profiles and flat patterns](/docs/guides/dxf-profiles) and [stress studies](/docs/guides/stress-studies) take a finished model further.
- Document types: [model](/docs/document-types/model), [STEP](/docs/document-types/step), [STL](/docs/document-types/stl), [3MF](/docs/document-types/threemf) and [GLB](/docs/document-types/glb). Integration: [build123d](/docs/integrations/build123d).
- In the repository: [the cad skill](repo:skills/cad/SKILL.md), [models](repo:skills/cad/references/model-contract.md), [build123d patterns](repo:skills/cad/references/build123d-modeling.md), [project layout](repo:skills/cad/references/project-layout.md), [positioning](repo:skills/cad/references/positioning.md), [exports](repo:skills/cad/references/exports.md), [inspection](repo:skills/cad/references/inspection-and-validation.md) and [snapshots](repo:skills/cad/references/snapshot-review.md).

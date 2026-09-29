---
name: implicit
description: Model parts as signed distance fields with cadgen — every shape is a function of distance, booleans are min/max, fillets and shells are offsets — mesh them to GLB/STL for printing, and answer wall-thickness, clearance and interference questions on the field itself. Use for organic or blended shapes, lattice-like repeats, shells, "smooth union", "SDF geometry", "implicit modeling", or when a boolean-heavy part keeps failing in B-rep CAD. Not for STEP output (use $cad) and not for SDFormat robot files (use $sdf).
---

# Implicit: parts as signed distance fields

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

A part is a Python script that returns a **field**: for any point, the signed
distance to the part's surface (negative inside, positive outside). Primitives
are exact distances, booleans are arithmetic on them (union is `min`,
intersection `max`, subtraction `max(a, -b)`), and a fillet, a shell or an
offset is a number added to the field. Nothing can fail the way a B-rep boolean
fails: every combination of fields is a field.

Running the script writes two files: `part.step`, the field's B-rep with its
blends as fillets, which opens in the viewer as any STEP does (edges, face
selection, measure, drawings); and `part.implicit.json`, the **tape**, the
field as data and the part's source of truth. Every primitive in the script is
a **leaf**, and every face of the STEP knows which leaf made it:
`cadgen implicit faces` turns a selector the user picked (`part.step#o1.f7`)
into the leaf's name and the script line that wrote it. When the kernel cannot
build the B-rep (a shell it refuses, a custom field) the script writes a mesh
of the same name instead and says why.

## Start with the task

| Task | First action | Reference |
| --- | --- | --- |
| **Create or edit a part** | Write or edit the decorated script below; run `python <part>.py`. | [Modeling](references/modeling.md) |
| **Know which line made a face the user picked** | `cadgen implicit faces part.step --ref part.step#o1.f7` | [Questions](references/questions.md#faces) |
| **Measure walls, clearance, interference** | Ask the field in Python, or `cadgen implicit measure` on the tape. | [Questions](references/questions.md) |
| **Start from an existing STEP** | `im.from_step(path)` makes it a leaf; shell, blend, cut or pattern it in the field; the STEP that comes out keeps its faces. | [Starting from a B-rep](references/modeling.md#starting-from-a-b-rep) |
| **A mesh for printing** | `cadgen implicit build <tape> part.stl --resolution 0.2`, or add `.glb`/`.stl` to `out`. | [Meshing](references/meshing.md) |
| **Review the result** | Snapshot the STEP; hand it to `$cad-viewer`. | [Meshing](references/meshing.md#reviewing) |

## Setup

`requirements.txt` pins `cadgen`; install it with the project interpreter.
The implicit engine needs nothing beyond that (numpy only), so it runs in every
cadgen install. Snapshots need Chromium (`python -m playwright install chromium`).

Units are whatever the script uses — millimetres by convention. Z is up. A
resolution is the size of one grid cell in those units.

## Create or edit a part

```python
from cadgen import implicit as im


@im.part
def housing():
    body = im.box((30, 30, 20), radius=2).named("body")
    bore = im.cylinder(radius=8, height=40).named("bore")
    boss = im.cylinder(radius=5, height=8).translate(0, 0, 14).named("boss")
    holes = im.cylinder(radius=1.6, height=30).translate(11, 11, 0).mirror("x").mirror("y").named("holes")
    return im.union(body - bore, boss, round=1.5) - holes


if __name__ == "__main__":
    housing()
```

```bash
python src/housing.py            # writes src/housing.step and src/housing.implicit.json
python src/housing.py --json     # the build result as one JSON line
```

- **One decorated part per script.** `out` relocates or adds outputs, relative
  to the script: `out="../STEP/housing.step"`, or a list that also names a
  `.glb`/`.stl` mesh for printing (`resolution=` sets its cell size). Omitted,
  `<stem>.step` beside the script. The tape goes beside the first output.
- **Name every leaf** with `.named("...")`: that is what a face maps back to.
  Naming a moved or unioned group names every unnamed leaf inside it.
- **Compose** by calling another part's decorated function inside a body: it
  returns that part's field. A field is immutable; every method returns a new one.
- Keep dimensions as named constants at the top, as in `$cad`.
- Read the build's warnings: a blend the kernel could not fillet is left sharp
  in the STEP and named; a tree it cannot build at all becomes a mesh.

The field vocabulary — primitives, 2D profiles for extrude and revolve,
placement, offsets, shells, rounds, chamfers, repeats and B-rep leaves — is in
[modeling.md](references/modeling.md).

## Verify and hand off

After writing or changing a part:

1. Run the script and read its result lines and warnings.
2. Measure what the request specified on the field; see
   [questions.md](references/questions.md).

   ```bash
   cadgen implicit measure src/housing.implicit.json --walls --at 0,0,0
   ```

3. Snapshot and look:

   ```bash
   cadgen step snapshot src/housing.step tmp/housing.png
   ```

4. Hand `src/housing.step` to `$cad-viewer` when installed and include its link.
   A face the user then picks arrives as `housing.step#o1.f7`; answer what it
   is with `cadgen implicit faces src/housing.step --ref housing.step#o1.f7`.

Report the output files, the measurements you took with their resolution
(every number is exact only to a cell), and any blend the STEP left sharp.

## Commands

Run `cadgen` from the environment `requirements.txt` was installed into
(`python -m cadgen.cli <verb>` is the PATH-independent form). The verbs work on
saved files, never on the script:

```bash
cadgen implicit build src/housing.implicit.json                          # the STEP again
cadgen implicit build src/housing.implicit.json STL/housing.stl --resolution 0.2
cadgen implicit measure src/housing.implicit.json --walls --at 14,14,0 --json
cadgen implicit faces src/housing.step --ref housing.step#o1.f7
```

`--help` on any of them lists the current flags.

## References

- Field vocabulary and modeling patterns: [modeling.md](references/modeling.md)
- Questions on the field (thickness, clearance, interference, probes): [questions.md](references/questions.md)
- Meshing, resolution, the tape, GLB nodes, review: [meshing.md](references/meshing.md)

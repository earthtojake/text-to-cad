# Migrating from 0.10 to the next release

Draft: this guide is renamed for its release when it ships. It covers the document types and
integrations: the library's imports and the `cad` command's.
The next release is a minor release, so it never installs itself: update with the update button or
`cad update` when you are ready. Its patch releases then install themselves, with automatic updates on.

## The library's imports

Every 0.10 import keeps working, as an alias of the same object. Each says so once per process,
with `CadDeprecationWarning` (a `FutureWarning`, which Python shows by default), naming the new path:

```text
model.py:1: CadDeprecationWarning: cad.read_step is deprecated; use cad.step.read
```

Migrate a project on first touch. A document type is one object now -- its decorator, its reader
and its operations -- and our helpers that take build123d's objects are `cad.build123d`'s.

| 0.10 | Now |
| --- | --- |
| `from cad import xbf, step, glb, stl, threemf, dxf` | unchanged: each is the type, and `@step("arm.step")` still declares a file; a file's type takes its files alone (`xbf.export("arm.xbf", ...)`), a model's id or handle is `cad.model`'s |
| `from cad import model` / `@model`, `model(shape, name=...)` | unchanged: `model` is also the type of a model the engine holds, with no file (`model.export`, `model.snapshot`, `model.inspect`, `model.dfm`, each taking a handle or a document id) |
| `from cad import read_step` / `read_step(path)` | `from cad import step` / `step.read(path)` |
| `from cad import read_xbf` / `read_xbf(path)` | `from cad import xbf` / `xbf.read(path)` |
| `from cad import read_mesh` / `read_mesh(path)` | `from cad import stl` / `stl.read(path)` |
| `from cad import export` / `export(handle, *paths)` | `from cad import model` / `model.export(handle, *paths)` (`tolerance=` as before); the alias is `cad.model.export` itself, so a file is its own type's: `xbf.export("arm.xbf", "arm.step")`, `stl.export("part.stl", "part.glb")` |
| `from cad import snapshot` / `snapshot(source, out)` | `cad.<type>.snapshot(source, out)`: `model.snapshot(handle, out)`, `stl.snapshot("part.stl", out)` |
| `from cad import inspect` / `inspect(source, ref)` | `cad.<type>.inspect(source, ref)`: `model.inspect(handle, ref)`, `step.inspect("part.step")` |
| `from cad import memo, paint` | `from cad.build123d import memo, paint` |
| `from cad.ap242 import mechanism_state, configuration_sequence, gear_pair, rack_and_pinion_pair, screw_pair, posed` | `from cad.build123d import ...` (the same names) |
| `from cad.gltf import animation` | `from cad.build123d import animation` |
| `from cad.geometry import overlap_volume, ...` | `from cad.build123d import overlap_volume, ...` |
| `from cad import flatten` / `flatten.flat_pattern(...)` | `from cad.build123d import flat_pattern` / `flat_pattern(...)` (also `planar_faces`, `flatten_face`, `flatten_faces`, `union_faces`, `offset_profile`) |
| `cad.urdf.validate`, `cad.sdf.validate`, `cad.srdf.validate` | unchanged |
| `cad.results.ValidationResult`, `ValidationIssue` | `cad.results.CheckResult`, `CheckFinding` (`.findings`, each with `.location`); the old names keep their 0.10 call shapes, `ValidationIssue(severity, message, element=, code=, hint=)` and `ValidationResult(ok, path, issues=, summary=)`, and `.issues` and `.element` still read |
| `cad.findings`, `cad.xml_common`, `cad.check_fonts`, `cad.urdf_source`, `cad.sdf_source`, `cad.sdf_validation`, `cad.sdf_external`, `cad.srdf_source`, `cad.srdf_validation` | private now (`cad._internal.*`, `cad.<type>._*`): the aliases keep working, and nothing of a model's needs them |
| `cad.pcb` (the KiCad pull request's, never released) | `cad.kicad_pcb`: `read` (was `read_board`), `inside`, `inspect` (was `inspect_board`), `drc`, `export`; a schematic's, `cad.kicad_sch`: `read`, `inspect`, `erc`, `export`; no alias, as they never shipped |
| `cad.eng_drawing` | unchanged |

`import build123d as bd` is unchanged: `cad.build123d` holds only our helpers, never build123d's own
names.

A model whose body returns something no producer takes now fails naming what the type is made of:
`model part.py::part returned DataFrame; a step document is made of a build123d Shape (there is no
pandas integration: one would add a producer of it)`.

## The `cad` command

A hard cutover: the old spellings are gone, and each answers as a command that never existed does.
The shape is `cad <document_type> <operation> <file>`, the type the file's (`cad --help` lists them).

| 0.10 | Now |
| --- | --- |
| `cad export arm.xbf arm.step` | `cad xbf export arm.xbf arm.step` |
| `cad export <id> arm.glb` (a model's id) | `cad model export <id> arm.glb` |
| `cad export vendor.step vendor.xbf` | `cad step export vendor.step vendor.xbf` |
| `cad export part.stl part.3mf` | `cad stl export part.stl part.3mf` |
| `cad snapshot <file> out.png` | `cad <type> snapshot <file> out.png`: `cad model snapshot <id> out.png`, `cad dxf snapshot panel.dxf out.png`, `cad urdf snapshot robot.urdf out.png` |
| `cad snapshot --job PACKET` | `cad <type> snapshot --job PACKET`, the type of the packet's input |
| `cad inspect <file or id> [REF]` | `cad model inspect <id> [REF]`, `cad step inspect <file>`, `cad glb inspect <file>` |
| `cad urdf validate robot.urdf`, `cad sdf validate world.sdf`, `cad srdf validate robot.srdf` | unchanged (`--urdf robot.urdf` names an SRDF's URDF) |
| `cad pcb drc board.kicad_pcb` (the KiCad pull request's) | `cad kicad_pcb drc board.kicad_pcb`; a schematic's ERC, `cad kicad_sch erc board.kicad_sch` |
| `python -m cad_server.cli.export ...`, `.snapshot`, `.inspect` | `python -m cad_server.cli.<type> <operation> ...` |
| `python -m cad_server.cli.urdf_validate ...` (and `sdf_`, `srdf_`) | `python -m cad_server.cli.urdf validate ...` |

The operations are named for what they do: `export` and `snapshot` are every type's that has them, and
the checks are `dfm` (a 3D type's manufacturing check), `drc` (a board's), `erc` (a schematic's) and
`validate` (a robot description's). `--json` of a check now answers `findings`, each `{severity, code, message, location, hint}`, where
0.10 answered `issues`, each with `element`. A file of another type is refused by name before anything
runs (`part.glb is a glb, not a stl: use cad glb snapshot`).

These stay as they were: `cad run`, `serve`, `status`, `stop`, `delete`, `server`, `setup`, `update`,
`uninstall`, `doctor`, `plugin`, `viewer`, `telemetry`.

## The manufacturing measurements

The dfm skill's `scripts/mold_tool.py` and the dfam-check skill's `scripts/dfam_tool.py`, and the
`requirements.txt` each installed beside them, are gone: their measurements are the library's trimesh
integration now (`cad[trimesh]`), reached by a 3D type's `dfm`. The report each printed is the
result's `measurements` (`--json`), its families and figures as they were; a family that could not be
measured fails the check (exit 1, where the scripts exited 2), and what the figures show are findings.

| 0.10 | Now |
| --- | --- |
| `python scripts/mold_tool.py measure part.stl --pull z [--units mm] [--wall-limit 45] [--zero-tol 0.05]` | `cad stl dfm part.stl --process molding --pull z [--units mm] [--wall-limit 45] [--zero-tol 0.05]` |
| `python scripts/mold_tool.py pulls part.stl` | `cad stl dfm part.stl --process molding --candidates` |
| `python scripts/dfam_tool.py measure part.stl [--samples 2000] [--angle-limit 45]` | `cad stl dfm part.stl --process printing [--samples 2000] [--angle-limit 45]` |
| `python scripts/dfam_tool.py orientations part.stl [--angle-limit 45]` | `cad stl dfm part.stl --process printing --candidates [--angle-limit 45]` |
| a `.3mf` | `cad threemf dfm part.3mf ...` (its declared unit, read as millimetres) |
| an `.obj` or a `.ply` | no document type: `cad.trimesh.molding(trimesh.load(path))`, `cad.trimesh.printing(...)` |
| a STEP or a model, exported to an STL first | `cad step dfm part.step ...`, `cad model dfm <id> ...`, `cad.model.dfm(handle, process=...)` |

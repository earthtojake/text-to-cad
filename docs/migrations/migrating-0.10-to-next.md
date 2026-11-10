# Migrating from 0.10 to the next release

Draft: this guide is renamed for its release when it ships. It covers the skills, the library's
imports, the `cad` command, what `cad run` runs a program in, and setting up and updating.
The next release is a minor release, so it never installs itself: update with the update button or
`cad update` when you are ready. Its patch releases then install themselves, with automatic updates on
([Setting up and updating](#setting-up-and-updating)).

Each change names its tier of the compatibility law ([law 15](../../packages/cad/README.md#the-design-laws),
"Compatibility, by who pays for a break"), which says what a change of its kind keeps working.

## The skills (tier 1)

The twelve skills are six, each an outcome rather than a file format. An agent reads the new ones
from the session it starts after the update; a prompt, a script or a config that names an old skill
names its new one.

| 0.10 | Now |
| --- | --- |
| `urdf`, `srdf`, `sdf` | `robot-simulation` |
| `dxf` | `cad`, which makes 2D profiles, flat patterns and DXFs |
| `dfm`, `dfam-check` | `cad`'s manufacturing checks ("Can it be made?"); their scripts are `cad <type> dfm` ([The manufacturing measurements](#the-manufacturing-measurements-tier-1)) |
| `gcode`, `bambu-labs` | `print3d`: slicing with OrcaSlicer (`scripts/orca_presets.py`, which was `gcode/scripts/orca_presets.py`) and the Bambu Connect or Bambu Studio handoff |
| `step-parts` and its `scripts/download_step_part.py` | gone: step.parts stays a service of its own |
| (new) | `pcb`: KiCad boards and schematics |

`cad`, `engineering-drawing` and `sendcutsend` keep their names. The install command and `cad
update` delete a loose copy of a retired skill -- one the Skills CLI installed, which never removes
a skill -- and the Skills CLI's record of it, so `npx skills update` does not bring it back; 0.10
moved such a copy aside. A loose copy of a skill that still ships is moved aside, as before.

## The library's imports (tier 2)

These renames break nothing, since every 0.10 spelling still works: each is an alias of the same
object as its new spelling, but the two result classes (below), and says so once per process, with
`CadDeprecationWarning` (a `FutureWarning`, which Python shows by default), naming the new path:

```text
model.py:1: CadDeprecationWarning: cad.read_step is deprecated; use cad.step.read
```

What does break is under [What an alias cannot keep](#what-an-alias-cannot-keep), at the end of this
section. Migrate a project on first touch. A document type is one object now -- its decorator, its
reader and its operations -- and our helpers that take build123d's objects are `cad.build123d`'s.

| 0.10 | Now |
| --- | --- |
| `from cad import xbf, step, glb, stl, threemf, dxf` | unchanged: each is the type, and `@step("arm.step")` still declares a file; a file's type takes its files alone (`xbf.export("arm.xbf", ...)`), a model's id or handle is `cad.model`'s |
| `from cad import model` / `@model`, `model(shape, name=...)` | unchanged: `model` is also the type of a model the engine holds, with no file (`model.export`, `model.snapshot`, `model.inspect`, `model.dfm`, each taking a handle or a document id) |
| `from cad import read_step` / `read_step(path)` | `from cad import step` / `step.read(path)` |
| `from cad import read_xbf` / `read_xbf(path)` | `from cad import xbf` / `xbf.read(path)` |
| `from cad import read_mesh` / `read_mesh(path)` | `from cad import stl` / `stl.read(path)` |
| `from cad import export` / `export(handle, *paths)` | `from cad import model` / `model.export(handle, *paths)` (`tolerance=` as before); a file is its own type's: `xbf.export("arm.xbf", "arm.step")`, `stl.export("part.stl", "part.glb")`. The alias is the engine's export (`cad.engine.api.export`), which takes any source as 0.10's did -- a handle, a document id or a file -- so a 0.10 `exports.py` keeps writing a file's exports until it is migrated |
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

### What an alias cannot keep

These do break, where a program relies on them:

- **A star import.** An alias is in no `__all__`, so `from cad import *` no longer binds `memo`,
  `paint`, `read_step`, `read_xbf`, `read_mesh`, `export`, `snapshot` or `inspect`, nor `from
  cad.results import *` `ValidationResult` or `ValidationIssue`: import each by its new path.
- **The result classes.** A check returns a `CheckResult`, and `ValidationResult` is 0.10's call shape
  of one, not the class itself: `isinstance(result, ValidationResult)` is false, and
  `dataclasses.asdict(result)` is `{ok, path, findings, summary, measurements}`, each finding `{severity,
  code, message, location, hint}`, where 0.10's was `{ok, path, issues, summary}`, each issue `{severity,
  message, element, code, hint}`. Test for `CheckResult`, and read `findings` and `location`.

## The `cad` command (tier 1)

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
| `cad snapshot --display dark` (or `light`, or `{"appearance": ...}`), and `cad_snapshot`'s `display` the same | gone: every snapshot is light, whatever the viewer's theme. The word is no display mode, the key no display key, and a drawing takes no `--display` |
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

These stay as they were, but for how they fail and what one that destroys asks (below): `serve`,
`status`, `stop`, `delete`, `server`, `uninstall`, `plugin`, `viewer`, `telemetry`. `cad run` changes
what it runs a program in ([`cad run`](#cad-run-tier-1)), and `setup`, `update` and `doctor` what they
set up ([Setting up and updating](#setting-up-and-updating)); what `cad doctor` reports, and what `cad
update --dry-run` reads, are below too.

### How a command fails

Every command fails by one contract: the failure's class sets the exit status, the same with `--json`
and without -- 2 for the command line and its input (a command or an option it does not take, an
argument missing or out of range, a file of another type or one that is not there, a command that
destroys run where no one can be asked, without `--yes`), 1 for a failure of the work, 130 for Ctrl-C --
and under `--json` it is one JSON document on stdout, `{"ok": false, "error": ..., "reason": ...}`,
with nothing else there and no traceback. `reason` is one of `usage`, `invalid_argument`, `wrong_type`,
`not_found`, `confirmation_required` (exit 2), `declined`, `engine_unavailable`, `failed`,
`internal_error` (exit 1) and `canceled` (130). Read the exit status, then `reason`; `error` is for a
person. A check's findings are still its answer, not a failure: a check that finds a blocking one exits
1 with its result (`"ok": false`, its `findings`), as `cad doctor` does with its report.

| 0.10 | Now |
| --- | --- |
| a refusal under `--json` (`part.glb is a glb, not a stl`) exited 1 | exits 2, as it does without `--json`, `"reason": "wrong_type"` |
| a usage error under `--json` (`cad xbf export --json`) was argparse's text on stderr | `{"ok": false, "error": "the following arguments are required: SRC, DST", "reason": "usage"}` on stdout, exit 2 |
| a failure no command expected, under `--json`, printed its JSON and then a traceback | its JSON alone, `"reason": "internal_error"`, exit 1 |
| a prefix of an option was read as the option: `cad status --js`, `cad doctor --p` (which ran `--prune`) | an unrecognized argument, exit 2, naming the option it is closest to |
| an unknown command printed the whole usage, and an operation a type does not have (`cad step exprt`) the type's whole help | its name, the one it is closest to, and where they are told, in one line: `'cad --help' lists the commands`; `it has export, snapshot, inspect, dfm; 'cad step --help' says what each does` |
| Ctrl-C printed a traceback | `cad: canceled`, exit 130 |
| `cad telemetry on` or `cad update auto off` that could not save the choice said so on stdout, where its answer goes | on stderr, as every failure's words are without `--json`: `cad telemetry: could not save the choice: ...`, exit 1 |
| a value a check's option does not take (`cad sdf validate world.sdf --gz-check maybe`, `cad stl dfm part.stl --process casting`) failed as a `ValueError` naming the Python parameter, exit 1 | `argument --gz-check: invalid choice: 'maybe' (choose from 'auto', 'required', 'never')`, exit 2, `usage` |
| a manufacturing check's option refused (`--samples 0`, `--pull` beside `--candidates`, the other process's option) exited 1 | exits 2, `invalid_argument`, measuring nothing |
| a file that is not there: `cad urdf validate missing.urdf` exited 1 with an `invalid_target` finding, `cad stl snapshot missing.stl` 2, `cad kicad_pcb inspect` 2 with its own words | every type's every operation: `no such file: missing.urdf`, exit 2, `not_found`, before anything runs |
| a file an option names that is not there: `cad srdf validate robot.srdf --urdf missing.urdf` exited 1 with a `missing_urdf` finding; `--annotation`, `--measurements` and `--job` exited 2 as `invalid_argument`; a schematic's `--display missing.json` beside `--sheet` printed a traceback | `--urdf missing.urdf: no such file` (and so for each), exit 2, `not_found`, before anything runs; a `--display` that is not JSON, `invalid_argument` |
| a file of no type given to a type's command (`cad urdf validate robot.xml`) exited 1 with a finding | `robot.xml is not a urdf file: cad urdf takes .urdf`, exit 2, `wrong_type` |
| `cad viewer --json missing.step` (or `part.py`, or an id the engine does not hold) started the engine, then said `CAD Viewer: no CAD file at ...` on stderr, exit 1 | refused before the engine is asked, exit 2: `no such file: missing.step` (`not_found`); ``part.py is a model's script, not a CAD file: `cad run part.py` builds its models and prints each one's page`` (`wrong_type`); an id the engine does not hold, `not_found` |
| `cad run missing.py` made the program's environment, then printed the runner's traceback, exit 1 | `cad run: no such file: missing.py`, exit 2, before any environment is made (a `--directory` that is not there: `no such folder`) |
| `cad doctor --help` moved an earlier release's state folder into this one's, and any command's `--help` or `--json` run could say the telemetry notice (and record it as said) | help -- `-h`, `--help`, and now `cad help <command ...>` at any depth (`cad help step` printed the root's) -- does nothing but print the help; an answer in JSON says no notice, which waits for a run a person reads |
| a model's script where its document is wanted (`cad model inspect part.py`) was refused saying `python SCRIPT.py` prints the id, and the help said the same | ``part.py is a model's script, not a document id: `cad run part.py` builds its models and prints each one's id``, exit 2, `wrong_type`; the help says `cad run SCRIPT.py`; `cad serve part.py` says to run `cad run part.py` first |

### A command that destroys asks first

`cad uninstall` (and `--purge`), `cad delete`, `cad doctor --prune` and `cad server --rotate-token` say
their plan -- what they remove, how many -- and ask, `(y/N)`, at a terminal; anything but `y` or `yes`
changes nothing (exit 1, `declined`). Where no one can be asked -- an agent's shell, a pipe, `--json`, CI
-- they change nothing without `-y`/`--yes`: exit 2, `confirmation_required`, naming the command with
`--yes` (under `--json`, `"userActionRequired": true` and `"next"`). A script or an agent that runs one
of them on a person's word adds `--yes`. `cad delete --dry-run` lists what it would delete, and how
many. `cad setup` asks nothing, and the install command's `--uninstall` passes `--yes` itself.

| 0.10 | Now |
| --- | --- |
| `cad delete <id>` deleted at once | asks; `cad delete <id> --yes` where nothing can ask |
| `cad uninstall`, `cad uninstall --purge` took text-to-cad out at once | the plan, then asks; `--yes` where nothing can ask |
| `cad doctor --prune` removed at once | the list, then asks; `cad doctor --prune --yes` where nothing can ask |
| `cad server --rotate-token` replaced the token at once | asks; `--yes` where nothing can ask |

### What `cad doctor` reports, and what `cad update --dry-run` reads

`cad doctor` exited 4 for a CAD kernel that would not load and wrote that line (`kernel FAILED`) to
stderr, the rest of its report to stdout. It exits 1 for it now, with the whole report on stdout. Its
help no longer says it makes the CAD kernel environment, which it no longer does ([Setting up and
updating](#setting-up-and-updating)). Two forms are new: `cad doctor --check` is the report alone -- it
registers, writes and starts nothing, and says what `cad doctor` would write -- for a bug report or a
look; `--json` is the report as one document, `{"ok", "version", "checks": [{"name", "status",
"detail"}]}`. The report also says where each integration's operations run (`trimesh`, `kicad`).

`cad update --dry-run` printed this release's setup plan alone, never reading the version feed; it reads
it now (bounded, keeping nothing) and says first what an update would install: `cad update: would install
text-to-cad 0.11.2 (this is 0.11.0), ...`, or that it would set this release up again because it is the
newest or the feed cannot be reached; under `--json` the plan's document carries it as `update`
(`{"current", "feed", "release"}`).

## The manufacturing measurements (tier 1)

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

## `cad run` (tier 1)

0.10 ran every program in the CAD kernel environment, `cad[build123d]`, with the packages a script's
header or `--with` named beside it. `cad run` is `uv run` now, with cad pinned at your device's
release, and what it runs a program in follows the program:

- **The integrations come from its imports.** A program that imports `build123d` or `OCP` gets the
  build123d integration: the kernel and what comes with it (`ezdxf`, `pillow`, `matplotlib`,
  `shapely`, `bd_materials`). One that imports neither gets the library's core alone, with numpy. So a
  script that reads a DXF with `ezdxf`, or checks one with `cad.engine.export.dxf.validate_dxf_file`,
  as 0.10's dxf skill taught, fails with `No module named 'ezdxf'` until its header names the
  integration (`# dependencies = ["cad[build123d]"]`) or it imports build123d. The imports are read
  from the program and its local modules before it runs: one made at run time
  (`importlib.import_module` of a name it builds) is not seen.
- **A header that names cad decides them alone.** `# dependencies = ["cad"]` is the core, whatever the
  script imports: name what it uses, `cad[build123d]` (or `cad[trimesh]`, `cad[kicad]`). A header
  names cad's integrations, never its release: one that pins cad to another release than the
  device's (`cad==0.10.4`) is refused in one line.
- **It reads the uv project around the working folder.** The nearest folder up with a
  `pyproject.toml` that holds a `[project]` table is the program's project, as uv finds one, or the
  one `--project` names: its dependencies are installed beside cad, or the project itself, editable,
  when it is packaged (a `[build-system]`), and a `uv.lock` beside it is taken exactly. A project or
  lock that pins cad to another release is refused, as is a `pyproject.toml` that is not TOML: drop the
  pin (`cad[build123d]`, not `cad[build123d]==0.10.4`). A script with a header reads no project, as
  under `uv run`; `cad run --no-project` leaves the project out.
- **It follows your uv settings.** The uv settings in your environment that say what uv resolves
  (`UV_INDEX_URL`, `UV_EXTRA_INDEX_URL`, `UV_FIND_LINKS` and the like) and the uv configuration the
  run reads (a `uv.toml`, a project's `[tool.uv]`) give the program an environment of its own, beside
  the CAD kernel environment, resolved through them: an index that lacks cad or the kernel fails the
  run where 0.10 ran it in the kernel environment. Settings that say only how uv reaches an index
  (`UV_NATIVE_TLS`, `UV_HTTP_TIMEOUT` and the like) keep a run in the kernel environment.

## Setting up and updating

- **Automatic updates are on** (tier 3: your settings). The CAD server installs a newer release that
  breaks nothing (a patch release, before 1.0) by itself, in the background, and switches to it once
  nothing has run for a minute; 0.10 installed nothing until you asked. A 0.10 settings file says
  nothing of them, so they are on: `cad update auto off`, or unchecking Automatic updates in the menu
  under CAD's logo, turns them off, and `cad update auto` says whether they are on.
  `CAD_UPDATE_CHECK=0` in the server's environment turns them off too, as it turns off the version
  check. A release that may break something, this one among them, still waits for you.
- **The CAD kernel environment is made on first need** (tier 1). The install command (`cad setup`),
  `cad update` and `cad doctor` no longer make it: the first build, or the first view or operation
  that needs the kernel, makes it, from uv's cache where it holds it, else the network. An automatic
  update makes its release's before it switches. An image or a CI step that ran `cad doctor` to make
  it and then built offline makes it at its first build now: run one (`cad run model.py`) while the
  network is there.
- **`cad doctor --prune` removes more** (tier 1): every release folder too, but the current
  release's and the one before's; 0.10's left the release folders alone.
- **On Windows the command is `cad.exe`** (tier 1), with a Python of its own beside it
  (`cad-launcher`), in place of 0.10's batch file, `cad.cmd`. The install command or `cad update`
  writes it, and deletes `cad.cmd` at the write after, so nothing of yours moves (tier 3). `cad` alone
  runs it, as it ran `cad.cmd`; a script or a shortcut that named `cad.cmd` names `cad.exe`, or `cad`.

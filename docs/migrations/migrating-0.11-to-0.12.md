# Migrating from 0.11 to 0.12

This guide covers what changes for a person and for a program that talks to the cad server when cad
stops keeping a record of each document, and when every command and the library's functions become a verb,
then a file. A document is its file: cad keeps one small library file (the project folders, the files you
opened or pinned) and nothing else about a document. Nothing needs doing by hand: the first start of the new
release carries what it can and removes the rest; a command line of 0.11 says what to type now, and a script
of 0.11 keeps running, with a warning for each spelling it should change.

Each change names its tier of the compatibility law ([law 14](../../packages/cad/README.md#the-design-laws),
"Compatibility, by who pays for a break"), which says what a change of its kind keeps working.

## Your data (tier 3)

The first start reads the records 0.11 kept in the state folder (`documents/`, `recents/`) once,
writes `library.json` there, and removes them. `cad server status` says what it did in one line
while that server runs.

| 0.11 | Now |
| --- | --- |
| A CAD file you opened, with its pin | Carried: it is in Recents as before, pinned as before |
| A model a script built | Listed again, as its `.xbf`, the next time its script runs. Its pin and its opened time are not carried: 0.11's record of a model named no file |
| A model's id (from its script and function) | The id of its `.xbf`. An old id, in a link or a command, names nothing: `no document <id> is held`. Running the script prints the new id and link |
| A card's picture | Taken again the next time its page is open |
| A file that was already gone | Not carried |

## Documents and the server (tier 1)

- **A document lives while its file does.** With a model's `.xbf` gone, its id names nothing, and
  running its script writes the file again. The states `unsaved` and `detached` are gone, and no
  message names a command that builds a document again.
- **`cad delete` is removed.** It is answered as any unknown command is: it has no replacement to name. cad has
  no copy of a document to delete: to be rid of one, delete its file.
- **A run takes a model from its `.xbf` whenever the file holds the model's key**, whoever wrote
  the file last. 0.11 built again when the file was not the one the server had written.
- **A script moved to another folder is a new document**, with the id of its `.xbf` there. Moved
  together with its `.xbf`, it is taken from that file; moved alone, it is built.
- **The first run after the server restarts says no "was ..." line** under its report: what it
  compares against is kept in memory.
- **`cad server status`** lists `live`, `building`, `failed` and `held` documents, and no command
  beside any. With `--json`, the key `identity` is gone and `library` says what the first start
  carried.

## The command line (tier 1)

Every command is a verb, then a file, and the file's suffix says its type: `cad export SRC DST`, `cad inspect
FILE`, `cad snapshot FILE OUT.png`, `cad dfm FILE`, `cad fea FILE`. A verb a type lacks is refused in one line
naming the types that have it. A tool's own checks are its integration's: `cad kicad drc BOARD`, `cad kicad erc
SCHEMATIC`, `cad mujoco check MODEL.xml`. A model is given by its `.xbf`, which its run writes; the id a run
prints still works, and no text asks for it.

A spelling 0.11 had runs nothing now: it answers in one line with the one that does it, and exits 2
(`'cad xbf export' is 'cad export SRC DST' now; 'cad export --help' says its options`).

| 0.11 | 0.12 |
| --- | --- |
| `cad xbf export arm.xbf arm.step arm.stl`, `cad step export ...`, any `cad <type> export` | `cad export arm.xbf arm.step`, then `cad export arm.xbf arm.stl`: one destination a command, its format by its suffix |
| `cad <type> snapshot FILE OUT.png` | `cad snapshot FILE OUT.png` |
| `cad <type> inspect FILE [REF]` | `cad inspect FILE [REF]` |
| `cad <type> dfm FILE` | `cad dfm FILE` |
| `cad xbf interference FILE`, `cad step interference FILE` | `cad inspect FILE --interference` |
| `cad xbf ranges FILE`, `cad step ranges FILE` | `cad inspect FILE --ranges` |
| `cad xbf solve FILE`, `cad step solve FILE` | `cad fea FILE` |
| `cad urdf validate ROBOT.urdf`, `cad srdf validate ROBOT.srdf` | `cad inspect ROBOT.urdf`, `cad inspect ROBOT.srdf`: the same check, options and exit status |
| `cad kicad_pcb drc BOARD`, `cad kicad_sch erc SCHEMATIC` | `cad kicad drc BOARD`, `cad kicad erc SCHEMATIC` |
| `cad kicad_pcb export BOARD --to KIND -o DIR`, a schematic's the same | `cad export BOARD DIR --to KIND` |
| `cad model <operation> ...` | the verb above |
| `cad status`, `cad stop` | `cad server status`, `cad server stop` |
| bare `cad server` | `cad server start` (`--foreground` runs it in that process) |
| `cad orcaslicer presets\|complete` | none: OrcaSlicer's own command line slices a project saved from its app as it is |
| `cad serve DOC` | `cad viewer DOC`; `cad serve` is answered as any unknown command is |
| `cad export <id> arm.step` | `cad export arm.xbf arm.step` (the id still works) |

`cad export a.xbf b.xbf`, refused in 0.11, writes a copy of the document, its build closure with it.
`cad dfm` of a KiCad board or schematic is refused, naming `cad kicad drc` or `cad kicad erc`.

## The library (tier 2)

The verbs are the library's too, one to one with the command's, each taking a file, the handle a model's
call returns, or for `export` a shape: `cad.export(source, destination)`, `cad.inspect(source, ...)`
(`interference=True`, `ranges=True`), `cad.snapshot(source, out)`, `cad.dfm(source, ...)`,
`cad.fea(source, ...)`, and `cad.save(shape, "plate.xbf")`, a shape a program holds saved as a model.
KiCad's checks are `cad.kicad.drc(board)` and `cad.kicad.erc(schematic)`. A source with no destination is
refused in one line, as is a `.xbf` given to `cad.export` with a shape (`cad.save`'s) and any other file given
to `cad.save` (`cad.export`'s). A model's file is its `.xbf`, and the document type is `xbf`.

Each spelling of 0.11 still works, says once a process that it is deprecated and which spelling to use
(`CadDeprecationWarning`, at the line that spelled it), and keeps working for at least one minor release:

| 0.12 writes | Still works, with a warning |
| --- | --- |
| `cad.export("arm.xbf", "arm.glb")`, `cad.export(arm(), "arm.glb")` | `cad.xbf.export(...)`, `cad.step.export(...)` and every `cad.<type>.export` |
| `cad.snapshot(source, "arm.png")`, `cad.inspect(source)` | `cad.<type>.snapshot(...)`, `cad.<type>.inspect(...)` |
| `cad.inspect(source, interference=True, poses=[...], fits=[...])` | `cad.xbf.interference(...)`, `cad.step.interference(...)` |
| `cad.inspect(source, ranges=True)` | `cad.xbf.ranges(...)`, `cad.step.ranges(...)` |
| `cad.inspect("robot.urdf")`, `cad.inspect("robot.srdf", urdf=...)` | `cad.urdf.validate(...)`, `cad.srdf.validate(...)` |
| `cad.dfm(source, process="cnc", ...)` | `cad.<type>.dfm(...)` |
| `cad.fea(source, study=..., out=...)` | `cad.xbf.solve(...)`, `cad.step.solve(...)` |
| `cad.kicad.drc(board)`, `cad.kicad.erc(schematic)` | `cad.kicad_pcb.drc(...)`, `cad.kicad_sch.erc(...)` |
| `cad.export(board, "fab/gerbers", to="gerbers")` | `cad.kicad_pcb.export(board, to="gerbers", out="fab/gerbers")`, a schematic's the same |
| `cad.save(shape, "plate.xbf")` | `xbf(shape, "plate.xbf")`, `xbf(shape, name="plate")`, `model(shape, ...)` |
| `cad.export(shape, "plate.step")` | `step(shape, "plate.step")`, and `glb`, `stl`, `threemf` and `dxf` given a shape |
| `from cad import xbf`, `@xbf`, `@xbf("XBF/arm.xbf")` | `from cad import model` and `@model` (`cad.model is deprecated; use cad.xbf`) |
| `xbf.param(...)`, `xbf.read(path)` | the same on `model` |
| `cad.xbf.read(path)` | `cad.read_xbf(path)` |
| Kind `xbf` in `GET /api/v1/documents` and the routes `/api/v1/documents/xbf/<id>/...` | Kind `model` and `/api/v1/documents/model/<id>/...`: answered as the same documents |

The decorators, `xbf.read` and `xbf.param` are as they were, and warn of nothing. A model's `.xbf` is written by
every run that declares a model, at the decorator's path or, with none, `<name>.xbf` beside the script.

## How long an earlier spelling lasts

A `cad` command or option the skills used is replaced, not kept: its old spelling answers in one line with the
new one. A library spelling keeps working, with a warning, for at least one minor release. Nothing another
program calls (an installer, an earlier release's updater, an agent app's launch) is removed before its
replacement ships: `cad setup --engine-update`, `cad plugin update` and `cad plugin --refresh` run as they did.

## The viewer

- **Recents lists a model as its file** (`arm.xbf`), with the file's size and time, and a file that
  is gone is on no list.

## The HTTP API (tier 4)

| Route | Change |
| --- | --- |
| `GET /api/v1/documents` rows | `record` is always `file`; a model's row has `path` its `.xbf`, `name` the file's name, `size` the file's. `script`, `rebuild`, `shown` and `file` are gone. A file that is gone is not listed |
| `GET /api/v1/documents/<id>` and every read by id | A 404 is `{"error", "hint"}`: no `state`, no `rebuild`. `entry.project` gains `folder` |
| `DELETE /api/v1/documents/<id>` | 405. `PATCH /api/v1/documents` with `remove` forgets a file's entry; `delete` is refused as an unknown action |
| `GET /api/v1/local/open-in`, `POST /api/v1/local/open` | A target offers the operating system's own handler only for the kinds listed for it (text, PDF, images, other CAD tools' files, cad's own formats but KiCad's), never for code, a model's script included (`default: false`), and on Linux only where `xdg-open` is installed. `POST` refuses what is not offered, and an app that cannot be started, with 400 (it was 500) |

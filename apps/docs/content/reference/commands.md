---
title: The cad command
description: An overview of the cad command line, grouped by what you do with it, with the pattern for document types and the one integration operation.
---

`cad` is the command your agent runs, and you can run it yourself. The install command writes it at `~/.local/bin/cad` (on Windows, `%USERPROFILE%\.local\bin\cad.exe`). It is a thin front door: each command runs the one text-to-cad server on your computer, which keeps its workers warm between calls.

`cad --help` lists every command, document type and integration operation. `cad <type> --help` lists a type's operations, and `cad <type> <operation> --help` and `cad <command> --help` list a command's options. This page is an overview, not the full list.

## Set-up and updates

| Command | What it does |
| --- | --- |
| `cad setup` | Sets up text-to-cad in every agent app on your computer, as this release. The install command runs it. |
| `cad update` | Installs the newest release and sets it up in every agent app. `--dry-run` says what it would do and changes nothing. |
| `cad update auto` | Shows, or with `on` or `off` changes, automatic updates. |
| `cad uninstall` | Takes text-to-cad out of every agent app. `--purge` removes its state and cache folders too. |
| `cad doctor` | Sets the server up and reports what your computer runs. `--check` only reports and changes nothing, which is what a bug report wants. |
| `cad plugin` | Writes the plugin folder every agent app is pointed at, and prints its path. |
| `cad telemetry` | Shows, or with `on` or `off` changes, the usage stats and crash reports text-to-cad sends. |

Commands that remove things ask first, with a `(y/N)` in a terminal, or take `--yes`. `--only` limits `cad setup`, `cad update` and `cad uninstall` to the apps you name. [Installing by hand](/docs/install) says what each of these does to each app.

## The server

One server runs for your installation: the first run starts it, and every command and the viewer go through it.

| Command | What it does |
| --- | --- |
| `cad status` | Shows the server's workers and what it serves. It starts none. |
| `cad stop` | Stops the server. |
| `cad server` | Runs the server in this process. `--rotate-token` replaces the page token, which retires every viewer link made before. |
| `cad serve` | Serves a document over HTTP and prints its page's URL. |

## Running and viewing

| Command | What it does |
| --- | --- |
| `cad run` | Runs a Python script as `uv run` does, with text-to-cad at your release and the integrations the script imports. This is how a model builds. |
| `cad viewer` | Opens the [CAD Viewer](/docs/guides/cad-viewer). It takes files to open, `--no-open` and `--json`. |
| `cad delete` | Deletes documents: the record, the cached document and the server's copy. Never a file of yours. `--dry-run` and `--yes` are available. |
| `cad requirement` | Prints the exact requirement that installs this release's `cad`, for a Python program of your own. `--json` prints it as JSON. |

Build a model with `cad run`:

```bash
cad run src/bracket.py
```

## Document types

A document type is a kind of file text-to-cad builds, shows or checks, such as a model, a STEP file or a KiCad board. Each one has operations, with the same pattern:

```text
cad <document_type> <operation> <file>
```

A `model` is a model the server holds, named by its id. Every other type takes a file. Some real examples:

```bash
cad model export "$ID" STEP/bracket.step STL/bracket.stl
cad step snapshot vendor/arm.step tmp/arm.png --camera right
cad urdf validate description/arm.urdf
cad model dfm "$ID" --process cnc
cad kicad_pcb drc board.kicad_pcb
```

The operations are `export`, `snapshot`, `inspect`, `dfm` (a manufacturing check), `interference`, `solve`, `ranges`, `drc`, `erc` and `validate`, and each type has the ones that make sense for it. A file of another type is refused by name. A check prints its findings, and `--json` prints them as one JSON document.

## Integrations

An integration is a tool text-to-cad runs for you. For a file of its tool's own that is not a document type, such as a MuJoCo model, it has one operation, `check`, with the pattern `cad <integration> <operation> <file>`:

```bash
cad mujoco check robot.xml
```

`--strict` makes warnings fail the check. The [MuJoCo page](/docs/integrations/mujoco) has the detail.

## Operations by document type

Each document type's page lists its operations. See [document types](/docs/document-types).

# Setup and troubleshooting

Read this for first-time setup, a missing command, or a version/connection error.
`cadgen` means the versioned CLI defined in this skill's `SKILL.md`.

## Install, update or find the CLI

The plugin's MCP startup normally downloads cadgen and registers the CLI. To install
or update text-to-cad on this computer, run its install command. It installs uv if it
is missing, then cadgen (the engine, the `cadgen` command and the MCP server) for
every agent app on the computer, and replaces an older engine; run again, it updates
them all:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. Restart
the agent app afterwards.

To register exactly this skill's release without changing any app (skills-only use,
or when the command says this release is not installed), run:

```bash
uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen doctor
```

It needs uv: the install command installs it, or follow uv's
[platform installation instructions](https://docs.astral.sh/uv/getting-started/installation/).
It downloads the pinned runtime, registers it, writes the CLI proxy and checks the
CAD kernel. It does not start an engine. Both commands download and write outside
the project: run them outside a sandbox that refuses either, or with that sandbox's
permission.

Use the explicit CLI path so the `cadgen` of an activated virtual environment cannot
shadow it:

- macOS/Linux: `~/.local/bin/cadgen +0.8.3`.
- Windows: `%USERPROFILE%\.local\bin\cadgen.cmd +0.8.3` (PowerShell: `$env:USERPROFILE`).
- If `CADGEN_LAUNCHER_DIR` moved the proxy, use `cadgen` or `cadgen.cmd` in that directory.

Keep that explicit version selection when appending verbs. `cadgen doctor <skill-dir>` checks
this skill's pin and the kernel and reports the selected engine. Each command's
`--help` lists its arguments.

## Run a model

Run model scripts with `cadgen run`:

```bash
cadgen run model.py                  # builds the models its __main__ calls
cadgen run --show-env model.py       # prints the folder of the environment it runs in
cadgen run --refresh model.py        # makes that environment again first (stop the engine first
                                     # if it still runs a worker there: `cadgen stop`)
```

It runs the script in a Python environment it makes for the script's project, so
nothing is installed in the project. The project is the nearest folder, the script's
own or one above it, with a `pyproject.toml`, `uv.lock` or `requirements.txt`; with
none, it is the script's folder. Declare what the models import in the project's
`requirements.txt`, in its `pyproject.toml` (a `[project]` table also installs the
project itself, editable), or in the script's inline metadata:

```python
# /// script
# dependencies = ["numpy"]
# ///
```

The environment holds those dependencies and the engine's own cadgen. uv makes it in
cadgen's cache folder (`envs/`); the project's own `.venv` is never touched. Its
Python is the one the project declares (`.python-version` or `requires-python`) when
that is 3.11 to 3.14, the versions OCP and build123d publish for, else the engine's.
The first run of a project downloads its dependencies, so it needs the network once;
later runs reuse the environment, which is made again when the declared dependencies,
the engine's release or the chosen Python change. A dependency that conflicts with
cadgen's own (build123d, OCP) fails in one line naming the conflict.

`cadgen run` starts the selected engine when none is running, then runs the script
with the environment's Python, and the engine builds its models in a warm worker of
that interpreter. Options go before the script; what follows the script is the
script's own. A first run downloads, writes cadgen's cache folder and may start the
engine: run it outside a sandbox that refuses any of these, or with its permission.

XML validation through `cadgen urdf|sdf|srdf validate` needs only the installed CLI,
not a project environment or running engine. Start an engine for viewing or snapshots.

## Your own Python environment

A test runner, a notebook, CI or a debugger runs models in an environment of its own
with cadgen installed: `uv pip install --python <python> cadgen==0.8.3`, `<python>`
being that environment's interpreter, or, for one command,
`uv run --with cadgen==0.8.3 pytest`. There a script runs as `python model.py`; it
attaches to the selected engine and never starts one. Its cadgen need not be the
engine's release ([compatibility](#engine-startup-and-selection)): the engine serves an
older one and says once, as its worker starts, that `uv pip install -U cadgen` there
updates it, and one newer than the engine says to update the engine with the install
command above.

## Engine startup and selection

With the CAD plugin, its MCP server starts or attaches to the engine and
advertises its release and port at initialization: use that port for `cadgen run` and
model scripts. Without the plugin, `cadgen run` starts the engine when none is
running. To start one yourself and keep it running (for viewing and snapshots, or for
scripts in your own environment), run it in a terminal of its own or in the background
from a shell that outlives the command, outside any sandbox that refuses listeners:

```bash
uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen server
```

With the CLI already registered, `cadgen server` does the same job; in the
background, for example
`nohup ~/.local/bin/cadgen +0.8.3 server > cadgen-server.log 2>&1 &`.

Clients select port 3245 by default; set `CADGEN_PORT` in both the server
and client environments to use another port (`cadgen server --port N` and
`cadgen run --port N` also select it). For GUI hosts, set it in the CAD MCP server's
`env` settings too; a terminal export alone does not configure the GUI server.

Client, engine and project worker need not share a cadgen release. They work
together when they speak the same protocol, the engine reads the document format
the worker writes, and both use the same CAD kernel line (OCP major.minor) on the
same OS and architecture; otherwise the failure names what differs and the fix.
Starting an engine (the MCP server, `cadgen server`, `cadgen run`) reuses a compatible
selected engine. An older cadgen's engine on the port, 0.8.0's and 0.8.1's included,
is retired once nothing is using it, and the newer engine takes the port; one still in
use is reported with its release and pid, and `cadgen stop` stops it. Starting fails
on any other listener and never changes ports. A script run by its own Python and the
CLI's document operations only attach; a missing or incompatible engine fails, with no
automatic startup or local fallback.

## Diagnose a failure

For version or connection conflicts, use this skill's directory and the Python the
model runs in: under `cadgen run`, the interpreter in the folder
`cadgen run --show-env model.py` prints (`bin/python`; `Scripts\python.exe` on
Windows), else your own environment's:

```bash
cadgen doctor --json --python <python> <skill-dir>
```

Omit `--python` when no model is involved, or omit `--json` for a text
project report. These diagnostic modes do not register, prune, start or stop
anything. They compare the CLI, skill, project and selected engine, and report
registered installations and discoverable provider configuration. Discovery is
bounded; cached plugins do not prove what an agent host has loaded. Use the
findings to update the side that is behind (the install command for the engine
and CLI, `uv pip install -U cadgen` for an environment of your own) or to configure
separate ports explicitly. Do not silently switch releases.

Under `cadgen run`, a `ModuleNotFoundError` names a package the project does not
declare: add it to `requirements.txt`, `pyproject.toml` or the script's inline
metadata, then run again. A first run that cannot reach the network stops before the
script runs; run it once where it can.

For installation or kernel-load problems, plain `cadgen doctor <skill-dir>` also
performs setup and checks the CAD kernel in a separate process.

A first launch downloads the runtime and may outlast the host's startup timeout.
The Codex plugin requests 300 seconds; Claude Code's `MCP_TIMEOUT` is in
milliseconds. Pre-download with the bootstrap doctor command, then restart the
host. If a command reports that the system denies the engine's folder, rerun it
with the sandbox's permission rather than repeating the refused call.

A model build cut off by the shell's timeout keeps running in the engine.
`cadgen status` reports its workers and documents; rerunning the same model call
waits for that build and replays it. Give a cold build a suitable shell timeout
or run it in the background.

## After changing dependencies

After changing what the project declares (`requirements.txt`, `pyproject.toml` or a
script's inline metadata), run the model again: `cadgen run` sees the change and
remakes the environment on its own (`--refresh` remakes it regardless; while the engine
still runs a worker in that environment, `cadgen run --refresh` refuses: `cadgen stop`
first).

A worker reads the installed packages once, when it starts. After installing,
upgrading or reinstalling packages in an environment of your own:

1. `cadgen stop` stops the selected engine, whoever started it.
2. Start it again: `cadgen server` as above, or, with the CAD plugin, its next CAD
   tool call starts it (a `python model.py` run only attaches).
3. Restart any long-lived Python process that calls cadgen, then run the model again.

Stop only the selected engine on your own machine, never one on a port another
person or project deliberately runs.

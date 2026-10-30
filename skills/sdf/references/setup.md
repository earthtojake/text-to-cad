# Setup and troubleshooting

Read this for first-time setup, an update, a missing `cadgen` command, or an
installation, kernel or engine error. `cadgen` means the command this skill's
`SKILL.md` defines, `cadgen +0.8.4`.

## Install or update text-to-cad

To install or update text-to-cad on this computer, run its install command. It
installs uv if it is missing, then sets up the plugin (for an agent without one, the
skills alone) in every agent app on the computer with each app's own commands,
registers the `cadgen` command, and stops an older release's engine that nothing is
using; run again, it updates them all and lists the apps to restart:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. Restart
the agent app afterwards. It downloads and writes outside the project: run it outside
a sandbox that refuses either, or with that sandbox's permission.

## Register this skill's release

If `cadgen` is not on your PATH, or it says 0.8.4 is not installed, run
`uvx --no-config --managed-python --python 3.14 --from cadgen==0.8.4 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command, makes the CAD kernel environment models run in and starts the engine.
With the CAD app's server running, nothing else needs the sandbox's permission: it starts
the engine and holds it. Without it, a sandboxed shell cannot start the engine; when a
command says no engine is running, run `cadgen server` outside the sandbox once.

The `cadgen` command lives in `~/.local/bin` (on Windows, `%USERPROFILE%\.local\bin`,
where it is run as `cadgen.cmd +0.8.4`); `CADGEN_LAUNCHER_DIR` moves the folder. A
project venv can put its own `cadgen` ahead of it on PATH, even when `~/.local/bin` is
on PATH. Run `~/.local/bin/cadgen +0.8.4 doctor` to diagnose
that case and use that full path for commands until PATH is corrected.

## Diagnose a failure

`cadgen doctor <skill-dir>` reports the installation in use, whether it is the one
this skill pins, whether the CAD kernel loads, and whether the engine is running,
starting it when none is; use it for installation or kernel load errors. Each
command's `--help` lists its flags.

The first launch downloads cadgen and may outlast a host's server start timeout
(Claude Code: 30 s by default, raised by setting `MCP_TIMEOUT` in milliseconds;
Codex: the plugin asks for 300 s); a restart resumes the download.

If a command ends with 'the system denies cadgen's local engine', this shell's
sandbox forbids the engine's folder itself: rerun it with the sandbox's permission
(in Codex, escalated permissions) rather than retrying.

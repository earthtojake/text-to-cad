# Setup and troubleshooting

Read this for first-time setup, an update, a missing `cad` command, or an
installation, kernel or server error. `cad` means the command this skill's
`SKILL.md` defines, `cad +0.10.0`.

## Install or update text-to-cad

To install or update text-to-cad on this computer, run its install command. It
installs uv if it is missing, then sets up the plugin (for an agent without one, the
skills alone) in every agent app on the computer with each app's own commands,
registers the `cad` command, and moves the computer's CAD server to that release;
run again, it updates them all and lists the apps to restart. The update button the
CAD Viewer and the CAD app show when a release is out, and `cad update`, do the
same:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. Restart
the agent app afterwards. It downloads and writes outside the project: run it outside
a sandbox that refuses either, or with that sandbox's permission.

## Register this skill's release

If `cad` is not on your PATH, or it says 0.10.0 is not installed, run
`uvx --no-config --managed-python --python 3.14 --from cad-server==0.10.0 cad doctor` once,
outside any sandbox or with its permission: it installs the server, registers it, writes the
`cad` command, makes the CAD kernel environment models run in and starts the server.
With the CAD app running, nothing else needs the sandbox's permission: it starts the
server and holds it. Without it, a sandboxed shell cannot start the server; when a
command says no engine server is running, run `cad server` outside the sandbox once.

The `cad` command lives in `~/.local/bin` (on Windows, `%USERPROFILE%\.local\bin`,
where it is run as `cad.cmd +0.10.0`); `CAD_LAUNCHER_DIR` moves the folder. A
project venv can put its own `cad` ahead of it on PATH, even when `~/.local/bin` is
on PATH. Run `~/.local/bin/cad +0.10.0 doctor` to diagnose
that case and use that full path for commands until PATH is corrected.

## Diagnose a failure

`cad doctor` reports the installation in use and the current one, the releases on
this computer and each agent app's plugin release, whether the CAD kernel loads, and
whether the server is running, starting it when none is; use it for installation or
kernel load errors. Each command's `--help` lists its flags.

The first launch downloads text-to-cad and may outlast a host's server start timeout
(Claude Code: 30 s by default, raised by setting `MCP_TIMEOUT` in milliseconds;
Codex: the plugin asks for 300 s); a restart resumes the download.

If a command ends with 'the system denies text-to-cad's local engine', this shell's
sandbox forbids the server's folder itself: rerun it with the sandbox's permission
(in Codex, escalated permissions) rather than retrying.

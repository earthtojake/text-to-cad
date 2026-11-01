# Migrating from text-to-cad 0.8 to 0.10

A model's code does not change: a project that builds on 0.8 builds on 0.10, and
`from cadgen import model` still works (`cadgen` is the library, `cad`, under its
earlier name). What changes is the names around it. What you do by hand, and nothing
more:

**1. Run the install command again**, then restart the apps it lists:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. It installs
0.10 in every agent app and the `cad` command, moves 0.8's state into 0.10's folder (step 5),
and stops 0.8's server on port 3245 when nothing is using it. An 0.8 server still in use
(an app's session on the 0.8 plugin, a page watching a model, a build) is left running, and
the installer says so: it keeps port 3245, and 0.10's server serves on the next free port
(3246), says so once, and keeps that port until 0.8's is gone: once the app is restarted,
run the stop command the installer names for it (0.8's own `cadgen stop`, by its path), or
restart your computer. The next time 0.10's server starts (after `cad stop`, an update or a
restart), it is back on 3245.

Each app's plugin now comes from a folder on your computer that the release writes,
`plugin` in the new state folder (step 5), rather than from GitHub: the installer takes out
the copy 0.8's put in each app -- Claude Code's and Codex's `earthtojake` catalog with its
plugin, Gemini's extension, Cursor's clone -- and puts the folder's in its place: a local
catalog, `texttocad` (`text-to-cad@texttocad`), in Claude Code and Codex, the folder
linked in Gemini, a copy of it in Cursor ([What each app gets](../install.md#what-each-app-gets)).
Codex no longer fetches the repository each time it starts, and no app updates its plugin by
itself. A plugin you installed by hand from GitHub goes the same way the next time the
installer runs.

**2. `cadgen` is `cad` in commands**, with the same verbs and options:
`cadgen export <id> part.step` is `cad export <id> part.step`, `~/.local/bin/cadgen` is
`~/.local/bin/cad` (on Windows `cad.cmd`), and a skill's
`uvx ... --from cadgen==0.8.4 cadgen doctor` is
`uvx --no-config --managed-python --python 3.14 --from cad-server==0.10.0 cad doctor`.
0.8's `cadgen` command finds nothing once its records have moved; `cad doctor --prune`
removes it.

**3. `CADGEN_*` is `CAD_*` in environments**, the rest of each name the same:
`CADGEN_TELEMETRY=0` is `CAD_TELEMETRY=0`, `CADGEN_ENGINE_PORT` is `CAD_ENGINE_PORT`,
`CADGEN_STATE_DIR` is `CAD_STATE_DIR`. 0.10 reads no `CADGEN_` name.

**4. A hand-installed MCP command line** -- an MCP config you wrote yourself, with
`uvx ... --from cadgen==0.8.4 cadgen mcp` -- is the CAD app's own package now:

```
uvx --no-config --managed-python --python 3.14 --from cad-mcp==0.10.0 cad-mcp
```

The server's key stays `cad`. The installer rewrites the Claude Desktop entry it wrote
([the whole entry](../install.md#claude-desktop-chat-tab)).

**5. The state and cache folders moved**, to names for text-to-cad:

| | 0.8 | 0.10 |
|---|---|---|
| State, macOS | `~/Library/Application Support/cadgen` | `~/Library/Application Support/texttocad` |
| State, Linux | `~/.local/state/cadgen` (`$XDG_STATE_HOME`) | `~/.local/state/texttocad` |
| State, Windows | `%LOCALAPPDATA%\cadgen-state` | `%LOCALAPPDATA%\texttocad-state` |
| Cache | `~/.cache/cadgen` (`$XDG_CACHE_HOME`; Windows `%LOCALAPPDATA%\cadgen`) | `~/.cache/texttocad` (Windows `%LOCALAPPDATA%\texttocad`) |

The installer moves into the new state folder, once, what 0.10 keeps: your settings (the
telemetry answer, so a no stays a no -- the old folder keeps a no too, for 0.8 while it
is still installed -- and the language), the installations' records, the
page token (your links keep working), the documents' records and Recents, and setup's
receipt. Recents is as it was. The cache does not move: a model in Recents opens again once
its script runs (`cad run model.py`), and the old cache folder can be deleted, as can the old
state folder once nothing of 0.8 runs. A `CAD_STATE_DIR` you set names a folder that moves
nowhere.

**6. Updates are by hand**: the update button in the CAD Viewer and the CAD app, `cad
update`, or the install command again. Nothing updates on its own.

**7. The engine's HTTP API is `/api/v1`**: a script that read the engine's port by hand reads
`GET /api/v1/server` for 0.8's `/__cad/server` and `/__cad/version`, a document by its id at
`/api/v1/documents/<id>` (its envelope, whose `api` names its kind's reads) for `/__cad/catalog`
and `/__cad/api/doc/<id>`, and the rest as the engine's README lists it (**Wire format**). A 0.8
page still open when the engine moves to 0.9 is reloaded by hand.

Installing the library into a Python of your own instead of the install command: it is
`cad` on PyPI now (`pip install 'cad[build123d]==0.10.0'`; pin it, the release you run), beside the
server, `cad-server`, and the CAD app's, `cad-mcp`; `cadgen` and `text-to-cad` install `cad` at the
same release (`cadgen[kernel]`, 0.8's spelling, as `cad[build123d]`).

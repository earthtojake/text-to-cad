# texttocad-server

The CAD server for text-to-cad, imported as `cad_server`: the computer's one daemon that builds, keeps and
serves CAD documents; the CAD Viewer and the CAD app's MCP endpoint on its listener; the environment the
CAD kernel runs in; the installations and the one that is current; and the command that runs and
installs them all.

Models are written against the library, `texttocad` (imported as `cad`), which the server imports without
its CAD kernel: the kernel lives in the environment the server makes for models and its own kernel
processes, `texttocad[build123d]` at the server's own release.

The mechanisms its laws constrain are [`src/cad_server/engine/README.md`](src/cad_server/engine/README.md).

## The shape of the package

```
src/cad_server/
  engine/                # the engine's server half: the daemon, its supervisor and the services it
                         #   declares (its workers, its render processes), its registry of documents,
                         #   the live models' book, the document cache, the verbs as commands
                         #   (cli), and the engine's README, the mechanisms the laws constrain
  cli/                   # the `cad` command: a module per command, each a shell over
                         #   the function or parser that does the work
  viewer/                # the engine's HTTP application (engine_app), launcher (main), routes
                         #   (http_app), files by absolute path (backend), a file's catalog row
                         #   (scanner), the explorer's reads (folders), the model library
                         #   every CAD view shares (recents), a STEP's and an .xbf's serve
                         #   by the engine and in-process document reads (documents), a DXF's
                         #   payload (drawings), a robot's (robots), Quick Edit's packets
                         #   (prompt_files)
  mcp/                   # the engine's MCP endpoint: its JSON-RPC vocabulary (protocol),
                         #   engine sessions (http), tools and launches (server), the agent
                         #   operations (operations), how a host presents CAD (host), open
                         #   views (views), sidebar views shared in memory (sidebar), the
                         #   viewer routes in-process (tunnel), the page (ui), and the CAD
                         #   Viewer link for a host that renders no MCP Apps (browser)
  robot_payload.py       # a robot description resolved for the viewer's page: its
                         #   articulation, its visuals in rest space, the facts a person
                         #   reads off it; held in memory
  drawing_payload.py     # a DXF flattened by ezdxf for the viewer's pane
  jobs.py                # the agent operations' and the viewer exports' admission, progress,
                         #   waiting and cancellation
  analytics.py           # telemetry: usage counts and crash reports, on by default once
                         #   a command has said so, never after a no
  settings.py            # the person's settings: settings.json in the state directory
  language.py            # the language the person chose for the CAD views
  updates.py             # the hourly version check, for a copy nothing else keeps current,
                         #   and the release an update moves to
  assets.py              # where the bundled runtime is
  _internal/             # the environment models run in (base: the installation's base,
                         #   texttocad[build123d], made by uv), the launch commands (launch), the
                         #   installations' registry, which one is current, and the proxy it
                         #   writes (installations: ~/.local/bin/cad, which the skills run as
                         #   `cad +<version>`; written by `cad doctor`, `cad setup` and a CAD
                         #   app's first registration), the proxy (proxy), the releases an update
                         #   installs (releases), the update the button starts (update) and its
                         #   switch (switch), the plugin folder every agent app is pointed at
                         #   (plugin), the agent apps setup reads and writes (providers),
                         #   what earlier releases left behind (leftovers), the daemon's entry
                         #   (engine_daemon) and what it is composed of (engine_host), the
                         #   server's observer of the engine and the telemetry sender, the
                         #   install channel, file locks (the state folder's one lock:
                         #   `file_lock.state`), the CLI derivation
  _runtime/              # BUILT: the CAD Viewer client, the CAD app page and the agent-app
                         #   plugin (its manifests and skills) -- produced when the wheel is
                         #   packaged, never committed, never edited
```

## Commands

`cad export`, `snapshot`, `serve`, `inspect`, `status`, `stop`, `delete` and `server` are the
engine's verbs (`snapshot` draws every file the viewer opens, a DXF or a robot among them);
`cad urdf|sdf|srdf validate` the validators; `cad doctor` the setup (the installation registered,
the `cad` command written, the CAD kernel environment made, the engine started; the releases on
disk, the current one, the engine's and each app's plugin's) and what earlier releases left behind
that nothing needs, which `cad doctor --prune` removes (`_internal/leftovers.py`: engine records of
an older format, the bytecode of installations no longer registered, cache folders no record names,
the launchers earlier releases published beside the `cad` command, 0.8's `cadgen` proxy among them;
none written in the last seven days); `cad run` a program in the CAD kernel environment (the base:
`_internal/base.py`), its own folder last on its path; `cad viewer` the engine page launcher;
`cad setup`, which the install command `curl -fsSL https://texttocad.dev/install.sh | sh` runs, sets
up or updates text-to-cad in every agent app it finds, each by its own command
(`_internal/providers.py`), installs its release's folder, makes the CAD kernel environment models
run in and moves the device's engine to its release; `cad update` runs the newest release's
`cad setup`, as the update button does; `cad uninstall` takes text-to-cad out; `cad plugin` writes
the plugin folder and prints its path; and `cad telemetry` the person's answer.

The plugin every agent app gets is one folder, `plugin` in the state folder, which the server writes
from its own copy of the plugin (`_runtime/plugin`: each host's manifest, its config for the CAD app's
server, and the skills, byte for byte as they were released) with every version this distribution's
(`_internal/plugin.py`). It is written again in place -- each file renamed over, never a symlink --
at a registration of the current installation, by `cad setup` before it points the apps at it, and by
the release left current after every switch of the engine (`cad plugin --refresh`). Each app takes it
the way it takes a local plugin (`_internal/providers.py`): a local catalog that Claude Code reads in
place and Codex copies, an extension Gemini CLI links, a copy in Cursor's local plugins folder, the
skills copied by the Skills CLI for the agents without a plugin. An update writes the folder for the
new release and brings the copies along; nothing updates by itself. A model builds by running its script: `cad run model.py`, or
`cad +<version> run model.py` through the `cad` command, which runs the current installation, else
the one registered last (`_internal/proxy.py`; a `+<version>` is taken off). The CAD app an agent
host starts is `cad-mcp`, of the `texttocad-mcp` distribution, which reaches this server.

The state folder is `texttocad` in the platform's place for state (`texttocad-state` on Windows),
the cache folder `texttocad` in its place for caches. On a computer an earlier release (0.8, named
cadgen) set up, `cad setup`, `cad doctor` and a registration move what this release keeps of the
earlier state folder into this one, each thing once and only where this one has none of it: the
settings, the installations' records, the engines' records with the page token, the documents'
records, Recents, the setup receipt and the install channels (`cad.engine.places.adopt`); the person's
telemetry no stays in the earlier folder too, for the earlier release while it is installed.

Coming from 0.7: cadgen 0.7.x kept a cache store, which can hold gigabytes, in its cache folder,
`~/.cache/cadgen` (macOS and Linux; `$XDG_CACHE_HOME/cadgen` when that is set),
`%LOCALAPPDATA%\cadgen` (Windows) or the folder `CAD_CACHE_DIR` named: its `objects/` and `index/`;
and state files only 0.7 writes in its state folder (its sidebar views, its snapshot browser's lock,
its viewer's log, its Recents log). No later release reads or writes them. Whether a 0.7 is still
installed cannot be told from here (0.7 never registered itself; it lives in uv's environments and
the agent apps' plugin configs), so they retire themselves: `cad doctor` looks for them in the
folders 0.7 used (or the ones `CAD_STATE_DIR` and `CAD_CACHE_DIR` name) and says they are there, with
their size and when they were last written, and `cad doctor --prune` removes them once nothing has
written them for seven days -- a 0.7 in use writes its store at every build -- or at once with
`--all-versions`, once no 0.7 is left in any agent app.

The viewer exposes `POST /__cad/clipboard` for explicit viewport PNG copies. It
uses the same host and custom-header POST gates as other mutation routes, limits
images to 20 MiB, and delegates native delivery to `viewer/clipboard.py`. It never
reads the clipboard. Unsupported desktop clipboard environments return an error.

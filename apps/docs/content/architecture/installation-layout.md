---
title: What is installed where
description: The folders, environments and command the install command puts on your computer, how an update moves them, and what uninstall leaves.
---

The install command (`curl -fsSL https://texttocad.dev/install.sh | sh`) installs uv if it is missing, then runs the newest release's `cad setup` through uvx. This page lists what that leaves on your computer; [Install](/docs/install) has the steps.

## The folders

text-to-cad keeps two folders of its own, plus the `cad` command:

| What | macOS | Linux | Windows |
| --- | --- | --- | --- |
| State folder | `~/Library/Application Support/cad` | `~/.local/state/cad` | `%USERPROFILE%\.local\state\cad` |
| Cache folder | `~/.cache/cad` | `~/.cache/cad` | `%USERPROFILE%\.cache\cad` |
| `cad` command | `~/.local/bin/cad` | `~/.local/bin/cad` | `%USERPROFILE%\.local\bin\cad.exe` |

The cache folder follows `$XDG_CACHE_HOME` when that is set, and `CAD_CACHE_DIR` moves it anywhere. On Windows both stay out of the local application data, which Windows virtualises for packaged apps such as the Claude desktop app. The server's door and lock live in a third folder only you can create: `cad-engine` in `$XDG_RUNTIME_DIR` or your own temporary folder, and on Windows `%USERPROFILE%\.local\state\cad-engine`.

## The state folder

Nothing in the state folder is geometry or source.

- `releases/<release>`: each installed release, its own environment made by uv. The current release and the one before are kept, so an update can go back.
- `installations/`: one record per registered installation, and `installations/current`, which names the release whose server your computer runs.
- `plugin`: the plugin every agent app is pointed at (manifests, CAD's server config and skills) at the current release; `cad plugin` prints its path.
- `settings.json`: your settings, such as your telemetry answer and whether automatic updates are on.
- `documents/<id>/document.json` and `recents`: one record per document the server built or opened, and the home's list of recent documents.
- `engines/`: the port the server keeps and your page token, `engines/token`, readable only by you.
- The install command's receipt of everything it changed, and `update.json` and `update.log` for the last update.

## The cache folder

The cache folder holds what can be made again:

- **The base environment**: the library with its CAD kernel, `cad[build123d]`, at the server's release, on the server's Python 3.14. Not made at install: the first model, or the first view that needs the kernel, makes it with uv. About 240 MB to download, 620 MB on disk.
- **Environments for `cad run`**: one for each distinct set of packages a script asks for, through its `# /// script` header, `--with`, or its project. Each is made once and kept for the runs after.
- **Integration environments**: `cad[kicad]` (about 100 MB to download, 340 MB on disk), `cad[trimesh]`, `cad[mujoco]` and `cad[coacd]` are each made the first time a command needs them, and work offline after that. A script importing Blender's `bpy` gets `cad[blender]`, on Python 3.13.
- `documents/`: the document cache, each model's document as last built, so a restart needs no build.
- `pycache/`: the bytecode the server's processes compile.
- `homes/`: private settings folders for tools such as Blender, so your own Blender setup stays out of a run.

See [environments](repo:skills/cad/references/environments.md) for how `cad run` chooses one, and [What a model runs in](/docs/install#what-a-model-runs-in) for a Python of your own.

## The `cad` command and the agent apps

`~/.local/bin/cad` runs the current installation, so every skill and terminal reaches the same release. `cad setup` and `cad doctor` write it, as does a CAD app's server as it starts. On Windows the Python `cad.exe` runs by, `cad-launcher`, sits beside it.

Each agent app takes the `plugin` folder the way it takes a local plugin: Claude Code and Gemini read it in place, while Codex, Cursor and the agents with skills alone get a copy. Claude Desktop gets CAD's server in its own config file, and the install command keeps a `.bak` of that file. Details: [What each app gets](/docs/install#what-each-app-gets).

## How an update moves the server

An update (the update button, `cad update`, the install command run again, or an automatic update) works in this order:

1. It installs the new release in `releases/<release>`. It makes no environment, except that an automatic update makes its base first.
2. It writes the `plugin` folder again from that release and brings the apps' copies along.
3. The running server finishes what it is doing and stops, `installations/current` moves to the new release, and its server starts on the same port with the same token. Open pages and cards keep their links and reload.
4. If the new server does not answer, `current` goes back and the release before starts again.

Older release folders go at the next switch, and older releases' environments as new ones are made. `cad doctor` lists the releases; `cad doctor --prune` removes release folders other than the current one and the one before, and environments no model has used for a week. [Updates](/docs/install#updates) covers automatic updates and how to turn them off.

## What uninstall leaves

`cad uninstall`, or the install command with `--uninstall`, takes back what the receipt records, removes the `cad` command and stops the server. Without `--purge` it leaves:

- in the state folder: `settings.json`, `versions.json`, the lock files, an empty `installations` folder, and your documents' records and Recents;
- the whole cache folder: environments, cached documents and bytecode.

`--purge` removes both folders. Neither touches uv or uv's own cache.

## Read more

- [Checking what your computer runs](/docs/install#checking-what-your-computer-runs), [Architecture overview](/docs/architecture) and [The engine](/docs/architecture/engine).
- [CONTRIBUTING.md, "Development dependencies"](repo:CONTRIBUTING.md#development-dependencies): how a checkout differs.
- [docs/install.md](repo:docs/install.md): the source for this page.

---
name: setup
description: Set up the CAD plugin after installing it - install uv if it is missing (with the user's approval) and prepare the pinned cadgen runtime that CAD's viewer runs on, so CAD opens in the sidebar and in thread tabs. Use right after the CAD plugin is installed or updated, or when CAD's viewer did not start.
---

# Set up CAD

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

CAD's viewer is a local server, `cadgen mcp`, that the agent app starts with
`uvx` for each thread, offline, from a runtime pinned to this plugin's version
(the `cadgen==` line in this skill's `requirements.txt`). This skill makes sure
that runtime is on the machine. It changes nothing in the user's projects.

## Steps

1. Check for uv:

   ```bash
   uv --version
   ```

   If it is missing, ask the user before installing it. The official installer
   is `curl -LsSf https://astral.sh/uv/install.sh | sh` on macOS and Linux and
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   on Windows; `brew install uv` also works.

2. From this skill's directory, prepare the pinned runtime. The first run
   downloads cadgen and its CAD kernel once; later runs are instant:

   ```bash
   uvx --no-config --from "$(grep -m1 '^cadgen' requirements.txt)" cadgen doctor
   ```

   It prints the cadgen version the plugin pins.

3. Check that the viewer's server starts the way the app starts it, offline:

   ```bash
   uvx --no-config --offline --from "$(grep -m1 '^cadgen' requirements.txt)" cadgen mcp --help
   ```

4. Tell the user to quit and reopen the app. Servers start with the app, so the
   viewer appears after a restart: **CAD** in the sidebar, and **CAD** as a tab
   in each thread.

## When the viewer does not start

- `uvx` not found: uv's installer puts it in `~/.local/bin`; the app reads the
  login shell's `PATH`, so open a new shell to confirm `uvx --version`, then
  restart the app.
- A download or resolution error in step 2: rerun it with a working network;
  step 3 must then succeed without one.
- After a plugin update, run steps 2-4 again: each version runs its own pinned
  runtime, and threads started before the update keep theirs until the restart.

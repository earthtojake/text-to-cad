---
name: cad-mcp-setup
description: Check that the CAD plugin can start after it is installed or updated - confirm uv is installed, point the user to uv's official installation guide when it is not, and tell them when to restart the app so CAD opens in the sidebar and in thread tabs. Use right after the CAD plugin is installed or updated, or when CAD's viewer did not start.
---

# Set up CAD

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

CAD's viewer is a local server that the agent app starts with `uvx`, from the
command in this plugin's MCP config, pinned to the plugin's version. The app
fetches that pinned runtime from PyPI the first time the server starts after an
install or an update, so that start needs a network connection. This skill only
checks and explains: it installs nothing, downloads nothing, and changes nothing
in the user's projects.

## Steps

1. Check for uv:

   ```bash
   uv --version
   ```

2. If uv is missing, tell the user CAD needs it, and give them uv's official
   installation guide to install it themselves:
   <https://docs.astral.sh/uv/getting-started/installation/>.

3. Tell the user to quit and reopen the app. Servers start with the app, so the
   viewer appears after a restart: **CAD** in the sidebar, and **CAD** as a tab
   in each thread.

## When the viewer does not start

- `uv` or `uvx` not found after installing uv: the app reads the login shell's
  `PATH`, so confirm `uv --version` in a new shell, then restart the app.
- No network on the first start after an install or an update: the pinned
  runtime could not be fetched. Restart the app once online.
- After a plugin update, restart the app: the first start fetches the new pinned
  runtime, which can take a few minutes on a slow connection. Threads started
  before the update keep the old one until the restart.

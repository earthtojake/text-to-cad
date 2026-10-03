---
name: cad-mcp-setup
description: Check that the CAD app can start after the CAD plugin is installed or updated, in Codex, Claude Code, Claude Desktop or another agent app - confirm uv is installed, point the user to uv's official installation guide when it is not, and tell them how CAD appears in their app and when to restart it. Use right after the CAD plugin is installed or updated, or when CAD's viewer did not start.
license: MIT
---

# Set up CAD

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

CAD's viewer is a local server that the agent app starts with `uvx`, pinned to
one release of cadgen. The app downloads that release from PyPI the first time
the server starts after an install or an update, so that start needs a network
connection. The plugin's skills use the same pinned command, so they
share that one installation and its warm build daemon. This skill only checks and explains: it installs nothing,
downloads nothing, and changes nothing in the user's projects.

## Steps

1. Check for uv:

   ```bash
   uv --version
   ```

2. If uv is missing, tell the user CAD needs it, and give them uv's official
   installation guide to install it themselves:
   <https://docs.astral.sh/uv/getting-started/installation/>.

3. Tell the user how CAD appears in their app:

   - **Codex**: quit and reopen Codex. **CAD** then appears in the sidebar and
     as a tab in each thread.
   - **Claude Code**: the plugin starts CAD with each session; `/mcp` shows
     whether it is connected. Where Claude Code can show app views, CAD shows
     models as viewer cards; otherwise, as in a terminal, it answers with a link
     that opens the model in the CAD Viewer in the browser.
   - **Claude Desktop**: the plugin doesn't reach Claude Desktop. The user adds
     CAD's server to its config (Settings > Developer > Edit Config), as the
     text-to-cad README shows, and restarts it. CAD then shows models as viewer
     cards in the chat.
   - **Cursor**: the plugin starts CAD; after a restart CAD shows models as
     viewer cards in the chat. Cursor also loads the Claude Code plugin, so one
     install covers both.
   - **Grok Build, Gemini CLI**: the plugin starts CAD, but these apps show tool
     results as text, so CAD answers with a link that opens the model in the CAD
     Viewer in the browser.
   - **Another app that shows MCP Apps** (VS Code, Goose): CAD shows models as
     viewer cards in the chat once the app restarts.

## When the viewer does not start

- `uv` or `uvx` not found after installing uv: the app reads the login shell's
  `PATH`, so confirm `uv --version` in a new shell, then restart the app. In
  Claude Desktop's config, the full path to `uvx` (`which uvx`) also works.
- No network on the first start after an install or an update: the pinned
  runtime could not be fetched. Restart the app once online.
- Claude Code gives a server 30 seconds to start, and the first start downloads
  CAD's libraries (about 1 GB unpacked). On a slow connection, start Claude Code
  once with `MCP_TIMEOUT=300000 claude` so the download can finish.
- After a plugin update, restart the app: the first start fetches the new pinned
  runtime, which can take a few minutes on a slow connection. In Codex, threads
  started before the update keep the old one until the restart.

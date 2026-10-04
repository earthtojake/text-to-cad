---
name: cad-setup
description: Set up and update text-to-cad. Check that the CAD app can start after the CAD plugin is installed or updated (uv installed, how CAD appears in the agent app, when to restart), and update text-to-cad when the user asks or CAD says a newer release is out ("Update text-to-cad to 0.9.0"), in Codex, Claude Code, Claude Desktop, Cursor, Grok Build, Gemini CLI or a Skills CLI install. Use right after the CAD plugin is installed or updated, when CAD's viewer did not start, or when asked to update text-to-cad.
license: MIT
---

# Set up and update CAD

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

CAD's viewer is a local server that the agent app starts with `uvx`, pinned to
one release of cadgen. The app downloads that release from PyPI the first time
the server starts after an install or an update, so that start needs a network
connection. The plugin's skills use the same pinned command, so they
share that one installation and its warm build daemon. Setting up only checks and explains: it installs nothing,
downloads nothing, and changes nothing in the user's projects. Updating runs the
agent app's own update commands, and only when the user asked for the update.

## Set up

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

## Update

CAD says when a newer release is out, to a copy installed by hand (from GitHub,
or with the Skills CLI): a blue update button in its viewer, a line with a tool
result, or a line in a command's output. Its prompt is worded like the install
message: "Update text-to-cad to 0.9.0 from
https://github.com/earthtojake/text-to-cad".

1. **Find how text-to-cad was installed**, by asking the agent app with its own
   list command:

   | App | Command | Installed from GitHub when | A store's copy when |
   | --- | --- | --- | --- |
   | Claude Code | `claude plugin list --json` | the id is `text-to-cad@earthtojake` | the id names another marketplace (the Claude directory) |
   | Codex | `codex plugin list --json` | the marketplace is `earthtojake` | another marketplace (the OpenAI directory) |
   | Cursor | look for `~/.cursor/plugins/local/text-to-cad` | that folder exists | Cursor's plugin settings list it, with no such folder |
   | Grok Build | `grok plugin list --json` | its `source` is `earthtojake/text-to-cad` | — |
   | Gemini CLI | `gemini extensions list` | always | — |

   Claude Desktop's chat has no plugin: CAD is the server in its config. When no
   plugin turns up, the skills came from the Skills CLI (`npx skills`).

2. **Installed from GitHub** (or by hand): update with the app's own command,
   then restart the app. Its first start downloads the new release.

   - Claude Code: `claude plugin marketplace update earthtojake`, then
     `claude plugin update text-to-cad@earthtojake`.
   - Codex: `codex plugin marketplace upgrade earthtojake`.
   - Cursor: `git -C ~/.cursor/plugins/local/text-to-cad pull`.
   - Grok Build: `grok plugin update text-to-cad`.
   - Gemini CLI: `gemini extensions update text-to-cad`.
   - Claude Desktop: in its config (Settings > Developer > Edit Config), change
     the version in `cadgen==…` in the `cad` server's `args` to the new release.
     If you cannot edit the file, give the user that one change to make.
   - Skills CLI: `npx skills add earthtojake/text-to-cad`. `add`, not
     `update`: it also installs skills that are new in the release. The new
     skills pin the new release, which uv downloads the first time they run.

3. **A store's copy** (the Claude directory, the OpenAI directory, the Cursor
   Marketplace) is updated by its store, once the release passes the store's
   review: there is nothing to run, and CAD never offers it an update. Tell the
   user the store will update it, and offer to switch to a copy installed from
   GitHub, which hears of each release as soon as it is out. Switch only if they
   say yes, and ask before disabling or uninstalling anything:

   - Claude Code: `claude plugin marketplace add earthtojake/text-to-cad`, then
     `claude plugin install text-to-cad@earthtojake`. Claude Code loads that copy
     in place of the directory's; nothing needs uninstalling.
   - Codex: disable the directory's copy (in Codex's plugin list), then
     `codex plugin marketplace add earthtojake/text-to-cad` and
     `codex plugin add text-to-cad@earthtojake`.
   - Cursor: uninstall the Marketplace copy in Cursor's plugin settings (Cursor
     prefers it over a local copy), then
     `git clone --depth 1 --branch plugin https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad`.

   A copy installed from GitHub does not update by itself: when CAD says a newer
   release is out, update it as in step 2.

4. Tell the user to restart the app, and that its first start downloads the new
   release.

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

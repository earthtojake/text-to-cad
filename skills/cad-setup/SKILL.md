---
name: cad-setup
description: Set up and update text-to-cad. After the CAD plugin is installed or updated, check that CAD can start (uv installed, how CAD appears in the agent app, when to restart); update text-to-cad when the user asks or CAD says a newer release is out ("Update text-to-cad to 0.9.0"). Covers Codex, Claude Code, Claude Desktop, Cursor, Grok Build, Gemini CLI and a Skills CLI install. Use right after the CAD plugin is installed or updated, when CAD's viewer did not start, or when asked to update text-to-cad.
license: MIT
---

# Set up and update CAD

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

CAD is a local server the agent app starts with `uvx`, pinned to one release of
cadgen; the plugin's skills run the same pinned command, so they share one
installation and its build daemon. The first start after an install or an
update downloads that release from PyPI, so it needs a network connection.

Two rules:

- **Setting up only checks and explains.** It installs nothing, downloads
  nothing and changes nothing in the user's projects.
- **Update only when the user asked**, and only with the agent app's own
  commands.

## Set up

1. Run `uv --version`. If uv is missing, tell the user CAD needs it and give
   them uv's official installation guide to install it themselves:
   <https://docs.astral.sh/uv/getting-started/installation/>.
2. Tell the user how CAD appears in their app:

   | App | How CAD appears |
   | --- | --- |
   | Codex | After quitting and reopening Codex: **CAD** in the sidebar, and a tab in each thread. |
   | Claude Code | It starts with each session (`/mcp` shows it). Where Claude Code shows app views, models open as viewer cards; in a terminal, as a link to the CAD Viewer in the browser. |
   | Claude Desktop | The plugin does not reach it: the user adds CAD's server to its config (Settings > Developer > Edit Config), as the text-to-cad README shows, and restarts it. Models then open as viewer cards in the chat. |
   | Cursor | After a restart, models open as viewer cards in the chat. Cursor also loads the Claude Code plugin, so one install covers both. |
   | Grok Build, Gemini CLI | These show tool results as text, so CAD answers with a link to the model in the CAD Viewer in the browser. |
   | Another MCP Apps host (VS Code, Goose) | After a restart, models open as viewer cards in the chat. |

## Update

CAD says when a newer release is out (a blue update button in its viewer, or a
line with a tool result) to a copy installed from the text-to-cad repository on
GitHub, or with the Skills CLI. Its prompt reads like the install message:
"Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad".

1. **Find where this copy came from**, with the app's own list command:

   | App | Command | From GitHub when | A store's copy when |
   | --- | --- | --- | --- |
   | Claude Code | `claude plugin list --json` | the id is `text-to-cad@earthtojake` | the id names another marketplace (the Claude directory) |
   | Codex | `codex plugin list --json` | the marketplace is `earthtojake` | another marketplace (the OpenAI directory) |
   | Cursor | look for `~/.cursor/plugins/local/text-to-cad` | that folder exists | Cursor's plugin settings list it, with no such folder |
   | Grok Build | `grok plugin list --json` | its `source` is `earthtojake/text-to-cad` | — |
   | Gemini CLI | `gemini extensions list` | always | — |

   Claude Desktop's chat has no plugin: CAD is the server in its config. With no
   plugin anywhere, the skills came from the Skills CLI (`npx skills`).

2. **From GitHub:** run the app's update command, then tell the user to restart
   the app. Its first start downloads the new release.

   | App | Update |
   | --- | --- |
   | Claude Code | `claude plugin marketplace update earthtojake`, then `claude plugin update text-to-cad@earthtojake` |
   | Codex | `codex plugin marketplace upgrade earthtojake` |
   | Cursor | `git -C ~/.cursor/plugins/local/text-to-cad pull` |
   | Grok Build | `grok plugin update text-to-cad` |
   | Gemini CLI | `gemini extensions update text-to-cad` |
   | Claude Desktop | In its config, change the version in `cadgen==…` in the `cad` server's `args` to the new release; if you cannot edit the file, give the user that one change to make. |
   | Skills CLI | `npx skills add earthtojake/text-to-cad` (`add`, not `update`: it also installs the release's new skills) |

3. **A store's copy** (the Claude directory, the OpenAI directory, the Cursor
   Marketplace) is updated by its store once the release passes its review, and
   CAD never offers it an update: there is nothing to run. Tell the user so. If
   they want each release as soon as it is out, offer to install the copy from
   GitHub instead; do it only if they say yes, and ask before disabling or
   uninstalling anything:

   - Claude Code: `claude plugin marketplace add earthtojake/text-to-cad`, then
     `claude plugin install text-to-cad@earthtojake`. It loads in place of the
     directory's copy, so nothing needs uninstalling.
   - Codex: disable the directory's copy in Codex's plugin list, then
     `codex plugin marketplace add earthtojake/text-to-cad` and
     `codex plugin add text-to-cad@earthtojake`.
   - Cursor: uninstall the Marketplace copy in Cursor's plugin settings (Cursor
     prefers it over a local one), then
     `git clone --depth 1 --branch plugin https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad`.

## When CAD does not start

- **`uv` or `uvx` not found after installing uv:** the app reads the login
  shell's `PATH`. Confirm `uv --version` in a new shell, then restart the app.
  In Claude Desktop's config, the full path to `uvx` (`which uvx`) also works.
- **No network on the first start** after an install or an update: the pinned
  release could not be downloaded. Restart the app once online.
- **Claude Code on a slow connection:** it gives a server 30 seconds to start,
  and the first start downloads CAD's libraries (about 1 GB unpacked). Start it
  once with `MCP_TIMEOUT=300000 claude` so the download can finish.
- **After an update**, restart the app: in Codex, threads started before the
  update keep the old release until then.

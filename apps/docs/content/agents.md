---
title: Supported agents
description: Which agent apps text-to-cad works with, what each one gets, and where the CAD Viewer appears in each.
---

text-to-cad works with any agent that supports plugins or skills. Claude Code, Codex and Cursor are the first-class integrations: a change to the plugin or the skills is tested in each of them before it ships. Claude Desktop, Grok Build and Gemini CLI have their own set-up. Other agents get the skills alone.

The [install command](/docs/install) finds the apps on your computer and sets each one up with its own commands. This page says what each app ends up with. The per-app commands, updates and reinstalls are on the [install page](/docs/install).

## What each app gets

| App | What it gets | Where the viewer appears |
| --- | --- | --- |
| [Claude Code](/docs/install#claude-code) | the skills | a link, in your browser or the desktop app's browser pane |
| [Claude Desktop](/docs/install#claude-desktop) | CAD's server, for the viewer cards | cards in the Chat tab and in the Code tab |
| [Codex](/docs/install#codex) | the plugin: the skills and CAD's server | tabs in the Codex app |
| [Cursor](/docs/install#cursor) | the plugin: the skills and CAD's server | cards in the chat |
| [Grok Build](/docs/install#grok-build) | the plugin: the skills and CAD's server | a link |
| [Gemini](/docs/install#gemini) | an extension: the skills and CAD's server | a link |
| [Other agents](/docs/install#other-agents) | the skills alone, through the Skills CLI | a link |

All of them run the same `cad` command and the same server on your computer, so a model built from one app is the model another app shows.

## Where the viewer appears

How you see a model depends on what the app can draw.

- **Claude Code** gets the skills but starts no CAD server. Asking it to show a model gives you a link that opens in your browser. In Claude Desktop's Code tab, where Claude Code runs, the cards come from Claude Desktop's own server.
- **Claude Desktop** draws a viewer card in the conversation each time the agent shows a model, in its Chat tab and in its Code tab. A newer card retires the older ones, which keep a still of their last frame. It reads its config when it starts, so restart it after the first set-up.
- **Codex** in its app has **CAD** in the sidebar, a **CAD** tab beside each thread that the agent drives, and *Open with CAD* for model files. The Codex terminal shows no tabs, so the agent gives you a link.
- **Cursor** draws viewer cards inline in the chat. It also loads the plugin installed with Claude Code.
- **Grok Build and Gemini CLI** show tool results as text, so the agent gives you a CAD Viewer link.
- **Other agents** open models in the CAD Viewer in your browser.

The [CAD Viewer](/docs/guides/cad-viewer) is the same in a card, a tab and the browser. [Viewer and CAD app](/docs/architecture/viewer-and-cad-app) explains how the hosts differ.

## The agents the skills reach

For an agent without a plugin, the install command copies the skills with the Skills CLI, which needs Node. It does this for GitHub Copilot (including VS Code's agent), Windsurf, Cline, Amp, Antigravity, OpenClaw, Droid, Goose, Kilo Code, Kiro CLI, Hermes Agent, OpenCode, Roo Code, Trae and Zed, when they are installed. For any other agent, the [install page](/docs/install#other-agents) has the Skills CLI command to run yourself.

Without a plugin there is no CAD server, so the skills open models in the CAD Viewer in your browser. If your agent has no plugin yet, you can [request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

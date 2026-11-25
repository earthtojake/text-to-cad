---
title: Supported agents
description: Which agent apps text-to-cad works with, what each one gets, and where the viewer appears in each.
---

text-to-cad works with any agent that supports plugins or skills. Claude Code, Codex and Cursor are the first-class integrations: a change to the plugin or the skills is tested in each of them before it ships. Every app gets the skills. The Codex app also gets the viewer inside the app, as tabs.

The [install command](/docs/install) finds the apps on your computer and installs the plugin in each one with that app's own command. This page says what each app ends up with. The per-app commands, updating and removing are on the [install page](/docs/install).

## What each app gets

| App | What it gets | Where the viewer appears |
| --- | --- | --- |
| [Claude Code](/docs/install#claude-code) | the plugin: the skills | its browser pane, or a link for your browser |
| [Codex](/docs/install#codex) | the plugin: the skills and, in the Codex app, CAD's server | a CAD tab beside the thread in the Codex app; a link in the terminal |
| [Cursor](/docs/install#cursor) | the plugin: the skills | its browser |
| [Gemini CLI](/docs/install#gemini-cli) | an extension: the skills | a link |
| [Grok Build](/docs/install#grok-build) | the plugin: the skills | a link |
| [Antigravity](/docs/install#antigravity), [Devin CLI](/docs/install#devin-cli), [Factory Droid](/docs/install#factory-droid), [GitHub Copilot CLI](/docs/install#github-copilot-cli), [Kimi Code](/docs/install#kimi-code), [Muse](/docs/install#muse), [Pi](/docs/install#pi), [Qwen Code](/docs/install#qwen-code) | the plugin: the skills | a link |
| [Other agents](/docs/install#other-agents) | the skills alone, copied into the agent's skills folder | a link |

All of them run the same `cad` command and the same server on your computer, so a model built from one app is the model another app shows.

## Where the viewer appears

How you see a model depends on what the app can show.

- **Claude Code** opens the model in its browser pane, or gives you a link that opens in your browser. Claude Desktop's Code tab runs Claude Code and uses the same plugin.
- **Codex** in its app has **CAD** in the sidebar, a **CAD** tab beside each thread that the agent drives, and *Open with CAD* for model files. It is the only app that gets the viewer inside the app. The Codex terminal shows no tabs, so the agent gives you a link.
- **Cursor** shows models in its browser. It also loads the plugin installed in Claude Code.
- **Every other app** gets the skills alone, so the agent gives you a viewer link to open in your browser.

The [viewer](/docs/viewer) is the same in a Codex tab and in the browser.

## The agents the skills reach

For an agent with no plugin command, the install command copies the skills into the agent's own skills folder. It does this for Amp, Cline, Goose, Hermes Agent, Kilo Code, Kiro CLI, OpenClaw, OpenCode, Roo Code, Trae and Windsurf, when they are installed. Kimi Code you install by hand. Zed and GitHub Copilot in VS Code are not supported yet. For any other agent, the [install page](/docs/install#other-agents) shows how to copy the skills yourself.

If your agent has no route yet, you can [request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

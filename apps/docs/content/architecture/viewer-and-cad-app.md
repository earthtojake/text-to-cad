---
title: The CAD Viewer and the CAD app
description: The two ways you see a document, in your browser and inside your agent app, and how each reaches the CAD server.
---

You look at documents in two places: the **CAD Viewer**, a page in your browser, and the **CAD app**, the same viewer drawn inside an agent app as a tab or a card. Both are views onto the one CAD server on your computer, and both draw with the same shared interface code. For how you use the viewer's tools, see the [CAD Viewer guide](/docs/guides/cad-viewer).

## The CAD Viewer

`cad viewer` opens the viewer:

```bash
cad viewer part.step
```

It starts the server if none is running (or reuses the one that is), registers each file you name, prints one URL per file, opens the first in your browser, and exits. With no file it prints the home's URL. `--no-open` prints the URL without opening a browser, and `--json` prints the launch as data. A model's script is not a document: `cad run` builds it and prints its page instead.

Every document has one address, `/<id>`: a model's id, or a file's id worked out from its path. `/` is the home, the library of documents you opened or built before. There is no hosted version: the page is served by the server on your computer, over HTTP on `127.0.0.1`.

When your agent rebuilds a model that a page is showing, the page picks up the engine's next version at once and fetches only the parts the edit changed.

### How it is built

- **The backend** is the server's own HTTP application, `cad_server.viewer`, in the `cad-server` distribution. It serves the page and the document routes under `/api/v1` on the same listener as everything else. A STEP or `.xbf` is read and meshed by the server's kernel processes, never in a request's thread.
- **The client** is a React app whose source is `apps/web`. Its production build ships inside the server's wheel, so nothing is fetched from the internet.
- **`@cad/ui`** holds the shared viewer: the file view, the CAD renderers, the home, the controls and the design system, used by both the CAD Viewer and the CAD app.
- **`@cad/core`** holds the code without React: the geometry and rendering (on Three.js) and the client that talks to the server over HTTP.

The viewer is read-only. It never changes a design or writes to your files: Export downloads a new file, and Delete on the home removes the server's record and cache of a document, not the document's file. Its tools (Select, Measure, Annotate, Quick Edit) exist to show you the design and to send feedback to your agent. A page never reads model source or starts a build.

## The CAD app

The CAD app is the viewer page drawn by an agent app through MCP Apps, an extension of the Model Context Protocol (MCP) that lets an agent app show a tool's own page. The server serves the tools, the page and its routes. What the agent app starts is `cad-mcp`, a small shim.

### The shim

`cad-mcp` is a stateless stdio program: the agent app talks to it over standard input and output, and it forwards each request over HTTP to the server's MCP endpoint, `/mcp`, with the token it reads through the server's door. It holds no tool, view or document of its own. On its own it:

- starts the current installation's server when none answers, and keeps it running while the agent app runs;
- opens a separate MCP session per shim, so closing one releases that session and leaves the server and other clients running;
- opens your browser for an agent app that shows text only, from the agent app's own environment, and tells the server whether it opened;
- tells the server which agent app started it.

### Tools

The agent opens a view with `cad_show` (and, where the host shows tabs, `cad_open` first). `cad_export`, `cad_snapshot` and `cad_inspect` work in every agent app, including text-only ones; they use the library's Python operations, never page state. The card has no Export button, because an agent app gives it nowhere to download to.

## Which agent app gets what

| Agent app | What you see |
| --- | --- |
| Codex app | A **CAD** item in the sidebar, a CAD tab beside each thread, and *Open with CAD* for a model file |
| `codex exec` and Codex's terminal interface | Text: `cad_show` opens the CAD Viewer in your browser |
| Claude Desktop, Chat tab | Viewer cards in the chat, from the server `cad setup` adds to Claude Desktop's config |
| Claude Desktop, Code tab | The same cards, from the same config entry |
| Claude Code in a terminal | No cards: the skills give you a `cad viewer` link |
| Cursor | Viewer cards in the chat |
| Other agent apps | A card where the app renders MCP Apps; otherwise the browser page |

Claude Code's plugin carries the skills alone and starts no CAD server: in Claude Desktop's Code tab the cards come from Claude Desktop's own config. [What each app gets](/docs/install#what-each-app-gets) lists the install side for every app, and [Agents](/docs/agents) covers each app in use.

## Read more

- [Architecture overview](/docs/architecture) and [The engine](/docs/architecture/engine).
- [Security and privacy](/docs/architecture/security): how the page and the card are authorised.
- [The CAD Viewer's README](repo:apps/web/README.md): launching, ports and behaviour.
- [The CAD app's README](repo:apps/mcp/README.md): presentations, the host tables and the rules.
- [The shim's README](repo:packages/cad-mcp/README.md), [`@cad/ui`](repo:packages/ui/README.md) and [`@cad/core`](repo:packages/core/README.md).

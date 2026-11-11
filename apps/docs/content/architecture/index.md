---
title: Architecture overview
description: How the plugin, the three Python distributions, the CAD server and its two views fit together on your computer.
---

text-to-cad runs on your own computer. Your agent follows the plugin's skills, writes Python scripts and runs the `cad` command. One CAD server per computer builds the models, keeps them, and serves them to the CAD Viewer in your browser and to the CAD app inside your agent app.

## The plugin

The repository root is the plugin. It holds the skills (`skills/`, one folder per skill, such as `cad`, `pcb` or `fea`) and a manifest for each kind of agent app: `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `.grok-plugin/`, `gemini-extension.json`, and the Agent Plugins standard's `plugin.json` and `mcp.json`.

A skill is a set of instructions for the agent. When you ask for a part, the agent follows the `cad` skill, writes a model script and runs `cad run model.py` to build it. Every skill that needs the server runs the `cad` command and names no release; some, such as `print3d`, never run the server. The install command gives every agent app the same plugin, from one `plugin` folder on your computer that each release writes ([What is installed where](/docs/architecture/installation-layout)).

## Three distributions, one version

text-to-cad is published as three Python distributions, always released together at the same version:

| Distribution | Imported as | What it is |
| --- | --- | --- |
| `cad` | `cad` | The library: what a model imports and what runs in a worker. The CAD kernel is its `build123d` extra. |
| `cad-server` | `cad_server` | The server: the daemon, the `cad` command, the CAD Viewer's and the CAD app's servers. |
| `cad-mcp` | `cad_mcp` | The shim: the stdio program an agent app starts for the CAD app. Standard library only. |

Where a file belongs depends on where its code runs: imported by a model or run in a worker, the library; run in the daemon or a `cad` command, the server; run inside the agent app's process, the shim. The server pins the library at its own release, because it speaks only to that release's library. `cadgen`, the library's old name, is still published at every release as a deprecated alias that installs `cad`.

## One server per computer

Your computer runs one CAD server, the current installation's. Every agent app, chat thread, skill command and CAD Viewer page shares that one daemon. The first client that finds none running starts it, and only an update moves it to another release.

The server builds nothing in its own process. It keeps a pool of warm **workers**, one per model script and Python, each holding a memo of the kernel operations it ran, so an edit costs only what it changed. Other child processes read files, mesh them and draw snapshots. Every process that loads the CAD kernel (OCP and build123d, the Python layer over OpenCASCADE) runs in an environment that has it.

The kernel is not installed up front. The first model, or the first view that needs it, makes the base environment (`cad[build123d]` at the server's release) with uv in text-to-cad's cache folder. `cad run` works like `uv run`: it runs your script in an environment the server makes, with `cad` pinned at your computer's release and the integrations your imports use. [The engine](/docs/architecture/engine) goes further.

Commands reach the server through its **door**: named pipes in a folder only you can open (on Windows, a loopback port and a token file), which works from inside an agent's sandbox that refuses every socket. Pages and the CAD app reach it over HTTP on `127.0.0.1`.

## Two views onto the same engine

- **The CAD Viewer** is a page in your browser. `cad viewer` opens it, and each document has its own address, `/<id>`. The server hosts the page and its React client.
- **The CAD app** is the same viewer inside an agent app: a tab in the Codex app, a card in the chat in Claude Desktop and other hosts that render MCP Apps. The agent app starts `cad-mcp`, which carries its requests to the server's MCP endpoint.

Both draw the same documents from the same engine with the same shared interface code, and both are read-only: changing a design belongs to the agent and the code. See [The CAD Viewer and the CAD app](/docs/architecture/viewer-and-cad-app).

## Document types and integrations

Two words organise the codebase:

- A **document type** is what is in a file text-to-cad shows: `model`, `xbf`, `step`, `glb`, `stl`, `threemf`, `dxf`, `urdf`, `sdf`, `srdf`, `kicad_pcb` and `kicad_sch`. Its id is the same in Python, the command line, the server and the viewer, and commands follow `cad <document_type> <operation> <file>`, such as `cad step snapshot`. See [Document types](/docs/document-types).
- An **integration** is support for one third-party tool, named after it: `build123d`, `kicad`, `trimesh`, `mujoco`, `coacd`, `netgen`, `calculix` and `blender`. Each is an extra of the library (`cad[kicad]`) whose environment is made the first time something needs it. See [Integrations](/docs/integrations).

One table in the library, the registry (`cad.registry`), names every type and integration, and every layer reads it.

## How the pieces talk

```text
+-------------------------------+   +----------------------+
| Agent app                     |   | Browser              |
|  skills and the agent's shell |   |  CAD Viewer page     |
|  CAD app (card or tab)        |   |  at /<id>            |
+----+------------------+-------+   +----------+-----------+
     |                  |                      |
  `cad` command,     cad-mcp shim              |
  model scripts      (stdio in, HTTP out)      |
     | door             | HTTP /mcp            | HTTP
     | (named pipes)    | 127.0.0.1:3245       | 127.0.0.1:3245
     v                  v                      v
+------------------------------------------------------------+
| CAD server: the cad-server daemon, one per computer        |
|  door and HTTP listener (viewer app, /mcp)                 |
|  registry of documents, document cache, supervisor         |
+-------+-----------------------------------+----------------+
        |                                   |
        v                                   v
+-----------------------+     +------------------------------+
| warm workers, one per |     | kernel processes             |
|  script and Python,   |     |  reading, meshing, documents |
|  memo kept in memory  |     |  worker, OCCT snapshots      |
+-----------------------+     +------------------------------+
  each runs where the CAD kernel is: the base environment,
  cad[build123d], made by uv on first need; a worker may run
  in its script's own environment instead
```

Port 3245 is the default; when another program holds it, the server takes the next free port and keeps it.

## Where to read more

- [The engine](/docs/architecture/engine), [The CAD Viewer and the CAD app](/docs/architecture/viewer-and-cad-app), [What is installed where](/docs/architecture/installation-layout) and [Security and privacy](/docs/architecture/security).
- [AGENTS.md](repo:AGENTS.md): the repository map and rules for contributors.
- [packages/README.md](repo:packages/README.md): the distributions and shared JavaScript packages.
- [The library's README](repo:packages/cad/README.md): definitions and the design laws of all three distributions.
- [The server's README](repo:packages/cad-server/README.md) and [the shim's README](repo:packages/cad-mcp/README.md).
- [The CAD Viewer's README](repo:apps/web/README.md) and [the CAD app's README](repo:apps/mcp/README.md).

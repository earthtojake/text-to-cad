# cad mcp

The stdio transport an agent app starts for cad's CAD app (`cad mcp`; `cad-mcp`, its command in releases before,
is the same entry point): it carries the app's MCP requests to the CAD server on this computer, over HTTP, and the
server's answers back. Imported as `cad_mcp`, part of the `cad` distribution; it reaches the server through the
library's client (`cad.engine.client`).

It holds no tool, view or document: the server does. What it does on its own, in order:

- **Starts the server once, as it starts**. Where cad is installed globally on this computer and this process
  is another cad (Codex's plugin line runs `cad mcp` from uvx's cache, at the plugin's release), it runs the
  installed cad's own `cad server start` and joins the server that leaves running, whatever the two releases are:
  never a server of its own, which would not be the cad the agent's shell runs and would never update itself; the
  installed cad's own update brings the server forward. Where no cad is installed and this process runs from uv's
  cache (its environment is in the folder `uv cache dir` names), it first installs cad, once, with
  `uv tool install --managed-python --python 3.14 "cad<N>"` (the newest release of this cad's major version, `N` its
  major + 1: a new major version is a person's to ask for; the Python flags are cad's own and may change with any
  release), within four minutes, and then uses the installed cad's server the same way. It never
  passes `--force`: where uv refuses or fails, no server is started from the cache, the transport's log says why,
  and every request is answered with one line, ``cad is not installed: run `uv tool install cad` ``. Run from anywhere else (a
  project's Python, a development checkout), it installs nothing and does exactly as `cad server start` does: a
  server of this release or a newer one left running and joined, one of an older release stopped first, and this
  release's started. Several started at once end with one server and one install (uv locks its tool folder). It
  starts no server after that: a server stopped later stays stopped.
- **Answers the handshake in time**: the app's `initialize` waits for the start 20 seconds at most, inside Codex's
  30-second start window, and is answered by this process past that, the server's session opened at the app's next
  request. While the start runs, a tool call is answered with a line saying the server is starting, a tool or
  resource list empty (and a list-changed notification once the start is done), anything else an error saying the
  same. `--startup-timeout SECONDS`, which server configs of releases before give, is taken and ignored.
- **Reaches the server running, never another**: each request asks the server's door for its HTTP endpoint and
  token. Where none runs, or one older than the release its start left running, a tool call is answered with cad's
  one line saying so, which
  the agent relays, and anything else with an error carrying it. Which release it accepts is decided in one place,
  `cad_mcp.shim.start_server`.
- **Holds the server** while the app runs, under a name its sessions are opened by, which end when the app quits.
- **Opens the person's browser** where a `cad_show` in an app that shows no views asks, in the app's own
  environment, never in the server's, and tells the server whether it opened.
- **Says which app started it**, read from its parent processes, which only it can see: the server offers its
  tools to the Codex app alone, told from `codex exec` and the Codex terminal UI by that program, whatever the app
  declares. `CAD_MCP_PRESENTATION=inline|tabs|text` in this process's environment is a development switch: the
  server then serves that presentation to any app, for testing.

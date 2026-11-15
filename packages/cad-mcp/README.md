# cad-mcp

The stdio transport an agent app starts for cad's CAD app (`cad-mcp`): it carries the app's MCP
requests to the CAD server on this computer, over HTTP, and the server's answers back. The standard
library alone, imported as `cad_mcp`.

It holds no tool, view or document: the server does. What it does on its own, in order:

- **Finds its version**: its own package's release (a development install names its build in
  `CAD_INSTALLATION_VERSION`). `--channel NAME` in the app's server config labels where the copy came from (a
  store's builder writes it, `cad-mcp --channel codex`); it changes nothing but the label the server counts the
  session's use under, with the app its `initialize` names.
- **Installs its version where it is missing**, as it starts, in the background, outside any sandbox: a version is
  installed when its marker is in `versions/<version>` in the state folder; where it is not, this process runs that
  release's own line, `uvx --no-config --managed-python --python 3.14 --from cad-server==<version> cad setup`.
  Where that fails (no network, uv missing), every request is answered with one line saying so and the command to
  run; nothing hangs. The app's `initialize` waits for the install at most 20 seconds, inside Codex's default
  30-second start window, or 80% of the app's startup timeout where its server config gives it as
  `--startup-timeout SECONDS`, a day at most (the rest of it is left to uvx starting this transport before the
  `initialize` arrives, and to the server's start and its own answer after): past that it is answered here and
  the server's session opened once the version is ready. Holding it matters: an app that does not act on
  `tools/list_changed` within a turn (Codex) keeps the empty list an early answer gave for the rest of that turn.
- **Never leaves a request waiting**: every wait is bounded. While its version is being installed (minutes, on a
  slow network), a request is answered here within seconds: a tool call with a result saying cad
  `<version>` is being installed and to try again shortly; a tool or resource list empty, and a list-changed
  notification once the version is ready, so the app asks again; anything else an error saying the same. The
  module documentation of `cad_mcp.shim` lists the answer for each method.
- **Starts and reaches its own version's server** alone, the way every client of that version does: through its
  door, `<version>` in the engine folder, which names the server's HTTP endpoint and token, and starts that
  version's server when none answers, never another's. From a source tree (a checkout, which has no version) it
  reaches the flat door and starts the server its own environment carries.
- **Holds the server** while the app runs, under a name its sessions are opened by, which end when the
  app quits.
- **Passes the app's requests on** and the server's answers back.
- **Opens the person's browser** where a `cad_show` in an app that shows no views asks, in the app's own
  environment, never in the server's, and tells the server whether it opened.
- **Says which app started it**, read from its parent processes, which only it can see: the server offers its
  tools to the Codex app alone, told from `codex exec` and the Codex terminal UI by that program, whatever the app
  declares. `CAD_MCP_PRESENTATION=inline|tabs|text` in this process's environment is a development switch: the
  server then serves that presentation to any app, for testing.

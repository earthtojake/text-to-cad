# cad-mcp

The stdio transport an agent app starts for text-to-cad's CAD app (`cad-mcp`): it carries the app's MCP
requests to the CAD server on this computer, over HTTP, and the server's answers back. The standard
library alone, imported as `cad_mcp`.

It holds no tool, view or document: the server does. What it does on its own:

- **Is one version on one channel.** Its version is its own package's release (a development install names
  its build in `CAD_INSTALLATION_VERSION`); its channel is `--channel NAME` in the app's server config that
  starts it, none for the default channel (`cad-mcp --channel codex`), as a store's builder writes it into the
  copy that store delivers. Nothing in its environment names a channel: `CAD_INSTALL_CHANNEL` and
  `CAD_AUTO_UPDATED`, which configs of 0.11.10 and earlier set, are not read. The server counts each session's
  use under that channel and the app its `initialize` names.
- **Makes its version ready as it starts**, in the background, outside any sandbox: its channel's pointer in
  the state folder read first, and where that names a newer version it is stale at once (below) and installs
  nothing; else installed where it is not, as the `cad` command installs one (`uvx --from
  cad-server==<version> cad setup --add --quiet`); then, where the pointer does not name it, that version's
  own `cad` run pinned to it (`cad +<version>[@<channel>] setup --add --quiet`), which moves the channel to it,
  or finds the channel past it. The app's `initialize` waits for this at most 20 seconds, inside Codex's start
  window: past that it is answered here and the server's session opened once the version is ready.
- **Never leaves a request waiting**: every wait is bounded. While its version is being installed (minutes,
  on a slow network), a request is answered here within seconds: a tool call with a result saying text-to-cad
  `<version>` is being installed and to try again shortly; a tool or resource list empty, and a list-changed
  notification once the version is ready, so the app asks again; anything else an error saying the same. The
  module documentation of `cad_mcp.shim` lists the answer for each method.
- **Reaches its own version's server** alone, the way every client of that version does: through its door,
  `<version>` in the engine folder, which names the server's HTTP endpoint and token, and starts that
  version's server when none answers, never another's.
- **Says a thread is stale**: once its channel's pointer names a newer version than its own (an update moved
  the channel while the app's thread stayed open, or the app still holds an older copy), it installs nothing,
  starts no server and connects to none, and answers every request with the line the `cad` command prints for
  a stale pin: which version it is, which its channel is on, and the repair (`cad update` for the default
  channel, the plugin's update in its app for another), then a new thread. A pointer naming an older version
  is the channel it is about to move, never stale.
- **From a source tree** (a checkout, which has no version) it reaches the server as every transport of 0.11.10
  and earlier does: the flat door, the current installation's server (`installations/current`), and on a
  computer with none, the one its environment carries registered first, else its own release's installed by
  `uvx`.
- **Holds the server** while the app runs, under a name its sessions are opened by, which end when the
  app quits.
- **Opens the person's browser** where a text-only app's `cad_show` asks, in the app's own environment,
  never in the server's, and tells the server whether it opened.
- **Says which app started it**, read from its parent processes, which only it can see.
- **Says when Claude Code started it**: `CLAUDE_CODE_ENTRYPOINT`, which Claude Code sets for every server
  it starts, in its terminal and in the Claude desktop app's Code tab, goes to the server with the host's
  `initialize`, and that session lists no tools: there CAD is the cad skill and the `cad` command. A server
  someone added to Claude Desktop's own config by hand never sees the variable, and keeps every tool.
  `CAD_MCP_CARDS=1` in this process's environment keeps the tools, for testing.
